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
_EXACT_POINT_TOL_S = 0.010      # a track point this close IS the contact point
# C07/CORRECTION 03 — FIX04 samples at 12.5 Hz (~0.08 s). Authoritative
# geometry may only be interpolated across ~3 normal sample intervals; a
# longer missing-track stretch (duel/overlap/occlusion/cut) is uncertainty
# and MUST fail closed as TRACK_GAP — never reconstructed.
_INTERP_MAX_GAP_S = 0.25
# C08 — close-duel hardened same-actor geometry (ALL conditions required)
_MATCH_IOU_MIN = 0.30
_MATCH_CENTER_FACTOR = 0.45
_MATCH_SIZE_RATIO_MIN = 0.55
_MATCH_SIZE_RATIO_MAX = 1.8

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


def bucket_index_for(contact_ms, buckets: list[tuple[int, int]], duration_ms: int):
    """Deterministic [start, end) bucket assignment; the exact video-duration
    contact belongs ONLY to the final bucket. None when unassignable."""
    if not buckets or not _is_int(contact_ms) or contact_ms < 0 or contact_ms > duration_ms:
        return None
    if contact_ms == duration_ms:
        return len(buckets) - 1
    idx = contact_ms // BUCKET_MS
    return idx if idx < len(buckets) else None


def validate_coverage_contract(discovery, duration_s) -> dict:
    """FIX09 P1–P3 — STRICT coverage-contract validation with diagnostics.
    Proves the contract is structurally complete and internally consistent —
    it can NEVER prove the model saw every real-world action, so it is never
    called 'exhaustive'. Requires exact unique bucket-set equality, reconciled
    events_found against the RAW discovery rows (actor authority is separate),
    and target_seen consistency."""
    buckets = build_coverage_buckets(duration_s)
    dur_ms = buckets[-1][1] if buckets else 0
    out = {"complete": False,
           "expected_bucket_count": len(buckets),
           "received_bucket_count": 0,
           "missing_buckets": [], "duplicate_buckets": [], "unexpected_buckets": [],
           "malformed_rows": 0, "events_found_mismatches": [],
           "unbucketable_events": 0, "coverage_contradictions": []}
    coverage = discovery.get("coverage") if isinstance(discovery, dict) else None
    if not buckets or not isinstance(coverage, list):
        return out
    ok = True
    keys = []          # ALL well-formed keys — duplicates never disappear
    rows = {}
    for r in coverage:
        if not (isinstance(r, dict) and _is_int(r.get("start_ms")) and _is_int(r.get("end_ms"))
                and isinstance(r.get("target_seen"), bool)
                and _is_int(r.get("events_found")) and r["events_found"] >= 0):
            out["malformed_rows"] += 1
            ok = False
            continue
        key = (r["start_ms"], r["end_ms"])
        keys.append(key)
        rows.setdefault(key, r)
    out["received_bucket_count"] = len(keys) + out["malformed_rows"]
    seen_counts = {}
    for k in keys:
        seen_counts[k] = seen_counts.get(k, 0) + 1
    expected = set(buckets)
    out["duplicate_buckets"] = sorted([list(k) for k, c in seen_counts.items() if c > 1])
    out["unexpected_buckets"] = sorted([list(k) for k in seen_counts if k not in expected])
    out["missing_buckets"] = sorted([list(b) for b in buckets if b not in seen_counts])
    if out["duplicate_buckets"] or out["unexpected_buckets"] or out["missing_buckets"]:
        ok = False
    for k, r in rows.items():
        if r["events_found"] > 0 and r["target_seen"] is not True:
            out["coverage_contradictions"].append(list(k))
            ok = False
    # P2 — reconcile events_found against the RAW discovery event rows using
    # canonical contact_ms (NOT the actor-verified ledger: wrong-player
    # rejections must never fake a coverage mismatch).
    per_bucket = {b: 0 for b in buckets}
    raw = discovery.get("events")
    if not isinstance(raw, list):
        ok = False
    else:
        for ev in raw:
            c = None
            if isinstance(ev, dict):
                c = ev.get("contact_ms")
                if not _is_int(c):
                    c = ev.get("start_ms")
            idx = bucket_index_for(c, buckets, dur_ms)
            if idx is None:
                out["unbucketable_events"] += 1
                ok = False
                continue
            per_bucket[buckets[idx]] += 1
        for b in buckets:
            r = rows.get(b)
            if r is not None and seen_counts.get(b) == 1 \
                    and r["events_found"] != per_bucket[b]:
                out["events_found_mismatches"].append(
                    {"bucket": list(b), "declared": r["events_found"],
                     "actual": per_bucket[b]})
                ok = False
    out["complete"] = ok
    return out


def _finalize_coverage_state(ledger: dict) -> dict:
    """FIX09 P4 — precise coverage-contract semantics, never 'proven
    exhaustive': COMPLETE / PARTIAL / UNAVAILABLE."""
    if ledger.get("status") != "ok" or not ledger.get("track_usable"):
        ledger["coverage_state"] = "UNAVAILABLE"
    elif ledger.get("coverage_contract_complete") is True:
        ledger["coverage_state"] = "COMPLETE"
    else:
        ledger["coverage_state"] = "PARTIAL"
    ledger["discovery_complete"] = ledger["coverage_state"] == "COMPLETE"
    return ledger


# ------------------------------------------------ spatial actor validation

def _valid_box(b) -> bool:
    if not isinstance(b, dict):
        return False
    try:
        x, y, w, h = float(b["x"]), float(b["y"]), float(b["w"]), float(b["h"])
    except (KeyError, TypeError, ValueError):
        return False
    return 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and 0.0 < w <= 1.0 and 0.0 < h <= 1.0


def _geom_ok(p) -> bool:
    return isinstance(p, dict) and all(
        isinstance(p.get(k), (int, float)) for k in ("x", "y", "w", "h"))


def resolve_target_box(track, contact_ms: int, max_gap_s: float = _INTERP_MAX_GAP_S):
    """C07 — FIX04 accepted target bbox AT the EXACT contact time (canonical
    ms). Exact point → used as-is; otherwise linear x/y/w/h interpolation
    between the surrounding track points, ONLY when the surrounding interval
    is a bounded normal tracking gap. Large gap / no surrounding pair →
    TRACK_GAP. Never widened to ±8 s, never presentation MM:SS.
    Returns (bbox dict | None, reason)."""
    pts = [p for p in ((track or {}).get("points") or [])
           if isinstance(p, dict) and isinstance(p.get("t"), (int, float))]
    if len(pts) < _MIN_TRACK_POINTS:
        return None, "NO_TARGET_TRACK"
    pts.sort(key=lambda p: float(p["t"]))
    sec = contact_ms / 1000.0
    before, after = None, None
    for p in pts:
        t = float(p["t"])
        if abs(t - sec) <= _EXACT_POINT_TOL_S:
            if not _geom_ok(p):
                return None, "TRACK_GAP"
            return {"x": float(p["x"]), "y": float(p["y"]),
                    "w": float(p["w"]), "h": float(p["h"]), "t": t}, "OK"
        if t < sec:
            before = p
        elif after is None:
            after = p
            break
    if before is None or after is None:
        return None, "TRACK_GAP"  # contact outside the tracked interval
    t0, t1 = float(before["t"]), float(after["t"])
    if (t1 - t0) > max_gap_s + 1e-9:  # tiny epsilon: float safety only
        return None, "TRACK_GAP"  # uncertainty gap — no false geometry
    if not (_geom_ok(before) and _geom_ok(after)):
        return None, "TRACK_GAP"
    f = (sec - t0) / (t1 - t0) if t1 > t0 else 0.0
    lerp = lambda a, b: float(a) + (float(b) - float(a)) * f  # noqa: E731
    return {"x": lerp(before["x"], after["x"]), "y": lerp(before["y"], after["y"]),
            "w": lerp(before["w"], after["w"]), "h": lerp(before["h"], after["h"]),
            "t": sec}, "OK"


def boxes_match(a: dict, b: dict) -> bool:
    """C08 — hardened deterministic same-actor geometry test in the shared
    normalized coordinate system (x/y top-left, 0..1). ALL required:
    compatible box size, center displacement small relative to body size,
    AND strong overlap. A nearby duel opponent whose box merely overlaps
    must fail closed — overlap alone is never identity."""
    ax, ay, aw, ah = float(a["x"]), float(a["y"]), float(a["w"]), float(a["h"])
    bx, by, bw, bh = float(b["x"]), float(b["y"]), float(b["w"]), float(b["h"])
    if min(aw, ah, bw, bh) <= 0:
        return False
    for ratio in (aw / bw, ah / bh):
        if not (_MATCH_SIZE_RATIO_MIN <= ratio <= _MATCH_SIZE_RATIO_MAX):
            return False
    acx, acy = ax + aw / 2.0, ay + ah / 2.0
    bcx, bcy = bx + bw / 2.0, by + bh / 2.0
    if abs(acx - bcx) > _MATCH_CENTER_FACTOR * max(aw, bw):
        return False
    if abs(acy - bcy) > _MATCH_CENTER_FACTOR * max(ah, bh):
        return False
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return union > 0 and inter / union >= _MATCH_IOU_MIN


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

def _chain_of(c: dict):
    sc = c.get("scoring_chain")
    return sc if isinstance(sc, dict) else None


def _valid_assist_chain(c: dict, contact_ms, duration_ms=None) -> bool:
    """C04 — STRICT temporal assist chain: all four chain times present,
    continuous, ordered inside the candidate window, pass contact equals the
    canonical contact, and everything inside the video duration."""
    sc = _chain_of(c)
    if not sc or sc.get("continuous_causal_sequence") is not True:
        return False
    pc, tr, tsh, go = (sc.get("pass_contact_ms"), sc.get("teammate_receive_ms"),
                       sc.get("teammate_shot_ms"), sc.get("goal_outcome_ms"))
    if not all(_is_int(v) for v in (pc, tr, tsh, go)):
        return False
    if _is_int(contact_ms) and pc != contact_ms:
        return False
    start = c.get("start_ms") if _is_int(c.get("start_ms")) else pc
    end = c.get("end_ms") if _is_int(c.get("end_ms")) else go
    if not (start <= pc <= tr <= tsh <= go <= end):
        return False
    if _is_int(duration_ms) and not all(
            0 <= v <= duration_ms for v in (start, pc, tr, tsh, go, end)):
        return False
    return True


def _valid_key_pass_chain(c: dict, contact_ms, duration_ms=None) -> bool:
    """C04 — KEY_PASS needs a valid continuous pass→receive→shot chain;
    the goal outcome may be absent."""
    sc = _chain_of(c)
    if not sc or sc.get("continuous_causal_sequence") is not True:
        return False
    pc, tr, tsh = (sc.get("pass_contact_ms"), sc.get("teammate_receive_ms"),
                   sc.get("teammate_shot_ms"))
    if not all(_is_int(v) for v in (pc, tr, tsh)):
        return False
    if _is_int(contact_ms) and pc != contact_ms:
        return False
    start = c.get("start_ms") if _is_int(c.get("start_ms")) else pc
    end = c.get("end_ms") if _is_int(c.get("end_ms")) else tsh
    if not (start <= pc <= tr <= tsh <= end):
        return False
    if _is_int(duration_ms) and not all(
            0 <= v <= duration_ms for v in (start, pc, tr, tsh, end)):
        return False
    return True


def classify_candidate(c: dict, contact_ms=None, duration_ms=None):
    """PART 6/7 + C04 — deterministic canonical classification of a spatially
    verified candidate. GOAL and ASSIST chains are enforced here AND again by
    verified_stats.normalize_canonical (single shared hard gate)."""
    if not _is_int(contact_ms):
        contact_ms = c.get("contact_ms") if _is_int(c.get("contact_ms")) \
            else c.get("start_ms")
    at = str(c.get("action_type") or "").strip().upper()
    out = str(c.get("outcome") or "").strip().upper()
    vis = c.get("outcome_visible") is True
    et, res = at, out or "UNKNOWN"
    if at == "SHOT":
        if out == "SCORED" and vis:
            et, res = "GOAL", "SCORED"
        elif not vis:
            res = "OUTCOME_NOT_VISIBLE"
    elif at in ("PASS", "CROSS"):
        if (out == "TEAMMATE_SCORED" and vis
                and _valid_assist_chain(c, contact_ms, duration_ms)):
            et, res = "ASSIST", "TEAMMATE_SCORED"
        elif (vis and out in ("TEAMMATE_SCORED", "TEAMMATE_SHOT")
                and _valid_key_pass_chain(c, contact_ms, duration_ms)):
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
    contract = validate_coverage_contract(discovery, duration_s)
    ledger["coverage_contract"] = contract
    ledger["coverage_contract_complete"] = contract["complete"]
    if not isinstance(discovery, dict):
        return _finalize_coverage_state(ledger)
    cands = discovery.get("events")
    if not isinstance(cands, list):
        return _finalize_coverage_state(ledger)
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
        et, cat, res, vis = classify_candidate(
            c, contact_ms=contact,
            duration_ms=int(round(max(0.0, float(duration_s or 0)) * 1000)) or None)
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
    return _finalize_coverage_state(ledger)


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
            "actor_spatial_verified": True,
            "ledger_sequence_id": e["sequence_id"],
            "ledger_contact_ms": e["contact_ms"],
            # C01 — canonical authority stays millisecond exact; the MM:SS
            # timestamp above is presentation only. FIX01 preserves these.
            "event_start_ms": e["contact_ms"],
            "event_end_ms": e["contact_ms"],
        })
    return rows


def authoritative_timeline(ledger) -> list[dict]:
    """C06 — the prose model is NEVER event authority for FIX08 reports.
    Valid ledger with usable track → projected verified candidates (possibly
    partial). Discovery failed / malformed / no usable track → EMPTY timeline,
    never the legacy 6-15 model highlight list."""
    if (isinstance(ledger, dict) and ledger.get("status") == "ok"
            and ledger.get("track_usable")):
        return project_to_timeline(ledger)
    return []


def discovery_summary(ledger) -> dict:
    """FIX09 P12 — compact deterministic audit state. The contract can be
    structurally COMPLETE; it is never described as 'proven exhaustive'."""
    if not isinstance(ledger, dict):
        return {"status": "unavailable", "coverage_state": "UNAVAILABLE",
                "coverage_contract_complete": False,
                "event_discovery_complete": False}
    contract = ledger.get("coverage_contract") if isinstance(
        ledger.get("coverage_contract"), dict) else {}
    out = {
        "status": ledger.get("status"),
        "coverage_state": ledger.get("coverage_state") or "UNAVAILABLE",
        "coverage_contract_complete": ledger.get("coverage_contract_complete") is True,
        "event_discovery_complete": ledger.get("discovery_complete") is True,
        "track_usable": ledger.get("track_usable") is True,
        "expected_bucket_count": contract.get("expected_bucket_count"),
        "received_bucket_count": contract.get("received_bucket_count"),
        "candidates_total": ledger.get("candidates_total"),
        "candidates_verified": ledger.get("candidates_verified"),
    }
    for k in ("missing_buckets", "duplicate_buckets", "unexpected_buckets",
              "events_found_mismatches", "coverage_contradictions"):
        v = contract.get(k)
        if v:
            out[k] = v[:10]
    if contract.get("unbucketable_events"):
        out["unbucketable_events"] = contract["unbucketable_events"]
    if contract.get("malformed_rows"):
        out["malformed_coverage_rows"] = contract["malformed_rows"]
    return out


DISCOVERY_UNAVAILABLE_NOTICE = (
    "\n\n📋 EVENT DISCOVERY UNAVAILABLE — DO NOT INVENT SPECIFIC EVENTS OR "
    "TIMESTAMPS. Write only general development observations without citing "
    "specific moments, goals, assists or times."
)


def ledger_prompt_block(ledger) -> str:
    """PART 9 — compact ledger context for the full-report prompt: the model
    writes ABOUT these observed events; it never invents new ones. When no
    verified ledger exists, an explicit unavailable notice is injected (C06)."""
    evs = ((ledger or {}).get("events") or [])
    if not evs:
        return DISCOVERY_UNAVAILABLE_NOTICE
    lines = []
    for e in evs[:80]:
        desc = (e.get("description") or "")[:120]
        lines.append(f"- {_mmss(e['contact_ms'])} — {e['action_type']}: {desc}")
    if (ledger or {}).get("coverage_state") == "COMPLETE":
        tail = (
            "\nTHE EVENT LEDGER IS THE AUTHORITATIVE OBSERVED-EVENT SOURCE. Do NOT "
            "invent new goals, new assists, new event timestamps or new target-player "
            "actions. Any football example or timestamp you use in prose MUST come "
            "from this ledger."
        )
    else:
        # FIX09 P11 — partial coverage contract: verified moments only.
        tail = (
            "\nEVENT COVERAGE IS PARTIAL. The entries above are verified individual "
            "moments only — NOT a complete match record. DO NOT describe event counts "
            "as complete match totals. DO NOT claim \"all\", \"every\", \"only\" or "
            "exhaustive totals from the event ledger. Do NOT invent new goals, new "
            "assists, new event timestamps or new target-player actions. Any football "
            "example or timestamp you use in prose MUST come from this ledger."
        )
    return (
        "\n\n📋 OBSERVED EVENT LEDGER (machine-validated: each entry passed exact "
        "contact-time spatial verification against the tapped player's own track):\n"
        + "\n".join(lines) + tail
    )


# ----------------------------------------------- event-native evidence (P12)

_PRIORITY = {"GOAL": 0, "ASSIST": 1, "KEY_PASS": 2, "SHOT": 3}


def create_event_native_evidence(full: dict, max_rows: int = 6, track=None) -> dict:
    """PART 12 + C02 — deterministic evidence rows EXACTLY bound to important
    VERIFIED events that have no exact evidence row yet. Zero model calls.
    event_track_locked (deterministic FIX04 identity at the exact contact) is
    set ONLY for spatially verified events whose target bbox resolves at
    event_start_ms — otherwise the row stays text-only downstream."""
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
        row = {
            "timestamp": e.get("timestamp"),
            "comment": desc,
            "player_check": "FIX08 event-native evidence — created deterministically "
                            "from the verified event.",
            "identity_confidence": "high",
            "event_id": e["event_id"],
            "evidence_time_ms": e["event_start_ms"],
            "event_native": True,
        }
        # C02 — deterministic identity: spatially verified event + exact
        # target bbox at contact. NEVER marked anchor_locked (separate
        # semantics) and NEVER model-checked downstream.
        if (e.get("actor_spatial_verified") is True
                or e.get("event_source") == "fix08_ledger"):
            pt, _why = resolve_target_box(track, e["event_start_ms"])
            if pt is not None:
                row["event_track_locked"] = True
                row["event_track_box"] = {"x": float(pt["x"]), "y": float(pt["y"]),
                                          "w": float(pt["w"]), "h": float(pt["h"])}
        comments.append(row)
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
    # C05 — keys the current web SnapshotsSection actually renders, in order.
    snap_keys = ("strength", "noticed", "hidden", "develop")
    for e, c in sorted(usable, key=_prio):
        if e["event_id"] in seen:
            continue
        seen.add(e["event_id"])
        et = str(e.get("canonical_event_type") or "").upper()
        moments.append({
            "key": snap_keys[len(moments)],
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
