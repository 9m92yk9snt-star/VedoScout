"""FIX10A occlusion-aware goal-plane crossing resolver.

This module creates a *separate* physical proof lane for the narrow case where
an already-verified strike sends the ball toward a verified goal mouth but the
ball becomes visually hidden by a player/body around the line crossing.

The resolver is deliberately fail-closed.  Celebration or goalkeeper reaction
is support only and can never create a crossing by itself.  A verified result
requires all of the following:

* at least three proof-eligible ACTUAL_MEDIA_PTS ball measurements immediately
  before the occlusion;
* time-aligned independent goal-line geometry;
* a low-residual, monotonic trajectory that projects the whole ball through the
  goal plane inside the mouth during a short, explicitly observed goal-mouth
  occlusion;
* no verified competing touch/contact or high-confidence visual contradiction;
* independently parsed supporting reaction cues (release-player celebration +
  goal-mouth defender late/no reaction), used only as a secondary confirmation.

No canonical event is written here.  The caller must still run the independent
FIELD_TO_GOAL direction gate and the final ball-proof certification gate.
"""
from __future__ import annotations

import math
from copy import deepcopy

VERSION = 1

# New lane-local thresholds.  These do not alter A3/A4/Step-3 global gates.
MIN_ANCHOR_ROWS = 3
MAX_ANCHOR_ROWS = 6
ANCHOR_LOOKBACK_MS = 500
MAX_LAST_VISIBLE_TO_OCCLUSION_MS = 220
MAX_CENTER_CROSSING_HORIZON_MS = 500
MAX_WHOLE_BALL_CROSSING_HORIZON_MS = 620
MAX_OCCLUSION_SPAN_MS = 900
GOAL_GEOMETRY_NEAR_MS = 500
MIN_APPROACH_R2 = 0.92
MAX_SIGNED_DISTANCE_RESIDUAL = 0.018
MAX_TANGENTIAL_RESIDUAL = 0.028
MIN_LINE_APPROACH_SPEED = 0.06  # normalized screen distance / second
MIN_PROJECTED_MOUTH_MARGIN = 0.012
MAX_COMPETING_TOUCH_PAD_MS = 160
BALL_PLANE_EPS = 1e-6


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _valid_box(box) -> bool:
    if not isinstance(box, dict):
        return False
    try:
        x, y, w, h = (float(box[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return False
    return -0.1 <= x <= 1.1 and -0.1 <= y <= 1.1 and 0 < w <= 1.2 and 0 < h <= 1.2


def _center(box):
    return float(box["x"]) + float(box["w"]) / 2.0, float(box["y"]) + float(box["h"]) / 2.0


def _canonical_segment(segment):
    if not isinstance(segment, tuple) or len(segment) != 2:
        return segment
    a, b = segment
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) >= abs(dy):
        return (a, b) if a[0] <= b[0] else (b, a)
    return (a, b) if a[1] <= b[1] else (b, a)


def _segment_from_line(line):
    if not isinstance(line, dict):
        return None
    try:
        p1, p2 = line["p1"], line["p2"]
        a = (float(p1["x"]), float(p1["y"]))
        b = (float(p2["x"]), float(p2["y"]))
    except (TypeError, KeyError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (*a, *b)) or a == b:
        return None
    return _canonical_segment((a, b))


def _nearest_timed(rows, media_ms, max_ms=GOAL_GEOMETRY_NEAR_MS):
    valid = [
        row for row in rows or []
        if isinstance(row, dict) and _num(row.get("media_ms"))
    ]
    if not valid or not _num(media_ms):
        return None
    best = min(valid, key=lambda row: abs(int(row["media_ms"]) - int(media_ms)))
    return best if abs(int(best["media_ms"]) - int(media_ms)) <= int(max_ms) else None


def _line_at(goal_geometry, media_ms):
    if not isinstance(goal_geometry, dict):
        return None
    timed = _nearest_timed(goal_geometry.get("line_by_ms"), media_ms)
    if timed:
        segment = _segment_from_line(timed.get("line"))
        if segment is not None:
            return segment
    return _segment_from_line(goal_geometry.get("line"))


def _line_metrics(row, segment):
    if not isinstance(row, dict) or not _valid_box(row.get("box")) or segment is None:
        return None
    a, b = segment
    vx, vy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(vx, vy)
    if length <= 1e-9:
        return None
    tx, ty = vx / length, vy / length
    nx, ny = -ty, tx
    cx, cy = _center(row["box"])
    relx, rely = cx - a[0], cy - a[1]
    signed = relx * nx + rely * ny
    along = relx * tx + rely * ty
    box = row["box"]
    half_normal = abs(nx) * float(box["w"]) / 2.0 + abs(ny) * float(box["h"]) / 2.0
    half_tangent = abs(tx) * float(box["w"]) / 2.0 + abs(ty) * float(box["h"]) / 2.0
    return {
        "media_ms": int(row["media_ms"]),
        "center": (cx, cy),
        "signed_distance": signed,
        "along": along,
        "line_length": length,
        "half_normal": half_normal,
        "half_tangent": half_tangent,
        "whole_ball_on_one_side": abs(signed) > half_normal + BALL_PLANE_EPS,
        "mouth_margin": min(along, length - along) - half_tangent,
    }


def _linear_fit(xs, ys):
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    xbar = sum(xs) / len(xs)
    ybar = sum(ys) / len(ys)
    denom = sum((x - xbar) ** 2 for x in xs)
    if denom <= 1e-12:
        return None
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denom
    intercept = ybar - slope * xbar
    predicted = [slope * x + intercept for x in xs]
    residuals = [y - p for y, p in zip(ys, predicted)]
    max_residual = max(abs(r) for r in residuals)
    ss_res = sum(r * r for r in residuals)
    ss_tot = sum((y - ybar) ** 2 for y in ys)
    r2 = 1.0 if ss_tot <= 1e-12 and ss_res <= 1e-12 else (
        0.0 if ss_tot <= 1e-12 else max(0.0, 1.0 - ss_res / ss_tot)
    )
    return {
        "slope": slope,
        "intercept": intercept,
        "r2": r2,
        "max_residual": max_residual,
    }


def _audit(goal_geometry):
    audit = goal_geometry.get("occlusion_crossing_audit") if isinstance(goal_geometry, dict) else None
    if not isinstance(audit, dict):
        return {
            "status": "UNRESOLVED", "confidence": "low",
            "occlusion_start_media_ms": None, "occlusion_end_media_ms": None,
            "occlusion_rows": [], "pre_occlusion_visible_rows": [],
            "same_ball_pre_occlusion": False,
            "reason": "OCCLUSION_AUDIT_MISSING",
        }
    return {
        "status": str(audit.get("status") or "UNRESOLVED").upper(),
        "confidence": str(audit.get("confidence") or "low").lower(),
        "occlusion_start_media_ms": audit.get("occlusion_start_media_ms"),
        "occlusion_end_media_ms": audit.get("occlusion_end_media_ms"),
        "last_field_side_media_ms": audit.get("last_field_side_media_ms"),
        "first_beyond_after_occlusion_media_ms": audit.get("first_beyond_after_occlusion_media_ms"),
        "occlusion_rows": list(audit.get("occlusion_rows") or []),
        "pre_occlusion_visible_rows": list(audit.get("pre_occlusion_visible_rows") or []),
        "same_ball_pre_occlusion": audit.get("same_ball_pre_occlusion") is True,
        "visual_contradiction": audit.get("visual_contradiction") is True,
        "reason": audit.get("reason"),
    }


def _reaction_support(goal_geometry):
    row = goal_geometry.get("reaction_support_evidence") if isinstance(goal_geometry, dict) else None
    if not isinstance(row, dict):
        return {"status": "UNRESOLVED", "reason": "REACTION_SUPPORT_MISSING"}
    return {
        "status": str(row.get("status") or "UNRESOLVED").upper(),
        "confidence": str(row.get("confidence") or "low").lower(),
        "release_player_celebration": deepcopy(row.get("release_player_celebration")),
        "goal_mouth_defender_response": deepcopy(row.get("goal_mouth_defender_response")),
        "goal_mouth_defender_ball_contact": deepcopy(row.get("goal_mouth_defender_ball_contact")),
        "reason": row.get("reason"),
    }


def _proof_anchor_rows(rows, strike_ms, occlusion_start_ms):
    start = max(int(strike_ms), int(occlusion_start_ms) - ANCHOR_LOOKBACK_MS)
    candidates = [
        row for row in rows or []
        if isinstance(row, dict)
        and row.get("state") == "MEASURED"
        and _num(row.get("media_ms"))
        and start <= int(row["media_ms"]) <= int(occlusion_start_ms)
        and _valid_box(row.get("box"))
        and row.get("proof_eligible") is True
        and row.get("time_authority") == "ACTUAL_MEDIA_PTS"
        and row.get("used_fallback") is not True
        and row.get("cut_barrier") is not True
    ]
    candidates.sort(key=lambda row: int(row["media_ms"]))
    return candidates[-MAX_ANCHOR_ROWS:]


def _provider_pre_occlusion_rows(goal_geometry, strike_ms, occlusion_start_ms):
    occ = _audit(goal_geometry)
    rows = []
    for row in occ.get("pre_occlusion_visible_rows") or []:
        if not isinstance(row, dict) or not _num(row.get("media_ms")):
            continue
        ms = int(row["media_ms"])
        if not (int(strike_ms) <= ms < int(occlusion_start_ms)):
            continue
        if row.get("ball_visible") is not True:
            continue
        if str(row.get("confidence") or "low").lower() not in {"high", "medium"}:
            continue
        if str(row.get("relation") or "UNRESOLVED").upper() not in {"FIELD_SIDE", "ON_OR_STRADDLING_LINE"}:
            continue
        if not _valid_box(row.get("ball_box")):
            continue
        rows.append({
            "media_ms": ms,
            "state": "VISUAL_MEASURED",
            "box": deepcopy(row["ball_box"]),
            "proof_eligible": False,
            "time_authority": "ACTUAL_MEDIA_PTS",
            "used_fallback": False,
            "cut_barrier": False,
            "anchor_source": "PROVIDER_VISUAL",
            "provider_confidence": str(row.get("confidence") or "low").lower(),
        })
    rows.sort(key=lambda row: int(row["media_ms"]))
    return rows[-MAX_ANCHOR_ROWS:]


def _center_distance(a, b):
    if not (isinstance(a, dict) and isinstance(b, dict) and _valid_box(a.get("box")) and _valid_box(b.get("box"))):
        return None
    ax, ay = _center(a["box"]); bx, by = _center(b["box"])
    return math.hypot(ax - bx, ay - by)


def _hybrid_anchor_path(detector_rows, provider_rows):
    """Join detector truth to provider visual anchors without source laundering."""
    if not detector_rows:
        return [], None
    if len(provider_rows) < 2:
        return list(detector_rows), None
    best = None
    for det in detector_rows:
        for vis in provider_rows:
            dt = abs(int(det["media_ms"]) - int(vis["media_ms"]))
            if dt > 120:
                continue
            distance = _center_distance(det, vis)
            if distance is None or distance > 0.075:
                continue
            key = (dt, distance)
            if best is None or key < best[0]:
                best = (key, det, vis)
    if best is None:
        return list(detector_rows), None
    link = {
        "detector_media_ms": int(best[1]["media_ms"]),
        "provider_media_ms": int(best[2]["media_ms"]),
        "center_distance": float(best[0][1]),
        "max_center_distance": 0.075,
    }
    by_ms = {}
    for row in detector_rows:
        copy = deepcopy(row); copy["anchor_source"] = "DETECTOR_PROOF"
        by_ms[int(copy["media_ms"])] = copy
    for row in provider_rows:
        # Detector proof wins on identical media time; provider rows remain
        # explicit otherwise and never gain proof_eligible=True.
        by_ms.setdefault(int(row["media_ms"]), deepcopy(row))
    combined = [by_ms[ms] for ms in sorted(by_ms)]
    return combined[-MAX_ANCHOR_ROWS:], link


def _competing_touch(touch_graph, strike_ms, last_visible_ms, whole_crossing_ms, strike_actor=None):
    graph = touch_graph if isinstance(touch_graph, dict) else {}
    for touch in graph.get("touches") or []:
        if not isinstance(touch, dict) or touch.get("status") != "VERIFIED":
            continue
        ms = touch.get("representative_ms") if _num(touch.get("representative_ms")) else touch.get("media_ms")
        if not _num(ms):
            continue
        ms = int(ms)
        if not (int(last_visible_ms) < ms <= int(whole_crossing_ms) + MAX_COMPETING_TOUCH_PAD_MS):
            continue
        actor = touch.get("player_track_id")
        if strike_actor is not None and actor == strike_actor:
            # A second verified touch by the shooter still changes the physical
            # story, so it remains a competing post-release contact.
            return touch
        return touch
    return None


def _high_confidence_visual_contradiction(goal_geometry, projected_crossing_ms):
    audit = goal_geometry.get("visual_crossing_audit") if isinstance(goal_geometry, dict) else None
    if isinstance(audit, dict) and str(audit.get("status") or "").upper() == "VERIFIED_NO_CROSSING":
        return "INDEPENDENT_VISUAL_NO_CROSSING"
    occ = _audit(goal_geometry)
    if occ.get("visual_contradiction"):
        return "OCCLUSION_AUDIT_VISUAL_CONTRADICTION"
    for row in (audit or {}).get("structured_evidence") or [] if isinstance(audit, dict) else []:
        if not isinstance(row, dict) or not _num(row.get("media_ms")):
            continue
        if int(row["media_ms"]) <= int(projected_crossing_ms):
            continue
        if str(row.get("confidence") or "low").lower() != "high" or row.get("ball_visible") is not True:
            continue
        relation = str(row.get("relation") or "UNRESOLVED").upper()
        if relation in {"FIELD_SIDE", "OTHER"}:
            return f"POST_PROJECTION_VISIBLE_{relation}"
    return None


def resolve_occluded_crossing(rows, goal_geometry, strike_ms, touch_graph=None, strike_actor=None):
    """Return a strict occluded-crossing candidate or ``None`` when inapplicable.

    A returned ``status=VERIFIED`` is still *pre-direction* and *pre-ball-proof*.
    The caller must pass it through ``fix10a_goal_direction`` and
    ``fix10a_ball_proof_gate`` before treating it as certified physical outcome.
    """
    if not _num(strike_ms) or not isinstance(goal_geometry, dict):
        return None
    if goal_geometry.get("source") != "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW":
        return None
    if str(goal_geometry.get("status") or "UNRESOLVED").upper() != "VERIFIED":
        return None

    occ = _audit(goal_geometry)
    if occ["status"] != "VERIFIED_OCCLUSION" or occ["confidence"] not in {"high", "medium"}:
        return None
    if not (_num(occ.get("occlusion_start_media_ms")) and _num(occ.get("occlusion_end_media_ms"))):
        return None
    occ_start = int(occ["occlusion_start_media_ms"])
    occ_end = int(occ["occlusion_end_media_ms"])
    if occ_end < occ_start or occ_end - occ_start > MAX_OCCLUSION_SPAN_MS:
        return {
            "status": "UNRESOLVED", "crossing_ms": None,
            "reason": "GOAL_MOUTH_OCCLUSION_OUT_OF_BOUNDS", "evidence": [],
            "occlusion_audit": occ, "reaction_support": _reaction_support(goal_geometry),
        }

    reaction = _reaction_support(goal_geometry)
    contact = reaction.get("goal_mouth_defender_ball_contact")
    contact_status = str((contact or {}).get("status") or "UNRESOLVED").upper() if isinstance(contact, dict) else "UNRESOLVED"
    contact_conf = str((contact or {}).get("confidence") or "low").lower() if isinstance(contact, dict) else "low"
    if contact_status == "OBSERVED_CONTACT" and contact_conf in {"high", "medium"}:
        return {
            "status": "REJECTED", "crossing_ms": None,
            "reason": "VISIBLE_GOAL_MOUTH_DEFENDER_CONTACT_BEFORE_OCCLUDED_CROSSING",
            "evidence": [], "occlusion_audit": occ, "reaction_support": reaction,
        }
    if reaction.get("status") != "VERIFIED" or reaction.get("confidence") not in {"high", "medium"}:
        return {
            "status": "UNRESOLVED", "crossing_ms": None,
            "reason": "SUPPORTING_REACTION_CONVERGENCE_MISSING", "evidence": [],
            "occlusion_audit": occ, "reaction_support": reaction,
        }

    detector_anchors = _proof_anchor_rows(rows, int(strike_ms), occ_start)
    provider_anchors = _provider_pre_occlusion_rows(goal_geometry, int(strike_ms), occ_start)
    hybrid_link = None
    if len(detector_anchors) >= MIN_ANCHOR_ROWS:
        anchors = [dict(row, anchor_source="DETECTOR_PROOF") for row in detector_anchors]
        anchor_mode = "DETECTOR_ONLY"
    else:
        anchors, hybrid_link = _hybrid_anchor_path(detector_anchors, provider_anchors)
        anchor_mode = "HYBRID_DETECTOR_PROVIDER"
        if not (
            detector_anchors
            and len(provider_anchors) >= 2
            and occ.get("same_ball_pre_occlusion") is True
            and hybrid_link is not None
        ):
            return {
                "status": "UNRESOLVED", "crossing_ms": None,
                "reason": "PRE_OCCLUSION_PROOF_TRAJECTORY_INSUFFICIENT", "evidence": [],
                "detector_anchor_count": len(detector_anchors),
                "provider_anchor_count": len(provider_anchors),
                "occlusion_audit": occ, "reaction_support": reaction,
            }
    if len(anchors) < MIN_ANCHOR_ROWS:
        return {
            "status": "UNRESOLVED", "crossing_ms": None,
            "reason": "PRE_OCCLUSION_PROOF_TRAJECTORY_INSUFFICIENT", "evidence": [],
            "detector_anchor_count": len(detector_anchors),
            "provider_anchor_count": len(provider_anchors),
            "occlusion_audit": occ, "reaction_support": reaction,
        }
    last_visible_ms = int(anchors[-1]["media_ms"])
    if not (0 <= occ_start - last_visible_ms <= MAX_LAST_VISIBLE_TO_OCCLUSION_MS):
        return {
            "status": "UNRESOLVED", "crossing_ms": None,
            "reason": "PRE_OCCLUSION_BALL_TO_VISUAL_OCCLUSION_GAP_TOO_LARGE", "evidence": [],
            "occlusion_audit": occ, "reaction_support": reaction,
        }

    metrics = []
    for row in anchors:
        segment = _line_at(goal_geometry, row["media_ms"])
        m = _line_metrics(row, segment)
        if m is None:
            continue
        metrics.append(m)
    if len(metrics) < MIN_ANCHOR_ROWS:
        return {
            "status": "UNRESOLVED", "crossing_ms": None,
            "reason": "TIME_ALIGNED_GOAL_GEOMETRY_MISSING_FOR_PRE_OCCLUSION_BALL", "evidence": [],
            "occlusion_audit": occ, "reaction_support": reaction,
        }

    # All pre-occlusion centers must remain on one side of the line and approach
    # it monotonically enough for a low-residual linear projection.
    signs = [1 if m["signed_distance"] > 0 else -1 if m["signed_distance"] < 0 else 0 for m in metrics]
    nonzero = [s for s in signs if s]
    if not nonzero or any(s != nonzero[0] for s in nonzero):
        return {
            "status": "UNRESOLVED", "crossing_ms": None,
            "reason": "PRE_OCCLUSION_TRAJECTORY_ALREADY_STRADDLES_OR_CHANGES_GOAL_SIDE", "evidence": [],
            "occlusion_audit": occ, "reaction_support": reaction,
        }
    pre_sign = nonzero[0]
    if not all(m["whole_ball_on_one_side"] for m in metrics[:-1]):
        return {
            "status": "UNRESOLVED", "crossing_ms": None,
            "reason": "PRE_OCCLUSION_WHOLE_BALL_SIDE_NOT_STABLE", "evidence": [],
            "occlusion_audit": occ, "reaction_support": reaction,
        }

    t0 = metrics[-1]["media_ms"]
    ts = [(m["media_ms"] - t0) / 1000.0 for m in metrics]
    signed = [m["signed_distance"] for m in metrics]
    along = [m["along"] for m in metrics]
    signed_fit = _linear_fit(ts, signed)
    along_fit = _linear_fit(ts, along)
    if signed_fit is None or along_fit is None:
        return None
    if (
        signed_fit["r2"] < MIN_APPROACH_R2
        or signed_fit["max_residual"] > MAX_SIGNED_DISTANCE_RESIDUAL
        or along_fit["max_residual"] > MAX_TANGENTIAL_RESIDUAL
    ):
        return {
            "status": "UNRESOLVED", "crossing_ms": None,
            "reason": "PRE_OCCLUSION_TRAJECTORY_FIT_NOT_STABLE", "evidence": [],
            "trajectory_fit": {"signed": signed_fit, "along": along_fit},
            "occlusion_audit": occ, "reaction_support": reaction,
        }
    slope = float(signed_fit["slope"])
    if abs(slope) < MIN_LINE_APPROACH_SPEED or pre_sign * slope >= 0:
        return {
            "status": "UNRESOLVED", "crossing_ms": None,
            "reason": "BALL_NOT_MOVING_TOWARD_GOAL_PLANE", "evidence": [],
            "trajectory_fit": {"signed": signed_fit, "along": along_fit},
            "occlusion_audit": occ, "reaction_support": reaction,
        }

    center_cross_t = -float(signed_fit["intercept"]) / slope
    if not math.isfinite(center_cross_t):
        return None
    center_cross_ms = int(round(t0 + center_cross_t * 1000.0))
    if not (last_visible_ms <= center_cross_ms <= last_visible_ms + MAX_CENTER_CROSSING_HORIZON_MS):
        return {
            "status": "UNRESOLVED", "crossing_ms": None,
            "reason": "PROJECTED_GOAL_PLANE_CROSSING_OUT_OF_BOUNDS", "evidence": [],
            "trajectory_fit": {"signed": signed_fit, "along": along_fit},
            "occlusion_audit": occ, "reaction_support": reaction,
        }

    half_normal = sum(m["half_normal"] for m in metrics[-3:]) / min(3, len(metrics))
    whole_extra_s = half_normal / abs(slope)
    whole_cross_ms = int(round(center_cross_ms + whole_extra_s * 1000.0))
    if not (center_cross_ms <= whole_cross_ms <= last_visible_ms + MAX_WHOLE_BALL_CROSSING_HORIZON_MS):
        return {
            "status": "UNRESOLVED", "crossing_ms": None,
            "reason": "PROJECTED_WHOLE_BALL_CROSSING_OUT_OF_BOUNDS", "evidence": [],
            "trajectory_fit": {"signed": signed_fit, "along": along_fit},
            "occlusion_audit": occ, "reaction_support": reaction,
        }
    # The predicted crossing must actually occur during/just after the observed
    # goal-mouth occlusion, not long before or after it.
    if whole_cross_ms < occ_start - 80 or whole_cross_ms > occ_end + 300:
        return {
            "status": "UNRESOLVED", "crossing_ms": None,
            "reason": "PROJECTED_CROSSING_NOT_COVERED_BY_GOAL_MOUTH_OCCLUSION", "evidence": [],
            "trajectory_fit": {"signed": signed_fit, "along": along_fit},
            "occlusion_audit": occ, "reaction_support": reaction,
        }

    crossing_segment = _line_at(goal_geometry, whole_cross_ms)
    if crossing_segment is None:
        return {
            "status": "UNRESOLVED", "crossing_ms": None,
            "reason": "GOAL_GEOMETRY_UNAVAILABLE_AT_PROJECTED_CROSSING", "evidence": [],
            "trajectory_fit": {"signed": signed_fit, "along": along_fit},
            "occlusion_audit": occ, "reaction_support": reaction,
        }
    a, b = crossing_segment
    vx, vy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(vx, vy)
    tx, ty = vx / length, vy / length
    nx, ny = -ty, tx
    t_whole = (whole_cross_ms - t0) / 1000.0
    projected_along = along_fit["slope"] * t_whole + along_fit["intercept"]
    last_box = anchors[-1]["box"]
    half_tangent = abs(tx) * float(last_box["w"]) / 2.0 + abs(ty) * float(last_box["h"]) / 2.0
    mouth_margin = min(projected_along, length - projected_along) - half_tangent
    uncertainty = max(
        MIN_PROJECTED_MOUTH_MARGIN,
        2.0 * float(along_fit["max_residual"]),
        1.5 * float(signed_fit["max_residual"]),
    )
    if mouth_margin <= uncertainty:
        return {
            "status": "UNRESOLVED", "crossing_ms": None,
            "reason": "PROJECTED_WHOLE_BALL_NOT_SAFELY_INSIDE_GOAL_MOUTH", "evidence": [],
            "projected_mouth_margin": mouth_margin, "required_margin": uncertainty,
            "trajectory_fit": {"signed": signed_fit, "along": along_fit},
            "occlusion_audit": occ, "reaction_support": reaction,
        }

    competing = _competing_touch(
        touch_graph, int(strike_ms), last_visible_ms, whole_cross_ms, strike_actor=strike_actor
    )
    if competing is not None:
        return {
            "status": "UNRESOLVED", "crossing_ms": None,
            "reason": "COMPETING_VERIFIED_POST_STRIKE_CONTACT_BEFORE_PROJECTED_CROSSING",
            "evidence": [], "competing_touch": deepcopy(competing),
            "trajectory_fit": {"signed": signed_fit, "along": along_fit},
            "occlusion_audit": occ, "reaction_support": reaction,
        }

    contradiction = _high_confidence_visual_contradiction(goal_geometry, whole_cross_ms)
    if contradiction:
        return {
            "status": "REJECTED", "crossing_ms": None,
            "reason": contradiction, "evidence": [],
            "trajectory_fit": {"signed": signed_fit, "along": along_fit},
            "occlusion_audit": occ, "reaction_support": reaction,
        }

    # Construct an explicit projected point just beyond the line.  This is not a
    # detector measurement; it is carried only so the independent direction gate
    # can compare the projected goal-side position with verified field-side
    # orientation.  The final ball-proof gate still requires all anchor rows.
    after_signed = -pre_sign * max(half_normal * 1.25, 0.006)
    projected_after = {
        "x": a[0] + tx * projected_along + nx * after_signed,
        "y": a[1] + ty * projected_along + ny * after_signed,
    }
    pre_center = metrics[-1]["center"]
    anchor_ms = [int(row["media_ms"]) for row in anchors]
    detector_anchor_ms = [
        int(row["media_ms"]) for row in anchors
        if str(row.get("anchor_source") or "") == "DETECTOR_PROOF"
    ]
    provider_anchor_ms = [
        int(row["media_ms"]) for row in anchors
        if str(row.get("anchor_source") or "") == "PROVIDER_VISUAL"
    ]
    evidence = [{
        "from_ms": last_visible_ms,
        "to_ms": whole_cross_ms,
        "crossing_ms": whole_cross_ms,
        "center_crossing_ms": center_cross_ms,
        "source": "FIX10A_OCCLUDED_GOAL_RESOLVER",
        "proof_lane": "OCCLUDED_TRAJECTORY_GOAL",
        "anchor_media_ms": anchor_ms,
        "detector_anchor_media_ms": detector_anchor_ms,
        "provider_anchor_media_ms": provider_anchor_ms,
        "anchor_mode": anchor_mode,
        "detector_visual_link": deepcopy(hybrid_link),
        "pre_ball_center": {"x": pre_center[0], "y": pre_center[1]},
        "projected_after_point": projected_after,
        "projected_mouth_margin": round(mouth_margin, 6),
        "required_mouth_margin": round(uncertainty, 6),
        "occlusion_start_media_ms": occ_start,
        "occlusion_end_media_ms": occ_end,
        "trajectory_r2": round(float(signed_fit["r2"]), 6),
        "trajectory_residual": round(float(signed_fit["max_residual"]), 6),
        "same_ball_pre_occlusion": True,
        "reaction_support_only": True,
    }]
    return {
        "status": "VERIFIED",
        "crossing_ms": whole_cross_ms,
        "reason": "BOUNDED_OCCLUDED_GOAL_CROSSING_WITH_PHYSICAL_TRAJECTORY_AND_SUPPORT",
        "evidence": evidence,
        "trajectory_fit": {
            "signed": signed_fit,
            "along": along_fit,
            "pre_side_sign": pre_sign,
        },
        "occlusion_audit": occ,
        "reaction_support": reaction,
    }
