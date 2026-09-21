"""motion_compensation.py — FIX06 camera-motion compensation for physical
pace/distance metrics.

Deterministic OpenCV + math only. Downstream of identity: consumes ACCEPTED
FIX04 geometry at FIX03 actual media times and decides, per consecutive-frame
interval, how much apparent image movement came from the CAMERA (pan / tilt /
zoom / small rotation) versus the PLAYER. Only the player residual may enter
speed/distance. Unsafe camera transforms FAIL CLOSED: the interval is skipped,
never approximated by raw screen displacement. This module never decides WHO
the player is and never fills missing identity geometry.
"""

from __future__ import annotations

import statistics

import cv2
import numpy as np

PROC_W = 480              # bounded downscale width for camera estimation
MAX_INTERVAL_S = 0.35     # existing safe track-gap contract — never bridged
BOX_MARGIN = 0.35         # target bbox exclusion margin (target never votes)
MIN_FEATURES = 12
MIN_INLIERS = 8
MIN_INLIER_RATIO = 0.5
SCALE_MIN, SCALE_MAX = 0.90, 1.10
MAX_ROT_DEG = 5.0
MAX_SHIFT_FRAC = 0.25     # of the frame diagonal
MIN_SPREAD_FRAC = 0.08    # spatial spread of background evidence
_LK = dict(winSize=(21, 21), maxLevel=3,
           criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))


def _med(vals, i, half=4):
    lo, hi = max(0, i - half), min(len(vals), i + half + 1)
    return statistics.median(vals[lo:hi])


def estimate_camera(g0, g1, exclude_boxes):
    """Background camera transform g0→g1 (2x3 similarity) or (None, reason).
    The target bbox (both frames, with margin) is masked out so the player
    can never define the camera transform."""
    h, w = g0.shape[:2]
    mask = np.full((h, w), 255, np.uint8)
    for (bx, by, bw_, bh_) in exclude_boxes:
        mx, my = bw_ * BOX_MARGIN, bh_ * BOX_MARGIN
        mask[int(max(0, by - my)):int(min(h, by + bh_ + my)),
             int(max(0, bx - mx)):int(min(w, bx + bw_ + mx))] = 0
    p0 = cv2.goodFeaturesToTrack(g0, maxCorners=240, qualityLevel=0.01,
                                 minDistance=8, mask=mask, blockSize=7)
    if p0 is None or len(p0) < MIN_FEATURES:
        return None, "features"
    p1, st, _ = cv2.calcOpticalFlowPyrLK(g0, g1, p0, None, **_LK)
    if p1 is None or st is None:
        return None, "flow"
    p0b, stb, _ = cv2.calcOpticalFlowPyrLK(g1, g0, p1, None, **_LK)  # fwd-bwd
    if p0b is None or stb is None:
        return None, "flow"
    ok = (st.reshape(-1) == 1) & (stb.reshape(-1) == 1) & \
        (np.linalg.norm((p0 - p0b).reshape(-1, 2), axis=1) < 1.0)
    a, b = p0.reshape(-1, 2)[ok], p1.reshape(-1, 2)[ok]
    if len(a) < MIN_FEATURES:
        return None, "flow"
    cv2.setRNGSeed(707)  # deterministic RANSAC
    m, inl = cv2.estimateAffinePartial2D(a, b, method=cv2.RANSAC,
                                         ransacReprojThreshold=2.0,
                                         maxIters=2000, confidence=0.995)
    if m is None or inl is None or not np.all(np.isfinite(m)):
        return None, "ransac"
    ninl = int(inl.sum())
    if ninl < MIN_INLIERS or ninl / len(a) < MIN_INLIER_RATIO:
        return None, "inliers"
    scale = float(np.hypot(m[0, 0], m[1, 0]))
    if not (SCALE_MIN <= scale <= SCALE_MAX):
        return None, "scale"
    if abs(float(np.degrees(np.arctan2(m[1, 0], m[0, 0])))) > MAX_ROT_DEG:
        return None, "rotation"
    diag = float(np.hypot(w, h))
    if float(np.hypot(m[0, 2], m[1, 2])) > MAX_SHIFT_FRAC * diag:
        return None, "shift"
    pin = a[inl.reshape(-1) == 1]
    if float(np.hypot(pin[:, 0].std(), pin[:, 1].std())) < MIN_SPREAD_FRAC * diag:
        return None, "spread"
    return m, ninl


def samples_from_frames(frames, points):
    """Pure core. frames: grayscale arrays aligned 1:1 with `points`
    (accepted FIX04 geometry, normalized coords, FIX03 actual media `t`).
    Returns {"w", "h", "samples": [...]}. Each interval sample:
      ok=True  → rx, ry (player residual, px), h_px (robust local height),
                 v_norm (residual in normalized screen units / s)
      ok=False → reason (camera transform not trustworthy — fail closed).
    Intervals with dt<=0 or dt>MAX_INTERVAL_S (gaps/segments) are never
    produced — movement is never bridged across them. A frame that could not
    be decoded (None placeholder) rejects BOTH intervals touching it: the
    original interval sequence is preserved, never re-stitched."""
    if not frames or len(frames) != len(points):
        return {"w": 0, "h": 0, "samples": []}
    ref = next((f for f in frames if f is not None), None)
    if ref is None:
        return {"w": 0, "h": 0, "samples": []}
    hgt, wid = ref.shape[:2]
    hs = [max(1e-4, float(p["h"])) for p in points]
    hmed = [_med(hs, i) for i in range(len(hs))]
    samples = []
    for i in range(1, len(points)):
        p0, p1 = points[i - 1], points[i]
        dt = float(p1["t"]) - float(p0["t"])
        if dt <= 0 or dt > MAX_INTERVAL_S:
            continue
        base = {"t0": float(p0["t"]), "t1": float(p1["t"]), "dt": dt}
        if frames[i - 1] is None or frames[i] is None:
            samples.append({**base, "ok": False, "reason": "decode"})
            continue
        b0 = (float(p0["x"]) * wid, float(p0["y"]) * hgt,
              float(p0["w"]) * wid, float(p0["h"]) * hgt)
        b1 = (float(p1["x"]) * wid, float(p1["y"]) * hgt,
              float(p1["w"]) * wid, float(p1["h"]) * hgt)
        try:
            m, q = estimate_camera(frames[i - 1], frames[i], (b0, b1))
        except Exception:  # any local CV failure fails closed for the interval
            m, q = None, "error"
        if m is None:
            samples.append({**base, "ok": False, "reason": q})
            continue
        # stable ground proxy: bottom-centre rebuilt from the box CENTRE plus
        # the PAIR-SHARED median-smoothed local height — stance / one-frame
        # bbox jitter / tracker scale steps cannot manufacture travel because
        # both interval endpoints use the same height estimate
        hpair = (hmed[i - 1] + hmed[i]) / 2.0
        x0 = (float(p0["x"]) + float(p0["w"]) / 2.0) * wid
        y0 = (float(p0["y"]) + float(p0["h"]) / 2.0 + hpair / 2.0) * hgt
        x1 = (float(p1["x"]) + float(p1["w"]) / 2.0) * wid
        y1 = (float(p1["y"]) + float(p1["h"]) / 2.0 + hpair / 2.0) * hgt
        ex = m[0, 0] * x0 + m[0, 1] * y0 + m[0, 2]
        ey = m[1, 0] * x0 + m[1, 1] * y0 + m[1, 2]
        rx, ry = x1 - ex, y1 - ey
        samples.append({**base, "ok": True, "rx": float(rx), "ry": float(ry),
                        "h_px": float(hpair * hgt),
                        "v_norm": float(np.hypot(rx / wid, ry / hgt)) / dt})
    return {"w": wid, "h": hgt, "samples": samples}


def compute_motion_samples(video_path, track):
    """Decode the accepted-geometry frames at their FIX03 actual media times
    (canonical post-grab PTS, bounded downscale) and run the pure core.

    FIX10A0 timebase contract: ``seek_with_preroll`` already grabs the first
    frame and returns its ACTUAL media PTS. Process that exact frame via
    ``retrieve()`` before advancing. Every later step advances exactly once
    through ``grab_frame_time_seconds`` and explicitly unpacks its
    ``(ok, seconds, used_fallback)`` result. Frames remain aligned 1:1 with the
    accepted track points; an undecodable point stays ``None`` and therefore
    rejects both touching motion intervals instead of re-stitching around it.
    Fail-soft: unreadable media yields zero samples → no physical claim.
    """
    import video_timebase as vt

    pts = (track or {}).get("points") or []
    if len(pts) < 2:
        return {"w": 0, "h": 0, "samples": []}
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return {"w": 0, "h": 0, "samples": []}
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        tol = max(0.012, 0.5 / fps) if fps > 1e-6 else 0.02
        ok, t, _used_fallback = vt.seek_with_preroll(
            cap, max(0.0, float(pts[0]["t"]) - 0.5), fps
        )
        # frames stay ALIGNED 1:1 with the original accepted track points —
        # an undecodable point keeps a None placeholder so both intervals
        # touching it are rejected, never re-stitched (C01)
        frames = [None] * len(pts)
        idx = 0
        last_t = float(pts[-1]["t"])

        while ok and idx < len(pts):
            if t > last_t + tol:
                break
            while idx < len(pts) and t > float(pts[idx]["t"]) + tol:
                idx += 1  # point's frame missed — placeholder stays None
            if idx >= len(pts):
                break
            if abs(t - float(pts[idx]["t"])) <= tol:
                # retrieve() belongs to the frame that established `t`; never
                # call grab() between reading the PTS and retrieving the image.
                okr, fr = cap.retrieve()
                if okr and fr is not None:
                    g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
                    if g.shape[1] > PROC_W:
                        s = PROC_W / g.shape[1]
                        g = cv2.resize(
                            g,
                            (PROC_W, max(2, int(round(g.shape[0] * s)))),
                            interpolation=cv2.INTER_AREA,
                        )
                    frames[idx] = g
                idx += 1
            if idx >= len(pts):
                break
            ok, t, _used_fallback = vt.grab_frame_time_seconds(cap, fps)

        return samples_from_frames(frames, pts)
    finally:
        cap.release()
