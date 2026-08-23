"""FIX10A A7 field-side direction and review-budget tests."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import fix10a_goal_direction as fgd  # noqa: E402


def _ball(ms, x):
    return {
        "media_ms": ms, "state": "MEASURED", "used_fallback": False,
        "box": {"x": x, "y": .44, "w": .02, "h": .02},
    }


def _geometry(field=True):
    row = {
        "status": "VERIFIED",
        "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
        "line": {"p1": {"x": .90, "y": .30}, "p2": {"x": .90, "y": .70}},
        "line_by_ms": [
            {"media_ms": 1000, "line": {"p1": {"x": .90, "y": .30}, "p2": {"x": .90, "y": .70}}},
            {"media_ms": 1040, "line": {"p1": {"x": .90, "y": .30}, "p2": {"x": .90, "y": .70}}},
        ],
    }
    if field:
        row.update({
            "field_side_status": "VERIFIED",
            "field_side_by_ms": [
                {"media_ms": 1000, "point": {"x": .70, "y": .50}, "confidence": "high"},
                {"media_ms": 1040, "point": {"x": .70, "y": .50}, "confidence": "high"},
            ],
        })
    return row


def _outcome():
    return {
        "physical_outcome": "GOAL_PLANE_CROSSING",
        "canonical_event_type": None,
        "goal_plane_crossing": {
            "status": "VERIFIED", "crossing_ms": 1025,
            "reason": "WHOLE_BALL_CROSSED_TIME_ALIGNED_GOAL_PLANE",
            "evidence": [{"from_ms": 1000, "to_ms": 1040, "crossing_ms": 1025}],
        },
        "intervention": {"status": "NONE"},
    }


def test_gd01_field_to_goal_direction_keeps_verified_crossing():
    out = fgd.apply_direction_gate(
        _outcome(), [_ball(1000, .84), _ball(1040, .94)], _geometry()
    )
    assert out["goal_plane_crossing"]["status"] == "VERIFIED"
    assert out["goal_plane_crossing"]["direction"] == "FIELD_TO_GOAL"
    assert out["direction_gate"]["status"] == "VERIFIED"
    assert out["physical_outcome"] == "GOAL_PLANE_CROSSING"


def test_gd02_reverse_goal_to_field_is_downgraded():
    out = fgd.apply_direction_gate(
        _outcome(), [_ball(1000, .94), _ball(1040, .84)], _geometry()
    )
    assert out["goal_plane_crossing"]["status"] == "UNRESOLVED"
    assert out["goal_plane_crossing"]["reason"] == "REVERSE_GOAL_TO_FIELD_CROSSING"
    assert out["physical_outcome"] == "UNRESOLVED"
    assert out["canonical_event_type"] is None


def test_gd03_missing_field_orientation_fails_closed():
    out = fgd.apply_direction_gate(
        _outcome(), [_ball(1000, .84), _ball(1040, .94)], _geometry(field=False)
    )
    assert out["goal_plane_crossing"]["status"] == "UNRESOLVED"
    assert out["goal_plane_crossing"]["reason"] == "FIELD_SIDE_ORIENTATION_UNAVAILABLE"


def test_gd04_legacy_geometry_is_not_reinterpreted():
    legacy = {"line": {"p1": {"x": .90, "y": .30}, "p2": {"x": .90, "y": .70}}}
    out = fgd.apply_direction_gate(
        _outcome(), [_ball(1000, .94), _ball(1040, .84)], legacy
    )
    assert out["goal_plane_crossing"]["status"] == "VERIFIED"
    assert "direction_gate" not in out


def test_gd05_review_budget_is_bounded_per_report():
    calls = []

    def base(window, strike):
        calls.append((window, strike))
        return {
            "status": "VERIFIED", "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
            "line_by_ms": [
                {"media_ms": 1000, "line": {"p1": {"x": .9, "y": .3}, "p2": {"x": .9, "y": .7}}},
                {"media_ms": 1100, "line": {"p1": {"x": .9, "y": .3}, "p2": {"x": .9, "y": .7}}},
            ],
        }

    provider = fgd.GoalDirectionProvider(base, "", "session", "video.mp4", max_reviews=1)
    provider({"dense_window_id": "w1"}, {"media_ms": 1000})
    second = provider({"dense_window_id": "w2"}, {"media_ms": 2000})
    assert len(calls) == 1
    assert second["status"] == "UNRESOLVED"
    assert second["reason"] == "GOAL_REVIEW_BUDGET_EXHAUSTED"


def test_gd06_wrapper_merges_multi_frame_field_side(monkeypatch):
    frame = np.zeros((80, 120, 3), dtype=np.uint8)

    def fake_frames(_video, requested):
        return [(int(ms), frame.copy()) for ms in requested]

    async def fake_read(_key, _session, _paths, media_ms):
        return {
            "status": "VERIFIED",
            "rows": [
                {"media_ms": int(ms), "point": {"x": .70, "y": .50}, "confidence": "high"}
                for ms in media_ms
            ],
            "reason": "MULTI_FRAME_FIELD_SIDE_VISIBLE",
        }

    def base(_window, _strike):
        return {
            "status": "VERIFIED", "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
            "line_by_ms": [
                {"media_ms": 1000, "line": {"p1": {"x": .9, "y": .3}, "p2": {"x": .9, "y": .7}}},
                {"media_ms": 1100, "line": {"p1": {"x": .9, "y": .3}, "p2": {"x": .9, "y": .7}}},
            ],
        }

    monkeypatch.setattr(fgd, "_read_frames", fake_frames)
    monkeypatch.setattr(fgd, "read_field_side_evidence", fake_read)
    provider = fgd.GoalDirectionProvider(base, "key", "session", "video.mp4", max_reviews=2)
    out = provider({"dense_window_id": "w1"}, {"media_ms": 1000})
    assert out["field_side_status"] == "VERIFIED"
    assert len(out["field_side_by_ms"]) == 2
    assert out["field_side_source"] == "INDEPENDENT_PLAYABLE_PITCH_REVIEW"
