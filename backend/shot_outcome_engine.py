"""FIX10A7 — post-strike / intervention / goal-plane physical evidence.

This layer never receives the primary model's GOAL/SAVED story.  It derives
post-strike physics only from the FIX10A Touch Graph and dense ball trajectory.
Goal-line crossing is emitted only when explicit goal geometry and measured
ball points prove it.  Player intervention may be verified without knowing the
player's role; SAVED evidence requires stronger goalkeeper + post-intervention
support and still is not a canonical event in FIX10A.
"""
from __future__ import annotations

import hashlib
import math
from copy import deepcopy

import fix10a_occluded_goal

VERSION = 1
MAX_POST_STRIKE_MS = 3000
MIN_RELEASE_TRAJECTORY_CHANGE = 0.20
INTERVENTION_MIN_TRAJECTORY_CHANGE = 0.25
STOP_SPEED_NORM_S = 0.22
AWAY_DOT_MIN = 0.05
GOAL_GEOMETRY_NEAR_MS = 500
MAX_GOAL_CROSSING_OBSERVATION_GAP_MS = 250
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


def _strike_id(touch_id, media_ms):
    raw = f"{touch_id}|{int(media_ms)}".encode("utf-8")
    return "strike_" + hashlib.sha1(raw).hexdigest()[:16]


def _trajectory_rows(ball_trajectory, start_ms, end_ms, scene_id=None):
    rows = []
    for row in ball_trajectory or []:
        if not isinstance(row, dict) or not _num(row.get("media_ms")):
            continue
        ms = int(row["media_ms"])
        if not (int(start_ms) <= ms <= int(end_ms)):
            continue
        if scene_id is not None and row.get("scene_id") not in {None, scene_id}:
            continue
        rows.append(row)
    return sorted(rows, key=lambda r: int(r["media_ms"]))


def _velocity_between(a, b):
    if not (isinstance(a, dict) and isinstance(b, dict)
            and _valid_box(a.get("box")) and _valid_box(b.get("box"))):
        return None
    dt = (int(b["media_ms"]) - int(a["media_ms"])) / 1000.0
    if dt <= 0:
        return None
    ax, ay = _center(a["box"]); bx, by = _center(b["box"])
    return {"x": (bx - ax) / dt, "y": (by - ay) / dt}


def _speed(vector):
    if not isinstance(vector, dict) or not _num(vector.get("x")) or not _num(vector.get("y")):
        return None
    return math.hypot(float(vector["x"]), float(vector["y"]))


def _measured_near(rows, media_ms, side=0, max_ms=220):
    candidates = [
        r for r in rows
        if r.get("state") == "MEASURED" and _valid_box(r.get("box"))
        and (side == 0 or (int(r["media_ms"]) - int(media_ms)) * side > 0)
        and abs(int(r["media_ms"]) - int(media_ms)) <= max_ms
    ]
    return min(candidates, key=lambda r: abs(int(r["media_ms"]) - int(media_ms)), default=None)


def find_strike_releases(touch_graph: dict | None, ball_trajectory=None) -> list[dict]:
    """Find physically meaningful release/strike candidates, not semantic SHOTs."""
    graph = touch_graph if isinstance(touch_graph, dict) else {}
    touches = [t for t in graph.get("touches") or [] if isinstance(t, dict)]
    trajectory = list(ball_trajectory or [])
    out = []
    for touch in touches:
        if touch.get("status") != "VERIFIED" or not isinstance(touch.get("player_track_id"), str):
            continue
        kinds = set(str(x) for x in (touch.get("possession_kinds") or []))
        change = float(touch.get("trajectory_change") or 0.0)
        contact_role = touch.get("contact_role") if isinstance(touch.get("contact_role"), dict) else None
        if contact_role is not None:
            # Step 4 is explicit release authority when it reviewed a contact.
            # RECEIVE/CONTROL and UNRESOLVED must never be promoted to a strike
            # merely because contact trajectory change is large. Touches with
            # no Step-4 role retain the legacy physical fallback for compatibility.
            if contact_role.get("status") != "VERIFIED":
                continue
            role = str(contact_role.get("role") or "")
            if role != "RELEASE":
                continue
            is_release = True
            physical_strike = True
        else:
            is_release = "RELEASE" in kinds
            physical_strike = is_release or change >= MIN_RELEASE_TRAJECTORY_CHANGE
        if not physical_strike:
            continue
        ms = int(touch.get("representative_ms") or touch.get("media_ms") or 0)
        rows = _trajectory_rows(trajectory, ms, ms + 300, touch.get("scene_id"))
        cur = _measured_near(rows, ms, side=0)
        after = _measured_near(rows, ms, side=1)
        post_velocity = _velocity_between(cur, after) if cur and after else None
        out.append({
            "strike_id": _strike_id(touch.get("touch_id"), ms),
            "touch_id": touch.get("touch_id"),
            "media_ms": ms,
            "scene_id": touch.get("scene_id"),
            "player_track_id": touch.get("player_track_id"),
            "global_target_id": touch.get("global_target_id"),
            "status": "VERIFIED_PHYSICAL_RELEASE",
            "semantic_action": None,
            "post_velocity": post_velocity,
            "post_speed": _speed(post_velocity),
            "trajectory_change": change,
            "proof_eligible": bool(touch.get("proof_eligible")),
        })
    return out


def _segment_intersection(a, b, c, d):
    """Return (hit, t, u) for AB and CD in normalized image coordinates."""
    ax, ay = a; bx, by = b; cx, cy = c; dx, dy = d
    r = (bx - ax, by - ay); s = (dx - cx, dy - cy)
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return False, None, None
    q = (cx - ax, cy - ay)
    t = (q[0] * s[1] - q[1] * s[0]) / den
    u = (q[0] * r[1] - q[1] * r[0]) / den
    return (0.0 <= t <= 1.0 and 0.0 <= u <= 1.0), t, u


def _segment_from_line(line):
    if not isinstance(line, dict):
        return None
    p1, p2 = line.get("p1"), line.get("p2")
    try:
        a = (float(p1["x"]), float(p1["y"]))
        b = (float(p2["x"]), float(p2["y"]))
    except (TypeError, KeyError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (*a, *b)) or a == b:
        return None
    return a, b


def _canonical_segment(segment):
    """Stabilise endpoint order so signed line-side tests survive p1/p2 swaps."""
    if not isinstance(segment, tuple) or len(segment) != 2:
        return segment
    a, b = segment
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) >= abs(dy):
        return (a, b) if a[0] <= b[0] else (b, a)
    return (a, b) if a[1] <= b[1] else (b, a)


def _goal_segment(goal_geometry):
    """Legacy/static goal segment reader retained for deterministic fixtures."""
    if not isinstance(goal_geometry, dict):
        return None
    line = goal_geometry.get("line") if isinstance(goal_geometry.get("line"), dict) else goal_geometry
    segment = _segment_from_line(line)
    return _canonical_segment(segment) if segment is not None else None


def _goal_segment_at(goal_geometry, media_ms):
    """Use geometry nearest the reviewed media time so camera pan is not frozen."""
    if not isinstance(goal_geometry, dict):
        return None
    if (
        goal_geometry.get("source") == "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW"
        and str(goal_geometry.get("status") or "UNRESOLVED").upper() != "VERIFIED"
    ):
        return None
    rows = []
    for row in goal_geometry.get("line_by_ms") or []:
        if not isinstance(row, dict) or not _num(row.get("media_ms")):
            continue
        segment = _segment_from_line(row.get("line"))
        if segment is not None:
            rows.append((int(row["media_ms"]), _canonical_segment(segment)))
    if rows and _num(media_ms):
        best_ms, best = min(rows, key=lambda item: abs(item[0] - int(media_ms)))
        if abs(best_ms - int(media_ms)) <= GOAL_GEOMETRY_NEAR_MS:
            return best
        # A multi-frame provider explicitly supplied time-varying geometry; do
        # not silently fall back to a stale static line outside its support.
        if goal_geometry.get("source") == "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW":
            return None
    return _goal_segment(goal_geometry)


def _line_ball_metrics(row, segment):
    """Ball extent relative to one time-aligned goal plane segment.

    The ball detector supplies an axis-aligned box in normalized image space.
    Projecting half of that box onto the line normal is conservative: the ball
    counts as wholly beyond the plane only when even its nearest box edge is on
    the far side.  Tangential extent is also required to remain between posts.
    """
    if not isinstance(row, dict) or not _valid_box(row.get("box")) or segment is None:
        return None
    a, b = _canonical_segment(segment)
    vx, vy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(vx, vy)
    if length <= 1e-9:
        return None
    tx, ty = vx / length, vy / length
    nx, ny = -ty, tx
    cx, cy = _center(row["box"])
    relx, rely = cx - a[0], cy - a[1]
    signed_distance = relx * nx + rely * ny
    along = relx * tx + rely * ty
    box = row["box"]
    half_normal = abs(nx) * float(box["w"]) / 2.0 + abs(ny) * float(box["h"]) / 2.0
    half_tangent = abs(tx) * float(box["w"]) / 2.0 + abs(ty) * float(box["h"]) / 2.0
    mouth_margin = min(along, length - along) - half_tangent
    return {
        "media_ms": int(row["media_ms"]),
        "center": (cx, cy),
        "signed_distance": signed_distance,
        "half_normal_extent": half_normal,
        "mouth_margin": mouth_margin,
        "whole_ball_on_one_side": abs(signed_distance) > half_normal + BALL_PLANE_EPS,
        "whole_ball_between_posts": mouth_margin > BALL_PLANE_EPS,
    }


def _visual_crossing_audit(goal_geometry):
    row = goal_geometry.get("visual_crossing_audit") if isinstance(goal_geometry, dict) else None
    if not isinstance(row, dict):
        return {
            "present": False, "status": "UNRESOLVED", "confidence": None, "reason": None,
            "proof_ready": False, "same_ball_continuity": False,
            "first_crossing_media_ms": None, "field_side_before_media_ms": None,
            "beyond_line_media_ms": None, "structured_evidence": [],
        }
    status = str(row.get("status") or "UNRESOLVED").upper()
    if status not in {"VERIFIED_CROSSING", "VERIFIED_NO_CROSSING", "UNRESOLVED"}:
        status = "UNRESOLVED"
    return {
        "present": True,
        "status": status,
        "confidence": str(row.get("confidence") or "low").lower(),
        "reason": row.get("reason"),
        "proof_ready": row.get("proof_ready") is True,
        "proof_reason": row.get("proof_reason"),
        "same_ball_continuity": row.get("same_ball_continuity") is True,
        "first_crossing_media_ms": row.get("first_crossing_media_ms"),
        "field_side_before_media_ms": row.get("field_side_before_media_ms"),
        "beyond_line_media_ms": row.get("beyond_line_media_ms"),
        "structured_evidence": list(row.get("structured_evidence") or []),
    }


def _structured_visual_crossing_proof(goal_geometry, strike_ms):
    """Validate the independent structured whole-ball proof lane.

    This does not trust a bare visual ``CROSSED`` label.  It requires the
    provider's machine-checked multi-frame continuity record, verified goal
    geometry and an ordered field-side -> fully-beyond transition after the
    physical release.  Direction and final ball-proof gates still run later.
    """
    audit = _visual_crossing_audit(goal_geometry)
    if not isinstance(goal_geometry, dict):
        return None
    if goal_geometry.get("source") != "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW":
        return None
    if str(goal_geometry.get("status") or "UNRESOLVED").upper() != "VERIFIED":
        return None
    if not (
        audit.get("status") == "VERIFIED_CROSSING"
        and audit.get("confidence") == "high"
        and audit.get("proof_ready") is True
        and audit.get("same_ball_continuity") is True
    ):
        return None
    if not _num(strike_ms):
        return None
    before_ms = audit.get("field_side_before_media_ms")
    crossing_ms = audit.get("first_crossing_media_ms")
    beyond_ms = audit.get("beyond_line_media_ms")
    if not all(_num(x) for x in (before_ms, crossing_ms, beyond_ms)):
        return None
    start = int(strike_ms)
    before_ms, crossing_ms, beyond_ms = int(before_ms), int(crossing_ms), int(beyond_ms)
    if not (start <= before_ms < crossing_ms <= beyond_ms <= start + MAX_POST_STRIKE_MS):
        return None
    evidence_rows = [row for row in audit.get("structured_evidence") or [] if isinstance(row, dict)]
    critical_before = [
        row for row in evidence_rows
        if _num(row.get("media_ms")) and int(row["media_ms"]) == before_ms
        and row.get("ball_visible") is True
        and str(row.get("relation") or "").upper() == "FIELD_SIDE"
        and str(row.get("confidence") or "").lower() == "high"
    ]
    critical_after = [
        row for row in evidence_rows
        if _num(row.get("media_ms")) and int(row["media_ms"]) == beyond_ms
        and row.get("ball_visible") is True
        and str(row.get("relation") or "").upper() == "BEYOND_LINE_INSIDE_MOUTH"
        and str(row.get("confidence") or "").lower() == "high"
    ]
    path_rows = sorted(
        [row for row in evidence_rows if _num(row.get("media_ms")) and before_ms <= int(row["media_ms"]) <= beyond_ms],
        key=lambda row: int(row["media_ms"]),
    )
    if not critical_before or not critical_after or len(path_rows) < 3:
        return None
    if any(
        row.get("ball_visible") is not True
        or str(row.get("confidence") or "low").lower() not in {"high", "medium"}
        or str(row.get("relation") or "").upper() not in {
            "FIELD_SIDE", "ON_OR_STRADDLING_LINE", "BEYOND_LINE_INSIDE_MOUTH"
        }
        for row in path_rows
    ):
        return None
    return {
        "status": "VERIFIED",
        "crossing_ms": crossing_ms,
        "reason": "INDEPENDENT_MULTI_FRAME_WHOLE_BALL_CROSSING",
        "evidence": [{
            "from_ms": before_ms,
            "to_ms": beyond_ms,
            "crossing_ms": crossing_ms,
            "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
            "proof_lane": "STRUCTURED_VISUAL_WHOLE_BALL",
            "same_ball_continuity": True,
        }],
        "visual_audit": audit,
    }


def _goal_crossing_evidence(rows, goal_geometry, strike_ms=None, touch_graph=None, strike_actor=None):
    audit = _visual_crossing_audit(goal_geometry)
    measured = [
        r for r in rows
        if r.get("state") == "MEASURED" and _valid_box(r.get("box"))
        and r.get("time_authority") == "ACTUAL_MEDIA_PTS"
        and r.get("used_fallback") is not True
    ]
    samples = []
    for row in measured:
        segment = _goal_segment_at(goal_geometry, int(row["media_ms"]))
        metrics = _line_ball_metrics(row, segment)
        if metrics is not None:
            metrics["cut_barrier"] = bool(row.get("cut_barrier"))
            samples.append(metrics)
    if not samples:
        visual_proof = _structured_visual_crossing_proof(goal_geometry, strike_ms)
        if visual_proof is not None:
            return visual_proof
        return {"status": "UNRESOLVED", "crossing_ms": None,
                "reason": "GOAL_GEOMETRY_UNAVAILABLE", "evidence": [],
                "visual_audit": audit}

    field_sign = None
    last_field_sample = None
    evidence = []
    for sample in samples:
        if sample.get("cut_barrier") is True:
            field_sign = None
            last_field_sample = None
        distance = float(sample["signed_distance"])
        sign = 1 if distance > 0 else -1 if distance < 0 else 0
        if field_sign is None:
            # We establish the field side only from a frame where the whole ball
            # is visibly on one side of the plane.  A straddling first frame is
            # not enough to decide which side is pre-goal.
            if sign and sample["whole_ball_on_one_side"]:
                field_sign = sign
                last_field_sample = sample
            continue
        if sign == field_sign:
            last_field_sample = sample
            continue
        if sign == 0:
            continue
        # The center has changed sides.  A goal still needs the detector box to
        # be wholly beyond the plane AND wholly between the posts.
        if not sample["whole_ball_on_one_side"] or not sample["whole_ball_between_posts"]:
            continue
        previous = last_field_sample
        if not isinstance(previous, dict):
            continue
        gap = int(sample["media_ms"]) - int(previous["media_ms"])
        if gap <= 0 or gap > MAX_GOAL_CROSSING_OBSERVATION_GAP_MS:
            continue
        before_d = float(previous["signed_distance"])
        after_d = float(sample["signed_distance"])
        denom = abs(before_d) + abs(after_d)
        t = abs(before_d) / denom if denom > 1e-12 else 0.5
        crossing_ms = int(round(int(previous["media_ms"]) + t * gap))
        evidence.append({
            "from_ms": int(previous["media_ms"]),
            "to_ms": int(sample["media_ms"]),
            "crossing_ms": crossing_ms,
            "from_center": {"x": previous["center"][0], "y": previous["center"][1]},
            "to_center": {"x": sample["center"][0], "y": sample["center"][1]},
            "whole_ball_beyond_margin": round(
                abs(after_d) - float(sample["half_normal_extent"]), 6
            ),
            "whole_ball_between_posts_margin": round(float(sample["mouth_margin"]), 6),
            "observation_gap_ms": gap,
        })
        break

    if evidence:
        if audit["status"] == "VERIFIED_NO_CROSSING":
            return {"status": "UNRESOLVED", "crossing_ms": None,
                    "reason": "WHOLE_BALL_PHYSICS_CONFLICTS_WITH_VISUAL_NO_CROSSING",
                    "evidence": evidence[:4], "visual_audit": audit}
        if audit["present"] and audit["status"] != "VERIFIED_CROSSING":
            return {"status": "UNRESOLVED", "crossing_ms": None,
                    "reason": "INDEPENDENT_VISUAL_CROSSING_UNRESOLVED",
                    "evidence": evidence[:4], "visual_audit": audit}
        return {"status": "VERIFIED", "crossing_ms": evidence[0]["crossing_ms"],
                "reason": "WHOLE_BALL_CROSSED_TIME_ALIGNED_GOAL_PLANE",
                "evidence": evidence[:4], "visual_audit": audit}
    if audit["status"] == "VERIFIED_CROSSING":
        visual_proof = _structured_visual_crossing_proof(goal_geometry, strike_ms)
        if visual_proof is not None:
            return visual_proof
        # A visibly asserted crossing can still be hidden at the exact line.
        # The dedicated occlusion lane must independently prove the physical
        # pre-occlusion trajectory and may never trust the bare CROSSED label.
        occluded = fix10a_occluded_goal.resolve_occluded_crossing(
            rows, goal_geometry, strike_ms, touch_graph=touch_graph,
            strike_actor=strike_actor,
        )
        if isinstance(occluded, dict) and occluded.get("status") in {"VERIFIED", "REJECTED"}:
            occluded["visual_audit"] = audit
            return occluded
        return {"status": "UNRESOLVED", "crossing_ms": None,
                "reason": (occluded or {}).get("reason") or
                          "VISUAL_CROSSING_WITHOUT_WHOLE_BALL_PHYSICAL_CROSSING",
                "evidence": list((occluded or {}).get("evidence") or []),
                "visual_audit": audit,
                "occlusion_audit": (occluded or {}).get("occlusion_audit"),
                "reaction_support": (occluded or {}).get("reaction_support")}
    if audit["status"] == "VERIFIED_NO_CROSSING":
        return {"status": "REJECTED", "crossing_ms": None,
                "reason": "INDEPENDENT_VISUAL_NO_CROSSING_AND_NO_WHOLE_BALL_CROSSING",
                "evidence": [], "visual_audit": audit}

    # Last chance is the strictly bounded occlusion-aware physical lane.  It is
    # intentionally evaluated even when the direct visual audit is UNRESOLVED,
    # because an occluding player can make a literal whole-ball frame
    # impossible while the pre-occlusion trajectory and independent reactions
    # still converge.
    occluded = fix10a_occluded_goal.resolve_occluded_crossing(
        rows, goal_geometry, strike_ms, touch_graph=touch_graph,
        strike_actor=strike_actor,
    )
    if isinstance(occluded, dict):
        occluded["visual_audit"] = audit
        if occluded.get("status") in {"VERIFIED", "REJECTED"}:
            return occluded
        if occluded.get("reason"):
            return {"status": "UNRESOLVED", "crossing_ms": None,
                    "reason": occluded.get("reason"),
                    "evidence": list(occluded.get("evidence") or []),
                    "visual_audit": audit,
                    "occlusion_audit": occluded.get("occlusion_audit"),
                    "reaction_support": occluded.get("reaction_support"),
                    "trajectory_fit": occluded.get("trajectory_fit")}
    return {"status": "UNRESOLVED", "crossing_ms": None,
            "reason": "NO_PROVEN_WHOLE_BALL_GOAL_PLANE_CROSSING", "evidence": [],
            "visual_audit": audit}


def _role_resolution(role_evidence, track_id):
    source = role_evidence if isinstance(role_evidence, dict) else {}
    row = source.get(track_id) if isinstance(track_id, str) else None
    if not isinstance(row, dict):
        return {"status": "UNRESOLVED", "role": None, "reason": "ROLE_EVIDENCE_MISSING"}
    role = str(row.get("role") or "UNKNOWN").upper()
    status = str(row.get("status") or "UNRESOLVED").upper()
    if status != "VERIFIED" or role not in {"GOALKEEPER", "OUTFIELD"}:
        return {"status": "UNRESOLVED", "role": None, "reason": "ROLE_EVIDENCE_UNRESOLVED"}
    return {"status": "VERIFIED", "role": role, "reason": row.get("reason") or "ROLE_VERIFIED"}


def _first_other_touch(touch_graph, strike, max_ms=MAX_POST_STRIKE_MS):
    graph = touch_graph if isinstance(touch_graph, dict) else {}
    start = int(strike["media_ms"])
    actor = strike.get("player_track_id")
    scene = strike.get("scene_id")
    candidates = [
        t for t in graph.get("touches") or []
        if isinstance(t, dict) and t.get("status") == "VERIFIED"
        and isinstance(t.get("player_track_id"), str)
        and t.get("player_track_id") != actor
        and t.get("scene_id") == scene
        and _num(t.get("media_ms"))
        and start < int(t["media_ms"]) <= start + int(max_ms)
    ]
    return min(candidates, key=lambda t: int(t["media_ms"]), default=None)


def _intervention_evidence(touch, rows):
    if not isinstance(touch, dict):
        return {"status": "NONE", "player_track_id": None, "media_ms": None,
                "kind": None, "trajectory_change": 0.0}
    ms = int(touch.get("representative_ms") or touch.get("media_ms") or 0)
    before = _measured_near(rows, ms, side=-1)
    at = _measured_near(rows, ms, side=0)
    after = _measured_near(rows, ms, side=1)
    v_before = _velocity_between(before, at) if before and at else None
    v_after = _velocity_between(at, after) if at and after else None
    sb, sa = _speed(v_before), _speed(v_after)
    change = float(touch.get("trajectory_change") or 0.0)
    if change < INTERVENTION_MIN_TRAJECTORY_CHANGE and not (
        sb is not None and sa is not None and sb > STOP_SPEED_NORM_S and sa <= STOP_SPEED_NORM_S
    ):
        return {"status": "UNRESOLVED", "player_track_id": touch.get("player_track_id"),
                "media_ms": ms, "kind": "CONTACT_WITHOUT_CLEAR_POST_STRIKE_EFFECT",
                "trajectory_change": change, "speed_before": sb, "speed_after": sa}
    if sa is not None and sa <= STOP_SPEED_NORM_S and touch.get("possession_after") == touch.get("player_track_id"):
        kind = "CATCH_LIKE_STOP"
    else:
        kind = "DEFLECTION_OR_PARRY_LIKE"
    return {
        "status": "VERIFIED", "player_track_id": touch.get("player_track_id"),
        "media_ms": ms, "kind": kind, "trajectory_change": round(change, 4),
        "speed_before": sb, "speed_after": sa,
        "touch_id": touch.get("touch_id"),
    }


def _moves_away_after_intervention(rows, intervention_ms, goal_geometry):
    segment = _goal_segment_at(goal_geometry, intervention_ms)
    if segment is None:
        return False
    # Goal-segment midpoint is enough for a conservative screen-space direction
    # check once explicit, time-aligned goal geometry has been supplied.
    gx = (segment[0][0] + segment[1][0]) / 2.0
    gy = (segment[0][1] + segment[1][1]) / 2.0
    after = [
        r for r in rows
        if r.get("state") == "MEASURED" and _valid_box(r.get("box"))
        and int(r["media_ms"]) >= int(intervention_ms)
    ]
    if len(after) < 2:
        return False
    a, b = _center(after[0]["box"]), _center(after[min(2, len(after) - 1)]["box"])
    toward_goal = (gx - a[0], gy - a[1])
    post = (b[0] - a[0], b[1] - a[1])
    return post[0] * toward_goal[0] + post[1] * toward_goal[1] < -AWAY_DOT_MIN


def reconstruct_post_strike_outcome(strike: dict, ball_trajectory, touch_graph: dict | None,
                                    goal_geometry=None, role_evidence=None) -> dict:
    """Build physical outcome evidence for one release/strike candidate."""
    if not isinstance(strike, dict) or not _num(strike.get("media_ms")):
        return {"version": VERSION, "status": "invalid", "reason": "INVALID_STRIKE"}
    start = int(strike["media_ms"])
    end = start + MAX_POST_STRIKE_MS
    rows = _trajectory_rows(ball_trajectory, start, end, strike.get("scene_id"))
    crossing = _goal_crossing_evidence(
        rows, goal_geometry, strike_ms=start, touch_graph=touch_graph,
        strike_actor=strike.get("player_track_id"),
    )
    other_touch = _first_other_touch(touch_graph, strike)
    intervention = _intervention_evidence(other_touch, rows)
    role = _role_resolution(role_evidence, intervention.get("player_track_id"))
    moves_away = (
        intervention.get("status") == "VERIFIED"
        and _moves_away_after_intervention(rows, intervention.get("media_ms"), goal_geometry)
    )
    audit = _visual_crossing_audit(goal_geometry)
    non_crossing_audit_ok = (
        not audit["present"] or audit["status"] == "VERIFIED_NO_CROSSING"
    )
    geometry_available = _goal_segment_at(
        goal_geometry, intervention.get("media_ms") if intervention.get("media_ms") is not None else start
    ) is not None
    save_verified = bool(
        intervention.get("status") == "VERIFIED"
        and role.get("status") == "VERIFIED" and role.get("role") == "GOALKEEPER"
        and crossing.get("status") != "VERIFIED"
        and geometry_available
        and non_crossing_audit_ok
        and (intervention.get("kind") == "CATCH_LIKE_STOP" or moves_away)
    )
    if crossing.get("status") == "VERIFIED":
        physical_outcome = "GOAL_PLANE_CROSSING"
    elif save_verified:
        physical_outcome = "GOALKEEPER_SAVE_EVIDENCE"
    elif intervention.get("status") == "VERIFIED":
        physical_outcome = "PLAYER_INTERVENTION"
    elif rows and any(r.get("state") in {"MISSING", "AMBIGUOUS"} for r in rows):
        physical_outcome = "UNRESOLVED_TERMINAL_VISIBILITY"
    else:
        physical_outcome = "UNRESOLVED"
    save = {
        "status": "VERIFIED" if save_verified else (
            "REJECTED" if role.get("status") == "VERIFIED" and role.get("role") == "OUTFIELD" else "UNRESOLVED"
        ),
        "reason": (
            "VERIFIED_KEEPER_INTERVENTION_WITH_NON_CROSSING_POST_PATH" if save_verified
            else "INTERVENTION_BY_VERIFIED_OUTFIELD_PLAYER" if role.get("role") == "OUTFIELD"
            else "KEEPER_AND_NON_CROSSING_EVIDENCE_INSUFFICIENT"
        ),
    }
    return {
        "version": VERSION,
        "status": "ok",
        "strike_id": strike.get("strike_id"),
        "touch_id": strike.get("touch_id"),
        "media_ms": start,
        "scene_id": strike.get("scene_id"),
        "strike_actor_track_id": strike.get("player_track_id"),
        "physical_outcome": physical_outcome,
        "goal_plane_crossing": crossing,
        "goal_geometry_evidence": deepcopy(goal_geometry) if isinstance(goal_geometry, dict) else None,
        "intervention": intervention,
        "intervention_role": role,
        "save_evidence": save,
        "moves_away_after_intervention": bool(moves_away),
        "terminal_ball_state": rows[-1].get("state") if rows else "NO_BALL_ROWS",
        "trajectory_rows_reviewed": len(rows),
        "canonical_event_type": None,
    }
