"""FIX 09B.3 — canonical target-event resolution.

Consumes the normalised FIX09B.2 sequence observations together with the
FIX09B.1 scene graph and FIX09B.0 GLOBAL_TARGET authority.  It decides which
observations are safe target-player facts and emits ONE canonical event truth
for downstream stats, report text, proof, snapshot and renderer layers.

This is deliberately stricter than discovery but less brittle than legacy
single-frame actor gating:

    FIND (B.2) → multi-frame actor resolution (B.3) → causal resolution (B.3)
               → canonical event or explicit unresolved/rejected observation.

Identity may be resolved from visible evidence at the action OR from bounded
same-track continuity before/after an occluded instant.  Football behaviour is
never identity evidence.  No geometry is invented at an occluded contact.
"""
from __future__ import annotations

import hashlib
import math
from copy import deepcopy

import unified_identity_authority as uia

VERSION = 1
GLOBAL_TARGET_ID = "GLOBAL_TARGET"

GRAPH_NEAR_MS = 300
CONTINUITY_SIDE_MS = 1800
CONTACT_NEAR_MS = 450
BOX_IOU_MIN = 0.18
BOX_CENTER_H = 0.75
DUP_CONTACT_MS = 450
DUP_EDGE_MS = 700

CONTACT_ACTIONS = {
    "RECEIVE", "FIRST_TOUCH", "CONTROL", "PASS", "CROSS", "KEY_PASS", "SHOT",
    "TACKLE", "INTERCEPTION", "RECOVERY",
}
SCORING_PASS_ACTIONS = {"PASS", "CROSS", "KEY_PASS"}
MICRO_ACTIONS = {
    "CARRY", "DRIBBLE", "TAKE_ON", "FEINT", "TURN", "DIRECTION_CHANGE",
    "ACCELERATION", "DECELERATION", "DUEL", "PRESS", "RUN", "OFF_BALL_RUN",
    "SPACE_CREATION", "SCAN", "BODY_ORIENTATION", "SUPPORT", "OTHER",
}


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


def _iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = float(a["x"]), float(a["y"]), float(a["x"] + a["w"]), float(a["y"] + a["h"])
    bx0, by0, bx1, by1 = float(b["x"]), float(b["y"]), float(b["x"] + b["w"]), float(b["y"] + b["h"])
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    union = float(a["w"] * a["h"] + b["w"] * b["h"]) - inter
    return inter / union if union > 0 else 0.0


def _boxes_match(a, b) -> bool:
    if not (_valid_box(a) and _valid_box(b)):
        return False
    if _iou(a, b) >= BOX_IOU_MIN:
        return True
    ax, ay = _center(a); bx, by = _center(b)
    h = max(float(a["h"]), float(b["h"]), 1e-6)
    return math.hypot(ax - bx, ay - by) / h <= BOX_CENTER_H


def _event_id(scene_id, kind, canonical_ms, actor_id) -> str:
    raw = f"{scene_id}|{kind}|{int(canonical_ms)}|{actor_id or GLOBAL_TARGET_ID}".encode("utf-8")
    return "evt_" + hashlib.sha1(raw).hexdigest()[:16]


def _flatten_actions(sequence_analysis) -> list[dict]:
    rows = []
    for seq in (sequence_analysis or {}).get("sequences") or []:
        if not isinstance(seq, dict):
            continue
        sid, scene = seq.get("sequence_id"), seq.get("scene_id")
        for a in seq.get("actions") or []:
            if not isinstance(a, dict):
                continue
            row = deepcopy(a)
            row["sequence_id"] = sid
            row["scene_id"] = scene
            row["sequence_start_ms"] = seq.get("start_ms")
            row["sequence_end_ms"] = seq.get("end_ms")
            rows.append(row)
    return rows


def _frames_by_scene(scene_graph) -> dict[str, list[dict]]:
    out = {}
    for f in (scene_graph or {}).get("frames") or []:
        if not isinstance(f, dict) or not _num(f.get("media_ms")):
            continue
        sid = str(f.get("scene_id") or "scene_unknown")
        out.setdefault(sid, []).append(f)
    for rows in out.values():
        rows.sort(key=lambda f: int(f["media_ms"]))
    return out


def _near_frame(frames, ms, max_ms=GRAPH_NEAR_MS):
    if not frames or not _num(ms):
        return None
    target = int(round(float(ms)))
    best = min(frames, key=lambda f: abs(int(f["media_ms"]) - target))
    return best if abs(int(best["media_ms"]) - target) <= max_ms else None


def _player_by_id(frame, track_id):
    if not frame or not isinstance(track_id, str):
        return None
    for p in frame.get("players") or []:
        if isinstance(p, dict) and p.get("local_track_id") == track_id:
            return p
    return None


def _map_box_to_local(frame, box) -> tuple[str | None, bool]:
    """Map visible actor geometry to a scene-local body.

    Returns (best_id, ambiguous).  Geometry maps bodies; GLOBAL_TARGET identity
    is decided separately from the frame's canonical target mapping.
    """
    if not frame or not _valid_box(box):
        return None, False
    ranked = []
    for p in frame.get("players") or []:
        if not isinstance(p, dict) or not _valid_box(p.get("box")):
            continue
        pb = p["box"]
        ov = _iou(box, pb)
        ax, ay = _center(box); bx, by = _center(pb)
        dh = math.hypot(ax - bx, ay - by) / max(float(box["h"]), float(pb["h"]), 1e-6)
        if ov >= BOX_IOU_MIN or dh <= BOX_CENTER_H:
            ranked.append((1.8 * ov + max(0.0, 1.0 - dh / BOX_CENTER_H), p.get("local_track_id")))
    ranked.sort(reverse=True, key=lambda x: x[0])
    if not ranked:
        return None, False
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.16:
        return None, True
    return ranked[0][1], False


def _target_map(frame) -> dict:
    return (frame or {}).get("global_target") or {}


def _target_ids(frame) -> set[str]:
    tm = _target_map(frame)
    ids = set()
    if isinstance(tm.get("local_track_id"), str):
        ids.add(tm["local_track_id"])
    for tid in tm.get("candidate_local_track_ids") or []:
        if isinstance(tid, str):
            ids.add(tid)
    return ids


def _verified_target_id(frame):
    tm = _target_map(frame)
    if tm.get("status") == "VERIFIED" and isinstance(tm.get("local_track_id"), str):
        return tm["local_track_id"]
    return None


def _action_evidence_samples(action, scene_frames) -> list[dict]:
    rows = []
    for e in action.get("actor_evidence") or []:
        if not isinstance(e, dict) or not _num(e.get("media_ms")) or not _valid_box(e.get("box")):
            continue
        fr = _near_frame(scene_frames, e["media_ms"])
        mapped, amb = _map_box_to_local(fr, e["box"])
        rows.append({
            "media_ms": int(e["media_ms"]), "visibility": e.get("visibility"),
            "box": deepcopy(e["box"]), "graph_frame_ms": int(fr["media_ms"]) if fr else None,
            "mapped_local_track_id": mapped, "mapping_ambiguous": amb,
            "verified_target_id": _verified_target_id(fr),
            "target_candidate_ids": sorted(_target_ids(fr)),
        })
    # actor_box/contact_ms is another visible mapping source when the model
    # explicitly supplied it and contact itself was not marked occluded.
    if (_valid_box(action.get("actor_box")) and _num(action.get("contact_ms"))
            and action.get("contact_visibility") != "OCCLUDED"):
        ms = int(action["contact_ms"])
        fr = _near_frame(scene_frames, ms)
        mapped, amb = _map_box_to_local(fr, action["actor_box"])
        rows.append({
            "media_ms": ms, "visibility": action.get("contact_visibility"),
            "box": deepcopy(action["actor_box"]), "graph_frame_ms": int(fr["media_ms"]) if fr else None,
            "mapped_local_track_id": mapped, "mapping_ambiguous": amb,
            "verified_target_id": _verified_target_id(fr),
            "target_candidate_ids": sorted(_target_ids(fr)),
        })
    return rows


def _actor_candidates(action, samples) -> list[str]:
    ids = []
    aid = action.get("actor_local_track_id")
    if isinstance(aid, str) and aid:
        ids.append(aid)
    for tid in action.get("actor_candidate_local_track_ids") or []:
        if isinstance(tid, str) and tid and tid not in ids:
            ids.append(tid)
    mapped = [s.get("mapped_local_track_id") for s in samples if s.get("mapped_local_track_id")]
    if mapped:
        # Visible geometry outranks a model-emitted id only when it maps
        # unambiguously. Keep all bounded possibilities for later continuity.
        for tid in mapped:
            if tid not in ids:
                ids.append(tid)
    return ids[:8]


def _verified_frames_for_track(scene_frames, track_id, lo, hi):
    return [
        f for f in scene_frames
        if lo <= int(f["media_ms"]) <= hi and _verified_target_id(f) == track_id
    ]


def _competing_verified_frames(scene_frames, track_id, lo, hi):
    return [
        f for f in scene_frames
        if lo <= int(f["media_ms"]) <= hi
        and _verified_target_id(f) is not None and _verified_target_id(f) != track_id
    ]


def _resolve_actor(action, scene_frames, unified_authority) -> dict:
    """Resolve target actor from multi-frame physical evidence, never behaviour."""
    start, end = int(action["start_ms"]), int(action["end_ms"])
    pivot = int(action.get("contact_ms") if _num(action.get("contact_ms")) else (start + end) // 2)
    samples = _action_evidence_samples(action, scene_frames)
    candidates = _actor_candidates(action, samples)

    # Strong contradiction: visible actor maps to a body while canonical graph
    # simultaneously verifies GLOBAL_TARGET as a different body.
    contradictions = []
    exact_support = {}
    for s in samples:
        mid, vid = s.get("mapped_local_track_id"), s.get("verified_target_id")
        if mid and vid and mid != vid:
            contradictions.append((s["media_ms"], mid, vid))
        if mid and vid and mid == vid:
            exact_support.setdefault(mid, []).append(s)

    if contradictions and not exact_support:
        return {
            "status": "REJECTED", "reason": "OTHER_PLAYER_VISIBLE_AT_ACTION",
            "actor_local_track_id": None, "samples": samples,
            "candidate_local_track_ids": candidates, "proof_eligible": False,
        }

    if len(exact_support) == 1:
        tid = next(iter(exact_support))
        if not _competing_verified_frames(scene_frames, tid, start, end):
            return {
                "status": "VERIFIED", "reason": "VISIBLE_TARGET_MATCH",
                "actor_local_track_id": tid, "samples": samples,
                "candidate_local_track_ids": [tid], "proof_eligible": True,
            }

    # If model id and all unambiguous visible mappings agree, continuity may
    # bridge an occluded contact. Require GLOBAL_TARGET verified on BOTH sides
    # of the action on that same local track and no competing verified target
    # inside the bounded bridge.
    plausible = []
    for tid in candidates:
        mapped_other = {
            s["mapped_local_track_id"] for s in samples
            if s.get("mapped_local_track_id") and not s.get("mapping_ambiguous")
            and s["mapped_local_track_id"] != tid
        }
        if mapped_other:
            continue
        before = [f for f in _verified_frames_for_track(
            scene_frames, tid, max(0, start - CONTINUITY_SIDE_MS), pivot)
                  if int(f["media_ms"]) <= pivot]
        after = [f for f in _verified_frames_for_track(
            scene_frames, tid, pivot, end + CONTINUITY_SIDE_MS)
                 if int(f["media_ms"]) >= pivot]
        if before and after:
            bridge_lo = int(before[-1]["media_ms"])
            bridge_hi = int(after[0]["media_ms"])
            if not _competing_verified_frames(scene_frames, tid, bridge_lo, bridge_hi):
                plausible.append((tid, bridge_lo, bridge_hi))
    if len(plausible) == 1:
        tid, a, b = plausible[0]
        return {
            "status": "VERIFIED", "reason": "BOUNDED_FORWARD_BACKWARD_CONTINUITY",
            "actor_local_track_id": tid, "samples": samples,
            "candidate_local_track_ids": [tid], "proof_eligible": True,
            "continuity_ms": [a, b],
        }

    # Unified identity geometry can still disprove a visible actor box even
    # when the scene-local graph happened to miss a mapping at that sample.
    if isinstance(unified_authority, dict):
        for s in samples:
            target, why = uia.resolve_target_at(
                unified_authority, int(s["media_ms"]), proof_required=True,
                max_interp_ms=CONTACT_NEAR_MS)
            if target and _valid_box(target.get("box")) and _valid_box(s.get("box")):
                if _boxes_match(target["box"], s["box"]):
                    # Geometry confirms GLOBAL_TARGET, but if local-track id is
                    # unknown keep the canonical actor as GLOBAL_TARGET rather
                    # than fabricate a scene-local id.
                    return {
                        "status": "VERIFIED", "reason": "UNIFIED_TARGET_GEOMETRY_MATCH",
                        "actor_local_track_id": candidates[0] if len(candidates) == 1 else None,
                        "samples": samples, "candidate_local_track_ids": candidates,
                        "proof_eligible": True,
                    }
                if why in ("OK_EXACT", "OK_INTERPOLATED"):
                    return {
                        "status": "REJECTED", "reason": "UNIFIED_TARGET_GEOMETRY_MISMATCH",
                        "actor_local_track_id": None, "samples": samples,
                        "candidate_local_track_ids": candidates, "proof_eligible": False,
                    }

    return {
        "status": "UNRESOLVED", "reason": "INSUFFICIENT_PHYSICAL_IDENTITY_EVIDENCE",
        "actor_local_track_id": None, "samples": samples,
        "candidate_local_track_ids": candidates, "proof_eligible": False,
    }


def _causal_resolution(action) -> dict:
    """Classify outcome only from the visible same-sequence causal chain."""
    kind = str(action.get("kind") or "OTHER")
    outcome = str(action.get("outcome") or "UNKNOWN")
    chain = action.get("causal_chain") if isinstance(action.get("causal_chain"), dict) else {}
    contact = action.get("contact_ms") if _num(action.get("contact_ms")) else None

    if kind == "SHOT" and outcome == "GOAL":
        goal_ms = chain.get("goal_outcome_ms")
        target_contact = chain.get("target_contact_ms") or contact
        ok = (
            _num(target_contact) and _num(goal_ms)
            and int(target_contact) <= int(goal_ms)
            and action.get("outcome_visible") is True
            and chain.get("continuous_visible_sequence") is True
        )
        return {
            "canonical_event_type": "GOAL" if ok else "SHOT",
            "canonical_action_type": "SHOT",
            "canonical_outcome": "GOAL" if ok else "UNKNOWN",
            "causal_verified": bool(ok),
            "reason": "VISIBLE_TARGET_SHOT_TO_GOAL" if ok else "GOAL_CHAIN_INCOMPLETE",
        }

    if kind in SCORING_PASS_ACTIONS and outcome == "TEAMMATE_GOAL":
        vals = [chain.get("target_contact_ms") or contact, chain.get("receiver_ms"),
                chain.get("teammate_shot_ms"), chain.get("goal_outcome_ms")]
        ordered = all(_num(x) for x in vals) and all(int(a) <= int(b) for a, b in zip(vals, vals[1:]))
        receiver = chain.get("receiver_local_track_id")
        actor = action.get("actor_local_track_id")
        different_receiver = isinstance(receiver, str) and (not actor or receiver != actor)
        ok = (ordered and different_receiver and action.get("outcome_visible") is True
              and chain.get("continuous_visible_sequence") is True)
        return {
            "canonical_event_type": "ASSIST" if ok else kind,
            "canonical_action_type": kind,
            "canonical_outcome": "TEAMMATE_GOAL" if ok else "UNKNOWN",
            "causal_verified": bool(ok),
            "reason": "VISIBLE_CONTINUOUS_ASSIST_CHAIN" if ok else "ASSIST_CHAIN_INCOMPLETE",
        }

    if kind == "SHOT":
        valid_outcome = outcome if outcome in {"SAVED", "BLOCKED", "OFF_TARGET"} and action.get("outcome_visible") else "UNKNOWN"
        return {
            "canonical_event_type": "SHOT", "canonical_action_type": "SHOT",
            "canonical_outcome": valid_outcome,
            "causal_verified": valid_outcome != "UNKNOWN",
            "reason": "VISIBLE_SHOT_OUTCOME" if valid_outcome != "UNKNOWN" else "SHOT_OUTCOME_UNVERIFIED",
        }

    if kind in SCORING_PASS_ACTIONS:
        normal = outcome if outcome in {"COMPLETED", "INCOMPLETE", "TEAMMATE_SHOT"} else "UNKNOWN"
        return {
            "canonical_event_type": kind, "canonical_action_type": kind,
            "canonical_outcome": normal, "causal_verified": normal != "UNKNOWN",
            "reason": "VISIBLE_PASS_OUTCOME" if normal != "UNKNOWN" else "PASS_OUTCOME_UNVERIFIED",
        }

    return {
        "canonical_event_type": kind,
        "canonical_action_type": kind,
        "canonical_outcome": outcome if action.get("outcome_visible") else (outcome if outcome in {"COMPLETED", "INCOMPLETE", "WON", "LOST"} else "UNKNOWN"),
        "causal_verified": True,
        "reason": "TARGET_ACTION_VERIFIED",
    }


def _proof_payload(action, actor_resolution, causal) -> dict:
    start, end = int(action["start_ms"]), int(action["end_ms"])
    seq_start = int(action.get("sequence_start_ms") or start)
    seq_end = int(action.get("sequence_end_ms") or end)
    evidence = sorted({int(x) for x in action.get("evidence_ms") or [] if _num(x)})
    evidence.extend(
        int(s["media_ms"]) for s in actor_resolution.get("samples") or []
        if _num(s.get("media_ms")) and int(s["media_ms"]) not in evidence
    )
    chain = action.get("causal_chain") or {}
    for k in ("target_contact_ms", "receiver_ms", "teammate_shot_ms", "goal_outcome_ms"):
        if _num(chain.get(k)):
            evidence.append(int(chain[k]))
    evidence = sorted(set(evidence))
    visible_actor = [
        {"media_ms": int(s["media_ms"]), "box": deepcopy(s["box"]),
         "visibility": s.get("visibility")}
        for s in actor_resolution.get("samples") or []
        if _valid_box(s.get("box")) and s.get("visibility") != "OCCLUDED"
    ]
    contact_geom = None
    contact = action.get("contact_ms")
    if _num(contact) and action.get("contact_visibility") != "OCCLUDED":
        near = min(visible_actor, key=lambda r: abs(r["media_ms"] - int(contact)), default=None)
        if near and abs(near["media_ms"] - int(contact)) <= CONTACT_NEAR_MS:
            contact_geom = deepcopy(near)
    return {
        "proof_start_ms": seq_start,
        "proof_end_ms": seq_end,
        "evidence_ms": evidence[:40],
        "actor_keyframes": visible_actor[:20],
        "contact_geometry": contact_geom,
        "contact_visibility": action.get("contact_visibility") or "UNKNOWN",
        "outcome_ms": int(chain["goal_outcome_ms"]) if _num(chain.get("goal_outcome_ms")) else None,
        "proof_eligible": bool(actor_resolution.get("proof_eligible")),
        "causal_verified": bool(causal.get("causal_verified")),
    }


def _canonical_ms(action) -> int:
    if _num(action.get("contact_ms")):
        return int(action["contact_ms"])
    ev = [int(x) for x in action.get("evidence_ms") or [] if _num(x)]
    return ev[0] if ev else int((int(action["start_ms"]) + int(action["end_ms"])) / 2)


def _overlap_ratio(a, b) -> float:
    lo = max(int(a["start_ms"]), int(b["start_ms"])); hi = min(int(a["end_ms"]), int(b["end_ms"]))
    inter = max(0, hi - lo)
    den = max(1, min(int(a["end_ms"]) - int(a["start_ms"]), int(b["end_ms"]) - int(b["start_ms"])))
    return inter / den


def _same_real_action(a, b) -> bool:
    if a.get("canonical_action_type") != b.get("canonical_action_type"):
        return False
    if a.get("scene_id") != b.get("scene_id"):
        return False
    ac, bc = a.get("contact_ms"), b.get("contact_ms")
    if _num(ac) and _num(bc):
        return abs(int(ac) - int(bc)) <= DUP_CONTACT_MS
    return (_overlap_ratio(a, b) >= 0.65
            and abs(int(a["start_ms"]) - int(b["start_ms"])) <= DUP_EDGE_MS
            and abs(int(a["end_ms"]) - int(b["end_ms"])) <= DUP_EDGE_MS)


def _merge_event(dst, src):
    """Merge overlapping-window observations without inventing stronger facts."""
    dst["source_action_ids"] = sorted(set(dst.get("source_action_ids") or []) | set(src.get("source_action_ids") or []))
    dst["source_sequence_ids"] = sorted(set(dst.get("source_sequence_ids") or []) | set(src.get("source_sequence_ids") or []))
    dst["details"] = list(dict.fromkeys((dst.get("details") or []) + (src.get("details") or [])))[:30]
    dproof, sproof = dst.get("proof") or {}, src.get("proof") or {}
    dproof["evidence_ms"] = sorted(set(dproof.get("evidence_ms") or []) | set(sproof.get("evidence_ms") or []))[:40]
    seen = {(r.get("media_ms"), str(r.get("box"))) for r in dproof.get("actor_keyframes") or []}
    for r in sproof.get("actor_keyframes") or []:
        key = (r.get("media_ms"), str(r.get("box")))
        if key not in seen:
            dproof.setdefault("actor_keyframes", []).append(r); seen.add(key)
    dproof["actor_keyframes"] = sorted(dproof.get("actor_keyframes") or [], key=lambda r: r.get("media_ms", 0))[:20]
    # Never upgrade a weaker duplicate into GOAL/ASSIST unless that duplicate
    # itself has verified causal evidence. Prefer the causally stronger row.
    if src.get("causal_verified") and not dst.get("causal_verified"):
        for k in ("canonical_event_type", "canonical_outcome", "causal_verified", "resolution_reason"):
            dst[k] = src.get(k)
        dproof["causal_verified"] = True
    dst["proof"] = dproof
    return dst


def resolve_canonical_events(sequence_analysis: dict | None, scene_graph: dict | None,
                             unified_authority: dict | None) -> dict:
    """Resolve B.2 observations into canonical target events.

    Accepted events are the ONLY rows intended for FIX09C/output authority.
    Unresolved rows are retained for diagnostics/refinement; rejected rows are
    explicit wrong-actor/malformed duplicates and never enter stats/report.
    """
    sa = sequence_analysis if isinstance(sequence_analysis, dict) else {}
    sg = scene_graph if isinstance(scene_graph, dict) else {}
    by_scene = _frames_by_scene(sg)
    accepted, unresolved, rejected = [], [], []

    for action in _flatten_actions(sa):
        scene = str(action.get("scene_id") or "scene_unknown")
        scene_frames = by_scene.get(scene) or []
        actor = _resolve_actor(action, scene_frames, unified_authority or {})
        base_diag = {
            "action_id": action.get("action_id"), "sequence_id": action.get("sequence_id"),
            "scene_id": scene, "kind": action.get("kind"),
            "start_ms": action.get("start_ms"), "contact_ms": action.get("contact_ms"),
            "end_ms": action.get("end_ms"), "actor_resolution": actor,
        }
        if action.get("duplicate_of"):
            base_diag["reason"] = "EXPLICIT_REPLAY_OR_DUPLICATE"
            rejected.append(base_diag)
            continue
        if actor["status"] == "REJECTED":
            base_diag["reason"] = actor["reason"]
            rejected.append(base_diag)
            continue
        if actor["status"] != "VERIFIED":
            base_diag["reason"] = actor["reason"]
            unresolved.append(base_diag)
            continue

        # Use the resolved actor in causal receiver-vs-actor checks. The source
        # normalised action remains untouched.
        action_for_causal = deepcopy(action)
        action_for_causal["actor_local_track_id"] = actor.get("actor_local_track_id")
        causal = _causal_resolution(action_for_causal)
        cms = _canonical_ms(action)
        proof = _proof_payload(action, actor, causal)
        event = {
            "event_id": _event_id(scene, causal["canonical_action_type"], cms,
                                  actor.get("actor_local_track_id")),
            "global_target_id": GLOBAL_TARGET_ID,
            "scene_id": scene,
            "sequence_id": action.get("sequence_id"),
            "source_sequence_ids": [action.get("sequence_id")] if action.get("sequence_id") else [],
            "source_action_ids": [action.get("action_id")] if action.get("action_id") else [],
            "start_ms": int(action["start_ms"]),
            "contact_ms": int(action["contact_ms"]) if _num(action.get("contact_ms")) else None,
            "end_ms": int(action["end_ms"]),
            "canonical_ms": cms,
            "canonical_event_type": causal["canonical_event_type"],
            "canonical_action_type": causal["canonical_action_type"],
            "canonical_outcome": causal["canonical_outcome"],
            "causal_verified": causal["causal_verified"],
            "resolution_reason": causal["reason"],
            "actor_local_track_id": actor.get("actor_local_track_id"),
            "identity_resolution": actor.get("reason"),
            "foot": action.get("foot") or "UNKNOWN",
            "pressure": deepcopy(action.get("pressure") or {}),
            "details": deepcopy(action.get("details") or []),
            "proof": proof,
            "causal_chain": deepcopy(action.get("causal_chain") or {}),
        }

        # Scoring claims fail closed to the underlying target action, not to
        # deletion. A visible target pass with incomplete goal chain remains a
        # PASS; a visible target shot with incomplete goal chain remains SHOT.
        accepted.append(event)

    # Overlapping broad windows intentionally see the same real action. Merge
    # duplicates AFTER actor/causal verification so recall does not create
    # duplicate stats.
    deduped = []
    for e in sorted(accepted, key=lambda x: (x["scene_id"], x["canonical_ms"], x["canonical_action_type"])):
        match = next((d for d in deduped if _same_real_action(d, e)), None)
        if match is None:
            deduped.append(e)
        else:
            _merge_event(match, e)
            rejected.append({
                "action_id": (e.get("source_action_ids") or [None])[0],
                "sequence_id": e.get("sequence_id"), "scene_id": e.get("scene_id"),
                "kind": e.get("canonical_action_type"), "reason": "OVERLAPPING_WINDOW_DUPLICATE",
                "duplicate_event_id": match.get("event_id"),
            })

    counts = {}
    for e in deduped:
        counts[e["canonical_event_type"]] = counts.get(e["canonical_event_type"], 0) + 1
    return {
        "version": VERSION,
        "status": "ok" if deduped else ("unresolved" if unresolved else "empty"),
        "global_target_id": GLOBAL_TARGET_ID,
        "timebase": "canonical_media_ms",
        "events": deduped,
        "unresolved": unresolved,
        "rejected": rejected,
        "counts": counts,
        "metrics": {
            "observations_total": len(_flatten_actions(sa)),
            "events_accepted": len(deduped),
            "observations_unresolved": len(unresolved),
            "observations_rejected": len(rejected),
            "goals": counts.get("GOAL", 0),
            "assists": counts.get("ASSIST", 0),
            "shots": counts.get("SHOT", 0) + counts.get("GOAL", 0),
        },
    }
