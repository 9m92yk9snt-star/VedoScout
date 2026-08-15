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
MIN_CLIP_SEC = 1.4
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


def _draw_ring(frame, cx: float, feet_y: float, w: float, h: float, alpha: float = 1.0):
    """Premium grounded ellipse under the player's feet: soft transparent fill,
    subtle glow, crisp volt ring with a dark under-stroke for depth. Sized from
    PLAYER HEIGHT so the player stands inside the marker at any distance."""
    if alpha <= 0.02:
        return
    fh, fw = frame.shape[:2]
    est_h = min(max(h * fh, fh * 0.045), fw * 0.333, fh * 0.42)
    rw = int(min(max(est_h * 0.30, fw * 0.024), fw * 0.10))
    rh = max(4, int(rw * 0.34))
    lw = max(2, int(rw * 0.085))
    px, py = int(cx * fw), int(min(feet_y, 0.995) * fh)
    m = lw * 8
    x0, y0 = max(0, px - rw - m), max(0, py - rh - m)
    x1, y1 = min(fw, px + rw + m), min(fh, py + rh + m)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return
    roi = frame[y0:y1, x0:x1]
    orig = roi.copy()
    c = (px - x0, py - y0)
    # glow — blurred ring blended per-pixel so only the ring glows
    glow = np.zeros_like(roi)
    cv2.ellipse(glow, c, (rw, rh), 0, 0, 360, (0, 255, 204), lw * 3, cv2.LINE_AA)
    glow = cv2.GaussianBlur(glow, (0, 0), max(1.0, lw * 1.4))
    ga = (glow.max(axis=2).astype(np.float32) / 255.0 * 0.45 * alpha)[..., None]
    roi[:] = (roi * (1 - ga) + VOLT_BGR * ga).astype(np.uint8)
    # soft transparent fill grounds the marker on the pitch
    fill = np.zeros(roi.shape[:2], np.uint8)
    cv2.ellipse(fill, c, (rw, rh), 0, 0, 360, 255, -1, cv2.LINE_AA)
    fa = (fill.astype(np.float32) / 255.0 * 0.10 * alpha)[..., None]
    roi[:] = (roi * (1 - fa) + VOLT_BGR * fa).astype(np.uint8)
    # crisp ring with dark under-stroke for depth
    ov = roi.copy()
    cv2.ellipse(ov, c, (rw, rh), 0, 0, 360, (20, 34, 14), lw + 2, cv2.LINE_AA)
    cv2.ellipse(ov, c, (rw, rh), 0, 0, 360, (0, 255, 204), lw, cv2.LINE_AA)
    a = 0.92 * min(1.0, alpha)
    cv2.addWeighted(ov, a, roi, 1 - a, 0, dst=roi)
    # player in front: restore the player's silhouette over the ring so the
    # line never crosses the front of boots/legs (marker painted on the pitch)
    hsv = cv2.cvtColor(orig, cv2.COLOR_BGR2HSV)
    ng = cv2.inRange(hsv, (30, 40, 40), (90, 255, 255)) == 0
    sel = np.zeros(ng.shape, bool)
    xl, xh = max(0, c[0] - int(rw * 0.6)), min(roi.shape[1], c[0] + int(rw * 0.6))
    yl, yh = max(0, c[1] - rh * 3), min(roi.shape[0], c[1] + rh)
    sel[yl:yh, xl:xh] = True
    m2 = (ng & sel).astype(np.uint8) * 255
    m2 = (cv2.GaussianBlur(m2, (5, 5), 0).astype(np.float32) / 255.0)[..., None]
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
        while idx <= f1:
            ok, frame = cap.read()
            if not ok:
                break
            a = min(1.0, (idx - f0 + 1) / fade, (f1 - idx + 1) / fade)
            a *= _risk_alpha(idx / fps, risky_windows)
            cx, feet_y, bw, bh = _interp(sm, idx / fps)
            est_h = min(max(bh * H, H * 0.045), W * 0.333, H * 0.42)
            rw = min(max(est_h * 0.30, W * 0.024), W * 0.10)
            feet_px = feet_y * H - min(bh * H * 0.08, rw * 0.34 * 0.8)
            _draw_ring(frame, cx, feet_px / H, bw, bh, a)
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
