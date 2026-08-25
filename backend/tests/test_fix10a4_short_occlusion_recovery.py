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
