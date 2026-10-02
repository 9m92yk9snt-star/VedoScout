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


def _dense_frame(media_ms, *, actor="p003", target_status="VERIFIED"):
    target = {
        "status": target_status,
        "local_track_id": actor if target_status == "VERIFIED" else None,
        "candidate_local_track_ids": [actor],
        "proof_eligible": target_status == "VERIFIED",
    }
    return {
        "media_ms": media_ms,
        "scene_id": "scene_1",
        "cut_barrier": False,
        "used_fallback": False,
        "players": [{
            "local_track_id": actor,
            "association_state": "VERIFIED_LOCAL",
            "box": {"x": .4, "y": .4, "w": .2, "h": .2},
        }],
        "global_target": target,
    }


def _ball(media_ms, distance_h):
    # Player foot is (.5, .6); keep y fixed and encode distance along x.
    center_x = .5 + .2 * distance_h
    return {
        "media_ms": media_ms,
        "scene_id": "scene_1",
        "state": "MEASURED",
        "proof_eligible": True,
        "box": {"x": center_x - .01, "y": .59, "w": .02, "h": .02},
    }


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


def test_s413_exact_target_support_path_can_prove_release_role():
    touch = _touch(["SHORT_OCCLUSION_CONTACT_RECOVERY"], source_ids=["c1"])
    out = crr.apply_contact_roles(_graph(touch), _contacts(_recovered(
        "c1", .40, distance=.20, score=.9, mode="EXACT_TARGET_SUPPORT_PATH"
    )))
    role = out["touches"][0]["contact_role"]
    assert role["status"] == "VERIFIED"
    assert role["role"] == "RELEASE"


def test_s414_delayed_measured_target_separation_promotes_terminal_control_to_release():
    touch = _touch(["CONTROL_TOUCH"])
    touch["global_target_id"] = "GLOBAL_TARGET"
    touch["global_target_resolution"] = {"status": "VERIFIED", "global_target_id": "GLOBAL_TARGET"}
    touch["contact_geometry"] = {"distance_h": .4}
    times = [1100, 1150, 1200, 1250]
    frames = [_dense_frame(ms) for ms in times]
    trajectory = [_ball(ms, dist) for ms, dist in zip(times, [1.05, 1.12, 1.20, 1.28])]

    out = crr.apply_contact_roles(
        _graph(touch), _contacts(), dense_frames=frames, ball_trajectory=trajectory
    )

    role = out["touches"][0]["contact_role"]
    assert role["status"] == "VERIFIED"
    assert role["role"] == "RELEASE"
    assert role["source"] == "A4_DELAYED_MEASURED_SEPARATION"
    assert out["metrics"]["delayed_separation_releases"] == 1


def test_s415_delayed_separation_does_not_promote_a_dribble_inside_strong_gate():
    touch = _touch(["CONTROL_TOUCH"])
    touch["global_target_id"] = "GLOBAL_TARGET"
    touch["global_target_resolution"] = {"status": "VERIFIED", "global_target_id": "GLOBAL_TARGET"}
    touch["contact_geometry"] = {"distance_h": .4}
    times = [1100, 1150, 1200, 1250]
    frames = [_dense_frame(ms) for ms in times]
    trajectory = [_ball(ms, dist) for ms, dist in zip(times, [.65, .75, .84, .88])]

    out = crr.apply_contact_roles(
        _graph(touch), _contacts(), dense_frames=frames, ball_trajectory=trajectory
    )

    assert out["touches"][0]["contact_role"]["role"] == "RECEIVE_CONTROL"
    assert out["metrics"]["delayed_separation_releases"] == 0


def test_s416_delayed_separation_requires_selected_actor_continuity():
    touch = _touch(["CONTROL_TOUCH"])
    touch["global_target_id"] = "GLOBAL_TARGET"
    touch["global_target_resolution"] = {"status": "VERIFIED", "global_target_id": "GLOBAL_TARGET"}
    touch["contact_geometry"] = {"distance_h": .4}
    times = [1100, 1150, 1200, 1250]
    frames = [_dense_frame(ms, actor="p999") for ms in times]
    trajectory = [_ball(ms, dist) for ms, dist in zip(times, [1.05, 1.12, 1.20, 1.28])]

    out = crr.apply_contact_roles(
        _graph(touch), _contacts(), dense_frames=frames, ball_trajectory=trajectory
    )

    assert out["touches"][0]["contact_role"]["role"] == "RECEIVE_CONTROL"
    assert out["metrics"]["delayed_separation_releases"] == 0


def test_s417_delayed_separation_rejects_quick_same_actor_recontact():
    touch = _touch(["CONTROL_TOUCH"])
    touch["global_target_id"] = "GLOBAL_TARGET"
    touch["global_target_resolution"] = {"status": "VERIFIED", "global_target_id": "GLOBAL_TARGET"}
    touch["contact_geometry"] = {"distance_h": .4}
    recontact = copy.deepcopy(touch)
    recontact.update({"touch_id": "touch_recontact", "media_ms": 1450, "representative_ms": 1450})
    graph = {"touches": [touch, recontact], "metrics": {"touches": 2}}
    times = [1100, 1150, 1200, 1250]
    frames = [_dense_frame(ms) for ms in times]
    trajectory = [_ball(ms, dist) for ms, dist in zip(times, [1.05, 1.12, 1.20, 1.28])]

    out = crr.apply_contact_roles(
        graph, _contacts(), dense_frames=frames, ball_trajectory=trajectory
    )

    assert out["touches"][0]["contact_role"]["role"] == "RECEIVE_CONTROL"


def test_s417b_delayed_separation_accepts_identity_authority_jersey_reid_track():
    touch = _touch(["CONTROL_TOUCH"])
    touch["global_target_id"] = "GLOBAL_TARGET"
    touch["global_target_resolution"] = {
        "status": "VERIFIED",
        "global_target_id": "GLOBAL_TARGET",
        "reason": "UNIQUE_MULTI_FRAME_JERSEY_REID_AFTER_USER_TAP",
        "verified_jersey_number": "15",
    }
    touch["contact_geometry"] = {"distance_h": .4}
    times = [1100, 1150, 1200, 1250]
    frames = [_dense_frame(ms, target_status="UNRESOLVED") for ms in times]
    for frame in frames:
        frame["players"][0]["jersey_posterior"] = {
            "status": "VERIFIED", "number": "15", "agreeing_frames": 3,
        }
    trajectory = [_ball(ms, dist) for ms, dist in zip(times, [1.05, 1.12, 1.20, 1.28])]

    out = crr.apply_contact_roles(
        _graph(touch), _contacts(), dense_frames=frames, ball_trajectory=trajectory
    )

    assert out["touches"][0]["contact_role"]["role"] == "RELEASE"
    assert out["touches"][0]["contact_role"]["source"] == "A4_DELAYED_MEASURED_SEPARATION"


def test_s418_exact_target_body_flow_release_requires_complete_independent_evidence():
    touch = _touch(["SHORT_OCCLUSION_CONTACT_RECOVERY"], source_ids=["c1"])
    contact = _recovered("c1", .0, mode="EXACT_TARGET_BODY_FLOW_RELEASE")
    contact["recovery_evidence"] = {
        "release_evidence_ms": 1067,
        "release_possession_evidence": {"kind": "RELEASE", "score": 1.0},
        "release_trajectory_evidence": {"score": .8},
        "body_flow_status": "VERIFIED_PATH",
        "ball_flow_status": "VERIFIED_PATH",
        "all_ball_rows_measured_proof_eligible": True,
    }

    out = crr.apply_contact_roles(_graph(touch), _contacts(contact))

    role = out["touches"][0]["contact_role"]
    assert role["status"] == "VERIFIED"
    assert role["role"] == "RELEASE"
    assert role["source"] == "STEP3_AGGREGATED_CONTACT_ROLE"
    assert role["evidence"]["source_roles"][0]["source"] == "EXACT_TARGET_BODY_FLOW_RELEASE"


def test_s419_exact_target_body_flow_release_fails_closed_if_ball_flow_is_missing():
    touch = _touch(["SHORT_OCCLUSION_CONTACT_RECOVERY"], source_ids=["c1"])
    contact = _recovered("c1", .0, mode="EXACT_TARGET_BODY_FLOW_RELEASE")
    contact["recovery_evidence"] = {
        "release_evidence_ms": 1067,
        "release_possession_evidence": {"kind": "RELEASE", "score": 1.0},
        "release_trajectory_evidence": {"score": .8},
        "body_flow_status": "VERIFIED_PATH",
        "ball_flow_status": "UNRESOLVED",
        "all_ball_rows_measured_proof_eligible": True,
    }

    out = crr.apply_contact_roles(_graph(touch), _contacts(contact))

    assert out["touches"][0]["contact_role"]["status"] == "UNRESOLVED"


def _tap_continuity_contact_role(*, ball_flow="VERIFIED_PATH", remote_spare=False):
    row = _recovered("c1", .60, distance=.20, score=1.0,
                     mode="TAP_CONTINUITY_SUPPORT_RELEASE")
    row["recovery_evidence"] = {
        "tap_anchor_ms": 1000,
        "release_evidence_ms": 1200,
        "tap_authority_status": "VERIFIED",
        "actor_continuity_status": "VERIFIED_PATH",
        "ball_flow_status": ball_flow,
        "a3_reacquisition_ms": 1233,
        "a3_reacquisition_proof_eligible": True,
        "remote_spare_ball_used": remote_spare,
    }
    return row


def test_s420_tap_continuity_release_requires_the_complete_active_ball_chain():
    touch = _touch(["SHORT_OCCLUSION_CONTACT_RECOVERY"], source_ids=["c1"])
    out = crr.apply_contact_roles(
        _graph(touch), _contacts(_tap_continuity_contact_role())
    )
    role = out["touches"][0]["contact_role"]
    assert role["status"] == "VERIFIED"
    assert role["role"] == "RELEASE"
    assert role["source"] == "TAP_CONTINUITY_SUPPORT_RELEASE"


def test_s421_tap_continuity_release_rejects_remote_spare_ball():
    touch = _touch(["SHORT_OCCLUSION_CONTACT_RECOVERY"], source_ids=["c1"])
    out = crr.apply_contact_roles(
        _graph(touch), _contacts(_tap_continuity_contact_role(remote_spare=True))
    )
    assert out["touches"][0]["contact_role"]["status"] == "UNRESOLVED"


def test_s422_tap_continuity_release_rejects_missing_ball_flow():
    touch = _touch(["SHORT_OCCLUSION_CONTACT_RECOVERY"], source_ids=["c1"])
    out = crr.apply_contact_roles(
        _graph(touch), _contacts(_tap_continuity_contact_role(ball_flow="UNRESOLVED"))
    )
    assert out["touches"][0]["contact_role"]["status"] == "UNRESOLVED"
