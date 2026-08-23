"""FIX 09B.0 — bridge the unified GLOBAL_TARGET authority into FIX08 safely.

This module is deliberately small and deterministic. It does NOT discover
football events and it does NOT change FIX08 classification rules. Its job is
to adapt the unified FIX09B.0 identity authority to the legacy track-shaped
input still consumed by ``event_ledger`` while preserving identity uncertainty
and non-proof geometry as hard interpolation barriers.

Why a bridge is required
------------------------
FIX08's legacy ``resolve_target_box`` may interpolate across a short gap in a
track. Simply removing an UNRESOLVED or predicted unified point would therefore
be unsafe: a contact inside a same-kit conflict/occlusion could accidentally be
reconstructed from resolved points on either side. The bridge inserts
non-geometric barrier points, so current FIX08 fails closed there instead of
silently manufacturing proof geometry.

This is a migration adapter, not a second identity system. The only identity
truth is ``unified_identity_authority``.
"""
from __future__ import annotations

from copy import deepcopy

import unified_identity_authority as uia

VERSION = 1
BARRIER_REASON = "UNRESOLVED_IDENTITY"
NON_PROOF_REASON = "NON_PROOF_IDENTITY_GEOMETRY"


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _normalise_interval(row):
    if not isinstance(row, dict):
        return None
    a, b = row.get("start_ms"), row.get("end_ms")
    if not (_is_num(a) and _is_num(b)):
        return None
    a, b = int(round(float(a))), int(round(float(b)))
    if b < a:
        a, b = b, a
    return {
        "scene_id": row.get("scene_id"),
        "start_ms": max(0, a),
        "end_ms": max(0, b),
        "reason": str(row.get("reason") or BARRIER_REASON),
    }


def _merge_intervals(rows):
    """Merge only overlapping/touching intervals in the same scene."""
    src = []
    for row in rows or []:
        n = _normalise_interval(row)
        if n is not None:
            src.append(n)
    src.sort(key=lambda r: (r["start_ms"], r["end_ms"], str(r.get("scene_id"))))
    out = []
    for r in src:
        last = out[-1] if out else None
        if (last is not None
                and last.get("scene_id") == r.get("scene_id")
                and r["start_ms"] <= last["end_ms"] + 1):
            last["end_ms"] = max(last["end_ms"], r["end_ms"])
            if r["reason"] not in last["reasons"]:
                last["reasons"].append(r["reason"])
        else:
            out.append({
                "scene_id": r.get("scene_id"),
                "start_ms": r["start_ms"],
                "end_ms": r["end_ms"],
                "reasons": [r["reason"]],
            })
    return out


def _inside_interval(ms: int, interval: dict) -> bool:
    return interval["start_ms"] <= ms <= interval["end_ms"]


def _scene_compatible(point, interval) -> bool:
    ps = point.get("scene_id")
    us = interval.get("scene_id")
    return ps is None or us is None or ps == us


def _barrier_point(ms: int, scene_id, reasons, reason=BARRIER_REASON) -> dict:
    """A time-only point intentionally has no x/y/w/h and can never be proof."""
    return {
        "t": round(ms / 1000.0, 3),
        "scene_id": scene_id,
        "authority_source": "IDENTITY_BARRIER",
        "identity_barrier": True,
        "barrier_reason": reason,
        "barrier_reasons": list(reasons or [reason]),
        "proof_eligible": False,
    }


def _nonproof_barriers(authority):
    """Create exact-time barriers for predicted/non-proof canonical rows.

    This closes a subtle legacy hole: without the barrier, FIX08 could remove a
    predicted sample and then interpolate across its neighbours, converting
    continuity-only geometry into apparent contact proof.
    """
    out = []
    if not isinstance(authority, dict):
        return out
    for p in authority.get("target_points") or []:
        if not isinstance(p, dict) or not isinstance(p.get("media_ms"), int):
            continue
        if p.get("state") == "UNRESOLVED":
            continue  # covered by explicit conflict intervals
        if p.get("predicted") or not p.get("proof_eligible"):
            why = str(p.get("reason") or p.get("state") or NON_PROOF_REASON)
            out.append(_barrier_point(
                int(p["media_ms"]), p.get("scene_id"), [NON_PROOF_REASON, why],
                reason=NON_PROOF_REASON,
            ))
    return out


def build_safe_event_track(authority: dict | None) -> dict:
    """Return a legacy track-shaped view safe for current FIX08 actor gating.

    Guarantees:
    - only proof-eligible unified geometry is exported;
    - every geometry point inside an explicit unresolved interval is removed;
    - unresolved boundaries block interpolation through source conflicts;
    - predicted/non-proof canonical samples become exact-time barriers, so
      legacy interpolation cannot promote them to proof;
    - original authority is never mutated.
    """
    auth = authority if isinstance(authority, dict) else {}
    base = uia.to_production_track(auth)
    intervals = _merge_intervals(auth.get("unresolved_intervals") or [])

    kept = []
    for p in deepcopy(base.get("points") or []):
        if not isinstance(p, dict) or not _is_num(p.get("t")):
            continue
        ms = int(round(float(p["t"]) * 1000.0))
        if any(_scene_compatible(p, u) and _inside_interval(ms, u) for u in intervals):
            continue
        p["proof_eligible"] = True
        p["global_target_id"] = uia.GLOBAL_TARGET_ID
        kept.append(p)

    for u in intervals:
        kept.append(_barrier_point(u["start_ms"], u.get("scene_id"), u.get("reasons")))
        if u["end_ms"] != u["start_ms"]:
            kept.append(_barrier_point(u["end_ms"], u.get("scene_id"), u.get("reasons")))

    kept.extend(_nonproof_barriers(auth))

    # Stable unique timestamps. If valid geometry and a barrier collide, the
    # barrier wins: explicit uncertainty must never be hidden by geometry.
    by_t = {}
    for p in kept:
        t = round(float(p["t"]), 3)
        old = by_t.get(t)
        if old is None or p.get("identity_barrier"):
            by_t[t] = p
    points = [by_t[t] for t in sorted(by_t)]

    return {
        "version": "FIX09B.0-EVENT-BRIDGE",
        "authority": "UNIFIED_IDENTITY",
        "global_target_id": uia.GLOBAL_TARGET_ID,
        "points": points,
        "segments": [],
        "seed_count": int(base.get("seed_count") or 0),
        "unresolved_intervals": deepcopy(intervals),
        "metrics": {
            "geometry_points": sum(1 for p in points if not p.get("identity_barrier")),
            "barrier_points": sum(1 for p in points if p.get("identity_barrier")),
            "unresolved_intervals": len(intervals),
        },
    }


def build_identity_bundle(fix04_track=None, identity_timeline=None, anchors=None,
                          anchor_time_offset=0.0, identity_profile=None) -> dict:
    """Build the canonical identity authority and its safe FIX08 adapter once."""
    authority = uia.build_unified_identity_authority(
        fix04_track=fix04_track,
        identity_timeline=identity_timeline,
        anchors=anchors,
        anchor_time_offset=anchor_time_offset,
        identity_profile=identity_profile,
    )
    return {
        "version": VERSION,
        "global_target_id": uia.GLOBAL_TARGET_ID,
        "authority": authority,
        "event_track": build_safe_event_track(authority),
        "identity_context": identity_context(authority),
    }


def identity_context(authority: dict | None) -> dict:
    """Compact structured context for later B stages and diagnostics."""
    auth = authority if isinstance(authority, dict) else {}
    metrics = deepcopy(auth.get("metrics") or {})
    intervals = _merge_intervals(auth.get("unresolved_intervals") or [])
    return {
        "global_target_id": auth.get("global_target_id") or uia.GLOBAL_TARGET_ID,
        "status": auth.get("status") or "empty",
        "timebase": auth.get("timebase") or "canonical_media_ms",
        "scene_count": len(auth.get("scenes") or []),
        "metrics": metrics,
        "unresolved_intervals": intervals,
        "identity_profile": deepcopy(auth.get("identity_profile")),
    }


def choose_event_track(bundle: dict | None, fallback_fix04_track=None,
                       min_geometry_points=10) -> tuple[dict | None, str]:
    """Select the one event/proof identity authority.

    Once a unified bundle exists, sparse safe geometry must remain sparse and
    fail closed. Falling back merely because fewer than ten proof points exist
    silently removes its barriers and restores FIX04 as a competing target
    authority. ``min_geometry_points`` remains accepted for compatibility but
    is no longer an authority gate.
    """
    if isinstance(bundle, dict):
        tr = bundle.get("event_track")
        auth = bundle.get("authority")
        if (isinstance(tr, dict) and isinstance(auth, dict)
                and auth.get("global_target_id") == uia.GLOBAL_TARGET_ID):
            return tr, "UNIFIED_IDENTITY"
    return fallback_fix04_track, "FIX04_FALLBACK"
