"""FIX10A A7 ball proof-boundary tests."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import fix10a_ball_proof_gate as gate  # noqa: E402


def _ball(ms, proof, source="LOCAL_YOLO_SPORTS_BALL"):
    return {
        "media_ms": int(ms),
        "state": "MEASURED",
        "box": {"x": .5, "y": .5, "w": .02, "h": .02},
        "proof_eligible": bool(proof),
        "measurement_source": source,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "used_fallback": False,
    }


def _verified_crossing():
    return {
        "physical_outcome": "GOAL_PLANE_CROSSING",
        "canonical_event_type": None,
        "goal_plane_crossing": {
            "status": "VERIFIED",
            "reason": "WHOLE_BALL_CROSSED_TIME_ALIGNED_GOAL_PLANE",
            "crossing_ms": 1050,
            "evidence": [{"from_ms": 1000, "to_ms": 1100, "crossing_ms": 1050}],
        },
        "intervention": {"status": "NONE"},
    }


def test_bpg01_verified_crossing_survives_only_with_proof_rows_on_both_sides():
    out = gate.apply_ball_proof_gate(
        _verified_crossing(),
        [_ball(1000, True), _ball(1100, True)],
    )
    assert out["goal_plane_crossing"]["status"] == "VERIFIED"
    assert out["goal_plane_crossing"]["proof_gate"]["status"] == "VERIFIED"
    assert out["ball_proof_gate"]["status"] == "VERIFIED"


def test_bpg02_uncertified_pixel_measurement_cannot_prove_goal_plane_crossing():
    out = gate.apply_ball_proof_gate(
        _verified_crossing(),
        [_ball(1000, True), _ball(1100, False, "PIXEL_BALL_RECOVERY")],
    )
    assert out["goal_plane_crossing"]["status"] == "UNRESOLVED"
    assert out["goal_plane_crossing"]["crossing_ms"] is None
    assert out["goal_plane_crossing"]["reason"] == "WHOLE_BALL_CROSSING_USES_UNCERTIFIED_MEASUREMENT"
    assert out["physical_outcome"] == "UNRESOLVED"
    assert out["canonical_event_type"] is None


def test_bpg03_non_crossing_outcome_is_not_promoted_or_rewritten():
    original = {
        "physical_outcome": "GOALKEEPER_SAVE_EVIDENCE",
        "goal_plane_crossing": {"status": "REJECTED", "reason": "NO_CROSSING"},
        "canonical_event_type": None,
    }
    out = gate.apply_ball_proof_gate(original, [])
    assert out == original
