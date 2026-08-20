"""event_ledger.py — FIX 08 PLAYER EVENT LEDGER + EVENT-NATIVE EVIDENCE.

Deterministic code around ONE dedicated event-discovery video pass:

    VIDEO → FIX00A taps → FIX04 track → FIX03 media time
          → FIX08 discovery (ONE bounded model call, made by the server)
          → FIX08 spatial actor validation (deterministic, here)
          → canonical player event ledger → existing cross verifier
          → FIX01 ids → FIX07 verified stats → FIX08 event-native evidence
          → FIX02 proof authority → report.

This module NEVER calls a model, the network, or the verifier. It only
validates/classifies the discovery response against accepted FIX04 geometry
and canonical FIX03 milliseconds, and derives event-native evidence and
snapshot moments from already-verified events. Fail closed everywhere:
no spatial match → no target-player event; no exact verified frame → no
snapshot moment.
"""

from __future__ import annotations

import verified_stats as vstats

EVENT_LEDGER_VERSION = 1
BUCKET_MS = 5000

ACTION_TYPES = {"SHOT", "PASS", "CROSS", "DRIBBLE", "DUEL", "TACKLE", "INTERCEPTION",
                "RECOVERY", "FIRST_TOUCH", "RUN", "DEFENSIVE_ACTION", "OTHER"}
OUTCOMES = {"SCORED", "TEAMMATE_SCORED", "TEAMMATE_SHOT", "SAVED", "BLOCKED",
            "OFF_TARGET", "COMPLETED", "INCOMPLETE", "WON", "LOST", "UNKNOWN"}
FEET = {"LEFT", "RIGHT", "UNKNOWN"}

_MIN_TRACK_POINTS = 10          # same usable-track threshold as cross-verification
_CONTACT_MAX_GAP_S = 1.0        # exact contact-time bbox resolve window
_IOU_MATCH = 0.15
_CENTER_MATCH_FACTOR = 0.75

_SAFE_TITLE = {"SHOT": "Shot attempt", "PASS": "Pass", "CROSS": "Cross",
               "DRIBBLE": "Dribble", "DUEL": "Duel", "TACKLE": "Tackle",
               "INTERCEPTION": "Interception", "RECOVERY": "Recovery",
               "FIRST_TOUCH": "First touch", "RUN": "Run",
               "DEFENSIVE_ACTION": "Defensive action", "OTHER": "Involvement",
               "GOAL": "Goal", "ASSIST": "Assist", "KEY_PASS": "Key pass"}


def _mmss(ms: int) -> str:
    s = int(round(max(0, int(ms)) / 1000.0))
    mm, ss = divmod(s, 60)
    return f"{mm:02d}:{ss:02d}"


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


# ---------------------------------------------------------------- discovery

DISCOVERY_PROMPT_HEADER = """You are a football EVENT DISCOVERY system. The attached video shows ONE specific youth player — the "tapped player". The reference crops attached FIRST show that exact player; the ground-truth tap positions below are never wrong.

YOUR ONLY JOB: enumerate ALL clearly observable football involvements of the TAPPED PLAYER across the ENTIRE video. This is EVENT DISCOVERY ONLY — no scores, no summaries, no development advice, no ratings, no prose report.

RULES:
- List EVERY clearly observable involvement — touches, passes, crosses, shots, dribbles, duels, tackles, interceptions, recoveries, runs, defensive actions. Do NOT cap the list. A busy player can produce 20-40+ events.
- ONLY the tapped player. If a different player performs an action — even right next to the tapped player — do NOT list it.
- For EVERY event return actor_box: the normalized bounding box (x, y, w, h, all 0..1, x/y = top-left corner) of the player PERFORMING the action at the contact moment. This must be the box of the actual actor you see — never a guess.
- contact_ms is the physical action-contact moment (kick contact for PASS/CROSS/SHOT, decisive touch for DRIBBLE, possession contact for TACKLE/RECOVERY). All times are canonical media milliseconds from video start. Never invent a timestamp.
- outcome_visible=true ONLY when the outcome itself is visible on screen.
- GOAL outcomes: outcome "SCORED" ONLY when the ball visibly enters the goal / crosses the line on screen. NEVER infer from celebration, scoreboard, restart or body language.
- scoring_chain: fill it for any PASS/CROSS that may lead to a teammate shot or goal — pass_contact_ms, teammate_receive_ms, teammate_shot_ms, goal_outcome_ms (null when not visible) and continuous_causal_sequence=true ONLY when the whole chain is one continuous visible sequence with no cut.

COVERAGE CONTRACT (mandatory): the video is divided into fixed 5-second buckets listed below. Return one coverage row for EVERY bucket with EXACTLY those start_ms/end_ms values, whether the tapped player was visible in it, and how many events you found in it. Missing buckets invalidate the scan.
{bucket_block}

Return ONLY valid JSON, no markdown:
{{"events": [{{"sequence_id": "<short id>", "start_ms": <int>, "contact_ms": <int or null>, "end_ms": <int>, "action_type": "SHOT" | "PASS" | "CROSS" | "DRIBBLE" | "DUEL" | "TACKLE" | "INTERCEPTION" | "RECOVERY" | "FIRST_TOUCH" | "RUN" | "DEFENSIVE_ACTION" | "OTHER", "foot": "LEFT" | "RIGHT" | "UNKNOWN", "actor_box": {{"x": <0..1>, "y": <0..1>, "w": <0..1>, "h": <0..1>}}, "outcome": "SCORED" | "TEAMMATE_SCORED" | "TEAMMATE_SHOT" | "SAVED" | "BLOCKED" | "OFF_TARGET" | "COMPLETED" | "INCOMPLETE" | "WON" | "LOST" | "UNKNOWN", "outcome_visible": true | false, "scoring_chain": {{"pass_contact_ms": <int|null>, "teammate_receive_ms": <int|null>, "teammate_shot_ms": <int|null>, "goal_outcome_ms": <int|null>, "continuous_causal_sequence": true | false}} | null, "description": "<short factual action description>"}}],
 "coverage": [{{"start_ms": <int>, "end_ms": <int>, "target_seen": true | false, "events_found": <int>}}]}}
"""


def build_coverage_buckets(duration_s) -> list[tuple[int, int]]:
    try:
        dur_ms = int(round(max(0.0, float(duration_s)) * 1000))
    except (TypeError, ValueError):
        return []
    buckets = []
    start = 0
    while start < dur_ms:
        buckets.append((start, min(start + BUCKET_MS, dur_ms)))
        start += BUCKET_MS
    return buckets


def build_discovery_prompt(duration_s, player_details: dict | None = None) -> str:
    buckets = build_coverage_buckets(duration_s)
    if buckets:
        rows = "\n".join(f"- bucket {i}: start_ms={b[0]}, end_ms={b[1]}"
                         for i, b in enumerate(buckets))
        block = (f"Video duration: {float(duration_s):.2f}s → {len(buckets)} buckets "
                 f"of {BUCKET_MS} ms:\n{rows}")
    else:
        block = "Video duration unknown — return coverage as an empty list."
    prompt = DISCOVERY_PROMPT_HEADER.format(bucket_block=block)
    pd = player_details or {}
    if pd:
        prompt += (f"\nTAPPED PLAYER DETAILS: name={pd.get('player_name') or 'unknown'}, "
                   f"age={pd.get('age') or 'youth'}, position={pd.get('position') or 'outfield'}.")
    return prompt


def validate_coverage(coverage, buckets: list[tuple[int, int]]) -> bool:
    """PART 2 — every expected 5s bucket must have a well-formed coverage row.
    Anything missing/malformed → the ledger is NOT exhaustive."""
    if not buckets or not isinstance(coverage, list):
        return False
    rows = {}
    for r in coverage:
        if not isinstance(r, dict):
            return False
        if not (_is_int(r.get("start_ms")) and _is_int(r.get("end_ms"))):
            return False
        if not isinstance(r.get("target_seen"), bool):
            return False
        if not _is_int(r.get("events_found")) or r["events_found"] < 0:
            return False
        rows[(r["start_ms"], r["end_ms"])] = r
    return all(b in rows for b in buckets)


# ------------------------------------------------ spatial actor validation

def _valid_box(b) -> bool:
    if not isinstance(b, dict):
        return False
    try:
        x, y, w, h = float(b["x"]), float(b["y"]), float(b["w"]), float(b["h"])
    except (KeyError, TypeError, ValueError):
        return False
    return 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and 0.0 < w <= 1.0 and 0.0 < h <= 1.0


def resolve_target_box(track, contact_ms: int, max_gap_s: float = _CONTACT_MAX_GAP_S):
    """FIX04 accepted target bbox at the EXACT contact time (canonical ms).
    Returns (point | None, reason). Never widens to ±8 s."""
    pts = [p for p in ((track or {}).get("points") or [])
           if isinstance(p, dict) and isinstance(p.get("t"), (int, float))]
    if len(pts) < _MIN_TRACK_POINTS:
        return None, "NO_TARGET_TRACK"
    sec = contact_ms / 1000.0
    best = None
    for p in pts:
        d = abs(float(p["t"]) - sec)
        if d <= max_gap_s and (best is None or d < abs(float(best["t"]) - sec)):
            best = p
    if best is None:
        return None, "TRACK_GAP"
    if not all(isinstance(best.get(k), (int, float)) for k in ("x", "y", "w", "h")):
        return None, "TRACK_GAP"
    return best, "OK"


def boxes_match(a: dict, b: dict) -> bool:
    """Deterministic same-actor geometry test in the shared normalized
    coordinate system (x/y top-left, 0..1): IoU or body-scaled center match."""
    ax, ay, aw, ah = float(a["x"]), float(a["y"]), float(a["w"]), float(a["h"])
    bx, by, bw, bh = float(b["x"]), float(b["y"]), float(b["w"]), float(b["h"])
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    if union > 0 and inter / union >= _IOU_MATCH:
        return True
    acx, acy = ax + aw / 2.0, ay + ah / 2.0
    bcx, bcy = bx + bw / 2.0, by + bh / 2.0
    return (abs(acx - bcx) <= _CENTER_MATCH_FACTOR * max(aw, bw)
            and abs(acy - bcy) <= _CENTER_MATCH_FACTOR * max(ah, bh))


def validate_actor(candidate: dict, track) -> tuple[bool, str, int | None]:
    """PART 4/5 — exact contact-time spatial actor gate. ±8 s presence is
    NEVER actor authority. Returns (actor_spatial_verified, reason, contact_ms)."""
    contact = candidate.get("contact_ms")
    if not _is_int(contact):
        contact = candidate.get("start_ms")
    if not _is_int(contact) or contact < 0:
        return False, "INVALID_TIMESTAMP", None
    box = candidate.get("actor_box")
    if not _valid_box(box):
        return False, "INVALID_ACTOR_BOX", contact
    target, why = resolve_target_box(track, contact)
    if target is None:
        return False, why, contact
    if boxes_match(box, target):
        return True, "ACTOR_MATCH", contact
    return False, "ACTOR_MISMATCH", contact


# --------------------------------------------------- canonical classification

def classify_candidate(c: dict):
    """PART 6/7 — deterministic canonical classification of a spatially
    verified candidate. GOAL and ASSIST chains are enforced here AND again by
    verified_stats.normalize_canonical (single shared hard gate)."""
    at = str(c.get("action_type") or "").strip().upper()
    out = str(c.get("outcome") or "").strip().upper()
    vis = c.get("outcome_visible") is True
    sc = c.get("scoring_chain") if isinstance(c.get("scoring_chain"), dict) else {}
    chain_ok = (sc.get("continuous_causal_sequence") is True
                and _is_int(sc.get("teammate_shot_ms")))
    goal_seen = _is_int(sc.get("goal_outcome_ms"))
    et, res = at, out or "UNKNOWN"
    if at == "SHOT":
        if out == "SCORED" and vis:
            et, res = "GOAL", "SCORED"
        elif not vis:
            res = "OUTCOME_NOT_VISIBLE"
    elif at in ("PASS", "CROSS"):
        if out == "TEAMMATE_SCORED" and vis and chain_ok and goal_seen:
            et, res = "ASSIST", "TEAMMATE_SCORED"
        elif vis and chain_ok and out in ("TEAMMATE_SCORED", "TEAMMATE_SHOT"):
            et, res = "KEY_PASS", "TEAMMATE_SHOT"
        elif out in ("TEAMMATE_SCORED", "TEAMMATE_SHOT"):
            res = "COMPLETED" if vis else "OUTCOME_NOT_VISIBLE"
        elif not vis:
            res = "OUTCOME_NOT_VISIBLE"
    elif at == "DRIBBLE":
        res = {"COMPLETED": "SUCCESS", "WON": "SUCCESS",
               "INCOMPLETE": "FAILED", "LOST": "FAILED"}.get(out, "UNKNOWN")
    elif at in ("INTERCEPTION", "RECOVERY"):
        res = "SUCCESS" if out in ("WON", "COMPLETED") else \
            ("FAILED" if out in ("LOST", "INCOMPLETE") else "UNKNOWN")
    return vstats.normalize_canonical(et, at, res, vis)


# ------------------------------------------------------------------- ledger

def build_ledger(discovery, track, duration_s) -> dict:
    """Deterministic target-player event ledger from the ONE discovery pass.
    Only candidates that pass the exact contact-time spatial actor gate enter.
    Never truncated to a fixed count."""
    ledger = {
        "version": EVENT_LEDGER_VERSION,
        "status": "invalid",
        "discovery_complete": False,
        "track_usable": False,
        "candidates_total": 0,
        "candidates_verified": 0,
        "dropped": [],
        "events": [],
    }
    pts = [p for p in ((track or {}).get("points") or [])
           if isinstance(p, dict) and isinstance(p.get("t"), (int, float))]
    ledger["track_usable"] = len(pts) >= _MIN_TRACK_POINTS
    if not isinstance(discovery, dict):
        return ledger
    ledger["discovery_complete"] = validate_coverage(
        discovery.get("coverage"), build_coverage_buckets(duration_s))
    cands = discovery.get("events")
    if not isinstance(cands, list):
        return ledger
    ledger["status"] = "ok"
    seen = set()
    events = []
    for i, c in enumerate(cands):
        if not isinstance(c, dict):
            ledger["dropped"].append({"sequence_id": None, "reason": "MALFORMED"})
            continue
        ledger["candidates_total"] += 1
        sid = str(c.get("sequence_id") or f"seq_{i}")

        def _drop(reason):
            ledger["dropped"].append({"sequence_id": sid, "reason": reason})

        at = str(c.get("action_type") or "").strip().upper()
        if at not in ACTION_TYPES:
            _drop("INVALID_ACTION_TYPE")
            continue
        out = str(c.get("outcome") or "UNKNOWN").strip().upper()
        if out not in OUTCOMES:
            _drop("INVALID_OUTCOME")
            continue
        ok, reason, contact = validate_actor(c, track)
        if not ok:
            _drop(reason)
            continue
        key = (contact, at)
        if key in seen:
            _drop("DUPLICATE")
            continue
        seen.add(key)
        et, cat, res, vis = classify_candidate(c)
        start = c.get("start_ms") if _is_int(c.get("start_ms")) else contact
        end = c.get("end_ms") if _is_int(c.get("end_ms")) else contact
        foot = str(c.get("foot") or "UNKNOWN").strip().upper()
        events.append({
            "sequence_id": sid,
            "start_ms": start,
            "contact_ms": contact,
            "end_ms": max(end, contact),
            "action_type": at,
            "foot": foot if foot in FEET else "UNKNOWN",
            "outcome": out,
            "canonical_event_type": et,
            "canonical_action_type": cat,
            "canonical_result": res,
            "outcome_visible": vis,
            "actor_spatial_verified": True,
            "actor_spatial_reason": "ACTOR_MATCH",
            "description": str(c.get("description") or "").strip()[:300],
        })
    events.sort(key=lambda e: (e["contact_ms"], e["action_type"]))
    ledger["events"] = events
    ledger["candidates_verified"] = len(events)
    return ledger


def project_to_timeline(ledger) -> list[dict]:
    """PART 8 — project verified ledger candidates into the existing
    action_timeline claim shape so the EXISTING cross verifier verifies them.
    No truncation, event time = real contact moment."""
    rows = []
    for e in ((ledger or {}).get("events") or []):
        rows.append({
            "timestamp": _mmss(e["contact_ms"]),
            "action_type": e["action_type"].lower(),
            "title": _SAFE_TITLE.get(e["action_type"], "Involvement"),
            "description": e["description"]
            or f"Observed {e['action_type'].lower()} by the tapped player.",
            "rating": None,
            "outcome": "neutral",
            "identity_confidence": "high",
            "event_source": "fix08_ledger",
            "ledger_sequence_id": e["sequence_id"],
            "ledger_contact_ms": e["contact_ms"],
        })
    return rows


def discovery_summary(ledger) -> dict:
    """Compact report-facing discovery state. Never silently exhaustive."""
    if not isinstance(ledger, dict):
        return {"status": "unavailable", "event_discovery_complete": False}
    return {
        "status": ledger.get("status"),
        "event_discovery_complete": ledger.get("discovery_complete") is True,
        "track_usable": ledger.get("track_usable") is True,
        "candidates_total": ledger.get("candidates_total"),
        "candidates_verified": ledger.get("candidates_verified"),
    }


def ledger_prompt_block(ledger) -> str:
    """PART 9 — compact ledger context for the full-report prompt: the model
    writes ABOUT these observed events; it never invents new ones."""
    evs = ((ledger or {}).get("events") or [])
    if not evs:
        return ""
    lines = []
    for e in evs[:80]:
        desc = (e.get("description") or "")[:120]
        lines.append(f"- {_mmss(e['contact_ms'])} — {e['action_type']}: {desc}")
    return (
        "\n\n📋 OBSERVED EVENT LEDGER (machine-validated: each entry passed exact "
        "contact-time spatial verification against the tapped player's own track):\n"
        + "\n".join(lines)
        + "\nTHE EVENT LEDGER IS THE OBSERVED EVENT SOURCE. Do NOT invent new goals, "
        "new assists, new event timestamps or new target-player actions. Any football "
        "example or timestamp you use in prose MUST come from this ledger."
    )


# ----------------------------------------------- event-native evidence (P12)

_PRIORITY = {"GOAL": 0, "ASSIST": 1, "KEY_PASS": 2, "SHOT": 3}


def create_event_native_evidence(full: dict, max_rows: int = 6) -> dict:
    """PART 12 — deterministic evidence rows EXACTLY bound to important
    VERIFIED events that have no exact evidence row yet. Zero model calls;
    the existing frame/identity/proof machinery consumes these rows."""
    if not isinstance(full, dict):
        return full
    events = [e for e in (full.get("action_timeline") or [])
              if isinstance(e, dict) and e.get("cross_verified") is True
              and e.get("event_id") and _is_int(e.get("event_start_ms"))]
    if not events:
        return full
    comments = full.get("video_comments")
    if not isinstance(comments, list):
        comments = []
        full["video_comments"] = comments
    bound = {c.get("event_id") for c in comments
             if isinstance(c, dict) and c.get("event_id")}

    def _prio(e):
        et = str(e.get("canonical_event_type") or "").upper()
        r = e.get("rating")
        return (_PRIORITY.get(et, 4),
                -(float(r) if isinstance(r, (int, float)) else 0.0),
                e.get("event_start_ms"))

    created = 0
    for e in sorted(events, key=_prio):
        if created >= max_rows:
            break
        if e["event_id"] in bound:
            continue
        desc = str(e.get("description") or e.get("title")
                   or "Verified match involvement").strip()
        comments.append({
            "timestamp": e.get("timestamp"),
            "comment": desc,
            "player_check": "FIX08 event-native evidence — created deterministically "
                            "from the verified event.",
            "identity_confidence": "high",
            "event_id": e["event_id"],
            "evidence_time_ms": e["event_start_ms"],
            "event_native": True,
        })
        bound.add(e["event_id"])
        created += 1
    return full


# ------------------------------------------------- snapshot moments (P14)

def build_snapshot_moments(full: dict, max_moments: int = 4):
    """PART 14 — snapshot moments ONLY from verified events with a usable
    EXACT proof frame (FIX02 compute_proof_frame_verified semantics already
    stamped on the evidence row). 2 real moments beat 4 fabricated ones."""
    if not isinstance(full, dict):
        return None
    events_by_id = {e.get("event_id"): e for e in (full.get("action_timeline") or [])
                    if isinstance(e, dict) and e.get("event_id")}
    usable = []
    for c in (full.get("video_comments") or []):
        if not isinstance(c, dict):
            continue
        e = events_by_id.get(c.get("event_id"))
        if not e or e.get("cross_verified") is not True:
            continue
        if c.get("proof_frame_verified") is not True or not c.get("frame_url"):
            continue  # fail closed — no exact verified frame, no snapshot card
        usable.append((e, c))

    def _prio(pair):
        e, _c = pair
        et = str(e.get("canonical_event_type") or "").upper()
        r = e.get("rating")
        return (_PRIORITY.get(et, 4),
                -(float(r) if isinstance(r, (int, float)) else 0.0),
                e.get("event_start_ms") or 0)

    seen = set()
    moments = []
    for e, c in sorted(usable, key=_prio):
        if e["event_id"] in seen:
            continue
        seen.add(e["event_id"])
        et = str(e.get("canonical_event_type") or "").upper()
        moments.append({
            "key": f"moment{len(moments) + 1}",
            "title": str(e.get("title") or _SAFE_TITLE.get(et, "Key moment")),
            "desc": str(e.get("description") or "").strip()[:200],
            "timestamp": e.get("timestamp"),
            "frame_url": c.get("frame_url"),
            "event_id": e.get("event_id"),
            "evidence_id": c.get("evidence_id"),
            "annot": "circle",
            "event_native": bool(c.get("event_native")),
            "proof_verified": True,
        })
        if len(moments) >= max_moments:
            break
    full["snapshot_moments"] = moments
    full["snapshot_moments_authority"] = True
    return moments
