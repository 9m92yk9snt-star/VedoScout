"""Reject global-object fallback through production caller contracts."""
from copy import deepcopy
import importlib

import pytest
import ball_trajectory as bt
import contact_role_resolver as crr
import physical_match_reconstruction as pmr


@pytest.mark.parametrize("bad_anchor", [None, {"proof_eligible": False}])
def test_physical_orchestrator_passes_no_global_ball_after_rejected_anchor(monkeypatch, bad_anchor):
    window = {"dense_window_id": "synthetic", "scene_id": "scene", "start_ms": 900, "end_ms": 1800}
    global_path = [{"media_ms": 1200, "state": "MEASURED", "proof_eligible": True,
                    "box": {"x": .8, "y": .5, "w": .01, "h": .01}}]
    monkeypatch.setattr(pmr.dense_replay, "select_critical_windows", lambda *_a: [window])
    monkeypatch.setattr(pmr.dense_replay, "iter_dense_frames", lambda *_a, **_k: iter([]))
    monkeypatch.setattr(pmr.dense_track_refinement, "refine_window", lambda *_a, **_k: {"frames": []})
    monkeypatch.setattr(bt, "reconstruct_ball_trajectory", lambda *_a: deepcopy(global_path))
    monkeypatch.setattr(pmr.ball_contact_engine, "detect_contact_candidates", lambda *_a: [])
    monkeypatch.setattr(pmr.ball_contact_engine, "resolve_contacts", lambda *_a:
                        {"contacts": [], "accepted": [], "unresolved": [], "rejected": []})
    monkeypatch.setattr(pmr.short_occlusion_contact_recovery, "recover_short_occlusion_contacts",
                        lambda *_a, **_k: {"verified": [], "metrics": {"verified": 0}})
    monkeypatch.setattr(pmr.short_occlusion_contact_recovery, "apply_recovered_contacts", lambda c, _r: c)
    monkeypatch.setattr(pmr.touch_graph, "build_touch_graph", lambda *_a: {"touches": []})
    monkeypatch.setattr(pmr.jersey_consensus, "select_jersey_review_requests", lambda *_a: [])
    monkeypatch.setattr(pmr.jersey_consensus, "apply_jersey_consensus", lambda f, t, _v:
                        {"window_evidence": f, "touch_graph": t, "consensus_by_track": {}})
    strike = {"strike_id": "contact", "status": "VERIFIED_PHYSICAL_RELEASE",
              "media_ms": 1000, "scene_id": "scene", "player_track_id": "actor",
              "proof_eligible": True, "active_ball_anchor": bad_anchor}
    monkeypatch.setattr(pmr.shot_outcome_engine, "find_strike_releases", lambda *_a: [deepcopy(strike)])
    seen = {}
    def intervention(_strike, _frames, trajectory):
        seen["intervention"] = trajectory
        return {"status": "UNRESOLVED", "proof_eligible": False}
    def outcome(_strike, trajectory, _graph, **_kwargs):
        seen["outcome"] = trajectory
        return {"physical_outcome": "UNRESOLVED", "goal_plane_crossing": {"status": "UNRESOLVED"}}
    monkeypatch.setattr(pmr.post_strike_intervention, "detect_post_strike_intervention", intervention)
    monkeypatch.setattr(pmr.post_strike_intervention, "apply_intervention_evidence", lambda o, *_a: o)
    monkeypatch.setattr(pmr.shot_outcome_engine, "reconstruct_post_strike_outcome", outcome)
    monkeypatch.setattr(pmr.fix10a_goal_direction, "apply_direction_gate", lambda o, *_a: o)
    monkeypatch.setattr(pmr.fix10a_ball_proof_gate, "apply_ball_proof_gate", lambda o, *_a: o)
    result = pmr.reconstruct_physical_match("never-open.mp4", {}, {}, {}, {})
    assert result["status"] == "ok"
    assert seen == {"intervention": [], "outcome": []}
    assert result["traces"][0]["outcome_evidence"][0]["ball_trajectory_source"] == "REJECTED_RELEASE_ANCHOR"


@pytest.mark.parametrize("bad_anchor", [None, {"proof_eligible": False}])
def test_control_touch_cannot_be_promoted_by_global_spare_ball(monkeypatch, bad_anchor):
    touch = {"touch_id": "control", "status": "VERIFIED", "proof_eligible": True,
             "media_ms": 1000, "scene_id": "scene", "player_track_id": "actor",
             "possession_kinds": ["CONTROL_TOUCH"], "ball_after": bad_anchor}
    received = []
    def delayed(_touch, _touches, _frames, trajectory):
        received.append(trajectory)
        return None if not trajectory else {"status": "VERIFIED", "role": "RELEASE"}
    monkeypatch.setattr(crr, "_delayed_separation_role", delayed)
    result = crr.apply_contact_roles({"touches": [touch]}, {"contacts": []},
                                    dense_frames=[], ball_trajectory=[{"state": "MEASURED"}])
    assert received == [[]]
    assert result["touches"][0]["contact_role"]["role"] == "RECEIVE_CONTROL"
    assert result["metrics"]["delayed_separation_releases"] == 0


def test_replay_and_live_use_the_same_anchor_selection_policy():
    replay = importlib.import_module("scripts.replay_report_evidence")
    assert replay.ball_trajectory.select_release_ball_trajectory is bt.select_release_ball_trajectory
