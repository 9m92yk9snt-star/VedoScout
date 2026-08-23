"""FIX10A4 — multi-signal physical ball-contact tests."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import ball_contact_engine as bce  # noqa: E402


P1 = {"x": 0.10, "y": 0.20, "w": 0.10, "h": 0.30}


def _player(track_id, box, state="VERIFIED_LOCAL"):
    return {
        "local_track_id": track_id,
        "candidate_local_track_ids": [track_id] if track_id else [],
        "box": dict(box),
        "confidence": 0.9,
        "association_state": state,
    }


def _frame(ms, players, **extra):
    return {
        "media_ms": int(ms), "scene_id": "scene_001",
        "players": list(players), "used_fallback": False,
        "time_authority": "ACTUAL_MEDIA_PTS", **extra,
    }


def _ball_row(ms, x, *, state="MEASURED", proof=True, y=0.48):
    return {
        "media_ms": int(ms), "state": state,
        "box": {"x": x, "y": y, "w": 0.02, "h": 0.02} if x is not None else None,
        "confidence": 0.9 if x is not None else 0.0,
        "proof_eligible": bool(proof),
        "time_authority": "ACTUAL_MEDIA_PTS",
    }


def _strike_fixture(players=None, middle_state="MEASURED", middle_proof=True):
    ps = players or [_player("p001", P1)]
    frames = [_frame(960, ps), _frame(1000, ps), _frame(1040, ps)]
    balls = [
        _ball_row(960, 0.14),
        _ball_row(1000, 0.14, state=middle_state, proof=middle_proof),
        _ball_row(1040, 0.22),
    ]
    return frames, balls


def test_a401_lower_body_contact_plus_trajectory_change_resolves_touch():
    frames, balls = _strike_fixture()
    result = bce.resolve_contacts(bce.detect_contact_candidates(frames, balls))
    assert len(result["accepted"]) == 1
    touch = result["accepted"][0]
    assert touch["media_ms"] == 1000
    assert touch["player_track_id"] == "p001"
    assert touch["status"] == "VERIFIED"
    assert touch["trajectory_evidence"]["score"] >= bce.TRAJECTORY_SIGNAL_MIN


def test_a402_nearby_non_touching_player_is_not_credited():
    p2 = {"x": 0.30, "y": 0.20, "w": 0.10, "h": 0.30}
    players = [_player("p001", P1), _player("p002", p2)]
    frames, balls = _strike_fixture(players=players)
    result = bce.resolve_contacts(bce.detect_contact_candidates(frames, balls))
    assert [r["player_track_id"] for r in result["accepted"]] == ["p001"]
    assert any(
        r.get("player_track_id") == "p002"
        and "BALL_OUTSIDE_LOWER_BODY_CONTACT_ZONE" in (r.get("rejection_reasons") or [])
        for r in result["rejected"]
    )


def test_a403_two_equal_physical_bodies_remain_unresolved_hypotheses():
    left = {"x": 0.09, "y": 0.20, "w": 0.10, "h": 0.30}
    right = {"x": 0.11, "y": 0.20, "w": 0.10, "h": 0.30}
    players = [_player("p010", left), _player("p012", right)]
    frames, balls = _strike_fixture(players=players)
    result = bce.resolve_contacts(bce.detect_contact_candidates(frames, balls))
    assert result["accepted"] == []
    assert len(result["unresolved"]) == 1
    row = result["unresolved"][0]
    assert row["status"] == "HYPOTHESES"
    assert set(row["player_candidate_track_ids"]) == {"p010", "p012"}


def test_a404_occluded_contact_needs_before_after_physics_and_stays_unverified():
    frames, balls = _strike_fixture(middle_state="PREDICTED_SHORT_GAP", middle_proof=False)
    result = bce.resolve_contacts(bce.detect_contact_candidates(frames, balls))
    assert result["accepted"] == []
    assert len(result["unresolved"]) == 1
    row = result["unresolved"][0]
    assert row["media_ms"] == 1000
    assert row["status"] == "CANDIDATE_OCCLUDED"
    assert row["proof_eligible"] is False


def test_a405_missing_ball_cannot_create_verified_contact():
    frames, _ = _strike_fixture()
    balls = [_ball_row(1000, None, state="MISSING", proof=False)]
    result = bce.resolve_contacts(bce.detect_contact_candidates(frames, balls))
    assert result["contacts"] == []
    assert result["accepted"] == []


def test_a406_primary_action_story_is_not_an_input_to_contact_truth():
    frames, balls = _strike_fixture()
    baseline = bce.resolve_contacts(bce.detect_contact_candidates(frames, balls))
    altered = copy.deepcopy(frames)
    for frame in altered:
        frame["primary_action_story"] = "#12 definitely scores"
        frame["model_confidence"] = 0.999
    challenged = bce.resolve_contacts(bce.detect_contact_candidates(altered, balls))
    assert [(r["media_ms"], r["player_track_id"]) for r in challenged["accepted"]] == [
        (r["media_ms"], r["player_track_id"]) for r in baseline["accepted"]
    ]


def test_a407_generic_box_geometry_never_invents_left_or_right_foot():
    frames, balls = _strike_fixture()
    result = bce.resolve_contacts(bce.detect_contact_candidates(frames, balls))
    assert len(result["accepted"]) == 1
    assert result["accepted"][0]["foot"] == "UNKNOWN"
