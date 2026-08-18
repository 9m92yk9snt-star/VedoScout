"""
player_tracking.py — deterministic optical tracking seeded by the user's taps.

Every tap gives a ground-truth (time, box). From each seed we track the player
forward AND backward (±SPAN seconds) with local NCC template matching:
- FIX 03/04: every frame carries its own ACTUAL post-grab media PTS (VFR-safe)
- search window = last box grown 45%, centred by bounded motion prediction
  (camera-compensated player velocity over ACTUAL media dt) — FIX 04
- conservative multi-scale matching (±6%/step, bounded vs the tap) — FIX 04
- geometry gates: same-kit ambiguity skip + implausible-jump rejection — FIX 04
- template updated from ACCEPTED frames only, drift-guarded against the
  ORIGINAL tap content
- COLOUR VETO: every accepted match is compared against the seed's HSV
  colour signature (jersey area). Consistent colour mismatch = likely an
  identity switch onto another player → stop honestly.
- track ends conservatively on low confidence (fail-safe: no data ≠ wrong data)

No AI involved — pure, repeatable computer vision.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np  # noqa: F401

import tracking_geometry
import video_timebase

logger = logging.getLogger(__name__)

SAMPLE_HZ = 12.5
SPAN = 4.0
TARGET_W = 480
COLOR_W = 240  # half-res colour frames for HSV signature checks
MATCH_MIN = 0.45
DRIFT_MIN = 0.30
MAX_MISSES = 3
# FIX 00A — explicit user-confirmed seeds: 10 Scout Mode taps + 3 manual
# verification taps + 3 doubt-confirmation taps. Seeds only — the tracking
# algorithm itself is unchanged.
MAX_TRACKER_SEEDS = 16
COLOR_MIN = 0.22      # HSV-correlation below this = colour mismatch
COLOR_MAX_MISSES = 3  # consecutive colour mismatches → stop (identity risk)
# ── track-end drift protection (validated on 3 real matches) ──
# Real players never sustain near-perfect NCC at 12.5 Hz (pose changes keep
# it ≤ ~0.89); a template latched onto STATIC BACKGROUND does (0.94-0.998).
LOCK_CONF = 0.93      # sustained match ≥ this = background latch
LOCK_STEPS = 6        # ≈ 0.5 s of near-perfect matches → stop + un-record
CUT_DIFF = 45.0       # global frame diff (160w gray) above this = scene cut
                      # (measured: pans p99 = 33, real montage cuts 47-67)


def _cut_flags(frames):
    """flags[i] = True when a scene cut lies between frames[i-1] and frames[i]."""
    flags = [False] * len(frames)
    prev = None
    for i, (_t, _g, _hsv, tiny) in enumerate(frames):
        sf = tiny
        if prev is not None and prev.shape == sf.shape:
            flags[i] = float(cv2.absdiff(prev, sf).mean()) > CUT_DIFF
        prev = sf
    return flags


def _read_window(cap, w0: float, w1: float, step: float, fps=None):
    """Returns [(t, gray_480w, hsv_240w, tiny_160w_f32), ...].

    FIX 03/04 canonical contract: adaptive-preroll seek at/before w0, then
    grab → read the ACTUAL post-grab PTS → retrieve that SAME frame. Only
    frames whose actual media time lies within [w0, w1] are included, and
    sampling is by elapsed ACTUAL media time — never frame_index/fps."""
    frames = []
    lo = max(0.0, w0)
    ok, t, _fb = video_timebase.seek_with_preroll(cap, lo, fps)
    last_t = None
    while ok:
        if t > w1 + 1e-3:
            break
        if t >= lo - 1e-3 and video_timebase.should_sample(t, last_t, step * 0.8):
            ok2, fr = cap.retrieve()
            if ok2:
                last_t = t
                h, w = fr.shape[:2]
                small = cv2.resize(fr, (TARGET_W, max(2, int(h * TARGET_W / w))))
                g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                hsv = cv2.cvtColor(
                    cv2.resize(small, (COLOR_W, max(2, small.shape[0] // 2))), cv2.COLOR_BGR2HSV,
                )
                tiny = cv2.resize(g, (160, max(2, int(g.shape[0] * 160 / g.shape[1])))).astype("float32")
                frames.append((t, g, hsv, tiny))
        ok, t, _fb = video_timebase.grab_frame_time_seconds(cap, fps)
    return frames


def _crop(g, box_px):
    x0, y0, x1, y1 = [int(v) for v in box_px]
    H, W = g.shape[:2]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    if x1 - x0 < 6 or y1 - y0 < 6:
        return None
    return g[y0:y1, x0:x1]


def _color_hist(hsv, box_px_gray, scale: float):
    """H-S histogram of the jersey area (upper 60% of the box), on the
    half-res HSV frame. Returns None when the crop is too small to judge."""
    x0, y0, x1, y1 = [int(v * scale) for v in box_px_gray]
    y1 = y0 + max(1, int((y1 - y0) * 0.6))  # jersey/torso region
    H, W = hsv.shape[:2]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    roi = hsv[y0:y1, x0:x1]
    hist = cv2.calcHist([roi], [0, 1], None, [30, 32], [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
    return hist


def _color_sim(ref_hist, hsv, box_px_gray, scale: float) -> float | None:
    cand = _color_hist(hsv, box_px_gray, scale)
    if cand is None or ref_hist is None:
        return None
    return float(cv2.compareHist(ref_hist, cand, cv2.HISTCMP_CORREL))


def _record(out: dict, t: float, cur, W: int, H: int, conf: float):
    key = round(t, 2)
    rec = {
        "t": key,
        "x": round(cur[0] / W, 4), "y": round(cur[1] / H, 4),
        "w": round((cur[2] - cur[0]) / W, 4), "h": round((cur[3] - cur[1]) / H, 4),
        "conf": round(float(conf), 3),
    }
    prev = out.get(key)
    if prev is None or rec["conf"] > prev["conf"]:
        out[key] = rec


def _doubt(doubts, t: float, cur, W: int, H: int, reason: str):
    if doubts is None:
        return
    doubts.append({
        "t": round(t, 2),
        "x": round(cur[0] / W, 4), "y": round(cur[1] / H, 4),
        "w": round((cur[2] - cur[0]) / W, 4), "h": round((cur[3] - cur[1]) / H, 4),
        "reason": reason,
    })


def _run_direction(frames, i0: int, box_px, out: dict, direction: int, doubts: list | None = None,
                   cuts: list | None = None):
    _t0, g0, hsv0, tiny0 = frames[i0]
    tmpl0 = _crop(g0, box_px)
    if tmpl0 is None:
        return
    tmpl = tmpl0
    bw0, bh0 = box_px[2] - box_px[0], box_px[3] - box_px[1]  # seed size = scale bounds
    bw, bh = float(bw0), float(bh0)
    H, W = g0.shape[:2]
    scale = hsv0.shape[1] / float(W)  # gray-px → colour-px
    ref_hist = _color_hist(hsv0, box_px, scale)  # FIXED colour signature from the tap
    misses = 0
    color_misses = 0
    ambig_misses = 0
    jump_misses = 0
    steps = 0
    lock_ts: list = []  # timestamps of the current near-perfect-match streak
    cur = list(box_px)
    vel = (0.0, 0.0)          # camera-compensated player velocity (gray px/s)
    t_last = frames[i0][0]    # media time of the last ACCEPTED geometry
    cam_acc = [0.0, 0.0]      # camera shift accumulated since last accept (gray px)
    prev_tiny = tiny0
    tiny_scale = W / float(tiny0.shape[1])
    end = len(frames) if direction > 0 else -1
    for i in range(i0 + direction, end, direction):
        # ── scene-cut stop: a montage cut invalidates template tracking ──
        if cuts is not None:
            boundary = cuts[i] if direction > 0 else (cuts[i + 1] if i + 1 < len(cuts) else False)
            if boundary:
                _doubt(doubts, frames[i][0], cur, W, H, "scene cut — tracking cannot continue")
                break
        t, g, hsv, tiny = frames[i]
        # ── global camera motion between the previously PROCESSED frame and
        # this one — a pan must not be read as player motion (fail-safe 0) ──
        cdx, cdy = tracking_geometry.estimate_camera_shift(prev_tiny, tiny)
        prev_tiny = tiny
        cam_acc[0] += cdx * tiny_scale
        cam_acc[1] += cdy * tiny_scale
        dt = abs(t - t_last)  # ACTUAL elapsed media time since last accept
        # ── bounded motion prediction: search follows camera + player motion ──
        pdx, pdy = tracking_geometry.predict_displacement(vel, dt, bw, bh)
        pcx = (cur[0] + cur[2]) / 2.0 + cam_acc[0] + pdx
        pcy = (cur[1] + cur[3]) / 2.0 + cam_acc[1] + pdy
        ex = min(abs(pdx) * 0.5 + abs(cam_acc[0]) * 0.25, bw * 0.6)
        ey = min(abs(pdy) * 0.5 + abs(cam_acc[1]) * 0.25, bh * 0.6)
        gx, gy = bw * 0.45 + ex, bh * 0.45 + ey
        sx0, sy0 = max(0, int(pcx - bw / 2.0 - gx)), max(0, int(pcy - bh / 2.0 - gy))
        sx1, sy1 = min(W, int(pcx + bw / 2.0 + gx)), min(H, int(pcy + bh / 2.0 + gy))
        region = g[sy0:sy1, sx0:sx1]
        # ── conservative multi-scale match (±6%/step, bounded vs the tap) ──
        best = None
        for s in tracking_geometry.scale_candidates(bw, bh, bw0, bh0):
            tw = max(6, int(round(tmpl.shape[1] * s)))
            th = max(6, int(round(tmpl.shape[0] * s)))
            if region.shape[0] <= th or region.shape[1] <= tw:
                continue
            tm = tmpl if (tw, th) == (tmpl.shape[1], tmpl.shape[0]) else cv2.resize(tmpl, (tw, th))
            res = cv2.matchTemplate(region, tm, cv2.TM_CCOEFF_NORMED)
            _mn, mx, _mnl, ml = cv2.minMaxLoc(res)
            if best is None or mx > best[0]:
                best = (mx, ml, tw, th, res)
        if best is None:
            break  # search region cannot even hold the template
        mx, ml, tw, th, res = best
        if mx < MATCH_MIN:
            misses += 1
            if misses >= MAX_MISSES:
                break
            continue
        misses = 0
        # ── same-kit crossover safety: two spatially distinct near-equal
        # candidates → this frame is NOT authoritative geometry. No record,
        # no template update, no jumping to the nearest teammate. ──
        mx2, _ml2 = tracking_geometry.second_peak(res, ml, tw, th)
        if tracking_geometry.is_ambiguous(mx, mx2, MATCH_MIN):
            ambig_misses += 1
            if ambig_misses >= MAX_MISSES:
                _doubt(doubts, t, cur, W, H, "two similar players — identity ambiguous")
                break
            continue
        cand_box = [sx0 + ml[0], sy0 + ml[1], sx0 + ml[0] + tw, sy0 + ml[1] + th]
        # ── geometry teleport gate: camera-compensated residual displacement
        # must stay plausible for the elapsed media time, however high NCC is ──
        rdx = (cand_box[0] + cand_box[2]) / 2.0 - pcx
        rdy = (cand_box[1] + cand_box[3]) / 2.0 - pcy
        if not tracking_geometry.plausible_motion(rdx, rdy, bw, bh, dt):
            jump_misses += 1
            if jump_misses >= MAX_MISSES:
                _doubt(doubts, t, cur, W, H, "implausible jump — geometry rejected")
                break
            continue
        # ── colour veto: does the matched box still wear the tapped colours? ──
        csim = _color_sim(ref_hist, hsv, cand_box, scale)
        if csim is not None and csim < COLOR_MIN:
            color_misses += 1
            if color_misses >= COLOR_MAX_MISSES:
                _doubt(doubts, t, cur, W, H, "kit-colour change — possible player crossover")
                break  # colours no longer match the tapped player — stop honestly
            continue  # do NOT accept the suspicious box
        color_misses = 0
        ambig_misses = 0
        jump_misses = 0
        # ── ACCEPT: velocity from the camera-compensated residual, ACTUAL dt ──
        vel = tracking_geometry.update_velocity(
            vel,
            ((cur[0] + cur[2]) / 2.0, (cur[1] + cur[3]) / 2.0),
            ((cand_box[0] + cand_box[2]) / 2.0, (cand_box[1] + cand_box[3]) / 2.0),
            cam_acc, dt)
        cur = cand_box
        bw, bh = float(tw), float(th)
        cam_acc = [0.0, 0.0]
        t_last = t
        steps += 1
        # ── static-background latch: real players never sustain near-perfect
        # NCC (pose keeps changing); static background does. Stop and remove
        # the latched points — no data is better than a ring on bushes. ──
        if mx >= LOCK_CONF:
            lock_ts.append(round(t, 2))
            if len(lock_ts) >= LOCK_STEPS:
                for tt in lock_ts:
                    out.pop(tt, None)
                _doubt(doubts, t, cur, W, H, "static background lock — player left the box")
                break
        else:
            lock_ts = []
        cand = _crop(g, cur)
        if cand is None:
            break
        if steps % 8 == 0:
            c0 = cv2.resize(cand, (tmpl0.shape[1], tmpl0.shape[0]))
            drift = float(cv2.matchTemplate(c0, tmpl0, cv2.TM_CCOEFF_NORMED)[0][0])
            if drift < DRIFT_MIN:
                _doubt(doubts, t, cur, W, H, "visual drift — tracker no longer certain")
                break  # drifted away from the original tap content — stop honestly
        tmpl = cand
        _record(out, t, cur, W, H, mx)


def track_player(video_path: str, anchors: list, t_off: float = 0.0, span: float = SPAN) -> dict:
    """Track the tapped player around every tap. Returns
    {points: [{t,x,y,w,h,conf}...], segments: [[t0,t1]...], t_off, hz}."""
    seeds = [
        (float(a["t"]) + float(t_off or 0.0), a["box"])
        for a in (anchors or [])[:MAX_TRACKER_SEEDS]
        if isinstance(a, dict) and isinstance(a.get("t"), (int, float)) and isinstance(a.get("box"), dict)
    ]
    logger.info(f"[track] tracker_seed_count={len(seeds)} (anchors_received={len(anchors or [])})")
    if not seeds:
        return {"points": [], "segments": [], "doubt_moments": [], "t_off": round(t_off, 3), "hz": SAMPLE_HZ, "seed_count": 0}
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return {"points": [], "segments": [], "doubt_moments": [], "t_off": round(t_off, 3), "hz": SAMPLE_HZ, "seed_count": len(seeds)}
    points: dict = {}
    doubts: list = []
    step = 1.0 / SAMPLE_HZ
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    fps = fps if fps > 0 else None  # explicit last-resort fallback only
    try:
        for t_seed, b in seeds:
            frames = _read_window(cap, t_seed - span, t_seed + span, step, fps)
            if len(frames) < 3:
                continue
            H, W = frames[0][1].shape[:2]
            i0 = min(range(len(frames)), key=lambda i: abs(frames[i][0] - t_seed))
            if abs(frames[i0][0] - t_seed) > 0.5:
                continue
            box_px = [
                float(b["x"]) * W, float(b["y"]) * H,
                (float(b["x"]) + float(b["w"])) * W, (float(b["y"]) + float(b["h"])) * H,
            ]
            _record(points, frames[i0][0], box_px, W, H, 1.0)  # the tap itself
            cuts = _cut_flags(frames)
            _run_direction(frames, i0, box_px, points, +1, doubts, cuts)
            _run_direction(frames, i0, box_px, points, -1, doubts, cuts)
            del frames
    finally:
        cap.release()
    pts = sorted(points.values(), key=lambda p: p["t"])
    segs: list = []
    for p in pts:
        if segs and p["t"] - segs[-1][1] <= 0.35:
            segs[-1][1] = p["t"]
        else:
            segs.append([p["t"], p["t"]])
    segs = [[round(a, 2), round(b, 2)] for a, b in segs if b - a >= 0.3]
    # ── doubt moments: identity-risk stops NOT already covered by a user tap ──
    seed_times = [t for t, _b in seeds]
    doubt_out: list = []
    for dmom in sorted(doubts, key=lambda d: d["t"]):
        if any(abs(dmom["t"] - st) <= 1.2 for st in seed_times):
            continue  # user already confirmed identity right there
        if doubt_out and dmom["t"] - doubt_out[-1]["t"] < 1.0:
            continue
        doubt_out.append(dmom)
    return {
        "points": pts, "segments": segs, "doubt_moments": doubt_out[:3],
        "t_off": round(float(t_off or 0.0), 3), "hz": SAMPLE_HZ,
        "seed_count": len(seeds),
    }


def track_at(points: list, sec: float, max_gap: float = 0.45) -> dict | None:
    best = None
    for p in points:
        d = abs(p["t"] - sec)
        if d <= max_gap and (best is None or d < abs(best["t"] - sec)):
            best = p
    return best
