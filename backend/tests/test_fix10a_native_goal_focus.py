"""A lost native ball must be inspected without weakening proof gates."""
from copy import deepcopy

import numpy as np
import pytest

import fix10a_vision_providers as providers
import goal_review_sampling as sampling


def job():
    def row(ms, x):
        return {"media_ms": ms, "scene_id": "scene", "state": "MEASURED", "box": {
            "x": x, "y": .6, "w": .02, "h": .01}, "confidence": .8,
            "proof_eligible": True, "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False,
            "cut_barrier": False, "provenance": "RELEASE_ANCHORED_NATIVE_CAMERA_MOTION",
            "frame_dimensions": {"width": 960, "height": 1707, "source": "DECODED_NATIVE_PIXELS"}}
    rows = [row(1100, .4), row(1150, .41), row(1200, .42)]
    anchor = {**deepcopy(rows[0]), "remote_spare_ball_used": False}
    return {"window": {"dense_window_id": "w", "start_ms": 0, "end_ms": 4000},
        "strike": {"media_ms": 1000, "scene_id": "scene", "status": "VERIFIED_PHYSICAL_RELEASE",
            "proof_eligible": True, "active_ball_anchor": anchor},
        "shot_track": {"source": "VERIFIED_RELEASE_ANCHOR", "seed_ms": 1100, "rows": rows,
            "contact_binding": {"status": "VERIFIED", "reason": "MEASURED_CONTACT_TO_EXACT_RELEASE_ANCHOR",
                "contact_ms": 1000, "seed_ms": 1100}}}


@pytest.mark.parametrize("field,value", [
    ("proof_eligible", False), ("state", "SEARCH_ONLY"), ("state", "PREDICTED_SHORT_GAP"),
    ("used_fallback", True), ("cut_barrier", True), ("cut", True), ("support_only", True),
    ("time_authority", "REQUESTED_MEDIA_TIME"), ("scene_id", "other"),
    ("media_ms", 1200.0), ("media_ms", 1300), ("media_ms", 1150),
    ("confidence", .039), ("confidence", float("nan")), ("confidence", True),
    ("provenance", "LOCAL_SEARCH_PROPOSAL"), ("frame_dimensions", None),
])
def test_search_predicted_foreign_duplicate_or_invalid_rows_cannot_choose_focus(field, value):
    data = job()
    data["shot_track"]["rows"][-1][field] = value
    assert sampling.contact_bound_native_path(data["strike"], data["shot_track"]) is None


@pytest.mark.parametrize("corruption", ["global", "rejected", "wrong_contact", "wrong_seed", "wrong_ball",
                                         "spare", "rejected_anchor", "unverified_contact", "one_point"])
def test_only_the_current_contact_bound_native_ball_can_choose_focus(corruption):
    data = job()
    path, strike = data["shot_track"], data["strike"]
    if corruption == "global": path["source"] = "WINDOW_GLOBAL_TRAJECTORY"
    elif corruption == "rejected": path["contact_binding"]["status"] = "REJECTED"
    elif corruption == "wrong_contact": path["contact_binding"]["contact_ms"] = 900
    elif corruption == "wrong_seed": path["seed_ms"] = 1150
    elif corruption == "wrong_ball": path["rows"][0]["box"]["x"] += .1
    elif corruption == "spare": strike["active_ball_anchor"]["remote_spare_ball_used"] = True
    elif corruption == "rejected_anchor": strike["active_ball_anchor"]["identity_rejection"] = "UNBOUND"
    elif corruption == "unverified_contact": strike["proof_eligible"] = False
    elif corruption == "one_point": path["rows"] = path["rows"][:1]
    assert "_goal_review_ball_path" not in sampling.provider_strike(data)


def test_current_job_overwrites_stale_focus_without_mutating_strike_or_trajectory():
    data = job()
    data["strike"]["_goal_review_ball_path"] = {"rows": [{"media_ms": 99999}]}
    before = deepcopy(data)
    result = sampling.provider_strike(data)
    assert result["_goal_review_ball_path"]["rows"][-1]["media_ms"] == 1200
    result["_goal_review_ball_path"]["rows"][-1]["box"]["x"] = .9
    assert data == before
    data["shot_track"]["source"] = "REJECTED_RELEASE_ANCHOR"
    assert "_goal_review_ball_path" not in sampling.provider_strike(data)


@pytest.mark.parametrize("shift", [0, 10000, 25000])
def test_generic_loss_focus_keeps_contact_seed_terminal_and_complete_short_occlusion(shift):
    times = providers._goal_review_times(1000 + shift, 4000 + shift, 12,
        focus_end_ms=1200 + shift, anchor_ms=1100 + shift)
    assert {1000 + shift, 1100 + shift, 1200 + shift, 3600 + shift} <= set(times)
    assert all(1200 + round(900 * i / 8) + shift in times for i in range(1, 9))
    assert times == sorted(set(times)) and len(times) == 12
    assert times[0] == 1000 + shift


def test_small_budget_and_window_bounds_remain_hard_limits():
    assert providers._goal_review_times(1000, 4000, 2, focus_end_ms=1200, anchor_ms=1100) == [1000, 3600]
    times = providers._goal_review_times(1000, 1320, 12, start_ms=1000, focus_end_ms=1200, anchor_ms=1100)
    assert all(1000 <= ms <= 1320 for ms in times)
    assert providers._goal_review_times(1000, 4000, 0, focus_end_ms=1200, anchor_ms=1100) == []
    assert providers._goal_review_times(1000, 1690, 2, focus_end_ms=1680, anchor_ms=1100) == [1000, 1690]


@pytest.mark.usefixtures("inline_support_vision")
def test_provider_uses_loss_focus_dedupes_actual_pts_and_does_not_invent_goal(monkeypatch):
    captured = {}
    def read(_path, requested):
        captured["requested"] = list(requested)
        return {ms: (1367 if ms in {1312, 1425} else ms, np.zeros((32, 32, 3), dtype=np.uint8)) for ms in requested}
    def write(path, _image):
        path.write_bytes(b"test")
        return True
    async def review(_key, _session, _paths, media_ms, *, ball_reference=None):
        captured["actual"] = list(media_ms)
        captured["reference"] = ball_reference
        return {"geometry_status": "UNRESOLVED", "frames": [], "reason": "no_visible_crossing"}
    monkeypatch.setattr(providers, "_read_frames", read)
    monkeypatch.setattr(providers, "_write_jpg", write)
    monkeypatch.setattr(providers, "read_goal_scene_evidence", review)
    data = job()
    bundle = providers.ShadowVisionProviders("injected-test-key", "test").bind_video_path("dummy")
    result = bundle.goal_geometry_provider(data["window"], sampling.provider_strike(data))
    assert all(1200 + round(900 * i / 8) in captured["requested"] for i in range(1, 9))
    assert captured["actual"].count(1367) == 1
    assert captured["reference"]["media_ms"] == 1100
    assert result["sampling_audit"]["native_path_end_ms"] == 1200
    assert result["sampling_audit"]["canonical_authority"] is False
    assert result["status"] == "UNRESOLVED"
    assert result["visual_crossing_audit"]["proof_ready"] is False
