"""Physical body distances must agree with decoded pixels in every aspect ratio."""
from copy import deepcopy
import math
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ball_contact_engine as contacts
import ball_trajectory as ball
import contact_role_resolver as roles
import dense_track_refinement as dense
import frame_geometry as geometry
import short_occlusion_contact_recovery as recovery


def frame_size(w, h):
    return {"frame_dimensions": {"width": w, "height": h, "source": "DECODED_NATIVE_PIXELS"}}


def norm(box, w, h):
    return {k: v / (w if k in ("x", "w") else h) for k, v in box.items()}


@pytest.mark.parametrize("w,h", [(400, 400), (800, 400), (400, 800), (1080, 1920)])
def test_contact_distance_matches_pixel_measurement_without_changing_radius(w, h):
    p = norm({"x": 100., "y": 100., "w": 60., "h": 100.}, w, h)
    b = norm({"x": 158., "y": 188., "w": 10., "h": 10.}, w, h)
    expected = math.hypot(163 - 130, 193 - 200) / 100
    result = contacts._lower_body_geometry(p, b, geometry.horizontal_scale(frame_size(w, h)))
    assert result["distance_h"] == pytest.approx(expected, abs=.0001)
    assert result["distance_h"] < contacts.CONTACT_MAX_H
    assert contacts.CONTACT_MAX_H == .58


@pytest.mark.parametrize("w,h", [(400, 400), (800, 400), (400, 800)])
def test_possession_and_step3_use_the_same_pixel_contact_geometry(w, h):
    p = {"local_track_id": "p1", "association_state": "VERIFIED_LOCAL",
         "box": norm({"x": 100., "y": 100., "w": 60., "h": 100.}, w, h)}
    b = norm({"x": 178., "y": 195., "w": 10., "h": 10.}, w, h)
    f = {**frame_size(w, h), "players": [p]}
    assert contacts._likely_holder(f, b) == "p1"
    found, reason, _ = recovery._unique_lower_body_actor(f, b)
    assert reason is None and found[0]["local_track_id"] == "p1"
    direct = contacts._best_lower_geometry(p, b, f)
    assert found[1]["distance_h"] == direct["distance_h"] == .53
    assert ball._nearest_player_foot_h(b, [p], geometry.horizontal_scale(f)) == pytest.approx(.53)


@pytest.mark.parametrize("w,h", [(400, 400), (800, 400), (400, 800)])
def test_trajectory_angle_is_measured_in_one_coordinate_system(w, h):
    rows = [{"media_ms": ms, "box": norm({"x": x, "y": y, "w": 10., "h": 10.}, w, h)}
            for ms, x, y in ((0, 100., 100.), (40, 130., 110.), (80, 120., 140.))]
    result = contacts._trajectory_change(*rows, geometry.horizontal_scale(frame_size(w, h)))
    assert result["direction_change_deg"] == pytest.approx(90., abs=.001)


@pytest.mark.parametrize("dims", [None, {}, {"width": 100}, {"width": True, "height": 200},
    {"width": 0, "height": 200}, {"width": 100, "height": -1},
    {"width": float("nan"), "height": 200}, {"width": 100, "height": float("inf")},
    {"width": "100", "height": 200}, {"width": 100, "height": 200, "source": "REPORTED"}])
def test_malformed_native_dimensions_never_fall_back_to_legacy_geometry(dims):
    if isinstance(dims, dict) and "source" not in dims:
        dims = {**dims, "source": "DECODED_NATIVE_PIXELS"}
    f = {"frame_dimensions": dims, "players": []}
    assert geometry.horizontal_scale(f) is None
    assert contacts._likely_holder(f, {"x": .1, "y": .1, "w": .1, "h": .1}) is None
    assert geometry.compatible_scale(f, f, f) is None


def test_unknown_legacy_frames_keep_the_previous_metric_and_mixed_frames_fail_closed():
    assert geometry.horizontal_scale({}) == 1.
    assert geometry.compatible_scale({}, {}) == 1.
    assert geometry.compatible_scale({}, frame_size(100, 100)) is None
    assert geometry.compatible_scale(frame_size(100, 100), frame_size(100, 200)) is None
    assert geometry.compatible_scale(frame_size(100, 200), frame_size(200, 400)) == .5


def fixture(w, h):
    player = {"local_track_id": "p1", "association_state": "VERIFIED_LOCAL",
              "box": norm({"x": 100., "y": 100., "w": 60., "h": 100.}, w, h)}
    frames = [{**frame_size(w, h), "media_ms": ms, "scene_id": "s", "players": [deepcopy(player)],
               "used_fallback": False, "time_authority": "ACTUAL_MEDIA_PTS"} for ms in (960, 1000, 1040)]
    balls = [{"media_ms": ms, "state": "MEASURED", "proof_eligible": True,
              "time_authority": "ACTUAL_MEDIA_PTS", "box": norm({"x": x, "y": 190., "w": 10., "h": 10.}, w, h)}
             for ms, x in ((960, 155.), (1000, 155.), (1040, 300.))]
    return frames, balls


@pytest.mark.parametrize("w,h", [(400, 400), (800, 400), (400, 800)])
def test_complete_contact_gate_is_invariant_to_canvas_aspect(w, h):
    frames, balls = fixture(w, h)
    result = contacts.resolve_contacts(contacts.detect_contact_candidates(frames, balls))
    assert len(result["accepted"]) == 1
    row = result["accepted"][0]
    assert row["media_ms"] == 1000
    assert row["contact_geometry"]["distance_h"] == pytest.approx(math.hypot(30, 5)/100, abs=.0001)
    assert row["possession_evidence"]["kind"] == "RELEASE"


@pytest.mark.parametrize("change", ["missing", "invalid", "changed_aspect"])
def test_inconsistent_geometry_blocks_full_contact_proof(change):
    frames, balls = fixture(400, 800)
    if change == "missing": frames[0].pop("frame_dimensions")
    elif change == "invalid": frames[0]["frame_dimensions"]["width"] = 0
    else: frames[0]["frame_dimensions"]["width"] = 800
    candidates = contacts.detect_contact_candidates(frames, balls)
    assert not contacts.resolve_contacts(candidates)["accepted"]
    middle = next(c for c in candidates if c["media_ms"] == 1000)
    assert "CONTACT_FRAME_GEOMETRY_UNAVAILABLE" in middle["rejection_reasons"]


def test_native_dimensions_are_measured_from_image_not_claimed_input_metadata(monkeypatch):
    monkeypatch.setattr(dense.uia, "resolve_target_at", lambda *_a, **_k: (None, "UNRESOLVED"))
    row = {"media_ms": 0, "width": 999, "height": 999, "frame_bgr": np.zeros((100, 200, 3), np.uint8),
           "used_fallback": False, "time_authority": "ACTUAL_MEDIA_PTS"}
    result = dense.refine_window([row], {}, {}, "s", detector_fn=lambda _: ([], []))
    assert result["frames"][0]["frame_dimensions"] == {
        "width": 200, "height": 100, "source": "DECODED_NATIVE_PIXELS"}


@pytest.mark.parametrize("w,h", [(400, 400), (800, 400), (400, 800)])
def test_step3_separation_gain_matches_direct_pixel_distances(w, h):
    p = norm({"x": 100., "y": 100., "w": 60., "h": 100.}, w, h)
    before = norm({"x": 158., "y": 188., "w": 10., "h": 10.}, w, h)
    after = norm({"x": 208., "y": 188., "w": 10., "h": 10.}, w, h)
    f = frame_size(w, h)
    assert recovery._actor_distance_h(p, before, f) == pytest.approx(math.hypot(33, 7) / 100)
    assert recovery._separation_gain_h(p, before, p, after, f, f) == pytest.approx(
        (math.hypot(83, 7) - math.hypot(33, 7)) / 100)
    assert recovery._separation_gain_h(p, before, p, after, f, {}) is None
    assert recovery._actor_distance_h(p, before, {"frame_dimensions": {}}) is None


@pytest.mark.parametrize("w,h", [(400, 400), (800, 400), (400, 800)])
@pytest.mark.parametrize("distances,expected", [
    ([.65, .75, .84, .88], "RECEIVE_CONTROL"),
    ([1.05, 1.12, 1.20, 1.28], "RELEASE"),
])
def test_delayed_role_uses_pixel_separation_and_keeps_strong_gate(w, h, distances, expected):
    touch = {"touch_id": "t", "media_ms": 1000, "scene_id": "s", "player_track_id": "p1",
             "status": "VERIFIED", "proof_eligible": True, "trajectory_change": 1.,
             "global_target_id": "GLOBAL_TARGET", "global_target_resolution": {"status": "VERIFIED"},
             "contact_geometry": {"distance_h": .4}, "possession_kinds": ["CONTROL_TOUCH"]}
    frames, trajectory = [], []
    for ms, distance in zip((1100, 1150, 1200, 1250), distances):
        frames.append({**frame_size(w, h), "media_ms": ms, "scene_id": "s", "used_fallback": False,
                       "players": [{"local_track_id": "p1", "association_state": "VERIFIED_LOCAL",
                                    "box": norm({"x": 100., "y": 100., "w": 60., "h": 100.}, w, h)}],
                       "global_target": {"status": "VERIFIED", "local_track_id": "p1"}})
        trajectory.append({"media_ms": ms, "scene_id": "s", "state": "MEASURED", "proof_eligible": True,
                           "box": norm({"x": 125. + 100. * distance, "y": 195., "w": 10., "h": 10.}, w, h)})
    result = roles.apply_contact_roles({"touches": [touch]}, {}, dense_frames=frames, ball_trajectory=trajectory)
    assert result["touches"][0]["contact_role"]["role"] == expected


@pytest.mark.parametrize("w,h", [(400, 400), (800, 400), (400, 800)])
@pytest.mark.parametrize("shift,valid", [(55., True), (110., False)])
def test_actor_and_tap_continuity_use_the_same_pixel_displacement(w, h, shift, valid):
    p = {"local_track_id": "p1", "association_state": "VERIFIED_LOCAL",
         "box": norm({"x": 100., "y": 100., "w": 60., "h": 100.}, w, h)}
    later = {**deepcopy(p), "box": {**p["box"], "x": p["box"]["x"] + shift / w}}
    f = {**frame_size(w, h), "media_ms": 1000, "scene_id": "s", "players": [p],
         "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False}
    nxt = {**deepcopy(f), "media_ms": 1100, "players": [later]}
    actor, audit = contacts._player_for_actor_continuity(f, "p1", nxt)
    assert (actor is not None) is valid
    assert audit["ok"] is valid
    found, path = recovery._tap_actor_continuity([f, nxt], f, p, nxt)
    assert (found is not None) is valid
    assert path["ok"] is valid
