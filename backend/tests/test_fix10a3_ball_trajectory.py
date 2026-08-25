"""FIX10A3 — dense ball trajectory reconstruction tests."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import ball_trajectory as bt  # noqa: E402


def _ball(x, y=0.40, conf=0.8, w=0.02, h=0.02):
    return {"box": {"x": x, "y": y, "w": w, "h": h}, "confidence": conf}


def _frame(ms, balls=None, *, cut=False, fallback=False):
    return {
        "media_ms": int(ms),
        "ball_candidates": list(balls or []),
        "cut_barrier": bool(cut),
        "used_fallback": bool(fallback),
        "time_authority": "FRAME_INDEX_FPS_FALLBACK" if fallback else "ACTUAL_MEDIA_PTS",
    }


def test_a301_continuity_beats_far_false_high_confidence_candidate():
    out = bt.reconstruct_ball_trajectory([
        _frame(1000, [_ball(0.10, conf=0.80)]),
        _frame(1040, [_ball(0.80, conf=0.98), _ball(0.12, conf=0.52)]),
    ])
    assert out[1]["state"] == "MEASURED"
    assert abs(out[1]["box"]["x"] - 0.12) < 1e-9
    assert out[1]["candidates"][0]["box"]["x"] == 0.12


def test_a302_two_plausible_equal_ball_paths_remain_ambiguous():
    out = bt.reconstruct_ball_trajectory([
        _frame(1000, [_ball(0.20, conf=0.80), _ball(0.22, conf=0.80)]),
    ])
    assert out[0]["state"] == "AMBIGUOUS"
    assert out[0]["box"] is None
    assert len(out[0]["candidates"]) == 2
    assert out[0]["proof_eligible"] is False


def test_a303_short_missing_span_is_prediction_not_measurement():
    out = bt.reconstruct_ball_trajectory([
        _frame(1000, [_ball(0.10)]),
        _frame(1040, [_ball(0.12)]),
        _frame(1080, []),
    ])
    assert out[2]["state"] == "PREDICTED_SHORT_GAP"
    assert out[2]["box"] is not None
    assert out[2]["proof_eligible"] is False
    assert out[2]["provenance"] == "KINEMATIC_SHORT_GAP"


def test_a304_long_missing_gap_is_not_bridged():
    out = bt.reconstruct_ball_trajectory([
        _frame(1000, [_ball(0.10)]),
        _frame(1300, []),
    ])
    assert out[1]["state"] == "MISSING"
    assert out[1]["box"] is None


def test_a305_scene_cut_resets_ball_continuity():
    out = bt.reconstruct_ball_trajectory([
        _frame(1000, [_ball(0.10)]),
        _frame(1040, [_ball(0.85, conf=0.95)], cut=True),
    ])
    assert out[1]["state"] == "MEASURED"
    assert out[1]["cut_barrier"] is True
    # trajectory_features resets at the cut: no false cross-cut velocity.
    assert out[1]["velocity"] is None


def test_a306_velocity_uses_actual_vfr_media_delta():
    out = bt.reconstruct_ball_trajectory([
        _frame(1000, [_ball(0.100)]),
        _frame(1075, [_ball(0.175)]),
    ])
    assert out[1]["state"] == "MEASURED"
    assert abs(out[1]["velocity"]["x"] - 1.0) < 1e-6
    assert abs(out[1]["velocity"]["y"]) < 1e-9


def test_a307_real_measured_direction_change_is_retained():
    out = bt.reconstruct_ball_trajectory([
        _frame(1000, [_ball(0.10, y=0.10)]),
        _frame(1050, [_ball(0.15, y=0.10)]),
        _frame(1100, [_ball(0.15, y=0.15)]),
    ])
    assert out[1]["state"] == "MEASURED"
    assert out[2]["state"] == "MEASURED"
    assert out[1]["direction"]["x"] > 0.99
    assert abs(out[1]["direction"]["y"]) < 1e-6
    assert out[2]["direction"]["y"] > 0.99
    assert abs(out[2]["direction"]["x"]) < 1e-6
    assert out[2]["acceleration"] is not None
