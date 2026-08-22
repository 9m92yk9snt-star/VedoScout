"""FIX 09C — one canonical event truth for every product surface.

The B.3 resolver is the factual football-event authority. This module adapts
that truth into the existing report schema without re-discovering, re-timing or
re-identifying events. Report timeline, deterministic stats, evidence frames,
proof clips, snapshots and renderer metadata can therefore share the SAME
stable event_id and canonical media time.

No model calls and no event classification happen here.
"""
from __future__ import annotations

from copy import deepcopy

VERSION = 1

# Existing FIX07 vocabulary is intentionally kept for statistical compatibility.
# IMPORTANT: rich micro-actions are NOT automatically equivalent to countable
# legacy stats. A carry is not necessarily a take-on/dribble, and RECEIVE / CONTROL
# are not extra FIRST_TOUCH attempts. Those details remain available through
# football_action_type/details without inflating deterministic match totals.
_STATS_ACTION = {
    "SHOT": "SHOT", "PASS": "PASS", "CROSS": "CROSS", "KEY_PASS": "PASS",
    "DRIBBLE": "DRIBBLE", "TAKE_ON": "DRIBBLE",
    "DUEL": "DUEL", "TACKLE": "TACKLE", "INTERCEPTION": "INTERCEPTION",
    "RECOVERY": "RECOVERY", "FIRST_TOUCH": "FIRST_TOUCH",
    "RUN": "RUN", "OFF_BALL_RUN": "RUN",
}

_TITLE = {
    "GOAL": "Goal", "ASSIST": "Assist", "SHOT": "Shot attempt",
    "KEY_PASS": "Key pass", "PASS": "Pass", "CROSS": "Cross",
    "DRIBBLE": "Dribble", "TAKE_ON": "Take-on", "CARRY": "Carry",
    "FEINT": "Body feint", "TURN": "Turn", "DIRECTION_CHANGE": "Change of direction",
    "ACCELERATION": "Acceleration", "DECELERATION": "Deceleration",
    "FIRST_TOUCH": "First touch", "RECEIVE": "Receive", "CONTROL": "Control",
    "DUEL": "Duel", "TACKLE": "Tackle", "INTERCEPTION": "Interception",
    "RECOVERY": "Recovery", "PRESS": "Press", "RUN": "Run",
    "OFF_BALL_RUN": "Off-ball run", "SPACE_CREATION": "Space creation",
    "SCAN": "Scan", "BODY_ORIENTATION": "Body orientation", "SUPPORT": "Support movement",
}

_PRIORITY = {"GOAL": 0, "ASSIST": 1, "SHOT": 2, "KEY_PASS": 3, "PASS": 4,
             "CROSS": 4, "DRIBBLE": 5, "TAKE_ON": 5, "FIRST_TOUCH": 6}


def _mmss(ms: int) -> str:
    sec = int(round(max(0, int(ms)) / 1000.0))
    mm, ss = divmod(sec, 60)
    return f"{mm:02d}:{ss:02d}"


def _stats_action(football_action: str) -> str:
    return _STATS_ACTION.get(str(football_action or "").upper(), "OTHER")


def _stats_event(event_type: str, stats_action: str) -> str:
    et = str(event_type or "").upper()
    if et in {"GOAL", "ASSIST", "KEY_PASS"}:
        return et
    return stats_action if stats_action != "OTHER" else "OTHER"


def _stats_result(event: dict) -> str:
    et = str(event.get("canonical_event_type") or "").upper()
    out = str(event.get("canonical_outcome") or "UNKNOWN").upper()
    if et == "GOAL" and event.get("causal_verified"):
        return "SCORED"
    if et == "ASSIST" and event.get("causal_verified"):
        return "TEAMMATE_SCORED"
    mapping = {
        "TEAMMATE_GOAL": "TEAMMATE_SCORED", "GOAL": "SCORED",
        "SAVED": "SAVED", "BLOCKED": "BLOCKED", "OFF_TARGET": "OFF_TARGET",
        "COMPLETED": "COMPLETED", "INCOMPLETE": "INCOMPLETE",
        "WON": "WON", "LOST": "LOST", "TURNOVER": "POSSESSION_LOST",
        "TEAMMATE_SHOT": "TEAMMATE_SHOT",
    }
    return mapping.get(out, "UNKNOWN")


def _description(event) -> str:
    details = [str(x).strip() for x in event.get("details") or [] if str(x).strip()]
    if details:
        return "; ".join(details[:4])[:500]
    football = str(event.get("canonical_action_type") or event.get("canonical_event_type") or "action")
    return f"Verified {football.lower()} by the selected player."


def project_event(event: dict) -> dict:
    football_action = str(event.get("canonical_action_type") or "OTHER").upper()
    football_event = str(event.get("canonical_event_type") or football_action).upper()
    stats_action = _stats_action(football_action)
    stats_event = _stats_event(football_event, stats_action)
    result = _stats_result(event)
    ms = int(event.get("canonical_ms") if isinstance(event.get("canonical_ms"), int)
             else event.get("contact_ms") if isinstance(event.get("contact_ms"), int)
             else event.get("start_ms") or 0)
    end_ms = int(event.get("end_ms") if isinstance(event.get("end_ms"), int) else ms)
    causal_visible = bool(event.get("causal_verified"))
    outcome_visible = causal_visible or result not in {"UNKNOWN", "OUTCOME_NOT_VISIBLE"}
    title_key = football_event if football_event in _TITLE else football_action
    return {
        "event_id": event.get("event_id"),
        "timestamp": _mmss(ms),
        "action_type": stats_action.lower(),
        "title": _TITLE.get(title_key, _TITLE.get(football_action, "Match involvement")),
        "description": _description(event),
        "rating": None,
        "outcome": "positive" if football_event in {"GOAL", "ASSIST"} else "neutral",
        "identity_confidence": "high",
        "event_source": "fix09b_canonical",
        "cross_verified": True,
        "actor_spatial_verified": True,
        "actor_spatial_reason": event.get("identity_resolution"),
        "event_start_ms": ms,
        "event_end_ms": max(ms, end_ms),
        "canonical_event_type": stats_event,
        "canonical_action_type": stats_action,
        "canonical_result": result,
        "outcome_visible": outcome_visible,
        "football_event_type": football_event,
        "football_action_type": football_action,
        "football_outcome": event.get("canonical_outcome"),
        "football_details": deepcopy(event.get("details") or []),
        "foot": event.get("foot") or "UNKNOWN",
        "pressure": deepcopy(event.get("pressure") or {}),
        "sequence_id": event.get("sequence_id"),
        "source_sequence_ids": deepcopy(event.get("source_sequence_ids") or []),
        "source_action_ids": deepcopy(event.get("source_action_ids") or []),
        "causal_chain": deepcopy(event.get("causal_chain") or {}),
        "proof_window": {
            "start_ms": (event.get("proof") or {}).get("proof_start_ms"),
            "end_ms": (event.get("proof") or {}).get("proof_end_ms"),
        },
    }


def project_timeline(canonical_bundle: dict | None) -> list[dict]:
    events = [e for e in (canonical_bundle or {}).get("events") or [] if isinstance(e, dict)]
    return [project_event(e) for e in sorted(events, key=lambda e: int(e.get("canonical_ms") or 0))]


def _best_proof_frame(event) -> dict | None:
    proof = event.get("proof") if isinstance(event.get("proof"), dict) else {}
    cg = proof.get("contact_geometry")
    if isinstance(cg, dict) and isinstance(cg.get("media_ms"), int) and isinstance(cg.get("box"), dict):
        return {"media_ms": cg["media_ms"], "box": deepcopy(cg["box"]),
                "visibility": cg.get("visibility") or "VISIBLE", "kind": "CONTACT"}
    keys = [r for r in proof.get("actor_keyframes") or []
            if isinstance(r, dict) and isinstance(r.get("media_ms"), int)
            and isinstance(r.get("box"), dict) and r.get("visibility") != "OCCLUDED"]
    if not keys:
        return None
    pivot = event.get("contact_ms") if isinstance(event.get("contact_ms"), int) else event.get("canonical_ms")
    pivot = int(pivot or keys[0]["media_ms"])
    row = min(keys, key=lambda r: abs(int(r["media_ms"]) - pivot))
    return {"media_ms": int(row["media_ms"]), "box": deepcopy(row["box"]),
            "visibility": row.get("visibility") or "VISIBLE", "kind": "ADJACENT_VISIBLE"}


def build_event_native_evidence(canonical_bundle: dict | None, max_rows=8) -> list[dict]:
    events = [e for e in (canonical_bundle or {}).get("events") or [] if isinstance(e, dict)]
    events.sort(key=lambda e: (_PRIORITY.get(str(e.get("canonical_event_type") or "").upper(), 9),
                               int(e.get("canonical_ms") or 0)))
    rows = []
    for e in events:
        if len(rows) >= max_rows:
            break
        fr = _best_proof_frame(e)
        if fr is None:
            continue
        rows.append({
            "timestamp": _mmss(fr["media_ms"]),
            "comment": _description(e),
            "player_check": "FIX09B canonical event evidence — same GLOBAL_TARGET and event_id.",
            "identity_confidence": "high",
            "event_id": e.get("event_id"),
            "evidence_time_ms": fr["media_ms"],
            "event_native": True,
            "event_track_locked": True,
            "event_track_box": deepcopy(fr["box"]),
            "event_keyframe_kind": fr["kind"],
            "canonical_event_ms": int(e.get("canonical_ms") or fr["media_ms"]),
            "proof_window_start_ms": (e.get("proof") or {}).get("proof_start_ms"),
            "proof_window_end_ms": (e.get("proof") or {}).get("proof_end_ms"),
        })
    return rows


def build_ledger_compat(canonical_bundle: dict | None, coverage_complete=False) -> dict:
    """Compatibility view for existing prompt/report diagnostics only.

    It is NOT a second event authority. Every row is a projection of B.3.
    """
    events = []
    for e in (canonical_bundle or {}).get("events") or []:
        if not isinstance(e, dict):
            continue
        p = project_event(e)
        football_action = str(e.get("canonical_action_type") or "OTHER").upper()
        legacy_action = p["canonical_action_type"]
        events.append({
            "sequence_id": e.get("sequence_id") or e.get("event_id"),
            "start_ms": int(e.get("start_ms") or p["event_start_ms"]),
            "contact_ms": p["event_start_ms"],
            "end_ms": int(e.get("end_ms") or p["event_end_ms"]),
            "action_type": legacy_action,
            "football_action_type": football_action,
            "foot": e.get("foot") or "UNKNOWN",
            "outcome": e.get("canonical_outcome") or "UNKNOWN",
            "canonical_event_type": p["canonical_event_type"],
            "canonical_action_type": p["canonical_action_type"],
            "canonical_result": p["canonical_result"],
            "outcome_visible": p["outcome_visible"],
            "actor_spatial_verified": True,
            "actor_spatial_reason": e.get("identity_resolution"),
            "description": p["description"],
            "event_id": e.get("event_id"),
        })
    return {
        "version": "FIX09C",
        "status": "ok",
        "authority": "FIX09B_CANONICAL_EVENTS",
        "discovery_complete": coverage_complete is True,
        "track_usable": True,
        "candidates_total": int((canonical_bundle or {}).get("metrics", {}).get("observations_total") or 0),
        "candidates_verified": len(events),
        "dropped": deepcopy((canonical_bundle or {}).get("rejected") or []),
        "unresolved": deepcopy((canonical_bundle or {}).get("unresolved") or []),
        "events": events,
    }


def apply_to_report(full: dict, canonical_bundle: dict | None,
                    sequence_analysis: dict | None = None,
                    *, add_event_evidence=True) -> dict:
    """Replace report event surfaces with the one canonical B.3 truth."""
    if not isinstance(full, dict):
        return full
    timeline = project_timeline(canonical_bundle or {})
    full["action_timeline"] = timeline
    full["event_discovery"] = {
        "status": (canonical_bundle or {}).get("status") or "unavailable",
        "event_discovery_complete": bool((sequence_analysis or {}).get("coverage_complete")),
        "track_usable": True,
        "candidates_total": int((canonical_bundle or {}).get("metrics", {}).get("observations_total") or 0),
        "candidates_verified": len(timeline),
        "authority": "FIX09B_CANONICAL_EVENTS",
    }
    full["analysis_authority"] = {
        "version": VERSION,
        "identity": "GLOBAL_TARGET/FIX09B.0",
        "scene_graph": "FIX09B.1",
        "sequence_intelligence": "FIX09B.2",
        "event_resolution": "FIX09B.3",
        "output": "FIX09C",
        "timebase": "canonical_media_ms",
    }
    if add_event_evidence:
        current = [c for c in full.get("video_comments") or [] if isinstance(c, dict)]
        event_ids = {c.get("event_id") for c in current if c.get("event_id")}
        for row in build_event_native_evidence(canonical_bundle):
            if row.get("event_id") not in event_ids:
                current.append(row)
                event_ids.add(row.get("event_id"))
        full["video_comments"] = current
    return full
