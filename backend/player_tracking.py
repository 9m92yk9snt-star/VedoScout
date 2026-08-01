"""
player_tracking.py — deterministic optical tracking seeded by the user's taps.

Every tap gives a ground-truth (time, box). From each seed we track the player
forward AND backward (±SPAN seconds) with local NCC template matching:
- search window = last box grown 45%
- template updated every frame, drift-guarded against the ORIGINAL tap content
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

logger = logging.getLogger(__name__)

SAMPLE_HZ = 12.5
SPAN = 4.0
TARGET_W = 480
COLOR_W = 240  # half-res colour frames for HSV signature checks
MATCH_MIN = 0.45
DRIFT_MIN = 0.30
MAX_MISSES = 3
COLOR_MIN = 0.22      # HSV-correlation below this = colour mismatch
COLOR_MAX_MISSES = 3  # consecutive colour mismatches → stop (identity risk)


def _read_window(cap, w0: float, w1: float, step: float):
    """Returns [(t, gray_480w, hsv_240w), ...]"""
    frames = []
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, w0) * 1000.0)
    last_t = -1e9
    while True:
        pos = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        ok, fr = cap.read()
        if not ok or pos > w1:
            break
        if pos - last_t < step * 0.8:
            continue
        last_t = pos
        h, w = fr.shape[:2]
        small = cv2.resize(fr, (TARGET_W, max(2, int(h * TARGET_W / w))))
        g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(
            cv2.resize(small, (COLOR_W, max(2, small.shape[0] // 2))), cv2.COLOR_BGR2HSV,
        )
        frames.append((pos, g, hsv))
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


def _run_direction(frames, i0: int, box_px, out: dict, direction: int, doubts: list | None = None):
    _t0, g0, hsv0 = frames[i0]
    tmpl0 = _crop(g0, box_px)
    if tmpl0 is None:
        return
    tmpl = tmpl0
    bw, bh = box_px[2] - box_px[0], box_px[3] - box_px[1]
    H, W = g0.shape[:2]
    scale = hsv0.shape[1] / float(W)  # gray-px → colour-px
    ref_hist = _color_hist(hsv0, box_px, scale)  # FIXED colour signature from the tap
    misses = 0
    color_misses = 0
    steps = 0
    cur = list(box_px)
    end = len(frames) if direction > 0 else -1
    for i in range(i0 + direction, end, direction):
        t, g, hsv = frames[i]
        gx, gy = bw * 0.45, bh * 0.45
        sx0, sy0 = max(0, int(cur[0] - gx)), max(0, int(cur[1] - gy))
        sx1, sy1 = min(W, int(cur[2] + gx)), min(H, int(cur[3] + gy))
        region = g[sy0:sy1, sx0:sx1]
        if region.shape[0] <= tmpl.shape[0] or region.shape[1] <= tmpl.shape[1]:
            break
        res = cv2.matchTemplate(region, tmpl, cv2.TM_CCOEFF_NORMED)
        _mn, mx, _mnl, ml = cv2.minMaxLoc(res)
        if mx < MATCH_MIN:
            misses += 1
            if misses >= MAX_MISSES:
                break
            continue
        misses = 0
        cand_box = [sx0 + ml[0], sy0 + ml[1], sx0 + ml[0] + int(bw), sy0 + ml[1] + int(bh)]
        # ── colour veto: does the matched box still wear the tapped colours? ──
        csim = _color_sim(ref_hist, hsv, cand_box, scale)
        if csim is not None and csim < COLOR_MIN:
            color_misses += 1
            if color_misses >= COLOR_MAX_MISSES:
                _doubt(doubts, t, cur, W, H, "kit-colour change — possible player crossover")
                break  # colours no longer match the tapped player — stop honestly
            continue  # do NOT accept the suspicious box
        color_misses = 0
        cur = cand_box
        steps += 1
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
        for a in (anchors or [])[:10]
        if isinstance(a, dict) and isinstance(a.get("t"), (int, float)) and isinstance(a.get("box"), dict)
    ]
    if not seeds:
        return {"points": [], "segments": [], "doubt_moments": [], "t_off": round(t_off, 3), "hz": SAMPLE_HZ}
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return {"points": [], "segments": [], "doubt_moments": [], "t_off": round(t_off, 3), "hz": SAMPLE_HZ}
    points: dict = {}
    doubts: list = []
    step = 1.0 / SAMPLE_HZ
    try:
        for t_seed, b in seeds:
            frames = _read_window(cap, t_seed - span, t_seed + span, step)
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
            _run_direction(frames, i0, box_px, points, +1, doubts)
            _run_direction(frames, i0, box_px, points, -1, doubts)
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
    }


def track_at(points: list, sec: float, max_gap: float = 0.45) -> dict | None:
    best = None
    for p in points:
        d = abs(p["t"] - sec)
        if d <= max_gap and (best is None or d < abs(best["t"] - sec)):
            best = p
    return best
