"""FIX10A7 — post-strike intervention / goal-plane evidence tests."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import shot_outcome_engine as soe  # noqa: E402


def _ball(ms, x=None, y=0.45, state="MEASURED"):
    return {
        "media_ms": int(ms),
        "scene_id": "scene_001",
        "state": state,
        "box": {"x": x, "y": y, "w": 0.02, "h": 0.02} if x is not None else None,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "used_fallback": False,
        "cut_barrier": False,
    }


def _touch(ms, player, change=0.8, after=None, kinds=None):
    return {
        "touch_id": f"t_{ms}_{player}",
        "media_ms": int(ms),
        "end_ms": int(ms),
        "representative_ms": int(ms),
        "scene_id": "scene_001",
        "player_track_id": player,
        "status": "VERIFIED",
        "proof_eligible": True,
        "trajectory_change": float(change),
        "possession_after": after,
        "possession_kinds": list(kinds or []),
    }


def _strike():
    return {
        "strike_id": "strike_target",
        "touch_id": "t_1000_p015",
        "media_ms": 1000,
        "scene_id": "scene_001",
        "player_track_id": "p015",
        "global_target_id": "GLOBAL_TARGET",
        "status": "VERIFIED_PHYSICAL_RELEASE",
    }


def _vertical_goal(x=0.90):
    return {"line": {"p1": {"x": x, "y": 0.30}, "p2": {"x": x, "y": 0.65}}}


def _deflection_fixture():
    trajectory = [
        _ball(1000, 0.40),
        _ball(1040, 0.50),
        _ball(1080, 0.60),
        _ball(1120, 0.65),
        _ball(1160, 0.55),
    ]
    graph = {"touches": [
        _touch(1000, "p015", change=0.8, after=None, kinds=["RELEASE"]),
        _touch(1120, "p001", change=0.9, after=None),
    ]}
    return trajectory, graph


def test_a701_strike_then_verified_intervention_is_not_goal():
    trajectory, graph = _deflection_fixture()
    result = soe.reconstruct_post_strike_outcome(_strike(), trajectory, graph)
    assert result["intervention"]["status"] == "VERIFIED"
    assert result["physical_outcome"] == "PLAYER_INTERVENTION"
    assert result["goal_plane_crossing"]["status"] == "UNRESOLVED"
    assert result["canonical_event_type"] is None
    assert "GOAL" not in result["physical_outcome"]


def test_a702_ball_disappearing_near_goal_is_unresolved_not_goal():
    trajectory = [
        _ball(1000, 0.70),
        _ball(1040, 0.80),
        _ball(1080, None, state="MISSING"),
    ]
    graph = {"touches": [_touch(1000, "p015", kinds=["RELEASE"])]}
    result = soe.reconstruct_post_strike_outcome(
        _strike(), trajectory, graph, goal_geometry=_vertical_goal(0.90)
    )
    assert result["goal_plane_crossing"]["status"] == "UNRESOLVED"
    assert result["physical_outcome"] == "UNRESOLVED_TERMINAL_VISIBILITY"
    assert result["canonical_event_type"] is None


def test_a703_goal_plane_crossing_requires_geometry_and_measured_crossing():
    trajectory = [
        _ball(1000, 0.85),
        _ball(1040, 0.88),
        _ball(1080, 0.92),
    ]
    graph = {"touches": [_touch(1000, "p015", kinds=["RELEASE"])]}
    without_geometry = soe.reconstruct_post_strike_outcome(_strike(), trajectory, graph)
    assert without_geometry["goal_plane_crossing"]["status"] == "UNRESOLVED"

    with_geometry = soe.reconstruct_post_strike_outcome(
        _strike(), trajectory, graph, goal_geometry=_vertical_goal(0.90)
    )
    assert with_geometry["goal_plane_crossing"]["status"] == "VERIFIED"
    assert with_geometry["physical_outcome"] == "GOAL_PLANE_CROSSING"
    assert 1040 < with_geometry["goal_plane_crossing"]["crossing_ms"] < 1080
    # Even proven physical crossing is not a canonical GOAL in FIX10A.
    assert with_geometry["canonical_event_type"] is None


def test_a704_verified_outfield_block_is_not_goalkeeper_save():
    trajectory, graph = _deflection_fixture()
    result = soe.reconstruct_post_strike_outcome(
        _strike(), trajectory, graph,
        goal_geometry=_vertical_goal(0.90),
        role_evidence={"p001": {"status": "VERIFIED", "role": "OUTFIELD"}},
    )
    assert result["intervention"]["status"] == "VERIFIED"
    assert result["intervention_role"]["role"] == "OUTFIELD"
    assert result["save_evidence"]["status"] == "REJECTED"
    assert result["physical_outcome"] == "PLAYER_INTERVENTION"


def test_a705_unknown_keeper_role_retains_intervention_without_saved_claim():
    trajectory, graph = _deflection_fixture()
    result = soe.reconstruct_post_strike_outcome(
        _strike(), trajectory, graph, goal_geometry=_vertical_goal(0.90)
    )
    assert result["intervention"]["status"] == "VERIFIED"
    assert result["intervention_role"]["status"] == "UNRESOLVED"
    assert result["save_evidence"]["status"] == "UNRESOLVED"
    assert result["physical_outcome"] == "PLAYER_INTERVENTION"


def test_a706_primary_goal_or_saved_story_is_not_read_by_physical_engine():
    trajectory, graph = _deflection_fixture()
    baseline = soe.reconstruct_post_strike_outcome(_strike(), trajectory, graph)
    poisoned_strike = copy.deepcopy(_strike())
    poisoned_strike["primary_outcome"] = "GOAL"
    poisoned_strike["model_confidence"] = 0.999
    poisoned_graph = copy.deepcopy(graph)
    poisoned_graph["primary_story"] = "goal despite keeper save"
    challenged = soe.reconstruct_post_strike_outcome(poisoned_strike, trajectory, poisoned_graph)
    for key in ("physical_outcome", "goal_plane_crossing", "intervention", "save_evidence"):
        assert challenged[key] == baseline[key]


def test_a707_verified_keeper_deflection_can_create_save_evidence_without_canonical_event():
    trajectory = [
        _ball(1000, 0.45),
        _ball(1060, 0.65),
        _ball(1120, 0.82),
        _ball(1180, 0.40),
        _ball(1240, 0.30),
    ]
    graph = {"touches": [
        _touch(1000, "p015", change=0.8, kinds=["RELEASE"]),
        _touch(1120, "p001", change=0.95, after=None),
    ]}
    result = soe.reconstruct_post_strike_outcome(
        _strike(), trajectory, graph,
        goal_geometry=_vertical_goal(0.95),
        role_evidence={"p001": {"status": "VERIFIED", "role": "GOALKEEPER"}},
    )
    assert result["goal_plane_crossing"]["status"] != "VERIFIED"
    assert result["intervention"]["status"] == "VERIFIED"
    assert result["save_evidence"]["status"] == "VERIFIED"
    assert result["physical_outcome"] == "GOALKEEPER_SAVE_EVIDENCE"
    assert result["canonical_event_type"] is None
