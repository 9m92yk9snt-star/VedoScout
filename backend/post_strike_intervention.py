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

# A7 support-only fallback.  These proposals never enter A3/A4/A5 truth.
SUPPORT_MAX_POST_STRIKE_MS = 1800
SUPPORT_MAX_GAP_MS = 220
SUPPORT_BASE_JUMP_NORM = 0.035
SUPPORT_MAX_SPEED_NORM_S = 5.5
SUPPORT_BEAM_WIDTH = 8
SUPPORT_AMBIGUITY_MARGIN = 0.035
SUPPORT_MIN_PATH_STEPS = 6
SUPPORT_BODY_PAD_SPAN = 0.28
SUPPORT_BODY_BOTTOM_PAD_SPAN = 0.05
SUPPORT_CLUSTER_MIN_HITS = 3
SUPPORT_CLUSTER_MAX_SPAN_MS = 350
SUPPORT_FRAME_NEAR_MS = 50


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


def _support_anchor(ball_trajectory, strike):
    """Return a proof-eligible A3 measurement anchoring the support path."""
    if not isinstance(strike, dict) or not _num(strike.get("media_ms")):
        return None
    strike_ms = int(strike["media_ms"])
    scene = strike.get("scene_id")
    rows = [
        row for row in (ball_trajectory or [])
        if isinstance(row, dict) and _num(row.get("media_ms"))
        and abs(int(row["media_ms"]) - strike_ms) <= FRAME_NEAR_MS
        and (scene is None or row.get("scene_id") in {None, scene})
        and row.get("state") == "MEASURED" and _valid_box(row.get("box"))
        and row.get("time_authority") == "ACTUAL_MEDIA_PTS"
        and row.get("used_fallback") is not True
        and row.get("proof_eligible") is True
    ]
    if not rows:
        return None
    return min(rows, key=lambda row: abs(int(row["media_ms"]) - strike_ms))


def _support_node(media_ms, candidate):
    return {
        "media_ms": int(media_ms),
        "box": deepcopy(candidate["box"]),
        "confidence": float(candidate.get("confidence") or 0.0),
        "support_only": bool(candidate.get("support_only") is True),
        "proof_eligible": False,
    }


def _support_path_quality(path):
    steps = int(path.get("steps") or 0)
    if steps <= 0:
        return -1e9
    # A small length bonus prevents a short lucky branch from beating a longer,
    # physically continuous reconstruction.
    return float(path.get("score") or 0.0) / steps + min(0.12, 0.005 * steps)


def _support_paths_materially_divergent(a, b):
    amap = {int(node["media_ms"]): node for node in (a.get("nodes") or [])[1:]}
    bmap = {int(node["media_ms"]): node for node in (b.get("nodes") or [])[1:]}
    common = sorted(set(amap).intersection(bmap))
    if len(common) < 2:
        return False
    separations = []
    for media_ms in common:
        ax, ay = _center(amap[media_ms]["box"])
        bx, by = _center(bmap[media_ms]["box"])
        separations.append(math.hypot(ax - bx, ay - by))
    large = sum(value >= 0.08 for value in separations)
    return large >= 2 or (max(separations) >= 0.14 and sum(separations) / len(separations) >= 0.05)


def _build_support_paths(strike, dense_frames, ball_trajectory):
    anchor = _support_anchor(ball_trajectory, strike)
    if anchor is None:
        return {"status": "UNRESOLVED", "reason": "A7_SUPPORT_NO_PROOF_ELIGIBLE_STRIKE_ANCHOR"}
    scene = strike.get("scene_id")
    strike_ms = int(strike["media_ms"])
    frames = sorted([
        frame for frame in (dense_frames or [])
        if isinstance(frame, dict) and _num(frame.get("media_ms"))
        and int(anchor["media_ms"]) < int(frame["media_ms"]) <= strike_ms + SUPPORT_MAX_POST_STRIKE_MS
        and (scene is None or frame.get("scene_id") == scene)
        and frame.get("used_fallback") is not True
        and frame.get("time_authority") == "ACTUAL_MEDIA_PTS"
    ], key=lambda frame: int(frame["media_ms"]))
    if not frames:
        return {"status": "UNRESOLVED", "reason": "A7_SUPPORT_NO_ACTUAL_PTS_FRAMES"}

    anchor_node = {
        "media_ms": int(anchor["media_ms"]),
        "box": deepcopy(anchor["box"]),
        "confidence": float(anchor.get("confidence") or 0.0),
        "support_only": False,
        "proof_eligible": True,
    }
    paths = [{"nodes": [anchor_node], "score": 0.0, "steps": 0}]
    for frame in frames:
        if frame.get("cut_barrier") is True:
            break
        media_ms = int(frame["media_ms"])
        candidates = [
            candidate for candidate in (frame.get("a7_ball_support_candidates") or [])
            if isinstance(candidate, dict) and _valid_box(candidate.get("box"))
        ]
        if not candidates:
            continue
        expanded = []
        for path in paths:
            last = path["nodes"][-1]
            gap_ms = media_ms - int(last["media_ms"])
            if 0 < gap_ms <= SUPPORT_MAX_GAP_MS:
                # Keep an unextended branch alive for a bounded occlusion.  It
                # receives a tiny penalty so measured continuity is preferred.
                expanded.append({
                    "nodes": path["nodes"],
                    "score": float(path.get("score") or 0.0) - 0.01,
                    "steps": int(path.get("steps") or 0),
                })
            if gap_ms <= 0 or gap_ms > SUPPORT_MAX_GAP_MS:
                continue
            dt = gap_ms / 1000.0
            lx, ly = _center(last["box"])
            max_dist = SUPPORT_BASE_JUMP_NORM + SUPPORT_MAX_SPEED_NORM_S * dt
            for candidate in candidates:
                cx, cy = _center(candidate["box"])
                dist = math.hypot(cx - lx, cy - ly)
                if dist > max_dist:
                    continue
                continuity = max(0.0, 1.0 - dist / max(max_dist, 1e-9))
                confidence = max(0.0, float(candidate.get("confidence") or 0.0))
                confidence_score = min(1.0, math.sqrt(confidence / 0.03))
                gap_score = max(0.0, 1.0 - max(0, gap_ms - 33) / SUPPORT_MAX_GAP_MS)
                increment = 0.50 * continuity + 0.40 * confidence_score + 0.10 * gap_score
                expanded.append({
                    "nodes": path["nodes"] + [_support_node(media_ms, candidate)],
                    "score": float(path.get("score") or 0.0) + increment,
                    "steps": int(path.get("steps") or 0) + 1,
                })
        if not expanded:
            continue
        expanded.sort(key=_support_path_quality, reverse=True)
        kept = []
        for path in expanded:
            if len(kept) >= SUPPORT_BEAM_WIDTH:
                break
            last = path["nodes"][-1]
            x, y = _center(last["box"])
            duplicate = False
            for prior in kept:
                plast = prior["nodes"][-1]
                if int(plast["media_ms"]) != int(last["media_ms"]):
                    continue
                px, py = _center(plast["box"])
                if math.hypot(x - px, y - py) < 0.01:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(path)
        paths = kept

    eligible = [path for path in paths if int(path.get("steps") or 0) >= SUPPORT_MIN_PATH_STEPS]
    if not eligible:
        return {"status": "UNRESOLVED", "reason": "A7_SUPPORT_PATH_TOO_SPARSE"}
    eligible.sort(key=_support_path_quality, reverse=True)
    best = eligible[0]
    if len(eligible) > 1:
        second = eligible[1]
        if (_support_path_quality(best) - _support_path_quality(second) <= SUPPORT_AMBIGUITY_MARGIN
                and _support_paths_materially_divergent(best, second)):
            return {
                "status": "UNRESOLVED",
                "reason": "A7_SUPPORT_COMPETING_BALL_PATHS",
                "path_scores": [round(_support_path_quality(best), 4), round(_support_path_quality(second), 4)],
            }
    return {
        "status": "VERIFIED_PATH",
        "reason": "A7_SUPPORT_UNIQUE_ANCHORED_PATH",
        "anchor": anchor_node,
        "path": best,
        "path_score": round(_support_path_quality(best), 4),
    }


def _pose_aware_body_hit(player_box, ball_box):
    """Full-body envelope that remains useful for a horizontal diving player."""
    bx, by = _center(ball_box)
    span = max(float(player_box["w"]), float(player_box["h"]))
    pad = SUPPORT_BODY_PAD_SPAN * span
    bottom_pad = SUPPORT_BODY_BOTTOM_PAD_SPAN * span
    return (
        float(player_box["x"]) - pad <= bx <= float(player_box["x"]) + float(player_box["w"]) + pad
        and float(player_box["y"]) - pad <= by <= float(player_box["y"]) + float(player_box["h"]) + bottom_pad
    )


def _support_frame_near(frames, media_ms, scene_id):
    candidates = [
        frame for frame in (frames or [])
        if isinstance(frame, dict) and _num(frame.get("media_ms"))
        and (scene_id is None or frame.get("scene_id") == scene_id)
        and frame.get("used_fallback") is not True
        and frame.get("time_authority") == "ACTUAL_MEDIA_PTS"
        and abs(int(frame["media_ms"]) - int(media_ms)) <= SUPPORT_FRAME_NEAR_MS
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda frame: abs(int(frame["media_ms"]) - int(media_ms)))


def _support_clusters(strike, dense_frames, support_path):
    scene = strike.get("scene_id")
    actor = strike.get("player_track_id")
    nodes = support_path.get("nodes") or []
    by_track = {}
    for index, node in enumerate(nodes):
        if index == 0 or index >= len(nodes) - 1:
            continue
        frame = _support_frame_near(dense_frames, int(node["media_ms"]), scene)
        if frame is None or frame.get("cut_barrier") is True:
            continue
        hits = []
        for player in frame.get("players") or []:
            if not isinstance(player, dict) or not _valid_box(player.get("box")):
                continue
            if player.get("association_state") != "VERIFIED_LOCAL":
                continue
            track = player.get("local_track_id")
            if not isinstance(track, str) or track == actor:
                continue
            if _pose_aware_body_hit(player["box"], node["box"]):
                hits.append(player)
        # A support sample overlapping multiple verified bodies is not actor
        # evidence for either one.
        if len(hits) != 1:
            continue
        player = hits[0]
        dynamics = _trajectory_change(nodes[index - 1], node, nodes[index + 1])
        speed_drop = (
            dynamics["speed_before"] is not None and dynamics["speed_after"] is not None
            and dynamics["speed_before"] - dynamics["speed_after"] >= SPEED_DROP_MIN
        )
        by_track.setdefault(player["local_track_id"], []).append({
            "media_ms": int(node["media_ms"]),
            "player_box": deepcopy(player["box"]),
            "ball_box": deepcopy(node["box"]),
            "confidence": float(node.get("confidence") or 0.0),
            "trajectory_change": dynamics,
            "speed_drop": bool(speed_drop),
        })

    verified = []
    for track, hits in by_track.items():
        hits.sort(key=lambda row: int(row["media_ms"]))
        for start in range(len(hits)):
            cluster = []
            for row in hits[start:]:
                if int(row["media_ms"]) - int(hits[start]["media_ms"]) > SUPPORT_CLUSTER_MAX_SPAN_MS:
                    break
                cluster.append(row)
            if len(cluster) < SUPPORT_CLUSTER_MIN_HITS:
                continue
            consequences = [
                row for row in cluster
                if float((row.get("trajectory_change") or {}).get("score") or 0.0) >= TRAJECTORY_SIGNAL_MIN
                or row.get("speed_drop") is True
            ]
            if not consequences:
                continue
            # The same scene-local track must still exist at both ends of the
            # multi-frame cluster.  This is actor continuity, not role inference.
            if not (_track_present(dense_frames, track, int(cluster[0]["media_ms"]), scene)
                    and _track_present(dense_frames, track, int(cluster[-1]["media_ms"]), scene)):
                continue
            strongest = max(
                consequences,
                key=lambda row: max(
                    float((row.get("trajectory_change") or {}).get("score") or 0.0),
                    1.0 if row.get("speed_drop") else 0.0,
                ),
            )
            verified.append({
                "player_track_id": track,
                "hits": cluster,
                "strongest": strongest,
            })
            break
    return verified


def _detect_support_intervention(strike, dense_frames, ball_trajectory):
    path_result = _build_support_paths(strike, dense_frames, ball_trajectory)
    if path_result.get("status") != "VERIFIED_PATH":
        return {
            "version": VERSION,
            "status": "UNRESOLVED",
            "reason": path_result.get("reason") or "A7_SUPPORT_PATH_UNRESOLVED",
            "support_path": path_result,
            "source": "A7_SUPPORT_ONLY_FULL_BODY_INTERVENTION",
        }
    clusters = _support_clusters(strike, dense_frames, path_result["path"])
    if len(clusters) != 1:
        return {
            "version": VERSION,
            "status": "UNRESOLVED",
            "reason": "A7_SUPPORT_BODY_CLUSTER_AMBIGUOUS" if clusters else "A7_SUPPORT_NO_MULTIFRAME_BODY_CLUSTER",
            "support_path": {"status": "VERIFIED_PATH", "path_score": path_result.get("path_score")},
            "candidate_tracks": [row.get("player_track_id") for row in clusters],
            "source": "A7_SUPPORT_ONLY_FULL_BODY_INTERVENTION",
        }
    cluster = clusters[0]
    strongest = cluster["strongest"]
    dynamics = strongest["trajectory_change"]
    kind = "CATCH_OR_CONTROL_LIKE" if (
        strongest.get("speed_drop") is True
        and dynamics.get("speed_after") is not None
        and float(dynamics["speed_after"]) <= 0.22
    ) else "DEFLECTION_OR_PARRY_LIKE"
    return {
        "version": VERSION,
        "status": "VERIFIED",
        "reason": "MULTIFRAME_SUPPORT_PATH_PLUS_FULL_BODY_BALL_CHANGE",
        "player_track_id": cluster["player_track_id"],
        "media_ms": int(strongest["media_ms"]),
        "kind": kind,
        "player_box": deepcopy(strongest["player_box"]),
        "ball_box": deepcopy(strongest["ball_box"]),
        "trajectory_change": deepcopy(dynamics),
        # Raw support proposals are never proof-eligible individually.  The
        # aggregate is eligible only because it is anchored to a proof-eligible
        # A3 strike measurement, unique, multi-frame, actual-PTS, and has a
        # physical trajectory consequence.
        "proof_eligible": True,
        "raw_support_proposals_proof_eligible": False,
        "support_hit_ms": [int(row["media_ms"]) for row in cluster["hits"]],
        "support_hit_count": len(cluster["hits"]),
        "support_path_score": path_result.get("path_score"),
        "source": "A7_SUPPORT_ONLY_FULL_BODY_INTERVENTION",
        "touch_graph_mutated": False,
    }


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
    support = _detect_support_intervention(strike, dense_frames, ball_trajectory)
    if support.get("status") == "VERIFIED":
        return support
    return {"version": VERSION, "status": "UNRESOLVED",
            "reason": support.get("reason") or "NO_INDEPENDENT_FULL_BODY_INTERVENTION_PROVEN",
            "candidates_unresolved": unresolved[:6],
            "support_fallback": support,
            "source": "A7_INDEPENDENT_FULL_BODY_INTERVENTION"}


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
