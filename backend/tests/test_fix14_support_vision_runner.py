"""FIX14: process-isolated supporting-vision runner, offline only.

Mechanics tests run test-only coroutines (fix14_offline_child) in fresh children. SDK tests run the
five production readers through the installed emergentintegrations + LiteLLM against a loopback
fake chat-completions server with dummy keys; the child allows loopback sockets only. Repeated reads
are sequential batches from this one pytest process, and each batch owns a fresh child (jersey and
role batches keep limit=3 / limit=2 inside that one child).
"""

import ast
import fcntl
import gc
import importlib.util
import inspect
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import warnings
from pathlib import Path

import cv2
import numpy as np
import pytest

import action_evidence_review as inspection
import fix10a_goal_direction as gd
import fix10a_vision_providers as vp
import identity_verify as iv
import support_vision_runner as svr

BACKEND = Path(__file__).resolve().parents[1]
CHILD = "fix14_offline_child"  # never imported here: it patches sockets in the importing process
PROXY_KEY = "sk-emergent-fix14dummy0000"
OPENAI_KEY = "sk-fix14-dummy-openai-key"
try:
    from emergentintegrations.llm.chat import LlmChat

    REAL_SDK = "litellm" in sys.modules and hasattr(LlmChat, "_build_completion_params")
except ImportError:
    REAL_SDK = False
sdk = pytest.mark.skipif(not REAL_SDK, reason="installed emergentintegrations + litellm required")


def _children():
    me, out = os.getpid(), set()
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        except OSError:
            continue
        if int(fields[1]) == me:
            out.add(int(pid))
    return out


def _litellm_state():
    lite = sys.modules.get("litellm")
    if lite is None:
        return None
    from litellm.litellm_core_utils.logging_worker import (
        GLOBAL_LOGGING_WORKER as worker,
    )

    return (len(getattr(lite.in_memory_llm_clients_cache, "cache_dict", {})), id(worker._worker_task), id(worker._queue))


@pytest.fixture(autouse=True)
def parent_hygiene():
    threads, children, lite = {t.ident for t in threading.enumerate()}, _children(), _litellm_state()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        yield
        gc.collect()
    assert not [str(w.message) for w in caught if issubclass(w.category, (RuntimeWarning, ResourceWarning))]
    assert {t.ident for t in threading.enumerate()} <= threads, "parent thread leaked"
    assert _children() <= children, "child process left running or unreaped"
    assert _litellm_state() == lite, "parent LiteLLM globals changed"


def _runner(**kwargs):
    return svr.SupportVisionRunner(bootstrap=CHILD, **kwargs)


def _fail_closed(call):
    with pytest.raises(svr.SupportVisionFailClosed) as info:
        call()
    return info.value


# --- registry, wiring and fingerprint ---------------------------------------------------

READER_FUNCTIONS = {
    "read_action_pixel_evidence": vp.read_action_pixel_evidence,
    "read_visible_player_role": vp.read_visible_player_role,
    "read_goal_scene_evidence": vp.read_goal_scene_evidence,
    "read_visible_jersey_number": iv.read_visible_jersey_number,
}


def test_exactly_the_seven_production_readers_are_registered_for_isolation():
    import video_model_input
    functions = {**READER_FUNCTIONS, "read_action_video_evidence": vp.read_action_video_evidence,
        "read_video": video_model_input.read_video, "read_text": video_model_input.read_text}
    assert {q for _m, q in svr.ISOLATED_READERS} == set(functions)
    for name, function in functions.items():
        assert svr.isolated_reader_ref(function) == (function.__module__, name)


@pytest.mark.parametrize(
    "module, expected",
    [
        (
            "fix10a_vision_providers.py",
            [
                "read_action_video_evidence",
                "read_action_pixel_evidence",
                "read_visible_jersey_number",
                "read_visible_player_role",
                "read_goal_scene_evidence",
            ],
        ),
        ("fix10a_goal_direction.py", []),
    ],
)
def test_call_sites_pass_registered_readers_inside_fail_closed_try(module, expected):
    tree = ast.parse((BACKEND / module).read_text())
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert not [n for n in calls if n.func.attr == "run" and getattr(n.func.value, "id", None) == "asyncio"]
    # Ordered geometry yields its registered reader request inside the same
    # exception boundary; the dispatcher executes only the owned-child runner
    # and throws failures back into that generator before evidence is parsed.
    sites = [(n, n.args[0]) for n in calls if n.func.attr == "run_support_vision"]
    sites.extend((n, n.value.elts[0]) for n in ast.walk(tree)
                 if isinstance(n, ast.Yield) and isinstance(n.value, ast.Tuple)
                 and len(n.value.elts) == 4)
    sites.sort(key=lambda pair: pair[0].lineno)
    assert [getattr(reader, "id", None) or reader.attr for _site, reader in sites] == expected
    for site, _reader in sites:
        if isinstance(site, ast.Call):
            assert any(k.arg == "deadline_s" for k in site.keywords)
        else:
            assert "DEADLINE_MARGIN_S" in ast.unparse(site.value.elts[2])
        node = site
        while not (isinstance(parents.get(node), ast.Try) and node in parents[node].body):
            node = parents[node]
        assert any(getattr(h.type, "id", None) == "Exception" for h in parents[node].handlers)


def test_ordered_dispatch_still_uses_owned_runner_and_forwards_deadline():
    tree = ast.parse((BACKEND / "ordered_vision_reviews.py").read_text())
    read = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "read")
    calls = [n for n in ast.walk(read) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "run_support_vision"]
    assert len(calls) == 1
    assert any(k.arg == "deadline_s" and isinstance(k.value, ast.Name) and k.value.id == "deadline"
               for k in calls[0].keywords)
    assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) and
                   (getattr(n, "module", "") or "").startswith(("litellm", "emergentintegrations"))
                   for n in ast.walk(tree))


def test_parent_side_never_touches_sdk_globals_and_runner_is_fingerprinted():
    tree = ast.parse((BACKEND / "support_vision_runner.py").read_text())
    top_imports = {
        a.name.split(".")[0] for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names
    } | {n.module.split(".")[0] for n in tree.body if isinstance(n, ast.ImportFrom) and n.module}
    assert not top_imports & {"litellm", "emergentintegrations"}
    parent = [
        n
        for n in tree.body
        if getattr(n, "name", None)
        in {
            "_Channel",
            "SupportVisionRunner",
            "run_support_vision",
            "isolated_reader_ref",
            "fail_closed_diagnostic",
            "_wait",
            "_scan_output",
        }
    ]
    parent_source = "".join(ast.unparse(n) for n in parent)
    assert len(parent) == 7 and "litellm" not in parent_source
    assert "asyncio.run(" not in ast.unparse(tree) and "stderr.write" not in ast.unparse(tree)
    export = ast.parse((BACKEND / "report_evidence_export.py").read_text())
    modules = next(
        ast.literal_eval(n.value)
        for n in ast.walk(export)
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "SOURCE_MODULES" for t in n.targets)
    )
    assert "support_vision_runner.py" in modules


async def _double(value):
    return value * 2


def test_unregistered_reader_fails_closed_without_starting_a_child(monkeypatch):
    runner = _runner()
    monkeypatch.setattr(svr, "_DEFAULT", runner)
    error = _fail_closed(lambda: svr.run_support_vision(_double, [((2,), {})], deadline_s=5))
    assert (error.record["outcome"], error.record["lifecycle"]) == ("UNREGISTERED_READER", "NOT_STARTED")
    assert not runner.lifecycles and error.diagnostic_results is None


def test_inline_reader_doubles_require_the_explicit_test_fixture(inline_support_vision):
    assert svr.run_support_vision(_double, [((2,), {}), ((5,), {})], limit=2, deadline_s=5) == [4, 10]


# --- child lifecycle mechanics (no SDK) -------------------------------------------------


def test_sequential_batches_each_own_a_fresh_child_that_exits_clean():
    runner = _runner()
    assert runner.run_isolated(CHILD, "echo", [(("a",), {})], deadline_s=20) == ["a"]
    assert runner.run_isolated(CHILD, "echo", [(("b",), {}), (("c",), {})], limit=2, deadline_s=20) == ["b", "c"]
    first, second = runner.lifecycles
    assert first["pid"] != second["pid"]
    for record in (first, second):
        assert (record["outcome"], record["lifecycle"], record["exit_code"], record["forced"]) == (
            "RESULT",
            "CLEAN",
            0,
            None,
        )
        assert record["reaped"] and record["teardown"]["status"] == "CLEAN" and not record["output_markers"]


def test_child_teardown_recancels_a_task_that_absorbed_one_cancellation():
    runner = _runner()
    assert runner.run_isolated(CHILD, "resistant_task_then", [(("READ",), {})], deadline_s=20) == ["READ"]
    record = runner.lifecycles[-1]
    drain = record["teardown"]["steps"]["cancel_pending_tasks"]
    assert record["lifecycle"] == "CLEAN" and drain["cancel_rounds"] >= 2 and not drain["still_pending"]
    assert "fix14-resistant" in drain["tasks_seen"]


def test_uncancellable_leftover_task_fails_closed_and_keeps_inert_diagnostic():
    runner = _runner()
    error = _fail_closed(lambda: runner.run_isolated(CHILD, "uncancellable_task_then", [(("READ",), {})], deadline_s=20))
    record = error.record
    assert (record["outcome"], record["lifecycle"], record["exit_code"], record["forced"]) == ("RESULT", "ERROR", 3, None)
    assert "pending_tasks_not_cancelled" in record["teardown"]["problems"]
    assert error.diagnostic_results == ["READ"]
    block = svr.fail_closed_diagnostic(error)["support_vision_fail_closed"]
    assert block["proof_eligible"] is False and json.loads(block["diagnostic_pre_teardown_result"]["json"]) == "READ"
    assert runner.run_isolated(CHILD, "echo", [(("after",), {})], deadline_s=20) == ["after"]


def test_deadline_with_cancel_absorbing_reader_is_terminated_after_graceful_budget():
    runner = _runner()
    error = _fail_closed(lambda: runner.run_isolated(CHILD, "ignore_cancel_forever", [((), {})], deadline_s=1.0))
    record = error.record
    assert (record["outcome"], record["lifecycle"], record["forced"]) == ("DEADLINE", "ABORTED", "terminate")
    assert record["exit_code"] == -signal.SIGTERM and record["reaped"] and error.diagnostic_results is None
    assert svr.GRACEFUL_S - 0.2 <= record["teardown_elapsed_s"] < svr.GRACEFUL_S + svr.TERMINATE_S
    assert runner.run_isolated(CHILD, "echo", [(("after",), {})], deadline_s=20) == ["after"]


def test_sigterm_ignoring_child_is_killed_and_reaped():
    runner = _runner()
    error = _fail_closed(lambda: runner.run_isolated(CHILD, "ignore_sigterm_and_block", [((), {})], deadline_s=1.0))
    record = error.record
    assert (record["outcome"], record["lifecycle"], record["forced"]) == ("DEADLINE", "ABORTED", "kill")
    assert record["exit_code"] == -signal.SIGKILL and record["reaped"]
    budget = svr.GRACEFUL_S + svr.TERMINATE_S
    assert budget - 0.2 <= record["teardown_elapsed_s"] < budget + svr.KILL_S
    assert runner.run_isolated(CHILD, "echo", [(("after",), {})], deadline_s=20) == ["after"]


def test_child_exit_without_reply_fails_closed():
    runner = _runner()
    error = _fail_closed(lambda: runner.run_isolated(CHILD, "hard_exit", [((), {})], deadline_s=20))
    assert (error.record["outcome"], error.record["lifecycle"], error.record["exit_code"]) == ("WORKER_LOST", "ERROR", 7)
    assert error.diagnostic_results is None


def test_forced_teardown_after_parsed_result_fails_closed_with_diagnostic():
    runner = _runner(graceful_s=0.0)
    error = _fail_closed(lambda: runner.run_isolated(CHILD, "echo", [(("kept",), {})], deadline_s=20))
    assert (error.record["outcome"], error.record["lifecycle"], error.record["forced"]) == ("RESULT", "ABORTED", "terminate")
    assert error.diagnostic_results == ["kept"]


def test_child_blocks_external_sockets(tmp_path):
    blocked = tmp_path / "blocked.log"
    result = _runner(env={"FIX14_TEST_BLOCKED_LOG": str(blocked)}).run_isolated(
        CHILD, "external_connect", [((), {})], deadline_s=20
    )
    assert result[0].startswith("blocked:") and blocked.read_text().split() == ["203.0.113.10"]


def test_child_output_is_counted_but_never_echoed(capfd):
    runner = _runner()
    assert runner.run_isolated(CHILD, "print_then", [(("ok",), {})], deadline_s=20) == ["ok"]
    out = capfd.readouterr()
    assert "FIX14-CHILD-OUTPUT" not in out.out + out.err
    assert runner.lifecycles[-1]["output_bytes"] > 0 and runner.lifecycles[-1]["lifecycle"] == "CLEAN"


def _pipe_capacity():
    read_fd, write_fd = os.pipe()
    try:
        return fcntl.fcntl(write_fd, 1032)  # F_GETPIPE_SZ
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_parent_deadline_bounds_a_request_larger_than_pipe_capacity_while_child_stalls():
    payload = "x" * (8 * _pipe_capacity())
    runner = _runner(env={"FIX14_TEST_STALL_BEFORE_CALL_S": "600"})
    started = time.monotonic()
    error = _fail_closed(lambda: runner.run_isolated(CHILD, "echo", [((payload,), {})], deadline_s=2.0))
    elapsed, record = time.monotonic() - started, error.record
    assert (record["outcome"], record["lifecycle"], record["forced"]) == ("DEADLINE", "ABORTED", "terminate")
    assert record["exit_code"] == -signal.SIGTERM and record["reaped"] and record["ipc"]["request_intact"] is False
    assert record["call_elapsed_s"] < 2.5 and elapsed < 2.0 + svr.GRACEFUL_S + svr.TERMINATE_S + 1.0


def test_parent_deadline_bounds_a_partial_stalled_reply_and_kills_a_sigterm_ignoring_child():
    runner = _runner(env={"FIX14_TEST_IGNORE_SIGTERM": "1"})
    started = time.monotonic()
    error = _fail_closed(lambda: runner.run_isolated(CHILD, "partial_reply_then_stall", [((), {})], deadline_s=3.0))
    elapsed, record = time.monotonic() - started, error.record
    assert (record["outcome"], record["lifecycle"], record["forced"]) == ("DEADLINE", "ABORTED", "kill")
    assert record["exit_code"] == -signal.SIGKILL and record["reaped"] and record["ipc"]["reply_intact"] is False
    budget = 3.0 + svr.GRACEFUL_S + svr.TERMINATE_S + svr.KILL_S
    assert record["call_elapsed_s"] < 3.5 and elapsed < budget and error.diagnostic_results is None


def test_concurrent_parent_threads_get_independent_children():
    runner, results = _runner(), {}

    def call(name):
        results[name] = runner.run_isolated(CHILD, "echo", [((name,), {})], deadline_s=20)

    workers = [threading.Thread(target=call, args=(name,)) for name in ("x", "y")]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(30)
    assert results == {"x": ["x"], "y": ["y"]}
    assert len({r["pid"] for r in runner.lifecycles}) == 2
    assert all(r["lifecycle"] == "CLEAN" for r in runner.lifecycles)


# --- aiohttp large raw-bytes body advisory: recorded and visible, never a lifecycle leak ---------

needs_aiohttp = pytest.mark.skipif(importlib.util.find_spec("aiohttp") is None, reason="installed aiohttp required")


def _advisory_where():
    import aiohttp.payload

    lines, start = inspect.getsourcelines(aiohttp.payload.BytesPayload.__init__)
    return f"payload.py:{next(start + i for i, text in enumerate(lines) if 'warnings.warn(' in text)}"


def _assert_one_visible_advisory(record):
    advisories = [w for w in record["teardown"]["warnings"] if w.get("advisory")]
    assert [(w["category"], w["advisory"], w["lifecycle"], w["where"]) for w in advisories] == [
        ("ResourceWarning", svr.ADVISORY_ID, False, _advisory_where())
    ]
    assert record["teardown"]["status"] == "CLEAN" and record["teardown"]["problems"] == []
    assert record["output_markers"] == {"ResourceWarning": 1} and record["dangerous_output_markers"] == {}
    assert record["advisory_output_lines_accounted"] == 1 and record["performance_advisories"] == 1


def _evidence(record_property, name, record, **extra):
    keep = ("outcome", "lifecycle", "exit_code", "forced", "reaped", "output_markers", "dangerous_output_markers",
            "advisory_output_lines_accounted", "performance_advisories", "output_bytes")
    teardown = record.get("teardown") or {}
    record_property(name, json.dumps({**{k: record.get(k) for k in keep}, "problems": teardown.get("problems"),
                                      "warnings": teardown.get("warnings"), **extra}, sort_keys=True))


@needs_aiohttp
def test_genuine_aiohttp_large_body_advisory_stays_visible_and_clean(record_property):
    runner = _runner()
    assert runner.run_isolated(CHILD, "genuine_large_body_advisory_then", [(("READ",), {})], deadline_s=20) == ["READ"]
    record = runner.lifecycles[-1]
    _evidence(record_property, "genuine_advisory_child", record)
    assert (record["outcome"], record["lifecycle"], record["exit_code"], record["forced"], record["reaped"]) == (
        "RESULT",
        "CLEAN",
        0,
        None,
        True,
    )
    _assert_one_visible_advisory(record)


@needs_aiohttp
@pytest.mark.parametrize("extra", ["copy", "other"])
def test_extra_unaccounted_resource_warning_output_fails_closed(extra, record_property):
    runner = _runner()
    error = _fail_closed(
        lambda: runner.run_isolated(
            CHILD, "genuine_large_body_advisory_then", [(("READ",), {"extra_output": extra})], deadline_s=20
        )
    )
    record = error.record
    _evidence(record_property, f"extra_output_{extra}", record)
    assert (record["outcome"], record["lifecycle"], record["exit_code"], record["teardown"]["status"]) == (
        "RESULT",
        "ERROR",
        0,
        "CLEAN",
    )
    assert record["output_markers"] == {"ResourceWarning": 2} and record["dangerous_output_markers"] == {"ResourceWarning": 1}
    assert record["advisory_output_lines_accounted"] == 1 and error.diagnostic_results == ["READ"]


@needs_aiohttp
@pytest.mark.parametrize("where", ["other_file", "other_line"])
def test_advisory_text_from_an_unrelated_source_fails_closed(where, record_property):
    error = _fail_closed(
        lambda: _runner().run_isolated(
            CHILD, "advisory_text_from_unrelated_source_then", [(("READ",), {"where": where})], deadline_s=20
        )
    )
    record = error.record
    _evidence(record_property, f"unrelated_source_{where}", record)
    assert (record["outcome"], record["lifecycle"], record["exit_code"]) == ("RESULT", "ERROR", 3)
    assert record["teardown"]["problems"] == ["lifecycle_warnings_emitted"]
    assert not [w for w in record["teardown"]["warnings"] if w.get("advisory")] and record["performance_advisories"] == 0
    assert record["dangerous_output_markers"] == {"ResourceWarning": 1} and record["advisory_output_lines_accounted"] == 0


def test_unknown_resource_warning_fails_closed(record_property):
    error = _fail_closed(lambda: _runner().run_isolated(CHILD, "unknown_resource_warning_then", [(("READ",), {})], deadline_s=20))
    record = error.record
    _evidence(record_property, "unknown_resource_warning", record)
    assert (record["outcome"], record["lifecycle"], record["exit_code"]) == ("RESULT", "ERROR", 3)
    assert record["teardown"]["problems"] == ["lifecycle_warnings_emitted"]
    assert record["dangerous_output_markers"].get("ResourceWarning", 0) >= 1 and record["advisory_output_lines_accounted"] == 0


@needs_aiohttp
def test_real_unclosed_client_session_leak_fails_closed(record_property):
    error = _fail_closed(lambda: _runner().run_isolated(CHILD, "leaked_client_session_then", [(("READ",), {})], deadline_s=20))
    record = error.record
    _evidence(record_property, "real_client_session_leak", record)
    assert (record["outcome"], record["lifecycle"], record["exit_code"]) == ("RESULT", "ERROR", 3)
    assert {"lifecycle_warnings_emitted", "asyncio_errors_logged"} <= set(record["teardown"]["problems"])
    assert not [w for w in record["teardown"]["warnings"] if w.get("advisory")]
    assert record["dangerous_output_markers"].get("Unclosed client session", 0) >= 1


@needs_aiohttp
def test_unaccounted_output_beyond_scan_cap_rejects_clean_genuine_advisory_result(record_property):
    kwargs = {"leading": b"ResourceWarning: fix14 unaccounted early output\n", "filler_lines": 40000}
    error = _fail_closed(
        lambda: _runner().run_isolated(CHILD, "output_around_genuine_advisory_then", [(("READ",), kwargs)], deadline_s=20)
    )
    record = error.record
    _evidence(record_property, "beyond_scan_cap", record, output_scan_complete=record["output_scan_complete"])
    assert (record["outcome"], record["exit_code"], record["teardown"]["status"], record["teardown"]["problems"]) == (
        "RESULT",
        0,
        "CLEAN",
        [],
    )
    assert record["lifecycle"] == "ERROR" and record["output_scan_complete"] is False
    assert record["output_bytes"] > svr._OUTPUT_TAIL_BYTES and record["performance_advisories"] == 1
    assert record["dangerous_output_markers"].get("OUTPUT_SCAN_INCOMPLETE") == 1
    assert record["advisory_output_lines_accounted"] == 0 and error.diagnostic_results == ["READ"]


@needs_aiohttp
@pytest.mark.parametrize("extra_bytes, lifecycle", [(0, "CLEAN"), (1, "ERROR")])
def test_scan_cap_boundary_with_genuine_advisory(extra_bytes, lifecycle, record_property):
    runner, total = _runner(), svr._OUTPUT_TAIL_BYTES + extra_bytes
    call = [(("READ",), {"pad_to": total})]
    if lifecycle == "CLEAN":
        assert runner.run_isolated(CHILD, "output_around_genuine_advisory_then", call, deadline_s=20) == ["READ"]
        record = runner.lifecycles[-1]
    else:
        record = _fail_closed(
            lambda: runner.run_isolated(CHILD, "output_around_genuine_advisory_then", call, deadline_s=20)
        ).record
    _evidence(record_property, f"scan_cap_boundary_{total}", record, output_scan_complete=record["output_scan_complete"])
    assert record["output_bytes"] == total and record["exit_code"] == 0 and record["teardown"]["status"] == "CLEAN"
    assert record["lifecycle"] == lifecycle and record["output_scan_complete"] is (lifecycle == "CLEAN")
    if lifecycle == "CLEAN":
        _assert_one_visible_advisory(record)
    else:
        assert record["dangerous_output_markers"] == {"ResourceWarning": 1, "OUTPUT_SCAN_INCOMPLETE": 1}
        assert record["advisory_output_lines_accounted"] == 0


# --- installed SDK + loopback fake HTTP ---------------------------------------------------


@pytest.mark.parametrize("count", [1, 2, 4])
def test_fake_action_server_success_covers_actual_image_parts_and_retains_partial_mode(count):
    from fix14_fake_llm_server import response_content

    messages = [
        {"role": "system", "content": "image_url in text is not an image"},
        {"role": "user", "content": [{"type": "text", "text": "inspect image_url"}] + [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,synthetic"}} for _ in range(count)
        ]},
    ]
    complete = vp._action_pixel_response(response_content("action", messages, "success"), list(range(count)))
    assert complete["status"] == "COMPLETED" and complete["returned_frame_indices"] == list(range(1, count + 1))
    partial = response_content("action", messages, "partial_action")
    assert [row["idx"] for row in partial["frames"]] == [1]


@pytest.mark.parametrize("count", [1, 2, 4])
def test_fake_goal_server_success_explicitly_covers_hidden_images_and_retains_partial_mode(count):
    from fix14_fake_llm_server import response_content
    messages = [{"content": [{"type": "text", "text": "image_url is not an image"}] + [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,synthetic"}} for _ in range(count)
    ]}]
    complete = vp._goal_scene_response_coverage(response_content("goal", messages, "success"), list(range(count)))
    assert complete["status"] == "COMPLETED"
    partial = vp._goal_scene_response_coverage(response_content("goal", messages, "partial_goal"), list(range(count)))
    assert partial["status"] == "PARTIAL_RESPONSE"
    assert partial["missing_frame_indices"] == {"frames": [count], "ball_evidence": []}


@pytest.fixture(scope="module")
def fake_server():
    server = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("fix14_fake_llm_server.py"))], stdout=subprocess.PIPE, text=True
    )
    port = int(server.stdout.readline())
    yield port
    server.terminate()
    server.wait(10)
    server.stdout.close()


BLOCKED_LOG = [os.devnull]


@pytest.fixture(scope="module", autouse=True)
def _route_blocked_log(blocked_log):
    BLOCKED_LOG[0] = blocked_log
    yield
    BLOCKED_LOG[0] = os.devnull


def _ctl(port, mode=None):
    data = json.dumps({"mode": mode}).encode() if mode else None
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/{'__mode' if mode else '__state'}", data, 10) as response:
        return json.loads(response.read())


def _sdk_runner(port, graceful_s=svr.GRACEFUL_S, **env):
    env.setdefault("FIX14_TEST_BLOCKED_LOG", str(BLOCKED_LOG[0]))
    return _runner(
        graceful_s=graceful_s,
        env={
            "INTEGRATION_PROXY_URL": f"http://127.0.0.1:{port}",
            "OPENAI_BASE_URL": f"http://127.0.0.1:{port}/v1",
            "OPENAI_API_BASE": f"http://127.0.0.1:{port}/v1",
            **env,
        },
    )


@pytest.fixture(scope="module")
def blocked_log(tmp_path_factory):
    path = tmp_path_factory.mktemp("fix14_blocked") / "blocked.log"
    path.write_text("")
    yield path
    assert path.read_text() == "", "a child attempted an external connection"


@pytest.fixture(scope="module")
def images(tmp_path_factory):
    root, rng = tmp_path_factory.mktemp("fix14_synthetic"), np.random.default_rng(14)
    paths = [str(root / f"synthetic_{i}.jpg") for i in range(3)]
    for path in paths:
        assert cv2.imwrite(path, rng.integers(0, 255, (96, 64, 3), dtype=np.uint8))
    return paths


def _reader_call(kind, images, key):
    a, b, c = images
    return {
        "action": (vp.read_action_pixel_evidence, ((key, "fix14-action", [a, b], [1000, 1040]), {"body_candidates": []})),
        "role": (vp.read_visible_player_role, ((key, "fix14-role", a, b), {})),
        "goal": (vp.read_goal_scene_evidence, ((key, "fix14-goal", [a, b, c], [1000, 1040, 1080]), {})),
        "number": (iv.read_visible_jersey_number, ((key, "fix14-number", a), {})),
    }[kind]


PARSED = {
    "action": lambda r: (
        r["status"] == "COMPLETED" and r["reason"] == "PIXEL_PROPOSALS_ONLY" and len(r["response_sha256"]) == 64
    ),
    "role": lambda r: r["role"] == "OUTFIELD" and "model_review_audit" in r,
    "goal": lambda r: r["reason"] == "fake offline server" and r["proof_ready"] is False and "model_review_audit" in r,
    "number": lambda r: r["readable"] is True and r["number"] == "88" and "model_review_audit" in r,
}
READER_FAIL_CLOSED = {
    "action": lambda r: (r["status"], r["reason"], r["frames"]) == ("ERROR", "action_pixel_reader_error", []),
    "role": lambda r: (r["role"], r["reason"]) == ("UNKNOWN", "role_reader_error"),
    "goal": lambda r: r["reason"] == "goal_scene_reader_error" and r["proof_ready"] is False,
    "number": lambda r: r["readable"] is False and r["reason"] == "reader_error",
}
KINDS = sorted(PARSED)


def _read(runner, port, kind, images, key, mode, deadline_s=60, monkeypatch=None):
    monkeypatch.setattr(svr, "_DEFAULT", runner)
    _ctl(port, mode)
    function, call = _reader_call(kind, images, key)
    return svr.run_support_vision(function, [call], deadline_s=deadline_s, label=f"fix14-{kind}")[0]


@sdk
@pytest.mark.parametrize("key", [PROXY_KEY, OPENAI_KEY])
def test_installed_sdk_action_partial_response_does_not_complete_or_retry(key, fake_server, images, monkeypatch):
    runner = _sdk_runner(fake_server)
    result = _read(runner, fake_server, "action", images, key, "partial_action", monkeypatch=monkeypatch)
    assert result["status"] == "PARTIAL_RESPONSE"
    assert result["returned_frame_indices"] == [1] and result["missing_frame_indices"] == [2]
    assert result["missing_media_ms"] == [1040] and len(result["frames"]) == 1
    assert len(_ctl(fake_server)["log"]) == 1 and len(runner.lifecycles) == 1
    assert runner.lifecycles[0]["lifecycle"] == "CLEAN" and BLOCKED_LOG[0].read_text() == ""


@sdk
@pytest.mark.parametrize("key", [PROXY_KEY, OPENAI_KEY])
def test_installed_sdk_goal_partial_response_does_not_complete_or_retry(key, fake_server, images, monkeypatch):
    runner = _sdk_runner(fake_server)
    result = _read(runner, fake_server, "goal", images, key, "partial_goal", monkeypatch=monkeypatch)
    assert result["response_coverage"]["status"] == "PARTIAL_RESPONSE"
    assert result["response_coverage"]["missing_frame_indices"] == {"frames": [3], "ball_evidence": []}
    assert result["proof_ready"] is False and result["crossing"] == "UNRESOLVED"
    assert result["geometry_status"] == "UNRESOLVED" and result["frames"] == []
    assert len(_ctl(fake_server)["log"]) == 1 and len(runner.lifecycles) == 1
    assert runner.lifecycles[0]["lifecycle"] == "CLEAN" and BLOCKED_LOG[0].read_text() == ""


@sdk
@pytest.mark.parametrize("kind", KINDS)
def test_installed_sdk_proxy_branch_success_error_timeout_cancel_then_success(kind, fake_server, images, monkeypatch):
    runner, short = _sdk_runner(fake_server), _sdk_runner(fake_server, FIX14_TEST_REQUEST_TIMEOUT_S="1.5")
    read = lambda r, mode, **kw: _read(r, fake_server, kind, images, PROXY_KEY, mode, monkeypatch=monkeypatch, **kw)  # noqa: E731
    first = read(runner, "success")
    function, call = _reader_call(kind, images, PROXY_KEY)
    second = svr.run_support_vision(function, [call], deadline_s=60)[0]
    assert PARSED[kind](first) and PARSED[kind](second)
    log = _ctl(fake_server)["log"]
    assert [(e["path"], e["kind"], e["model"], e["auth_scheme"], e["key_prefix"]) for e in log] == [
        ("/llm/chat/completions", kind, "gpt-4o", "Bearer", PROXY_KEY[:12])
    ] * 2 and all(e["images"] for e in log)
    assert READER_FAIL_CLOSED[kind](read(runner, "api_error"))
    started = time.monotonic()
    assert READER_FAIL_CLOSED[kind](read(short, "hang"))
    assert time.monotonic() - started < 15
    error = _fail_closed(lambda: read(runner, "hang", deadline_s=6))
    assert error.record["outcome"] == "DEADLINE" and error.record["reaped"] and error.diagnostic_results is None
    assert error.record["lifecycle"] == "CLEAN", error.record
    assert PARSED[kind](read(runner, "success"))
    records = [*runner.lifecycles, *short.lifecycles]
    assert len(records) == 6 and len({r["pid"] for r in records}) == 6
    assert all(r["lifecycle"] == "CLEAN" and r["exit_code"] == 0 for r in records), records
    assert BLOCKED_LOG[0].read_text() == ""


@sdk
@pytest.mark.parametrize("kind", KINDS)
def test_installed_sdk_openai_branch_two_sequential_reads(kind, fake_server, images, monkeypatch):
    runner = _sdk_runner(fake_server)
    for _ in range(2):
        assert PARSED[kind](_read(runner, fake_server, kind, images, OPENAI_KEY, "success", monkeypatch=monkeypatch))
        assert [(e["path"], e["key_prefix"]) for e in _ctl(fake_server)["log"]] == [
            ("/v1/chat/completions", OPENAI_KEY[:12])
        ]
    assert [r["lifecycle"] for r in runner.lifecycles] == ["CLEAN", "CLEAN"]
    assert BLOCKED_LOG[0].read_text() == ""


@sdk
@pytest.mark.parametrize("kind, limit, count", [("number", 3, 5), ("role", 2, 3)])
def test_installed_sdk_batch_runs_bounded_concurrency_in_one_child(kind, limit, count, fake_server, images, monkeypatch):
    runner = _sdk_runner(fake_server)
    monkeypatch.setattr(svr, "_DEFAULT", runner)
    _ctl(fake_server, "slow:0.8")
    function, call = _reader_call(kind, images, PROXY_KEY)
    results = svr.run_support_vision(function, [call] * count, limit=limit, deadline_s=60)
    assert len(results) == count and all(PARSED[kind](r) for r in results)
    state = _ctl(fake_server)
    assert state["max_active"] == limit and len(state["log"]) == count
    assert [(r["lifecycle"], r["calls"], r["limit"]) for r in runner.lifecycles] == [("CLEAN", count, limit)]


@pytest.fixture(scope="module")
def large_images(tmp_path_factory):
    root, rng = tmp_path_factory.mktemp("fix14_synthetic_large"), np.random.default_rng(1414)
    paths = [str(root / f"synthetic_large_{i}.jpg") for i in range(4)]
    for path in paths:
        assert cv2.imwrite(path, rng.integers(0, 255, (540, 720, 3), dtype=np.uint8), [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        assert cv2.imread(path) is not None
    assert sum(os.path.getsize(p) for p in paths) * 4 / 3 > 1.2 * 2**20
    return paths


@sdk
def test_installed_sdk_multi_image_body_over_one_mib_keeps_advisory_visible_and_clean(
    fake_server, images, large_images, monkeypatch, record_property
):
    runner = _sdk_runner(fake_server)
    monkeypatch.setattr(svr, "_DEFAULT", runner)
    _ctl(fake_server, "success")
    call = ((PROXY_KEY, "fix14-action-large", large_images, [1000, 1040, 1080, 1120]), {"body_candidates": []})
    assert PARSED["action"](svr.run_support_vision(vp.read_action_pixel_evidence, [call], deadline_s=60)[0])
    log = _ctl(fake_server)["log"]
    # the fake server counts "image_url" substrings: each image part carries it as type and as key
    assert [(e["path"], e["kind"], e["images"]) for e in log] == [("/llm/chat/completions", "action", 2 * len(large_images))]
    assert log[0]["body_bytes"] > 2**20
    large = runner.lifecycles[-1]
    _evidence(record_property, "sdk_large_body", large, body_bytes=log[0]["body_bytes"], images=log[0]["images"])
    assert (large["outcome"], large["lifecycle"], large["exit_code"], large["forced"], large["reaped"]) == (
        "RESULT",
        "CLEAN",
        0,
        None,
        True,
    )
    _assert_one_visible_advisory(large)
    small = _read(runner, fake_server, "action", images, PROXY_KEY, "success", monkeypatch=monkeypatch)
    assert PARSED["action"](small) and _ctl(fake_server)["log"][0]["body_bytes"] < 2**20
    record = runner.lifecycles[-1]
    _evidence(record_property, "sdk_small_body", record, body_bytes=_ctl(fake_server)["log"][0]["body_bytes"])
    assert record["lifecycle"] == "CLEAN" and record["output_markers"] == {} and record["performance_advisories"] == 0
    assert BLOCKED_LOG[0].read_text() == ""


def _zero_frames(_video, requested):
    return {int(ms): (int(ms), np.zeros((240, 320, 3), np.uint8)) for ms in requested}


JERSEY_ROWS = [
    {"track_id": "p1", "media_ms": ms, "request_id": f"r{ms}", "box": {"x": 0.3, "y": 0.2, "w": 0.3, "h": 0.5}}
    for ms in (1000, 1040, 1080, 1120)
]


@sdk
def test_jersey_call_site_clean_read_then_aborted_read_fails_closed(fake_server, monkeypatch):
    monkeypatch.setattr(vp, "_read_frames", _zero_frames)
    monkeypatch.setattr(svr, "_DEFAULT", _sdk_runner(fake_server))
    _ctl(fake_server, "success")
    votes = vp.ShadowVisionProviders(PROXY_KEY, "fix14").jersey_vote_provider("unused.mp4", JERSEY_ROWS)["p1"]
    assert [(v["readable"], v["number"]) for v in votes] == [(True, "88")] * 4
    monkeypatch.setattr(svr, "_DEFAULT", _sdk_runner(fake_server, graceful_s=0.0))
    votes = vp.ShadowVisionProviders(PROXY_KEY, "fix14").jersey_vote_provider("unused.mp4", JERSEY_ROWS)["p1"]
    assert [(v["readable"], v["number"], v["reason"]) for v in votes] == [(False, None, "reader_error")] * 4
    for vote in votes:
        block = vote["support_vision_fail_closed"]
        assert block["proof_eligible"] is False and block["lifecycle"]["lifecycle"] == "ABORTED"
        assert json.loads(block["diagnostic_pre_teardown_result"]["json"])["number"] == "88"


# --- every call site turns a non-clean lifecycle into fail-closed evidence ------------------


def _raise_fail_closed(seen):
    def run(function, calls, **_kwargs):
        seen.append(svr.isolated_reader_ref(function))
        record = {"label": "stub", "outcome": "RESULT", "lifecycle": "ABORTED"}
        raise svr.SupportVisionFailClosed(record, [{"diagnostic": True, "proof_ready": True}] * len(calls))

    return run


def test_action_and_role_call_sites_fail_closed_with_diagnostic(monkeypatch):
    seen = []
    monkeypatch.setattr(svr, "run_support_vision", _raise_fail_closed(seen))
    monkeypatch.setattr(vp, "_read_frames", _zero_frames)
    monkeypatch.setattr(inspection, "motion_frame_times", lambda *_: [1000, 1300])
    frames = [
        {"media_ms": ms, "scene_id": "scene", "time_authority": "ACTUAL_MEDIA_PTS", "players": []} for ms in (1000, 1300)
    ]
    job = {"inspection_id": "fix14", "scene_id": "scene", "start_ms": 900, "end_ms": 1500}
    review = vp.ShadowVisionProviders("key", "fix14").action_evidence_provider("unused.mp4", job, frames)
    assert (review["status"], review["reason"], review["error_type"]) == (
        "ERROR",
        "action_pixel_reader_error",
        "SupportVisionFailClosed",
    )
    assert review["support_vision_fail_closed"]["proof_eligible"] is False
    window = [{"media_ms": 1000, "players": [{"local_track_id": "p1", "box": {"x": 0.3, "y": 0.2, "w": 0.3, "h": 0.5}}]}]
    interventions = [{"status": "VERIFIED", "proof_eligible": True, "player_track_id": "p1", "media_ms": 1000}]
    roles = vp.ShadowVisionProviders("key", "fix14").role_evidence_provider("unused.mp4", {}, [], {}, window, interventions)
    assert roles["p1"]["status"] == "UNRESOLVED" and roles["p1"]["role"] is None
    assert roles["p1"]["votes"][0]["support_vision_fail_closed"]["lifecycle"]["lifecycle"] == "ABORTED"
    assert [ref[1] for ref in seen] == ["read_action_video_evidence", "read_visible_player_role"]


def test_goal_failure_stays_diagnostic_without_opening_a_second_field_side_call(monkeypatch):
    seen = []
    monkeypatch.setattr(svr, "run_support_vision", _raise_fail_closed(seen))
    monkeypatch.setattr(vp, "_read_frames", _zero_frames)
    goal = vp.build_shadow_providers("key", "fix14", "unused.mp4").goal_geometry_provider(
        {"dense_window_id": "d1", "end_ms": 4000}, {"media_ms": 1000, "strike_id": "s1"}
    )
    assert goal["status"] == "UNRESOLVED" and goal["visual_crossing_audit"]["proof_ready"] is False
    assert goal["support_vision_fail_closed"]["proof_eligible"] is False
    lines = [{"media_ms": ms, "line": {"p1": {"x": 0.9, "y": 0.3}, "p2": {"x": 0.9, "y": 0.7}}} for ms in (1000, 1100)]
    base = lambda _w, _s: {"status": "VERIFIED", "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW", "line_by_ms": lines}  # noqa: E731
    out = gd.GoalDirectionProvider(base, "key", "fix14", "unused.mp4", max_reviews=2)(
        {"dense_window_id": "w1"}, {"media_ms": 1000}
    )
    assert (out["field_side_status"], out["field_side_by_ms"], out["field_side_reason"]) == (
        "UNRESOLVED",
        [],
        "FIELD_SIDE_NOT_OBSERVED_BY_GOAL_SCENE_READER",
    )
    assert [ref[1] for ref in seen] == ["read_goal_scene_evidence"]
