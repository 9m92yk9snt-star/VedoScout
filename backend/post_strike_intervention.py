"""FIX10A7 — independent post-strike player-intervention evidence.

This module is deliberately downstream of a VERIFIED_PHYSICAL_RELEASE.  It does
not consume semantic SHOT/GOAL/SAVE labels and it never writes to A4/A5 contact
or touch truth.  A candidate intervention requires full-body ball/body geometry
plus an independently measured change in the ball path on both sides of the
candidate time.  Ambiguous local player association fails closed.
"""
from __future__ import annotations

import math
from copy import deepcopy

VERSION = 1
MAX_POST_STRIKE_MS = 3000
SIDE_WINDOW_MS = 180
FRAME_NEAR_MS = 120
BODY_PAD_W = 0.12
BODY_PAD_TOP_H = 0.08
BODY_PAD_BOTTOM_H = 0.10
TRAJECTORY_SIGNAL_MIN = 0.28
SPEED_DROP_MIN = 0.18
CONTINUITY_MAX_MS = 180


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


def _velocity(a, b):
    if not (isinstance(a, dict) and isinstance(b, dict) and _valid_box(a.get("box")) and _valid_box(b.get("box"))):
        return None
    dt = (int(b["media_ms"]) - int(a["media_ms"])) / 1000.0
    if dt <= 0:
        return None
    x0, y0 = _center(a["box"]); x1, y1 = _center(b["box"])
    return ((x1 - x0) / dt, (y1 - y0) / dt)


def _trajectory_change(prev_row, cur_row, next_row):
    before = _velocity(prev_row, cur_row)
    after = _velocity(cur_row, next_row)
    if before is None or after is None:
        return {"score": 0.0, "speed_before": None, "speed_after": None,
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
    return {"score": round(max(speed_score, direction_score), 4),
            "speed_before": sb, "speed_after": sa,
            "speed_delta": round(speed_delta, 6),
            "direction_change_deg": round(direction_deg, 3)}


def _measured_rows(trajectory, strike):
    start = int(strike["media_ms"]); end = start + MAX_POST_STRIKE_MS
    scene = strike.get("scene_id")
    return sorted([
        r for r in (trajectory or [])
        if isinstance(r, dict) and _num(r.get("media_ms"))
        and start < int(r["media_ms"]) <= end
        and (scene is None or r.get("scene_id") in {None, scene})
        and r.get("state") == "MEASURED" and _valid_box(r.get("box"))
        and r.get("time_authority") == "ACTUAL_MEDIA_PTS"
        and r.get("used_fallback") is not True
    ], key=lambda r: int(r["media_ms"]))


def _nearest_side(rows, index, direction):
    pivot_ms = int(rows[index]["media_ms"])
    j = index + direction
    while 0 <= j < len(rows):
        row = rows[j]
        if abs(int(row["media_ms"]) - pivot_ms) > SIDE_WINDOW_MS:
            return None
        if row.get("cut_barrier") is True:
            return None
        return row
    return None


def _frame_near(frames, media_ms, scene_id):
    candidates = [f for f in (frames or []) if isinstance(f, dict) and _num(f.get("media_ms"))
                  and (scene_id is None or f.get("scene_id") == scene_id)
                  and f.get("used_fallback") is not True]
    if not candidates:
        return None
    best = min(candidates, key=lambda f: abs(int(f["media_ms"]) - int(media_ms)))
    return best if abs(int(best["media_ms"]) - int(media_ms)) <= FRAME_NEAR_MS else None


def _body_hit(player_box, ball_box):
    bx, by = _center(ball_box)
    x0 = float(player_box["x"]) - BODY_PAD_W * float(player_box["w"])
    x1 = float(player_box["x"]) + (1.0 + BODY_PAD_W) * float(player_box["w"])
    y0 = float(player_box["y"]) - BODY_PAD_TOP_H * float(player_box["h"])
    y1 = float(player_box["y"]) + (1.0 + BODY_PAD_BOTTOM_H) * float(player_box["h"])
    return x0 <= bx <= x1 and y0 <= by <= y1


def _track_present(frames, track_id, media_ms, scene_id):
    for f in frames or []:
        if not isinstance(f, dict) or not _num(f.get("media_ms")) or f.get("scene_id") != scene_id:
            continue
        if abs(int(f["media_ms"]) - int(media_ms)) > CONTINUITY_MAX_MS:
            continue
        for p in f.get("players") or []:
            if isinstance(p, dict) and p.get("local_track_id") == track_id and _valid_box(p.get("box")):
                return True
    return False


def detect_post_strike_intervention(strike, dense_frames, ball_trajectory):
    """Return the earliest independently verified full-body intervention."""
    if not isinstance(strike, dict) or strike.get("status") != "VERIFIED_PHYSICAL_RELEASE" or not _num(strike.get("media_ms")):
        return {"version": VERSION, "status": "UNRESOLVED", "reason": "NO_VERIFIED_PHYSICAL_RELEASE"}
    rows = _measured_rows(ball_trajectory, strike)
    actor = strike.get("player_track_id"); scene = strike.get("scene_id")
    unresolved = []
    for i, ball in enumerate(rows):
        prev_row = _nearest_side(rows, i, -1); next_row = _nearest_side(rows, i, 1)
        if prev_row is None or next_row is None:
            continue
        frame = _frame_near(dense_frames, int(ball["media_ms"]), scene)
        if frame is None or frame.get("cut_barrier") is True:
            continue
        dynamics = _trajectory_change(prev_row, ball, next_row)
        speed_drop = (dynamics["speed_before"] is not None and dynamics["speed_after"] is not None
                      and dynamics["speed_before"] - dynamics["speed_after"] >= SPEED_DROP_MIN)
        if dynamics["score"] < TRAJECTORY_SIGNAL_MIN and not speed_drop:
            continue
        hits = []
        ambiguous_body = False
        for player in frame.get("players") or []:
            if not isinstance(player, dict) or not _valid_box(player.get("box")):
                continue
            if not _body_hit(player["box"], ball["box"]):
                continue
            if str(player.get("association_state") or "") == "HYPOTHESES" or not isinstance(player.get("local_track_id"), str):
                ambiguous_body = True
                continue
            track = player["local_track_id"]
            if track == actor:
                continue
            if not (_track_present(dense_frames, track, int(prev_row["media_ms"]), scene)
                    and _track_present(dense_frames, track, int(next_row["media_ms"]), scene)):
                continue
            hits.append(player)
        if len(hits) != 1:
            if hits or ambiguous_body:
                unresolved.append({"media_ms": int(ball["media_ms"]), "reason": "INTERVENING_BODY_AMBIGUOUS"})
            continue
        player = hits[0]
        kind = "CATCH_OR_CONTROL_LIKE" if speed_drop and dynamics["speed_after"] <= 0.22 else "DEFLECTION_OR_PARRY_LIKE"
        return {
            "version": VERSION,
            "status": "VERIFIED",
            "reason": "FULL_BODY_GEOMETRY_PLUS_MEASURED_POST_STRIKE_BALL_CHANGE",
            "player_track_id": player["local_track_id"],
            "media_ms": int(ball["media_ms"]),
            "kind": kind,
            "player_box": deepcopy(player["box"]),
            "ball_box": deepcopy(ball["box"]),
            "trajectory_change": dynamics,
            "proof_eligible": bool(ball.get("proof_eligible") is True),
            "source": "A7_INDEPENDENT_FULL_BODY_INTERVENTION",
            "touch_graph_mutated": False,
        }
    return {"version": VERSION, "status": "UNRESOLVED",
            "reason": "NO_INDEPENDENT_FULL_BODY_INTERVENTION_PROVEN",
            "candidates_unresolved": unresolved[:6], "source": "A7_INDEPENDENT_FULL_BODY_INTERVENTION"}


def apply_intervention_evidence(outcome, intervention, role_evidence=None):
    """Attach A7 evidence without creating canonical event truth.

    SAVE remains stricter than intervention: verified goalkeeper role plus
    independently resolved non-crossing is required.  Unknown role never becomes
    a goalkeeper by position, kit colour, or football expectation.
    """
    out = deepcopy(outcome) if isinstance(outcome, dict) else {}
    ev = deepcopy(intervention) if isinstance(intervention, dict) else {}
    out["a7_intervention_evidence"] = ev
    if ev.get("status") != "VERIFIED":
        return out
    # Independent A7 evidence supersedes a weaker/unresolved A4-touch-derived
    # intervention only in the outcome layer; A4/A5 data themselves are untouched.
    out["intervention"] = ev
    crossing = out.get("goal_plane_crossing") if isinstance(out.get("goal_plane_crossing"), dict) else {}
    if crossing.get("status") != "VERIFIED":
        out["physical_outcome"] = "PLAYER_INTERVENTION"
    roles = role_evidence if isinstance(role_evidence, dict) else {}
    role = roles.get(ev.get("player_track_id")) if isinstance(ev.get("player_track_id"), str) else None
    role_ok = isinstance(role, dict) and str(role.get("status") or "").upper() == "VERIFIED"
    role_name = str((role or {}).get("role") or "UNKNOWN").upper()
    audit = ((out.get("goal_geometry_evidence") or {}).get("visual_crossing_audit")
             if isinstance(out.get("goal_geometry_evidence"), dict) else None)
    audit_status = str((audit or {}).get("status") or "UNRESOLVED").upper()
    save_verified = bool(role_ok and role_name == "GOALKEEPER"
                         and crossing.get("status") != "VERIFIED"
                         and audit_status == "VERIFIED_NO_CROSSING"
                         and ev.get("proof_eligible") is True)
    out["intervention_role"] = {
        "status": "VERIFIED" if role_ok and role_name in {"GOALKEEPER", "OUTFIELD"} else "UNRESOLVED",
        "role": role_name if role_ok and role_name in {"GOALKEEPER", "OUTFIELD"} else None,
        "reason": (role or {}).get("reason") if isinstance(role, dict) else "ROLE_EVIDENCE_MISSING",
    }
    if save_verified:
        out["save_evidence"] = {"status": "VERIFIED",
                                "reason": "A7_KEEPER_INTERVENTION_PLUS_INDEPENDENT_VERIFIED_NO_CROSSING"}
        out["physical_outcome"] = "GOALKEEPER_SAVE_EVIDENCE"
    elif role_ok and role_name == "OUTFIELD":
        out["save_evidence"] = {"status": "REJECTED", "reason": "A7_INTERVENTION_BY_VERIFIED_OUTFIELD_PLAYER"}
    else:
        out["save_evidence"] = {"status": "UNRESOLVED", "reason": "A7_KEEPER_OR_NON_CROSSING_EVIDENCE_INSUFFICIENT"}
    out["canonical_event_type"] = None
    return out
