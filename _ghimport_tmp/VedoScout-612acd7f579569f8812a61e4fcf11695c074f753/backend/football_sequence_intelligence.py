"""FIX 09B.2 — football sequence intelligence.

This module turns the unified FIX09B.1 scene graph into a high-recall sequence
analysis plan and validates the structured result of ONE whole-video multimodal
analysis pass.  It does not create a second player identity authority and it
does not decide final canonical events; FIX09B.3 does that.

Core principle
--------------
FIND → UNDERSTAND → REFINE → VERIFY → SHOW

The planner deliberately covers every interval where GLOBAL_TARGET is visible
or a bounded target hypothesis exists.  High-rate refinement windows are then
added around possession changes, ball proximity, close pressure, motion change,
and identity ambiguity.  This avoids the old failure mode where an uncertain
single contact frame deleted an otherwise observable football sequence.

Contracts
---------
* Input identity is only GLOBAL_TARGET from FIX09B.0/B.1.
* All times are canonical media milliseconds.
* Hard scene cuts are absolute causal boundaries.
* Ambiguity is preserved; model output may never silently select one of several
  target candidates merely because that candidate performs a football action.
* Model observations require visible evidence timestamps.
* No unseen action/outcome may be inferred.
* The model call itself remains in the server/orchestrator.  This module is pure
  planning, prompting and result validation and is therefore deterministic.
"""
from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy

import open_observation_compat

VERSION = 1
GLOBAL_TARGET_ID = "GLOBAL_TARGET"

# Broad sequence coverage: enough context to understand buildup and outcome.
CONTEXT_BEFORE_MS = 1800
CONTEXT_AFTER_MS = 2400
ACTIVE_GAP_MS = 1300
MAX_ANALYSIS_WINDOW_MS = 9000
ANALYSIS_OVERLAP_MS = 1500

# Local precision refinement around likely contact/duel/identity moments.
REFINE_BEFORE_MS = 1400
REFINE_AFTER_MS = 1800
REFINE_GROUP_GAP_MS = 1500
MAX_REFINE_WINDOW_MS = 5200
NORMAL_REVIEW_HZ = 12.5
HIGH_REVIEW_HZ = 25.0

# Geometry-derived supporting triggers.  They never classify football events.
BALL_NEAR_TARGET_H = 1.35
PRESSURE_H = 1.75
ACCEL_TRIGGER_H_S2 = 3.5

ACTION_KINDS = {
    "RECEIVE", "FIRST_TOUCH", "CONTROL", "CARRY", "DRIBBLE", "TAKE_ON",
    "FEINT", "TURN", "DIRECTION_CHANGE", "ACCELERATION", "DECELERATION",
    "PASS", "CROSS", "KEY_PASS", "SHOT", "DUEL", "TACKLE", "INTERCEPTION",
    "RECOVERY", "PRESS", "RUN", "OFF_BALL_RUN", "SPACE_CREATION", "SCAN",
    "BODY_ORIENTATION", "SUPPORT", "OTHER",
}

OUTCOMES = {
    "GOAL", "SAVED", "BLOCKED", "OFF_TARGET", "COMPLETED", "INCOMPLETE",
    "WON", "LOST", "TEAMMATE_SHOT", "TEAMMATE_GOAL", "TURNOVER", "UNKNOWN",
}

FEET = {"LEFT", "RIGHT", "BOTH", "UNKNOWN"}
TARGET_STATES = {"VERIFIED", "HYPOTHESES", "UNRESOLVED"}


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _valid_box(b) -> bool:
    if not isinstance(b, dict):
        return False
    try:
        x, y, w, h = (float(b[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return False
    return -0.05 <= x <= 1.05 and -0.05 <= y <= 1.05 and 0 < w <= 1.1 and 0 < h <= 1.1


def _center(b):
    return float(b["x"]) + float(b["w"]) / 2.0, float(b["y"]) + float(b["h"]) / 2.0


def _foot(b):
    return float(b["x"]) + float(b["w"]) / 2.0, float(b["y"]) + float(b["h"])


def _dist(a, b) -> float:
    ax, ay = _center(a)
    bx, by = _center(b)
    return math.hypot(ax - bx, ay - by)


def _scene_bounds(scene_graph) -> dict:
    out = {}
    for s in (scene_graph or {}).get("scenes") or []:
        if not isinstance(s, dict) or not _num(s.get("start_ms")) or not _num(s.get("end_ms")):
            continue
        a, b = int(round(float(s["start_ms"]))), int(round(float(s["end_ms"])))
        if b < a:
            a, b = b, a
        out[str(s.get("scene_id") or f"scene@{a}")] = (a, b)
    return out


def _frame_target_ids(frame) -> list[str]:
    tm = (frame or {}).get("global_target") or {}
    ids = []
    one = tm.get("local_track_id")
    if isinstance(one, str) and one:
        ids.append(one)
    for tid in tm.get("candidate_local_track_ids") or []:
        if isinstance(tid, str) and tid and tid not in ids:
            ids.append(tid)
    return ids[:4]


def _player_map(frame) -> dict:
    return {
        p.get("local_track_id"): p
        for p in (frame or {}).get("players") or []
        if isinstance(p, dict) and isinstance(p.get("local_track_id"), str)
    }


def _target_boxes(frame) -> list[tuple[str, dict]]:
    pm = _player_map(frame)
    out = []
    for tid in _frame_target_ids(frame):
        p = pm.get(tid)
        if p and _valid_box(p.get("box")):
            out.append((tid, p["box"]))
    return out


def _ball_near_target(frame) -> bool:
    b = ((frame or {}).get("ball") or {}).get("box")
    if not _valid_box(b):
        return False
    bx, by = _center(b)
    for _tid, tb in _target_boxes(frame):
        fx, fy = _foot(tb)
        if math.hypot(bx - fx, by - fy) / max(float(tb["h"]), 1e-6) <= BALL_NEAR_TARGET_H:
            return True
    return False


def _pressure_count(frame) -> int:
    """Nearby non-target bodies; team labels refine the count when available.

    This is only a refinement trigger.  It never claims a duel or opponent
    action because ingestion may not yet have a reliable team label.
    """
    pm = _player_map(frame)
    target_ids = set(_frame_target_ids(frame))
    target = _target_boxes(frame)
    if not target:
        return 0
    count = 0
    seen = set()
    for tid, p in pm.items():
        if tid in target_ids or tid in seen or not _valid_box(p.get("box")):
            continue
        for _tt, tb in target:
            d_h = _dist(tb, p["box"]) / max(float(tb["h"]), float(p["box"]["h"]), 1e-6)
            if d_h <= PRESSURE_H:
                count += 1
                seen.add(tid)
                break
    return count


def _target_motion(frames) -> dict[int, dict]:
    """Camera-compensated scene-local track velocity/acceleration estimates.

    B.1 already removed camera translation when associating tracks, but its
    output intentionally stores only geometry.  Here we derive scale-normalised
    screen motion from consecutive points of the same scene-local target track.
    It is a trigger, not a physical speed statistic.
    """
    per_track = {}
    result = {}
    for f in frames:
        ms = int(f["media_ms"])
        scene = f.get("scene_id")
        pm = _player_map(f)
        for tid in _frame_target_ids(f):
            p = pm.get(tid)
            if not p or not _valid_box(p.get("box")):
                continue
            key = (scene, tid)
            cx, cy = _center(p["box"])
            h = max(float(p["box"]["h"]), 1e-6)
            prev = per_track.get(key)
            speed = accel = None
            if prev and ms > prev["ms"]:
                dt = (ms - prev["ms"]) / 1000.0
                speed = math.hypot(cx - prev["cx"], cy - prev["cy"]) / max(h, prev["h"], 1e-6) / dt
                if prev.get("speed") is not None:
                    accel = (speed - prev["speed"]) / dt
            per_track[key] = {"ms": ms, "cx": cx, "cy": cy, "h": h, "speed": speed}
            row = result.setdefault(ms, {"speed_h_s": None, "accel_h_s2": None})
            # For hypotheses keep the largest motion magnitude so refinement is
            # recall-oriented without selecting an identity candidate.
            if speed is not None and (row["speed_h_s"] is None or speed > row["speed_h_s"]):
                row["speed_h_s"] = speed
            if accel is not None and (row["accel_h_s2"] is None or abs(accel) > abs(row["accel_h_s2"])):
                row["accel_h_s2"] = accel
    return result


def _frame_reasons(frame, prev_frame, motion_row) -> list[str]:
    tm = (frame or {}).get("global_target") or {}
    status = str(tm.get("status") or "UNRESOLVED")
    reasons = []
    if status == "HYPOTHESES":
        reasons.append("IDENTITY_AMBIGUITY")
    elif status == "UNRESOLVED":
        reasons.append("TARGET_UNRESOLVED")

    pos = (frame or {}).get("possession") or {}
    rel = str(pos.get("target_relation") or "")
    if rel == "TARGET_LIKELY_POSSESSION":
        reasons.append("TARGET_POSSESSION")
    elif rel == "TARGET_POSSESSION_CANDIDATE":
        reasons.append("TARGET_POSSESSION_CANDIDATE")

    if _ball_near_target(frame):
        reasons.append("BALL_NEAR_TARGET")

    if prev_frame is not None:
        prev_pos = (prev_frame.get("possession") or {}).get("holder_local_track_id")
        cur_pos = pos.get("holder_local_track_id")
        if prev_pos != cur_pos and (prev_pos is not None or cur_pos is not None):
            ids = set(_frame_target_ids(frame)) | set(_frame_target_ids(prev_frame))
            if prev_pos in ids or cur_pos in ids:
                reasons.append("TARGET_POSSESSION_CHANGE")
        prev_rel = str((prev_frame.get("possession") or {}).get("target_relation") or "")
        if prev_rel != rel and ("TARGET" in prev_rel or "TARGET" in rel):
            reasons.append("TARGET_BALL_RELATION_CHANGE")

    pressure = _pressure_count(frame)
    if pressure:
        reasons.append("CLOSE_PRESSURE")
    if pressure >= 2:
        reasons.append("MULTI_DEFENDER_PRESSURE")

    acc = (motion_row or {}).get("accel_h_s2")
    if _num(acc) and abs(float(acc)) >= ACCEL_TRIGGER_H_S2:
        reasons.append("TARGET_MOTION_CHANGE")
    return reasons


def _stable_id(prefix: str, scene_id, start_ms: int, end_ms: int) -> str:
    raw = f"{prefix}|{scene_id}|{int(start_ms)}|{int(end_ms)}".encode("utf-8")
    return f"{prefix}_{hashlib.sha1(raw).hexdigest()[:12]}"


def _clip_window(scene_bounds, scene_id, start_ms, end_ms):
    a, b = scene_bounds.get(scene_id, (int(start_ms), int(end_ms)))
    return max(a, int(start_ms)), min(b, int(end_ms))


def _split_span(start_ms: int, end_ms: int, max_ms=MAX_ANALYSIS_WINDOW_MS,
                overlap_ms=ANALYSIS_OVERLAP_MS) -> list[tuple[int, int]]:
    if end_ms <= start_ms:
        return [(start_ms, end_ms)]
    if end_ms - start_ms <= max_ms:
        return [(start_ms, end_ms)]
    out = []
    step = max(1000, max_ms - overlap_ms)
    s = start_ms
    while s < end_ms:
        e = min(end_ms, s + max_ms)
        out.append((s, e))
        if e >= end_ms:
            break
        s += step
    return out


def _active_spans(frames) -> list[dict]:
    """Continuous target-visible/hypothesis spans, split by scene and long gap."""
    spans = []
    cur = None
    for f in frames:
        tm = f.get("global_target") or {}
        status = str(tm.get("status") or "UNRESOLVED")
        active = status in ("VERIFIED", "HYPOTHESES") and bool(_frame_target_ids(f))
        if not active:
            continue
        ms, scene = int(f["media_ms"]), str(f.get("scene_id") or "scene_unknown")
        if cur is None or cur["scene_id"] != scene or ms - cur["last_ms"] > ACTIVE_GAP_MS:
            if cur:
                spans.append(cur)
            cur = {"scene_id": scene, "start_ms": ms, "end_ms": ms, "last_ms": ms,
                   "verified_frames": 0, "hypothesis_frames": 0}
        cur["end_ms"] = cur["last_ms"] = ms
        if status == "VERIFIED":
            cur["verified_frames"] += 1
        else:
            cur["hypothesis_frames"] += 1
    if cur:
        spans.append(cur)
    return spans


def _group_refinement_points(points, scene_bounds) -> list[dict]:
    groups = []
    cur = None
    for row in sorted(points, key=lambda r: (r["scene_id"], r["media_ms"])):
        if (cur is None or cur["scene_id"] != row["scene_id"]
                or row["media_ms"] - cur["last_ms"] > REFINE_GROUP_GAP_MS):
            if cur:
                groups.append(cur)
            cur = {"scene_id": row["scene_id"], "first_ms": row["media_ms"],
                   "last_ms": row["media_ms"], "reasons": set(row["reasons"]),
                   "trigger_ms": [row["media_ms"]]}
        else:
            cur["last_ms"] = row["media_ms"]
            cur["reasons"].update(row["reasons"])
            cur["trigger_ms"].append(row["media_ms"])
    if cur:
        groups.append(cur)

    out = []
    for g in groups:
        s, e = _clip_window(
            scene_bounds, g["scene_id"],
            g["first_ms"] - REFINE_BEFORE_MS,
            g["last_ms"] + REFINE_AFTER_MS,
        )
        for ss, ee in _split_span(s, e, MAX_REFINE_WINDOW_MS, 700):
            out.append({
                "refinement_id": _stable_id("ref", g["scene_id"], ss, ee),
                "scene_id": g["scene_id"],
                "start_ms": ss, "end_ms": ee,
                "review_hz": HIGH_REVIEW_HZ,
                "reasons": sorted(g["reasons"]),
                "trigger_ms": [m for m in sorted(set(g["trigger_ms"])) if ss <= m <= ee],
            })
    return out


def _context_rows(frames, start_ms, end_ms, max_rows=20) -> list[dict]:
    inside = [f for f in frames if start_ms <= int(f["media_ms"]) <= end_ms]
    if not inside:
        return []
    stride = max(1, math.ceil(len(inside) / max_rows))
    chosen = inside[::stride]
    if chosen[-1] is not inside[-1]:
        chosen.append(inside[-1])
    rows = []
    for f in chosen[:max_rows + 1]:
        tm = f.get("global_target") or {}
        pos = f.get("possession") or {}
        rows.append({
            "media_ms": int(f["media_ms"]),
            "target_status": tm.get("status"),
            "target_local_track_id": tm.get("local_track_id"),
            "target_candidates": list(tm.get("candidate_local_track_ids") or [])[:4],
            "target_proof_eligible": bool(tm.get("proof_eligible")),
            "ball_state": f.get("ball_state"),
            "possession_status": pos.get("status"),
            "holder_local_track_id": pos.get("holder_local_track_id"),
            "target_ball_relation": pos.get("target_relation"),
            "pressure_count": _pressure_count(f),
        })
    return rows


def build_sequence_plan(scene_graph: dict | None) -> dict:
    """Build exhaustive broad windows + targeted high-rate refinement windows."""
    sg = scene_graph if isinstance(scene_graph, dict) else {}
    frames = sorted(
        [f for f in sg.get("frames") or [] if isinstance(f, dict) and _num(f.get("media_ms"))],
        key=lambda f: int(f["media_ms"]),
    )
    if not frames:
        return {
            "version": VERSION, "status": "empty", "global_target_id": GLOBAL_TARGET_ID,
            "timebase": "canonical_media_ms", "analysis_windows": [],
            "refinement_windows": [], "metrics": {},
        }

    bounds = _scene_bounds(sg)
    motion = _target_motion(frames)

    # Broad coverage. Every target-active span is reviewed with context and
    # split into overlapping bounded windows. This is the recall floor.
    analysis = []
    for span in _active_spans(frames):
        s, e = _clip_window(
            bounds, span["scene_id"],
            span["start_ms"] - CONTEXT_BEFORE_MS,
            span["end_ms"] + CONTEXT_AFTER_MS,
        )
        for ss, ee in _split_span(s, e):
            analysis.append({
                "sequence_id": _stable_id("seq", span["scene_id"], ss, ee),
                "scene_id": span["scene_id"],
                "start_ms": ss, "end_ms": ee,
                "review_hz": NORMAL_REVIEW_HZ,
                "coverage_reason": "GLOBAL_TARGET_ACTIVE",
                "verified_frames": span["verified_frames"],
                "hypothesis_frames": span["hypothesis_frames"],
                "graph_context": _context_rows(frames, ss, ee),
            })

    # Precision triggers, intentionally independent of whether an event has
    # already been classified. These tell the later refinement stage where
    # first touch/kick contact/feints/crossovers deserve denser inspection.
    trigger_rows = []
    prev = None
    for f in frames:
        reasons = _frame_reasons(f, prev, motion.get(int(f["media_ms"])))
        if reasons:
            trigger_rows.append({
                "scene_id": str(f.get("scene_id") or "scene_unknown"),
                "media_ms": int(f["media_ms"]), "reasons": reasons,
            })
        prev = f
    refinement = _group_refinement_points(trigger_rows, bounds)

    # Attach each refinement window to all overlapping broad sequence windows.
    for r in refinement:
        r["sequence_ids"] = [
            a["sequence_id"] for a in analysis
            if a["scene_id"] == r["scene_id"]
            and not (a["end_ms"] < r["start_ms"] or a["start_ms"] > r["end_ms"])
        ]

    covered_ms = sum(max(0, a["end_ms"] - a["start_ms"]) for a in analysis)
    return {
        "version": VERSION,
        "status": "ok" if analysis else "no_target_coverage",
        "global_target_id": GLOBAL_TARGET_ID,
        "timebase": "canonical_media_ms",
        "analysis_windows": analysis,
        "refinement_windows": refinement,
        "metrics": {
            "scene_graph_frames": len(frames),
            "analysis_windows": len(analysis),
            "refinement_windows": len(refinement),
            "broad_covered_ms_unioned_approx": covered_ms,
            "trigger_points": len(trigger_rows),
            "target_active_spans": len(_active_spans(frames)),
        },
    }


def _prompt_plan(plan: dict, max_context_rows=12) -> dict:
    """Compact prompt-safe plan; prevents huge graph dumps into the model."""
    windows = []
    for w in (plan or {}).get("analysis_windows") or []:
        windows.append({
            "sequence_id": w.get("sequence_id"), "scene_id": w.get("scene_id"),
            "start_ms": w.get("start_ms"), "end_ms": w.get("end_ms"),
            "graph_context": list(w.get("graph_context") or [])[:max_context_rows],
        })
    refs = []
    for r in (plan or {}).get("refinement_windows") or []:
        refs.append({
            "refinement_id": r.get("refinement_id"), "scene_id": r.get("scene_id"),
            "start_ms": r.get("start_ms"), "end_ms": r.get("end_ms"),
            "reasons": list(r.get("reasons") or []),
        })
    return {"analysis_windows": windows, "refinement_windows": refs}


def build_analysis_prompt(plan: dict, player_details=None, identity_context=None) -> str:
    """Strong whole-sequence multimodal prompt for the existing video call.

    The graph is context, never ground truth about a football action. The model
    must inspect the actual video and attach visible evidence timestamps to each
    claimed target action/observation.
    """
    pd = player_details if isinstance(player_details, dict) else {}
    ident = identity_context if isinstance(identity_context, dict) else {}
    compact = json.dumps(_prompt_plan(plan), separators=(",", ":"), ensure_ascii=False)
    profile = ident.get("identity_profile") if isinstance(ident.get("identity_profile"), dict) else {}
    return f"""You are the football SEQUENCE INTELLIGENCE stage for one specifically selected youth player called GLOBAL_TARGET.

MISSION
Inspect the ACTUAL attached video, sequence by sequence, and find EVERY clearly observable football contribution by GLOBAL_TARGET. Understand complete causal sequences, not isolated frames. High recall is required, but never invent an action, actor, foot, outcome, or timestamp that is not visually supported.

IDENTITY RULES
- GLOBAL_TARGET is the exact player selected by the user. Never select a player because he performs an interesting action.
- The structured graph below is SUPPORTING context only. VERIFIED local-track mappings are strong identity evidence; HYPOTHESES means multiple bodies remain possible and you MUST inspect before/after frames rather than choose by behaviour.
- If identity cannot be physically resolved from visible continuity, return target_status=UNRESOLVED for that action. Do not guess.
- Do not use behavioural profiling such as 'the target usually dribbles this way' as identity evidence.

SEQUENCE RULES
- Follow the sequence several seconds BEFORE and AFTER each possible target involvement.
- A sequence may contain: scan, body orientation, receive, first touch, control, turn, feint, direction change, acceleration/deceleration, carry, dribble/take-on, pass/cross/key pass, shot, duel, tackle, interception, recovery, press, support, off-ball run, or space creation.
- Record micro-actions separately when they are genuinely visible. Do not collapse receive → turn → feint → acceleration → shot into one generic label.
- Open-world perception: if a visible football behaviour does not fit the canonical kind enum, set kind=OTHER but preserve a concise free-form raw_kind and raw_description. Never discard a visible behaviour merely because the enum has no exact label.
- Distinguish target action from teammate/opponent action. Track possession transfer and who performs the next action.
- For a pass/cross that might become an assist, inspect the continuous visible chain: TARGET contact → teammate receive/use → teammate shot → visible goal. A cut breaks the causal chain.
- For a target goal, require target shot contact and a visible goal outcome in the same causal sequence.
- start_ms/end_ms describe the target's own action. Later receiver/shot/goal timestamps belong in causal_chain and may occur after action end, but they MUST remain inside the same supplied no-cut sequence window.
- The target does NOT need to remain on screen after his pass if the teammate's outcome remains continuously visible.
- If contact is briefly occluded, use adjacent frames to describe what is visible, but mark contact_visibility=OCCLUDED rather than fabricating exact contact.
- Replays/duplicate views of the same real-world action must be marked duplicate_of, not counted as a second action.

DETAIL STANDARD
For every action, capture the useful visible detail: pressure, nearby defenders, direction of movement, body orientation, first-touch direction, turn/feint type if actually distinguishable, acceleration/separation, passing direction, receiving teammate, shooting foot when visible, and visible outcome. Observations such as scanning or space creation require their own evidence_ms.

PLAYER CONTEXT
name={pd.get('player_name') or 'selected player'}; age={pd.get('age') or 'youth'}; position={pd.get('position') or 'unknown'}; jersey_hint={profile.get('jersey_number') or 'unknown'}.
These hints NEVER override the video or identity graph.

ANALYSIS PLAN (canonical media milliseconds; hard scene boundaries)
{compact}

RETURN ONLY VALID JSON with this exact top-level shape:
{{
  "sequences": [
    {{
      "sequence_id": "one supplied sequence_id",
      "scene_id": "supplied scene_id",
      "start_ms": 0,
      "end_ms": 0,
      "summary": "short factual sequence summary",
      "actions": [
        {{
          "action_id": "unique within response",
          "kind": "RECEIVE|FIRST_TOUCH|CONTROL|CARRY|DRIBBLE|TAKE_ON|FEINT|TURN|DIRECTION_CHANGE|ACCELERATION|DECELERATION|PASS|CROSS|KEY_PASS|SHOT|DUEL|TACKLE|INTERCEPTION|RECOVERY|PRESS|RUN|OFF_BALL_RUN|SPACE_CREATION|SCAN|BODY_ORIENTATION|SUPPORT|OTHER",
          "raw_kind": "concise free-form visible football action label; may be outside canonical enum",
          "raw_description": "concise factual visible behaviour/context; no inference",
          "start_ms": 0,
          "contact_ms": null,
          "end_ms": 0,
          "target_status": "VERIFIED|HYPOTHESES|UNRESOLVED",
          "actor_local_track_id": null,
          "actor_candidate_local_track_ids": [],
          "actor_box": null,
          "actor_evidence": [{{"media_ms":0,"box":{{"x":0,"y":0,"w":0,"h":0}},"visibility":"VISIBLE|PARTIAL|OCCLUDED"}}],
          "evidence_ms": [0],
          "foot": "LEFT|RIGHT|BOTH|UNKNOWN",
          "pressure": {{"level":"NONE|LOW|MEDIUM|HIGH|UNKNOWN","nearby_players":0}},
          "details": ["short visible micro-detail"],
          "outcome": "GOAL|SAVED|BLOCKED|OFF_TARGET|COMPLETED|INCOMPLETE|WON|LOST|TEAMMATE_SHOT|TEAMMATE_GOAL|TURNOVER|UNKNOWN",
          "outcome_visible": true,
          "causal_chain": {{
             "target_contact_ms": null,
             "receiver_local_track_id": null,
             "receiver_ms": null,
             "teammate_shot_ms": null,
             "goal_outcome_ms": null,
             "continuous_visible_sequence": false
          }},
          "contact_visibility": "VISIBLE|PARTIAL|OCCLUDED|UNKNOWN",
          "duplicate_of": null
        }}
      ]
    }}
  ],
  "coverage": [{{"sequence_id":"supplied sequence_id","reviewed":true,"target_seen":true,"actions_found":0}}]
}}

Return EXACTLY ONE sequences row and EXACTLY ONE coverage row for EVERY supplied
analysis window, including windows where no action is found. For an empty window,
return actions=[] and actions_found=0. actions_found MUST equal the number of
actions returned for that sequence. Never claim reviewed=true for an omitted or
truncated sequence row.

Do not cap the number of actions. Every factual action/detail needs visible evidence_ms from the same sequence."""


def _int_ms(v):
    if not _num(v):
        return None
    return max(0, int(round(float(v))))


def _normalise_actor_evidence(rows, start_ms, end_ms):
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        ms = _int_ms(r.get("media_ms"))
        if ms is None or not (start_ms <= ms <= end_ms) or not _valid_box(r.get("box")):
            continue
        vis = str(r.get("visibility") or "UNKNOWN").upper()
        if vis not in {"VISIBLE", "PARTIAL", "OCCLUDED", "UNKNOWN"}:
            vis = "UNKNOWN"
        out.append({"media_ms": ms, "box": deepcopy(r["box"]), "visibility": vis})
    seen = set()
    uniq = []
    for r in sorted(out, key=lambda x: x["media_ms"]):
        key = (r["media_ms"], tuple(round(float(r["box"][k]), 4) for k in ("x", "y", "w", "h")))
        if key not in seen:
            seen.add(key); uniq.append(r)
    return uniq[:20]


def _normalise_action(a, window):
    if not isinstance(a, dict):
        return None
    ws, we = int(window["start_ms"]), int(window["end_ms"])
    start = _int_ms(a.get("start_ms"))
    end = _int_ms(a.get("end_ms"))
    if start is None or end is None:
        return None
    if end < start:
        start, end = end, start
    # A model timestamp outside the supplied same-scene window is not silently
    # clipped into truth; reject the malformed action.
    if start < ws or end > we:
        return None
    contact = _int_ms(a.get("contact_ms")) if a.get("contact_ms") is not None else None
    if contact is not None and not (start <= contact <= end):
        return None
    kind = str(a.get("kind") or "OTHER").upper()
    if kind not in ACTION_KINDS:
        kind = "OTHER"
    target_state = str(a.get("target_status") or "UNRESOLVED").upper()
    if target_state not in TARGET_STATES:
        target_state = "UNRESOLVED"
    foot = str(a.get("foot") or "UNKNOWN").upper()
    if foot not in FEET:
        foot = "UNKNOWN"
    outcome = str(a.get("outcome") or "UNKNOWN").upper()
    if outcome not in OUTCOMES:
        outcome = "UNKNOWN"
    evidence_ms = sorted({
        x for x in (_int_ms(v) for v in (a.get("evidence_ms") or []))
        if x is not None and start <= x <= end
    })[:30]
    actor_evidence = _normalise_actor_evidence(a.get("actor_evidence"), start, end)
    # No visible evidence → no factual action. This is intentionally stricter
    # than model prose but still allows an occluded exact contact if adjacent
    # evidence exists inside the action.
    if not evidence_ms and not actor_evidence:
        return None
    cand_ids = []
    for tid in a.get("actor_candidate_local_track_ids") or []:
        if isinstance(tid, str) and tid and tid not in cand_ids:
            cand_ids.append(tid)
    actor_id = a.get("actor_local_track_id") if isinstance(a.get("actor_local_track_id"), str) else None
    actor_box = deepcopy(a.get("actor_box")) if _valid_box(a.get("actor_box")) else None
    details = [str(x).strip()[:180] for x in (a.get("details") or []) if str(x).strip()][:20]
    cv = str(a.get("contact_visibility") or "UNKNOWN").upper()
    if cv not in {"VISIBLE", "PARTIAL", "OCCLUDED", "UNKNOWN"}:
        cv = "UNKNOWN"
    pressure = a.get("pressure") if isinstance(a.get("pressure"), dict) else {}
    plev = str(pressure.get("level") or "UNKNOWN").upper()
    if plev not in {"NONE", "LOW", "MEDIUM", "HIGH", "UNKNOWN"}:
        plev = "UNKNOWN"
    nearby = pressure.get("nearby_players")
    nearby = int(nearby) if isinstance(nearby, int) and not isinstance(nearby, bool) and nearby >= 0 else None
    chain = a.get("causal_chain") if isinstance(a.get("causal_chain"), dict) else {}
    chain_out = {
        "target_contact_ms": _int_ms(chain.get("target_contact_ms")),
        "receiver_local_track_id": chain.get("receiver_local_track_id") if isinstance(chain.get("receiver_local_track_id"), str) else None,
        "receiver_ms": _int_ms(chain.get("receiver_ms")),
        "teammate_shot_ms": _int_ms(chain.get("teammate_shot_ms")),
        "goal_outcome_ms": _int_ms(chain.get("goal_outcome_ms")),
        "continuous_visible_sequence": chain.get("continuous_visible_sequence") is True,
    }
    for k in ("target_contact_ms", "receiver_ms", "teammate_shot_ms", "goal_outcome_ms"):
        if chain_out[k] is not None and not (ws <= chain_out[k] <= we):
            chain_out[k] = None
    normalised = {
        "action_id": str(a.get("action_id") or "")[:80] or None,
        "kind": kind,
        "start_ms": start, "contact_ms": contact, "end_ms": end,
        "target_status": target_state,
        "actor_local_track_id": actor_id,
        "actor_candidate_local_track_ids": cand_ids[:6],
        "actor_box": actor_box,
        "actor_evidence": actor_evidence,
        "evidence_ms": evidence_ms,
        "foot": foot,
        "pressure": {"level": plev, "nearby_players": nearby},
        "details": details,
        "outcome": outcome,
        "outcome_visible": a.get("outcome_visible") is True,
        "causal_chain": chain_out,
        "contact_visibility": cv,
        "duplicate_of": str(a.get("duplicate_of"))[:80] if a.get("duplicate_of") else None,
    }
    return open_observation_compat.preserve_open_observation(a, normalised)


def normalise_sequence_analysis(raw, plan: dict) -> dict:
    """Validate model output against supplied sequence windows and timebase."""
    obj = raw if isinstance(raw, dict) else {}
    windows = {
        w.get("sequence_id"): w for w in (plan or {}).get("analysis_windows") or []
        if isinstance(w, dict) and w.get("sequence_id")
    }
    sequences = []
    sequence_ids_returned = set()
    sequence_row_counts = {}
    raw_action_counts = {}
    seen_action_ids = set()
    for s in obj.get("sequences") or []:
        if not isinstance(s, dict) or s.get("sequence_id") not in windows:
            continue
        sid = s["sequence_id"]
        sequence_row_counts[sid] = sequence_row_counts.get(sid, 0) + 1
        if s["sequence_id"] in sequence_ids_returned:
            # One supplied window has one response row. Duplicate rows are an
            # incomplete/malformed model contract, never extra event recall.
            continue
        w = windows[s["sequence_id"]]
        if str(s.get("scene_id")) != str(w.get("scene_id")):
            continue
        raw_actions = s.get("actions")
        raw_action_counts[sid] = len(raw_actions) if isinstance(raw_actions, list) else None
        actions = []
        for a in raw_actions if isinstance(raw_actions, list) else []:
            n = _normalise_action(a, w)
            if n is None:
                continue
            aid = n.get("action_id") or _stable_id("act", w["sequence_id"], n["start_ms"], n["end_ms"])
            if aid in seen_action_ids:
                # Duplicate ids cannot become two facts. Keep first occurrence;
                # replay duplication is represented explicitly by duplicate_of.
                continue
            seen_action_ids.add(aid)
            n["action_id"] = aid
            actions.append(n)
        sequences.append({
            "sequence_id": w["sequence_id"], "scene_id": w["scene_id"],
            "start_ms": int(w["start_ms"]), "end_ms": int(w["end_ms"]),
            "summary": str(s.get("summary") or "")[:500],
            "actions": sorted(actions, key=lambda a: (a["start_ms"], a["end_ms"], a["action_id"])),
        })
        sequence_ids_returned.add(w["sequence_id"])

    coverage_raw = {}
    coverage_row_counts = {}
    for r in obj.get("coverage") or []:
        if not isinstance(r, dict) or r.get("sequence_id") not in windows:
            continue
        sid = r["sequence_id"]
        coverage_row_counts[sid] = coverage_row_counts.get(sid, 0) + 1
        if sid not in coverage_raw:
            coverage_raw[sid] = r
    actions_by_sequence = {
        s["sequence_id"]: len(s.get("actions") or []) for s in sequences
    }
    coverage = []
    missing_sequence_ids = []
    action_count_mismatch_ids = []
    for sid in windows:
        r = coverage_raw.get(sid)
        reported_actions = (
            int(r.get("actions_found"))
            if r and isinstance(r.get("actions_found"), int)
            and not isinstance(r.get("actions_found"), bool)
            and r.get("actions_found") >= 0
            else None
        )
        sequence_returned = sid in sequence_ids_returned
        actual_actions = actions_by_sequence.get(sid)
        raw_actions = raw_action_counts.get(sid)
        action_count_matches = (
            reported_actions is not None
            and actual_actions is not None
            and raw_actions is not None
            and reported_actions == actual_actions
            and reported_actions == raw_actions
        )
        contract_complete = bool(
            r and r.get("reviewed") is True
            and sequence_returned
            and action_count_matches
            and sequence_row_counts.get(sid) == 1
            and coverage_row_counts.get(sid) == 1
        )
        if not sequence_returned:
            missing_sequence_ids.append(sid)
        if sequence_returned and not action_count_matches:
            action_count_mismatch_ids.append(sid)
        coverage.append({
            "sequence_id": sid,
            "reviewed": bool(r and r.get("reviewed") is True),
            "target_seen": bool(r and r.get("target_seen") is True),
            "actions_found": reported_actions,
            "raw_actions": raw_actions,
            "normalised_actions": actual_actions,
            "sequence_returned": sequence_returned,
            "sequence_rows": sequence_row_counts.get(sid, 0),
            "coverage_rows": coverage_row_counts.get(sid, 0),
            "contract_complete": contract_complete,
        })
    incomplete_sequence_ids = [r["sequence_id"] for r in coverage if not r["contract_complete"]]
    complete = bool(windows) and not incomplete_sequence_ids
    actions_total = sum(len(s["actions"]) for s in sequences)
    return {
        "version": VERSION,
        "status": "ok" if sequences or complete else "incomplete",
        "global_target_id": GLOBAL_TARGET_ID,
        "timebase": "canonical_media_ms",
        "sequences": sequences,
        "coverage": coverage,
        "coverage_complete": complete,
        "metrics": {
            "planned_windows": len(windows),
            "returned_sequences": len(sequences),
            "actions_total": actions_total,
            "reviewed_windows": sum(1 for r in coverage if r["reviewed"]),
            "contract_complete_windows": sum(1 for r in coverage if r["contract_complete"]),
            "missing_sequence_windows": len(missing_sequence_ids),
            "action_count_mismatches": len(action_count_mismatch_ids),
        },
        "incomplete_sequence_ids": incomplete_sequence_ids,
        "missing_sequence_ids": missing_sequence_ids,
        "action_count_mismatch_ids": action_count_mismatch_ids,
    }


def subset_sequence_plan(plan: dict | None, sequence_ids) -> dict:
    """Return a prompt-safe retry plan for only incomplete original windows.

    IDs and canonical boundaries are copied from the original plan; this helper
    cannot create new windows or move an existing one across a scene cut.
    """
    src = plan if isinstance(plan, dict) else {}
    wanted = {str(x) for x in (sequence_ids or []) if isinstance(x, str) and x}
    analysis = [
        deepcopy(w) for w in (src.get("analysis_windows") or [])
        if isinstance(w, dict) and str(w.get("sequence_id")) in wanted
    ]
    kept_ids = {w.get("sequence_id") for w in analysis}
    refinement = []
    for r in src.get("refinement_windows") or []:
        if not isinstance(r, dict):
            continue
        linked = [sid for sid in (r.get("sequence_ids") or []) if sid in kept_ids]
        if not linked:
            continue
        row = deepcopy(r)
        row["sequence_ids"] = linked
        refinement.append(row)
    return {
        "version": src.get("version") or VERSION,
        "status": "ok" if analysis else "empty",
        "global_target_id": src.get("global_target_id") or GLOBAL_TARGET_ID,
        "timebase": src.get("timebase") or "canonical_media_ms",
        "analysis_windows": analysis,
        "refinement_windows": refinement,
        "metrics": {
            "analysis_windows": len(analysis),
            "refinement_windows": len(refinement),
            "retry_subset": True,
        },
    }


def merge_raw_sequence_results(results) -> dict:
    """Merge bounded model attempts atomically by sequence_id, latest wins.

    A retry is allowed to replace an incomplete first row for the same window,
    while unrelated already-complete windows stay intact. Unknown top-level
    fields are deliberately ignored so prose/model metadata never becomes
    analysis authority. The sequence and coverage rows for a touched window are
    one contract unit: a later attempt cannot combine its new sequence row with
    stale coverage (or vice versa) from an earlier attempt.
    """
    sequences = {}
    coverage = {}
    attempts = 0
    for raw in results or []:
        if not isinstance(raw, dict):
            continue
        attempts += 1
        attempt_sequences = {}
        for row in raw.get("sequences") or []:
            if isinstance(row, dict) and isinstance(row.get("sequence_id"), str):
                attempt_sequences.setdefault(row["sequence_id"], []).append(deepcopy(row))
        attempt_coverage = {}
        for row in raw.get("coverage") or []:
            if isinstance(row, dict) and isinstance(row.get("sequence_id"), str):
                attempt_coverage.setdefault(row["sequence_id"], []).append(deepcopy(row))
        touched = list(dict.fromkeys([*attempt_sequences, *attempt_coverage]))
        for sid in touched:
            # Duplicate rows inside one attempt stay visible to the strict
            # normaliser. A missing counterpart is deliberately removed so it
            # cannot be inherited from an older attempt and falsely complete
            # the per-window coverage contract.
            if sid in attempt_sequences:
                sequences[sid] = attempt_sequences[sid]
            else:
                sequences.pop(sid, None)
            if sid in attempt_coverage:
                coverage[sid] = attempt_coverage[sid]
            else:
                coverage.pop(sid, None)
    return {
        "sequences": [row for rows in sequences.values() for row in rows],
        "coverage": [row for rows in coverage.values() for row in rows],
        "attempts": attempts,
    }
