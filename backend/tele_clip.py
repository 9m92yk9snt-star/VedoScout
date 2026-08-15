"""tele_clip.py — Level 2 telestration: a ring that follows the player through a
short proof clip. Positions come STRAIGHT from the report's ground-truth player
track (seeded by the user's own taps, colour-vetoed, drift-guarded) — the clip
is trimmed to the confidently tracked window and skipped entirely when the
track is too short or too sparse. Never a wrong ring."""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger("elite-scout")

MIN_COVERAGE = 0.90   # user rule: only near-complete tracking ships, else fallback video
MAX_GAP_SEC = 0.5     # track samples further apart than this end the usable window
FADE_SEC = 0.35       # ring fades in/out — never pops
MIN_CLIP_SEC = 3.0    # shorter verified windows fall back to the full video
                      # with the moment chip — no meaningless 2-3 s loops
SEED_TOL = 0.35       # a track point must exist this close to the cited moment


def _make_chip(label: str, frame_w: int):
    """Small dark pill '• NAME · TRACKED' with a downward pointer baked in."""
    from PIL import Image, ImageDraw, ImageFont
    fs = max(12, int(frame_w / 58))
    h = int(fs * 1.75)
    ptr = max(5, int(fs * 0.45))
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", fs)
    except Exception:
        font = ImageFont.load_default()
    tmp = Image.new("RGBA", (10, 10))
    tw = int(ImageDraw.Draw(tmp).textlength(label, font=font))
    pad_x = int(fs * 0.6)
    dot_r = fs * 0.2
    w = int(tw + 2 * pad_x + dot_r * 2 + fs * 0.4)
    img = Image.new("RGBA", (w, h + ptr), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=(10, 15, 13, 218))
    d.polygon([(w / 2 - ptr, h - 1), (w / 2 + ptr, h - 1), (w / 2, h + ptr - 1)], fill=(10, 15, 13, 218))
    dcx = pad_x + dot_r
    d.ellipse([dcx - dot_r, h / 2 - dot_r, dcx + dot_r, h / 2 + dot_r], fill=(204, 255, 0, 255))
    d.text((dcx + dot_r + fs * 0.32, (h - fs) / 2 - fs * 0.05), label, font=font, fill=(255, 255, 255, 245))
    return np.array(img)


def _blend_chip(frame, chip, x: int, y: int, alpha: float = 1.0):
    ch, cw = chip.shape[:2]
    fh, fw = frame.shape[:2]
    x = max(0, min(fw - cw, x))
    y = max(0, min(fh - ch, y))
    if alpha <= 0.02:
        return
    rgb = chip[:, :, [2, 1, 0]].astype(np.float32)
    a = (chip[:, :, 3:4].astype(np.float32)) / 255.0 * min(1.0, alpha)
    roi = frame[y:y + ch, x:x + cw].astype(np.float32)
    frame[y:y + ch, x:x + cw] = (roi * (1 - a) + rgb * a).astype(np.uint8)


VOLT_BGR = np.float32([0, 255, 204])


def _ground_anchor(frame, px, py, bw, bh):
    """Visual Ground-Anchor Resolver: locate the target's ACTUAL ground
    contact (feet/hands footprint) near the accepted box instead of blindly
    trusting bbox bottom-center. Handles running, wide stance, distant
    players, duels (ownership stays within the accepted box's columns) and
    falls (contact may sit BELOW a torso-hugging box). Fail-safe fallback:
    the incoming bbox bottom-center. Never touches tracking data."""
    fh, fw = frame.shape[:2]
    x0, x1 = int(max(0, px - bw * 0.62)), int(min(fw, px + bw * 0.62))
    y0, y1 = int(max(0, py - bh * 0.85)), int(min(fh, py + bh * 0.45))
    if x1 - x0 < 8 or y1 - y0 < 10:
        return px, py, None
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    pm = (cv2.inRange(hsv, (30, 40, 40), (90, 255, 255)) == 0).astype(np.uint8)
    pm = cv2.morphologyEx(pm, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    ys, xs = np.nonzero(pm)
    if len(ys) < 30:
        return px, py, None
    keep = np.abs(xs + x0 - px) <= bw * 0.5  # ownership: target's own columns
    ys, xs = ys[keep], xs[keep]
    if len(ys) < 25:
        return px, py, None
    y_low = float(np.percentile(ys, 96))
    band = ys >= y_low - max(3.0, bh * 0.12)
    if int(band.sum()) < 10:
        return px, py, None
    bx, by = xs[band], ys[band]
    ax = x0 + float(np.median(bx))
    ay = y0 + float(np.percentile(by, 85))
    foot_w = float(np.percentile(bx, 95) - np.percentile(bx, 5))
    if abs(ax - px) > bw * 0.45 or ay < py - bh * 0.55:
        return px, py, None  # implausible → honest fallback
    return ax, min(ay, fh - 2.0), foot_w


def _draw_ring(frame, cx: float, feet_y: float, w: float, h: float, alpha: float = 1.0,
               state: dict | None = None):
    """Ground-integrated marker: the ellipse reads as PAINTED ON the pitch under
    the player, not as a graphic overlay. Volt paint is modulated by the grass
    luminance (inherits pitch texture), a soft contact shadow grounds the player,
    the rim has gentle falloff + controlled glow, flatness follows perspective,
    and the player's silhouette is restored in front so no line ever crosses
    boots/ankles/legs. Pure downstream visualization of the verified track."""
    if alpha <= 0.02:
        return
    fh, fw = frame.shape[:2]
    bx_w, bx_h = max(8.0, w * fw), max(12.0, h * fh)
    ax, ay, foot_w = _ground_anchor(frame, cx * fw, min(feet_y, 0.995) * fh, bx_w, bx_h)
    if state is not None:  # temporal stability across clip frames
        prev = state.get("anchor")
        if prev is not None:
            jump = float(np.hypot(ax - prev[0], ay - prev[1]))
            k = 0.15 if jump > bx_h * 0.6 else 0.45  # implausible jump → glide
            ax = prev[0] + k * (ax - prev[0])
            ay = prev[1] + k * (ay - prev[1])
            if foot_w and state.get("foot_w"):
                foot_w = state["foot_w"] + 0.3 * (foot_w - state["foot_w"])
        state["anchor"] = (ax, ay)
        if foot_w:
            state["foot_w"] = foot_w
    est_h = min(max(h * fh, fh * 0.045), fw * 0.333, fh * 0.42)
    rw = est_h * 0.30
    if foot_w:  # stance-adaptive: the real footprint decides the width
        rw = max(rw, min(foot_w * 0.85, est_h * 0.50))
    else:
        rw = max(rw, min(w * fw * 0.55, est_h * 0.45))
    rw = int(min(max(rw, fw * 0.024), fw * 0.10))
    px, py = int(ax), int(min(ay, fh * 0.995))
    ratio = 0.26 + 0.14 * min(1.0, max(0.0, py / max(1, fh)))  # flatter when far away
    rh = max(4, int(rw * ratio))
    lw = max(2, int(rw * 0.085))
    m = lw * 10
    x0, y0 = max(0, px - rw - m), max(0, py - rh - m)
    x1, y1 = min(fw, px + rw + m), min(fh, py + rh + m)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return
    roi = frame[y0:y1, x0:x1]
    orig = roi.copy()
    c = (px - x0, py - y0)

    # paint tint: volt carried by the local grass luminance → chalk-like paint
    gray = cv2.cvtColor(orig, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    tint = VOLT_BGR[None, None, :] * (0.42 + 0.58 * gray[..., None])

    # 1 — soft contact shadow under the player (grounds him on the grass)
    sh = np.zeros(roi.shape[:2], np.uint8)
    cv2.ellipse(sh, c, (max(3, int(rw * 0.58)), max(3, int(rh * 0.66))),
                0, 0, 360, 255, -1, cv2.LINE_AA)
    sh = cv2.GaussianBlur(sh, (0, 0), max(2.0, rw * 0.16)).astype(np.float32) / 255.0
    roi[:] = (roi * (1 - (sh * 0.28 * alpha)[..., None])).astype(np.uint8)

    # 2 — very subtle transparent ground fill with a soft edge
    fill = np.zeros(roi.shape[:2], np.uint8)
    cv2.ellipse(fill, c, (rw, rh), 0, 0, 360, 255, -1, cv2.LINE_AA)
    fillf = cv2.GaussianBlur(fill, (0, 0), max(1.5, lw * 0.9)).astype(np.float32) / 255.0
    fa = (fillf * 0.07 * alpha)[..., None]
    roi[:] = (roi * (1 - fa) + tint * fa).astype(np.uint8)

    # 3 — controlled glow hugging the rim (no neon bloom)
    ring_l = np.zeros(roi.shape[:2], np.uint8)
    cv2.ellipse(ring_l, c, (rw, rh), 0, 0, 360, 255, lw, cv2.LINE_AA)
    glowf = cv2.GaussianBlur(ring_l, (0, 0), max(1.5, lw * 1.6)).astype(np.float32) / 255.0
    ga = (glowf * 0.20 * alpha)[..., None]
    roi[:] = (roi * (1 - ga) + tint * ga).astype(np.uint8)

    # 4 — the painted line: soft-edged + a faint offset under-stroke for depth
    depth = np.zeros(roi.shape[:2], np.uint8)
    cv2.ellipse(depth, (c[0], c[1] + max(1, lw // 2)), (rw, rh), 0, 0, 360, 255,
                lw + 2, cv2.LINE_AA)
    da = (cv2.GaussianBlur(depth, (0, 0), max(1.0, lw * 0.5)).astype(np.float32)
          / 255.0 * 0.26 * alpha)[..., None]
    roi[:] = (roi * (1 - da)).astype(np.uint8)
    linef = cv2.GaussianBlur(ring_l, (0, 0), max(0.8, lw * 0.35)).astype(np.float32) / 255.0
    la = (linef * 0.80 * alpha)[..., None]
    roi[:] = (roi * (1 - la) + tint * la).astype(np.uint8)

    # 5 — player in front: restore the silhouette over the marker (full ellipse
    # width so a wide stance/second foot is always covered); slight dilation
    # kills anti-alias halos along boots/legs
    hsv = cv2.cvtColor(orig, cv2.COLOR_BGR2HSV)
    ng = (cv2.inRange(hsv, (30, 40, 40), (90, 255, 255)) == 0).astype(np.uint8) * 255
    sel = np.zeros(ng.shape, np.uint8)
    xl, xh = max(0, c[0] - int(rw * 0.95)), min(roi.shape[1], c[0] + int(rw * 0.95))
    yl, yh = max(0, c[1] - rh * 4), min(roi.shape[0], c[1] + rh + 1)
    sel[yl:yh, xl:xh] = 255
    m2 = cv2.bitwise_and(ng, sel)
    m2 = cv2.dilate(m2, np.ones((3, 3), np.uint8))
    m2 = (cv2.GaussianBlur(m2, (7, 7), 0).astype(np.float32) / 255.0)[..., None]
    roi[:] = (orig * m2 + roi * (1 - m2)).astype(np.uint8)


def _window_points(track_points: list, t_moment: float, pre: float, post: float):
    """Contiguous, dense run of track points around the cited moment.
    Returns (points, w0, w1, coverage) or None when the track can't back a clip."""
    pts = sorted(
        (p for p in (track_points or [])
         if isinstance(p, dict) and isinstance(p.get("t"), (int, float))
         and t_moment - pre - 1.0 <= float(p["t"]) <= t_moment + post + 1.0),
        key=lambda p: float(p["t"]),
    )
    if not pts:
        return None
    i_seed = min(range(len(pts)), key=lambda i: abs(float(pts[i]["t"]) - t_moment))
    if abs(float(pts[i_seed]["t"]) - t_moment) > SEED_TOL:
        return None
    lo = hi = i_seed
    while lo - 1 >= 0 and float(pts[lo]["t"]) - float(pts[lo - 1]["t"]) <= MAX_GAP_SEC:
        lo -= 1
    while hi + 1 < len(pts) and float(pts[hi + 1]["t"]) - float(pts[hi]["t"]) <= MAX_GAP_SEC:
        hi += 1
    seg = pts[lo:hi + 1]
    w0 = max(float(seg[0]["t"]), t_moment - pre)
    w1 = min(float(seg[-1]["t"]), t_moment + post)
    if w1 - w0 < MIN_CLIP_SEC:
        logger.info(f"[teleclip] tracked window too short ({w1 - w0:.1f}s) — no clip")
        return None
    inside = [p for p in seg if w0 <= float(p["t"]) <= w1]
    if len(inside) < 4:
        return None
    dts = [float(b["t"]) - float(a["t"]) for a, b in zip(inside, inside[1:])]
    med_dt = sorted(dts)[len(dts) // 2] if dts else 0.08
    expected = max(1.0, (w1 - w0) / max(0.02, med_dt))
    coverage = min(1.0, len(inside) / expected)
    if coverage < MIN_COVERAGE:
        logger.info(f"[teleclip] track coverage {coverage:.2f} below gate — no clip")
        return None
    return inside, w0, w1, coverage


def _smooth(pts: list) -> list:
    """Moving average over ±2 samples on (cx, feet_y, w, h)."""
    raw = [(float(p["t"]),
            float(p["x"]) + float(p["w"]) / 2.0,
            float(p["y"]) + float(p["h"]),
            float(p["w"]),
            float(p["h"])) for p in pts]
    out = []
    for i in range(len(raw)):
        n = raw[max(0, i - 2):i + 3]
        out.append((raw[i][0],
                    sum(v[1] for v in n) / len(n),
                    sum(v[2] for v in n) / len(n),
                    sum(v[3] for v in n) / len(n),
                    sum(v[4] for v in n) / len(n)))
    return out


def _interp(sm: list, t: float):
    if t <= sm[0][0]:
        return sm[0][1:]
    if t >= sm[-1][0]:
        return sm[-1][1:]
    for a, b in zip(sm, sm[1:]):
        if a[0] <= t <= b[0]:
            f = (t - a[0]) / max(1e-6, b[0] - a[0])
            return tuple(a[i] + (b[i] - a[i]) * f for i in (1, 2, 3, 4))
    return sm[-1][1:]


pos_at = _interp  # public: (cx, feet_y, w, h) at time t from a smoothed position list


def plan_window(track_points: list, t_moment: float, pre: float = 1.8, post: float = 1.8):
    """Plan the clip window without rendering. Returns
    {"w0","w1","coverage","sm"} or None when the track can't back a clip."""
    win = _window_points(track_points, t_moment, pre, post)
    if not win:
        return None
    pts, w0, w1, coverage = win
    return {"w0": w0, "w1": w1, "coverage": coverage, "sm": _smooth(pts)}


def _risk_alpha(t: float, windows, fade: float = FADE_SEC) -> float:
    """P19 marker state logic: inside a switch-risk window the ring fades
    OUT smoothly (never jumps to another player); it fades back in after."""
    m = 1.0
    for r0, r1 in windows or []:
        if r0 - fade < t < r1 + fade:
            if t < r0:
                m = min(m, (r0 - t) / fade)
            elif t > r1:
                m = min(m, (t - r1) / fade)
            else:
                return 0.0
    return m


def generate_tracked_clip(video_path: str, t_moment: float, track_points: list, out_path: str,
                          label: str = "PLAYER · TRACKED", pre: float = 1.8, post: float = 1.8,
                          risky_windows: list | None = None):
    """Returns {"ok": True, "coverage": float, "start": s, "end": s} or None. Never raises."""
    cap = None
    writer = None
    try:
        plan = plan_window(track_points, t_moment, pre, post)
        if not plan:
            return None
        w0, w1, coverage, sm = plan["w0"], plan["w1"], plan["coverage"], plan["sm"]
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
        if fps <= 1 or fps > 60:
            fps = 15.0
        W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if W < 100 or H < 100:
            return None
        f0, f1 = int(w0 * fps), max(int(w1 * fps) - 1, int(w0 * fps) + 1)
        fade = max(2, int(fps * FADE_SEC))

        import imageio
        writer = imageio.get_writer(out_path, fps=round(fps, 2), codec="libx264",
                                    quality=7, pixelformat="yuv420p", macro_block_size=1,
                                    output_params=["-movflags", "+faststart"])
        cap.set(cv2.CAP_PROP_POS_FRAMES, f0)
        idx = f0
        ema_wh = None
        ring_state = {}  # ground-anchor temporal smoothing across frames
        while idx <= f1:
            ok, frame = cap.read()
            if not ok:
                break
            a = min(1.0, (idx - f0 + 1) / fade, (f1 - idx + 1) / fade)
            a *= _risk_alpha(idx / fps, risky_windows)
            cx, feet_y, bw, bh = _interp(sm, idx / fps)
            # size stability: EMA on box size only (position stays responsive)
            if ema_wh is None:
                ema_wh = [bw, bh]
            else:
                ema_wh[0] += 0.25 * (bw - ema_wh[0])
                ema_wh[1] += 0.25 * (bh - ema_wh[1])
            bw, bh = ema_wh[0], ema_wh[1]
            est_h = min(max(bh * H, H * 0.045), W * 0.333, H * 0.42)
            rw = min(max(est_h * 0.30, W * 0.024), W * 0.10)
            feet_px = feet_y * H - min(bh * H * 0.08, rw * 0.34 * 0.8)
            _draw_ring(frame, cx, feet_px / H, bw, bh, a, state=ring_state)
            # no label/chip: the grounded ellipse alone is the visual marker
            writer.append_data(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            idx += 1
        writer.close()
        writer = None
        if not Path(out_path).exists() or Path(out_path).stat().st_size < 20_000:
            return None
        return {"ok": True, "coverage": round(coverage, 2), "start": round(w0, 2), "end": round(w1, 2)}
    except Exception as e:
        logger.warning(f"[teleclip] failed for {video_path}@{t_moment}: {e}")
        try:
            Path(out_path).unlink(missing_ok=True)
        except Exception:
            pass
        return None
    finally:
        try:
            if writer is not None:
                writer.close()
        except Exception:
            pass
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass
