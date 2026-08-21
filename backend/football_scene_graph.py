"""FIX 09B.1 — unified multi-player + ball scene graph.

The scene graph is the spatial/causal substrate for later football-sequence
reasoning.  It consumes the FIX09B.0 GLOBAL_TARGET authority; it never creates
a competing target identity.

Architecture
------------
VIDEO → local YOLO person + sports-ball candidates → scene-local MOT
      → map GLOBAL_TARGET into those local tracks
      → ball continuity + possession hypotheses
      → one time-aligned scene graph.

Important contracts
-------------------
* GLOBAL_TARGET comes only from ``unified_identity_authority``.
* Every other player gets a scene-local id; ids never cross hard cuts.
* Ambiguous target mapping remains a bounded candidate set, never a guess.
* Ball detection is supporting evidence, not event authority. Missing/ambiguous
  ball frames are explicit and may be resolved later from neighbouring frames.
* No goal/assist/pass/dribble classification happens here.
* All timestamps are canonical media milliseconds.
* Pure ``assemble_scene_graph`` is independently testable without video/model.
"""
from __future__ import annotations

import math
import os
import time
from copy import deepcopy

import unified_identity_authority as uia

VERSION = 1
HZ = float(os.environ.get("FOOTBALL_SCENE_GRAPH_HZ", "8"))

# Scene-local player association.  Values are deliberately body-relative so
# the same code works across wide/close camera scales.
PLAYER_IOU_MIN = 0.06
PLAYER_CENTER_H = 1.25
PLAYER_SCALE_MIN = 0.52
PLAYER_SCALE_MAX = 1.90
PLAYER_MAX_GAP_MS = 900

# GLOBAL_TARGET → local track mapping.
TARGET_IOU_MIN = 0.14
TARGET_CENTER_H = 0.80
TARGET_AMBIG_MARGIN = 0.18
TARGET_NEAR_MS = 250

# Ball continuity / possession are hypothesis signals only.
BALL_MAX_GAP_MS = 650
BALL_MAX_SPEED_FW_S = 2.8
BALL_SCORE_MARGIN = 0.12
POSSESSION_MAX_H = 1.10
POSSESSION_AMBIG_MARGIN_H = 0.22


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _valid_box(b) -> bool:
    if not isinstance(b, dict):
        return False
    try:
        x, y, w, h = (float(b[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return False
    return -0.05 <= x <= 1.05 and -0.05 <= y <= 1.05 and 0 < w <= 1.1 and 0 < h <= 1.1


def _box(b):
    return {k: float(b[k]) for k in ("x", "y", "w", "h")}


def _center(b):
    return b["x"] + b["w"] / 2.0, b["y"] + b["h"] / 2.0


def _foot(b):
    return b["x"] + b["w"] / 2.0, b["y"] + b["h"]


def _iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]
    bx0, by0, bx1, by1 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


def _dist(a, b) -> float:
    ax, ay = _center(a)
    bx, by = _center(b)
    return math.hypot(ax - bx, ay - by)


def _scale_ok(a, b) -> bool:
    if min(a["h"], b["h"]) <= 0:
        return False
    r = a["h"] / b["h"]
    return PLAYER_SCALE_MIN <= r <= PLAYER_SCALE_MAX


def _player_match_score(pred, det) -> float | None:
    if not (_valid_box(pred) and _valid_box(det)) or not _scale_ok(pred, det):
        return None
    ov = _iou(pred, det)
    d_h = _dist(pred, det) / max(pred["h"], det["h"], 1e-6)
    if ov < PLAYER_IOU_MIN and d_h > PLAYER_CENTER_H:
        return None
    return 1.6 * ov + max(0.0, 1.0 - d_h / PLAYER_CENTER_H)


def _predict(tr, ms, cam_dx=0.0, cam_dy=0.0):
    b = tr["box"]
    dt = max(0.0, (ms - tr["last_ms"]) / 1000.0)
    return {
        "x": b["x"] + float(cam_dx or 0.0) + tr["vx"] * dt,
        "y": b["y"] + float(cam_dy or 0.0) + tr["vy"] * dt,
        "w": b["w"], "h": b["h"],
    }


def _associate_players(live, detections, ms, cam_dx, cam_dy, scene_id, next_id):
    """Greedy one-to-one scene-local MOT with bounded motion/scale gates."""
    dets = [d for d in detections if isinstance(d, dict) and _valid_box(d.get("box"))]
    pairs = []
    for ti, tr in enumerate(live):
        if ms - tr["last_ms"] > PLAYER_MAX_GAP_MS:
            continue
        pred = _predict(tr, ms, cam_dx, cam_dy)
        for di, d in enumerate(dets):
            sc = _player_match_score(pred, d["box"])
            if sc is not None:
                pairs.append((sc, ti, di))
    pairs.sort(reverse=True)
    used_t, used_d = set(), set()
    for sc, ti, di in pairs:
        if ti in used_t or di in used_d:
            continue
        used_t.add(ti); used_d.add(di)
        tr, d = live[ti], dets[di]
        old_c, new_c = _center(tr["box"]), _center(d["box"])
        dt = max(1e-3, (ms - tr["last_ms"]) / 1000.0)
        # Remove the frame-to-frame camera translation from body velocity.
        tr["vx"] = (new_c[0] - old_c[0] - float(cam_dx or 0.0)) / dt
        tr["vy"] = (new_c[1] - old_c[1] - float(cam_dy or 0.0)) / dt
        tr["box"] = _box(d["box"])
        tr["last_ms"] = ms
        tr["misses"] = 0
        tr["confidence"] = float(d.get("confidence") or 0.0)
        tr["team"] = d.get("team")
        tr["matched"] = True

    for ti, tr in enumerate(live):
        if ti not in used_t:
            tr["misses"] += 1
            tr["matched"] = False

    for di, d in enumerate(dets):
        if di in used_d:
            continue
        live.append({
            "local_track_id": f"p{next_id:03d}", "scene_id": scene_id,
            "box": _box(d["box"]), "last_ms": ms,
            "vx": 0.0, "vy": 0.0, "misses": 0, "matched": True,
            "confidence": float(d.get("confidence") or 0.0), "team": d.get("team"),
        })
        next_id += 1

    live[:] = [tr for tr in live if ms - tr["last_ms"] <= PLAYER_MAX_GAP_MS]
    active = [tr for tr in live if tr.get("matched")]
    return active, next_id


def _target_candidates(authority, ms, active):
    """Map the canonical GLOBAL_TARGET to current scene-local player tracks."""
    resolved, why = uia.resolve_target_at(
        authority, int(ms), proof_required=False, max_interp_ms=TARGET_NEAR_MS)
    if resolved is not None and _valid_box(resolved.get("box")):
        rb = resolved["box"]
        ranked = []
        for tr in active:
            b = tr["box"]
            ov = _iou(rb, b)
            dh = _dist(rb, b) / max(rb["h"], b["h"], 1e-6)
            if ov >= TARGET_IOU_MIN or dh <= TARGET_CENTER_H:
                score = 1.7 * ov + max(0.0, 1.0 - dh / TARGET_CENTER_H)
                ranked.append((score, tr["local_track_id"], tr))
        ranked.sort(reverse=True, key=lambda x: x[0])
        if ranked:
            best = ranked[0]
            second = ranked[1][0] if len(ranked) > 1 else None
            if second is None or best[0] >= second + TARGET_AMBIG_MARGIN:
                return {
                    "status": "VERIFIED", "reason": why,
                    "local_track_id": best[1], "candidate_local_track_ids": [best[1]],
                    "identity_strength": resolved.get("identity_strength"),
                    "proof_eligible": bool(resolved.get("proof_eligible")),
                }
            return {
                "status": "HYPOTHESES", "reason": "LOCAL_TRACK_AMBIGUITY",
                "local_track_id": None,
                "candidate_local_track_ids": [x[1] for x in ranked[:3]],
                "identity_strength": resolved.get("identity_strength"),
                "proof_eligible": False,
            }

    # If the canonical point itself is unresolved, project its bounded physical
    # hypotheses onto local tracks.  This preserves alternatives for B.2/B.3.
    near = [p for p in (authority or {}).get("target_points") or []
            if isinstance(p, dict) and abs(int(p.get("media_ms", -10**9)) - ms) <= TARGET_NEAR_MS]
    near.sort(key=lambda p: abs(int(p.get("media_ms", 0)) - ms))
    ids = []
    for p in near[:2]:
        for h in p.get("hypotheses") or []:
            hb = h.get("box")
            if not _valid_box(hb):
                continue
            ranked = []
            for tr in active:
                ov = _iou(hb, tr["box"])
                dh = _dist(hb, tr["box"]) / max(hb["h"], tr["box"]["h"], 1e-6)
                if ov >= TARGET_IOU_MIN or dh <= TARGET_CENTER_H:
                    ranked.append((1.7 * ov + max(0.0, 1.0 - dh / TARGET_CENTER_H),
                                   tr["local_track_id"]))
            if ranked:
                ranked.sort(reverse=True)
                if ranked[0][1] not in ids:
                    ids.append(ranked[0][1])
    return {
        "status": "HYPOTHESES" if ids else "UNRESOLVED",
        "reason": why,
        "local_track_id": None,
        "candidate_local_track_ids": ids[:4],
        "identity_strength": "UNRESOLVED",
        "proof_eligible": False,
    }


def _select_ball(previous, candidates, ms):
    cands = [c for c in candidates if isinstance(c, dict) and _valid_box(c.get("box"))]
    if not cands:
        return None, "MISSING", []
    ranked = []
    for c in cands:
        conf = float(c.get("confidence") or 0.0)
        continuity = 0.0
        if previous and ms - previous["media_ms"] <= BALL_MAX_GAP_MS:
            dt = max(1e-3, (ms - previous["media_ms"]) / 1000.0)
            d = _dist(previous["box"], c["box"])
            max_d = BALL_MAX_SPEED_FW_S * dt
            if d > max_d:
                continuity = -1.0
            else:
                continuity = 1.0 - d / max(max_d, 1e-6)
        ranked.append((conf + 0.45 * continuity, conf, c))
    ranked.sort(reverse=True, key=lambda x: x[0])
    best = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else None
    state = "DETECTED" if second is None or best[0] >= second + BALL_SCORE_MARGIN else "AMBIGUOUS"
    out = {
        "media_ms": int(ms), "box": _box(best[2]["box"]),
        "confidence": round(best[1], 4), "state": state,
    }
    return out, state, [deepcopy(x[2]) for x in ranked[:4]]


def _possession(ball, active, target_map):
    if not ball or not _valid_box(ball.get("box")):
        return {"status": "NO_BALL", "holder_local_track_id": None,
                "candidate_local_track_ids": [], "target_relation": "UNKNOWN"}
    bx, by = _center(ball["box"])
    ranked = []
    for tr in active:
        fx, fy = _foot(tr["box"])
        h = max(tr["box"]["h"], 1e-6)
        d_h = math.hypot(bx - fx, by - fy) / h
        if d_h <= POSSESSION_MAX_H:
            ranked.append((d_h, tr["local_track_id"]))
    ranked.sort()
    cand = [x[1] for x in ranked[:4]]
    holder = None
    status = "NONE"
    if ranked:
        status = "CANDIDATE"
        if len(ranked) == 1 or ranked[1][0] - ranked[0][0] >= POSSESSION_AMBIG_MARGIN_H:
            holder, status = ranked[0][1], "LIKELY"
        else:
            status = "AMBIGUOUS"
    target_ids = set(target_map.get("candidate_local_track_ids") or [])
    if holder and holder in target_ids:
        rel = "TARGET_LIKELY_POSSESSION"
    elif target_ids.intersection(cand):
        rel = "TARGET_POSSESSION_CANDIDATE"
    elif cand:
        rel = "OTHER_PLAYER_POSSESSION_CANDIDATE"
    else:
        rel = "LOOSE_OR_IN_FLIGHT"
    return {"status": status, "holder_local_track_id": holder,
            "candidate_local_track_ids": cand, "target_relation": rel}


def assemble_scene_graph(observations, unified_authority) -> dict:
    """Pure deterministic scene graph over precomputed detections."""
    obs = sorted((o for o in observations or [] if isinstance(o, dict) and _num(o.get("media_ms"))),
                 key=lambda o: float(o["media_ms"]))
    if not obs:
        return {"version": VERSION, "status": "empty", "global_target_id": uia.GLOBAL_TARGET_ID,
                "frames": [], "player_points": [], "ball_points": [], "scenes": [],
                "metrics": {}}

    frames, player_points, ball_points, scenes = [], [], [], []
    live = []
    next_id = 1
    scene_no = 0
    scene_id = f"scene_{scene_no + 1:03d}"
    scene_start = int(obs[0]["media_ms"])
    previous_ball = None
    target_verified = target_hyp = ball_seen = possession_target = 0

    for oi, o in enumerate(obs):
        ms = int(round(float(o["media_ms"])))
        if oi > 0 and o.get("cut"):
            scenes.append({"scene_id": scene_id, "start_ms": scene_start,
                           "end_ms": int(obs[oi - 1]["media_ms"])})
            scene_no += 1
            scene_id = f"scene_{scene_no + 1:03d}"
            scene_start = ms
            live = []
            next_id = 1
            previous_ball = None

        active, next_id = _associate_players(
            live, o.get("players") or [], ms,
            float(o.get("cam_dx") or 0.0), float(o.get("cam_dy") or 0.0),
            scene_id, next_id)
        target_map = _target_candidates(unified_authority or {}, ms, active)
        if target_map["status"] == "VERIFIED":
            target_verified += 1
        elif target_map["status"] == "HYPOTHESES":
            target_hyp += 1

        ball, ball_state, ball_candidates = _select_ball(previous_ball, o.get("balls") or [], ms)
        if ball is not None:
            previous_ball = ball
            ball_seen += 1
            bp = dict(ball); bp["scene_id"] = scene_id
            ball_points.append(bp)
        possession = _possession(ball, active, target_map)
        if possession["target_relation"] in ("TARGET_LIKELY_POSSESSION", "TARGET_POSSESSION_CANDIDATE"):
            possession_target += 1

        active_rows = []
        target_set = set(target_map.get("candidate_local_track_ids") or [])
        for tr in active:
            row = {
                "media_ms": ms, "scene_id": scene_id,
                "local_track_id": tr["local_track_id"], "box": deepcopy(tr["box"]),
                "confidence": tr.get("confidence"), "team": tr.get("team"),
                "global_target_candidate": tr["local_track_id"] in target_set,
                "global_target_verified": tr["local_track_id"] == target_map.get("local_track_id"),
            }
            player_points.append(row)
            active_rows.append(row)

        frames.append({
            "media_ms": ms, "scene_id": scene_id,
            "players": active_rows,
            "global_target": target_map,
            "ball": deepcopy(ball), "ball_state": ball_state,
            "ball_candidates": ball_candidates,
            "possession": possession,
        })

    scenes.append({"scene_id": scene_id, "start_ms": scene_start,
                   "end_ms": int(obs[-1]["media_ms"])})
    return {
        "version": VERSION,
        "status": "ok",
        "global_target_id": uia.GLOBAL_TARGET_ID,
        "timebase": "canonical_media_ms",
        "hz": HZ,
        "scenes": scenes,
        "frames": frames,
        "player_points": player_points,
        "ball_points": ball_points,
        "metrics": {
            "samples": len(frames), "scenes": len(scenes),
            "player_points": len(player_points), "ball_points": len(ball_points),
            "target_verified_frames": target_verified,
            "target_hypothesis_frames": target_hyp,
            "ball_seen_frames": ball_seen,
            "target_possession_frames": possession_target,
        },
    }


def _detect_people_and_ball(detector, frame_bgr):
    """One YOLO forward pass → person + COCO sports-ball candidates.

    Sports-ball class 32 is intentionally supporting evidence only.  We retain
    multiple candidates; temporal graph logic decides whether one is useful.
    """
    import cv2
    import numpy as np
    import cv_detect

    if detector is None or not getattr(detector, "ok", False):
        return [], []
    H, W = frame_bgr.shape[:2]
    scale = cv_detect.INPUT / max(H, W)
    nw, nh = int(W * scale), int(H * scale)
    img = np.zeros((cv_detect.INPUT, cv_detect.INPUT, 3), np.uint8)
    img[:nh, :nw] = cv2.resize(frame_bgr, (nw, nh))
    blob = cv2.dnn.blobFromImage(img, 1 / 255.0, (cv_detect.INPUT, cv_detect.INPUT), swapRB=True)
    detector.net.setInput(blob)
    out = detector.net.forward()[0].T
    cls = out[:, 4:].argmax(1)
    conf = out[:, 4:].max(1)

    results = {0: [], 32: []}
    thresholds = {0: float(cv_detect.CONF_T), 32: 0.10}
    for cid in (0, 32):
        keep = (cls == cid) & (conf > thresholds[cid])
        boxes, scores = [], []
        for r, c in zip(out[keep], conf[keep]):
            cx, cy, bw, bh = r[:4]
            boxes.append([int(cx - bw / 2), int(cy - bh / 2), int(bw), int(bh)])
            scores.append(float(c))
        idx = cv2.dnn.NMSBoxes(boxes, scores, thresholds[cid], cv_detect.NMS_T)
        for i in np.array(idx).flatten() if len(idx) else []:
            x, y, bw, bh = boxes[i]
            b = {
                "x": max(0.0, min(1.0, x / (W * scale))),
                "y": max(0.0, min(1.0, y / (H * scale))),
                "w": max(1e-4, min(1.0, bw / (W * scale))),
                "h": max(1e-4, min(1.0, bh / (H * scale))),
            }
            results[cid].append({"box": b, "confidence": scores[i]})
    return results[0], results[32]


def build_scene_graph(video_path: str, unified_authority: dict) -> dict:
    """Production ingestion: one local detector pass at HZ, zero network/LLM."""
    import cv2
    import numpy as np
    import cv_detect
    import video_timebase

    started = time.time()
    cap = None
    try:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return {"version": VERSION, "status": "skipped", "reason": "no_video"}
        fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
        detector = cv_detect.PersonDetector()
        if not detector.ok:
            return {"version": VERSION, "status": "skipped", "reason": "detector_unavailable"}
        cam = cv_detect.CameraMotion(out_scale=1.0)
        prev_tiny = None
        prev_sample = None
        observations = []
        interval = 1.0 / max(HZ, 0.1)
        while True:
            ok, t, _ = video_timebase.grab_frame_time_seconds(cap, fps)
            if not ok:
                break
            if not video_timebase.should_sample(t, prev_sample, interval):
                continue
            ok2, frame = cap.retrieve()
            if not ok2:
                continue
            prev_sample = t
            H, W = frame.shape[:2]
            tiny_h = max(2, int(H * 160 / max(W, 1)))
            tiny = cv2.cvtColor(cv2.resize(frame, (160, tiny_h)), cv2.COLOR_BGR2GRAY).astype(np.float32)
            diff = (float(cv2.absdiff(prev_tiny, tiny).mean())
                    if prev_tiny is not None and prev_tiny.shape == tiny.shape else 0.0)
            cam.update(tiny)
            cut = (diff > 45.0 and cam.mode != "affine") or diff > 75.0
            prev_tiny = tiny
            people, balls = _detect_people_and_ball(detector, frame)
            observations.append({
                "media_ms": int(round(t * 1000)), "cut": bool(cut),
                "cam_dx": 0.0 if cut else float(cam.dx) / 160.0,
                "cam_dy": 0.0 if cut else float(cam.dy) / max(tiny_h, 1),
                "players": people, "balls": balls,
            })
        graph = assemble_scene_graph(observations, unified_authority)
        graph["compute_s"] = round(time.time() - started, 2)
        graph["detector"] = "yolov8n.onnx/person+sports_ball"
        return graph
    except Exception as exc:
        return {"version": VERSION, "status": "error", "reason": str(exc)[:240]}
    finally:
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass
