from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import ball_trajectory as bt


def _anchor():
    return {
        "media_ms": 1000,
        "state": "MEASURED_REACQUISITION",
        "box": {"x": .49, "y": .49, "w": .02, "h": .02},
        "confidence": .08,
        "proof_eligible": True,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "used_fallback": False,
    }


def _player():
    # Foot centre is close to the distant candidate, not the seed ball.
    return {"local_track_id": "p002", "association_state": "VERIFIED_LOCAL",
            "box": {"x": .68, "y": .35, "w": .10, "h": .20}}


def _frame(ms, x, *, player=True, cut=False):
    return {
        "media_ms": ms, "scene_id": "s1", "cut_barrier": cut,
        "used_fallback": False, "time_authority": "ACTUAL_MEDIA_PTS",
        "players": [_player()] if player else [],
        "ball_candidates": [{"box": {"x": x, "y": .49, "w": .02, "h": .02},
                             "confidence": .08}],
    }


def test_fix11_release_anchor_reacquires_only_after_second_frame_confirms_jump():
    frames = [_frame(1017, .72), _frame(1034, .74), _frame(1051, .76)]
    rows = bt.reconstruct_ball_trajectory_from_release_anchor(frames, _anchor(), "s1")

    assert [row["media_ms"] for row in rows] == [1000, 1017, 1034, 1051]
    assert rows[0]["provenance"] == "VERIFIED_RELEASE_CONTACT_BALL_AFTER"
    assert rows[1]["provenance"] == "RELEASE_ANCHOR_REACQUISITION_CONFIRMED"
    assert all(row["proof_eligible"] is True for row in rows)


def test_fix11_unconfirmed_jump_never_becomes_measured_path():
    rows = bt.reconstruct_ball_trajectory_from_release_anchor(
        [_frame(1017, .72), _frame(1120, .74)], _anchor(), "s1"
    )

    assert len(rows) == 1
    assert rows[0]["media_ms"] == 1000


def test_fix11_release_anchor_path_stops_at_scene_cut():
    rows = bt.reconstruct_ball_trajectory_from_release_anchor(
        [_frame(1017, .51), _frame(1034, .53, cut=True), _frame(1051, .55)],
        _anchor(), "s1",
    )

    assert [row["media_ms"] for row in rows] == [1000, 1017]


def test_fix11_invalid_or_non_proof_anchor_does_not_seed_path():
    anchor = _anchor()
    anchor["proof_eligible"] = False
    assert bt.reconstruct_ball_trajectory_from_release_anchor(
        [_frame(1017, .51)], anchor, "s1"
    ) == []
