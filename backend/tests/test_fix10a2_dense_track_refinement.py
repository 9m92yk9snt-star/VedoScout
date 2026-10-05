"""FIX10A2 — dense scene-local tracking regression tests."""
from __future__ import annotations

import math
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import dense_track_refinement as dtr  # noqa: E402
import touch_graph as tg  # noqa: E402


BASE = {"x": 0.10, "y": 0.20, "w": 0.10, "h": 0.30}


def test_two_exact_proofs_verify_only_unambiguous_dense_body(monkeypatch):
    monkeypatch.setattr(dtr.uia, "resolve_target_at",
                        lambda *_a, **_k: ({"box": BASE}, "OK_INTERPOLATED"))
    def frames(candidate=("p001",)):
        return [{
            "media_ms": ms, "scene_id": "scene_001", "cut_barrier": False,
            "used_fallback": False, "time_authority": "ACTUAL_MEDIA_PTS",
            "players": [{"local_track_id": "p001", "box": dict(BASE),
                         "association_state": "VERIFIED_LOCAL"}],
            "global_target": {
                "status": "VERIFIED" if i in (0, 2) else "HYPOTHESES",
                "reason": "OK_EXACT" if i in (0, 2) else "NON_PROOF_IDENTITY_CONTINUITY",
                "local_track_id": "p001" if i in (0, 2) else None,
                "candidate_local_track_ids": ["p001"] if i in (0, 2) else list(candidate),
                "proof_eligible": i in (0, 2),
            },
        } for i, ms in enumerate((1000, 1100, 1200))]

    valid = frames()
    dtr._verify_bracketed_dense_target(valid, {})
    assert valid[1]["global_target"]["reason"] == "DENSE_TWO_ANCHOR_CONTINUITY"
    binding = tg._global_target_binding({}, valid, 1100, "p001")
    assert binding["global_target_id"] == "GLOBAL_TARGET"

    for change in (lambda f: f[1].update(cut_barrier=True),
                   lambda f: f[1]["global_target"].update(candidate_local_track_ids=["p001", "p002"]),
                   lambda f: f[1]["players"][0].update(association_state="HYPOTHESES"),
                   lambda f: f[2]["global_target"].update(local_track_id="p002"),
                   lambda f: f[2].update(media_ms=1300)):
        blocked = frames()
        change(blocked)
        dtr._verify_bracketed_dense_target(blocked, {})
        assert blocked[1]["global_target"]["status"] == "HYPOTHESES"

    monkeypatch.setattr(dtr.uia, "resolve_target_at",
                        lambda *_a, **_k: (None, "UNRESOLVED_IDENTITY"))
    blocked = frames()
    dtr._verify_bracketed_dense_target(blocked, {})
    assert blocked[1]["global_target"]["status"] == "HYPOTHESES"


def _frame(ms, *, cut=False, scene_id="scene_001"):
    return {
        "media_ms": int(ms),
        "scene_id": scene_id,
        "cut": bool(cut),
        "used_fallback": False,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "frame_bgr": np.full((100, 100, 3), 30, dtype=np.uint8),
    }


def _det(box, conf=0.9, team=None):
    row = {"box": dict(box), "confidence": float(conf)}
    if team is not None:
        row.update({"team": team, "team_confidence": 0.9, "team_source": "KIT_CHROMA_SCENE_CLUSTER"})
    return row


def _graph(box=BASE, *, team=None, target_status="UNRESOLVED", proof=False):
    player = {
        "local_track_id": "p001", "box": dict(box), "confidence": 0.9,
        "team": team, "team_confidence": 0.9 if team else None,
        "team_source": "KIT_CHROMA_SCENE_CLUSTER" if team else None,
    }
    target = {
        "status": target_status,
        "reason": "fixture",
        "local_track_id": "p001" if target_status == "VERIFIED" else None,
        "candidate_local_track_ids": ["p001"],
        "proof_eligible": bool(proof),
    }
    return {
        "frames": [{
            "media_ms": 1000, "scene_id": "scene_001",
            "players": [player], "global_target": target,
        }]
    }


def _detector_sequence(rows):
    it = iter(rows)
    return lambda _frame_bgr: (next(it), [])


def _identity_unresolved(monkeypatch):
    monkeypatch.setattr(dtr.uia, "resolve_target_at", lambda *_a, **_k: (None, "UNRESOLVED"))


def test_exact_tap_keeps_selected_authority_box_separate_from_detected_body(monkeypatch):
    selected = {"x": .08, "y": .18, "w": .14, "h": .35}
    monkeypatch.setattr(
        dtr.uia,
        "resolve_target_at",
        lambda *_a, **_k: ({
            "box": selected,
            "proof_eligible": True,
            "tap_authority": True,
            "primary_source": "USER_TAP",
        }, "OK_EXACT"),
    )
    target = dtr._resolve_dense_target({}, 1000, [{
        "local_track_id": "p001",
        "box": dict(BASE),
        "confidence": .9,
        "association_state": "VERIFIED_LOCAL",
    }])
    assert target["status"] == "VERIFIED"
    assert target["local_track_id"] == "p001"
    assert target["body_box"] == BASE
    assert target["authority_box"] == selected
    assert target["authority_tap"] is True
    assert target["authority_primary_source"] == "USER_TAP"


def test_nearest_actual_pts_inherits_only_direct_user_tap_observation():
    selected = {"x": .08, "y": .18, "w": .14, "h": .35}
    authority = {
        "target_points": [{
            "media_ms": 1000,
            "box": selected,
            "state": "PINNED",
            "proof_eligible": True,
            "tap_authority": True,
            "primary_source": "USER_TAP",
            "sources": ["USER_TAP"],
        }],
    }
    player = {
        "local_track_id": "p001",
        "box": dict(BASE),
        "confidence": .9,
        "association_state": "VERIFIED_LOCAL",
    }
    near = dtr._resolve_dense_target(authority, 1016, [player])
    assert near["status"] == "VERIFIED"
    assert near["reason"] == "OK_NEAREST_TAP_FRAME"
    assert near["authority_media_ms"] == 1000
    assert near["authority_frame_delta_ms"] == 16
    assert near["authority_box"] == selected

    far = dtr._resolve_dense_target(authority, 1033, [player])
    assert far["status"] != "VERIFIED"


def test_refinement_assigns_a_tap_to_only_one_nearest_pts(monkeypatch):
    selected = {"x": .08, "y": .18, "w": .14, "h": .35}
    authority = {"target_points": [{
        "media_ms": 1000,
        "box": selected,
        "state": "PINNED",
        "proof_eligible": True,
        "tap_authority": True,
        "primary_source": "USER_TAP",
        "sources": ["USER_TAP"],
    }]}
    rows = [
        {"media_ms": ms, "players": [{
            "local_track_id": "p001", "box": dict(BASE),
            "association_state": "VERIFIED_LOCAL", "confidence": .9,
        }], "global_target": {"status": "UNRESOLVED"}}
        for ms in (983, 999, 1016)
    ]
    dtr._apply_nearest_tap_frames(rows, authority)
    matched = [row for row in rows if row["global_target"].get("reason") == "OK_NEAREST_TAP_FRAME"]
    assert [row["media_ms"] for row in matched] == [999]


def test_a201_scene_local_id_survives_safe_camera_pan(monkeypatch):
    _identity_unresolved(monkeypatch)
    shifted = {**BASE, "x": BASE["x"] + 0.05}
    detector = _detector_sequence([[ _det(BASE) ], [ _det(shifted) ]])
    pan = np.array([[1.0, 0.0, 5.0], [0.0, 1.0, 0.0]], dtype=float)
    out = dtr.refine_window(
        [_frame(1000), _frame(1040)], _graph(), {}, "scene_001",
        detector_fn=detector, camera_estimator=lambda *_a: (pan, 20),
    )
    assert out["frames"][0]["players"][0]["local_track_id"] == "p001"
    assert out["frames"][1]["players"][0]["local_track_id"] == "p001"
    assert out["frames"][1]["camera_state"] == "AFFINE_VERIFIED"


def test_a202_scene_local_id_survives_safe_zoom_and_rotation(monkeypatch):
    _identity_unresolved(monkeypatch)
    angle = math.radians(2.0)
    scale = 1.04
    matrix = np.array([
        [scale * math.cos(angle), -scale * math.sin(angle), 1.0],
        [scale * math.sin(angle), scale * math.cos(angle), 1.0],
    ])
    moved = dtr.transform_box_affine(BASE, matrix, (100, 100))
    assert moved is not None
    detector = _detector_sequence([[ _det(BASE) ], [ _det(moved) ]])
    out = dtr.refine_window(
        [_frame(1000), _frame(1040)], _graph(), {}, "scene_001",
        detector_fn=detector, camera_estimator=lambda *_a: (matrix, 20),
    )
    assert out["frames"][1]["players"][0]["local_track_id"] == "p001"


def test_a203_extreme_affine_transform_fails_closed():
    extreme = np.array([[3.0, 0.0, 500.0], [0.0, 3.0, 500.0]], dtype=float)
    assert dtr.transform_box_affine(BASE, extreme, (100, 100)) is None


def test_a204_close_equal_players_remain_local_track_hypotheses(monkeypatch):
    _identity_unresolved(monkeypatch)
    left = {**BASE, "x": 0.095}
    right = {**BASE, "x": 0.105}
    detector = _detector_sequence([[ _det(BASE) ], [ _det(left), _det(right) ]])
    identity = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    out = dtr.refine_window(
        [_frame(1000), _frame(1040)], _graph(), {}, "scene_001",
        detector_fn=detector, camera_estimator=lambda *_a: (identity, 20),
    )
    second = out["frames"][1]["players"]
    hyp = [p for p in second if p["association_state"] == "HYPOTHESES"]
    assert len(hyp) == 2
    assert all(p["local_track_id"] is None for p in hyp)
    assert all(p["candidate_local_track_ids"] == ["p001"] for p in hyp)


def test_a205_scene_cut_forbids_local_id_bridge(monkeypatch):
    _identity_unresolved(monkeypatch)
    detector = _detector_sequence([[ _det(BASE) ], [ _det(BASE) ]])
    out = dtr.refine_window(
        [_frame(1000), _frame(1040, cut=True)], _graph(), {}, "scene_001",
        detector_fn=detector,
    )
    assert out["frames"][0]["players"][0]["local_track_id"] == "p001"
    assert out["frames"][1]["cut_barrier"] is True
    assert out["frames"][1]["players"][0]["local_track_id"] == "p002"


def test_a206_dense_tracker_cannot_upgrade_predicted_target_identity(monkeypatch):
    monkeypatch.setattr(
        dtr.uia,
        "resolve_target_at",
        lambda *_a, **_k: ({"box": dict(BASE), "proof_eligible": False}, "OK_INTERPOLATED"),
    )
    out = dtr.refine_window(
        [_frame(1000)], _graph(), {}, "scene_001",
        detector_fn=_detector_sequence([[ _det(BASE) ]]),
    )
    target = out["frames"][0]["global_target"]
    assert target["status"] == "HYPOTHESES"
    assert target["local_track_id"] is None
    assert target["proof_eligible"] is False


def test_a207_target_team_label_never_becomes_global_target_identity(monkeypatch):
    _identity_unresolved(monkeypatch)
    out = dtr.refine_window(
        [_frame(1000)], _graph(team="target_team"), {}, "scene_001",
        detector_fn=_detector_sequence([[ _det(BASE, team="target_team") ]]),
    )
    player = out["frames"][0]["players"][0]
    target = out["frames"][0]["global_target"]
    assert player["team"] == "target_team"
    assert target["status"] == "UNRESOLVED"
    assert target["local_track_id"] is None


def test_a208_far_new_body_cannot_steal_existing_local_id(monkeypatch):
    _identity_unresolved(monkeypatch)
    far = {"x": 0.75, "y": 0.20, "w": 0.10, "h": 0.30}
    detector = _detector_sequence([[ _det(BASE) ], [ _det(far) ]])
    identity = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    out = dtr.refine_window(
        [_frame(1000), _frame(1040)], _graph(), {}, "scene_001",
        detector_fn=detector, camera_estimator=lambda *_a: (identity, 20),
    )
    second = out["frames"][1]["players"]
    assert len(second) == 1
    assert second[0]["local_track_id"] == "p002"
    assert second[0]["association_state"] == "NEW_LOCAL_TRACK"


def test_a209_zero_media_time_is_a_real_previous_timestamp():
    track = {"last_ms": 0, "vx": 1.0, "vy": 0.0}
    predicted = dtr._residual_predict(track, dict(BASE), 40)
    # 1.0 normalized units/s for 40 ms must move x by exactly 0.04.  Treating
    # last_ms=0 as falsy would incorrectly produce zero residual movement.
    assert abs(predicted["x"] - (BASE["x"] + 0.04)) < 1e-9
    assert dtr._last_ms(track, 40) == 0


def test_constant_motion_keeps_actor_id_after_a_bounded_sampling_gap():
    boxes = [{**BASE, "x": x} for x in (.1, .3, .5, .9)]
    identity = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    result = dtr.refine_window(
        [_frame(ms) for ms in (1000, 1100, 1200, 1400)],
        _graph(), {}, "scene_001",
        detector_fn=_detector_sequence([[_det(box)] for box in boxes]),
        camera_estimator=lambda *_args: (identity, 20),
    )
    assert [frame["players"][0]["local_track_id"]
            for frame in result["frames"]] == ["p001"] * 4
    assert all(frame["players"][0]["association_state"] == "VERIFIED_LOCAL"
               for frame in result["frames"])


def test_constant_motion_tracks_camera_pan_separately_from_player_velocity():
    boxes = [{**BASE, "x": x} for x in (.1, .3, .5, .9)]
    camera_steps = iter((2.0, 2.0, 4.0))
    def camera(*_args):
        return np.array([[1.0, 0.0, next(camera_steps)], [0.0, 1.0, 0.0]]), 20

    result = dtr.refine_window(
        [_frame(ms) for ms in (1000, 1100, 1200, 1400)],
        _graph(), {}, "scene_001",
        detector_fn=_detector_sequence([[_det(box)] for box in boxes]),
        camera_estimator=camera,
    )
    assert [frame["players"][0]["local_track_id"]
            for frame in result["frames"]] == ["p001"] * 4


def test_camera_motion_accumulates_across_bounded_detector_misses():
    boxes = [{**BASE, "x": x} for x in (.1, .3, .9)]
    matrix = np.array([[1., 0., 20.], [0., 1., 0.]])
    result = dtr.refine_window(
        [_frame(ms) for ms in (1000, 1100, 1200, 1300, 1400)],
        _graph(), {}, "scene_001",
        detector_fn=_detector_sequence([[_det(boxes[0])], [_det(boxes[1])], [], [], [_det(boxes[2])]]),
        camera_estimator=lambda *_args: (matrix, 20),
    )
    assert result["frames"][-1]["players"][0]["local_track_id"] == "p001"


def test_dense_detector_empty_output_does_not_abort_recall_window():
    class EmptyNet:
        def setInput(self, _blob):
            pass

        def forward(self):
            return np.empty((1, 84, 0), dtype=np.float32)

    class Detector:
        ok = True
        net = EmptyNet()

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    assert dtr._detect_dense_people_and_ball(Detector(), frame, True) == ([], [], [])


def test_dense_detector_invalid_output_reports_shape_instead_of_index_error():
    class InvalidNet:
        def setInput(self, _blob):
            pass

        def forward(self):
            return np.ones((2, 3, 4), dtype=np.float32)

    class Detector:
        ok = True
        net = InvalidNet()

    import pytest
    with pytest.raises(ValueError, match="DENSE_DETECTOR_OUTPUT_SHAPE"):
        dtr._detect_dense_people_and_ball(
            Detector(), np.zeros((100, 100, 3), dtype=np.uint8)
        )


def test_empty_target_hypotheses_leave_recall_window_unresolved_not_crashed(monkeypatch):
    # Regression for staging windows 0–8 s and 34–47 s: proof-level geometry
    # may exist while the dense detector has no matching body in this frame.
    monkeypatch.setattr(
        dtr.uia, "resolve_target_at",
        lambda *_a, **_k: ({"box": dict(BASE), "proof_eligible": True}, "OK_EXACT"),
    )
    result = dtr.refine_window(
        [_frame(1000), _frame(1040)], _graph(), {}, "scene_001",
        detector_fn=_detector_sequence([([], []), ([], [])]),
    )
    assert result["status"] == "ok"
    assert len(result["frames"]) == 2
    for frame in result["frames"]:
        target = frame["global_target"]
        assert target["status"] == "UNRESOLVED"
        assert target["reason"] == "DENSE_TARGET_BODY_NOT_RESOLVED"
        assert target["local_track_id"] is None
        assert target["candidate_local_track_ids"] == []
        assert target["proof_eligible"] is False


def test_dense_team_anchor_samples_follow_only_contiguous_direct_tap_track():
    frames = []
    for index, ms in enumerate((1000, 1040, 1080, 1120)):
        frames.append({
            "media_ms": ms, "scene_id": "scene_001", "cut_barrier": False,
            "used_fallback": False, "time_authority": "ACTUAL_MEDIA_PTS",
            "global_target": {
                "status": "VERIFIED" if index == 0 else "UNRESOLVED",
                "proof_eligible": index == 0,
                "reason": "OK_NEAREST_TAP_FRAME" if index == 0 else "UNRESOLVED",
                "authority_tap": index == 0,
                "authority_primary_source": "USER_TAP",
                "authority_reason": "OK_NEAREST_TAP_FRAME",
                "authority_media_ms": 1000,
                "local_track_id": "p001" if index == 0 else None,
            },
            "players": [{
                "local_track_id": "p001", "association_state": "VERIFIED_LOCAL",
                "box": dict(BASE), "kit_chroma": [45.0 + index, 55.0],
            }],
        })
    samples = dtr._dense_target_kit_samples(frames)
    assert samples == [[45.0, 55.0], [46.0, 55.0], [47.0, 55.0], [48.0, 55.0]]
    frames[2]["cut_barrier"] = True
    assert dtr._dense_target_kit_samples(frames) == [[45.0, 55.0], [46.0, 55.0]]
    frames[0]["global_target"]["authority_primary_source"] = "FIX04"
    assert dtr._dense_target_kit_samples(frames) == []
    frames[0]["global_target"].update(
        authority_primary_source="USER_TAP",
        reason="PROOF_TARGET_SINGLE_CANDIDATE_HYPOTHESIS_COLLAPSE")
    assert dtr._dense_target_kit_samples(frames) == [[45.0, 55.0], [46.0, 55.0]]


def _changing_light_team_frames():
    frames = []
    for start, chroma in ((1000, 20.0), (3000, 90.0)):
        for index in range(10):
            tapped = index == 4
            frames.append({
                "media_ms": start + index * 40, "scene_id": "scene_001",
                "cut_barrier": False, "used_fallback": False,
                "time_authority": "ACTUAL_MEDIA_PTS",
                "global_target": {
                    "status": "VERIFIED" if tapped else "UNRESOLVED",
                    "proof_eligible": tapped, "authority_tap": tapped,
                    "authority_primary_source": "USER_TAP",
                    "authority_reason": "OK_EXACT",
                    "authority_media_ms": start + index * 40,
                    "reason": "OK_EXACT" if tapped else "TARGET_GAP",
                    "local_track_id": "p001" if tapped else None,
                },
                "players": [{
                    "local_track_id": f"p{actor:03d}",
                    "association_state": "VERIFIED_LOCAL", "box": dict(BASE),
                    "kit_chroma": [chroma + (25.0 if actor > 3 else 0.0), 20.0],
                } for actor in range(1, 6)],
            })
    return frames


def test_dense_team_models_are_local_when_pooled_tap_colors_are_inconsistent():
    frames = _changing_light_team_frames()
    targets_before = deepcopy([f["global_target"] for f in frames])
    diagnostic = dtr._apply_dense_team_labels(frames)
    assert diagnostic["status"] == "partial"
    assert diagnostic["pooled_status"] == "unresolved"
    assert len(diagnostic["local_models"]) == 2
    for frame in frames:
        assert frame["players"][1]["team"] == "target_team"
        assert frame["players"][4]["team"] == "opponent"
    # Team inference cannot create target attribution in an identity gap.
    for before, frame in zip(targets_before, frames):
        for key in ("status", "proof_eligible", "local_track_id", "reason"):
            assert frame["global_target"][key] == before[key]


def test_local_team_fallback_keeps_sample_and_cut_barriers():
    frames = _changing_light_team_frames()
    frames[3]["cut_barrier"] = True
    for frame in frames[6:10]:
        frame["used_fallback"] = True
    for frame in frames[10:]:
        frame["global_target"]["authority_tap"] = False
    diagnostic = dtr._apply_dense_team_labels(frames)
    assert diagnostic["status"] == "unresolved"
    assert all("team" not in p for frame in frames for p in frame["players"])


def test_overlapping_local_team_models_must_agree_before_publishing(monkeypatch):
    frames = _changing_light_team_frames()[:10]
    frames[5]["global_target"] = deepcopy(frames[4]["global_target"])
    frames[5]["global_target"]["authority_media_ms"] = frames[5]["media_ms"]
    calls = []

    def fit(rows, samples):
        calls.append(len(samples))
        if len(calls) == 1:
            return {"status": "unresolved", "reason": "TARGET_KIT_CLUSTER_INCONSISTENT"}
        for row in rows:
            for player in row["players"]:
                player.update(team="target_team" if len(calls) == 2 else "opponent",
                              team_confidence=.9, team_source=dtr.fsg.DENSE_TEAM_SOURCE)
        return {"status": "ok"}

    monkeypatch.setattr(dtr.fsg, "apply_dense_team_authority", fit)
    diagnostic = dtr._apply_dense_team_labels(frames)
    assert diagnostic["status"] == "unresolved"
    assert diagnostic["conflicting_detections"] == 50
    assert all("team" not in p for frame in frames for p in frame["players"])
