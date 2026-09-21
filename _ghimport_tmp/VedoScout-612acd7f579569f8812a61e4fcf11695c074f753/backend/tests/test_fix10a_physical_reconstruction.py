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
