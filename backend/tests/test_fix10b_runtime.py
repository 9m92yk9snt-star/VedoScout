"""FIX10B unified-result runtime bridge tests."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import fix10b_runtime as rt  # noqa: E402


def _target_touch(ms=1000):
    return {
        "touch_id": "t_target", "media_ms": ms, "representative_ms": ms,
        "scene_id": "scene_1", "player_track_id": "p001",
        "global_target_id": "GLOBAL_TARGET", "status": "VERIFIED",
        "proof_eligible": True,
        "team_relation": {"status": "SUPPORTING", "team": "target_team", "confidence": .95},
    }


def _mate_touch(ms=1500):
    return {
        "touch_id": "t_mate", "media_ms": ms, "representative_ms": ms,
        "scene_id": "scene_1", "player_track_id": "p003",
        "global_target_id": None, "status": "VERIFIED", "proof_eligible": True,
        "team_relation": {"status": "SUPPORTING", "team": "target_team", "confidence": .96},
    }


def _strike(sid, ms, track, target=False):
    return {
        "strike_id": sid, "touch_id": "t_target" if target else "t_mate",
        "media_ms": ms, "scene_id": "scene_1", "player_track_id": track,
        "global_target_id": "GLOBAL_TARGET" if target else None,
        "status": "VERIFIED_PHYSICAL_RELEASE", "proof_eligible": True,
    }


def _physical_assist():
    target = _strike("s_target", 1000, "p001", True)
    scorer = _strike("s_scorer", 2100, "p003", False)
    return {
        "status": "ok",
        "traces": [{
            "trace_id": "dense_1",
            "touch_graph": {"touches": [_target_touch(), _mate_touch()]},
            "strike_evidence": [target, scorer],
            "outcome_evidence": [
                {"status": "ok", "strike_id": "s_target", "media_ms": 1000,
                 "physical_outcome": "UNRESOLVED",
                 "goal_plane_crossing": {"status": "UNRESOLVED", "crossing_ms": None}},
                {"status": "ok", "strike_id": "s_scorer", "media_ms": 2100,
                 "physical_outcome": "GOAL_PLANE_CROSSING",
                 "goal_plane_crossing": {"status": "VERIFIED", "crossing_ms": 2600,
                                         "reason": "WHOLE_BALL_CROSSED_TIME_ALIGNED_GOAL_PLANE",
                                         "evidence": [{"from_ms": 2500, "to_ms": 2640}]}},
            ],
        }],
    }


def _unified():
    return {
        "version": 1, "status": "ok", "global_target_id": "GLOBAL_TARGET",
        "sequence_analysis": {"coverage_complete": True, "sequences": []},
        "canonical_events": {
            "version": 1, "status": "ok", "global_target_id": "GLOBAL_TARGET",
            "timebase": "canonical_media_ms",
            "events": [{
                "event_id": "old_goal", "global_target_id": "GLOBAL_TARGET",
                "scene_id": "scene_1", "start_ms": 900, "contact_ms": 1000,
                "end_ms": 1500, "canonical_ms": 1000,
                "canonical_event_type": "GOAL", "canonical_action_type": "SHOT",
                "canonical_outcome": "GOAL", "causal_verified": True,
                "resolution_reason": "OLD", "actor_local_track_id": "p001",
                "identity_resolution": "VISIBLE_TARGET_MATCH", "foot": "UNKNOWN",
                "pressure": {}, "details": [],
                "proof": {"proof_start_ms": 900, "proof_end_ms": 1500,
                          "evidence_ms": [1000], "actor_keyframes": [],
                          "proof_eligible": True, "causal_verified": True},
                "causal_chain": {}, "receiver_team_resolution": None,
                "source_sequence_ids": [], "source_action_ids": [],
            }],
            "unresolved": [], "rejected": [], "counts": {"GOAL": 1},
            "metrics": {"observations_total": 1, "events_accepted": 1,
                        "observations_unresolved": 0, "observations_rejected": 0,
                        "goals": 1, "assists": 0, "shots": 1},
        },
        "metrics": {"coverage_complete": True, "events_accepted": 1},
    }


def test_fix10b_runtime01_flag_defaults_off(monkeypatch):
    monkeypatch.delenv(rt.FLAG, raising=False)
    assert rt.canonical_enabled() is False
    candidate = rt.build_candidate(_unified(), _physical_assist())
    assert candidate["enabled"] is False
    # Candidate is still computed for deterministic audit/CI; the caller is the
    # authority gate and must not apply it unless enabled.
    assert candidate["summary"]["proposals_applied"] == 1


def test_fix10b_runtime02_flag_enables_canonical_candidate(monkeypatch):
    monkeypatch.setenv(rt.FLAG, "1")
    candidate = rt.build_candidate(_unified(), _physical_assist())
    assert candidate["enabled"] is True
    result = candidate["unified_result"]
    assert result["canonical_events"]["events"][0]["canonical_event_type"] == "ASSIST"
    assert result["event_ledger"]["events"][0]["canonical_event_type"] == "ASSIST"
    assert result["action_timeline"][0]["canonical_event_type"] == "ASSIST"
    assert result["scoring_scan"]["verified_assists"] == 1
    assert result["scoring_scan"]["verified_goals"] == 0
    assert result["metrics"]["verified_assists"] == 1
    assert result["metrics"]["verified_goals"] == 0


def test_fix10b_runtime03_input_is_not_mutated():
    original = _unified()
    before_type = original["canonical_events"]["events"][0]["canonical_event_type"]
    rt.reconcile_unified_result(original, _physical_assist())
    assert original["canonical_events"]["events"][0]["canonical_event_type"] == before_type == "GOAL"


def test_fix10b_runtime04_partial_physical_result_can_only_use_successful_trace_proof():
    physical = _physical_assist()
    physical["status"] = "partial"
    physical["windows"] = [
        {"status": "ok", "dense_window_id": "dense_1"},
        {"status": "error", "dense_window_id": "dense_bad", "reason": "WINDOW_RECONSTRUCTION_ERROR:IndexError"},
    ]
    result = rt.reconcile_unified_result(_unified(), physical)
    assert result["canonical_events"]["events"][0]["canonical_event_type"] == "ASSIST"
    assert result["fix10b_summary"]["status"] == "applied"
