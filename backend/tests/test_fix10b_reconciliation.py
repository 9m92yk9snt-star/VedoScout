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


def test_fix10b09_target_recontact_breaks_early_dribble_release_assist_chain():
    target = strike(1000, "p001", target=True)
    scorer = strike(2200, "p003")
    tr = trace(
        [
            touch(1000, "p001", target=True),
            touch(1300, "p001", target=True),
            touch(1500, "p003"),
        ],
        [target, scorer],
        [outcome(target, goal=False), outcome(scorer, goal=True, crossing_ms=2600)],
    )
    proposals = f10b.proposals_from_trace(tr)
    assert not any(row["kind"] == "ASSIST" for row in proposals)


def test_fix10b10_target_reid_track_is_not_mistaken_for_teammate_receiver():
    target = strike(1000, "p001", target=True)
    scorer = strike(2200, "p003")
    tr = trace(
        [
            touch(1000, "p001", target=True),
            touch(1500, "p099", target=True),
            touch(1800, "p003"),
        ],
        [target, scorer],
        [outcome(target, goal=False), outcome(scorer, goal=True, crossing_ms=2600)],
    )
    proposals = f10b.proposals_from_trace(tr)
    assert not any(row["kind"] == "ASSIST" for row in proposals)


def _deflected_assist_trace(*, control=False, remote_x=.10, target_also_goal=False):
    target = strike(1000, "p001", target=True)
    target["active_ball_anchor"] = {
        "media_ms": 1080,
        "state": "MEASURED",
        "box": {"x": .47, "y": .60, "w": .02, "h": .02},
        "proof_eligible": True,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "used_fallback": False,
        "source": "VERIFIED_RELEASE_CONTACT_BALL_AFTER",
        "remote_spare_ball_used": False,
    }
    scorer = strike(2200, "p003")
    target_touch = touch(1000, "p001", target=True)
    remote = touch(2000, "p009", team="opponent")
    remote["ball_at_contact"] = {
        "media_ms": 2000,
        "state": "MEASURED",
        "box": {"x": remote_x, "y": .60, "w": .02, "h": .02},
        "proof_eligible": True,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "used_fallback": False,
    }
    scorer_touch = touch(2200, "p003", team=None, confidence=0)
    scorer_touch["team_relation"] = {
        "status": "UNRESOLVED", "team": None, "confidence": None,
        "reason": "CONFLICTING_DENSE_TEAM_LABELS",
    }
    scorer_touch["contact_geometry"] = {
        "actor_box_used": {"x": .48, "y": .30, "w": .10, "h": .30},
    }
    scorer_touch["ball_at_contact"] = {
        "media_ms": 2200,
        "state": "MEASURED",
        "box": {"x": .51, "y": .60, "w": .02, "h": .02},
        "proof_eligible": True,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "used_fallback": False,
    }
    target_outcome = outcome(target, goal=target_also_goal, crossing_ms=2600)
    target_outcome["intervention"] = {
        "status": "VERIFIED",
        "proof_eligible": True,
        "player_track_id": "p002",
        "media_ms": 1500,
        "kind": "DEFLECTION_OR_PARRY_LIKE",
        "player_box": {"x": .46, "y": .30, "w": .12, "h": .30},
        "ball_box": {"x": .49, "y": .60, "w": .02, "h": .02},
        "control_evidence": {
            "status": "VERIFIED" if control else "UNRESOLVED",
            "reason": "SAME_PLAYER_RETAINS_SLOW_BALL_ACROSS_MEASURED_INTERVAL" if control else "SUSTAINED_CONTROL_NOT_PROVEN",
        },
    }
    frames = []
    for ms in (1540, 1620, 1700):
        frames.append({
            "media_ms": ms, "scene_id": "scene_007", "cut_barrier": False,
            "players": [{
                "local_track_id": "p002", "association_state": "VERIFIED_LOCAL",
                "box": {"x": .46, "y": .30, "w": .12, "h": .30},
                "team": "opponent", "team_confidence": .94,
                "team_source": "KIT_CHROMA_DENSE_TAP_CLUSTER",
            }],
        })
    for ms in (2185, 2200, 2250):
        frames.append({
            "media_ms": ms, "scene_id": "scene_007", "cut_barrier": False,
            "players": [{
                "local_track_id": "p003", "association_state": "VERIFIED_LOCAL",
                "box": {"x": .48, "y": .30, "w": .10, "h": .30},
                "team": "target_team", "team_confidence": .95,
                "team_source": "KIT_CHROMA_DENSE_TAP_CLUSTER",
            }],
        })
    tr = trace(
        [target_touch, remote, scorer_touch],
        [target, scorer],
        [target_outcome, outcome(scorer, goal=True, crossing_ms=2600)],
    )
    tr["decoded_frames"] = frames
    return tr


def test_fix10b11_opponent_deflection_without_control_preserves_assist():
    tr = _deflected_assist_trace()
    proposals = f10b.proposals_from_trace(tr)
    assists = [row for row in proposals if row["kind"] == "ASSIST"]
    assert len(assists) == 1
    proof = assists[0]["deflection_proof"]
    assert proof["active_ball_lineage"]["status"] == "VERIFIED"
    assert len(proof["active_ball_lineage"]["ignored_remote_ball_touches"]) == 1
    assert assists[0]["scorer_track_id"] == "p003"


def test_fix10b12_sustained_defender_control_breaks_deflected_assist():
    proposals = f10b.proposals_from_trace(_deflected_assist_trace(control=True))
    assert not any(row["kind"] == "ASSIST" for row in proposals)


def test_fix10b13_intervening_touch_on_active_lineage_fails_closed():
    proposals = f10b.proposals_from_trace(_deflected_assist_trace(remote_x=.50))
    assert not any(row["kind"] == "ASSIST" for row in proposals)


def test_fix10b14_later_teammate_scoring_release_owns_goal_not_target_pass():
    tr = _deflected_assist_trace(target_also_goal=True)
    out = f10b.reconcile_canonical_events(
        canonical([canonical_event("GOAL", "SHOT", 1000)]), physical([tr])
    )
    assert len(out["events"]) == 1
    assert out["events"][0]["canonical_event_type"] == "ASSIST"
    assert out["metrics"]["goals"] == 0
    assert out["metrics"]["assists"] == 1
    assert out["reconciliation"]["proposals_contradictory"] == 0


def _with_visual_defender_proof(*, narrow_actor=False, active_save=True):
    tr = _deflected_assist_trace(target_also_goal=True)
    scorer = tr["strike_evidence"][1]
    scorer["status"] = "VERIFIED_PHYSICAL_SCORING_CONTACT"
    target_outcome = tr["outcome_evidence"][0]
    intervention = target_outcome["intervention"]
    intervention["player_box"] = (
        {"x": .46, "y": .30, "w": .08, "h": .30}
        if narrow_actor else
        {"x": .43, "y": .42, "w": .20, "h": .15}
    )
    for frame in tr["decoded_frames"]:
        if 1500 <= int(frame["media_ms"]) <= 1800:
            frame["players"][0]["team"] = "target_team"
            frame["players"][0]["team_confidence"] = .94
            frame["players"][0]["box"] = dict(intervention["player_box"])
    target_outcome["goal_geometry_evidence"] = {
        "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
        "reaction_support_evidence": {
            "goal_mouth_defender_ball_contact": {
                "status": "OBSERVED_CONTACT", "confidence": "high", "tracked": True,
            },
            "goal_mouth_defender_response": {
                "status": "ACTIVE_SAVE_ATTEMPT" if active_save else "OTHER",
                "confidence": "high", "tracked": True,
            },
        },
    }
    return tr


def test_fix10b15_controlled_teammate_finish_can_own_deflected_goal():
    proposals = f10b.proposals_from_trace(_with_visual_defender_proof())
    assists = [row for row in proposals if row["kind"] == "ASSIST"]
    assert len(assists) == 1
    assert assists[0]["teammate_shot_ms"] == 2200
    assert assists[0]["reason"] == (
        "TARGET_RELEASE_OPPONENT_DEFLECTION_WITHOUT_CONTROL_TO_TEAMMATE_GOAL"
    )
    evidence = assists[0]["deflection_proof"]["intervention_team_evidence"]
    assert evidence["source"] == "INDEPENDENT_VISUAL_GOAL_MOUTH_DEFENDER_CONTACT"
    assert evidence["association_ambiguous"] is True


def test_fix10b16_visual_contact_without_active_save_attempt_fails_closed():
    proposals = f10b.proposals_from_trace(
        _with_visual_defender_proof(active_save=False)
    )
    assert not any(row["kind"] == "ASSIST" for row in proposals)


def test_fix10b17_visual_defender_cannot_override_clear_narrow_teammate_body():
    proposals = f10b.proposals_from_trace(
        _with_visual_defender_proof(narrow_actor=True)
    )
    assert not any(row["kind"] == "ASSIST" for row in proposals)


def test_fix10b18_earlier_control_touch_cannot_steal_later_players_goal():
    target = strike(1000, "p001", target=True)
    target["status"] = "VERIFIED_PHYSICAL_SCORING_CONTACT"
    scorer = strike(1700, "p007")
    shared_crossing = 2300
    tr = trace(
        [touch(1000, "p001", target=True), touch(1700, "p007")],
        [target, scorer],
        [
            outcome(target, goal=True, crossing_ms=shared_crossing),
            outcome(scorer, goal=True, crossing_ms=shared_crossing),
        ],
    )
    proposals = f10b.proposals_from_trace(tr)
    assert not any(
        row["kind"] == "GOAL" and row["target_track_id"] == "p001"
        for row in proposals
    )


def test_fix10b19_target_control_contact_can_own_goal_without_later_release():
    target = strike(3000, "p001", target=True)
    target["status"] = "VERIFIED_PHYSICAL_SCORING_CONTACT"
    tr = trace(
        [touch(3000, "p001", target=True)],
        [target],
        [outcome(target, goal=True, crossing_ms=3500)],
    )
    proposals = f10b.proposals_from_trace(tr)
    goals = [row for row in proposals if row["kind"] == "GOAL"]
    assert len(goals) == 1
    assert goals[0]["target_contact_kind"] == "SCORING_CONTROL_CONTACT"
    assert goals[0]["reason"] == (
        "TARGET_SCORING_CONTROL_CONTACT_PLUS_VERIFIED_GOAL_PLANE_CROSSING"
    )
    event = f10b.reconcile_canonical_events(canonical([]), physical([tr]))["events"][0]
    assert event["identity_resolution"] == "FIX10A_VERIFIED_GLOBAL_TARGET_SCORING_CONTACT"
    assert event["proof"]["fix10b_physical"]["target_contact_kind"] == (
        "SCORING_CONTROL_CONTACT"
    )
