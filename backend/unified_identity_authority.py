"""FIX 09B.0 — Unified GLOBAL_TARGET identity authority.

Pure deterministic fusion layer that turns the existing FIX04 local tap-seeded
track and FIX09A global identity timeline into ONE canonical target authority.

The module deliberately does not detect players, call models, or understand
football events. It only reconciles identity evidence already produced by the
existing pipeline.

Design contract
---------------
* FIX00A user taps remain absolute identity authority inside a bounded tap
  window. A later tracker/timeline disagreement may never override a tap.
* FIX04 is trusted LOCAL geometry/evidence, not whole-video identity truth.
* FIX09A supplies scene-aware GLOBAL_TARGET identity and cut/re-ID semantics.
* Agreement strengthens identity. Disagreement outside tap authority becomes
  explicit UNRESOLVED hypotheses; boxes are never averaged between two bodies.
* Predicted/occluded geometry is continuity evidence only and is never
  proof-eligible.
* Inputs are never mutated.
* All time is canonical media milliseconds.

This is the identity spine consumed by later FIX09B stages. It intentionally
keeps a compatibility adapter (`to_production_track`) so existing deterministic
movement/event/evidence code can migrate to the same authority incrementally.
"""
from __future__ import annotations

from copy import deepcopy

VERSION = 1
GLOBAL_TARGET_ID = "GLOBAL_TARGET"

FUSE_TOL_MS = 140
TAP_AUTHORITY_MS = 650
AGREE_IOU_MIN = 0.18
AGREE_CENTER_H = 0.70
MAX_RESOLVE_INTERP_MS = 500
PRODUCTION_SEGMENT_GAP_S = 0.35


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _valid_box(b) -> bool:
    if not isinstance(b, dict):
        return False
    try:
        x, y, w, h = (float(b[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return False
    return 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and 0.0 < w <= 1.0 and 0.0 < h <= 1.0


def _box(b):
    return {k: float(b[k]) for k in ("x", "y", "w", "h")}


def _iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]
    bx0, by0, bx1, by1 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


def _centers_agree(a, b) -> bool:
    acx, acy = a["x"] + a["w"] / 2.0, a["y"] + a["h"] / 2.0
    bcx, bcy = b["x"] + b["w"] / 2.0, b["y"] + b["h"] / 2.0
    ref_h = max(a["h"], b["h"], 1e-6)
    return ((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5 <= AGREE_CENTER_H * ref_h


def boxes_agree(a, b) -> bool:
    """Timestamp-near identity geometry agreement, never an identity decision alone."""
    if not (_valid_box(a) and _valid_box(b)):
        return False
    aa, bb = _box(a), _box(b)
    return _iou(aa, bb) >= AGREE_IOU_MIN or _centers_agree(aa, bb)


def _scene_for_ms(scenes, ms):
    for s in scenes or []:
        if not isinstance(s, dict):
            continue
        a, b = s.get("start_ms"), s.get("end_ms")
        if _is_num(a) and _is_num(b) and int(a) <= ms <= int(b):
            return s.get("scene_id")
    return None


def _tap_times(anchors, anchor_time_offset) -> list[int]:
    out = []
    off = float(anchor_time_offset or 0.0)
    for a in anchors or []:
        if isinstance(a, dict) and _is_num(a.get("t")):
            out.append(int(round((float(a["t"]) + off) * 1000.0)))
    return sorted(set(out))


def _near_tap(ms, taps) -> bool:
    return any(abs(ms - t) <= TAP_AUTHORITY_MS for t in taps)


def _timeline_rows(identity_timeline) -> list[dict]:
    rows = []
    tl = identity_timeline if isinstance(identity_timeline, dict) else {}
    for p in tl.get("target_points") or []:
        if not isinstance(p, dict) or not _is_num(p.get("media_ms")) or not _valid_box(p.get("box")):
            continue
        rows.append({
            "media_ms": int(round(float(p["media_ms"]))),
            "scene_id": p.get("scene_id"),
            "box": _box(p["box"]),
            "state": str(p.get("state") or "VISIBLE"),
            "predicted": p.get("predicted") is True,
            "proof_eligible": p.get("proof_eligible") is True and p.get("predicted") is not True,
            "identity_score": p.get("identity_score") if _is_num(p.get("identity_score")) else None,
            "local_track_id": p.get("local_track_id"),
            "geometry_source": p.get("geometry_source"),
        })
    return sorted(rows, key=lambda r: r["media_ms"])


def _fix04_rows(fix04_track, scenes) -> list[dict]:
    rows = []
    tr = fix04_track if isinstance(fix04_track, dict) else {}
    for p in tr.get("points") or []:
        if not isinstance(p, dict) or not _is_num(p.get("t")):
            continue
        b = {k: p.get(k) for k in ("x", "y", "w", "h")}
        if not _valid_box(b):
            continue
        ms = int(round(float(p["t"]) * 1000.0))
        rows.append({
            "media_ms": ms,
            "scene_id": _scene_for_ms(scenes, ms),
            "box": _box(b),
            "conf": float(p["conf"]) if _is_num(p.get("conf")) else None,
        })
    return sorted(rows, key=lambda r: r["media_ms"])


def _nearest(rows, ms, tol_ms=FUSE_TOL_MS):
    best = None
    best_d = None
    for r in rows:
        d = abs(r["media_ms"] - ms)
        if d <= tol_ms and (best_d is None or d < best_d):
            best, best_d = r, d
        if r["media_ms"] > ms + tol_ms:
            break
    return best


def _hyp(source, row):
    if not row:
        return None
    h = {"source": source, "media_ms": int(row["media_ms"]), "box": deepcopy(row["box"])}
    if source == "FIX09A":
        h.update({"scene_id": row.get("scene_id"), "state": row.get("state"),
                  "identity_score": row.get("identity_score"),
                  "local_track_id": row.get("local_track_id")})
    else:
        h["conf"] = row.get("conf")
    return h


def _canonical(source, row, *, strength, sources, tap_authority=False,
               proof_eligible=True, hypotheses=None, reason=None):
    state = "PINNED" if tap_authority else (row.get("state") or "VISIBLE")
    if row.get("predicted"):
        state = "OCCLUDED"
    return {
        "media_ms": int(row["media_ms"]),
        "scene_id": row.get("scene_id"),
        "global_target_id": GLOBAL_TARGET_ID,
        "box": deepcopy(row.get("box")) if _valid_box(row.get("box")) else None,
        "state": state,
        "identity_strength": strength,
        "sources": list(sources),
        "primary_source": source,
        "predicted": row.get("predicted") is True,
        "proof_eligible": bool(proof_eligible and not row.get("predicted")),
        "tap_authority": bool(tap_authority),
        "reason": reason,
        "hypotheses": [h for h in (hypotheses or []) if h],
    }


def _unresolved(ms, scene_id, hypotheses, reason="SOURCE_CONFLICT"):
    return {
        "media_ms": int(ms),
        "scene_id": scene_id,
        "global_target_id": GLOBAL_TARGET_ID,
        "box": None,
        "state": "UNRESOLVED",
        "identity_strength": "UNRESOLVED",
        "sources": sorted({h["source"] for h in hypotheses if h}),
        "primary_source": None,
        "predicted": False,
        "proof_eligible": False,
        "tap_authority": False,
        "reason": reason,
        "hypotheses": [h for h in hypotheses if h],
    }


def _dedupe_points(points):
    """Keep the strongest canonical row when two rows land on the same media ms."""
    rank = {"PINNED": 6, "FUSED": 5, "GLOBAL": 4, "LOCAL": 3,
            "PREDICTED": 2, "UNRESOLVED": 1}
    by_ms = {}
    for p in points:
        ms = p["media_ms"]
        old = by_ms.get(ms)
        if old is None or rank.get(p.get("identity_strength"), 0) > rank.get(old.get("identity_strength"), 0):
            by_ms[ms] = p
        elif old and old.get("state") == "UNRESOLVED" and p.get("state") == "UNRESOLVED":
            old_h = {(h["source"], h["media_ms"]) for h in old.get("hypotheses") or []}
            for h in p.get("hypotheses") or []:
                if (h["source"], h["media_ms"]) not in old_h:
                    old["hypotheses"].append(h)
    return [by_ms[k] for k in sorted(by_ms)]


def _merge_conflict_intervals(points):
    rows = [p for p in points if p.get("state") == "UNRESOLVED"]
    if not rows:
        return []
    out = []
    for p in rows:
        cur = {"scene_id": p.get("scene_id"), "start_ms": p["media_ms"],
               "end_ms": p["media_ms"], "reason": p.get("reason") or "SOURCE_CONFLICT"}
        last = out[-1] if out else None
        if (last and last["scene_id"] == cur["scene_id"] and last["reason"] == cur["reason"]
                and cur["start_ms"] - last["end_ms"] <= 2 * FUSE_TOL_MS):
            last["end_ms"] = cur["end_ms"]
        else:
            out.append(cur)
    return out


def build_unified_identity_authority(fix04_track=None, identity_timeline=None,
                                     anchors=None, anchor_time_offset=0.0,
                                     identity_profile=None) -> dict:
    """Build ONE production-facing GLOBAL_TARGET identity authority.

    No source may silently overrule another. A real disagreement outside the
    user's bounded tap window is retained as competing hypotheses and therefore
    not proof-eligible until a later FIX09B stage resolves it.
    """
    tl = identity_timeline if isinstance(identity_timeline, dict) else {}
    scenes = deepcopy(tl.get("scenes") or [])
    taps = _tap_times(anchors, anchor_time_offset)
    arows = _timeline_rows(tl)
    frows = _fix04_rows(fix04_track, scenes)
    points = []

    # FIX09A rows carry the whole-video scene-aware identity spine.
    for a in arows:
        f = _nearest(frows, a["media_ms"])
        near_pin = _near_tap(a["media_ms"], taps)
        if a["predicted"]:
            # Prediction remains useful continuity even if FIX04 is absent.
            points.append(_canonical(
                "FIX09A", a, strength="PREDICTED", sources=["FIX09A"],
                proof_eligible=False, hypotheses=[_hyp("FIX09A", a)],
                reason="OCCLUSION_CONTINUITY"))
            continue
        if f is None:
            points.append(_canonical(
                "FIX09A", a, strength="GLOBAL", sources=["FIX09A"],
                proof_eligible=a["proof_eligible"], hypotheses=[_hyp("FIX09A", a)]))
            continue
        if boxes_agree(a["box"], f["box"]):
            points.append(_canonical(
                "FIX09A", a, strength="FUSED", sources=["FIX09A", "FIX04"],
                proof_eligible=a["proof_eligible"],
                hypotheses=[_hyp("FIX09A", a), _hyp("FIX04", f)],
                reason="SOURCE_AGREEMENT"))
        elif near_pin:
            # At a user-confirmed instant FIX04 geometry wins only because it is
            # the tap-seeded local observation; the disagreement remains visible.
            ff = dict(f)
            ff["state"] = "PINNED"
            points.append(_canonical(
                "FIX04", ff, strength="PINNED", sources=["FIX04", "FIX09A"],
                tap_authority=True, proof_eligible=True,
                hypotheses=[_hyp("FIX04", f), _hyp("FIX09A", a)],
                reason="TAP_AUTHORITY_OVERRIDES_CONFLICT"))
        else:
            points.append(_unresolved(
                a["media_ms"], a.get("scene_id"),
                [_hyp("FIX09A", a), _hyp("FIX04", f)]))

    # Keep FIX04's denser local samples as trusted local evidence. They extend
    # event-contact geometry without pretending to provide whole-video identity.
    for f in frows:
        a = _nearest(arows, f["media_ms"])
        near_pin = _near_tap(f["media_ms"], taps)
        ff = dict(f)
        ff["state"] = "PINNED" if near_pin else "VISIBLE"
        if a is None:
            points.append(_canonical(
                "FIX04", ff, strength="PINNED" if near_pin else "LOCAL",
                sources=["FIX04"], tap_authority=near_pin, proof_eligible=True,
                hypotheses=[_hyp("FIX04", f)]))
        elif boxes_agree(f["box"], a["box"]):
            points.append(_canonical(
                "FIX04", ff, strength="PINNED" if near_pin else "FUSED",
                sources=["FIX04", "FIX09A"], tap_authority=near_pin,
                proof_eligible=True,
                hypotheses=[_hyp("FIX04", f), _hyp("FIX09A", a)],
                reason="SOURCE_AGREEMENT"))
        elif near_pin:
            points.append(_canonical(
                "FIX04", ff, strength="PINNED", sources=["FIX04", "FIX09A"],
                tap_authority=True, proof_eligible=True,
                hypotheses=[_hyp("FIX04", f), _hyp("FIX09A", a)],
                reason="TAP_AUTHORITY_OVERRIDES_CONFLICT"))
        else:
            points.append(_unresolved(
                f["media_ms"], f.get("scene_id"),
                [_hyp("FIX04", f), _hyp("FIX09A", a)]))

    points = _dedupe_points(points)
    accepted = [p for p in points if p.get("box") is not None and p.get("state") != "UNRESOLVED"]
    proof = [p for p in accepted if p.get("proof_eligible")]
    predicted = [p for p in accepted if p.get("predicted")]
    conflicts = [p for p in points if p.get("state") == "UNRESOLVED"]

    inherited_unresolved = deepcopy(tl.get("unresolved_intervals") or [])
    conflict_intervals = _merge_conflict_intervals(points)
    status = "ok" if accepted else ("unresolved" if conflicts else "empty")
    profile_summary = None
    if isinstance(identity_profile, dict):
        # Keep only structured analysis metadata needed by later identity stages;
        # this layer never converts prose traits into target geometry.
        profile_summary = {
            "same_player": identity_profile.get("same_player"),
            "confidence": identity_profile.get("confidence"),
            "description": identity_profile.get("description") or identity_profile.get("identity_description"),
            "jersey_number": identity_profile.get("jersey_number"),
        }

    return {
        "version": VERSION,
        "status": status,
        "global_target_id": GLOBAL_TARGET_ID,
        "timebase": "canonical_media_ms",
        "scenes": scenes,
        "target_points": points,
        "unresolved_intervals": inherited_unresolved + conflict_intervals,
        "tap_times_ms": taps,
        "identity_profile": profile_summary,
        "metrics": {
            "fix04_points": len(frows),
            "fix09a_points": len(arows),
            "canonical_points": len(points),
            "accepted_points": len(accepted),
            "proof_eligible_points": len(proof),
            "predicted_points": len(predicted),
            "conflict_points": len(conflicts),
            "fused_points": sum(1 for p in points if "FIX04" in p.get("sources", []) and "FIX09A" in p.get("sources", [])
                                and p.get("state") != "UNRESOLVED"),
            "pinned_points": sum(1 for p in points if p.get("tap_authority")),
        },
    }


def _same_scene(a, b) -> bool:
    sa, sb = a.get("scene_id"), b.get("scene_id")
    return sa is None or sb is None or sa == sb


def resolve_target_at(authority, media_ms: int, *, proof_required=False,
                      max_interp_ms=MAX_RESOLVE_INTERP_MS):
    """Resolve canonical target geometry at one media time.

    Returns ``(point_or_none, reason)``. Interpolation is allowed only between
    accepted points in the same scene, never across a source conflict, cut, or
    predicted geometry when proof is required.
    """
    if not isinstance(authority, dict) or not isinstance(media_ms, int):
        return None, "INVALID_INPUT"
    pts = [p for p in authority.get("target_points") or []
           if isinstance(p, dict) and isinstance(p.get("media_ms"), int)]
    if proof_required:
        pts = [p for p in pts if p.get("proof_eligible") and _valid_box(p.get("box"))]
    else:
        pts = [p for p in pts if p.get("state") != "UNRESOLVED" and _valid_box(p.get("box"))]
    if not pts:
        return None, "NO_TARGET_AUTHORITY"
    pts.sort(key=lambda p: p["media_ms"])
    exact = next((p for p in pts if p["media_ms"] == media_ms), None)
    if exact:
        return deepcopy(exact), "OK_EXACT"
    before = max((p for p in pts if p["media_ms"] < media_ms), key=lambda p: p["media_ms"], default=None)
    after = min((p for p in pts if p["media_ms"] > media_ms), key=lambda p: p["media_ms"], default=None)
    if before is None or after is None:
        return None, "TARGET_GAP"
    if not _same_scene(before, after):
        return None, "SCENE_CUT"
    if after["media_ms"] - before["media_ms"] > int(max_interp_ms):
        return None, "TARGET_GAP"
    # Never interpolate across an explicitly unresolved interval.
    for u in authority.get("unresolved_intervals") or []:
        if not isinstance(u, dict):
            continue
        a, b = u.get("start_ms"), u.get("end_ms")
        if _is_num(a) and _is_num(b) and int(a) <= media_ms <= int(b):
            return None, "UNRESOLVED_IDENTITY"
    f = (media_ms - before["media_ms"]) / max(1, after["media_ms"] - before["media_ms"])
    bb, ab = before["box"], after["box"]
    box = {k: float(bb[k]) + (float(ab[k]) - float(bb[k])) * f for k in ("x", "y", "w", "h")}
    out = {
        "media_ms": media_ms,
        "scene_id": before.get("scene_id") or after.get("scene_id"),
        "global_target_id": GLOBAL_TARGET_ID,
        "box": box,
        "state": "VISIBLE",
        "identity_strength": "INTERPOLATED",
        "sources": sorted(set(before.get("sources") or []) | set(after.get("sources") or [])),
        "primary_source": "UNIFIED",
        "predicted": True,
        "proof_eligible": False,
        "tap_authority": False,
        "reason": "BOUNDED_INTERPOLATION",
        "hypotheses": [],
    }
    return out, "OK_INTERPOLATED"


def to_production_track(authority) -> dict:
    """Compatibility adapter for existing FIX04-track consumers.

    Only accepted, non-predicted, proof-eligible canonical geometry is exported.
    Unresolved conflicts and occlusion predictions are intentionally omitted.
    """
    pts = []
    if isinstance(authority, dict):
        for p in authority.get("target_points") or []:
            if not (isinstance(p, dict) and p.get("proof_eligible") and not p.get("predicted")
                    and p.get("state") != "UNRESOLVED" and _valid_box(p.get("box"))):
                continue
            b = p["box"]
            pts.append({
                "t": round(p["media_ms"] / 1000.0, 3),
                "x": round(float(b["x"]), 4), "y": round(float(b["y"]), 4),
                "w": round(float(b["w"]), 4), "h": round(float(b["h"]), 4),
                "conf": 1.0 if p.get("tap_authority") else 0.9,
                "authority_source": p.get("identity_strength"),
                "scene_id": p.get("scene_id"),
            })
    # stable unique time rows, preserving strongest evidence on duplicate times
    best = {}
    rank = {"PINNED": 4, "FUSED": 3, "GLOBAL": 2, "LOCAL": 1}
    for p in pts:
        old = best.get(p["t"])
        if old is None or rank.get(p.get("authority_source"), 0) > rank.get(old.get("authority_source"), 0):
            best[p["t"]] = p
    out = [best[k] for k in sorted(best)]
    segments = []
    last_scene = None
    for p in out:
        scene = p.get("scene_id")
        if (segments and scene == last_scene
                and float(p["t"]) - float(segments[-1][1]) <= PRODUCTION_SEGMENT_GAP_S):
            segments[-1][1] = float(p["t"])
        else:
            segments.append([float(p["t"]), float(p["t"])])
        last_scene = scene
    segments = [
        [round(a, 3), round(b, 3)] for a, b in segments
        if b - a >= PRODUCTION_SEGMENT_GAP_S - 1e-9
    ]
    return {
        "version": "FIX09B.0",
        "global_target_id": GLOBAL_TARGET_ID,
        "authority": "UNIFIED_IDENTITY",
        "points": out,
        "segments": segments,
        "seed_count": len((authority or {}).get("tap_times_ms") or []) if isinstance(authority, dict) else 0,
    }
