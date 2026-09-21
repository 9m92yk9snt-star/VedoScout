"""FIX10A8 bounded diagnostic-summary regression tests."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import event_trace as et  # noqa: E402


def _frame(ms, candidates=0):
    return {
        "media_ms": int(ms),
        "scene_id": "s1",
        "time_authority": "ACTUAL_MEDIA_PTS",
        "used_fallback": False,
        "players": [],
        "ball_candidates": [
            {"box": {"x": .40, "y": .45, "w": .02, "h": .02}, "confidence": .8}
            for _ in range(int(candidates))
        ],
    }


def _ball(ms, state):
    return {
        "media_ms": int(ms),
        "scene_id": "s1",
        "state": state,
        "box": {"x": .40, "y": .45, "w": .02, "h": .02} if state in {"MEASURED", "PREDICTED_SHORT_GAP"} else None,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "used_fallback": False,
    }


def _trace(*, frames, trajectory, jerseys=None, outcomes=None):
    return et.build_event_trace(
        trace_id="diag",
        source_video={"role": "canonical_web"},
        window={"dense_window_id": "d1", "scene_id": "s1", "start_ms": 1000, "end_ms": 1240},
        dense_frames=frames,
        ball_trajectory=trajectory,
        contact_result={
            "accepted": [{"contact_id": "c1"}],
            "unresolved": [{"contact_id": "c2"}],
            "rejected": [{"contact_id": "c3"}],
            "metrics": {"candidate_count": 3},
        },
        touch_graph={"touches": [
            {"touch_id": "t1", "status": "VERIFIED"},
            {"touch_id": "t2", "status": "UNRESOLVED"},
        ]},
        jersey_consensus={"consensus_by_track": jerseys or {}},
        outcome_evidence=outcomes or [],
        sequence_analysis={"sequences": []},
    )


def test_a8d01_ball_recall_and_visibility_runs_are_visible_in_summary():
    frames = [
        _frame(1000, 1), _frame(1040, 0), _frame(1080, 1),
        _frame(1120, 0), _frame(1160, 1), _frame(1200, 0),
    ]
    trajectory = [
        _ball(1000, "MEASURED"),
        _ball(1040, "MISSING"),
        _ball(1080, "MISSING"),
        _ball(1120, "PREDICTED_SHORT_GAP"),
        _ball(1160, "AMBIGUOUS"),
        _ball(1200, "MEASURED"),
    ]
    trace = _trace(frames=frames, trajectory=trajectory)
    ball = trace["diagnostics"]["ball"]
    assert ball["decoded_frames"] == 6
    assert ball["frames_with_ball_candidates"] == 3
    assert ball["ball_candidate_frame_ratio"] == 0.5
    assert ball["trajectory_states"] == {
        "AMBIGUOUS": 1,
        "MEASURED": 2,
        "MISSING": 2,
        "PREDICTED_SHORT_GAP": 1,
    }
    assert ball["measured_ratio"] == 0.3333
    assert ball["median_sample_interval_ms"] == 40
    assert ball["longest_missing_run_ms"] == 80
    assert ball["longest_unmeasured_run_ms"] == 160
    summary = et.compact_trace_summary(trace)
    assert summary["diagnostics"]["ball"] == ball
    assert "decoded_frames" not in summary
    assert "ball_trajectory" not in summary


def test_a8d02_jersey_contact_and_touch_failure_states_are_bounded():
    jerseys = {
        "p010": {
            "status": "VERIFIED", "number": "10", "leading_number": "10",
            "top_posterior": .88, "margin": .70, "agreeing_frames": 3,
            "reason": "MULTI_FRAME_NUMBER_CONSENSUS",
        },
        "p012": {
            "status": "UNRESOLVED", "number": None, "leading_number": "12",
            "top_posterior": .52, "margin": .04, "agreeing_frames": 2,
            "reason": "CONFLICTING_JERSEY_NUMBER_VOTES",
        },
    }
    trace = _trace(
        frames=[_frame(1000, 1)], trajectory=[_ball(1000, "MEASURED")], jerseys=jerseys,
    )
    diag = trace["diagnostics"]
    assert diag["contacts"]["accepted"] == 1
    assert diag["contacts"]["unresolved"] == 1
    assert diag["contacts"]["rejected"] == 1
    assert diag["touches"] == {"total": 2, "verified": 1}
    assert diag["jersey"]["status_counts"] == {"UNRESOLVED": 1, "VERIFIED": 1}
    rows = {row["track_id"]: row for row in diag["jersey"]["tracks"]}
    assert rows["p010"]["number"] == "10"
    assert rows["p012"]["number"] is None
    assert rows["p012"]["leading_number"] == "12"


def test_a8d03_goal_direction_keeper_and_save_states_are_visible_without_dense_payload():
    outcome = {
        "strike_id": "strike1",
        "media_ms": 1100,
        "physical_outcome": "GOAL_PLANE_CROSSING",
        "terminal_ball_state": "MEASURED",
        "trajectory_rows_reviewed": 8,
        "goal_plane_crossing": {
            "status": "VERIFIED",
            "reason": "WHOLE_BALL_CROSSED_TIME_ALIGNED_GOAL_PLANE",
            "crossing_ms": 1220,
            "direction": "FIELD_TO_GOAL",
            "direction_status": "VERIFIED",
            "visual_audit": {"status": "VERIFIED_CROSSING"},
        },
        "goal_geometry_evidence": {
            "status": "VERIFIED",
            "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
            "line_by_ms": [{"media_ms": 1160}, {"media_ms": 1240}],
            "field_side_status": "VERIFIED",
            "field_side_by_ms": [{"media_ms": 1160}, {"media_ms": 1240}],
            "field_side_reason": "MULTI_FRAME_FIELD_SIDE_VISIBLE",
        },
        "intervention": {
            "status": "VERIFIED", "player_track_id": "p001",
            "media_ms": 1180, "kind": "DEFLECTION_OR_PARRY_LIKE",
        },
        "intervention_role": {
            "status": "VERIFIED", "role": "GOALKEEPER", "reason": "ROLE_VERIFIED",
        },
        "save_evidence": {"status": "UNRESOLVED", "reason": "KEEPER_AND_NON_CROSSING_EVIDENCE_INSUFFICIENT"},
        "direction_gate": {"status": "VERIFIED", "reason": "FIELD_TO_GOAL_DIRECTION_VERIFIED"},
    }
    trace = _trace(
        frames=[_frame(1000, 1), _frame(1040, 1)],
        trajectory=[_ball(1000, "MEASURED"), _ball(1040, "MEASURED")],
        outcomes=[outcome],
    )
    diag = et.compact_trace_summary(trace)["diagnostics"]["outcomes"][0]
    assert diag["physical_outcome"] == "GOAL_PLANE_CROSSING"
    assert diag["goal_crossing"]["direction"] == "FIELD_TO_GOAL"
    assert diag["goal_geometry"]["field_side_status"] == "VERIFIED"
    assert diag["goal_geometry"]["line_frames"] == 2
    assert diag["goal_geometry"]["field_side_frames"] == 2
    assert diag["role"]["role"] == "GOALKEEPER"
    assert diag["direction_gate"]["status"] == "VERIFIED"
    assert "evidence" not in diag["goal_crossing"]
