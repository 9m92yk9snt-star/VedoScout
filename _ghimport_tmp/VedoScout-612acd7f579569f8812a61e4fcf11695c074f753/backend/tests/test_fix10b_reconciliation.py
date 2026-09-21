"""FIX10B target-centered/full-context reconciliation regression tests."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import fix10b_reconciliation as f10b  # noqa: E402


def touch(ms, track, *, target=False, team="target_team", confidence=.95):
    return {
        "touch_id": f"touch_{track}_{ms}",
        "media_ms": ms,
        "representative_ms": ms,
        "scene_id": "scene_007",
        "player_track_id": track,
        "global_target_id": "GLOBAL_TARGET" if target else None,
        "status": "VERIFIED",
        "proof_eligible": True,
        "team_relation": {
            "status": "SUPPORTING",
            "team": team,
            "confidence": confidence,
            "source": "TEST_PHYSICAL_TEAM",
        },
    }


def strike(ms, track, *, target=False, sid=None):
    return {
        "strike_id": sid or f"strike_{track}_{ms}",
        "touch_id": f"touch_{track}_{ms}",
        "media_ms": ms,
        "scene_id": "scene_007",
        "player_track_id": track,
        "global_target_id": "GLOBAL_TARGET" if target else None,
        "status": "VERIFIED_PHYSICAL_RELEASE",
        "proof_eligible": True,
    }


def outcome(strike_row, *, goal=True, crossing_ms=None):
    cms = crossing_ms if crossing_ms is not None else int(strike_row["media_ms"]) + 650
    return {
        "status": "ok",
        "strike_id": strike_row["strike_id"],
        "touch_id": strike_row["touch_id"],
        "media_ms": strike_row["media_ms"],
        "scene_id": strike_row["scene_id"],
        "strike_actor_track_id": strike_row["player_track_id"],
        "physical_outcome": "GOAL_PLANE_CROSSING" if goal else "UNRESOLVED",
        "goal_plane_crossing": {
            "status": "VERIFIED" if goal else "UNRESOLVED",
            "crossing_ms": cms if goal else None,
            "reason": "WHOLE_BALL_CROSSED_TIME_ALIGNED_GOAL_PLANE" if goal else "NO_PROOF",
            "evidence": [{"from_ms": cms - 80, "to_ms": cms + 40}] if goal else [],
        },
    }


def trace(touches, strikes, outcomes):
    return {
        "trace_id": "dense_lse_goal_window",
        "window": {"dense_window_id": "dense_lse_goal_window", "scene_id": "scene_007",
                   "start_ms": 53000, "end_ms": 59000},
        "touch_graph": {"touches": list(touches)},
        "strike_evidence": list(strikes),
        "outcome_evidence": list(outcomes),
    }


def physical(trace_rows, status="ok"):
    return {"version": 1, "status": status, "traces": list(trace_rows)}


def canonical_event(kind="GOAL", action="SHOT", ms=1000):
    return {
        "event_id": "existing_event",
        "global_target_id": "GLOBAL_TARGET",
        "scene_id": "scene_007",
        "sequence_id": "seq_1",
        "source_sequence_ids": ["seq_1"],
        "source_action_ids": ["a1"],
        "start_ms": ms - 100,
        "contact_ms": ms,
        "end_ms": ms + 600,
        "canonical_ms": ms,
        "canonical_event_type": kind,
        "canonical_action_type": action,
        "canonical_outcome": "GOAL" if kind == "GOAL" else "UNKNOWN",
        "causal_verified": kind == "GOAL",
        "resolution_reason": "OLD_CANONICAL_RESULT",
        "actor_local_track_id": "p001",
        "identity_resolution": "VISIBLE_TARGET_MATCH",
        "foot": "UNKNOWN",
        "pressure": {},
        "details": [],
        "proof": {"evidence_ms": [ms], "proof_eligible": True, "causal_verified": kind == "GOAL"},
        "causal_chain": {},
        "receiver_team_resolution": None,
    }


def canonical(events):
    return {
        "version": 1,
        "status": "ok" if events else "empty",
        "global_target_id": "GLOBAL_TARGET",
        "timebase": "canonical_media_ms",
        "events": list(events),
        "unresolved": [],
        "rejected": [],
        "counts": {},
        "metrics": {},
    }


def test_fix10b01_target_pass_teammate_scores_becomes_assist_not_target_goal():
    """Critical contract: analysed player assists; teammate owns the goal."""
    target = strike(1000, "p001", target=True)
    scorer = strike(2200, "p003")
    tr = trace(
        [touch(1000, "p001", target=True), touch(1500, "p003")],
        [target, scorer],
        [outcome(target, goal=False), outcome(scorer, goal=True, crossing_ms=2600)],
    )
    # Simulate the exact class of attribution error we must correct: old
    # canonical called the target's release a GOAL/SHOT.
    out = f10b.reconcile_canonical_events(canonical([canonical_event("GOAL", "SHOT", 1000)]), physical([tr]))
    assert len(out["events"]) == 1
    event = out["events"][0]
    assert event["canonical_event_type"] == "ASSIST"
    assert event["canonical_action_type"] == "PASS"
    assert event["canonical_outcome"] == "TEAMMATE_GOAL"
    assert event["actor_local_track_id"] == "p001"
    assert event["causal_chain"]["receiver_local_track_id"] == "p003"
    assert event["causal_chain"]["teammate_shot_ms"] == 2200
    assert event["causal_chain"]["goal_outcome_ms"] == 2600
    assert out["metrics"]["assists"] == 1
    assert out["metrics"]["goals"] == 0
    assert event["reconciliation_authority"] == "FIX10B_PHYSICAL_RECONCILIATION"


def test_fix10b02_target_strike_with_verified_crossing_becomes_target_goal():
    target = strike(3000, "p001", target=True)
    tr = trace([touch(3000, "p001", target=True)], [target], [outcome(target, goal=True, crossing_ms=3500)])
    out = f10b.reconcile_canonical_events(canonical([canonical_event("SHOT", "SHOT", 3000)]), physical([tr]))
    event = out["events"][0]
    assert event["canonical_event_type"] == "GOAL"
    assert event["canonical_action_type"] == "SHOT"
    assert event["canonical_outcome"] == "GOAL"
    assert out["metrics"]["goals"] == 1
    assert out["metrics"]["shots"] == 1


def test_fix10b03_extra_teammate_touch_breaks_direct_assist_chain():
    target = strike(1000, "p001", target=True)
    receiver_release = strike(1700, "p003")
    scorer = strike(2400, "p004")
    tr = trace(
        [touch(1000, "p001", target=True), touch(1400, "p003"), touch(1900, "p004")],
        [target, receiver_release, scorer],
        [outcome(target, goal=False), outcome(receiver_release, goal=False), outcome(scorer, goal=True, crossing_ms=2700)],
    )
    out = f10b.reconcile_canonical_events(canonical([canonical_event("PASS", "PASS", 1000)]), physical([tr]))
    assert out["events"][0]["canonical_event_type"] == "PASS"
    assert out["metrics"]["assists"] == 0


def test_fix10b04_opponent_receiver_never_creates_assist():
    target = strike(1000, "p001", target=True)
    opponent = strike(2200, "p002")
    tr = trace(
        [touch(1000, "p001", target=True), touch(1500, "p002", team="opponent")],
        [target, opponent],
        [outcome(target, goal=False), outcome(opponent, goal=True, crossing_ms=2500)],
    )
    out = f10b.reconcile_canonical_events(canonical([canonical_event("PASS", "PASS", 1000)]), physical([tr]))
    assert out["events"][0]["canonical_event_type"] == "PASS"
    assert out["metrics"]["assists"] == 0


def test_fix10b05_unresolved_goal_crossing_never_promotes_scoring_event():
    target = strike(1000, "p001", target=True)
    receiver = strike(2200, "p003")
    tr = trace(
        [touch(1000, "p001", target=True), touch(1500, "p003")],
        [target, receiver],
        [outcome(target, goal=False), outcome(receiver, goal=False)],
    )
    out = f10b.reconcile_canonical_events(canonical([canonical_event("PASS", "PASS", 1000)]), physical([tr]))
    assert out["events"][0]["canonical_event_type"] == "PASS"
    assert out["metrics"]["assists"] == 0
    assert out["metrics"]["goals"] == 0


def test_fix10b06_missing_model_event_can_be_synthesised_from_complete_physical_proof():
    target = strike(1000, "p001", target=True)
    scorer = strike(2200, "p003")
    tr = trace(
        [touch(1000, "p001", target=True), touch(1500, "p003")],
        [target, scorer],
        [outcome(target, goal=False), outcome(scorer, goal=True, crossing_ms=2600)],
    )
    out = f10b.reconcile_canonical_events(canonical([]), physical([tr]))
    assert len(out["events"]) == 1
    event = out["events"][0]
    assert event["canonical_event_type"] == "ASSIST"
    assert event["identity_resolution"] == "FIX10A_VERIFIED_GLOBAL_TARGET_PHYSICAL_RELEASE"
    assert event["proof"]["fix10b_physical"]["proof_eligible"] is True


def test_fix10b07_overlapping_trace_duplicate_does_not_double_count_assist():
    target = strike(1000, "p001", target=True)
    scorer = strike(2200, "p003")
    base = trace(
        [touch(1000, "p001", target=True), touch(1500, "p003")],
        [target, scorer],
        [outcome(target, goal=False), outcome(scorer, goal=True, crossing_ms=2600)],
    )
    dup = dict(base)
    dup["trace_id"] = "dense_overlap"
    out = f10b.reconcile_canonical_events(canonical([]), physical([base, dup]))
    assert len(out["events"]) == 1
    assert out["metrics"]["assists"] == 1


def test_fix10b08_target_goal_and_assist_same_contact_conflict_fails_closed():
    target = strike(1000, "p001", target=True)
    scorer = strike(2200, "p003")
    tr = trace(
        [touch(1000, "p001", target=True), touch(1500, "p003")],
        [target, scorer],
        [outcome(target, goal=True, crossing_ms=1800), outcome(scorer, goal=True, crossing_ms=2600)],
    )
    out = f10b.reconcile_canonical_events(canonical([canonical_event("SHOT", "SHOT", 1000)]), physical([tr]))
    # Contradictory physical scoring ownership is diagnostic only; it cannot
    # silently choose one story.
    assert out["events"][0]["canonical_event_type"] == "SHOT"
    assert out["reconciliation"]["proposals_contradictory"] == 2
    assert out["reconciliation"]["proposals_applied"] == 0
