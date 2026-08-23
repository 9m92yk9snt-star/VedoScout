"""FIX10A4 — physical ball-contact reconstruction.

A player being near the ball is not a touch.  Verified contact requires lower-
body contact geometry plus independent temporal/ball-dynamics evidence.  This
module consumes only dense physical evidence; jersey numbers, action stories,
model confidence and football reputation are deliberately absent from the API.
"""
from __future__ import annotations

import math
from copy import deepcopy

VERSION = 1
CONTACT_MAX_H = 0.58
CONTACT_STRONG_H = 0.30
POSSESSION_MAX_H = 0.72
POSSESSION_MARGIN_H = 0.16
SIDE_WINDOW_MS = 180
PLAYER_CONTINUITY_MS = 140
TRAJECTORY_SIGNAL_MIN = 0.28
POSSESSION_SIGNAL_MIN = 0.60
CONTINUITY_SIGNAL_MIN = 0.50
VERIFIED_CONFIDENCE_MIN = 0.62
CONTACT_AMBIG_MARGIN = 0.10


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


def _foot(box):
    return float(box["x"]) + float(box["w"]) / 2.0, float(box["y"]) + float(box["h"])


def _ball_snapshot(row):
    if not isinstance(row, dict):
        return None
    return {
        "media_ms": row.get("media_ms"),
        "state": row.get("state"),
        "box": deepcopy(row.get("box")),
        "confidence": row.get("confidence"),
        "proof_eligible": row.get("proof_eligible"),
        "time_authority": row.get("time_authority"),
    }


def _nearest_trajectory_side(rows, index, direction):
    pivot = rows[index]
    pivot_ms = int(pivot["media_ms"])
    j = index + direction
    while 0 <= j < len(rows):
        row = rows[j]
        dt = abs(int(row["media_ms"]) - pivot_ms)
        if dt > SIDE_WINDOW_MS:
            return None
        if row.get("state") == "MEASURED" and _valid_box(row.get("box")):
            return row
        if row.get("cut_barrier") is True:
            return None
        j += direction
    return None


def _velocity(a, b):
    if not (isinstance(a, dict) and isinstance(b, dict)
            and _valid_box(a.get("box")) and _valid_box(b.get("box"))):
        return None
    dt = (int(b["media_ms"]) - int(a["media_ms"])) / 1000.0
    if dt <= 0:
        return None
    x0, y0 = _center(a["box"]); x1, y1 = _center(b["box"])
    return ((x1 - x0) / dt, (y1 - y0) / dt)


def _trajectory_change(prev_row, cur_row, next_row) -> dict:
    before = _velocity(prev_row, cur_row) if prev_row is not None else None
    after = _velocity(cur_row, next_row) if next_row is not None else None
    if before is None or after is None:
        return {"score": 0.0, "before": before, "after": after,
                "speed_delta": None, "direction_change_deg": None}
    sb, sa = math.hypot(*before), math.hypot(*after)
    speed_delta = abs(sa - sb)
    speed_score = min(1.0, speed_delta / 1.20)
    direction_deg = 0.0
    direction_score = 0.0
    if sb > 1e-6 and sa > 1e-6:
        cosv = max(-1.0, min(1.0, (before[0] * after[0] + before[1] * after[1]) / (sb * sa)))
        direction_deg = math.degrees(math.acos(cosv))
        direction_score = min(1.0, direction_deg / 75.0)
    score = max(speed_score, direction_score)
    return {
        "score": round(score, 4),
        "before": {"x": before[0], "y": before[1]},
        "after": {"x": after[0], "y": after[1]},
        "speed_delta": round(speed_delta, 6),
        "direction_change_deg": round(direction_deg, 3),
    }


def _frame_near(frames, media_ms):
    rows = [f for f in frames if isinstance(f, dict) and _num(f.get("media_ms"))]
    if not rows:
        return None
    best = min(rows, key=lambda f: abs(int(f["media_ms"]) - int(media_ms)))
    return best if abs(int(best["media_ms"]) - int(media_ms)) <= PLAYER_CONTINUITY_MS else None


def _player_by_id(frame, track_id):
    if not isinstance(frame, dict) or not isinstance(track_id, str):
        return None
    return next((p for p in frame.get("players") or []
                 if isinstance(p, dict) and p.get("local_track_id") == track_id
                 and _valid_box(p.get("box"))), None)


def _lower_body_geometry(player_box, ball_box) -> dict:
    fx, fy = _foot(player_box); bx, by = _center(ball_box)
    h = max(float(player_box["h"]), 1e-6)
    d_h = math.hypot(bx - fx, by - fy) / h
    proximity = max(0.0, 1.0 - d_h / CONTACT_MAX_H)
    lower_y0 = float(player_box["y"]) + 0.58 * float(player_box["h"])
    lower_y1 = float(player_box["y"]) + 1.10 * float(player_box["h"])
    lower_x0 = float(player_box["x"]) - 0.20 * float(player_box["w"])
    lower_x1 = float(player_box["x"]) + 1.20 * float(player_box["w"])
    overlap = 1.0 if lower_x0 <= bx <= lower_x1 and lower_y0 <= by <= lower_y1 else 0.0
    geometry = 0.72 * proximity + 0.28 * overlap
    return {
        "distance_h": round(d_h, 4),
        "proximity_score": round(proximity, 4),
        "lower_body_overlap": bool(overlap),
        "score": round(geometry, 4),
    }


def _likely_holder(frame, ball_box):
    if not isinstance(frame, dict) or not _valid_box(ball_box):
        return None
    ranked = []
    for p in frame.get("players") or []:
        if not isinstance(p, dict) or not isinstance(p.get("local_track_id"), str) or not _valid_box(p.get("box")):
            continue
        fx, fy = _foot(p["box"]); bx, by = _center(ball_box)
        d_h = math.hypot(bx - fx, by - fy) / max(float(p["box"]["h"]), 1e-6)
        if d_h <= POSSESSION_MAX_H:
            ranked.append((d_h, p["local_track_id"]))
    ranked.sort()
    if not ranked:
        return None
    if len(ranked) > 1 and ranked[1][0] - ranked[0][0] < POSSESSION_MARGIN_H:
        return None
    return ranked[0][1]


def _possession_transition(track_id, prev_frame, prev_ball, next_frame, next_ball, trajectory_score):
    if not isinstance(track_id, str):
        return {"score": 0.0, "kind": "UNRESOLVED", "before_holder": None, "after_holder": None}
    before_holder = _likely_holder(prev_frame, prev_ball.get("box")) if prev_ball else None
    after_holder = _likely_holder(next_frame, next_ball.get("box")) if next_ball else None
    if before_holder == track_id and after_holder != track_id:
        score, kind = 1.0, "RELEASE"
    elif before_holder != track_id and after_holder == track_id:
        score, kind = 1.0, "RECEIVE"
    elif before_holder == track_id and after_holder == track_id and trajectory_score >= TRAJECTORY_SIGNAL_MIN:
        score, kind = 0.65, "CONTROL_TOUCH"
    else:
        score, kind = 0.0, "NO_TRANSITION_SUPPORT"
    return {
        "score": score,
        "kind": kind,
        "before_holder": before_holder,
        "after_holder": after_holder,
    }


def _player_continuity(track_id, prev_frame, cur_frame, next_frame):
    if not isinstance(track_id, str):
        return 0.0
    count = sum(_player_by_id(f, track_id) is not None for f in (prev_frame, cur_frame, next_frame))
    return count / 3.0


def detect_contact_candidates(dense_frames, ball_trajectory) -> list[dict]:
    """Generate physical contact candidates and explicit rejection reasons."""
    frames = [f for f in (dense_frames or []) if isinstance(f, dict) and _num(f.get("media_ms"))]
    frames.sort(key=lambda f: int(f["media_ms"]))
    trajectory = [r for r in (ball_trajectory or []) if isinstance(r, dict) and _num(r.get("media_ms"))]
    trajectory.sort(key=lambda r: int(r["media_ms"]))
    out = []
    for i, ball in enumerate(trajectory):
        if ball.get("state") not in {"MEASURED", "PREDICTED_SHORT_GAP"} or not _valid_box(ball.get("box")):
            continue
        media_ms = int(ball["media_ms"])
        cur_frame = _frame_near(frames, media_ms)
        if cur_frame is None:
            continue
        prev_ball = _nearest_trajectory_side(trajectory, i, -1)
        next_ball = _nearest_trajectory_side(trajectory, i, +1)
        prev_frame = _frame_near(frames, prev_ball["media_ms"]) if prev_ball else None
        next_frame = _frame_near(frames, next_ball["media_ms"]) if next_ball else None
        trajectory_evidence = _trajectory_change(prev_ball, ball, next_ball)
        for player in cur_frame.get("players") or []:
            if not isinstance(player, dict) or not _valid_box(player.get("box")):
                continue
            track_id = player.get("local_track_id") if isinstance(player.get("local_track_id"), str) else None
            candidate_ids = [x for x in (player.get("candidate_local_track_ids") or []) if isinstance(x, str)]
            geometry = _lower_body_geometry(player["box"], ball["box"])
            continuity = _player_continuity(track_id, prev_frame, cur_frame, next_frame)
            possession = _possession_transition(
                track_id, prev_frame, prev_ball, next_frame, next_ball, trajectory_evidence["score"]
            )
            exact_time = (
                ball.get("proof_eligible") is True
                and ball.get("time_authority") == "ACTUAL_MEDIA_PTS"
                and cur_frame.get("used_fallback") is not True
            )
            measured = ball.get("state") == "MEASURED"
            association_safe = (
                track_id is not None
                and str(player.get("association_state") or "") != "HYPOTHESES"
            )
            dynamic_support = (
                trajectory_evidence["score"] >= TRAJECTORY_SIGNAL_MIN
                or possession["score"] >= POSSESSION_SIGNAL_MIN
            )
            overall = (
                0.38 * geometry["score"]
                + 0.27 * trajectory_evidence["score"]
                + 0.20 * possession["score"]
                + 0.15 * continuity
            )
            rejection_reasons = []
            if geometry["distance_h"] > CONTACT_MAX_H:
                rejection_reasons.append("BALL_OUTSIDE_LOWER_BODY_CONTACT_ZONE")
            if not dynamic_support:
                rejection_reasons.append("NO_INDEPENDENT_BALL_OR_POSSESSION_CHANGE")
            if continuity < CONTINUITY_SIGNAL_MIN:
                rejection_reasons.append("PLAYER_TEMPORAL_CONTINUITY_WEAK")
            if not exact_time:
                rejection_reasons.append("CONTACT_TIME_NOT_EXACT_PROOF")
            if not association_safe:
                rejection_reasons.append("PLAYER_ASSOCIATION_UNRESOLVED")
            qualifies_verified = bool(
                measured
                and geometry["distance_h"] <= CONTACT_MAX_H
                and dynamic_support
                and continuity >= CONTINUITY_SIGNAL_MIN
                and exact_time
                and association_safe
                and overall >= VERIFIED_CONFIDENCE_MIN
            )
            occluded_supported = bool(
                not measured
                and ball.get("state") == "PREDICTED_SHORT_GAP"
                and geometry["distance_h"] <= CONTACT_MAX_H
                and trajectory_evidence["score"] >= TRAJECTORY_SIGNAL_MIN
                and continuity >= CONTINUITY_SIGNAL_MIN
            )
            out.append({
                "media_ms": media_ms,
                "scene_id": cur_frame.get("scene_id"),
                "player_track_id": track_id,
                "player_candidate_track_ids": candidate_ids,
                "player_box": deepcopy(player["box"]),
                "player_association_state": player.get("association_state"),
                "contact_visibility": "VISIBLE" if measured else "OCCLUDED",
                "foot": "UNKNOWN",
                "contact_geometry": geometry,
                "ball_before": _ball_snapshot(prev_ball),
                "ball_at_contact": _ball_snapshot(ball),
                "ball_after": _ball_snapshot(next_ball),
                "trajectory_evidence": trajectory_evidence,
                "possession_evidence": possession,
                "temporal_continuity": round(continuity, 4),
                "confidence": round(overall, 4),
                "qualifies_verified": qualifies_verified,
                "occluded_supported": occluded_supported,
                "rejection_reasons": rejection_reasons,
                "time_authority": ball.get("time_authority"),
                "proof_eligible": bool(qualifies_verified),
            })
    return out


def _contact_id(media_ms, player_track_id, candidate_ids):
    actor = player_track_id or "+".join(candidate_ids or []) or "unknown"
    return f"touchcand_{int(media_ms):010d}_{actor}"


def resolve_contacts(candidates) -> dict:
    """Resolve per-time candidates without guessing between close bodies."""
    rows = [deepcopy(c) for c in (candidates or []) if isinstance(c, dict) and _num(c.get("media_ms"))]
    by_time = {}
    for row in rows:
        by_time.setdefault(int(row["media_ms"]), []).append(row)
    accepted, unresolved, rejected = [], [], []
    for media_ms in sorted(by_time):
        group = by_time[media_ms]
        verified = sorted(
            [r for r in group if r.get("qualifies_verified") is True],
            reverse=True,
            key=lambda r: float(r.get("confidence") or 0.0),
        )
        if verified:
            if (len(verified) > 1
                    and float(verified[0].get("confidence") or 0.0)
                    - float(verified[1].get("confidence") or 0.0) < CONTACT_AMBIG_MARGIN):
                ids = list(dict.fromkeys(
                    [r.get("player_track_id") for r in verified if isinstance(r.get("player_track_id"), str)]
                ))
                top = verified[0]
                unresolved.append({
                    **top,
                    "contact_id": _contact_id(media_ms, None, ids),
                    "status": "HYPOTHESES",
                    "player_track_id": None,
                    "player_candidate_track_ids": ids,
                    "proof_eligible": False,
                    "resolution_reason": "MULTIPLE_PHYSICALLY_PLAUSIBLE_BODIES",
                })
                rejected.extend([{**r, "resolution_reason": "AMBIGUOUS_COMPETING_BODY"} for r in verified])
            else:
                top = verified[0]
                accepted.append({
                    **top,
                    "contact_id": _contact_id(media_ms, top.get("player_track_id"), []),
                    "status": "VERIFIED",
                    "resolution_reason": "MULTI_SIGNAL_PHYSICAL_CONTACT",
                    "proof_eligible": True,
                })
                rejected.extend([{**r, "resolution_reason": "LOWER_RANKED_CONTACT_CANDIDATE"} for r in verified[1:]])
            rejected.extend([
                {**r, "resolution_reason": "PHYSICAL_GATES_NOT_MET"}
                for r in group if r not in verified and not r.get("occluded_supported")
            ])
            continue
        occluded = sorted(
            [r for r in group if r.get("occluded_supported") is True],
            reverse=True,
            key=lambda r: float(r.get("confidence") or 0.0),
        )
        if occluded:
            ids = list(dict.fromkeys([
                r.get("player_track_id") for r in occluded if isinstance(r.get("player_track_id"), str)
            ]))
            top = occluded[0]
            unresolved.append({
                **top,
                "contact_id": _contact_id(media_ms, top.get("player_track_id") if len(ids) == 1 else None, ids),
                "status": "CANDIDATE_OCCLUDED",
                "player_track_id": ids[0] if len(ids) == 1 else None,
                "player_candidate_track_ids": ids,
                "proof_eligible": False,
                "resolution_reason": "BOUNDED_BEFORE_AFTER_PHYSICS_ONLY",
            })
            rejected.extend([
                {**r, "resolution_reason": "PHYSICAL_GATES_NOT_MET"}
                for r in group if r not in occluded
            ])
        else:
            rejected.extend([{**r, "resolution_reason": "PHYSICAL_GATES_NOT_MET"} for r in group])
    contacts = sorted([*accepted, *unresolved], key=lambda r: int(r["media_ms"]))
    return {
        "version": VERSION,
        "contacts": contacts,
        "accepted": accepted,
        "unresolved": unresolved,
        "rejected": rejected,
        "metrics": {
            "candidates": len(rows),
            "accepted": len(accepted),
            "unresolved": len(unresolved),
            "rejected": len(rejected),
        },
    }
