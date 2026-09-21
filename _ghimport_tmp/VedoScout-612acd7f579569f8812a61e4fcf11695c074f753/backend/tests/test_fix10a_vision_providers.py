"""FIX10A A6/A7 supporting vision provider regression tests."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import fix10a_vision_providers as fvp  # noqa: E402


def _frame():
    return np.zeros((120, 160, 3), dtype=np.uint8)


def _box():
    return {"x": 0.25, "y": 0.20, "w": 0.20, "h": 0.45}


def test_vp01_role_consensus_requires_multiple_agreeing_frames():
    one = fvp.aggregate_role_votes([
        {"media_ms": 1000, "role": "GOALKEEPER", "confidence": "high"},
    ])
    assert one["status"] == "UNRESOLVED"
    assert one["role"] is None

    two = fvp.aggregate_role_votes([
        {"media_ms": 1000, "role": "GOALKEEPER", "confidence": "high"},
        {"media_ms": 1200, "role": "GOALKEEPER", "confidence": "medium"},
    ])
    assert two["status"] == "VERIFIED"
    assert two["role"] == "GOALKEEPER"


def test_vp02_role_conflict_is_unresolved_not_majority_guess():
    out = fvp.aggregate_role_votes([
        {"media_ms": 1000, "role": "GOALKEEPER", "confidence": "high"},
        {"media_ms": 1200, "role": "OUTFIELD", "confidence": "high"},
        {"media_ms": 1400, "role": "GOALKEEPER", "confidence": "low"},
    ])
    assert out["status"] == "UNRESOLVED"
    assert out["role"] is None


def test_vp03_jersey_provider_reads_pixels_without_expected_number(monkeypatch):
    captured = []

    def fake_frames(_video, requested):
        return {int(ms): (int(ms) + 7, _frame()) for ms in requested}

    async def fake_reader(api_key, session_id, crop_path):
        captured.append((api_key, session_id, crop_path))
        return {"readable": True, "number": "10", "confidence": "high", "reason": "visible digits"}

    monkeypatch.setattr(fvp, "_read_frames", fake_frames)
    monkeypatch.setattr(fvp.identity_verify, "read_visible_jersey_number", fake_reader)
    bundle = fvp.build_shadow_providers("key", "session", "video.mp4")
    out = bundle.jersey_vote_provider("video.mp4", [{
        "request_id": "jersey_p010_0000001000",
        "track_id": "p010",
        "media_ms": 1000,
        "box": _box(),
        "expected_jersey_number": "12",  # must never be passed to the reader
    }])
    assert out["p010"][0]["number"] == "10"
    assert out["p010"][0]["media_ms"] == 1007
    assert len(captured) == 1
    # Reader contract is pixel-only: only api key, session id and crop path.
    assert len(captured[0]) == 3


def test_vp04_role_provider_binds_first_post_strike_other_touch(monkeypatch):
    def fake_frames(_video, requested):
        return {int(ms): (int(ms), _frame()) for ms in requested}

    async def fake_role(_api_key, _session_id, _tight, _context):
        return {"role": "GOALKEEPER", "confidence": "high", "reason": "visible keeper cues"}

    monkeypatch.setattr(fvp, "_read_frames", fake_frames)
    monkeypatch.setattr(fvp, "read_visible_player_role", fake_role)
    bundle = fvp.build_shadow_providers("key", "session", "video.mp4")
    strikes = [{"media_ms": 1000, "scene_id": "s1", "player_track_id": "p015"}]
    graph = {"touches": [
        {"media_ms": 1000, "representative_ms": 1000, "scene_id": "s1", "player_track_id": "p015", "status": "VERIFIED"},
        {"media_ms": 1200, "representative_ms": 1200, "scene_id": "s1", "player_track_id": "p001", "status": "VERIFIED"},
        {"media_ms": 1500, "representative_ms": 1500, "scene_id": "s1", "player_track_id": "p002", "status": "VERIFIED"},
    ]}
    evidence = []
    for ms in (1050, 1200, 1400):
        evidence.append({
            "media_ms": ms, "used_fallback": False,
            "players": [{"local_track_id": "p001", "box": _box(), "association_state": "VERIFIED_LOCAL"}],
        })
    out = bundle.role_evidence_provider("video.mp4", {"scene_id": "s1"}, strikes, graph, evidence)
    assert set(out) == {"p001"}
    assert out["p001"]["status"] == "VERIFIED"
    assert out["p001"]["role"] == "GOALKEEPER"


def test_vp05_goal_provider_returns_dynamic_lines_and_independent_audit(monkeypatch):
    def fake_frames(_video, requested):
        return {int(ms): (int(ms), _frame()) for ms in requested}

    async def fake_goal(_api_key, _session_id, _paths, media_ms):
        return {
            "geometry_status": "VERIFIED",
            "frames": [
                {"media_ms": media_ms[1], "line": {"p1": {"x": .80, "y": .30}, "p2": {"x": .80, "y": .70}}, "confidence": "high"},
                {"media_ms": media_ms[2], "line": {"p1": {"x": .82, "y": .30}, "p2": {"x": .82, "y": .70}}, "confidence": "medium"},
            ],
            "crossing": "CROSSED",
            "crossing_confidence": "medium",
            "reason": "ball visibly beyond line",
        }

    monkeypatch.setattr(fvp, "_read_frames", fake_frames)
    monkeypatch.setattr(fvp, "read_goal_scene_evidence", fake_goal)
    bundle = fvp.build_shadow_providers("key", "session", "video.mp4")
    out = bundle.goal_geometry_provider(
        {"dense_window_id": "d1", "end_ms": 4000},
        {"media_ms": 1000, "strike_id": "s1"},
    )
    assert out["status"] == "VERIFIED"
    assert len(out["line_by_ms"]) == 2
    assert out["visual_crossing_audit"]["status"] == "VERIFIED_CROSSING"
    assert out["source"] == "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW"


def test_vp06_goal_provider_low_confidence_outcome_is_unresolved(monkeypatch):
    def fake_frames(_video, requested):
        return {int(ms): (int(ms), _frame()) for ms in requested}

    async def fake_goal(_api_key, _session_id, _paths, media_ms):
        return {
            "geometry_status": "VERIFIED",
            "frames": [
                {"media_ms": media_ms[0], "line": {"p1": {"x": .80, "y": .30}, "p2": {"x": .80, "y": .70}}, "confidence": "high"},
                {"media_ms": media_ms[1], "line": {"p1": {"x": .80, "y": .30}, "p2": {"x": .80, "y": .70}}, "confidence": "high"},
            ],
            "crossing": "NOT_CROSSED",
            "crossing_confidence": "low",
            "reason": "ball too small",
        }

    monkeypatch.setattr(fvp, "_read_frames", fake_frames)
    monkeypatch.setattr(fvp, "read_goal_scene_evidence", fake_goal)
    bundle = fvp.build_shadow_providers("key", "session", "video.mp4")
    out = bundle.goal_geometry_provider(
        {"dense_window_id": "d1", "end_ms": 4000},
        {"media_ms": 1000, "strike_id": "s1"},
    )
    assert out["status"] == "VERIFIED"
    assert out["visual_crossing_audit"]["status"] == "UNRESOLVED"


def test_vp07_missing_api_key_is_fail_closed():
    bundle = fvp.build_shadow_providers(None, "session", "video.mp4")
    assert bundle.jersey_vote_provider("video.mp4", []) == {}
    assert bundle.role_evidence_provider("video.mp4", {}, [], {}, []) == {}
    assert bundle.goal_geometry_provider({}, {"media_ms": 1000}) is None
