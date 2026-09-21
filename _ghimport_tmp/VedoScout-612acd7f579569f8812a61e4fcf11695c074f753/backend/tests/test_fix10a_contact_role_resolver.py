"""FIX10A Step 4 — contact role / possession continuity regressions."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import contact_role_resolver as crr  # noqa: E402
import shot_outcome_engine as soe  # noqa: E402


def _touch(kinds, *, change=1.0, source_ids=None):
    return {
        "touch_id": "touch_x",
        "media_ms": 1000,
        "representative_ms": 1000,
        "scene_id": "scene_1",
        "player_track_id": "p003",
        "status": "VERIFIED",
        "proof_eligible": True,
        "trajectory_change": change,
        "possession_after": "p003",
        "possession_kinds": list(kinds),
        "source_contact_ids": list(source_ids or []),
    }


def _recovered(cid, separation, *, distance=.08, score=1.0, mode="POST_GAP_MEASURED_REACQUISITION"):
    return {
        "contact_id": cid,
        "media_ms": 1000,
        "scene_id": "scene_1",
        "player_track_id": "p003",
        "status": "VERIFIED",
        "proof_eligible": True,
        "recovery_mode": mode,
        "separation_gain_h": separation,
        "contact_geometry": {"distance_h": distance, "score": .9},
        "trajectory_evidence": {"score": score, "direction_change_deg": 170.0},
    }


def _graph(touch):
    return {"touches": [copy.deepcopy(touch)], "metrics": {"touches": 1}}


def _contacts(*rows):
    return {"contacts": [copy.deepcopy(x) for x in rows]}


def test_s401_explicit_a4_release_remains_release():
    role = crr.resolve_touch_role(_touch(["RELEASE"]))
    assert role["status"] == "VERIFIED"
    assert role["role"] == "RELEASE"


def test_s402_a4_receive_is_control_not_release():
    role = crr.resolve_touch_role(_touch(["RECEIVE"]))
    assert role["status"] == "VERIFIED"
    assert role["role"] == "RECEIVE_CONTROL"


def test_s403_a4_control_touch_is_control_not_release():
    role = crr.resolve_touch_role(_touch(["CONTROL_TOUCH"]))
    assert role["status"] == "VERIFIED"
    assert role["role"] == "RECEIVE_CONTROL"


def test_s404_conflicting_a4_transition_fails_closed():
    role = crr.resolve_touch_role(_touch(["RELEASE", "CONTROL_TOUCH"]))
    assert role["status"] == "UNRESOLVED"
    assert role["proof_eligible"] is False


def test_s405_step3_strong_separation_is_release():
    touch = _touch(["SHORT_OCCLUSION_CONTACT_RECOVERY"], source_ids=["c1"])
    out = crr.apply_contact_roles(_graph(touch), _contacts(_recovered(
        "c1", .236, distance=.05, score=1.0, mode="PRE_ANCHORED_SUPPORT_FLOW"
    )))
    role = out["touches"][0]["contact_role"]
    assert role["status"] == "VERIFIED"
    assert role["role"] == "RELEASE"


def test_s406_step3_small_separation_inside_possession_radius_is_control():
    touch = _touch(["SHORT_OCCLUSION_CONTACT_RECOVERY"], source_ids=["c1"])
    out = crr.apply_contact_roles(_graph(touch), _contacts(_recovered(
        "c1", .0706, distance=.05, score=1.0
    )))
    role = out["touches"][0]["contact_role"]
    assert role["status"] == "VERIFIED"
    assert role["role"] == "RECEIVE_CONTROL"


def test_s407_step3_missing_source_contact_is_unresolved():
    touch = _touch(["SHORT_OCCLUSION_CONTACT_RECOVERY"], source_ids=["missing"])
    out = crr.apply_contact_roles(_graph(touch), _contacts())
    assert out["touches"][0]["contact_role"]["status"] == "UNRESOLVED"


def test_s408_step3_weak_separation_but_ball_outside_possession_is_unresolved():
    touch = _touch(["SHORT_OCCLUSION_CONTACT_RECOVERY"], source_ids=["c1"])
    out = crr.apply_contact_roles(_graph(touch), _contacts(_recovered(
        "c1", .10, distance=.68, score=1.0
    )))
    assert out["touches"][0]["contact_role"]["status"] == "UNRESOLVED"


def test_s409_apply_does_not_mutate_inputs():
    touch = _touch(["SHORT_OCCLUSION_CONTACT_RECOVERY"], source_ids=["c1"])
    graph = _graph(touch); contacts = _contacts(_recovered("c1", .0706))
    before = copy.deepcopy((graph, contacts))
    crr.apply_contact_roles(graph, contacts)
    assert (graph, contacts) == before


def test_s410_verified_receive_control_blocks_high_change_strike_fallback():
    touch = _touch(["SHORT_OCCLUSION_CONTACT_RECOVERY"], change=1.0)
    touch["contact_role"] = {"status": "VERIFIED", "role": "RECEIVE_CONTROL"}
    assert soe.find_strike_releases(_graph(touch), []) == []


def test_s411_explicit_unresolved_role_blocks_high_change_strike_fallback():
    touch = _touch(["SHORT_OCCLUSION_CONTACT_RECOVERY"], change=1.0)
    touch["contact_role"] = {"status": "UNRESOLVED", "role": "UNRESOLVED"}
    assert soe.find_strike_releases(_graph(touch), []) == []


def test_s412_legacy_high_change_without_step4_role_remains_compatible():
    touch = _touch([], change=1.0)
    strikes = soe.find_strike_releases(_graph(touch), [])
    assert len(strikes) == 1
    assert strikes[0]["status"] == "VERIFIED_PHYSICAL_RELEASE"
