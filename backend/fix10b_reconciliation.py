"""FIX10B — proof-gated reconciliation from FIX10A physical evidence.

FIX10A reconstructs physical truth but intentionally has no canonical authority.
FIX10B is the separate deterministic bridge that may strengthen/correct target
canonical events only when a complete physical proof chain exists.

Core invariant: GLOBAL_TARGET is the player being analysed, not the owner of
all events in the surrounding sequence.  A target release followed by a
verified teammate receive -> teammate strike -> verified goal-plane crossing is
an ASSIST for the target; the teammate owns the scoring strike.

This module performs no detection, model calls, database writes or report
mutation.  Missing/ambiguous evidence fails closed and leaves canonical truth
unchanged.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy

VERSION = 1
GLOBAL_TARGET_ID = "GLOBAL_TARGET"
DIRECT_RECEIVE_MAX_MS = 2400
DIRECT_SHOT_MAX_MS = 4200
DIRECT_GOAL_MAX_MS = 5200
CANONICAL_MATCH_MS = 900
TEAM_CONFIDENCE_MIN = 0.70
PASS_ACTIONS = {"PASS", "CROSS", "KEY_PASS"}


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _ms(row, key="media_ms"):
    return int(round(float(row[key]))) if isinstance(row, dict) and _num(row.get(key)) else None


def _verified_release(strike: dict) -> bool:
    return bool(
        isinstance(strike, dict)
        and strike.get("status") == "VERIFIED_PHYSICAL_RELEASE"
        and strike.get("proof_eligible") is True
        and isinstance(strike.get("player_track_id"), str)
        and _num(strike.get("media_ms"))
    )


def _verified_goal(outcome: dict) -> bool:
    if not isinstance(outcome, dict):
        return False
    crossing = outcome.get("goal_plane_crossing") if isinstance(outcome.get("goal_plane_crossing"), dict) else {}
    return bool(
        outcome.get("status") == "ok"
        and outcome.get("physical_outcome") == "GOAL_PLANE_CROSSING"
        and crossing.get("status") == "VERIFIED"
        and _num(crossing.get("crossing_ms"))
    )


def _verified_touch(touch: dict) -> bool:
    return bool(
        isinstance(touch, dict)
        and touch.get("status") == "VERIFIED"
        and touch.get("proof_eligible") is True
        and isinstance(touch.get("player_track_id"), str)
        and _num(touch.get("representative_ms") if _num(touch.get("representative_ms")) else touch.get("media_ms"))
    )


def _touch_ms(touch: dict):
    if not isinstance(touch, dict):
        return None
    value = touch.get("representative_ms") if _num(touch.get("representative_ms")) else touch.get("media_ms")
    return int(round(float(value))) if _num(value) else None


def _team_is_target(touch: dict) -> bool:
    rel = touch.get("team_relation") if isinstance(touch, dict) and isinstance(touch.get("team_relation"), dict) else {}
    conf = rel.get("confidence")
    return bool(
        rel.get("status") == "SUPPORTING"
        and rel.get("team") == "target_team"
        and _num(conf) and float(conf) >= TEAM_CONFIDENCE_MIN
    )


def _outcomes_by_strike(trace: dict) -> dict[str, dict]:
    out = {}
    for row in trace.get("outcome_evidence") or [] if isinstance(trace, dict) else []:
        if isinstance(row, dict) and isinstance(row.get("strike_id"), str):
            out[row["strike_id"]] = row
    return out


def _touches(trace: dict) -> list[dict]:
    graph = trace.get("touch_graph") if isinstance(trace, dict) and isinstance(trace.get("touch_graph"), dict) else {}
    rows = [deepcopy(x) for x in graph.get("touches") or [] if _verified_touch(x)]
    rows.sort(key=lambda x: (_touch_ms(x) or 0, str(x.get("touch_id") or "")))
    return rows


def _strikes(trace: dict) -> list[dict]:
    rows = [deepcopy(x) for x in trace.get("strike_evidence") or [] if _verified_release(x)] if isinstance(trace, dict) else []
    rows.sort(key=lambda x: (_ms(x) or 0, str(x.get("strike_id") or "")))
    return rows


def _first_other_touch_after(touches, *, actor, scene, after_ms, max_ms):
    rows = [
        t for t in touches
        if t.get("scene_id") == scene
        and t.get("player_track_id") != actor
        and _touch_ms(t) is not None
        and int(after_ms) < int(_touch_ms(t)) <= int(after_ms) + int(max_ms)
    ]
    return min(rows, key=lambda t: int(_touch_ms(t)), default=None)


def _intervening_other_touch(touches, *, allowed_actor, scene, start_ms, end_ms) -> bool:
    return any(
        t.get("scene_id") == scene
        and t.get("player_track_id") != allowed_actor
        and _touch_ms(t) is not None
        and int(start_ms) < int(_touch_ms(t)) < int(end_ms)
        for t in touches
    )


def _goal_proof(outcome: dict) -> dict:
    crossing = outcome.get("goal_plane_crossing") if isinstance(outcome, dict) and isinstance(outcome.get("goal_plane_crossing"), dict) else {}
    return {
        "status": crossing.get("status"),
        "crossing_ms": crossing.get("crossing_ms"),
        "reason": crossing.get("reason"),
        "evidence": deepcopy(crossing.get("evidence") or []),
        "visual_audit": deepcopy(crossing.get("visual_audit") or {}),
    }


def _proposal_id(kind: str, scene: str, target_ms: int, scorer_track: str | None = None) -> str:
    raw = f"{kind}|{scene}|{int(target_ms)}|{scorer_track or ''}".encode("utf-8")
    return "fix10b_" + hashlib.sha1(raw).hexdigest()[:16]


def proposals_from_trace(trace: dict | None) -> list[dict]:
    """Derive only scoring proposals with complete physical chains."""
    row = trace if isinstance(trace, dict) else {}
    touches = _touches(row)
    strikes = _strikes(row)
    outcomes = _outcomes_by_strike(row)
    proposals = []

    # Direct target scoring release -> verified whole-ball goal-plane crossing.
    for strike in strikes:
        if strike.get("global_target_id") != GLOBAL_TARGET_ID:
            continue
        outcome = outcomes.get(strike.get("strike_id"))
        if not _verified_goal(outcome):
            continue
        scene = str(strike.get("scene_id") or "scene_unknown")
        contact_ms = int(strike["media_ms"])
        crossing_ms = int((outcome.get("goal_plane_crossing") or {})["crossing_ms"])
        proposals.append({
            "proposal_id": _proposal_id("GOAL", scene, contact_ms, strike.get("player_track_id")),
            "kind": "GOAL",
            "scene_id": scene,
            "target_contact_ms": contact_ms,
            "target_track_id": strike.get("player_track_id"),
            "scorer_track_id": strike.get("player_track_id"),
            "receiver_track_id": None,
            "receiver_ms": None,
            "teammate_shot_ms": None,
            "goal_outcome_ms": crossing_ms,
            "source_trace_id": row.get("trace_id"),
            "source_touch_id": strike.get("touch_id"),
            "source_strike_id": strike.get("strike_id"),
            "goal_proof": _goal_proof(outcome),
            "proof_eligible": True,
            "reason": "TARGET_RELEASE_PLUS_VERIFIED_GOAL_PLANE_CROSSING",
        })

    # Direct assist: target release -> first other verified touch is teammate ->
    # same teammate owns the next scoring release -> verified goal crossing.
    for target in strikes:
        if target.get("global_target_id") != GLOBAL_TARGET_ID:
            continue
        scene = str(target.get("scene_id") or "scene_unknown")
        target_ms = int(target["media_ms"])
        target_track = target.get("player_track_id")
        receiver = _first_other_touch_after(
            touches, actor=target_track, scene=scene, after_ms=target_ms,
            max_ms=DIRECT_RECEIVE_MAX_MS,
        )
        if not isinstance(receiver, dict) or not _team_is_target(receiver):
            continue
        receiver_track = receiver.get("player_track_id")
        receiver_ms = _touch_ms(receiver)
        if not isinstance(receiver_track, str) or receiver_track == target_track or receiver_ms is None:
            continue

        receiver_strikes = [
            s for s in strikes
            if s.get("scene_id") == scene
            and s.get("player_track_id") == receiver_track
            and _ms(s) is not None
            and int(receiver_ms) <= int(_ms(s)) <= target_ms + DIRECT_SHOT_MAX_MS
        ]
        scoring = None
        scoring_outcome = None
        for strike in receiver_strikes:
            shot_ms = int(strike["media_ms"])
            if _intervening_other_touch(
                touches, allowed_actor=receiver_track, scene=scene,
                start_ms=int(receiver_ms), end_ms=shot_ms,
            ):
                continue
            outcome = outcomes.get(strike.get("strike_id"))
            if not _verified_goal(outcome):
                continue
            crossing_ms = int((outcome.get("goal_plane_crossing") or {})["crossing_ms"])
            if crossing_ms > target_ms + DIRECT_GOAL_MAX_MS:
                continue
            scoring, scoring_outcome = strike, outcome
            break
        if scoring is None:
            continue

        shot_ms = int(scoring["media_ms"])
        crossing_ms = int((scoring_outcome.get("goal_plane_crossing") or {})["crossing_ms"])
        proposals.append({
            "proposal_id": _proposal_id("ASSIST", scene, target_ms, receiver_track),
            "kind": "ASSIST",
            "scene_id": scene,
            "target_contact_ms": target_ms,
            "target_track_id": target_track,
            "receiver_track_id": receiver_track,
            "receiver_ms": int(receiver_ms),
            "scorer_track_id": receiver_track,
            "teammate_shot_ms": shot_ms,
            "goal_outcome_ms": crossing_ms,
            "source_trace_id": row.get("trace_id"),
            "source_touch_id": target.get("touch_id"),
            "source_strike_id": scoring.get("strike_id"),
            "goal_proof": _goal_proof(scoring_outcome),
            "receiver_team_evidence": deepcopy(receiver.get("team_relation") or {}),
            "proof_eligible": True,
            "reason": "TARGET_RELEASE_TO_TEAMMATE_RECEIVE_TO_TEAMMATE_GOAL",
        })

    return proposals


def collect_proposals(physical_result: dict | None) -> list[dict]:
    physical = physical_result if isinstance(physical_result, dict) else {}
    rows = []
    for trace in physical.get("traces") or []:
        if isinstance(trace, dict):
            rows.extend(proposals_from_trace(trace))
    # Overlapping FIX10A windows can contain the same real chain. Keep one
    # deterministic proposal per kind/scene/target/scorer within a tight bound.
    deduped = []
    for proposal in sorted(rows, key=lambda p: (p["scene_id"], p["target_contact_ms"], p["kind"])):
        duplicate = next((
            old for old in deduped
            if old["kind"] == proposal["kind"]
            and old["scene_id"] == proposal["scene_id"]
            and old.get("scorer_track_id") == proposal.get("scorer_track_id")
            and abs(int(old["target_contact_ms"]) - int(proposal["target_contact_ms"])) <= 220
        ), None)
        if duplicate is None:
            deduped.append(proposal)
    return deduped


def _event_match(events, proposal):
    scene = proposal.get("scene_id")
    target_ms = int(proposal["target_contact_ms"])
    candidates = [
        e for e in events
        if isinstance(e, dict)
        and e.get("scene_id") == scene
        and _num(e.get("canonical_ms"))
        and abs(int(e["canonical_ms"]) - target_ms) <= CANONICAL_MATCH_MS
    ]
    if proposal.get("kind") == "GOAL":
        preferred = [e for e in candidates if e.get("canonical_action_type") == "SHOT"]
    else:
        preferred = [e for e in candidates if e.get("canonical_action_type") in PASS_ACTIONS]
        # A model may have mislabelled the target's pass as a SHOT/GOAL. The
        # complete physical teammate chain is allowed to correct that ownership
        # error, so fall back to the nearest target event when no pass row exists.
    pool = preferred or candidates
    return min(pool, key=lambda e: abs(int(e["canonical_ms"]) - target_ms), default=None)


def _physical_proof(proposal) -> dict:
    evidence_ms = [
        proposal.get("target_contact_ms"), proposal.get("receiver_ms"),
        proposal.get("teammate_shot_ms"), proposal.get("goal_outcome_ms"),
    ]
    return {
        "source": "FIX10B_PHYSICAL_RECONCILIATION",
        "proposal_id": proposal.get("proposal_id"),
        "source_trace_id": proposal.get("source_trace_id"),
        "source_touch_id": proposal.get("source_touch_id"),
        "source_strike_id": proposal.get("source_strike_id"),
        "evidence_ms": [int(x) for x in evidence_ms if _num(x)],
        "goal_proof": deepcopy(proposal.get("goal_proof") or {}),
        "receiver_team_evidence": deepcopy(proposal.get("receiver_team_evidence") or {}),
        "proof_eligible": proposal.get("proof_eligible") is True,
    }


def _synth_event(proposal) -> dict:
    contact = int(proposal["target_contact_ms"])
    scene = str(proposal.get("scene_id") or "scene_unknown")
    kind = proposal["kind"]
    action_type = "SHOT" if kind == "GOAL" else "PASS"
    chain = {
        "target_contact_ms": contact,
        "receiver_local_track_id": proposal.get("receiver_track_id"),
        "receiver_ms": proposal.get("receiver_ms"),
        "teammate_shot_ms": proposal.get("teammate_shot_ms"),
        "goal_outcome_ms": proposal.get("goal_outcome_ms"),
        "continuous_visible_sequence": True,
    }
    proof = {
        "proof_start_ms": contact,
        "proof_end_ms": int(proposal.get("goal_outcome_ms") or contact),
        "evidence_ms": _physical_proof(proposal)["evidence_ms"],
        "actor_keyframes": [],
        "contact_geometry": None,
        "contact_visibility": "PHYSICALLY_VERIFIED",
        "outcome_ms": proposal.get("goal_outcome_ms"),
        "proof_eligible": True,
        "causal_verified": True,
        "receiver_team_evidence": deepcopy(proposal.get("receiver_team_evidence") or {}),
        "fix10b_physical": _physical_proof(proposal),
    }
    return {
        "event_id": proposal["proposal_id"],
        "global_target_id": GLOBAL_TARGET_ID,
        "scene_id": scene,
        "sequence_id": None,
        "source_sequence_ids": [],
        "source_action_ids": [],
        "start_ms": contact,
        "contact_ms": contact,
        "end_ms": int(proposal.get("goal_outcome_ms") or contact),
        "canonical_ms": contact,
        "canonical_event_type": kind,
        "canonical_action_type": action_type,
        "canonical_outcome": "GOAL" if kind == "GOAL" else "TEAMMATE_GOAL",
        "causal_verified": True,
        "resolution_reason": proposal.get("reason"),
        "actor_local_track_id": proposal.get("target_track_id"),
        "identity_resolution": "FIX10A_VERIFIED_GLOBAL_TARGET_PHYSICAL_RELEASE",
        "foot": "UNKNOWN",
        "pressure": {},
        "details": [],
        "proof": proof,
        "causal_chain": chain,
        "receiver_team_resolution": deepcopy(proposal.get("receiver_team_evidence") or {}),
        "reconciliation_authority": "FIX10B_PHYSICAL_RECONCILIATION",
    }


def _apply_proposal(event: dict, proposal: dict) -> dict:
    out = deepcopy(event)
    before = {
        "canonical_event_type": out.get("canonical_event_type"),
        "canonical_action_type": out.get("canonical_action_type"),
        "canonical_outcome": out.get("canonical_outcome"),
    }
    if proposal["kind"] == "GOAL":
        out["canonical_event_type"] = "GOAL"
        out["canonical_action_type"] = "SHOT"
        out["canonical_outcome"] = "GOAL"
    else:
        out["canonical_event_type"] = "ASSIST"
        if out.get("canonical_action_type") not in PASS_ACTIONS:
            out["canonical_action_type"] = "PASS"
        out["canonical_outcome"] = "TEAMMATE_GOAL"
        out["receiver_team_resolution"] = deepcopy(proposal.get("receiver_team_evidence") or {})
    out["causal_verified"] = True
    out["resolution_reason"] = proposal.get("reason")
    out["actor_local_track_id"] = proposal.get("target_track_id") or out.get("actor_local_track_id")
    out["global_target_id"] = GLOBAL_TARGET_ID
    out["causal_chain"] = {
        "target_contact_ms": proposal.get("target_contact_ms"),
        "receiver_local_track_id": proposal.get("receiver_track_id"),
        "receiver_ms": proposal.get("receiver_ms"),
        "teammate_shot_ms": proposal.get("teammate_shot_ms"),
        "goal_outcome_ms": proposal.get("goal_outcome_ms"),
        "continuous_visible_sequence": True,
    }
    proof = deepcopy(out.get("proof") or {})
    proof["proof_eligible"] = True
    proof["causal_verified"] = True
    proof["outcome_ms"] = proposal.get("goal_outcome_ms")
    proof["fix10b_physical"] = _physical_proof(proposal)
    merged_ms = set(proof.get("evidence_ms") or [])
    merged_ms.update(_physical_proof(proposal)["evidence_ms"])
    proof["evidence_ms"] = sorted(int(x) for x in merged_ms if _num(x))[:60]
    if proposal["kind"] == "ASSIST":
        proof["receiver_team_evidence"] = deepcopy(proposal.get("receiver_team_evidence") or {})
    out["proof"] = proof
    out["reconciliation_authority"] = "FIX10B_PHYSICAL_RECONCILIATION"
    out["fix10b_previous_classification"] = before
    return out


def _dedupe_events(events):
    # FIX10B only dedupes target scoring classifications at the same physical
    # contact. Non-scoring/micro events remain untouched.
    out = []
    for event in sorted(events, key=lambda e: (str(e.get("scene_id") or ""), int(e.get("canonical_ms") or 0), str(e.get("event_id") or ""))):
        duplicate = next((
            old for old in out
            if event.get("canonical_event_type") in {"GOAL", "ASSIST"}
            and old.get("canonical_event_type") == event.get("canonical_event_type")
            and old.get("scene_id") == event.get("scene_id")
            and _num(old.get("canonical_ms")) and _num(event.get("canonical_ms"))
            and abs(int(old["canonical_ms"]) - int(event["canonical_ms"])) <= 220
        ), None)
        if duplicate is None:
            out.append(event)
    return out


def _recount(bundle: dict) -> dict:
    events = bundle.get("events") or []
    counts = {}
    for event in events:
        if isinstance(event, dict):
            kind = str(event.get("canonical_event_type") or "OTHER")
            counts[kind] = counts.get(kind, 0) + 1
    metrics = deepcopy(bundle.get("metrics") or {})
    metrics.update({
        "events_accepted": len(events),
        "goals": counts.get("GOAL", 0),
        "assists": counts.get("ASSIST", 0),
        "shots": counts.get("SHOT", 0) + counts.get("GOAL", 0),
    })
    bundle["counts"] = counts
    bundle["metrics"] = metrics
    bundle["status"] = "ok" if events else bundle.get("status", "empty")
    return bundle


def reconcile_canonical_events(canonical_bundle: dict | None,
                               physical_result: dict | None) -> dict:
    """Return a copied FIX10B canonical bundle and an auditable change set."""
    canonical = deepcopy(canonical_bundle) if isinstance(canonical_bundle, dict) else {
        "version": 1, "status": "empty", "global_target_id": GLOBAL_TARGET_ID,
        "timebase": "canonical_media_ms", "events": [], "unresolved": [],
        "rejected": [], "counts": {}, "metrics": {},
    }
    events = [deepcopy(e) for e in canonical.get("events") or [] if isinstance(e, dict)]
    proposals = collect_proposals(physical_result)
    changes = []

    # If the same target contact has both a GOAL and an ASSIST proposal, the
    # chain is contradictory and neither gets authority.
    contradictory = set()
    for i, left in enumerate(proposals):
        for right in proposals[i + 1:]:
            if (left["scene_id"] == right["scene_id"]
                    and abs(int(left["target_contact_ms"]) - int(right["target_contact_ms"])) <= 220
                    and left["kind"] != right["kind"]):
                contradictory.update({left["proposal_id"], right["proposal_id"]})

    applied = []
    for proposal in proposals:
        if proposal["proposal_id"] in contradictory or proposal.get("proof_eligible") is not True:
            continue
        match = _event_match(events, proposal)
        if match is None:
            new_event = _synth_event(proposal)
            events.append(new_event)
            changes.append({
                "proposal_id": proposal["proposal_id"], "change": "ADDED_PHYSICAL_EVENT",
                "event_id": new_event.get("event_id"), "to": proposal["kind"],
            })
        else:
            index = events.index(match)
            before = deepcopy(match)
            events[index] = _apply_proposal(match, proposal)
            changes.append({
                "proposal_id": proposal["proposal_id"], "change": "RECLASSIFIED_CANONICAL_EVENT",
                "event_id": match.get("event_id"),
                "from": before.get("canonical_event_type"), "to": proposal["kind"],
            })
        applied.append(proposal["proposal_id"])

    canonical["events"] = _dedupe_events(events)
    canonical["version"] = f"FIX10B.{VERSION}"
    canonical["global_target_id"] = GLOBAL_TARGET_ID
    canonical["timebase"] = "canonical_media_ms"
    canonical["reconciliation"] = {
        "version": VERSION,
        "authority": "FIX10B_PHYSICAL_RECONCILIATION",
        "proposals_total": len(proposals),
        "proposals_applied": len(applied),
        "proposals_contradictory": len(contradictory),
        "applied_proposal_ids": applied,
        "changes": changes,
        "physical_status": (physical_result or {}).get("status") if isinstance(physical_result, dict) else None,
    }
    return _recount(canonical)
