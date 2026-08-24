"""FIX10A Step 3 — bounded physical contact recovery through short occlusion.

This module is deliberately separate from ordinary A4 contact detection.  It may
recover one otherwise-unresolved physical lower-body contact only when strict
before/contact/after evidence closes a short ball-visibility gap.  Low-confidence
support proposals remain support-only: they never enter A3 and never become A4/A5
truth by themselves.

Two fail-closed paths are supported:
* PRE_ANCHORED_SUPPORT_FLOW: a proof-eligible measured contact anchor is followed
  by a short disappearance; a unique weak support proposal is then confirmed over
  multiple actual video frames by forward/backward optical flow.
* POST_GAP_MEASURED_REACQUISITION: the first proof-eligible measured ball after a
  bounded gap is at a unique lower body, with measured incoming and outgoing
  trajectory on opposite sides of the gap.

No semantic SHOT/GOAL/SAVE label, jersey number, or fixture truth is consumed.
"""
from __future__ import annotations

import hashlib
import math
from copy import deepcopy

import cv2
import numpy as np

import ball_contact_engine as bce
import dense_replay

VERSION = 1

# Keep the recovery inside the already-approved A3 short-gap/dormant horizon.
SHORT_GAP_MS = 180
MAX_OCCLUSION_MS = 450
MAX_INCOMING_SIDE_MS = 180
MAX_OUTGOING_SIDE_MS = 180
MAX_SUPPORT_SEED_MS = 220
MIN_SUPPORT_SEED_MS = 34

# Support proposals are detector search evidence only.  They must be close to the
# measured anchor and to the same verified actor before optical flow is attempted.
SUPPORT_BASE_JUMP_NORM = 0.030
SUPPORT_MAX_SPEED_NORM_S = 3.0
SUPPORT_SEED_ACTOR_MAX_H = 1.10
MAX_SUPPORT_SEEDS = 4

# Aggregate flow proof: one weak detector proposal + at least two independently
# tracked later frames, with forward/backward agreement on multiple points.
FLOW_SPAN_MS = 110
FLOW_FRAME_NEAR_MS = 20
FLOW_MIN_NODES = 3
FLOW_MIN_GOOD_POINTS = 3
FLOW_FB_MAX_PX = 1.50
FLOW_MIN_STEP_DISPLACEMENT_NORM = 0.0015

# Strong physical consequence; proximity alone can never satisfy this gate.
TRAJECTORY_SIGNAL_MIN = 0.45
DIRECTION_CHANGE_STRONG_DEG = 45.0
SPEED_DELTA_STRONG_NORM_S = 0.55
MIN_SEPARATION_GAIN_H = 0.03

# If two independently plausible outcomes materially diverge, do not choose one.
RECOVERY_AMBIGUITY_SCORE_MARGIN = 0.08
RECOVERY_DIVERGENCE_NORM = 0.07
DUPLICATE_CONTACT_NEAR_MS = 80


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _valid_box(box):
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


def _snapshot(row):
    if not isinstance(row, dict):
        return None
    return {
        "media_ms": row.get("media_ms"),
        "state": row.get("state"),
        "box": deepcopy(row.get("box")),
        "confidence": row.get("confidence"),
        "proof_eligible": row.get("proof_eligible"),
        "time_authority": row.get("time_authority"),
        "used_fallback": bool(row.get("used_fallback")),
        "provenance": row.get("provenance"),
    }


def _proof_measured(row):
    return bool(
        isinstance(row, dict)
        and row.get("state") == "MEASURED"
        and _valid_box(row.get("box"))
        and row.get("proof_eligible") is True
        and row.get("time_authority") == "ACTUAL_MEDIA_PTS"
        and row.get("used_fallback") is not True
        and _num(row.get("media_ms"))
    )


def _frame_near(frames, media_ms, max_ms=45):
    rows = [
        f for f in (frames or [])
        if isinstance(f, dict) and _num(f.get("media_ms"))
        and f.get("time_authority") == "ACTUAL_MEDIA_PTS"
        and f.get("used_fallback") is not True
    ]
    if not rows:
        return None
    best = min(rows, key=lambda f: abs(int(f["media_ms"]) - int(media_ms)))
    return best if abs(int(best["media_ms"]) - int(media_ms)) <= int(max_ms) else None


def _player_by_id(frame, track_id):
    if not isinstance(frame, dict) or not isinstance(track_id, str):
        return None
    return next((
        p for p in frame.get("players") or []
        if isinstance(p, dict)
        and p.get("local_track_id") == track_id
        and p.get("association_state") == "VERIFIED_LOCAL"
        and _valid_box(p.get("box"))
    ), None)


def _lower_geometry(player_box, ball_box):
    # Reuse the exact A4 physical geometry formula without changing A4 gates.
    return bce._lower_body_geometry(player_box, ball_box)


def _unique_lower_body_actor(frame, ball_box):
    """Return one VERIFIED_LOCAL actor or an explicit fail-closed reason."""
    if not isinstance(frame, dict) or not _valid_box(ball_box):
        return None, "CONTACT_FRAME_UNAVAILABLE", []
    verified = []
    ambiguous = []
    for player in frame.get("players") or []:
        if not isinstance(player, dict) or not _valid_box(player.get("box")):
            continue
        geom = _lower_geometry(player["box"], ball_box)
        if float(geom.get("distance_h") or 999.0) > float(bce.CONTACT_MAX_H):
            continue
        track = player.get("local_track_id") if isinstance(player.get("local_track_id"), str) else None
        if player.get("association_state") == "VERIFIED_LOCAL" and track:
            verified.append((player, geom))
        else:
            ambiguous.append((player, geom))
    ids = [x[0].get("local_track_id") for x in verified if isinstance(x[0].get("local_track_id"), str)]
    if ambiguous:
        return None, "LOWER_BODY_ASSOCIATION_AMBIGUOUS", ids
    if len(verified) != 1:
        return None, "MULTIPLE_LOWER_BODY_ACTORS" if len(verified) > 1 else "NO_UNIQUE_VERIFIED_LOWER_BODY_ACTOR", ids
    return (verified[0][0], verified[0][1]), None, ids


def _scene_cut_between(frames, start_ms, end_ms, scene_id=None):
    lo, hi = sorted((int(start_ms), int(end_ms)))
    for frame in frames or []:
        if not isinstance(frame, dict) or not _num(frame.get("media_ms")):
            continue
        ms = int(frame["media_ms"])
        if lo < ms <= hi and frame.get("cut_barrier") is True:
            return True
        if lo <= ms <= hi and scene_id is not None and frame.get("scene_id") not in {None, scene_id}:
            return True
    return False


def _velocity(a, b):
    if not (isinstance(a, dict) and isinstance(b, dict)
            and _valid_box(a.get("box")) and _valid_box(b.get("box"))
            and _num(a.get("media_ms")) and _num(b.get("media_ms"))):
        return None
    dt = (int(b["media_ms"]) - int(a["media_ms"])) / 1000.0
    if dt <= 0:
        return None
    ax, ay = _center(a["box"]); bx, by = _center(b["box"])
    return ((bx - ax) / dt, (by - ay) / dt)


def _trajectory_change(in_a, in_b, out_a, out_b):
    before = _velocity(in_a, in_b)
    after = _velocity(out_a, out_b)
    if before is None or after is None:
        return {"score": 0.0, "before": None, "after": None,
                "speed_delta": None, "direction_change_deg": None}
    sb, sa = math.hypot(*before), math.hypot(*after)
    speed_delta = abs(sa - sb)
    direction_deg = 0.0
    direction_score = 0.0
    if sb > 1e-7 and sa > 1e-7:
        cosv = max(-1.0, min(1.0, (before[0] * after[0] + before[1] * after[1]) / (sb * sa)))
        direction_deg = math.degrees(math.acos(cosv))
        direction_score = min(1.0, direction_deg / 75.0)
    speed_score = min(1.0, speed_delta / 1.20)
    return {
        "score": round(max(direction_score, speed_score), 4),
        "before": {"x": before[0], "y": before[1], "speed": sb},
        "after": {"x": after[0], "y": after[1], "speed": sa},
        "speed_delta": round(speed_delta, 6),
        "direction_change_deg": round(direction_deg, 3),
    }


def _strong_trajectory_consequence(change):
    if not isinstance(change, dict):
        return False
    return bool(
        float(change.get("score") or 0.0) >= TRAJECTORY_SIGNAL_MIN
        and (
            float(change.get("direction_change_deg") or 0.0) >= DIRECTION_CHANGE_STRONG_DEG
            or float(change.get("speed_delta") or 0.0) >= SPEED_DELTA_STRONG_NORM_S
        )
    )


def _actor_distance_h(player_box, ball_box):
    fx, fy = _foot(player_box); bx, by = _center(ball_box)
    return math.hypot(bx - fx, by - fy) / max(float(player_box["h"]), 1e-6)


def _separation_gain_h(anchor_player_box, anchor_ball_box, later_player_box, later_ball_box):
    if not all(_valid_box(x) for x in (anchor_player_box, anchor_ball_box, later_player_box, later_ball_box)):
        return None
    start = _actor_distance_h(anchor_player_box, anchor_ball_box)
    end = _actor_distance_h(later_player_box, later_ball_box)
    return end - start


def _contact_id(media_ms, track_id, mode):
    raw = f"{int(media_ms)}|{track_id}|{mode}".encode("utf-8")
    return "touchcand_step3_" + hashlib.sha1(raw).hexdigest()[:16]


def _make_contact(*, mode, anchor, actor, geometry, before_row, after_row,
                  trajectory_change, gap_ms, separation_gain_h, recovery_evidence):
    media_ms = int(anchor["media_ms"])
    track = actor["local_track_id"]
    confidence = min(0.99, max(
        0.70,
        0.32 * float(geometry.get("score") or 0.0)
        + 0.48 * float(trajectory_change.get("score") or 0.0)
        + 0.20,
    ))
    return {
        "media_ms": media_ms,
        "scene_id": recovery_evidence.get("scene_id"),
        "player_track_id": track,
        "player_candidate_track_ids": [track],
        "player_box": deepcopy(actor["box"]),
        "player_association_state": "VERIFIED_LOCAL",
        "contact_visibility": "VISIBLE",
        "foot": "UNKNOWN",
        "contact_geometry": deepcopy(geometry),
        "ball_before": _snapshot(before_row),
        "ball_at_contact": _snapshot(anchor),
        "ball_after": _snapshot(after_row),
        "trajectory_evidence": deepcopy(trajectory_change),
        "possession_evidence": {
            "score": 0.0,
            "kind": "SHORT_OCCLUSION_CONTACT_RECOVERY",
            "before_holder": None,
            "after_holder": None,
        },
        "temporal_continuity": 1.0,
        "confidence": round(confidence, 4),
        "qualifies_verified": True,
        "occluded_supported": False,
        "rejection_reasons": [],
        "time_authority": "ACTUAL_MEDIA_PTS",
        "proof_eligible": True,
        "contact_id": _contact_id(media_ms, track, mode),
        "status": "VERIFIED",
        "resolution_reason": "STEP3_BOUNDED_SHORT_OCCLUSION_MULTI_SIGNAL_RECOVERY",
        "recovery_mode": mode,
        "recovery_gap_ms": int(gap_ms),
        "separation_gain_h": round(float(separation_gain_h), 4) if _num(separation_gain_h) else None,
        "recovery_evidence": deepcopy(recovery_evidence),
    }


def _incoming_pair(measured, anchor_index):
    if anchor_index <= 0:
        return None
    anchor = measured[anchor_index]
    prev = measured[anchor_index - 1]
    if int(anchor["media_ms"]) - int(prev["media_ms"]) > MAX_INCOMING_SIDE_MS:
        return None
    return prev, anchor


def _pre_gap_incoming_pair(measured, anchor_index):
    # For a post-gap anchor, use the two last measured rows on the pre-gap side.
    if anchor_index < 2:
        return None
    prev = measured[anchor_index - 1]
    prev2 = measured[anchor_index - 2]
    if int(prev["media_ms"]) - int(prev2["media_ms"]) > MAX_INCOMING_SIDE_MS:
        return None
    return prev2, prev


def _next_measured(measured, anchor_index):
    if anchor_index + 1 >= len(measured):
        return None
    nxt = measured[anchor_index + 1]
    return nxt


def _accepted_duplicate(contact_result, media_ms, track_id):
    source = contact_result if isinstance(contact_result, dict) else {}
    for row in source.get("accepted") or []:
        if not isinstance(row, dict) or not _num(row.get("media_ms")):
            continue
        if row.get("player_track_id") == track_id and abs(int(row["media_ms"]) - int(media_ms)) <= DUPLICATE_CONTACT_NEAR_MS:
            return True
    return False


def _support_seed_candidates(frames, anchor, actor):
    anchor_ms = int(anchor["media_ms"]); scene = actor.get("scene_id")
    ax, ay = _center(anchor["box"])
    out = []
    for frame in frames or []:
        if not isinstance(frame, dict) or not _num(frame.get("media_ms")):
            continue
        ms = int(frame["media_ms"]); dt_ms = ms - anchor_ms
        if dt_ms < MIN_SUPPORT_SEED_MS or dt_ms > MAX_SUPPORT_SEED_MS:
            continue
        if frame.get("cut_barrier") is True or frame.get("used_fallback") is True or frame.get("time_authority") != "ACTUAL_MEDIA_PTS":
            continue
        if scene is not None and frame.get("scene_id") != scene:
            continue
        current_actor = _player_by_id(frame, actor["local_track_id"])
        if current_actor is None:
            continue
        dt = dt_ms / 1000.0
        max_jump = SUPPORT_BASE_JUMP_NORM + SUPPORT_MAX_SPEED_NORM_S * dt
        for candidate in frame.get("a7_ball_support_candidates") or []:
            if not isinstance(candidate, dict) or candidate.get("support_only") is not True or not _valid_box(candidate.get("box")):
                continue
            cx, cy = _center(candidate["box"])
            displacement = math.hypot(cx - ax, cy - ay)
            if displacement > max_jump:
                continue
            actor_h = _actor_distance_h(current_actor["box"], candidate["box"])
            if actor_h > SUPPORT_SEED_ACTOR_MAX_H:
                continue
            out.append({
                "frame": frame,
                "candidate": candidate,
                "actor": current_actor,
                "dt_ms": dt_ms,
                "anchor_displacement": displacement,
                "actor_distance_h": actor_h,
            })
    out.sort(key=lambda x: (
        -float(x["candidate"].get("confidence") or 0.0),
        int(x["dt_ms"]),
        float(x["actor_distance_h"]),
    ))
    return out[:MAX_SUPPORT_SEEDS]


def _seed_points(box, width, height):
    x, y = _center(box)
    w, h = float(box["w"]), float(box["h"])
    offsets = [(0, 0), (-0.22*w, 0), (0.22*w, 0), (0, -0.22*h), (0, 0.22*h)]
    pts = [[(x + dx) * width, (y + dy) * height] for dx, dy in offsets]
    return np.asarray(pts, dtype=np.float32).reshape(-1, 1, 2)


def _flow_frames_from_video(video_path, start_ms, end_ms):
    return list(dense_replay.iter_dense_frames(str(video_path), int(start_ms), int(end_ms)))


def _track_support_with_flow(video_path, seed_ms, seed_box, *, flow_frame_provider=None):
    provider = flow_frame_provider or _flow_frames_from_video
    try:
        frames = list(provider(str(video_path), int(seed_ms), int(seed_ms) + FLOW_SPAN_MS) or [])
    except Exception as exc:
        return {"status": "UNRESOLVED", "reason": f"FLOW_FRAME_PROVIDER_ERROR:{type(exc).__name__}"}
    frames = sorted([
        f for f in frames
        if isinstance(f, dict) and _num(f.get("media_ms"))
        and f.get("used_fallback") is not True
        and f.get("time_authority") == "ACTUAL_MEDIA_PTS"
        and f.get("frame_bgr") is not None
    ], key=lambda f: int(f["media_ms"]))
    if not frames:
        return {"status": "UNRESOLVED", "reason": "FLOW_NO_ACTUAL_PTS_FRAMES"}
    seed_frame = min(frames, key=lambda f: abs(int(f["media_ms"]) - int(seed_ms)))
    if abs(int(seed_frame["media_ms"]) - int(seed_ms)) > FLOW_FRAME_NEAR_MS:
        return {"status": "UNRESOLVED", "reason": "FLOW_SEED_FRAME_NOT_FOUND"}
    start_index = frames.index(seed_frame)
    frames = frames[start_index:]
    if len(frames) < FLOW_MIN_NODES:
        return {"status": "UNRESOLVED", "reason": "FLOW_INSUFFICIENT_MULTIFRAME_SUPPORT"}

    first = frames[0]["frame_bgr"]
    h, w = first.shape[:2]
    points = _seed_points(seed_box, w, h)
    prev_gray = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
    current_center = np.asarray(_center(seed_box), dtype=float)
    nodes = [{
        "media_ms": int(frames[0]["media_ms"]),
        "box": deepcopy(seed_box),
        "good_points": int(len(points)),
        "fb_error_px": 0.0,
        "source": "SUPPORT_ONLY_DETECTOR_SEED",
        "proof_eligible": False,
    }]
    active = points
    prior_ms = int(frames[0]["media_ms"])
    for frame in frames[1:]:
        if frame.get("cut_barrier") is True:
            return {"status": "UNRESOLVED", "reason": "FLOW_SCENE_CUT_BARRIER"}
        cur = frame["frame_bgr"]
        if cur.shape[:2] != first.shape[:2]:
            return {"status": "UNRESOLVED", "reason": "FLOW_FRAME_SIZE_CHANGED"}
        gray = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY)
        p1, st1, _err1 = cv2.calcOpticalFlowPyrLK(
            prev_gray, gray, active, None,
            winSize=(21, 21), maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
        )
        if p1 is None or st1 is None:
            return {"status": "UNRESOLVED", "reason": "FLOW_FORWARD_TRACK_FAILED"}
        p0r, st2, _err2 = cv2.calcOpticalFlowPyrLK(
            gray, prev_gray, p1, None,
            winSize=(21, 21), maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
        )
        if p0r is None or st2 is None:
            return {"status": "UNRESOLVED", "reason": "FLOW_BACKWARD_TRACK_FAILED"}
        fb = np.linalg.norm(active.reshape(-1, 2) - p0r.reshape(-1, 2), axis=1)
        good = (st1.reshape(-1) == 1) & (st2.reshape(-1) == 1) & np.isfinite(fb) & (fb <= FLOW_FB_MAX_PX)
        if int(good.sum()) < FLOW_MIN_GOOD_POINTS:
            return {"status": "UNRESOLVED", "reason": "FLOW_FORWARD_BACKWARD_SUPPORT_WEAK"}
        old_good = active.reshape(-1, 2)[good]
        new_good = p1.reshape(-1, 2)[good]
        shift_px = np.median(new_good - old_good, axis=0)
        shift_norm = np.asarray([shift_px[0] / w, shift_px[1] / h], dtype=float)
        if not np.all(np.isfinite(shift_norm)):
            return {"status": "UNRESOLVED", "reason": "FLOW_NONFINITE_SHIFT"}
        current_center = current_center + shift_norm
        step_disp = float(math.hypot(*shift_norm))
        box = {
            "x": float(current_center[0] - float(seed_box["w"]) / 2.0),
            "y": float(current_center[1] - float(seed_box["h"]) / 2.0),
            "w": float(seed_box["w"]),
            "h": float(seed_box["h"]),
        }
        if not _valid_box(box):
            return {"status": "UNRESOLVED", "reason": "FLOW_PATH_LEFT_VALID_IMAGE"}
        media_ms = int(frame["media_ms"])
        if media_ms <= prior_ms:
            continue
        nodes.append({
            "media_ms": media_ms,
            "box": box,
            "good_points": int(good.sum()),
            "fb_error_px": round(float(np.median(fb[good])), 4),
            "step_displacement_norm": round(step_disp, 6),
            "source": "FORWARD_BACKWARD_OPTICAL_FLOW",
            "proof_eligible": False,
        })
        active = p1[good].reshape(-1, 1, 2).astype(np.float32)
        prev_gray = gray
        prior_ms = media_ms
        if len(nodes) >= FLOW_MIN_NODES:
            # Two later actual frames are sufficient; keeping the proof window
            # narrow reduces drift and matches the bounded Step-3 contract.
            break
    if len(nodes) < FLOW_MIN_NODES:
        return {"status": "UNRESOLVED", "reason": "FLOW_INSUFFICIENT_MULTIFRAME_SUPPORT"}
    total_dx = _center(nodes[-1]["box"])[0] - _center(nodes[0]["box"])[0]
    total_dy = _center(nodes[-1]["box"])[1] - _center(nodes[0]["box"])[1]
    if math.hypot(total_dx, total_dy) < FLOW_MIN_STEP_DISPLACEMENT_NORM:
        return {"status": "UNRESOLVED", "reason": "FLOW_PATH_NO_MEANINGFUL_MOTION"}
    return {"status": "VERIFIED_PATH", "reason": "MULTIFRAME_FORWARD_BACKWARD_FLOW",
            "nodes": nodes, "proof_eligible": False}


def _support_flow_recoveries(frames, measured, contact_result, video_path, flow_frame_provider=None):
    verified = []
    unresolved = []
    for i, anchor in enumerate(measured):
        incoming = _incoming_pair(measured, i)
        if incoming is None:
            continue
        # This path is specifically for disappearance after the measured contact.
        later_measured = measured[i + 1] if i + 1 < len(measured) else None
        if later_measured is not None and int(later_measured["media_ms"]) - int(anchor["media_ms"]) <= SHORT_GAP_MS:
            continue
        frame = _frame_near(frames, int(anchor["media_ms"]))
        if frame is None or frame.get("cut_barrier") is True:
            continue
        actor_result, reason, ids = _unique_lower_body_actor(frame, anchor["box"])
        if actor_result is None:
            if reason in {"LOWER_BODY_ASSOCIATION_AMBIGUOUS", "MULTIPLE_LOWER_BODY_ACTORS"}:
                unresolved.append({"media_ms": int(anchor["media_ms"]), "reason": reason,
                                   "candidate_tracks": ids, "mode": "PRE_ANCHORED_SUPPORT_FLOW"})
            continue
        actor, geometry = actor_result
        actor = {**deepcopy(actor), "scene_id": frame.get("scene_id")}
        track = actor["local_track_id"]
        if _accepted_duplicate(contact_result, int(anchor["media_ms"]), track):
            continue
        seeds = _support_seed_candidates(frames, anchor, actor)
        if not seeds:
            continue
        candidates = []
        for seed in seeds:
            seed_ms = int(seed["frame"]["media_ms"])
            if seed_ms - int(anchor["media_ms"]) > MAX_OCCLUSION_MS:
                continue
            if _scene_cut_between(frames, int(anchor["media_ms"]), seed_ms, frame.get("scene_id")):
                continue
            flow = _track_support_with_flow(
                video_path, seed_ms, seed["candidate"]["box"], flow_frame_provider=flow_frame_provider
            )
            if flow.get("status") != "VERIFIED_PATH":
                unresolved.append({
                    "media_ms": int(anchor["media_ms"]), "reason": flow.get("reason"),
                    "mode": "PRE_ANCHORED_SUPPORT_FLOW", "support_seed_ms": seed_ms,
                })
                continue
            final_node = flow["nodes"][-1]
            final_frame = _frame_near(frames, int(final_node["media_ms"]), max_ms=50)
            final_actor = _player_by_id(final_frame, track)
            if final_actor is None:
                continue
            synthetic_final = {
                "media_ms": int(final_node["media_ms"]),
                "state": "RECOVERED_SUPPORT_PATH",
                "box": deepcopy(final_node["box"]),
                "confidence": seed["candidate"].get("confidence"),
                "proof_eligible": False,
                "time_authority": "ACTUAL_MEDIA_PTS",
                "used_fallback": False,
                "provenance": "STEP3_SUPPORT_PLUS_FORWARD_BACKWARD_FLOW",
            }
            change = _trajectory_change(incoming[0], incoming[1], anchor, synthetic_final)
            if not _strong_trajectory_consequence(change):
                continue
            separation = _separation_gain_h(actor["box"], anchor["box"], final_actor["box"], synthetic_final["box"])
            if separation is None or separation < MIN_SEPARATION_GAIN_H:
                continue
            evidence = {
                "version": VERSION,
                "mode": "PRE_ANCHORED_SUPPORT_FLOW",
                "scene_id": frame.get("scene_id"),
                "anchor_ms": int(anchor["media_ms"]),
                "support_seed_ms": seed_ms,
                "support_seed_confidence": float(seed["candidate"].get("confidence") or 0.0),
                "raw_support_proof_eligible": False,
                "flow_status": flow.get("status"),
                "flow_nodes": deepcopy(flow.get("nodes") or []),
                "trajectory_change": deepcopy(change),
                "separation_gain_h": round(float(separation), 4),
                "fixture_truth_used": False,
            }
            score = (
                0.55 * float(change.get("score") or 0.0)
                + 0.25 * min(1.0, float(geometry.get("score") or 0.0))
                + 0.20 * min(1.0, max(0.0, float(separation)) / 0.25)
            )
            candidates.append({"score": score, "anchor": anchor, "actor": actor,
                               "geometry": geometry, "before": incoming[0], "after": synthetic_final,
                               "change": change, "gap_ms": seed_ms - int(anchor["media_ms"]),
                               "separation": separation, "evidence": evidence})
        if not candidates:
            continue
        candidates.sort(key=lambda row: float(row["score"]), reverse=True)
        if len(candidates) > 1:
            a, b = candidates[0], candidates[1]
            ac = _center(a["after"]["box"]); bc = _center(b["after"]["box"])
            divergent = math.hypot(ac[0] - bc[0], ac[1] - bc[1]) >= RECOVERY_DIVERGENCE_NORM
            close_score = float(a["score"]) - float(b["score"]) <= RECOVERY_AMBIGUITY_SCORE_MARGIN
            if divergent and close_score:
                unresolved.append({"media_ms": int(anchor["media_ms"]),
                                   "reason": "COMPETING_SUPPORT_FLOW_PATHS",
                                   "mode": "PRE_ANCHORED_SUPPORT_FLOW"})
                continue
        best = candidates[0]
        verified.append(_make_contact(
            mode="PRE_ANCHORED_SUPPORT_FLOW", anchor=best["anchor"], actor=best["actor"],
            geometry=best["geometry"], before_row=best["before"], after_row=best["after"],
            trajectory_change=best["change"], gap_ms=best["gap_ms"],
            separation_gain_h=best["separation"], recovery_evidence=best["evidence"],
        ))
    return verified, unresolved


def _measured_reacquisition_recoveries(frames, measured, contact_result):
    verified = []
    unresolved = []
    for i, anchor in enumerate(measured):
        if i < 2 or i + 1 >= len(measured):
            continue
        prev = measured[i - 1]
        gap_ms = int(anchor["media_ms"]) - int(prev["media_ms"])
        if gap_ms <= SHORT_GAP_MS or gap_ms > MAX_OCCLUSION_MS:
            continue
        incoming = _pre_gap_incoming_pair(measured, i)
        nxt = _next_measured(measured, i)
        if incoming is None or nxt is None:
            continue
        if int(nxt["media_ms"]) - int(anchor["media_ms"]) > MAX_OUTGOING_SIDE_MS:
            continue
        frame = _frame_near(frames, int(anchor["media_ms"]))
        if frame is None or frame.get("cut_barrier") is True:
            continue
        if _scene_cut_between(frames, int(prev["media_ms"]), int(nxt["media_ms"]), frame.get("scene_id")):
            unresolved.append({"media_ms": int(anchor["media_ms"]), "reason": "SCENE_CUT_BARRIER",
                               "mode": "POST_GAP_MEASURED_REACQUISITION"})
            continue
        actor_result, reason, ids = _unique_lower_body_actor(frame, anchor["box"])
        if actor_result is None:
            if reason in {"LOWER_BODY_ASSOCIATION_AMBIGUOUS", "MULTIPLE_LOWER_BODY_ACTORS"}:
                unresolved.append({"media_ms": int(anchor["media_ms"]), "reason": reason,
                                   "candidate_tracks": ids, "mode": "POST_GAP_MEASURED_REACQUISITION"})
            continue
        actor, geometry = actor_result
        actor = {**deepcopy(actor), "scene_id": frame.get("scene_id")}
        track = actor["local_track_id"]
        if _accepted_duplicate(contact_result, int(anchor["media_ms"]), track):
            continue
        next_frame = _frame_near(frames, int(nxt["media_ms"]))
        next_actor = _player_by_id(next_frame, track)
        if next_actor is None:
            continue
        change = _trajectory_change(incoming[0], incoming[1], anchor, nxt)
        if not _strong_trajectory_consequence(change):
            continue
        separation = _separation_gain_h(actor["box"], anchor["box"], next_actor["box"], nxt["box"])
        if separation is None or separation < MIN_SEPARATION_GAIN_H:
            continue
        evidence = {
            "version": VERSION,
            "mode": "POST_GAP_MEASURED_REACQUISITION",
            "scene_id": frame.get("scene_id"),
            "anchor_ms": int(anchor["media_ms"]),
            "pre_gap_last_measured_ms": int(prev["media_ms"]),
            "post_anchor_measured_ms": int(nxt["media_ms"]),
            "occlusion_gap_ms": gap_ms,
            "trajectory_change": deepcopy(change),
            "separation_gain_h": round(float(separation), 4),
            "all_ball_rows_measured_proof_eligible": bool(
                all(_proof_measured(x) for x in (incoming[0], incoming[1], anchor, nxt))
            ),
            "fixture_truth_used": False,
        }
        if evidence["all_ball_rows_measured_proof_eligible"] is not True:
            continue
        verified.append(_make_contact(
            mode="POST_GAP_MEASURED_REACQUISITION", anchor=anchor, actor=actor,
            geometry=geometry, before_row=incoming[1], after_row=nxt,
            trajectory_change=change, gap_ms=gap_ms,
            separation_gain_h=separation, recovery_evidence=evidence,
        ))
    return verified, unresolved


def recover_short_occlusion_contacts(dense_frames, ball_trajectory, contact_result=None,
                                     *, video_path=None, flow_frame_provider=None):
    """Recover strict Step-3 contacts without mutating A3/A4/A5 inputs."""
    frames = sorted([
        deepcopy(f) for f in (dense_frames or [])
        if isinstance(f, dict) and _num(f.get("media_ms"))
    ], key=lambda f: int(f["media_ms"]))
    measured = sorted([
        deepcopy(r) for r in (ball_trajectory or []) if _proof_measured(r)
    ], key=lambda r: int(r["media_ms"]))
    if len(measured) < 2:
        return {"version": VERSION, "status": "UNRESOLVED", "verified": [], "unresolved": [],
                "reason": "INSUFFICIENT_PROOF_MEASURED_TRAJECTORY", "metrics": {"verified": 0}}

    measured_verified, measured_unresolved = _measured_reacquisition_recoveries(
        frames, measured, contact_result or {}
    )
    flow_verified, flow_unresolved = ([], [])
    if video_path or flow_frame_provider is not None:
        flow_verified, flow_unresolved = _support_flow_recoveries(
            frames, measured, contact_result or {}, str(video_path or ""), flow_frame_provider
        )

    combined = sorted([*measured_verified, *flow_verified], key=lambda row: int(row["media_ms"]))
    # Never create two Step-3 contacts for the same actor/moment.  If two modes
    # independently resolve the same contact, keep the measured-reacquisition
    # path because all of its after-evidence is proof-eligible A3 measurement.
    deduped = []
    for row in combined:
        duplicate_index = next((
            i for i, prior in enumerate(deduped)
            if prior.get("player_track_id") == row.get("player_track_id")
            and abs(int(prior["media_ms"]) - int(row["media_ms"])) <= DUPLICATE_CONTACT_NEAR_MS
        ), None)
        if duplicate_index is None:
            deduped.append(row)
            continue
        prior = deduped[duplicate_index]
        if row.get("recovery_mode") == "POST_GAP_MEASURED_REACQUISITION" and prior.get("recovery_mode") != row.get("recovery_mode"):
            deduped[duplicate_index] = row
    unresolved = [*measured_unresolved, *flow_unresolved]
    return {
        "version": VERSION,
        "status": "VERIFIED" if deduped else "UNRESOLVED",
        "verified": deduped,
        "unresolved": unresolved,
        "reason": "STEP3_CONTACT_RECOVERED" if deduped else "NO_STEP3_CONTACT_PROVEN",
        "metrics": {
            "verified": len(deduped),
            "measured_reacquisition_verified": sum(r.get("recovery_mode") == "POST_GAP_MEASURED_REACQUISITION" for r in deduped),
            "support_flow_verified": sum(r.get("recovery_mode") == "PRE_ANCHORED_SUPPORT_FLOW" for r in deduped),
            "unresolved_candidates": len(unresolved),
        },
    }


def apply_recovered_contacts(contact_result, recovery_result):
    """Add only separately VERIFIED Step-3 rows to A5 input.

    Ordinary A4 output is copied, never rewritten in place.  A matching unresolved
    A4 frame candidate is superseded only after Step-3 verification so A5 does not
    receive duplicate contradictory nodes for the same physical moment.
    """
    out = deepcopy(contact_result) if isinstance(contact_result, dict) else {
        "version": getattr(bce, "VERSION", 1), "contacts": [], "accepted": [],
        "unresolved": [], "rejected": [], "metrics": {},
    }
    recovered = [
        deepcopy(r) for r in ((recovery_result or {}).get("verified") or [])
        if isinstance(r, dict) and r.get("status") == "VERIFIED" and r.get("proof_eligible") is True
    ]
    if not recovered:
        out["step3_short_occlusion_recovery"] = deepcopy(recovery_result or {})
        return out

    def matches(row, rec):
        return bool(
            isinstance(row, dict) and _num(row.get("media_ms"))
            and row.get("player_track_id") == rec.get("player_track_id")
            and abs(int(row["media_ms"]) - int(rec["media_ms"])) <= DUPLICATE_CONTACT_NEAR_MS
            and str(row.get("status") or "") != "VERIFIED"
        )

    original_unresolved = list(out.get("unresolved") or [])
    superseded = []
    kept_unresolved = []
    for row in original_unresolved:
        rec = next((r for r in recovered if matches(row, r)), None)
        if rec is None:
            kept_unresolved.append(row)
        else:
            superseded.append({**deepcopy(row), "resolution_reason": "SUPERSEDED_BY_STEP3_VERIFIED_RECOVERY"})
    out["unresolved"] = kept_unresolved
    out["rejected"] = [*(out.get("rejected") or []), *superseded]

    # Remove only the superseded unresolved copies from the mixed contact list.
    contacts = []
    for row in out.get("contacts") or []:
        if any(matches(row, rec) for rec in recovered):
            continue
        contacts.append(row)
    existing_keys = {
        (r.get("player_track_id"), int(r.get("media_ms") or -1))
        for r in out.get("accepted") or [] if isinstance(r, dict)
    }
    added = []
    for rec in recovered:
        key = (rec.get("player_track_id"), int(rec["media_ms"]))
        if key in existing_keys:
            continue
        out.setdefault("accepted", []).append(rec)
        contacts.append(rec)
        added.append(rec)
        existing_keys.add(key)
    out["contacts"] = sorted(contacts, key=lambda r: int(r.get("media_ms") or 0))
    out["accepted"] = sorted(out.get("accepted") or [], key=lambda r: int(r.get("media_ms") or 0))
    metrics = deepcopy(out.get("metrics") or {})
    metrics["accepted"] = len(out.get("accepted") or [])
    metrics["unresolved"] = len(out.get("unresolved") or [])
    metrics["rejected"] = len(out.get("rejected") or [])
    metrics["step3_recovered"] = len(added)
    out["metrics"] = metrics
    out["step3_short_occlusion_recovery"] = deepcopy(recovery_result or {})
    return out
