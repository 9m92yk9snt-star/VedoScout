"""FIX14 contract: every supporting-vision reader forwards a float request timeout and disabled
retries through the installed LlmChat to ``litellm.acompletion`` (mocked here), and a breach fails
closed. This does not exercise real LiteLLM background tasks or process teardown; see
test_fix14_support_vision_runner.py for the process-isolated lifecycle tests.
"""
import asyncio
import threading
import time
from pathlib import Path

import pytest

import fix10a_vision_providers as vp
import identity_verify as iv

litellm = pytest.importorskip("litellm")
if not hasattr(vp.LlmChat, "_build_completion_params"):
    pytest.skip("installed emergentintegrations SDK required (CI stub present)", allow_module_level=True)

PATCHED_DEADLINE = 1.0  # seconds (float); shorter than the readers' 60/90s wait_for


def _make_fake_acompletion(captured):
    """Mimic litellm.acompletion: run the sync completion in the default
    executor and honour the forwarded HTTP ``timeout`` by raising, exactly as a
    real httpx timeout would once retries are disabled."""
    async def fake_acompletion(**kwargs):
        captured.append(kwargs)
        deadline = kwargs.get("timeout")

        def _sync_completion():
            start = time.time()
            while True:
                if deadline is not None and time.time() - start >= deadline:
                    raise TimeoutError(f"simulated httpx timeout after {deadline}s")
                time.sleep(0.02)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync_completion)

    return fake_acompletion


def _img(tmp_path: Path, name: str) -> str:
    p = tmp_path / name
    p.write_bytes(b"\xff\xd8\xff\xe0fix14-regression-not-a-real-image\xff\xd9")
    return str(p)


def _readers(tmp_path):
    a, b, c = _img(tmp_path, "f1.jpg"), _img(tmp_path, "f2.jpg"), _img(tmp_path, "f3.jpg")
    return {
        "action": lambda: vp.read_action_pixel_evidence("k", "s", [a, b], [1000, 1040], body_candidates=[]),
        "role": lambda: vp.read_visible_player_role("k", "s", a, b),
        "goal": lambda: vp.read_goal_scene_evidence("k", "s", [a, b, c], [1000, 1040, 1080]),
        "number": lambda: iv.read_visible_jersey_number("k", "s", a),
    }


@pytest.mark.parametrize("reader_name", ["action", "role", "goal", "number"])
def test_reader_request_deadline_and_no_hang(reader_name, tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(litellm, "acompletion", _make_fake_acompletion(captured))
    # Keep the deadline short so the regression is fast; still < every wait_for.
    monkeypatch.setattr(vp, "VERIFY_REQUEST_TIMEOUT_S", PATCHED_DEADLINE)
    monkeypatch.setattr(iv, "VERIFY_REQUEST_TIMEOUT_S", PATCHED_DEADLINE)

    coro = _readers(tmp_path)[reader_name]()
    baseline_threads = threading.active_count()
    started = time.time()
    result = asyncio.run(coro)  # mirrors the provider's asyncio.run teardown
    elapsed = time.time() - started

    # (1) with_params forwarded the bounded deadline + disabled retries through
    #     the real SDK path, and the model is unchanged.
    assert captured, f"{reader_name}: model network boundary was never reached"
    kw = captured[-1]
    assert kw.get("timeout") == PATCHED_DEADLINE, kw.get("timeout")
    # OpenAI handler validates timeout as float|httpx.Timeout: forward a float,
    # never an int that relies on an uncontrolled intermediate conversion.
    assert isinstance(kw.get("timeout"), float), type(kw.get("timeout"))
    assert kw.get("num_retries") == 0, kw.get("num_retries")
    assert kw.get("max_retries") == 0, kw.get("max_retries")
    assert "gpt-4o" in str(kw.get("model")), kw.get("model")

    # (2) under the mocked completion only: bounded wall-time, no leaked executor worker.
    assert elapsed < PATCHED_DEADLINE + 8, f"{reader_name}: took {elapsed:.1f}s (possible hang)"
    assert threading.active_count() <= baseline_threads, (
        f"{reader_name}: leaked worker thread ({threading.active_count()} > {baseline_threads})")

    # (3) fail-closed status with no fabricated proof (evidence gates intact).
    if reader_name == "action":
        assert result["status"] == "ERROR" and result.get("frames") == []
    elif reader_name == "role":
        assert result.get("role") == "UNKNOWN"
    elif reader_name == "number":
        assert result.get("readable") is False and result.get("number") is None
    elif reader_name == "goal":
        # goal reader fails closed in its outer except: proof stays not-ready and
        # the reason is goal_scene_reader_error (no parser/gate change needed).
        assert isinstance(result, dict)
        assert result.get("proof_ready") is False
        assert result.get("reason") == "goal_scene_reader_error"
        assert result.get("crossing") not in (True,)


def test_default_request_timeout_is_float():
    """The shipped deadline must be a float for the OpenAI handler's
    float|httpx.Timeout validation (no int->float coercion dependency)."""
    assert isinstance(vp.VERIFY_REQUEST_TIMEOUT_S, float)
    assert isinstance(iv.VERIFY_REQUEST_TIMEOUT_S, float)
    # shorter than the smallest existing wait_for (60s)
    for v in (vp.VERIFY_REQUEST_TIMEOUT_S, iv.VERIFY_REQUEST_TIMEOUT_S):
        assert 0 < v < 60
