from __future__ import annotations

import copy
import sys
from pathlib import Path

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import short_occlusion_contact_recovery as s3


def _box(cx, cy, w=.03, h=.02):
    return {"x": cx - w/2, "y": cy - h/2, "w": w, "h": h}


def _player(track="p001", x=.45, y=.40, w=.20, h=.30, state="VERIFIED_LOCAL"):
    return {
        "local_track_id": track if state == "VERIFIED_LOCAL" else None,
        "candidate_local_track_ids": [track],
        "box": {"x": x, "y": y, "w": w, "h": h},
        "association_state": state,
    }


def _frame(ms, players=None, support=None, *, cut=False):
    return {
        "media_ms": ms,
        "scene_id": "s1",
        "used_fallback": False,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "cut_barrier": cut,
        "players": list(players or []),
        "ball_candidates": [],
        "a7_ball_support_candidates": list(support or []),
    }


def _measured(ms, cx, cy, *, proof=True):
    return {
        "media_ms": ms,
        "state": "MEASURED",
        "box": _box(cx, cy),
        "confidence": .8,
        "proof_eligible": proof,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "used_fallback": False,
        "provenance": "LOCAL_DENSE_DETECTOR",
    }


def _support(cx, cy, conf=.01):
    return {
        "box": _box(cx, cy),
        "confidence": conf,
        "support_only": True,
        "proof_eligible": False,
    }


def _flow_provider(motion=(4, -4), count=3):
    rng = np.random.default_rng(7)
    base = rng.integers(0, 256, (200, 200), dtype=np.uint8)
    base = cv2.cvtColor(base, cv2.COLOR_GRAY2BGR)

    def provider(_video_path, start_ms, _end_ms):
        rows = []
        for i in range(count):
            matrix = np.float32([[1, 0, motion[0] * i], [0, 1, motion[1] * i]])
            image = cv2.warpAffine(base, matrix, (200, 200), flags=cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_REFLECT)
            rows.append({
                "media_ms": int(start_ms) + (0 if i == 0 else 33 if i == 1 else 67),
                "time_authority": "ACTUAL_MEDIA_PTS",
                "used_fallback": False,
                "frame_bgr": image,
            })
        return rows
    return provider


def _empty_contacts():
    return {"version": 1, "contacts": [], "accepted": [], "unresolved": [], "rejected": [],
            "metrics": {"accepted": 0, "unresolved": 0, "rejected": 0}}


def _b_fixture(*, ambiguous=False, cut=False):
    actor = _player()
    players = [actor]
    if ambiguous:
        players.append(_player("p002", x=.47, y=.40, w=.20, h=.30))
    frames = [
        _frame(967, [actor]),
        _frame(1000, players),
        _frame(1033, [actor]),
        _frame(1067, [actor], cut=cut),
        _frame(1100, [actor], [_support(.58, .61)]),
        _frame(1133, [actor]),
        _frame(1167, [actor]),
    ]
    trajectory = [
        _measured(967, .55, .63),
        _measured(1000, .55, .67),
        {"media_ms": 1033, "state": "PREDICTED_SHORT_GAP", "box": _box(.55,.68),
         "proof_eligible": False, "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False},
        {"media_ms": 1067, "state": "PREDICTED_SHORT_GAP", "box": _box(.55,.69),
         "proof_eligible": False, "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False},
    ]
    return frames, trajectory


def _c_fixture(*, anchor_proof=True, gap_ms=333, same_direction=False, ambiguous=False, cut=False):
    actor = _player()
    anchor_ms = 567 + gap_ms
    next_ms = anchor_ms + 33
    players = [actor]
    if ambiguous:
        players.append(_player("p002", x=.47, y=.40, w=.20, h=.30))
    if same_direction:
        anchor = (.55, .64)
        nxt = (.55, .68)
    else:
        anchor = (.55, .67)
        nxt = (.58, .61)
    frames = [
        _frame(500, [actor]),
        _frame(567, [actor]),
        _frame(700, [actor], cut=cut),
        _frame(anchor_ms, players),
        _frame(next_ms, [actor]),
    ]
    trajectory = [
        _measured(500, .55, .55),
        _measured(567, .55, .59),
        _measured(anchor_ms, *anchor, proof=anchor_proof),
        _measured(next_ms, *nxt),
    ]
    return frames, trajectory


def test_s3_01_support_plus_two_fb_flow_frames_recovers_visible_anchor_contact():
    frames, trajectory = _b_fixture()
    out = s3.recover_short_occlusion_contacts(
        frames, trajectory, _empty_contacts(), video_path="synthetic.mp4",
        flow_frame_provider=_flow_provider(),
    )
    assert out["status"] == "VERIFIED"
    assert len(out["verified"]) == 1
    row = out["verified"][0]
    assert row["media_ms"] == 1000
    assert row["player_track_id"] == "p001"
    assert row["recovery_mode"] == "PRE_ANCHORED_SUPPORT_FLOW"
    assert row["proof_eligible"] is True
    assert row["recovery_evidence"]["raw_support_proof_eligible"] is False
    assert len(row["recovery_evidence"]["flow_nodes"]) >= 3
    assert row["trajectory_evidence"]["direction_change_deg"] >= 45


def test_s3_02_post_gap_measured_reacquisition_preserves_c_style_recovery():
    frames, trajectory = _c_fixture()
    out = s3.recover_short_occlusion_contacts(frames, trajectory, _empty_contacts())
    assert out["status"] == "VERIFIED"
    row = out["verified"][0]
    assert row["recovery_mode"] == "POST_GAP_MEASURED_REACQUISITION"
    assert row["recovery_gap_ms"] == 333
    assert row["trajectory_evidence"]["direction_change_deg"] > 120
    assert row["recovery_evidence"]["fixture_truth_used"] is False


def test_s3_03_proximity_without_trajectory_consequence_stays_unresolved():
    frames, trajectory = _c_fixture(same_direction=True)
    out = s3.recover_short_occlusion_contacts(frames, trajectory, _empty_contacts())
    assert out["verified"] == []


def test_s3_04_competing_lower_body_actors_fail_closed():
    frames, trajectory = _c_fixture(ambiguous=True)
    out = s3.recover_short_occlusion_contacts(frames, trajectory, _empty_contacts())
    assert out["verified"] == []
    assert any(row["reason"] == "MULTIPLE_LOWER_BODY_ACTORS" for row in out["unresolved"])


def test_s3_05_scene_cut_is_hard_barrier():
    frames, trajectory = _c_fixture(cut=True)
    out = s3.recover_short_occlusion_contacts(frames, trajectory, _empty_contacts())
    assert out["verified"] == []
    assert any(row["reason"] == "SCENE_CUT_BARRIER" for row in out["unresolved"])


def test_s3_06_non_proof_anchor_cannot_be_recovered():
    frames, trajectory = _c_fixture(anchor_proof=False)
    out = s3.recover_short_occlusion_contacts(frames, trajectory, _empty_contacts())
    assert out["verified"] == []


def test_s3_07_gap_beyond_dormant_horizon_cannot_be_recovered():
    frames, trajectory = _c_fixture(gap_ms=500)
    out = s3.recover_short_occlusion_contacts(frames, trajectory, _empty_contacts())
    assert out["verified"] == []


def test_s3_08_single_weak_support_frame_is_never_enough():
    frames, trajectory = _b_fixture()
    out = s3.recover_short_occlusion_contacts(
        frames, trajectory, _empty_contacts(), video_path="synthetic.mp4",
        flow_frame_provider=_flow_provider(count=1),
    )
    assert out["verified"] == []
    assert any(row["reason"] == "FLOW_INSUFFICIENT_MULTIFRAME_SUPPORT" for row in out["unresolved"])


def test_s3_09_existing_verified_a4_contact_blocks_duplicate_recovery():
    frames, trajectory = _c_fixture()
    existing = _empty_contacts()
    existing["accepted"] = [{"media_ms": 900, "player_track_id": "p001", "status": "VERIFIED"}]
    out = s3.recover_short_occlusion_contacts(frames, trajectory, existing)
    assert out["verified"] == []


def test_s3_10_apply_adds_only_verified_aggregate_and_does_not_mutate_inputs():
    frames, trajectory = _c_fixture()
    contacts = _empty_contacts()
    contacts["unresolved"] = [{
        "media_ms": 900, "player_track_id": "p001", "status": "CANDIDATE_OCCLUDED",
        "proof_eligible": False,
    }]
    contacts["contacts"] = copy.deepcopy(contacts["unresolved"])
    before = copy.deepcopy(contacts)
    recovery = s3.recover_short_occlusion_contacts(frames, trajectory, contacts)
    applied = s3.apply_recovered_contacts(contacts, recovery)
    assert contacts == before
    assert len(applied["accepted"]) == 1
    assert applied["accepted"][0]["proof_eligible"] is True
    assert applied["unresolved"] == []
    assert any(r.get("resolution_reason") == "SUPERSEDED_BY_STEP3_VERIFIED_RECOVERY"
               for r in applied["rejected"])
    assert applied["metrics"]["step3_recovered"] == 1


def test_s3_11_support_candidates_remain_support_only_and_inputs_are_unchanged():
    frames, trajectory = _b_fixture()
    frames_before = copy.deepcopy(frames)
    trajectory_before = copy.deepcopy(trajectory)
    out = s3.recover_short_occlusion_contacts(
        frames, trajectory, _empty_contacts(), video_path="synthetic.mp4",
        flow_frame_provider=_flow_provider(),
    )
    assert out["verified"]
    assert frames == frames_before
    assert trajectory == trajectory_before
    raw = frames[4]["a7_ball_support_candidates"][0]
    assert raw["support_only"] is True
    assert raw["proof_eligible"] is False


def _exact_tap_fixture(*, a3_reacquisition=True, authority_tap=True, competitor=False):
    selected = {"x": .40, "y": .40, "w": .20, "h": .30}
    anchor_actor = _player("p001", x=.45, y=.40, w=.20, h=.30)
    middle_actor = _player("p001", x=.38, y=.40, w=.20, h=.30)
    final_actor = _player("p001", x=.30, y=.40, w=.20, h=.30)
    players = [anchor_actor]
    if competitor:
        players.append(_player("p002", x=.46, y=.40, w=.20, h=.30))
    seed = _support(.55, .68, .004)
    middle = _support(.57, .66, .008)
    final = _support(.59, .64, .08)
    if a3_reacquisition:
        final.update({"support_only": False, "a3_eligible": True})
    frames = [
        _frame(1000, players, [seed]),
        _frame(1033, [middle_actor], [middle]),
        _frame(1067, [final_actor], [final]),
    ]
    frames[0]["global_target"] = {
        "status": "VERIFIED",
        "reason": "OK_EXACT",
        "local_track_id": "p001",
        "candidate_local_track_ids": ["p001"],
        "proof_eligible": True,
        "authority_box": selected,
        "authority_tap": authority_tap,
        "authority_primary_source": "USER_TAP",
    }
    return frames


def test_s3_12_exact_target_weak_ball_needs_flow_and_a3_reacquisition():
    out = s3.recover_short_occlusion_contacts(
        _exact_tap_fixture(), [], _empty_contacts(),
        video_path="synthetic.mp4", flow_frame_provider=_flow_provider(),
    )
    assert out["status"] == "VERIFIED"
    assert out["metrics"]["exact_target_support_verified"] == 1
    row = out["verified"][0]
    assert row["media_ms"] == 1000
    assert row["player_track_id"] == "p001"
    assert row["player_actor_key"] == "GLOBAL_TARGET"
    assert row["recovery_mode"] == "EXACT_TARGET_SUPPORT_PATH"
    assert row["proof_eligible"] is True
    assert row["recovery_evidence"]["raw_support_proof_eligible"] is False
    assert row["recovery_evidence"]["a3_reacquisition_ms"] == 1067
    assert row["separation_gain_h"] >= s3.EXACT_TAP_MIN_SEPARATION_GAIN_H


def test_s3_13_exact_target_single_weak_proposal_never_proves_contact():
    out = s3.recover_short_occlusion_contacts(
        _exact_tap_fixture(a3_reacquisition=False), [], _empty_contacts(),
        video_path="synthetic.mp4", flow_frame_provider=_flow_provider(),
    )
    assert out["verified"] == []


def test_s3_14_non_tap_exact_identity_cannot_seed_support_recovery():
    out = s3.recover_short_occlusion_contacts(
        _exact_tap_fixture(authority_tap=False), [], _empty_contacts(),
        video_path="synthetic.mp4", flow_frame_provider=_flow_provider(),
    )
    assert out["verified"] == []


def test_s3_15_competing_lower_body_actor_blocks_exact_target_recovery():
    out = s3.recover_short_occlusion_contacts(
        _exact_tap_fixture(competitor=True), [], _empty_contacts(),
        video_path="synthetic.mp4", flow_frame_provider=_flow_provider(),
    )
    assert out["verified"] == []
    assert any(
        row["reason"] == "EXACT_TARGET_SUPPORT_COMPETING_LOWER_BODY_ACTOR"
        for row in out["unresolved"]
    )


def _exact_tap_measured_release_fixture(*, release_kind="RELEASE", competitor=False):
    selected = {"x": .40, "y": .40, "w": .20, "h": .30}
    actor = _player("p001", x=.45, y=.40, w=.20, h=.30)
    anchor_players = [actor]
    if competitor:
        anchor_players.append(_player("p002", x=.45, y=.40, w=.20, h=.30))
    frames = [
        _frame(1000, anchor_players),
        _frame(1033, [actor]),
        _frame(1067, [actor]),
    ]
    frames[0]["global_target"] = {
        "status": "VERIFIED",
        "reason": "OK_EXACT",
        "local_track_id": "p001",
        "candidate_local_track_ids": ["p001"],
        "proof_eligible": True,
        "authority_box": selected,
        "authority_tap": True,
        "authority_primary_source": "USER_TAP",
    }
    anchor_ball = _measured(1000, .55, .68)
    release_ball = _measured(1067, .59, .64)
    contacts = _empty_contacts()
    contacts["rejected"] = [
        {
            "contact_id": "anchor_contact",
            "media_ms": 1000,
            "scene_id": "s1",
            "player_track_id": "p001",
            "player_association_state": "VERIFIED_LOCAL",
            "ball_before": _measured(967, .53, .70),
            "ball_at_contact": anchor_ball,
            "ball_after": _measured(1033, .57, .66),
            "contact_geometry": {"distance_h": .18, "score": .78},
            "possession_evidence": {"kind": "CONTROL_TOUCH", "score": .8},
            "trajectory_evidence": {"score": .20},
            "temporal_continuity": 1.0,
            "rejection_reasons": [],
        },
        {
            "contact_id": "release_contact",
            "media_ms": 1067,
            "scene_id": "s1",
            "player_track_id": "p001",
            "player_association_state": "VERIFIED_LOCAL",
            "ball_before": _measured(1033, .57, .66),
            "ball_at_contact": release_ball,
            "ball_after": _measured(1100, .63, .61),
            "contact_geometry": {"distance_h": .62, "score": .45},
            "possession_evidence": {"kind": release_kind, "score": 1.0},
            "trajectory_evidence": {"score": .8},
            "temporal_continuity": 1.0,
            "rejection_reasons": ["CONTACT_GEOMETRY_WEAK"],
        },
    ]
    contacts["contacts"] = copy.deepcopy(contacts["rejected"])
    return frames, contacts


def test_s3_16_exact_tap_body_and_ball_flow_can_bridge_measured_release():
    frames, contacts = _exact_tap_measured_release_fixture()
    before = copy.deepcopy((frames, contacts))

    out = s3.recover_short_occlusion_contacts(
        frames, [], contacts,
        video_path="synthetic.mp4", flow_frame_provider=_flow_provider(),
    )

    assert (frames, contacts) == before
    assert out["status"] == "VERIFIED"
    assert out["metrics"]["exact_target_body_flow_releases"] == 1
    row = out["verified"][0]
    assert row["media_ms"] == 1000
    assert row["player_track_id"] == "p001"
    assert row["recovery_mode"] == "EXACT_TARGET_BODY_FLOW_RELEASE"
    assert row["recovery_evidence"]["release_evidence_ms"] == 1067
    assert row["recovery_evidence"]["body_flow_status"] == "VERIFIED_PATH"
    assert row["recovery_evidence"]["ball_flow_status"] == "VERIFIED_PATH"


def test_s3_17_exact_tap_body_flow_requires_independent_a4_release_transition():
    frames, contacts = _exact_tap_measured_release_fixture(release_kind="CONTROL_TOUCH")
    out = s3.recover_short_occlusion_contacts(
        frames, [], contacts,
        video_path="synthetic.mp4", flow_frame_provider=_flow_provider(),
    )
    assert not any(
        row.get("recovery_mode") == "EXACT_TARGET_BODY_FLOW_RELEASE"
        for row in out["verified"]
    )


def test_s3_18_exact_tap_body_flow_rejects_competing_contact_actor():
    frames, contacts = _exact_tap_measured_release_fixture(competitor=True)
    out = s3.recover_short_occlusion_contacts(
        frames, [], contacts,
        video_path="synthetic.mp4", flow_frame_provider=_flow_provider(),
    )
    assert not any(
        row.get("recovery_mode") == "EXACT_TARGET_BODY_FLOW_RELEASE"
        for row in out["verified"]
    )
    assert any(
        row.get("reason") == "EXACT_TARGET_MEASURED_COMPETING_LOWER_BODY_ACTOR"
        for row in out["unresolved"]
    )


def _tap_continuity_release_fixture(*, competing_body=False, competing_ball=False):
    def actor(ms):
        left = {1000: .45, 1033: .43, 1067: .41, 1100: .39,
                1133: .38, 1166: .34, 1200: .30}[ms]
        return _player("p001", x=left, y=.40, w=.20, h=.30)

    frames = []
    for ms in (1000, 1033, 1067, 1100, 1133, 1166, 1200):
        players = [actor(ms)]
        if competing_body and ms == 1067:
            players.append(_player("p002", x=.415, y=.40, w=.20, h=.30))
        support = []
        if ms == 1133:
            support = [_support(.55, .68, .004)]
            if competing_ball:
                support.append(_support(.48, .67, .004))
        elif ms == 1166:
            support = [_support(.57, .66, .008)]
        elif ms == 1200:
            support = [_support(.59, .64, .08)]
            support[0].update({"support_only": False, "a3_eligible": True})
        # A high-confidence spare ball is deliberately remote from the tapped
        # body and must never substitute for the continuous release path.
        support.append({
            **_support(.05, .55, .20),
            "support_only": False,
            "a3_eligible": True,
        })
        frames.append(_frame(ms, players, support))

    frames[0]["global_target"] = {
        "status": "VERIFIED",
        "reason": "OK_NEAREST_TAP_FRAME",
        "local_track_id": "p001",
        "candidate_local_track_ids": ["p001"],
        "proof_eligible": True,
        "authority_box": {"x": .40, "y": .40, "w": .20, "h": .30},
        "authority_tap": True,
        "authority_primary_source": "USER_TAP",
        "authority_media_ms": 984,
    }
    return frames


def test_s3_19_nearest_tap_continuity_recovers_only_the_active_release_ball():
    out = s3.recover_short_occlusion_contacts(
        _tap_continuity_release_fixture(), [], _empty_contacts(),
        video_path="synthetic.mp4", flow_frame_provider=_flow_provider(),
    )

    rows = [row for row in out["verified"]
            if row.get("recovery_mode") == "TAP_CONTINUITY_SUPPORT_RELEASE"]
    assert len(rows) == 1
    row = rows[0]
    evidence = row["recovery_evidence"]
    assert row["media_ms"] == 1133
    assert row["player_track_id"] == "p001"
    assert row["player_actor_key"] == "GLOBAL_TARGET"
    assert row["ball_after"]["media_ms"] == 1200
    assert row["ball_after"]["box"]["x"] > .50
    assert evidence["tap_anchor_ms"] == 1000
    assert evidence["actor_continuity_status"] == "VERIFIED_PATH"
    assert evidence["ball_flow_status"] == "VERIFIED_PATH"
    assert evidence["flow_detector_match_count"] >= s3.FLOW_MIN_NODES - 1
    assert evidence["a3_reacquisition_proof_eligible"] is True
    assert evidence["remote_spare_ball_used"] is False


def test_s3_20_competing_body_breaks_tap_continuity_fail_closed():
    out = s3.recover_short_occlusion_contacts(
        _tap_continuity_release_fixture(competing_body=True), [], _empty_contacts(),
        video_path="synthetic.mp4", flow_frame_provider=_flow_provider(),
    )
    assert not any(row.get("recovery_mode") == "TAP_CONTINUITY_SUPPORT_RELEASE"
                   for row in out["verified"])


def test_s3_21_competing_release_ball_path_fails_closed():
    out = s3.recover_short_occlusion_contacts(
        _tap_continuity_release_fixture(competing_ball=True), [], _empty_contacts(),
        video_path="synthetic.mp4", flow_frame_provider=_flow_provider(),
    )
    assert not any(row.get("recovery_mode") == "TAP_CONTINUITY_SUPPORT_RELEASE"
                   for row in out["verified"])
