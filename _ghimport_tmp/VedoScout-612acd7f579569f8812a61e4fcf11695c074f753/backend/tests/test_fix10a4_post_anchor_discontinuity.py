from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import short_occlusion_contact_recovery as s3


def _box(cx, cy, w=.03, h=.02):
    return {"x": cx - w / 2, "y": cy - h / 2, "w": w, "h": h}


def _player():
    return {
        "local_track_id": "p001",
        "candidate_local_track_ids": ["p001"],
        "box": {"x": .45, "y": .40, "w": .20, "h": .30},
        "association_state": "VERIFIED_LOCAL",
    }


def _frame(ms):
    return {
        "media_ms": ms,
        "scene_id": "s1",
        "used_fallback": False,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "cut_barrier": False,
        "players": [_player()],
        "ball_candidates": [],
        "a7_ball_support_candidates": [],
    }


def _measured(ms, cx, cy):
    return {
        "media_ms": ms,
        "state": "MEASURED",
        "box": _box(cx, cy),
        "confidence": .8,
        "proof_eligible": True,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "used_fallback": False,
        "provenance": "LOCAL_DENSE_DETECTOR",
    }


def _empty_contacts():
    return {
        "version": 1, "contacts": [], "accepted": [], "unresolved": [], "rejected": [],
        "metrics": {"accepted": 0, "unresolved": 0, "rejected": 0},
    }


def _valid_post_gap_fixture():
    frames = [_frame(500), _frame(567), _frame(900), _frame(933)]
    trajectory = [
        _measured(500, .55, .55),
        _measured(567, .55, .59),
        _measured(900, .55, .67),
        _measured(933, .58, .61),
    ]
    return frames, trajectory


def test_s3_post_anchor_discontinuity_blocks_false_measured_reacquisition():
    frames, trajectory = _valid_post_gap_fixture()
    trajectory.insert(3, {
        "media_ms": 915,
        "state": "PREDICTED_SHORT_GAP",
        "box": _box(.56, .66),
        "confidence": .2,
        "proof_eligible": False,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "used_fallback": False,
        "provenance": "KINEMATIC_SHORT_GAP_DISCONTINUITY_REJECTED",
    })
    out = s3.recover_short_occlusion_contacts(frames, trajectory, _empty_contacts())
    assert out["verified"] == []
    row = next(x for x in out["unresolved"]
               if x["reason"] == "POST_ANCHOR_TRAJECTORY_DISCONTINUITY_REJECTED")
    assert row["media_ms"] == 900
    assert row["next_measured_ms"] == 933
    assert row["discontinuity_rows"] == [{
        "media_ms": 915,
        "state": "PREDICTED_SHORT_GAP",
        "provenance": "KINEMATIC_SHORT_GAP_DISCONTINUITY_REJECTED",
        "proof_eligible": False,
    }]


def test_s3_immediate_measured_outgoing_without_contradiction_still_recovers():
    frames, trajectory = _valid_post_gap_fixture()
    out = s3.recover_short_occlusion_contacts(frames, trajectory, _empty_contacts())
    assert out["status"] == "VERIFIED"
    assert len(out["verified"]) == 1
    assert out["verified"][0]["media_ms"] == 900
    assert out["verified"][0]["recovery_mode"] == "POST_GAP_MEASURED_REACQUISITION"


def test_s3_pre_anchor_discontinuity_does_not_block_legitimate_reacquisition():
    frames, trajectory = _valid_post_gap_fixture()
    trajectory.insert(2, {
        "media_ms": 700,
        "state": "PREDICTED_SHORT_GAP",
        "box": _box(.55, .61),
        "confidence": .2,
        "proof_eligible": False,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "used_fallback": False,
        "provenance": "DORMANT_REACQUIRE_DISCONTINUITY_REJECTED",
    })
    out = s3.recover_short_occlusion_contacts(frames, trajectory, _empty_contacts())
    assert out["status"] == "VERIFIED"
    assert len(out["verified"]) == 1
    assert out["verified"][0]["media_ms"] == 900
