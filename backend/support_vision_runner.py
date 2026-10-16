"""FIX14: run each supporting-vision reader batch in a fresh, owned child process.

The parent never imports or cleans SDK globals and never echoes child output. Each registered reader
batch runs in a spawned child that owns its event loop and every LiteLLM global; all parent IPC is
framed and bounded by absolute deadlines; the child is retired with a bounded graceful shutdown, then
terminate, kill and reap. A batch result reaches the caller only when the child exited 0 on its own
after a clean owned teardown; anything else, including an unregistered reader, raises
SupportVisionFailClosed.
"""
from __future__ import annotations

import asyncio
import collections
import gc
import hashlib
import importlib
import importlib.util
import inspect
import json
import linecache
import logging
import os
import pickle
import select
import struct
import subprocess
import sys
import tempfile
import threading
import time
import warnings
from copy import deepcopy
from pathlib import Path

logger = logging.getLogger(__name__)

DEADLINE_MARGIN_S = 15.0
GRACEFUL_S = 5.0
TERMINATE_S = 3.0
KILL_S = 2.0
EXIT_RESERVE_S = 1.0
_CANCEL_ROUND_S = 0.25
_DIAGNOSTIC_CHARS = 50000
_OUTPUT_TAIL_BYTES = 65536
_MAX_FRAME_BYTES = 64 * 1024 * 1024
_HEADER = struct.Struct("!Q")
_LIFECYCLE_WARNINGS = (RuntimeWarning, ResourceWarning)
OUTPUT_MARKERS = ("was never awaited", "Task was destroyed but it is pending", "Unclosed client session",
                  "Unclosed connector", "unclosed transport", "ResourceWarning", "Exception ignored in")
# aiohttp BytesPayload's advisory for a raw in-memory body > 2**20 bytes; a performance note, not a leak.
ADVISORY_ID = "AIOHTTP_LARGE_RAW_BYTES_BODY"
AIOHTTP_LARGE_BODY_ADVISORY = ("Sending a large body directly with raw bytes might lock the event loop. "
                               "You should probably pass an io.BytesIO object instead")
ISOLATED_READERS = frozenset({
    ("video_model_input", "read_video"),
    ("video_model_input", "read_text"),
    ("fix10a_vision_providers", "read_action_pixel_evidence"),
    ("fix10a_vision_providers", "read_action_video_evidence"),
    ("fix10a_vision_providers", "read_visible_player_role"),
    ("fix10a_vision_providers", "read_goal_scene_evidence"),
    ("fix10a_goal_direction", "read_field_side_evidence"),
    ("identity_verify", "read_visible_jersey_number"),
})


class SupportVisionFailClosed(RuntimeError):
    def __init__(self, record, diagnostic_results=None):
        super().__init__(f"{record['label']}: outcome={record['outcome']} lifecycle={record['lifecycle']}")
        self.record = record
        self.diagnostic_results = diagnostic_results


async def _gather_limited(function, calls, limit):
    semaphore = asyncio.Semaphore(max(1, int(limit)))

    async def one(args, kwargs):
        async with semaphore:
            return await function(*args, **kwargs)

    return await asyncio.gather(*(one(args, kwargs) for args, kwargs in calls))


def _markers(text):
    return [m for m in OUTPUT_MARKERS if m in text]


# --- framed pipe IPC: blocking without a deadline (child), bounded with one (parent) ----

def _io_wait(fd, event, deadline):
    if deadline is None:
        return
    remaining = deadline - time.monotonic()
    poller = select.poll()
    poller.register(fd, event)
    if remaining <= 0 or not poller.poll(remaining * 1000.0):
        raise TimeoutError("support vision IPC deadline")


def _write_all(fd, data, deadline=None):
    view = memoryview(data)
    while view:
        _io_wait(fd, select.POLLOUT, deadline)
        try:
            view = view[os.write(fd, view):]
        except BlockingIOError:
            pass


def _read_exact(fd, size, deadline=None):
    chunks, got = [], 0
    while got < size:
        _io_wait(fd, select.POLLIN, deadline)
        try:
            chunk = os.read(fd, min(size - got, 1 << 20))
        except BlockingIOError:
            continue
        if not chunk:
            raise EOFError("support vision channel closed")
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


def _frame(message):
    data = pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
    return _HEADER.pack(len(data)) + data


def _recv_frame(fd, deadline=None):
    size = _HEADER.unpack(_read_exact(fd, _HEADER.size, deadline))[0]
    if size > _MAX_FRAME_BYTES:
        raise EOFError("support vision frame too large")
    return pickle.loads(_read_exact(fd, size, deadline))


# --- child process side: owns its loop and every SDK global ---------------------------

def _resolve(module_name, qualname):
    target = importlib.import_module(module_name)
    for part in qualname.split("."):
        target = getattr(target, part)
    return target


def _task_identity(task):
    return {"task_name": task.get_name(),
            "stack": [f"{f.f_code.co_filename}:{f.f_lineno}:{f.f_code.co_name}" for f in task.get_stack(limit=12)]}


async def _bounded(awaitable, budget_s):
    task = asyncio.ensure_future(awaitable)
    done, _ = await asyncio.wait({task}, timeout=budget_s)
    if task not in done:
        task.cancel()
        await asyncio.wait({task}, timeout=_CANCEL_ROUND_S)
        return {"status": "TIMEOUT", "error_type": None}
    if task.cancelled():
        return {"status": "CANCELLED", "error_type": None}
    error = task.exception()
    return {"status": "DONE", "error_type": type(error).__name__ if error else None}


def _ok(step):
    return step["status"] == "DONE" and not step["error_type"]


async def _cancel_until_done(budget_s, seen):
    """Cancel every other task, re-cancelling tasks that absorbed an earlier cancellation."""
    loop = asyncio.get_running_loop()
    me = asyncio.current_task()
    deadline = loop.time() + budget_s
    rounds = 0
    while True:
        pending = {t for t in asyncio.all_tasks() if t is not me and not t.done()}
        seen.update(pending)
        if not pending or loop.time() >= deadline:
            return rounds, pending
        rounds += 1
        for task in pending:
            task.cancel()
        await asyncio.wait(pending, timeout=min(_CANCEL_ROUND_S, max(0.0, deadline - loop.time())))


def _is_litellm_worker(task):
    code = getattr(task.get_coro(), "cr_code", None)
    return bool(code and code.co_name == "_worker_loop" and "litellm" in code.co_filename)


def _open_async_clients(litellm):
    clients = []
    for client in list(getattr(litellm.in_memory_llm_clients_cache, "cache_dict", {}).values()):
        probe = getattr(client, "is_closed", None)
        try:
            is_closed = probe() if callable(probe) else probe
        except (AttributeError, TypeError, RuntimeError):
            is_closed = None
        if is_closed is False and inspect.iscoroutinefunction(getattr(client, "close", None)):
            clients.append(client)
    return clients


async def _owned_teardown(observed, budget_s):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0.5, float(budget_s))

    def left(cap):
        return max(0.05, min(cap, deadline - loop.time()))

    steps, problems = {}, []
    litellm = sys.modules.get("litellm")
    worker = None
    if litellm is not None:
        from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER as worker
        steps["litellm_logging_flush"] = await _bounded(worker.flush(), left(1.0))
        if not _ok(steps["litellm_logging_flush"]):
            problems.append("litellm_logging_flush_failed")
    seen = set()
    rounds, pending = await _cancel_until_done(left(1.5), seen)
    steps["cancel_pending_tasks"] = {
        "cancel_rounds": rounds, "tasks_seen": sorted(t.get_name() for t in seen),
        "litellm_worker_seen": any(_is_litellm_worker(t) for t in seen),
        "task_errors": [{"task_name": t.get_name(), "error_type": type(t.exception()).__name__}
                        for t in seen if t.done() and not t.cancelled() and t.exception() is not None],
        "still_pending": [_task_identity(t) for t in pending]}
    if pending:
        problems.append("pending_tasks_not_cancelled")
    elif litellm is not None:
        from litellm.llms.custom_httpx.async_client_cleanup import close_litellm_async_clients
        if steps["cancel_pending_tasks"]["litellm_worker_seen"]:
            steps["litellm_logging_stop"] = await _bounded(worker.stop(), left(0.5))
            if not _ok(steps["litellm_logging_stop"]):
                problems.append("litellm_logging_stop_failed")
        steps["close_litellm_async_clients"] = await _bounded(close_litellm_async_clients(), left(0.5))
        if not _ok(steps["close_litellm_async_clients"]):
            problems.append("close_litellm_async_clients_failed")
        steps["close_remaining_async_clients"] = [
            {"client_type": type(c).__name__, **await _bounded(c.close(), left(0.25))}
            for c in _open_async_clients(litellm)]
        steps["open_async_clients_after_cleanup"] = [type(c).__name__ for c in _open_async_clients(litellm)]
        if steps["open_async_clients_after_cleanup"]:
            problems.append("async_clients_still_open")
    for name, factory in (("shutdown_asyncgens", loop.shutdown_asyncgens),
                          ("shutdown_default_executor", loop.shutdown_default_executor)):
        steps[name] = await _bounded(factory(), left(0.5))
        if not _ok(steps[name]):
            problems.append(f"{name}_failed")
    gc.collect()
    if [w for w in observed["warnings"] if w["lifecycle"]]:
        problems.append("lifecycle_warnings_emitted")
    if observed["asyncio_errors"]:
        problems.append("asyncio_errors_logged")
    if observed["unraisable"]:
        problems.append("unraisable_exceptions")
    threads = sorted(t.name for t in threading.enumerate() if t is not threading.main_thread())
    return {"steps": steps, "problems": problems, "threads_at_teardown": threads, **observed}


def _is_aiohttp_large_body_advisory(message, category, filename, lineno):
    """Exact category + full message + the loaded aiohttp.payload BytesPayload.__init__ warn call only."""
    module = sys.modules.get("aiohttp.payload")
    code = getattr(getattr(getattr(module, "BytesPayload", None), "__init__", None), "__code__", None)
    if category is not ResourceWarning or str(message) != AIOHTTP_LARGE_BODY_ADVISORY or code is None:
        return False
    try:
        trusted = Path(module.__file__).resolve()
        same_source = Path(filename).resolve() == trusted == Path(code.co_filename).resolve()
    except (TypeError, OSError):
        return False
    in_init = lineno in {line for _start, _end, line in code.co_lines() if line}
    return same_source and in_init and linecache.getline(str(trusted), lineno).strip() == "warnings.warn("


def _install_observers():
    """Record safe category/location metadata only; message text is matched, never stored."""
    observed = {"warnings": [], "asyncio_errors": [], "unraisable": []}
    show, unraisable = warnings.showwarning, sys.unraisablehook

    def record_warning(message, category, filename, lineno, file=None, line=None):
        advisory = _is_aiohttp_large_body_advisory(message, category, filename, lineno)
        entry = {"category": category.__name__, "where": f"{Path(filename).name}:{lineno}",
                 "lifecycle": issubclass(category, _LIFECYCLE_WARNINGS) and not advisory,
                 "markers": _markers(str(message))}
        if advisory:
            entry.update(advisory=ADVISORY_ID, source=str(filename), lineno=int(lineno))
        observed["warnings"].append(entry)
        show(message, category, filename, lineno, file, line)

    def record_unraisable(info):
        observed["unraisable"].append({"error_type": type(info.exc_value).__name__,
                                       "object_type": type(info.object).__name__})
        unraisable(info)

    class _AsyncioErrors(logging.Handler):
        def emit(self, record):
            observed["asyncio_errors"].append({
                "where": f"{Path(record.pathname).name}:{record.lineno}", "level": record.levelname,
                "error_type": type(record.exc_info[1]).__name__ if record.exc_info else None,
                "markers": _markers(record.getMessage())})

    warnings.filterwarnings("default", category=ResourceWarning)
    warnings.showwarning = record_warning
    sys.unraisablehook = record_unraisable
    logging.getLogger("asyncio").addHandler(_AsyncioErrors(logging.ERROR))
    return observed


def _send(fd, message):
    try:
        data = _frame(message)
    except Exception as exc:
        data = _frame(("ERROR", type(exc).__name__))
    try:
        _write_all(fd, data)
    except OSError:
        pass


def _shutdown_budget(message, default_s):
    return float(message[1]) if message and message[0] == "SHUTDOWN" else default_s


def _serve_call(loop, request_fd, message, default_s):
    """Run one batch; a SHUTDOWN arriving mid-batch cancels it. Returns (reply, budget|None)."""
    _, module_name, qualname, calls, limit = message
    try:
        function = _resolve(module_name, qualname)
    except Exception as exc:
        return ("ERROR", type(exc).__name__), None
    task = loop.create_task(_gather_limited(function, calls, limit), name="support-vision-batch")
    control = {}

    def on_control():
        loop.remove_reader(request_fd)
        try:
            control["budget"] = _shutdown_budget(_recv_frame(request_fd), default_s)
        except (EOFError, OSError, pickle.UnpicklingError):
            control["budget"] = default_s
        task.cancel()

    loop.add_reader(request_fd, on_control)
    try:
        reply = ("RESULT", loop.run_until_complete(task))
    except asyncio.CancelledError:
        reply = ("CANCELLED", None)
    except Exception as exc:
        reply = ("ERROR", type(exc).__name__)
    if "budget" not in control:
        loop.remove_reader(request_fd)
    return reply, control.get("budget")


def _worker_main(request_fd: int, reply_fd: int) -> int:
    observed = _install_observers()
    init = _recv_frame(request_fd)
    sys.path[:0] = [p for p in init["sys_path"] if p not in sys.path]
    if init["bootstrap"]:
        importlib.import_module(init["bootstrap"])
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    budget = None
    try:
        message = _recv_frame(request_fd)
    except (EOFError, OSError, pickle.UnpicklingError):
        message = ("SHUTDOWN", init["teardown_s"])
    if message[0] == "CALL":
        reply, budget = _serve_call(loop, request_fd, message, init["teardown_s"])
        _send(reply_fd, reply)
    else:
        budget = _shutdown_budget(message, init["teardown_s"])
    if budget is None:
        try:
            budget = _shutdown_budget(_recv_frame(request_fd), init["teardown_s"])
        except (EOFError, OSError, pickle.UnpicklingError):
            budget = init["teardown_s"]
    report = loop.run_until_complete(_owned_teardown(observed, budget))
    asyncio.set_event_loop(None)
    if not report["steps"]["cancel_pending_tasks"]["still_pending"]:
        loop.close()
    report["status"] = "ERROR" if report["problems"] else "CLEAN"
    _send(reply_fd, ("TEARDOWN", report))
    return 0 if report["status"] == "CLEAN" else 3


# --- parent side: owns only its child processes; never imports or cleans SDK globals --

class _Channel:
    """Parent ends of both pipes, non-blocking; a frame cut short marks its direction broken."""

    def __init__(self, request_fd, reply_fd):
        os.set_blocking(request_fd, False)
        os.set_blocking(reply_fd, False)
        self.request_fd, self.reply_fd = request_fd, reply_fd
        self.request_intact = self.reply_intact = True

    def send(self, message, deadline):
        if not self.request_intact:
            raise EOFError("support vision request channel broken")
        _io_wait(self.request_fd, select.POLLOUT, deadline)
        try:
            _write_all(self.request_fd, _frame(message), deadline)
        except BaseException:
            self.request_intact = False
            raise

    def recv(self, deadline):
        if not self.reply_intact:
            raise EOFError("support vision reply channel broken")
        _io_wait(self.reply_fd, select.POLLIN, deadline)
        try:
            return _recv_frame(self.reply_fd, deadline)
        except BaseException:
            self.reply_intact = False
            raise

    def close_request(self):
        if self.request_fd is not None:
            os.close(self.request_fd)
            self.request_fd, self.request_intact = None, False

    def close(self):
        self.close_request()
        os.close(self.reply_fd)


def _wait(process, timeout_s):
    try:
        return process.wait(timeout=max(0.0, timeout_s))
    except subprocess.TimeoutExpired:
        return None


def _trusted_aiohttp_payload_paths():
    try:
        spec = importlib.util.find_spec("aiohttp")
    except (ImportError, ValueError):
        return set()
    return {(Path(p) / "payload.py").resolve() for p in (getattr(spec, "submodule_search_locations", None) or [])}


def _advisory_lines(teardown):
    """Exact output lines of advisories the child recorded from this interpreter's aiohttp/payload.py."""
    trusted, lines = _trusted_aiohttp_payload_paths(), []
    for w in (teardown or {}).get("warnings") or []:
        if (w.get("advisory") == ADVISORY_ID and w.get("lifecycle") is False and isinstance(w.get("lineno"), int)
                and Path(str(w.get("source"))).resolve() in trusted):
            lines.append(f"{w['source']}:{w['lineno']}: ResourceWarning: {AIOHTTP_LARGE_BODY_ADVISORY}\n")
    return lines


def _scan_output(output, teardown=None):
    """Child output is never echoed; output beyond the bounded scan fails closed, else exact advisory lines are accounted."""
    output.seek(0, os.SEEK_END)
    size = output.tell()
    output.seek(max(0, size - _OUTPUT_TAIL_BYTES))
    text = output.read().decode("utf-8", "replace")
    markers = {m: text.count(m) for m in _markers(text)}
    if size > _OUTPUT_TAIL_BYTES:
        return markers, {**markers, "OUTPUT_SCAN_INCOMPLETE": 1}, 0, size, False
    accounted = sum(min(text.count(line), n) for line, n in collections.Counter(_advisory_lines(teardown)).items())
    dangerous = {**markers, "ResourceWarning": markers.get("ResourceWarning", 0) - accounted}
    return markers, {m: n for m, n in dangerous.items() if n > 0}, accounted, size, True


class SupportVisionRunner:
    def __init__(self, *, graceful_s=GRACEFUL_S, terminate_s=TERMINATE_S, kill_s=KILL_S,
                 bootstrap=None, env=None, history=256):
        self.graceful_s, self.terminate_s, self.kill_s = float(graceful_s), float(terminate_s), float(kill_s)
        self.bootstrap = bootstrap
        self.env = dict(env or {})
        self.lifecycles = collections.deque(maxlen=history)
        self._unreaped = []
        self._lock = threading.Lock()

    def _child_env(self):
        env = dict(os.environ)
        env.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
        env.update(self.env)
        return env

    def _teardown_s(self):
        return max(0.5, self.graceful_s - EXIT_RESERVE_S)

    def _reap_stragglers(self):
        with self._lock:
            self._unreaped = [p for p in self._unreaped if p.poll() is None]
            return len(self._unreaped)

    def _spawn(self, output):
        request_r, request_w = os.pipe()
        reply_r, reply_w = os.pipe()
        try:
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--worker", str(request_r), str(reply_w)],
                pass_fds=(request_r, reply_w), stdin=subprocess.DEVNULL, stdout=output,
                stderr=subprocess.STDOUT, env=self._child_env())
        except BaseException:
            os.close(request_w)
            os.close(reply_r)
            raise
        finally:
            os.close(request_r)
            os.close(reply_w)
        return process, _Channel(request_w, reply_r)

    def _exchange(self, channel, message, deadline):
        try:
            channel.send({"sys_path": list(sys.path), "bootstrap": self.bootstrap,
                          "teardown_s": self._teardown_s()}, deadline)
            channel.send(message, deadline)
            kind, payload = channel.recv(deadline)
        except TimeoutError:
            return "DEADLINE", None
        except (EOFError, OSError):
            return "WORKER_LOST", None
        if kind == "RESULT" and isinstance(payload, list) and len(payload) == len(message[3]):
            return "RESULT", payload
        return "WORKER_ERROR", payload if kind == "ERROR" else f"unexpected_{kind}"

    def _retire(self, process, channel):
        """Bounded graceful shutdown, then terminate, then kill; reaps whenever the OS allows."""
        graceful_deadline = time.monotonic() + self.graceful_s
        teardown = late = None
        try:
            channel.send(("SHUTDOWN", self._teardown_s()), graceful_deadline)
        except (TimeoutError, EOFError, OSError):
            channel.close_request()
        while teardown is None and channel.reply_intact:
            try:
                kind, payload = channel.recv(graceful_deadline)
            except Exception:
                break
            if kind == "TEARDOWN":
                teardown = payload
            elif kind == "RESULT":
                late = payload
        forced = None
        code = _wait(process, graceful_deadline - time.monotonic())
        if code is None:
            forced = "terminate"
            process.terminate()
            code = _wait(process, self.terminate_s)
        if code is None:
            forced = "kill"
            process.kill()
            code = _wait(process, self.kill_s)
        if code is None:
            with self._lock:
                self._unreaped.append(process)
        return teardown, late, forced, code

    def run_isolated(self, module, qualname, calls, *, limit=1, deadline_s, label="support_vision"):
        calls = [(tuple(args), dict(kwargs)) for args, kwargs in calls]
        record = {"label": label, "reader": f"{module}.{qualname}", "calls": len(calls), "limit": int(limit),
                  "deadline_s": float(deadline_s), "unreaped_before": self._reap_stragglers()}
        started = time.monotonic()
        with tempfile.TemporaryFile() as output:
            process, channel = self._spawn(output)
            record["pid"] = process.pid
            try:
                try:
                    outcome, payload = self._exchange(
                        channel, ("CALL", module, qualname, calls, int(limit)), started + float(deadline_s))
                except Exception as exc:
                    outcome, payload = "WORKER_ERROR", type(exc).__name__
                record["call_elapsed_s"] = round(time.monotonic() - started, 3)
                retire_started = time.monotonic()
                teardown, late, forced, code = self._retire(process, channel)
                record["teardown_elapsed_s"] = round(time.monotonic() - retire_started, 3)
                record["ipc"] = {"request_intact": channel.request_intact, "reply_intact": channel.reply_intact}
            except BaseException:
                if process.poll() is None:
                    process.kill()
                    _wait(process, self.kill_s)
                raise
            finally:
                channel.close()
            markers, dangerous, accounted, size, scan_complete = _scan_output(output, teardown)
        if outcome == "WORKER_ERROR":
            record["worker_error"], payload = payload, None
        record.update(outcome=outcome, forced=forced, exit_code=code, reaped=code is not None,
                      teardown=teardown, output_markers=markers, dangerous_output_markers=dangerous,
                      performance_advisories=sum(bool(w.get("advisory")) for w in (teardown or {}).get("warnings") or []),
                      advisory_output_lines_accounted=accounted, output_bytes=size, output_scan_complete=scan_complete)
        if forced or code is None:
            record["lifecycle"] = "ABORTED"
        elif code == 0 and (teardown or {}).get("status") == "CLEAN" and scan_complete and not dangerous:
            record["lifecycle"] = "CLEAN"
        else:
            record["lifecycle"] = "ERROR"
        self.lifecycles.append(record)
        log = logger.info if record["lifecycle"] == "CLEAN" else logger.warning
        log("support vision %s pid=%s outcome=%s lifecycle=%s exit=%s forced=%s", label, record["pid"],
            outcome, record["lifecycle"], code, forced)
        if outcome == "RESULT" and record["lifecycle"] == "CLEAN":
            return payload
        raise SupportVisionFailClosed(deepcopy(record), payload if outcome == "RESULT" else late)


_DEFAULT = SupportVisionRunner()


def isolated_reader_ref(function):
    ref = (getattr(function, "__module__", None), getattr(function, "__qualname__", None))
    module = sys.modules.get(ref[0]) if ref in ISOLATED_READERS else None
    return ref if module is not None and getattr(module, ref[1], None) is function else None


def run_support_vision(function, calls, *, limit=1, deadline_s, label="support_vision"):
    """Only registered production readers run, always in an owned child; anything else fails closed."""
    ref = isolated_reader_ref(function)
    if ref is None:
        raise SupportVisionFailClosed({"label": label, "reader": str(getattr(function, "__qualname__", "?"))[:120],
                                       "outcome": "UNREGISTERED_READER", "lifecycle": "NOT_STARTED"})
    return _DEFAULT.run_isolated(*ref, calls, limit=limit, deadline_s=deadline_s, label=label)


def support_vision_lifecycles():
    return list(_DEFAULT.lifecycles)


def fail_closed_diagnostic(exc, index=0):
    """Inert diagnostic copy of a pre-teardown read; never usable as evidence or proof."""
    if not isinstance(exc, SupportVisionFailClosed):
        return {}
    diagnostic = None
    results = exc.diagnostic_results
    if isinstance(results, list) and 0 <= index < len(results):
        text = json.dumps(results[index], sort_keys=True, default=str)
        diagnostic = {"json": text[:_DIAGNOSTIC_CHARS], "truncated": len(text) > _DIAGNOSTIC_CHARS,
                      "sha256": hashlib.sha256(text.encode()).hexdigest()}
    return {"support_vision_fail_closed": {"proof_eligible": False, "lifecycle": deepcopy(exc.record),
                                           "diagnostic_pre_teardown_result": diagnostic}}


if __name__ == "__main__" and sys.argv[1:2] == ["--worker"]:
    sys.exit(_worker_main(int(sys.argv[2]), int(sys.argv[3])))
