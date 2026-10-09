"""FIX10A2 — dense scene-local player-track refinement.

The broad FIX09B.1 scene graph remains the discovery substrate.  This module
refines scene-local player geometry only inside bounded FIX10A dense windows.
It may reuse existing scene-local ids, but it never creates or upgrades the
GLOBAL_TARGET identity: that authority remains exclusively in
``unified_identity_authority``.
"""
from __future__ import annotations

import math
from copy import deepcopy

import cv2
import numpy as np

import football_scene_graph as fsg
import motion_compensation
import unified_identity_authority as uia

VERSION = 1
TRACK_MAX_GAP_MS = 450
MATCH_IOU_MIN = 0.05
MATCH_CENTER_H = 0.95
MATCH_SCALE_MIN = 0.55
MATCH_SCALE_MAX = 1.85
MATCH_AMBIG_MARGIN = 0.14
TARGET_MATCH_IOU_MIN = 0.14
TARGET_MATCH_CENTER_H = 0.75
TARGET_MATCH_AMBIG_MARGIN = 0.16
TARGET_NEAR_MS = 250
# A user tap is recorded in canonical media time while decoded frames land on
# the nearest actual PTS.  Treat only the nearest frame-sized delta as the same
# observation; this does not extend tap authority through time.
TAP_FRAME_NEAR_MS = 25
DENSE_BALL_CONF_T = 0.03
A7_BALL_SUPPORT_CONF_T = 0.001
A7_BALL_SUPPORT_MAX = 12
DENSE_TEAM_TAP_CONTINUITY_MS = 1200


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


def _box(box):
    return {k: float(box[k]) for k in ("x", "y", "w", "h")}


def _center(box):
    return float(box["x"]) + float(box["w"]) / 2.0, float(box["y"]) + float(box["h"]) / 2.0


def _iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]
    bx0, by0, bx1, by1 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


def _track_number(track_id) -> int:
    if not isinstance(track_id, str) or not track_id.startswith("p"):
        return 0
    try:
        return int(track_id[1:])
    except ValueError:
        return 0


def _new_track_id(next_id: int) -> str:
    return f"p{int(next_id):03d}"


def _last_ms(track: dict, default_ms: int) -> int:
    """Return a track timestamp without treating valid media time 0 as missing."""
    value = track.get("last_ms") if isinstance(track, dict) else None
    return int(round(float(value))) if _num(value) else int(default_ms)


def seed_scene_tracks(scene_graph: dict | None, scene_id: str, start_ms: int) -> dict:
    """Seed local tracks from the nearest broad graph frame in one scene.

    Existing local ids are preserved.  The broad frame's GLOBAL_TARGET mapping
    is copied only when it was already VERIFIED/proof-eligible; ambiguous target
    candidates remain unbound and never become local-track identity authority.
    """
    graph = scene_graph if isinstance(scene_graph, dict) else {}
    scene = str(scene_id or "")
    frames = [
        f for f in graph.get("frames") or []
        if isinstance(f, dict) and str(f.get("scene_id") or "") == scene
        and _num(f.get("media_ms"))
    ]
    frames.sort(key=lambda f: int(f["media_ms"]))
    all_ids = [
        _track_number(p.get("local_track_id"))
        for f in frames for p in (f.get("players") or []) if isinstance(p, dict)
    ]
    next_id = max([0, *all_ids]) + 1
    if not frames:
        return {"scene_id": scene, "seed_media_ms": None, "tracks": [], "next_id": next_id,
                "seed_global_target_local_track_id": None}
    pivot = min(frames, key=lambda f: abs(int(f["media_ms"]) - int(start_ms)))
    tracks = []
    for p in pivot.get("players") or []:
        if not isinstance(p, dict) or not isinstance(p.get("local_track_id"), str) or not _valid_box(p.get("box")):
            continue
        tracks.append({
            "local_track_id": p["local_track_id"],
            "box": _box(p["box"]),
            "last_ms": int(pivot["media_ms"]),
            "vx": 0.0,
            "vy": 0.0,
            "team": p.get("team"),
            "team_confidence": p.get("team_confidence"),
            "team_source": p.get("team_source"),
        })
    target = pivot.get("global_target") if isinstance(pivot.get("global_target"), dict) else {}
    seed_target = (
        target.get("local_track_id")
        if target.get("status") == "VERIFIED"
        and target.get("proof_eligible") is True
        and isinstance(target.get("local_track_id"), str)
        else None
    )
    return {
        "scene_id": scene,
        "seed_media_ms": int(pivot["media_ms"]),
        "tracks": tracks,
        "next_id": next_id,
        "seed_global_target_local_track_id": seed_target,
    }


def transform_box_affine(box: dict, matrix, frame_size) -> dict | None:
    """Transform all four box corners through a safe 2x3 affine matrix.

    The function is deliberately stricter than drawing code: non-finite,
    off-frame or extreme scale results fail closed instead of being clipped into
    a plausible-looking identity box.
    """
    if not _valid_box(box):
        return None
    try:
        width, height = float(frame_size[0]), float(frame_size[1])
        m = np.asarray(matrix, dtype=float)
    except Exception:
        return None
    if width <= 0 or height <= 0 or m.shape != (2, 3) or not np.all(np.isfinite(m)):
        return None
    x0, y0 = float(box["x"]) * width, float(box["y"]) * height
    x1, y1 = float(box["x"] + box["w"]) * width, float(box["y"] + box["h"]) * height
    corners = np.asarray([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=float)
    aug = np.concatenate([corners, np.ones((4, 1), dtype=float)], axis=1)
    mapped = aug @ m.T
    if not np.all(np.isfinite(mapped)):
        return None
    nx0, ny0 = mapped[:, 0].min() / width, mapped[:, 1].min() / height
    nx1, ny1 = mapped[:, 0].max() / width, mapped[:, 1].max() / height
    nw, nh = nx1 - nx0, ny1 - ny0
    if nw <= 0 or nh <= 0:
        return None
    scale_w = nw / max(float(box["w"]), 1e-9)
    scale_h = nh / max(float(box["h"]), 1e-9)
    if not (0.5 <= scale_w <= 2.0 and 0.5 <= scale_h <= 2.0):
        return None
    if nx1 < -0.15 or ny1 < -0.15 or nx0 > 1.15 or ny0 > 1.15:
        return None
    if nx0 < -0.2 or ny0 < -0.2 or nx1 > 1.2 or ny1 > 1.2:
        return None
    cx0, cy0, cx1, cy1 = max(0.0, nx0), max(0.0, ny0), min(1.0, nx1), min(1.0, ny1)
    if cx1 <= cx0 or cy1 <= cy0:
        return None
    return {"x": cx0, "y": cy0, "w": cx1 - cx0, "h": cy1 - cy0}


def _residual_predict(track: dict, affine_box: dict, media_ms: int) -> dict:
    dt = max(0.0, (int(media_ms) - _last_ms(track, media_ms)) / 1000.0)
    return {
        "x": affine_box["x"] + float(track.get("vx") or 0.0) * dt,
        "y": affine_box["y"] + float(track.get("vy") or 0.0) * dt,
        "w": affine_box["w"],
        "h": affine_box["h"],
    }


def _match_score(pred, det_box) -> float | None:
    if not (_valid_box(pred) and _valid_box(det_box)):
        return None
    ratio = float(det_box["h"]) / max(float(pred["h"]), 1e-9)
    if not (MATCH_SCALE_MIN <= ratio <= MATCH_SCALE_MAX):
        return None
    ov = _iou(pred, det_box)
    px, py = _center(pred); dx, dy = _center(det_box)
    dist_h = math.hypot(px - dx, py - dy) / max(float(pred["h"]), float(det_box["h"]), 1e-6)
    if ov < MATCH_IOU_MIN and dist_h > MATCH_CENTER_H:
        return None
    return 1.7 * ov + max(0.0, 1.0 - dist_h / MATCH_CENTER_H)


def _pixel_box(box, width, height):
    return (
        float(box["x"]) * width,
        float(box["y"]) * height,
        float(box["w"]) * width,
        float(box["h"]) * height,
    )


def _default_camera_estimator(prev_gray, gray, exclude_boxes):
    # Camera motion is background evidence. Work at the same bounded width as
    # the pace engine, then map the verified affine matrix back to native pixels.
    # Person/ball detections and their coordinates remain native observations.
    if prev_gray.shape != gray.shape:
        return None, "frame_shape_changed"
    h, w = gray.shape[:2]
    if w <= motion_compensation.PROC_W:
        return motion_compensation.estimate_camera(prev_gray, gray, exclude_boxes)
    sw = motion_compensation.PROC_W
    sh = max(2, int(round(h * sw / w)))
    sx, sy = sw / w, sh / h
    small_prev = cv2.resize(prev_gray, (sw, sh), interpolation=cv2.INTER_AREA)
    small = cv2.resize(gray, (sw, sh), interpolation=cv2.INTER_AREA)
    excluded = [(x * sx, y * sy, bw * sx, bh * sy) for x, y, bw, bh in exclude_boxes]
    matrix, reason = motion_compensation.estimate_camera(small_prev, small, excluded)
    if matrix is None:
        return None, reason
    # S^-1 M S also handles the one-pixel aspect rounding in a portrait frame.
    matrix = np.asarray(matrix, dtype=float).copy()
    matrix[0, 1] *= sy / sx
    matrix[1, 0] *= sx / sy
    matrix[0, 2] /= sx
    matrix[1, 2] /= sy
    return matrix, reason


def _default_detector():
    import cv_detect
    detector = cv_detect.PersonDetector(enabled=True)
    if not detector.ok:
        return None
    return detector


def _detect_dense_people_and_ball(detector, frame_bgr, include_a7_support=False, *, _detail_pass=False):
    """FIX10A dense detector with isolated A7 support proposals.

    Person detection keeps the production threshold.  A3 receives only sports-
    ball proposals at ``DENSE_BALL_CONF_T``.  When requested, A7 additionally
    receives a separate support-only list down to ``A7_BALL_SUPPORT_CONF_T``.
    Those weak proposals are never exposed to A3/A4/A5 truth.
    """
    import cv_detect
    if detector is None or not getattr(detector, "ok", False):
        return [], []
    H, W = frame_bgr.shape[:2]
    scale = cv_detect.INPUT / max(H, W)
    nw, nh = int(W * scale), int(H * scale)
    img = np.zeros((cv_detect.INPUT, cv_detect.INPUT, 3), np.uint8)
    img[:nh, :nw] = cv2.resize(frame_bgr, (nw, nh))
    blob = cv2.dnn.blobFromImage(
        img, 1 / 255.0, (cv_detect.INPUT, cv_detect.INPUT), swapRB=True
    )
    detector.net.setInput(blob)
    raw = np.asarray(detector.net.forward())
    # OpenCV can return an empty prediction tensor on a valid decoded frame.
    # Treat that as no detections; never let a detector shape abort the whole
    # physical-recall window with an opaque IndexError.
    if raw.size == 0:
        return ([], [], []) if include_a7_support else ([], [])
    if raw.ndim == 3 and raw.shape[0] == 1:
        raw = raw[0]
    if raw.ndim != 2:
        raise ValueError(f"DENSE_DETECTOR_OUTPUT_SHAPE:{raw.shape}")
    # YOLO exports use either (channels, predictions) or its transpose.
    if (raw.shape[0] >= 5 and raw.shape[0] < raw.shape[1]) or raw.shape[1] < 5:
        raw = raw.T
    if raw.shape[1] < 5:
        raise ValueError(f"DENSE_DETECTOR_OUTPUT_SHAPE:{raw.shape}")
    out = raw
    cls = out[:, 4:].argmax(1)
    conf = out[:, 4:].max(1)
    def collect(cid, threshold, *, require_top_class=True):
        class_col = 4 + int(cid)
        if class_col >= out.shape[1]:
            return []
        class_conf = out[:, class_col]
        scores_all = conf if require_top_class else class_conf
        keep = scores_all > float(threshold)
        if require_top_class:
            keep &= cls == cid
        boxes, scores = [], []
        top_classes = []
        top_scores = []
        for row, score, top_class, top_score in zip(
            out[keep], scores_all[keep], cls[keep], conf[keep]
        ):
            cx, cy, bw, bh = row[:4]
            boxes.append([int(cx - bw / 2), int(cy - bh / 2), int(bw), int(bh)])
            scores.append(float(score))
            top_classes.append(int(top_class))
            top_scores.append(float(top_score))
        idx = cv2.dnn.NMSBoxes(boxes, scores, float(threshold), cv_detect.NMS_T)
        rows = []
        for i in np.asarray(idx if idx is not None else [], dtype=int).reshape(-1):
            i = int(i)
            if i < 0 or i >= len(boxes):
                raise ValueError(f"DENSE_DETECTOR_NMS_INDEX:{i}/{len(boxes)}")
            x, y, bw, bh = boxes[i]
            result = {
                "box": {
                    "x": max(0.0, min(1.0, x / (W * scale))),
                    "y": max(0.0, min(1.0, y / (H * scale))),
                    "w": max(1e-4, min(1.0, bw / (W * scale))),
                    "h": max(1e-4, min(1.0, bh / (H * scale))),
                },
                "confidence": scores[i],
            }
            if not require_top_class:
                result.update({
                    "class_specific_support": True,
                    "top_class_id": top_classes[i],
                    "top_class_confidence": top_scores[i],
                })
            rows.append(result)
        return sorted(rows, key=lambda r: float(r.get("confidence") or 0.0), reverse=True)

    people = collect(0, float(cv_detect.CONF_T))
    fsg._annotate_kit_chroma(frame_bgr, people)
    balls = collect(32, float(DENSE_BALL_CONF_T))
    # Portrait padding shrinks the pitch into ~360 detector columns. Only when
    # the ball is missing, inspect the visible players' ground band at native
    # detail. These are detector proposals with the SAME class/confidence gate;
    # downstream same-ball/contact proof remains mandatory.
    if not _detail_pass and not balls and H > 1.5 * W and people:
        heights = sorted(p["box"]["h"] for p in people)
        median = heights[len(heights) // 2]
        field_players = [p for p in people if p["box"]["h"] <= median * 1.8]
        feet = [p["box"]["y"] + p["box"]["h"] for p in field_players]
        y0 = max(0, int((min(feet) - .08) * H))
        y1 = min(H, int((max(feet) + .08) * H))
        if 0 < y1 - y0 <= .45 * H:
            _people, detailed = _detect_dense_people_and_ball(
                detector, frame_bgr[y0:y1, :], _detail_pass=True)
            for candidate in detailed:
                box = candidate["box"]
                box["y"] = (y0 + box["y"] * (y1 - y0)) / H
                box["h"] *= (y1 - y0) / H
                if box["w"] <= .08 and box["h"] <= .04:
                    candidate["source"] = "NATIVE_GROUND_BAND_DETECTOR"
                    balls.append(candidate)
    if not include_a7_support:
        return people, balls
    # A7 is a support-only search channel, so read the sports-ball class score
    # itself even when another class narrowly wins argmax.  This does not lower
    # A3's ball floor and cannot create contact/event truth by itself.
    support = collect(
        32, float(A7_BALL_SUPPORT_CONF_T), require_top_class=False
    )[:A7_BALL_SUPPORT_MAX]
    for row in support:
        row["a3_eligible"] = bool(
            row.get("top_class_id") == 32
            and float(row.get("confidence") or 0.0) >= float(DENSE_BALL_CONF_T)
        )
        row["support_only"] = not row["a3_eligible"]
        row["proof_eligible"] = False
    return people, balls, support


def _is_direct_tap_target(frame):
    target = frame.get("global_target") or {}
    return bool(
        target.get("status") == "VERIFIED"
        and target.get("proof_eligible") is True
        and target.get("authority_tap") is True
        and target.get("authority_primary_source") == "USER_TAP"
        and target.get("authority_reason") in {"OK_EXACT", "OK_NEAREST_TAP_FRAME"}
        and _num(target.get("authority_media_ms"))
        and abs(int(frame["media_ms"]) - int(target["authority_media_ms"])) <= TAP_FRAME_NEAR_MS
    )


def _dense_target_kit_samples(frames, *, authority_ms=None):
    """Collect kit chroma only along a direct-tap body's contiguous local track."""
    rows = sorted(
        [frame for frame in (frames or [])
         if isinstance(frame, dict) and _num(frame.get("media_ms"))],
        key=lambda frame: int(frame["media_ms"]),
    )
    samples = []
    seen = set()
    anchors = [
        (index, frame) for index, frame in enumerate(rows)
        if _is_direct_tap_target(frame)
        and (authority_ms is None or int(frame["media_ms"]) == authority_ms)
    ]
    for index, anchor in anchors:
        target = anchor.get("global_target") or {}
        track_id = target.get("local_track_id")
        if not isinstance(track_id, str):
            continue
        anchor_ms = int(anchor["media_ms"])
        scene = anchor.get("scene_id")
        for direction in (1, -1):
            cursor = index if direction == 1 else index - 1
            while 0 <= cursor < len(rows):
                frame = rows[cursor]
                delta = abs(int(frame["media_ms"]) - anchor_ms)
                if delta > DENSE_TEAM_TAP_CONTINUITY_MS:
                    break
                if (
                    frame.get("scene_id") != scene
                    or frame.get("cut_barrier") is True
                    or frame.get("used_fallback") is True
                    or frame.get("time_authority") != "ACTUAL_MEDIA_PTS"
                ):
                    break
                bodies = [
                    player for player in frame.get("players") or []
                    if isinstance(player, dict)
                    and player.get("local_track_id") == track_id
                    and player.get("association_state") != "HYPOTHESES"
                    and fsg._valid_chroma(player.get("kit_chroma"))
                ]
                if len(bodies) != 1:
                    break
                key = (str(scene), int(frame["media_ms"]), track_id)
                if key not in seen:
                    seen.add(key)
                    samples.append(deepcopy(bodies[0]["kit_chroma"]))
                cursor += direction
    return samples


def _apply_dense_team_labels(frames):
    samples = _dense_target_kit_samples(frames)
    diagnostic = fsg.apply_dense_team_authority(frames, samples)
    if diagnostic.get("status") != "ok":
        # Different tap episodes can have different lighting or body crops.
        # A failed pooled model must not erase independently proven local kits.
        # Fit each bounded direct-tap episode under the SAME team gates, then
        # publish only labels on which all successful overlapping models agree.
        indexed = sorted(((i, f) for i, f in enumerate(frames or [])
                          if isinstance(f, dict) and _num(f.get("media_ms"))),
                         key=lambda row: int(row[1]["media_ms"]))
        proposals, models = {}, []
        for anchor_index, (_, anchor) in enumerate(indexed):
            ms = int(anchor["media_ms"])
            if not _is_direct_tap_target(anchor):
                continue
            region = []
            for direction in (1, -1):
                cursor = anchor_index if direction == 1 else anchor_index - 1
                while 0 <= cursor < len(indexed):
                    original_index, frame = indexed[cursor]
                    if (abs(int(frame["media_ms"]) - ms) > DENSE_TEAM_TAP_CONTINUITY_MS
                            or frame.get("scene_id") != anchor.get("scene_id")
                            or frame.get("cut_barrier") is True
                            or frame.get("used_fallback") is True
                            or frame.get("time_authority") != "ACTUAL_MEDIA_PTS"):
                        break
                    region.append((original_index, deepcopy(frame)))
                    cursor += direction
            local_rows = [row for _, row in region]
            for row in local_rows:
                for player in row.get("players") or []:
                    if not isinstance(player, dict):
                        continue
                    if player.get("team_source") == fsg.DENSE_TEAM_SOURCE:
                        for key in ("team", "team_confidence", "team_source"):
                            player.pop(key, None)
            local_samples = _dense_target_kit_samples(local_rows, authority_ms=ms)
            model = fsg.apply_dense_team_authority(local_rows, local_samples)
            models.append({**model, "authority_media_ms": ms,
                           "scene_id": anchor.get("scene_id")})
            if model.get("status") != "ok":
                continue
            for original_index, frame in region:
                for player_index, player in enumerate(frame.get("players") or []):
                    if not isinstance(player, dict):
                        continue
                    if player.get("team_source") == fsg.DENSE_TEAM_SOURCE:
                        proposals.setdefault((original_index, player_index), []).append(player)
        applied, conflicts = 0, 0
        for (frame_index, player_index), votes in proposals.items():
            if len({vote["team"] for vote in votes}) != 1:
                conflicts += 1
                continue
            player = frames[frame_index]["players"][player_index]
            player.update(team=votes[0]["team"],
                          team_confidence=min(vote["team_confidence"] for vote in votes),
                          team_source=fsg.DENSE_TEAM_SOURCE)
            applied += 1
        diagnostic = {**diagnostic, "pooled_status": diagnostic["status"],
                      "local_models": models, "conflicting_detections": conflicts,
                      "labeled_detections": applied,
                      "status": "partial" if applied else "unresolved"}
    if diagnostic.get("status") in {"ok", "partial"}:
        for frame in frames or []:
            target = frame.get("global_target") if isinstance(frame, dict) else None
            if not isinstance(target, dict) or target.get("status") != "VERIFIED":
                continue
            player = next((
                row for row in frame.get("players") or []
                if isinstance(row, dict)
                and row.get("local_track_id") == target.get("local_track_id")
            ), None)
            if isinstance(player, dict):
                target["body_team"] = player.get("team")
                target["body_team_confidence"] = player.get("team_confidence")
                target["body_team_source"] = player.get("team_source")
    return diagnostic


def _nearest_tap_point(identity_authority: dict, media_ms: int):
    """Return one direct user-tap row on its nearest decoded PTS.

    The selected box remains the authority geometry.  Competing equidistant
    taps fail closed, although ordinary reports space taps many seconds apart.
    """
    authority = identity_authority if isinstance(identity_authority, dict) else {}
    rows = []
    for row in authority.get("target_points") or []:
        if not (
            isinstance(row, dict)
            and _num(row.get("media_ms"))
            and abs(int(round(float(row["media_ms"]))) - int(media_ms)) <= TAP_FRAME_NEAR_MS
            and row.get("tap_authority") is True
            and row.get("proof_eligible") is True
            and _valid_box(row.get("box"))
            and (
                row.get("primary_source") == "USER_TAP"
                or "USER_TAP" in (row.get("sources") or [])
            )
        ):
            continue
        rows.append(row)
    if not rows:
        return None
    rows.sort(key=lambda row: abs(int(round(float(row["media_ms"]))) - int(media_ms)))
    best_delta = abs(int(round(float(rows[0]["media_ms"]))) - int(media_ms))
    tied = [
        row for row in rows
        if abs(int(round(float(row["media_ms"]))) - int(media_ms)) == best_delta
    ]
    if len(tied) != 1:
        return None
    return deepcopy(tied[0])


def _resolve_dense_target(identity_authority: dict, media_ms: int, players: list[dict], *,
                          allow_nearest_tap=True, tap_override=None) -> dict:
    authority = identity_authority if isinstance(identity_authority, dict) else {}
    resolved = deepcopy(tap_override) if isinstance(tap_override, dict) else (
        _nearest_tap_point(authority, int(media_ms)) if allow_nearest_tap else None
    )
    if resolved is not None:
        why = "OK_NEAREST_TAP_FRAME"
    else:
        resolved, why = uia.resolve_target_at(
            authority,
            int(media_ms),
            proof_required=False,
            max_interp_ms=TARGET_NEAR_MS,
        )
    if not isinstance(resolved, dict) or not _valid_box(resolved.get("box")):
        return {
            "status": "UNRESOLVED", "reason": why,
            "local_track_id": None, "candidate_local_track_ids": [],
            "proof_eligible": False,
        }
    rb = resolved["box"]
    authority_evidence = {
        "authority_box": deepcopy(rb),
        "authority_reason": why,
        "authority_tap": resolved.get("tap_authority") is True,
        "authority_primary_source": resolved.get("primary_source"),
        "authority_media_ms": resolved.get("media_ms"),
        "authority_frame_delta_ms": (
            int(media_ms) - int(round(float(resolved["media_ms"])))
            if _num(resolved.get("media_ms")) else None
        ),
    }
    ranked = []
    for p in players:
        if not isinstance(p, dict) or not _valid_box(p.get("box")):
            continue
        pb = p["box"]
        ov = _iou(rb, pb)
        rx, ry = _center(rb); px, py = _center(pb)
        dist_h = math.hypot(rx - px, ry - py) / max(float(rb["h"]), float(pb["h"]), 1e-6)
        if ov >= TARGET_MATCH_IOU_MIN or dist_h <= TARGET_MATCH_CENTER_H:
            score = 1.8 * ov + max(0.0, 1.0 - dist_h / TARGET_MATCH_CENTER_H)
            ranked.append({"score": score, "player": p})
    ranked.sort(reverse=True, key=lambda x: float(x["score"]))

    normal = [row for row in ranked if isinstance(row["player"].get("local_track_id"), str)]
    if normal:
        ids = [row["player"]["local_track_id"] for row in normal[:3]]
        ambiguous = len(normal) > 1 and float(normal[0]["score"]) - float(normal[1]["score"]) < TARGET_MATCH_AMBIG_MARGIN
        if ambiguous or resolved.get("proof_eligible") is not True:
            return {
                "status": "HYPOTHESES",
                "reason": "DENSE_TARGET_AMBIGUITY" if ambiguous else "NON_PROOF_IDENTITY_CONTINUITY",
                "local_track_id": None,
                "candidate_local_track_ids": ids,
                "proof_eligible": False,
            }
        winner = normal[0]["player"]
        return {
            "status": "VERIFIED", "reason": why,
            "local_track_id": winner["local_track_id"],
            "candidate_local_track_ids": [winner["local_track_id"]],
            "proof_eligible": True,
            "body_box": deepcopy(winner.get("box")),
            "body_confidence": winner.get("confidence"),
            "body_team": winner.get("team"),
            "body_team_confidence": winner.get("team_confidence"),
            "body_team_source": winner.get("team_source"),
            **authority_evidence,
        }

    # Target-only collapse of detector duplicates. This is permitted only when
    # proof-level target geometry independently exists and every matching raw
    # hypothesis points to the same single underlying local track. The raw
    # HYPOTHESES remain untouched.
    hypotheses = [row for row in ranked if row["player"].get("association_state") == "HYPOTHESES"]
    candidate_sets = [
        {x for x in (row["player"].get("candidate_local_track_ids") or []) if isinstance(x, str)}
        for row in hypotheses
    ]
    union = set().union(*candidate_sets) if candidate_sets else set()
    unique_geometry = bool(
        hypotheses and (
            len(hypotheses) == 1
            or float(hypotheses[0]["score"]) - float(hypotheses[1]["score"]) >= TARGET_MATCH_AMBIG_MARGIN
        )
    )
    if (
        resolved.get("proof_eligible") is True
        and hypotheses
        and union and len(union) == 1
        and all(s == union for s in candidate_sets)
        and unique_geometry
    ):
        track = next(iter(union))
        winner = hypotheses[0]["player"]
        predicted = (winner.get("candidate_predicted_boxes") or {}).get(track)
        return {
            "status": "VERIFIED",
            "reason": "PROOF_TARGET_SINGLE_CANDIDATE_HYPOTHESIS_COLLAPSE",
            "local_track_id": track,
            "candidate_local_track_ids": [track],
            "proof_eligible": True,
            "body_box": deepcopy(winner.get("box")),
            "body_predicted_box": deepcopy(predicted) if _valid_box(predicted) else None,
            "body_confidence": winner.get("confidence"),
            "body_team": winner.get("team"),
            "body_team_confidence": winner.get("team_confidence"),
            "body_team_source": winner.get("team_source"),
            "body_association_state": "VERIFIED_TARGET_HYPOTHESIS_COLLAPSE",
            "collapsed_hypothesis_count": len(hypotheses),
            **authority_evidence,
        }
    ids = sorted(union) if union else []
    return {
        "status": "HYPOTHESES" if ranked else "UNRESOLVED",
        "reason": "DENSE_TARGET_HYPOTHESIS_NOT_COLLAPSIBLE" if ranked else "DENSE_TARGET_BODY_NOT_RESOLVED",
        "local_track_id": None,
        "candidate_local_track_ids": ids,
        "proof_eligible": False,
    }


def _apply_nearest_tap_frames(frames, authority):
    """Map each direct user tap to exactly one nearest decoded source frame."""
    rows = [frame for frame in (frames or []) if isinstance(frame, dict) and _num(frame.get("media_ms"))]
    taps = [
        point for point in (authority or {}).get("target_points") or []
        if isinstance(point, dict)
        and _num(point.get("media_ms"))
        and point.get("tap_authority") is True
        and point.get("proof_eligible") is True
        and _valid_box(point.get("box"))
        and (
            point.get("primary_source") == "USER_TAP"
            or "USER_TAP" in (point.get("sources") or [])
        )
    ]
    for tap in taps:
        tap_ms = int(round(float(tap["media_ms"])))
        candidates = [
            frame for frame in rows
            if abs(int(frame["media_ms"]) - tap_ms) <= TAP_FRAME_NEAR_MS
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda frame: abs(int(frame["media_ms"]) - tap_ms))
        best_delta = abs(int(candidates[0]["media_ms"]) - tap_ms)
        if sum(abs(int(frame["media_ms"]) - tap_ms) == best_delta for frame in candidates) != 1:
            continue
        frame = candidates[0]
        frame["global_target"] = _resolve_dense_target(
            authority, int(frame["media_ms"]), frame.get("players") or [],
            allow_nearest_tap=False, tap_override=tap,
        )

def _verify_bracketed_dense_target(frames, authority):
    """Verify continuous local body between two independent exact target proofs.

    The existing authority stays untouched. A cut, missing frame, competing
    body, predicted/ambiguous local association, or identity barrier prevents
    promotion for the entire interval.
    """
    exact = [i for i, frame in enumerate(frames)
             if (frame.get("global_target") or {}).get("status") == "VERIFIED"
             and (frame.get("global_target") or {}).get("reason") in {
                 "OK_EXACT", "OK_NEAREST_TAP_FRAME"
             }
             and frame.get("used_fallback") is not True]
    for left, right in zip(exact, exact[1:]):
        start, end = frames[left], frames[right]
        track = (start.get("global_target") or {}).get("local_track_id")
        if (not track or track != (end.get("global_target") or {}).get("local_track_id")
                or start.get("scene_id") != end.get("scene_id")
                or int(end["media_ms"]) - int(start["media_ms"]) > TARGET_NEAR_MS
                or right == left + 1):
            continue
        middle = frames[left + 1:right]
        if any(f.get("cut_barrier") or f.get("used_fallback")
               or f.get("scene_id") != start.get("scene_id")
               or f.get("time_authority") != "ACTUAL_MEDIA_PTS"
               or (f.get("global_target") or {}).get("reason") != "NON_PROOF_IDENTITY_CONTINUITY"
               or (f.get("global_target") or {}).get("candidate_local_track_ids") != [track]
               or len([p for p in f.get("players") or []
                       if p.get("local_track_id") == track
                       and p.get("association_state") == "VERIFIED_LOCAL"]) != 1
               for f in middle):
            continue
        # The canonical resolver enforces unresolved intervals and scene cuts.
        # Its interpolation is only a geometry cross-check; independent dense
        # tracking across every source frame supplies the additional proof.
        if any(uia.resolve_target_at(authority, int(f["media_ms"]),
                                     max_interp_ms=TARGET_NEAR_MS)[1] != "OK_INTERPOLATED"
               for f in middle):
            continue
        for f in middle:
            player = next(p for p in f["players"] if p.get("local_track_id") == track)
            f["global_target"] = {
                "status": "VERIFIED", "reason": "DENSE_TWO_ANCHOR_CONTINUITY",
                "local_track_id": track, "candidate_local_track_ids": [track],
                "proof_eligible": True, "body_box": deepcopy(player["box"]),
                "body_confidence": player.get("confidence"),
                "body_team": player.get("team"),
                "body_team_confidence": player.get("team_confidence"),
                "body_team_source": player.get("team_source"),
            }


def refine_window(dense_frames, scene_graph: dict | None, identity_authority: dict | None,
                  scene_id: str, detector_fn=None, camera_estimator=None) -> dict:
    """Refine scene-local tracks over one already bounded dense window.

    ``detector_fn(frame_bgr)`` may be injected for deterministic tests and may
    return ``(people, balls)`` or ``(people, balls, a7_support)``.  Production
    performs one detector forward pass per dense frame; weak A7 support proposals
    remain isolated from A3/A4/A5 truth.  No image arrays are retained.
    """
    scene = str(scene_id or "")
    frames_iter = iter(dense_frames or [])
    seed = seed_scene_tracks(scene_graph, scene, 0)
    live = deepcopy(seed.get("tracks") or [])
    next_id = int(seed.get("next_id") or 1)
    seeded = False
    output_frames = []
    prev_gray = None
    active_scene = scene
    detector = None
    if detector_fn is None:
        detector = _default_detector()
        if detector is None:
            return {"version": VERSION, "status": "skipped", "reason": "detector_unavailable",
                    "scene_id": scene, "frames": [], "metrics": {}}
        detector_fn = lambda frame: _detect_dense_people_and_ball(detector, frame, include_a7_support=True)
    if camera_estimator is None:
        camera_estimator = _default_camera_estimator

    for dense in frames_iter:
        if not isinstance(dense, dict) or not _num(dense.get("media_ms")):
            continue
        frame = dense.get("frame_bgr")
        if frame is None or not hasattr(frame, "shape"):
            continue
        media_ms = int(round(float(dense["media_ms"])))
        row_scene = str(dense.get("scene_id") or active_scene)
        cut = dense.get("cut") is True or (active_scene and row_scene != active_scene)
        if not seeded:
            seed = seed_scene_tracks(scene_graph, row_scene, media_ms)
            live = deepcopy(seed.get("tracks") or [])
            next_id = max(next_id, int(seed.get("next_id") or 1))
            active_scene = row_scene
            seeded = True
        elif cut:
            # Hard barrier: never carry a scene-local id through a cut.
            live = []
            prev_gray = None
            active_scene = row_scene

        detected = detector_fn(frame)
        a7_support = []
        if isinstance(detected, (tuple, list)) and len(detected) == 3:
            people, balls, a7_support = detected
        else:
            people, balls = detected
        detections = [d for d in (people or []) if isinstance(d, dict) and _valid_box(d.get("box"))]
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        matrix = np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=float)
        camera_state = "SEED_OR_FIRST_FRAME"
        if prev_gray is not None and live:
            exclude = [_pixel_box(tr["box"], w, h) for tr in live if _valid_box(tr.get("box"))]
            try:
                matrix_result, camera_reason = camera_estimator(prev_gray, gray, exclude)
            except Exception:
                matrix_result, camera_reason = None, "error"
            if matrix_result is None:
                matrix = None
                camera_state = f"UNRESOLVED:{camera_reason}"
            else:
                matrix = np.asarray(matrix_result, dtype=float)
                camera_state = "AFFINE_VERIFIED"

        predictions = {}
        camera_boxes = {}
        if matrix is not None:
            for ti, tr in enumerate(live):
                if media_ms - _last_ms(tr, media_ms) > TRACK_MAX_GAP_MS:
                    continue
                # Camera matrices are between successive decoded frames, even
                # when a player detection is missing. Keep their accumulated
                # effect separately from the last measured body and velocity.
                tb = transform_box_affine(tr.get("camera_box", tr.get("box")), matrix, (w, h))
                tr["camera_box"] = tb
                if tb is not None:
                    pred = _residual_predict(tr, tb, media_ms)
                    if _valid_box(pred):
                        predictions[ti] = pred
                        camera_boxes[ti] = tb
        else:
            for tr in live:
                tr["camera_box"] = None  # an unknown camera step breaks continuity

        # Candidate scores per existing track.  Near-equal alternatives remain
        # unbound hypotheses instead of being decided by detector/list order.
        per_track = {}
        for ti, pred in predictions.items():
            ranked = []
            for di, det in enumerate(detections):
                score = _match_score(pred, det["box"])
                if score is not None:
                    ranked.append((score, di))
            ranked.sort(reverse=True)
            per_track[ti] = ranked

        ambiguous_det_candidates: dict[int, set[str]] = {}
        assign_pairs = []
        for ti, ranked in per_track.items():
            if not ranked:
                continue
            tr_id = live[ti]["local_track_id"]
            if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < MATCH_AMBIG_MARGIN:
                for _score, di in ranked[:2]:
                    ambiguous_det_candidates.setdefault(di, set()).add(tr_id)
                continue
            for score, di in ranked:
                assign_pairs.append((score, ti, di))
        assign_pairs.sort(reverse=True)

        # Resolve ambiguity in BOTH directions. Two old tracks competing for
        # one detected body must not acquire identity by greedy list order.
        by_detection = {}
        for score, ti, di in assign_pairs:
            by_detection.setdefault(di, []).append((score, ti))
        for di, choices in by_detection.items():
            if len(choices) > 1 and choices[0][0] - choices[1][0] < MATCH_AMBIG_MARGIN:
                ambiguous_det_candidates.setdefault(di, set()).update(
                    live[ti]["local_track_id"] for score, ti in choices
                    if choices[0][0] - score < MATCH_AMBIG_MARGIN)

        used_tracks, used_dets = set(), set()
        players_out = []
        for score, ti, di in assign_pairs:
            if ti in used_tracks or di in used_dets or di in ambiguous_det_candidates:
                continue
            tr, det = live[ti], detections[di]
            pred = predictions.get(ti)
            if pred is None:
                continue
            dt = max(1e-3, (media_ms - _last_ms(tr, media_ms)) / 1000.0)
            # Measure player motion from the camera-transformed last box.
            # Prediction error would subtract the previous velocity again.
            pcx, pcy = _center(camera_boxes[ti]); dcx, dcy = _center(det["box"])
            tr["vx"] = (dcx - pcx) / dt
            tr["vy"] = (dcy - pcy) / dt
            tr["box"] = _box(det["box"])
            tr["camera_box"] = _box(det["box"])
            tr["last_ms"] = media_ms
            if det.get("team") is not None:
                tr["team"] = det.get("team")
                tr["team_confidence"] = det.get("team_confidence")
                tr["team_source"] = det.get("team_source")
            if fsg._valid_chroma(det.get("kit_chroma")):
                tr["kit_chroma"] = deepcopy(det["kit_chroma"])
            used_tracks.add(ti); used_dets.add(di)
            players_out.append({
                "local_track_id": tr["local_track_id"],
                "candidate_local_track_ids": [tr["local_track_id"]],
                "box": _box(det["box"]),
                "confidence": float(det.get("confidence") or 0.0),
                "association_state": "VERIFIED_LOCAL",
                "association_reason": camera_state,
                "association_score": round(float(score), 4),
                "team": tr.get("team"),
                "team_confidence": tr.get("team_confidence"),
                "team_source": tr.get("team_source"),
                "kit_chroma": deepcopy(det.get("kit_chroma"))
                if fsg._valid_chroma(det.get("kit_chroma")) else None,
            })

        # Preserve the motion-predicted geometry behind unresolved hypotheses.
        # It remains non-canonical and is consumed only by a later proof-backed
        # GLOBAL_TARGET hypothesis collapse.
        predicted_box_by_track = {
            live[ti]["local_track_id"]: _box(pred)
            for ti, pred in predictions.items()
            if ti < len(live) and isinstance(live[ti].get("local_track_id"), str) and _valid_box(pred)
        }

        # Explicit unresolved close-body hypotheses.  Do not allocate a new id
        # to either body because that would silently collapse the alternative.
        for di, candidates in sorted(ambiguous_det_candidates.items()):
            if di in used_dets:
                continue
            det = detections[di]
            players_out.append({
                "local_track_id": None,
                "candidate_local_track_ids": sorted(candidates),
                "candidate_predicted_boxes": {
                    tid: deepcopy(predicted_box_by_track[tid])
                    for tid in sorted(candidates) if tid in predicted_box_by_track
                },
                "box": _box(det["box"]),
                "confidence": float(det.get("confidence") or 0.0),
                "association_state": "HYPOTHESES",
                "association_reason": "CLOSE_EQUAL_LOCAL_TRACK_CANDIDATES",
                "association_score": None,
                "team": det.get("team"),
                "team_confidence": det.get("team_confidence"),
                "team_source": det.get("team_source"),
                "kit_chroma": deepcopy(det.get("kit_chroma"))
                if fsg._valid_chroma(det.get("kit_chroma")) else None,
            })
            used_dets.add(di)

        # Unmatched detections are new scene-local bodies and must receive ids
        # strictly above the existing scene maximum; they can never steal an id.
        for di, det in enumerate(detections):
            if di in used_dets:
                continue
            tid = _new_track_id(next_id); next_id += 1
            tr = {
                "local_track_id": tid,
                "box": _box(det["box"]),
                "last_ms": media_ms,
                "vx": 0.0, "vy": 0.0,
                "team": det.get("team"),
                "team_confidence": det.get("team_confidence"),
                "team_source": det.get("team_source"),
                "kit_chroma": deepcopy(det.get("kit_chroma"))
                if fsg._valid_chroma(det.get("kit_chroma")) else None,
            }
            live.append(tr)
            players_out.append({
                "local_track_id": tid,
                "candidate_local_track_ids": [tid],
                "box": _box(det["box"]),
                "confidence": float(det.get("confidence") or 0.0),
                "association_state": "NEW_LOCAL_TRACK",
                "association_reason": "UNMATCHED_DETECTION",
                "association_score": None,
                "team": tr.get("team"),
                "team_confidence": tr.get("team_confidence"),
                "team_source": tr.get("team_source"),
                "kit_chroma": deepcopy(det.get("kit_chroma"))
                if fsg._valid_chroma(det.get("kit_chroma")) else None,
            })

        # Expire only by time; unresolved/ambiguous bodies do not rewrite the
        # last accepted geometry of an existing track.
        live = [tr for tr in live if media_ms - _last_ms(tr, media_ms) <= TRACK_MAX_GAP_MS]
        target_map = _resolve_dense_target(
            identity_authority or {}, media_ms, players_out, allow_nearest_tap=False
        )
        output_frames.append({
            "media_ms": media_ms,
            "scene_id": active_scene,
            "cut_barrier": bool(cut),
            "camera_state": camera_state,
            "players": players_out,
            "ball_candidates": deepcopy(balls or []),
            "a7_ball_support_candidates": deepcopy(a7_support or []),
            "global_target": target_map,
            "time_authority": dense.get("time_authority"),
            "used_fallback": bool(dense.get("used_fallback")),
        })
        prev_gray = gray

    _apply_nearest_tap_frames(output_frames, identity_authority or {})
    _verify_bracketed_dense_target(output_frames, identity_authority or {})
    team_authority = _apply_dense_team_labels(output_frames)
    return {
        "version": VERSION,
        "status": "ok" if output_frames else "empty",
        "scene_id": scene,
        "frames": output_frames,
        "team_authority": team_authority,
        "metrics": {
            "frames": len(output_frames),
            "players": sum(len(f.get("players") or []) for f in output_frames),
            "target_verified_frames": sum(
                (f.get("global_target") or {}).get("status") == "VERIFIED" for f in output_frames
            ),
            "target_hypothesis_frames": sum(
                (f.get("global_target") or {}).get("status") == "HYPOTHESES" for f in output_frames
            ),
            "team_labeled_players": sum(
                player.get("team") is not None
                for frame in output_frames for player in (frame.get("players") or [])
                if isinstance(player, dict)
            ),
        },
    }
