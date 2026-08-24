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
DENSE_BALL_CONF_T = 0.03
A7_BALL_SUPPORT_CONF_T = 0.001
A7_BALL_SUPPORT_MAX = 12


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
    return motion_compensation.estimate_camera(prev_gray, gray, exclude_boxes)


def _default_detector():
    import cv_detect
    detector = cv_detect.PersonDetector(enabled=True)
    if not detector.ok:
        return None
    return detector


def _detect_dense_people_and_ball(detector, frame_bgr, include_a7_support=False):
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
    out = detector.net.forward()[0].T
    cls = out[:, 4:].argmax(1)
    conf = out[:, 4:].max(1)
    def collect(cid, threshold):
        keep = (cls == cid) & (conf > float(threshold))
        boxes, scores = [], []
        for row, score in zip(out[keep], conf[keep]):
            cx, cy, bw, bh = row[:4]
            boxes.append([int(cx - bw / 2), int(cy - bh / 2), int(bw), int(bh)])
            scores.append(float(score))
        idx = cv2.dnn.NMSBoxes(boxes, scores, float(threshold), cv_detect.NMS_T)
        rows = []
        for i in np.array(idx).flatten() if len(idx) else []:
            x, y, bw, bh = boxes[i]
            rows.append({
                "box": {
                    "x": max(0.0, min(1.0, x / (W * scale))),
                    "y": max(0.0, min(1.0, y / (H * scale))),
                    "w": max(1e-4, min(1.0, bw / (W * scale))),
                    "h": max(1e-4, min(1.0, bh / (H * scale))),
                },
                "confidence": scores[i],
            })
        return sorted(rows, key=lambda r: float(r.get("confidence") or 0.0), reverse=True)

    people = collect(0, float(cv_detect.CONF_T))
    balls = collect(32, float(DENSE_BALL_CONF_T))
    if not include_a7_support:
        return people, balls
    support = collect(32, float(A7_BALL_SUPPORT_CONF_T))[:A7_BALL_SUPPORT_MAX]
    for row in support:
        row["support_only"] = float(row.get("confidence") or 0.0) < float(DENSE_BALL_CONF_T)
        row["proof_eligible"] = False
    return people, balls, support


def _resolve_dense_target(identity_authority: dict, media_ms: int, players: list[dict]) -> dict:
    resolved, why = uia.resolve_target_at(
        identity_authority if isinstance(identity_authority, dict) else {},
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
            ranked.append((score, p.get("local_track_id")))
    ranked = [x for x in sorted(ranked, reverse=True, key=lambda x: x[0]) if isinstance(x[1], str)]
    if not ranked:
        return {
            "status": "UNRESOLVED", "reason": "DENSE_TARGET_BODY_NOT_RESOLVED",
            "local_track_id": None, "candidate_local_track_ids": [],
            "proof_eligible": False,
        }
    ids = [x[1] for x in ranked[:3]]
    ambiguous = len(ranked) > 1 and ranked[0][0] - ranked[1][0] < TARGET_MATCH_AMBIG_MARGIN
    if ambiguous or resolved.get("proof_eligible") is not True:
        return {
            "status": "HYPOTHESES",
            "reason": "DENSE_TARGET_AMBIGUITY" if ambiguous else "NON_PROOF_IDENTITY_CONTINUITY",
            "local_track_id": None,
            "candidate_local_track_ids": ids,
            "proof_eligible": False,
        }
    return {
        "status": "VERIFIED", "reason": why,
        "local_track_id": ranked[0][1],
        "candidate_local_track_ids": [ranked[0][1]],
        "proof_eligible": True,
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
        if matrix is not None:
            for ti, tr in enumerate(live):
                if media_ms - _last_ms(tr, media_ms) > TRACK_MAX_GAP_MS:
                    continue
                tb = transform_box_affine(tr.get("box"), matrix, (w, h))
                if tb is not None:
                    pred = _residual_predict(tr, tb, media_ms)
                    if _valid_box(pred):
                        predictions[ti] = pred

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
            pcx, pcy = _center(pred); dcx, dcy = _center(det["box"])
            tr["vx"] = (dcx - pcx) / dt
            tr["vy"] = (dcy - pcy) / dt
            tr["box"] = _box(det["box"])
            tr["last_ms"] = media_ms
            if det.get("team") is not None:
                tr["team"] = det.get("team")
                tr["team_confidence"] = det.get("team_confidence")
                tr["team_source"] = det.get("team_source")
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
            })

        # Explicit unresolved close-body hypotheses.  Do not allocate a new id
        # to either body because that would silently collapse the alternative.
        for di, candidates in sorted(ambiguous_det_candidates.items()):
            if di in used_dets:
                continue
            det = detections[di]
            players_out.append({
                "local_track_id": None,
                "candidate_local_track_ids": sorted(candidates),
                "box": _box(det["box"]),
                "confidence": float(det.get("confidence") or 0.0),
                "association_state": "HYPOTHESES",
                "association_reason": "CLOSE_EQUAL_LOCAL_TRACK_CANDIDATES",
                "association_score": None,
                "team": det.get("team"),
                "team_confidence": det.get("team_confidence"),
                "team_source": det.get("team_source"),
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
            })

        # Expire only by time; unresolved/ambiguous bodies do not rewrite the
        # last accepted geometry of an existing track.
        live = [tr for tr in live if media_ms - _last_ms(tr, media_ms) <= TRACK_MAX_GAP_MS]
        target_map = _resolve_dense_target(identity_authority or {}, media_ms, players_out)
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

    return {
        "version": VERSION,
        "status": "ok" if output_frames else "empty",
        "scene_id": scene,
        "frames": output_frames,
        "metrics": {
            "frames": len(output_frames),
            "players": sum(len(f.get("players") or []) for f in output_frames),
            "target_verified_frames": sum(
                (f.get("global_target") or {}).get("status") == "VERIFIED" for f in output_frames
            ),
            "target_hypothesis_frames": sum(
                (f.get("global_target") or {}).get("status") == "HYPOTHESES" for f in output_frames
            ),
        },
    }
