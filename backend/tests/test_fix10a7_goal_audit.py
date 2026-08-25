"""FIX10A7 camera-aware goal geometry / independent audit tests."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import shot_outcome_engine as soe  # noqa: E402


def _ball(ms, x, state="MEASURED"):
    return {
        "media_ms": int(ms), "scene_id": "s1", "state": state,
        "box": {"x": x, "y": .44, "w": .02, "h": .02} if x is not None else None,
        "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False,
        "cut_barrier": False,
    }


def _touch(ms, player, change=.9, after=None, kinds=None):
    return {
        "touch_id": f"t{ms}_{player}", "media_ms": int(ms), "end_ms": int(ms),
        "representative_ms": int(ms), "scene_id": "s1", "player_track_id": player,
        "status": "VERIFIED", "proof_eligible": True, "trajectory_change": change,
        "possession_after": after, "possession_kinds": list(kinds or []),
    }


def _strike():
    return {
        "strike_id": "strike1", "touch_id": "t1000_p015", "media_ms": 1000,
        "scene_id": "s1", "player_track_id": "p015", "global_target_id": "GLOBAL_TARGET",
        "status": "VERIFIED_PHYSICAL_RELEASE",
    }


def _provider_geometry(audit="VERIFIED_CROSSING", lines=None):
    lines = lines or [(1000, .90), (1080, .92), (1160, .94)]
    return {
        "status": "VERIFIED",
        "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
        "line": {"p1": {"x": lines[0][1], "y": .30}, "p2": {"x": lines[0][1], "y": .70}},
        "line_by_ms": [
            {"media_ms": ms, "line": {"p1": {"x": x, "y": .30}, "p2": {"x": x, "y": .70}}, "confidence": "high"}
            for ms, x in lines
        ],
        "visual_crossing_audit": {"status": audit, "confidence": "high", "reason": "fixture visual audit"},
    }


def test_ga01_time_aligned_geometry_plus_crossing_audit_can_verify_physical_crossing():
    trajectory = [_ball(1000, .84), _ball(1040, .89), _ball(1080, .94)]
    graph = {"touches": [_touch(1000, "p015", kinds=["RELEASE"])]}
    out = soe.reconstruct_post_strike_outcome(
        _strike(), trajectory, graph,
        goal_geometry=_provider_geometry("VERIFIED_CROSSING", [(1000, .90), (1040, .91), (1080, .92)]),
    )
    assert out["goal_plane_crossing"]["status"] == "VERIFIED"
    assert out["physical_outcome"] == "GOAL_PLANE_CROSSING"
    assert out["goal_plane_crossing"]["visual_audit"]["status"] == "VERIFIED_CROSSING"
    assert out["canonical_event_type"] is None


def test_ga02_measured_intersection_cannot_override_visual_no_crossing():
    trajectory = [_ball(1000, .84), _ball(1040, .89), _ball(1080, .94)]
    graph = {"touches": [_touch(1000, "p015", kinds=["RELEASE"])]}
    out = soe.reconstruct_post_strike_outcome(
        _strike(), trajectory, graph,
        goal_geometry=_provider_geometry("VERIFIED_NO_CROSSING", [(1000, .90), (1040, .91), (1080, .92)]),
    )
    assert out["goal_plane_crossing"]["status"] == "UNRESOLVED"
    assert out["goal_plane_crossing"]["reason"] == "WHOLE_BALL_PHYSICS_CONFLICTS_WITH_VISUAL_NO_CROSSING"
    assert out["physical_outcome"] != "GOAL_PLANE_CROSSING"


def test_ga03_unclear_visual_audit_blocks_provider_based_goal_claim():
    trajectory = [_ball(1000, .84), _ball(1040, .89), _ball(1080, .94)]
    graph = {"touches": [_touch(1000, "p015", kinds=["RELEASE"])]}
    out = soe.reconstruct_post_strike_outcome(
        _strike(), trajectory, graph,
        goal_geometry=_provider_geometry("UNRESOLVED", [(1000, .90), (1040, .91), (1080, .92)]),
    )
    assert out["goal_plane_crossing"]["status"] == "UNRESOLVED"
    assert out["physical_outcome"] != "GOAL_PLANE_CROSSING"


def _save_fixture():
    trajectory = [
        _ball(1000, .44), _ball(1060, .64), _ball(1120, .81),
        _ball(1180, .39), _ball(1240, .29),
    ]
    graph = {"touches": [
        _touch(1000, "p015", kinds=["RELEASE"]),
        _touch(1120, "p001", change=.95),
    ]}
    role = {"p001": {"status": "VERIFIED", "role": "GOALKEEPER", "reason": "multi-frame role consensus"}}
    lines = [(1000, .95), (1120, .95), (1240, .95)]
    return trajectory, graph, role, lines


def test_ga04_provider_save_requires_verified_no_crossing_audit():
    trajectory, graph, role, lines = _save_fixture()
    unclear = soe.reconstruct_post_strike_outcome(
        _strike(), trajectory, graph,
        goal_geometry=_provider_geometry("UNRESOLVED", lines),
        role_evidence=role,
    )
    assert unclear["intervention"]["status"] == "VERIFIED"
    assert unclear["save_evidence"]["status"] == "UNRESOLVED"
    assert unclear["physical_outcome"] == "PLAYER_INTERVENTION"

    verified = soe.reconstruct_post_strike_outcome(
        _strike(), trajectory, graph,
        goal_geometry=_provider_geometry("VERIFIED_NO_CROSSING", lines),
        role_evidence=role,
    )
    assert verified["save_evidence"]["status"] == "VERIFIED"
    assert verified["physical_outcome"] == "GOALKEEPER_SAVE_EVIDENCE"


def test_ga05_stale_dynamic_geometry_fails_closed_instead_of_using_static_line():
    trajectory = [_ball(2000, .84), _ball(2040, .89), _ball(2080, .94)]
    strike = dict(_strike(), media_ms=2000)
    graph = {"touches": [_touch(2000, "p015", kinds=["RELEASE"])]}
    geometry = _provider_geometry("VERIFIED_CROSSING", [(1000, .90), (1100, .91)])
    out = soe.reconstruct_post_strike_outcome(strike, trajectory, graph, goal_geometry=geometry)
    assert out["goal_plane_crossing"]["status"] == "UNRESOLVED"
    assert out["goal_plane_crossing"]["reason"] == "GOAL_GEOMETRY_UNAVAILABLE"
    assert out["physical_outcome"] != "GOAL_PLANE_CROSSING"


def test_ga06_trace_output_retains_bounded_goal_geometry_evidence():
    trajectory = [_ball(1000, .84), _ball(1040, .89), _ball(1080, .94)]
    graph = {"touches": [_touch(1000, "p015", kinds=["RELEASE"])]}
    geometry = _provider_geometry("VERIFIED_CROSSING", [(1000, .90), (1040, .91), (1080, .92)])
    out = soe.reconstruct_post_strike_outcome(_strike(), trajectory, graph, goal_geometry=geometry)
    assert out["goal_geometry_evidence"]["source"] == "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW"
    assert len(out["goal_geometry_evidence"]["line_by_ms"]) == 3
    assert out["canonical_event_type"] is None


def test_ga07_goal_may_become_visible_after_strike_without_false_unresolved():
    # At release time the camera has not yet exposed a trustworthy goal line.
    # Geometry starts 600ms later, but the measured ball crossing occurs inside
    # that later supported interval.  A7 must use the later time-aligned lines
    # rather than requiring geometry at the strike frame itself.
    trajectory = [
        _ball(1000, .50),
        _ball(1600, .84),
        _ball(1700, .89),
        _ball(1800, .95),
    ]
    graph = {"touches": [_touch(1000, "p015", kinds=["RELEASE"])]}
    geometry = _provider_geometry(
        "VERIFIED_CROSSING",
        [(1600, .90), (1700, .91), (1800, .92)],
    )
    out = soe.reconstruct_post_strike_outcome(_strike(), trajectory, graph, goal_geometry=geometry)
    assert out["goal_plane_crossing"]["status"] == "VERIFIED"
    assert out["physical_outcome"] == "GOAL_PLANE_CROSSING"


def test_ga08_ball_center_crossing_is_not_enough_for_goal():
    # The final center is 0.5% beyond the line, but a 2%-wide ball still
    # straddles it.  The entire ball has not crossed, so physical GOAL evidence
    # must remain unresolved even when the independent visual reader says it
    # believes there was a crossing.
    trajectory = [_ball(1000, .84), _ball(1040, .895)]
    graph = {"touches": [_touch(1000, "p015", kinds=["RELEASE"])]}
    geometry = _provider_geometry("VERIFIED_CROSSING", [(1000, .90), (1040, .90)])
    out = soe.reconstruct_post_strike_outcome(_strike(), trajectory, graph, goal_geometry=geometry)
    assert out["goal_plane_crossing"]["status"] == "UNRESOLVED"
    assert out["physical_outcome"] != "GOAL_PLANE_CROSSING"
