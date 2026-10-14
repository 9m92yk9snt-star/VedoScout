"""Reuse pixel work without reusing mutable tracks or evidence decisions."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

import cv_detect
import dense_track_refinement as dense
import physical_match_reconstruction as physical


def install(monkeypatch, *, model_sha="a" * 64):
    detector = SimpleNamespace(ok=True, model_sha256=model_sha)
    calls = []
    def detect(actual, image, include_a7_support=False):
        assert actual is detector and include_a7_support is True
        calls.append(image.shape)
        return ([{"box": {"x": .2, "y": .3, "w": .1, "h": .3}, "confidence": .8}],
                [{"box": {"x": .3, "y": .6, "w": .01, "h": .01}, "confidence": .1}],
                [{"support_only": True, "proof_eligible": False}])
    monkeypatch.setattr(dense, "_default_detector", lambda: detector)
    monkeypatch.setattr(dense, "_detect_dense_people_and_ball", detect)
    return detector, calls


def test_identical_pixels_reuse_proposals_but_never_caller_mutations(monkeypatch):
    _, calls = install(monkeypatch)
    session = dense.NativeDetectionSession()
    image = np.zeros((48, 32, 3), np.uint8)
    first = session.detect(image)
    original = deepcopy(first)
    first[0][0]["global_target_id"] = "forged"
    first[0][0]["box"]["x"] = .9
    second = session.detect(image.copy())
    second[2][0]["proof_eligible"] = True
    assert session.detect(image) == original
    assert len(calls) == 1 and session.metrics()["hits"] == 2


@pytest.mark.parametrize("change", ["pixel", "shape", "dtype", "model", "threshold"])
def test_different_detector_inputs_always_run_again(monkeypatch, change):
    detector, calls = install(monkeypatch)
    session = dense.NativeDetectionSession()
    image = np.zeros((48, 32, 3), np.uint8)
    session.detect(image)
    if change == "pixel":
        image[0, 0, 0] = 1
    elif change == "shape":
        image = image.reshape(32, 48, 3)
    elif change == "dtype":
        image = image.view(np.int8)
    elif change == "model":
        detector.model_sha256 = "b" * 64
    else:
        monkeypatch.setattr(cv_detect, "CONF_T", cv_detect.CONF_T + .01)
    session.detect(image)
    assert len(calls) == 2 and session.metrics()["hits"] == 0


def test_cache_has_entry_and_exact_serialized_payload_bounds(monkeypatch):
    _, calls = install(monkeypatch)
    image = np.zeros((48, 32, 3), np.uint8)
    session = dense.NativeDetectionSession(max_entries=2, max_bytes=2048)
    for value in (0, 1, 2, 0):
        session.detect(np.full_like(image, value))
    assert len(calls) == 4
    assert session.metrics()["entries"] == 2 and session.metrics()["evictions"] == 2
    assert session.metrics()["payload_bytes"] <= 2048
    small = dense.NativeDetectionSession(max_bytes=10)
    small.detect(image); small.detect(image)
    assert small.metrics()["entries"] == 0 and small.metrics()["hits"] == 0


def test_failure_is_retried_and_unknown_model_is_never_reused(monkeypatch):
    detector, calls = install(monkeypatch, model_sha=None)
    session = dense.NativeDetectionSession()
    image = np.zeros((48, 32, 3), np.uint8)
    session.detect(image); session.detect(image)
    assert len(calls) == 2 and session.metrics()["entries"] == 0
    detector.model_sha256 = "a" * 64
    original = dense._detect_dense_people_and_ball
    attempts = []
    def fail_once(*a, **k):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("temporary native failure")
        return original(*a, **k)
    monkeypatch.setattr(dense, "_detect_dense_people_and_ball", fail_once)
    with pytest.raises(RuntimeError):
        session.detect(image)
    session.detect(image)
    assert len(attempts) == 2 and session.metrics()["entries"] == 1


def test_reuse_keeps_native_selected_body_refinement_and_scene_state_separate(monkeypatch):
    detector, calls = install(monkeypatch)
    refinements = []
    def body(actual, *_args):
        refinements.append(actual)
        return None
    monkeypatch.setattr(dense, "_refine_selected_native_body", body)
    session = dense.NativeDetectionSession()
    image = np.zeros((48, 32, 3), np.uint8)
    results = []
    for scene in ("first", "second"):
        frame = {"media_ms": 1000, "frame_bgr": image, "scene_id": scene,
                 "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False}
        results.append(dense.refine_window([frame], {}, {}, scene, native_session=session))
    assert len(calls) == 1 and refinements == [detector, detector]
    assert [r["frames"][0]["scene_id"] for r in results] == ["first", "second"]
    assert all(r["frames"][0]["global_target"]["proof_eligible"] is False for r in results)
    results[0]["frames"][0]["players"][0]["box"]["x"] = .9
    assert results[1]["frames"][0]["players"][0]["box"]["x"] == .2


def test_physical_windows_share_only_one_run_local_session(monkeypatch):
    windows = [{"dense_window_id": str(i), "scene_id": "s", "start_ms": i * 1000,
                "end_ms": i * 1000 + 200} for i in range(2)]
    monkeypatch.setattr(physical.dense_replay, "select_critical_windows", lambda *_a: windows)
    monkeypatch.setattr(physical.dense_replay, "iter_dense_frames", lambda *_a: [])
    seen = []
    def refine(*_a, **kw):
        seen.append(kw["native_session"])
        return {"frames": []}
    monkeypatch.setattr(dense, "refine_window", refine)
    for _ in range(2):
        physical.reconstruct_physical_match("unused.mp4", {}, {}, {}, {})
    assert len(seen) == 4 and seen[0] is seen[1] and seen[2] is seen[3]
    assert seen[0] is not seen[2]
