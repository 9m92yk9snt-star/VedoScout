"""FIX10A2 — dense scene-local tracking regression tests."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import dense_track_refinement as dtr  # noqa: E402


BASE = {"x": 0.10, "y": 0.20, "w": 0.10, "h": 0.30}


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
