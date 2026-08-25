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

GLOBAL_TARGET_ACTOR_KEY = "GLOBAL_TARGET"
ACTOR_HANDOFF_MAX_MS = 300
ACTOR_HANDOFF_BASE_CENTER_H = 0.45
ACTOR_HANDOFF_SPEED_H_PER_S = 5.0
ACTOR_HANDOFF_HEIGHT_RATIO_MIN = 0.45
ACTOR_HANDOFF_HEIGHT_RATIO_MAX = 2.20
ACTOR_HANDOFF_TEAM_CONF_MIN = 0.70


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
    direct = next((p for p in frame.get("players") or []
                   if isinstance(p, dict) and p.get("local_track_id") == track_id
                   and _valid_box(p.get("box"))), None)
    if direct is not None:
        return direct

    # Narrow target-only body recovery. Dense refinement may retain two raw
    # HYPOTHESES detections while independently proving that both hypotheses
    # refer to one underlying GLOBAL_TARGET local-track candidate. We do not
    # rewrite those raw hypotheses; this synthetic body exists only for strict
    # physical continuity/contact evidence.
    target = frame.get("global_target") if isinstance(frame.get("global_target"), dict) else {}
    if not (
        target.get("status") == "VERIFIED"
        and target.get("proof_eligible") is True
        and target.get("local_track_id") == track_id
        and target.get("reason") == "PROOF_TARGET_SINGLE_CANDIDATE_HYPOTHESIS_COLLAPSE"
        and _valid_box(target.get("body_box"))
    ):
        return None
    out = {
        "local_track_id": track_id,
        "candidate_local_track_ids": [track_id],
        "box": deepcopy(target["body_box"]),
        "confidence": target.get("body_confidence"),
        "association_state": "VERIFIED_GLOBAL_TARGET_BODY",
        "association_reason": target.get("reason"),
        "team": target.get("body_team"),
        "team_confidence": target.get("body_team_confidence"),
        "team_source": target.get("body_team_source"),
        "synthetic_target_body": True,
        "alternate_actor_boxes": [],
    }
    if _valid_box(target.get("body_predicted_box")):
        out["alternate_actor_boxes"].append(deepcopy(target["body_predicted_box"]))
    return out

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


def _players_for_physics(frame):
    if not isinstance(frame, dict):
        return []
    rows = [deepcopy(p) for p in (frame.get("players") or []) if isinstance(p, dict)]
    target = frame.get("global_target") if isinstance(frame.get("global_target"), dict) else {}
    target_track = target.get("local_track_id") if isinstance(target.get("local_track_id"), str) else None
    collapse = bool(
        target.get("status") == "VERIFIED"
        and target.get("proof_eligible") is True
        and target.get("reason") == "PROOF_TARGET_SINGLE_CANDIDATE_HYPOTHESIS_COLLAPSE"
        and target_track
        and _valid_box(target.get("body_box"))
    )
    if not collapse:
        return rows

    filtered = []
    for row in rows:
        candidates = {x for x in (row.get("candidate_local_track_ids") or []) if isinstance(x, str)}
        if row.get("association_state") == "HYPOTHESES" and candidates == {target_track}:
            continue
        filtered.append(row)
    if not any(row.get("local_track_id") == target_track for row in filtered):
        synthetic = _player_by_id(frame, target_track)
        if synthetic is not None:
            filtered.append(synthetic)
    return filtered


def _verified_global_target_track(frame):
    if not isinstance(frame, dict):
        return None
    target = frame.get("global_target") if isinstance(frame.get("global_target"), dict) else {}
    track = target.get("local_track_id") if isinstance(target.get("local_track_id"), str) else None
    if not (target.get("status") == "VERIFIED" and target.get("proof_eligible") is True and track):
        return None
    player = _player_by_id(frame, track)
    if player is None or player.get("association_state") == "HYPOTHESES":
        return None
    return track


def _actor_identity_key(frame, track_id):
    if not isinstance(track_id, str):
        return None
    return GLOBAL_TARGET_ACTOR_KEY if _verified_global_target_track(frame) == track_id else f"LOCAL:{track_id}"


def _boxes_actor_continuous(a, b, dt_ms):
    if not (_valid_box(a) and _valid_box(b) and _num(dt_ms)):
        return {"ok": False, "reason": "ACTOR_GEOMETRY_MISSING"}
    ah, bh = float(a["h"]), float(b["h"])
    ratio = bh / max(ah, 1e-6)
    if not ACTOR_HANDOFF_HEIGHT_RATIO_MIN <= ratio <= ACTOR_HANDOFF_HEIGHT_RATIO_MAX:
        return {"ok": False, "reason": "ACTOR_SCALE_DISCONTINUITY", "height_ratio": ratio}
    ax, ay = _center(a); bx, by = _center(b)
    d_h = math.hypot(bx - ax, by - ay) / max(ah, bh, 1e-6)
    max_h = ACTOR_HANDOFF_BASE_CENTER_H + ACTOR_HANDOFF_SPEED_H_PER_S * max(0.0, float(dt_ms) / 1000.0)
    return {
        "ok": d_h <= max_h,
        "reason": "ACTOR_GEOMETRY_CONTINUOUS" if d_h <= max_h else "ACTOR_SPATIAL_DISCONTINUITY",
        "center_distance_h": round(d_h, 4),
        "max_center_distance_h": round(max_h, 4),
        "height_ratio": round(ratio, 4),
    }


def _team_conflict(a, b):
    if not (isinstance(a, dict) and isinstance(b, dict)):
        return False
    ta, tb = a.get("team"), b.get("team")
    ca, cb = a.get("team_confidence"), b.get("team_confidence")
    return bool(
        ta not in {None, "", "UNKNOWN"} and tb not in {None, "", "UNKNOWN"}
        and _num(ca) and _num(cb)
        and float(ca) >= ACTOR_HANDOFF_TEAM_CONF_MIN
        and float(cb) >= ACTOR_HANDOFF_TEAM_CONF_MIN
        and ta != tb
    )


def _player_for_actor_continuity(anchor_frame, anchor_track_id, frame):
    if not (isinstance(anchor_frame, dict) and isinstance(frame, dict) and isinstance(anchor_track_id, str)):
        return None, {"ok": False, "reason": "ACTOR_CONTINUITY_INPUT_INVALID"}
    if anchor_frame.get("cut_barrier") is True or frame.get("cut_barrier") is True:
        return None, {"ok": False, "reason": "ACTOR_SCENE_CUT_BARRIER"}
    if (anchor_frame.get("scene_id") is not None and frame.get("scene_id") is not None
            and anchor_frame.get("scene_id") != frame.get("scene_id")):
        return None, {"ok": False, "reason": "ACTOR_SCENE_CHANGED"}
    if not (_num(anchor_frame.get("media_ms")) and _num(frame.get("media_ms"))):
        return None, {"ok": False, "reason": "ACTOR_TIME_MISSING"}
    dt_ms = abs(int(frame["media_ms"]) - int(anchor_frame["media_ms"]))
    if dt_ms > ACTOR_HANDOFF_MAX_MS:
        return None, {"ok": False, "reason": "ACTOR_HANDOFF_TIME_EXCEEDED", "dt_ms": dt_ms}

    anchor_player = _player_by_id(anchor_frame, anchor_track_id)
    if anchor_player is None:
        return None, {"ok": False, "reason": "ANCHOR_ACTOR_NOT_FOUND"}
    anchor_target = _verified_global_target_track(anchor_frame)
    frame_target = _verified_global_target_track(frame)

    # If anchor is the verified GLOBAL_TARGET and the next frame has its own
    # verified target mapping, that mapping outranks a stale same-local box.
    if anchor_target == anchor_track_id and isinstance(frame_target, str):
        candidate = _player_by_id(frame, frame_target)
        candidate_track = frame_target
        target_handoff = True
    else:
        candidate = _player_by_id(frame, anchor_track_id)
        candidate_track = anchor_track_id
        target_handoff = False
    if candidate is None or candidate.get("association_state") == "HYPOTHESES":
        return None, {"ok": False, "reason": "ACTOR_CONTINUITY_BODY_NOT_RESOLVED"}
    if _team_conflict(anchor_player, candidate):
        return None, {"ok": False, "reason": "ACTOR_TEAM_CONTRADICTION"}

    anchor_boxes = [anchor_player.get("box")]
    candidate_boxes = [candidate.get("box")]
    if target_handoff and anchor_player.get("synthetic_target_body") is True:
        anchor_boxes.extend(x for x in (anchor_player.get("alternate_actor_boxes") or []) if _valid_box(x))
    if target_handoff and candidate.get("synthetic_target_body") is True:
        candidate_boxes.extend(x for x in (candidate.get("alternate_actor_boxes") or []) if _valid_box(x))
    geometry_options = [
        _boxes_actor_continuous(a, b, dt_ms)
        for a in anchor_boxes for b in candidate_boxes
        if _valid_box(a) and _valid_box(b)
    ]
    passing = [g for g in geometry_options if g.get("ok") is True]
    geom = min(
        passing or geometry_options or [{"ok": False, "reason": "ACTOR_GEOMETRY_MISSING"}],
        key=lambda g: float(g.get("center_distance_h") or 999.0),
    )
    if geom.get("ok") is not True:
        return None, geom

    if target_handoff:
        reason = (
            "SAME_LOCAL_TRACK_AND_VERIFIED_GLOBAL_TARGET"
            if candidate_track == anchor_track_id
            else "VERIFIED_GLOBAL_TARGET_LOCAL_TRACK_HANDOFF"
        )
        actor_key = GLOBAL_TARGET_ACTOR_KEY
    else:
        if candidate_track != anchor_track_id:
            return None, {"ok": False, "reason": "ARBITRARY_LOCAL_TRACK_SWITCH_REJECTED"}
        reason = "SAME_LOCAL_TRACK"
        actor_key = _actor_identity_key(anchor_frame, anchor_track_id) or f"LOCAL:{anchor_track_id}"
    evidence = {
        "ok": True,
        "reason": reason,
        "geometry_reason": geom.get("reason"),
        "actor_key": actor_key,
        "anchor_track_id": anchor_track_id,
        "resolved_track_id": candidate_track,
        "dt_ms": dt_ms,
        "center_distance_h": geom.get("center_distance_h"),
        "max_center_distance_h": geom.get("max_center_distance_h"),
        "height_ratio": geom.get("height_ratio"),
    }
    return candidate, evidence


def _best_lower_geometry(player, ball_box):
    if not (isinstance(player, dict) and _valid_box(player.get("box")) and _valid_box(ball_box)):
        return _lower_body_geometry(player.get("box") if isinstance(player, dict) else {}, ball_box)
    variants = [("DETECTED_BODY", player["box"])]
    if player.get("synthetic_target_body") is True:
        for box in player.get("alternate_actor_boxes") or []:
            if _valid_box(box):
                variants.append(("TARGET_MOTION_PREDICTED_BODY", box))
    scored = []
    for source, box in variants:
        geom = _lower_body_geometry(box, ball_box)
        geom["geometry_source"] = source
        geom["actor_box_used"] = deepcopy(box)
        scored.append(geom)
    scored.sort(key=lambda g: (
        0 if float(g.get("distance_h") or 999.0) <= CONTACT_MAX_H else 1,
        -float(g.get("score") or 0.0),
        float(g.get("distance_h") or 999.0),
    ))
    return scored[0]

def _likely_holder(frame, ball_box):
    if not isinstance(frame, dict) or not _valid_box(ball_box):
        return None
    ranked = []
    for p in _players_for_physics(frame):
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

def _possession_transition(track_id, cur_frame, prev_frame, prev_ball, next_frame, next_ball, trajectory_score):
    if not isinstance(track_id, str):
        return {"score": 0.0, "kind": "UNRESOLVED", "before_holder": None, "after_holder": None}
    if prev_frame is None or prev_ball is None or next_frame is None or next_ball is None:
        return {"score": 0.0, "kind": "INSUFFICIENT_BOTH_SIDES",
                "before_holder": None, "after_holder": None}
    before_holder = _likely_holder(prev_frame, prev_ball.get("box"))
    after_holder = _likely_holder(next_frame, next_ball.get("box"))
    actor_key = _actor_identity_key(cur_frame, track_id) or f"LOCAL:{track_id}"

    # Exact local-id continuity is still hard physical evidence even when a
    # neighbouring frame lacks proof-level GLOBAL_TARGET authority. Different
    # ids, however, may only bridge through independently verified target maps.
    if before_holder == track_id:
        before_key = actor_key
    else:
        before_key = _actor_identity_key(prev_frame, before_holder) if isinstance(before_holder, str) else None
        before_key = before_key or (f"LOCAL:{before_holder}" if isinstance(before_holder, str) else None)
    if after_holder == track_id:
        after_key = actor_key
    else:
        after_key = _actor_identity_key(next_frame, after_holder) if isinstance(after_holder, str) else None
        after_key = after_key or (f"LOCAL:{after_holder}" if isinstance(after_holder, str) else None)

    # A nearby competing body may make exclusive holder selection ambiguous.
    # Ambiguity is not evidence that the contact actor released the ball. If
    # the same physical actor is independently continuous into the adjacent
    # frame and the measured ball remains inside the existing possession
    # radius, preserve actor continuity. This can block a false RELEASE/RECEIVE
    # but cannot bridge an arbitrary local-id switch.
    for side, side_frame, side_ball in (("before", prev_frame, prev_ball), ("after", next_frame, next_ball)):
        resolved_actor, _continuity = _player_for_actor_continuity(cur_frame, track_id, side_frame)
        if resolved_actor is None or not _valid_box(side_ball.get("box")):
            continue
        fx, fy = _foot(resolved_actor["box"]); bx, by = _center(side_ball["box"])
        distance_h = math.hypot(bx - fx, by - fy) / max(float(resolved_actor["box"]["h"]), 1e-6)
        if distance_h > POSSESSION_MAX_H:
            continue
        if side == "before":
            before_key = actor_key
            if before_holder is None:
                before_holder = resolved_actor.get("local_track_id")
        else:
            after_key = actor_key
            if after_holder is None:
                after_holder = resolved_actor.get("local_track_id")

    if before_key == actor_key and after_key != actor_key:
        score, kind = 1.0, "RELEASE"
    elif before_key != actor_key and after_key == actor_key:
        score, kind = 1.0, "RECEIVE"
    elif before_key == actor_key and after_key == actor_key and trajectory_score >= TRAJECTORY_SIGNAL_MIN:
        score, kind = 0.65, "CONTROL_TOUCH"
    else:
        score, kind = 0.0, "NO_TRANSITION_SUPPORT"
    return {
        "score": score,
        "kind": kind,
        "actor_key": actor_key,
        "before_holder": before_holder,
        "after_holder": after_holder,
        "before_holder_actor_key": before_key,
        "after_holder_actor_key": after_key,
    }

def _player_continuity(track_id, prev_frame, cur_frame, next_frame):
    if not isinstance(track_id, str):
        return 0.0
    current_key = _actor_identity_key(cur_frame, track_id)
    count = 0
    for frame in (prev_frame, cur_frame, next_frame):
        if frame is None:
            continue
        if _player_by_id(frame, track_id) is not None:
            count += 1
            continue
        if current_key == GLOBAL_TARGET_ACTOR_KEY and _verified_global_target_track(frame) is not None:
            count += 1
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
        has_both_sides = (
            prev_ball is not None and next_ball is not None
            and prev_frame is not None and next_frame is not None
        )
        trajectory_evidence = _trajectory_change(prev_ball, ball, next_ball)
        for player in _players_for_physics(cur_frame):
            if not isinstance(player, dict) or not _valid_box(player.get("box")):
                continue
            track_id = player.get("local_track_id") if isinstance(player.get("local_track_id"), str) else None
            candidate_ids = [x for x in (player.get("candidate_local_track_ids") or []) if isinstance(x, str)]
            geometry = _best_lower_geometry(player, ball["box"])
            continuity = _player_continuity(track_id, prev_frame, cur_frame, next_frame)
            possession = _possession_transition(
                track_id, cur_frame, prev_frame, prev_ball, next_frame, next_ball, trajectory_evidence["score"]
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
            dynamic_support = bool(
                has_both_sides
                and (
                    trajectory_evidence["score"] >= TRAJECTORY_SIGNAL_MIN
                    or possession["score"] >= POSSESSION_SIGNAL_MIN
                )
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
            if not has_both_sides:
                rejection_reasons.append("INSUFFICIENT_BEFORE_AFTER_PHYSICS")
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
                and has_both_sides
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
                and has_both_sides
                and geometry["distance_h"] <= CONTACT_MAX_H
                and trajectory_evidence["score"] >= TRAJECTORY_SIGNAL_MIN
                and continuity >= CONTINUITY_SIGNAL_MIN
            )
            out.append({
                "media_ms": media_ms,
                "scene_id": cur_frame.get("scene_id"),
                "player_track_id": track_id,
                "player_actor_key": _actor_identity_key(cur_frame, track_id),
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
