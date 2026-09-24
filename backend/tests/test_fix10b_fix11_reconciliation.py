"""FIX11 reconciliation regressions for saved shots and teammate track splits."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import fix10b_reconciliation as f10b  # noqa: E402


def _team():
    return {
        "status": "SUPPORTING",
        "team": "target_team",
        "confidence": 0.96,
        "source": "TEST",
    }


def _jersey(number="10"):
    return {
        "status": "VERIFIED",
        "number": number,
        "top_posterior": 0.96,
        "margin": 0.80,
        "agreeing_frames": 3,
    }


def _touch(ms, track, *, target=False, jersey=None):
    return {
        "touch_id": f"touch_{track}_{ms}",
        "media_ms": ms,
        "representative_ms": ms,
        "scene_id": "scene_1",
        "player_track_id": track,
        "global_target_id": "GLOBAL_TARGET" if target else None,
        "status": "VERIFIED",
        "proof_eligible": True,
        "team_relation": _team(),
        "jersey_posterior": _jersey(jersey) if jersey else None,
    }


def _strike(ms, track, *, target=False):
    return {
        "strike_id": f"strike_{track}_{ms}",
        "touch_id": f"touch_{track}_{ms}",
        "media_ms": ms,
        "scene_id": "scene_1",
        "player_track_id": track,
        "global_target_id": "GLOBAL_TARGET" if target else None,
        "status": "VERIFIED_PHYSICAL_RELEASE",
        "proof_eligible": True,
    }


def _goal_outcome(strike, crossing_ms):
    return {
        "status": "ok",
        "strike_id": strike["strike_id"],
        "media_ms": strike["media_ms"],
        "physical_outcome": "GOAL_PLANE_CROSSING",
        "goal_plane_crossing": {
            "status": "VERIFIED",
            "crossing_ms": crossing_ms,
            "reason": "WHOLE_BALL_CROSSED_TIME_ALIGNED_GOAL_PLANE",
            "evidence": [{"from_ms": crossing_ms - 60, "to_ms": crossing_ms + 20}],
        },
    }


def _save_outcome(strike):
    return {
        "status": "ok",
        "strike_id": strike["strike_id"],
        "media_ms": strike["media_ms"],
        "physical_outcome": "GOALKEEPER_SAVE_EVIDENCE",
        "goal_plane_crossing": {
            "status": "UNRESOLVED",
            "crossing_ms": None,
            "reason": "NO_VERIFIED_CROSSING",
            "evidence": [],
        },
        "intervention": {
            "status": "VERIFIED",
            "player_track_id": "gk_1",
            "media_ms": strike["media_ms"] + 500,
            "kind": "DEFLECTION",
        },
        "intervention_role": {
            "status": "VERIFIED",
            "role": "GOALKEEPER",
            "reason": "MULTI_FRAME_ROLE_EVIDENCE",
        },
        "save_evidence": {
            "status": "VERIFIED",
            "reason": "KEEPER_INTERVENTION_WITH_NO_CROSSING",
        },
    }


def _frame(ms, players):
    return {
        "media_ms": ms,
        "scene_id": "scene_1",
        "players": [
            {"local_track_id": track, "box": box}
            for track, box in players
        ],
    }


def _box(x):
    return {"x": x, "y": 0.25, "w": 0.10, "h": 0.32}


def _empty_canonical():
    return {
        "version": 1,
        "status": "empty",
        "global_target_id": "GLOBAL_TARGET",
        "timebase": "canonical_media_ms",
        "events": [],
        "unresolved": [],
        "rejected": [],
        "counts": {},
        "metrics": {},
    }


def test_fix11_verified_keeper_save_can_create_missing_canonical_shot():
    target = _strike(23680, "p001", target=True)
    trace = {
        "trace_id": "save_window",
        "touch_graph": {"touches": [_touch(23680, "p001", target=True)]},
        "strike_evidence": [target],
        "outcome_evidence": [_save_outcome(target)],
        "decoded_frames": [],
    }
    proposals = f10b.proposals_from_trace(trace)
    assert len(proposals) == 1
    assert proposals[0]["kind"] == "SHOT"
    assert proposals[0]["canonical_outcome"] == "SAVED"

    out = f10b.reconcile_canonical_events(_empty_canonical(), {
        "status": "ok",
        "traces": [trace],
    })
    assert out["metrics"]["shots"] == 1
    assert out["metrics"]["goals"] == 0
    assert out["events"][0]["canonical_event_type"] == "SHOT"
    assert out["events"][0]["canonical_outcome"] == "SAVED"
    assert out["events"][0]["proof"]["save_proof"]["save_evidence"]["status"] == "VERIFIED"


def _assist_trace(*, concurrent=False):
    target_touch = _touch(1000, "p001", target=True)
    receiver = _touch(1500, "p010", jersey="10")
    scorer_touch = _touch(2500, "p099", jersey="10")
    target_strike = _strike(1000, "p001", target=True)
    scorer_strike = _strike(2500, "p099")
    frames = [
        _frame(1500, [("p010", _box(0.30))]),
        _frame(1800, [("p010", _box(0.34))]),
        _frame(
            1900,
            [("p010", _box(0.35)), ("p099", _box(0.36))]
            if concurrent else [("p010", _box(0.35))],
        ),
        _frame(2000, [("p099", _box(0.37))]),
        _frame(2300, [("p099", _box(0.40))]),
        _frame(2500, [("p099", _box(0.43))]),
    ]
    return {
        "trace_id": "assist_track_split",
        "touch_graph": {"touches": [target_touch, receiver, scorer_touch]},
        "strike_evidence": [target_strike, scorer_strike],
        "outcome_evidence": [_goal_outcome(scorer_strike, 3100)],
        "decoded_frames": frames,
    }


def test_fix11_assist_survives_verified_teammate_local_track_split():
    proposals = f10b.proposals_from_trace(_assist_trace())
    assists = [p for p in proposals if p["kind"] == "ASSIST"]
    assert len(assists) == 1
    assist = assists[0]
    assert assist["receiver_track_id"] == "p010"
    assert assist["scorer_track_id"] == "p099"
    assert assist["receiver_actor_stitch"]["status"] == "VERIFIED_STITCH"
    assert assist["receiver_actor_stitch"]["jersey_number"] == "10"


def test_fix11_track_stitch_fails_closed_when_two_ids_are_visible_together():
    proposals = f10b.proposals_from_trace(_assist_trace(concurrent=True))
    assert not any(p["kind"] == "ASSIST" for p in proposals)
