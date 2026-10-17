"""Overlap two remote readers while all evidence/state changes stay ordered."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextvars import copy_context

import analysis_jobs
import support_vision_runner


def advance(steps, value=None, error=None, *, first=False):
    try:
        return False, (next(steps) if first else steps.throw(error) if error else steps.send(value))
    except StopIteration as done:
        return True, done.value


def read(request):
    analysis_jobs.check_cancelled()
    function, calls, deadline, label = request
    value = support_vision_runner.run_support_vision(function, calls, deadline_s=deadline, label=label)[0]
    analysis_jobs.check_cancelled()
    return value


def single_reader(steps):
    try:
        done, request = advance(steps, first=True)
        if done:
            return request
        try:
            reply = read(request)
        except Exception as exc:
            done, result = advance(steps, error=exc)
        else:
            done, result = advance(steps, reply)
        if not done:
            raise RuntimeError("Unexpected second remote reader request")
        return result
    finally:
        steps.close()


def ordered(provider, owner, jobs):
    """Prepare/admit in priority order, run ONLY remote readers concurrently.

    Native OpenCV objects, quotas, caches, and final geometry stay on this
    calling thread. Repeated in-flight requests wait for the earlier cache
    result and spend no second reader slot. Cancellation prevents new calls.
    """
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="goal-reader")
    pending = deque()
    provider._pending_reviews = {}
    opened = []

    def finish(ticket):
        if ticket[0] == "DONE":
            return ticket[1]
        kind, wrapper, payload = ticket
        if kind == "REUSE":
            key, start, end = payload
            found, value = provider._cached_review(key, start, end)
            if not found:
                raise RuntimeError("Earlier ordered review did not publish its cache result")
            done, result = advance(wrapper, value)
        else:
            base_steps, future = payload
            while True:
                analysis_jobs.check_cancelled()
                try:
                    reply = future.result(timeout=.2)
                    break
                except FutureTimeout:
                    if future.done():
                        break
                except Exception:
                    break
            try:
                try:
                    reply = future.result()
                except Exception as exc:
                    done, base = advance(base_steps, error=exc)
                else:
                    done, base = advance(base_steps, reply)
                if not done:
                    raise RuntimeError("Unexpected second goal reader request")
            except Exception as exc:
                done, result = advance(wrapper, error=exc)
            else:
                done, result = advance(wrapper, base)
        if not done:
            raise RuntimeError("Unexpected second goal provider request")
        return result

    try:
        for window, strike in jobs:
            analysis_jobs.check_cancelled()
            if len(pending) >= 2:
                yield finish(pending.popleft())
            wrapper = provider._review_steps(window, strike)
            opened.append(wrapper)
            try:
                done, request = advance(wrapper, first=True)
            except Exception:
                pending.append(("DONE", None))
                continue
            if done:
                pending.append(("DONE", request))
                continue
            kind, payload = request
            if kind == "REUSE":
                pending.append((kind, wrapper, payload))
                continue
            base_steps = owner.goal_review_steps(*payload)
            opened.append(base_steps)
            try:
                done, request = advance(base_steps, first=True)
            except Exception as exc:
                done, result = advance(wrapper, error=exc)
                if not done:
                    raise RuntimeError("Unexpected goal provider continuation")
                pending.append(("DONE", result))
                continue
            if done:
                done, result = advance(wrapper, request)
                if not done:
                    raise RuntimeError("Unexpected goal provider continuation")
                pending.append(("DONE", result))
            else:
                context = copy_context()
                future = executor.submit(context.run, read, request)
                pending.append(("REMOTE", wrapper, (base_steps, future)))
        while pending:
            yield finish(pending.popleft())
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
        for steps in reversed(opened):
            steps.close()
        provider._pending_reviews = {}
