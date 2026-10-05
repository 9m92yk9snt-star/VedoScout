"""FIX10A — physical reconstruction orchestration regression tests."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import physical_match_reconstruction as pmr  # noqa: E402


WINDOW = {
    "dense_window_id": "dense_case",
    "scene_id": "scene_001",
    "start_ms": 900,
    "end_ms": 1300,
    "source_sequence_ids": ["seq1"],
}


def _frame(ms=1000, target_status="HYPOTHESES"):
    return {
        "media_ms": ms,
        "scene_id": "scene_001",
        "used_fallback": False,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "global_target": {
            "status": target_status,
            "local_track_id": None,
            "candidate_local_track_ids": ["p010"],
            "proof_eligible": False,
        },
        "players": [
            {"local_track_id": "p010", "box": {"x": .10, "y": .20, "w": .10, "h": .30},
             "association_state": "VERIFIED_LOCAL"},
            {"local_track_id": "p012", "box": {"x": .17, "y": .20, "w": .10, "h": .30},
             "association_state": "VERIFIED_LOCAL"},
        ],
        "ball_candidates": [],
    }


def _accepted_contact(track="p010", ms=1000):
    return {
        "contact_id": "contact1",
        "media_ms": ms,
        "scene_id": "scene_001",
        "player_track_id": track,
        "player_candidate_track_ids": [track],
        "status": "VERIFIED",
        "contact_visibility": "VISIBLE",
        "foot": "UNKNOWN",
        "contact_geometry": {"score": .9},
        "trajectory_evidence": {"score": .8},
        "possession_evidence": {
            "kind": "RELEASE", "before_holder": track, "after_holder": None,
        },
        "confidence": .9,
        "proof_eligible": True,
        "rejection_reasons": [],
    }


def _base_inputs():
    plan = {"analysis_windows": [{"sequence_id": "seq1", "scene_id": "scene_001", "start_ms": 900, "end_ms": 1300}]}
    analysis = {"sequences": [{"sequence_id": "seq1", "scene_id": "scene_001", "actions": []}]}
    graph = {"frames": []}
    authority = {"target_points": []}
    return plan, analysis, graph, authority


def _contact_result(accepted=None, unresolved=None, rejected=None, metrics=None):
    accepted = list(accepted or [])
    unresolved = list(unresolved or [])
    rejected = list(rejected or [])
    return {
        "contacts": [*copy.deepcopy(accepted), *copy.deepcopy(unresolved)],
        "accepted": accepted,
        "unresolved": unresolved,
        "rejected": rejected,
        "metrics": dict(metrics or {}),
    }


def _patch_window(monkeypatch, frames=None, trajectory=None, contact=None):
    frames = list(frames or [_frame()])
    trajectory = list(trajectory or [])
    contact = contact if contact is not None else _contact_result(
        accepted=[_accepted_contact()], metrics={"accepted": 1}
    )
    monkeypatch.setattr(pmr.dense_replay, "select_critical_windows", lambda *_a: [copy.deepcopy(WINDOW)])
    monkeypatch.setattr(pmr.dense_replay, "iter_dense_frames", lambda *_a, **_k: iter([]))
    monkeypatch.setattr(
        pmr.dense_track_refinement, "refine_window",
        lambda *_a, **_k: {"status": "ok", "frames": copy.deepcopy(frames)},
    )
    monkeypatch.setattr(pmr.ball_trajectory, "reconstruct_ball_trajectory", lambda *_a: copy.deepcopy(trajectory))
    monkeypatch.setattr(pmr.ball_contact_engine, "detect_contact_candidates", lambda *_a: [])
    monkeypatch.setattr(pmr.ball_contact_engine, "resolve_contacts", lambda *_a: copy.deepcopy(contact))


def test_a901_pipeline_builds_physical_touch_chain_without_canonical_events(monkeypatch):
    _patch_window(monkeypatch)
    monkeypatch.setattr(pmr.shot_outcome_engine, "find_strike_releases", lambda *_a: [])
    plan, analysis, graph, authority = _base_inputs()
    out = pmr.reconstruct_physical_match("video.mp4", plan, analysis, graph, authority)
    assert out["status"] == "ok"
    assert out["metrics"]["touches"] == 1
    assert out["traces"][0]["touch_graph"]["touches"][0]["player_track_id"] == "p010"
    assert "canonical_events" not in out
    assert "event_ledger" not in out
    assert "verified_stats" not in out


def test_completed_trace_callback_failure_preserves_reconstructed_evidence(monkeypatch):
    _patch_window(monkeypatch)
    monkeypatch.setattr(pmr.shot_outcome_engine, "find_strike_releases", lambda *_a: [])
    plan, analysis, graph, authority = _base_inputs()
    def fail(_trace):
        raise RuntimeError("synthetic delivery failure")
    out = pmr.reconstruct_physical_match("video.mp4", plan, analysis, graph, authority, trace_callback=fail)
    assert out["status"] == "ok" and out["metrics"]["touches"] == 1
    assert out["traces"][0]["incremental_storage_error_type"] == "RuntimeError"
    assert out["windows"][0]["status"] == "ok"


def test_a902_close_10_12_analogue_keeps_nearby_12_at_zero_touches(monkeypatch):
    _patch_window(monkeypatch, frames=[_frame()], contact=_contact_result(
        accepted=[_accepted_contact("p010")], metrics={"accepted": 1}
    ))
    monkeypatch.setattr(pmr.shot_outcome_engine, "find_strike_releases", lambda *_a: [])
    plan, analysis, graph, authority = _base_inputs()
    out = pmr.reconstruct_physical_match("video.mp4", plan, analysis, graph, authority)
    touches = out["traces"][0]["touch_graph"]["touches"]
    assert [t["player_track_id"] for t in touches] == ["p010"]
    assert all(t["player_track_id"] != "p012" for t in touches)


def test_a903_save_analogue_forbids_goal_without_crossing_evidence(monkeypatch):
    _patch_window(monkeypatch)
    strike = {"strike_id": "s1", "touch_id": "t1", "media_ms": 1000, "scene_id": "scene_001", "player_track_id": "p010"}
    monkeypatch.setattr(pmr.shot_outcome_engine, "find_strike_releases", lambda *_a: [copy.deepcopy(strike)])
    monkeypatch.setattr(
        pmr.shot_outcome_engine, "reconstruct_post_strike_outcome",
        lambda *_a, **_k: {
            "status": "ok", "strike_id": "s1", "physical_outcome": "PLAYER_INTERVENTION",
            "goal_plane_crossing": {"status": "UNRESOLVED", "reason": "NO_PROVEN_GOAL_SEGMENT_CROSSING"},
            "canonical_event_type": None,
        },
    )
    plan, analysis, graph, authority = _base_inputs()
    out = pmr.reconstruct_physical_match("video.mp4", plan, analysis, graph, authority)
    outcome = out["traces"][0]["outcome_evidence"][0]
    assert outcome["physical_outcome"] == "PLAYER_INTERVENTION"
    assert outcome["goal_plane_crossing"]["status"] == "UNRESOLVED"
    assert outcome["canonical_event_type"] is None
    assert "canonical_events" not in out


def test_a904_identity_barrier_propagates_uncertainty_to_touch_binding(monkeypatch):
    _patch_window(monkeypatch, frames=[_frame(target_status="HYPOTHESES")])
    monkeypatch.setattr(pmr.shot_outcome_engine, "find_strike_releases", lambda *_a: [])
    plan, analysis, graph, authority = _base_inputs()
    out = pmr.reconstruct_physical_match("video.mp4", plan, analysis, graph, authority)
    touch = out["traces"][0]["touch_graph"]["touches"][0]
    assert touch["player_track_id"] == "p010"
    assert touch["global_target_id"] is None
    assert touch["global_target_resolution"]["status"] == "UNRESOLVED"


def test_a905_missing_ball_becomes_unresolved_not_a_guess(monkeypatch):
    _patch_window(monkeypatch, trajectory=[{
        "media_ms": 1000, "state": "MISSING", "box": None,
        "used_fallback": False, "time_authority": "ACTUAL_MEDIA_PTS",
    }], contact=_contact_result())
    monkeypatch.setattr(pmr.shot_outcome_engine, "find_strike_releases", lambda *_a: [])
    plan, analysis, graph, authority = _base_inputs()
    out = pmr.reconstruct_physical_match("video.mp4", plan, analysis, graph, authority)
    assert out["metrics"]["accepted_contacts"] == 0
    assert "NO_VERIFIED_PHYSICAL_CONTACT" in out["unresolved_reasons"]
    assert out["traces"][0]["touch_graph"]["touches"] == []


def test_a906_inputs_are_not_mutated(monkeypatch):
    _patch_window(monkeypatch)
    monkeypatch.setattr(pmr.shot_outcome_engine, "find_strike_releases", lambda *_a: [])
    plan, analysis, graph, authority = _base_inputs()
    originals = copy.deepcopy((plan, analysis, graph, authority))
    pmr.reconstruct_physical_match("video.mp4", plan, analysis, graph, authority)
    assert (plan, analysis, graph, authority) == originals


def _goal_review_strike(ms, track, touch_id, *, target=False, scene="scene_001"):
    return {
        "strike_id": f"strike_{touch_id}",
        "touch_id": touch_id,
        "media_ms": ms,
        "scene_id": scene,
        "player_track_id": track,
        "global_target_id": pmr.GLOBAL_TARGET_ID if target else None,
        "status": "VERIFIED_PHYSICAL_RELEASE",
        "proof_eligible": True,
    }


def _goal_review_touch(ms, track, touch_id, team, confidence):
    return {
        "touch_id": touch_id,
        "media_ms": ms,
        "representative_ms": ms,
        "scene_id": "scene_001",
        "player_track_id": track,
        "status": "VERIFIED",
        "proof_eligible": True,
        "team_relation": {
            "status": "SUPPORTING",
            "team": team,
            "confidence": confidence,
        },
    }


def test_a907_goal_review_eligibility_is_limited_to_target_scoring_chain():
    target = _goal_review_strike(1000, "p015", "t1", target=True)
    teammate = _goal_review_strike(2200, "p010", "t2")
    opponent = _goal_review_strike(2300, "p020", "t3")
    late_teammate = _goal_review_strike(7000, "p011", "t4")
    graph = {"touches": [
        _goal_review_touch(1000, "p015", "t1", "target_team", .95),
        _goal_review_touch(2200, "p010", "t2", "target_team", .81),
        _goal_review_touch(2300, "p020", "t3", "opponent", .93),
        _goal_review_touch(7000, "p011", "t4", "target_team", .90),
    ]}
    strikes = [target, teammate, opponent, late_teammate]

    assert pmr._goal_review_eligibility(target, strikes, graph)["eligible"] is True
    teammate_result = pmr._goal_review_eligibility(teammate, strikes, graph)
    assert teammate_result["eligible"] is True
    assert teammate_result["reason"] == "VERIFIED_TARGET_TEAM_RELEASE_AFTER_TARGET_PASS"
    assert pmr._goal_review_eligibility(opponent, strikes, graph) == {
        "eligible": False,
        "reason": "DOWNSTREAM_RELEASE_TARGET_TEAM_UNVERIFIED",
        "team_status": "SUPPORTING",
        "team": "opponent",
        "team_confidence": .93,
    }
    assert pmr._goal_review_eligibility(late_teammate, strikes, graph)["reason"] == (
        "NO_PRIOR_TARGET_RELEASE_IN_CAUSAL_HORIZON"
    )


def test_a908_only_causally_eligible_strikes_consume_goal_provider(monkeypatch):
    _patch_window(monkeypatch)
    target = _goal_review_strike(1000, "p015", "t1", target=True)
    teammate = _goal_review_strike(1100, "p010", "t2")
    opponent = _goal_review_strike(1150, "p020", "t3")
    graph = {"touches": [
        _goal_review_touch(1000, "p015", "t1", "target_team", .95),
        _goal_review_touch(1100, "p010", "t2", "target_team", .81),
        _goal_review_touch(1150, "p020", "t3", "opponent", .93),
    ]}
    monkeypatch.setattr(pmr.touch_graph, "build_touch_graph", lambda *_a: copy.deepcopy(graph))
    monkeypatch.setattr(pmr.contact_role_resolver, "apply_contact_roles", lambda touches, *_a, **_k: touches)
    monkeypatch.setattr(pmr.jersey_consensus, "select_jersey_review_requests", lambda *_a: [])
    monkeypatch.setattr(
        pmr.jersey_consensus,
        "apply_jersey_consensus",
        lambda frames, touches, _votes: {
            "window_evidence": frames,
            "touch_graph": touches,
            "consensus_by_track": {},
        },
    )
    monkeypatch.setattr(
        pmr.unified_identity_authority,
        "apply_verified_jersey_handoff",
        lambda _authority, _frames, touches, _consensus: touches,
    )
    monkeypatch.setattr(
        pmr.shot_outcome_engine,
        "find_strike_releases",
        lambda *_a: copy.deepcopy([target, teammate, opponent]),
    )
    monkeypatch.setattr(
        pmr.post_strike_intervention,
        "detect_post_strike_intervention",
        lambda *_a: {"status": "NONE", "proof_eligible": False},
    )
    monkeypatch.setattr(
        pmr.shot_outcome_engine,
        "reconstruct_post_strike_outcome",
        lambda strike, *_a, goal_geometry=None, **_k: {
            "status": "ok",
            "strike_id": strike["strike_id"],
            "physical_outcome": "UNRESOLVED",
            "goal_plane_crossing": {"status": "UNRESOLVED"},
            "goal_geometry_evidence": copy.deepcopy(goal_geometry),
        },
    )
    monkeypatch.setattr(
        pmr.post_strike_intervention,
        "apply_intervention_evidence",
        lambda outcome, *_a: outcome,
    )
    monkeypatch.setattr(pmr.fix10a_goal_direction, "apply_direction_gate", lambda outcome, *_a: outcome)
    monkeypatch.setattr(pmr.fix10a_ball_proof_gate, "apply_ball_proof_gate", lambda outcome, *_a: outcome)
    reviewed = []

    def goal_provider(_window, strike):
        reviewed.append(strike["strike_id"])
        return {"status": "UNRESOLVED", "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW"}

    plan, analysis, scene_graph, authority = _base_inputs()
    out = pmr.reconstruct_physical_match(
        "video.mp4", plan, analysis, scene_graph, authority,
        goal_geometry_provider=goal_provider,
    )

    assert reviewed == ["strike_t1", "strike_t2"]
    assert out["metrics"]["goal_reviews_requested"] == 2
    assert out["metrics"]["goal_reviews_skipped"] == 1
    skipped = out["traces"][0]["outcome_evidence"][2]
    assert skipped["goal_geometry_evidence"]["reason"] == "GOAL_REVIEW_NOT_CAUSALLY_ELIGIBLE"
