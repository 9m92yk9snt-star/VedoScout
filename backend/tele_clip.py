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

import video_timebase

logger = logging.getLogger("elite-scout")

MIN_COVERAGE = 0.90   # user rule: only near-complete tracking ships, else fallback video
MAX_GAP_SEC = 0.5     # track samples further apart than this end the usable window
FADE_SEC = 0.35       # ring fades in/out — never pops
MIN_CLIP_SEC = 3.0    # minimum SHIPPED clip length — short verified windows are
                      # PADDED with raw context (marker hidden there), never
                      # replaced by the whole uploaded video
MIN_TRACKED_SEC = 1.2  # smallest verified core worth marking at all
PAD_PRE = 2.5         # raw context before the event (build-up)
PAD_POST = 3.5        # raw context after the event (completed action)
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


def _ground_anchor(frame, px, py, bw, bh, vx=0.0):
    """Visual Ground-Anchor Resolver: locate the target's ACTUAL ground
    contact (feet/hands footprint) near the accepted box instead of blindly
    trusting bbox bottom-center. Handles running, wide stance, distant
    players, duels (ownership stays within the accepted box's columns) and
    falls (contact may sit BELOW a torso-hugging box). `vx` (px/s, from the
    track itself) LEADS the search in the motion direction. Only the
    component CONNECTED to the player's body may provide the footprint —
    pitch lines / mud patches can never hijack the anchor. If the box holds
    no body mass, ONE unambiguous person-mass directly above in the box's
    own columns may rescue the anchor; otherwise returns None and the
    marker is HIDDEN (no marker is better than a wrong marker).
    Benign small-mask cases fall back to bbox bottom-center."""
    fh, fw = frame.shape[:2]
    lead = float(np.clip(vx * 0.25, -bw * 0.55, bw * 0.55))
    tcx = px + lead * 0.6
    x0 = int(max(0, px - bw * 0.62 + min(0.0, lead)))
    x1 = int(min(fw, px + bw * 0.62 + max(0.0, lead)))
    y1 = int(min(fh, py + bh * 0.45))

    def _mask(y_top):
        y0 = int(max(0, y_top))
        if x1 - x0 < 8 or y1 - y0 < 10:
            return None
        hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
        m = (cv2.inRange(hsv, (30, 40, 40), (90, 255, 255)) == 0).astype(np.uint8)
        return cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)), y0

    got = _mask(py - bh * 0.85)
    if got is None:
        return px, py, None
    pm, y0 = got
    _, lbl = cv2.connectedComponents(pm)
    tx0 = int(max(0, tcx - bw * 0.30 - x0))
    tx1 = int(min(x1 - x0, tcx + bw * 0.30 - x0))
    ty0 = int(max(0, py - bh * 0.80 - y0))
    ty1 = int(min(y1 - y0, py - bh * 0.25 - y0))
    rescue = False
    ids = []
    if tx1 > tx0 and ty1 > ty0:
        sub = lbl[ty0:ty1, tx0:tx1]
        ids, cnts = np.unique(sub[sub > 0], return_counts=True)
    if len(ids):
        order = np.argsort(cnts)[::-1]
        top = int(ids[order[0]])
        if len(ids) >= 2 and cnts[order[1]] >= 0.55 * cnts[order[0]]:
            # duel: a second body owns comparable mass of the contact area.
            # If it is horizontally distinct it is ANOTHER player — hide the
            # ring rather than guess which body the anchor belongs to.
            second = int(ids[order[1]])
            cx_a = float(np.nonzero(lbl == top)[1].mean())
            cx_b = float(np.nonzero(lbl == second)[1].mean())
            if abs(cx_a - cx_b) > bw * 0.35:
                return None
        pm = (lbl == top).astype(np.uint8)
    else:
        # box holds no body mass (track box may sit below the player during
        # fast motion). Identity-safe rescue: accept ONLY if exactly one
        # plausible person-mass stands in the box's own columns above.
        got = _mask(py - bh * 1.9)
        if got is None:
            return None
        pm2, y0 = got
        num, lbl2 = cv2.connectedComponents(pm2)
        cands = []
        for cid in range(1, num):
            comp = lbl2 == cid
            if int(comp.sum()) < 40:
                continue
            ys_c, xs_c = np.nonzero(comp)
            if (ys_c.max() - ys_c.min()) >= bh * 0.25 and abs(x0 + float(xs_c.mean()) - tcx) <= bw * 0.5:
                cands.append(cid)
        if len(cands) != 1:
            return None  # ambiguous or empty → hide, never guess
        pm = (lbl2 == cands[0]).astype(np.uint8)
        rescue = True
    ys, xs = np.nonzero(pm)
    if len(ys) < 30:
        return None if rescue else (px, py, None)
    # ownership: target's own columns, shifted along the motion direction
    keep = np.abs(xs + x0 - tcx) <= bw * 0.5 + abs(lead) * 0.5
    ys, xs = ys[keep], xs[keep]
    if len(ys) < 25:
        return None if rescue else (px, py, None)
    y_low = 0.0
    bx = by = None
    foot_w = 0.0
    for _ in range(6):
        y_low = float(np.percentile(ys, 96))
        band = ys >= y_low - max(3.0, bh * 0.07)
        if int(band.sum()) < 8:
            return None if rescue else (px, py, None)
        bx, by = xs[band], ys[band]
        foot_w = float(np.percentile(bx, 95) - np.percentile(bx, 5))
        band_h = float(by.max() - by.min())
        line_like = band_h <= max(3.0, bh * 0.06) and foot_w >= bw * 0.85
        if foot_w >= bw * 0.14 and not line_like:
            break  # plausible foot/contact footprint
        # line-like sliver (white pitch line running below the player) or a
        # razor-thin full-width stripe merged with the body — never a foot;
        # discard those rows and climb to the real footprint above
        keepy = ys < y_low - max(3.0, bh * 0.07)
        ys, xs = ys[keepy], xs[keepy]
        if len(ys) < 25:
            return None if rescue else (px, py, None)
    else:
        return None if rescue else (px, py, None)
    ax = x0 + float(np.median(bx))
    ay = y0 + float(np.percentile(by, 85))
    if abs(ax - px) > bw * (0.45 if not rescue else 0.55) + abs(lead):
        return None if rescue else (px, py, None)
    if not rescue and ay < py - bh * 0.35:
        # contact band floats too high (airborne stride / legs lost in the
        # mask) — NEVER ring a knee/shin/torso; the accepted bbox bottom is
        # the only safe plausible ground proxy
        return px, py, None
    return ax, min(ay, fh - 2.0), foot_w


def _draw_ring(frame, cx: float, feet_y: float, w: float, h: float, alpha: float = 1.0,
               state: dict | None = None, vx: float = 0.0):
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
    res = _ground_anchor(frame, cx * fw, min(feet_y, 0.995) * fh, bx_w, bx_h, vx=vx)
    if res is None:
        return  # no body at the box and no unambiguous rescue → no marker
    ax, ay, foot_w = res
    if state is not None:  # FIX05: DISPLAY smoothing only — damp jitter, then
        # CLAMP to the plausible envelope of the CURRENT accepted geometry.
        # The ring can never trail a sprint, overshoot a hard stop or keep
        # moving in the old direction after a reversal.
        raw_ax, raw_ay = ax, ay
        prev = state.get("anchor")
        if prev is not None:
            jump = float(np.hypot(ax - prev[0], ay - prev[1]))
            # sprint-responsive smoothing: fast steady motion is followed
            # closely (no trailing); only small jitter is damped
            k = min(0.85, 0.35 + 0.9 * (jump / max(1.0, bx_h * 0.5)))
            ax = prev[0] + k * (ax - prev[0])
            ay = prev[1] + k * (ay - prev[1])
            ax = float(np.clip(ax, raw_ax - bx_w * 0.30, raw_ax + bx_w * 0.30))
            ay = float(np.clip(ay, raw_ay - bx_h * 0.12, raw_ay + bx_h * 0.12))
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
    rw = min(max(rw, fw * 0.024), fw * 0.10)
    if state is not None:  # width continuity: no sudden ellipse size jumps
        prev_rw = state.get("rw")
        if prev_rw:
            rw = min(max(rw, prev_rw * 0.85), prev_rw * 1.15)
        state["rw"] = rw
    rw = int(rw)
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

    # 5 — player in front: restore ONLY body components that reach the
    # target's own footprint columns (FIX05) — a broad band mask could
    # resurrect a NEARBY player as part of the target; slight dilation
    # kills anti-alias halos along boots/legs
    hsv = cv2.cvtColor(orig, cv2.COLOR_BGR2HSV)
    ng = (cv2.inRange(hsv, (30, 40, 40), (90, 255, 255)) == 0).astype(np.uint8)
    sel = np.zeros(ng.shape, np.uint8)
    xl, xh = max(0, c[0] - int(rw * 0.95)), min(roi.shape[1], c[0] + int(rw * 0.95))
    yl, yh = max(0, c[1] - rh * 4), min(roi.shape[0], c[1] + rh + 1)
    sel[yl:yh, xl:xh] = 1
    num_c, lbl_c = cv2.connectedComponents(ng * sel)
    own_r = max(rw * 0.55, float(foot_w or 0.0) * 0.6)
    m2 = np.zeros(ng.shape, np.uint8)
    for cid in range(1, num_c):
        comp = lbl_c == cid
        xs_c = np.nonzero(comp)[1]
        if xs_c.size and float(np.abs(xs_c - c[0]).min()) <= own_r:
            m2[comp] = 255
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
    if w1 - w0 < MIN_TRACKED_SEC:
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
    """FIX05: the CURRENT accepted FIX04 geometry is the positional source of
    truth — (cx, feet_y) pass through RAW, so a sprint never trails, a hard
    stop never overshoots and a reversal never drifts in the old direction.
    Only SIZE (w, h) is averaged over ±2 samples; any display smoothing
    happens at the final anchor and is clamped to the current bbox envelope."""
    raw = [(float(p["t"]),
            float(p["x"]) + float(p["w"]) / 2.0,
            float(p["y"]) + float(p["h"]),
            float(p["w"]),
            float(p["h"])) for p in pts]
    out = []
    for i in range(len(raw)):
        n = raw[max(0, i - 2):i + 3]
        out.append((raw[i][0],
                    raw[i][1],
                    raw[i][2],
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
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        # FIX 03 — media duration is authoritative; frame_count/fps is an
        # explicit last-resort fallback only
        duration = video_timebase.media_duration_seconds(video_path)
        if not duration:
            duration = n_frames / fps if n_frames > 0 else None
        if duration is not None and duration < MIN_CLIP_SEC + 1.0:
            return None  # source itself is short → full video is the better proof
        # C: pad the CLIP with raw context around the verified window so short
        # verified windows still make a useful proof. The marker only shows
        # inside the verified window — the padding never claims identity.
        c0 = min(w0, t_moment - PAD_PRE)
        c1 = max(w1, t_moment + PAD_POST)
        if c1 - c0 < MIN_CLIP_SEC:
            half = (MIN_CLIP_SEC - (c1 - c0)) / 2.0
            c0, c1 = c0 - half, c1 + half
        c0 = max(0.0, c0)
        if duration is not None:
            c1 = min(duration - 0.05, c1)
        # FIX 03 — SOURCE FRAME ↔ TRACK TIME is matched via each decoded
        # frame's ACTUAL media timestamp (VFR-safe). C01 contract: grab →
        # read THAT frame's PTS → retrieve the SAME frame. The CFR output is
        # TIME-RESAMPLED from source PTS (drop/duplicate) so
        # output_local_time ≈ source_media_time − clip_start within one
        # output frame — VFR spacing is never flattened sequentially.
        eps = 1.0 / max(1.0, fps)
        fade_s = max(2.0 * eps, FADE_SEC)
        out_fps = max(1.0, round(fps, 2))
        out_dt = 1.0 / out_fps

        import imageio
        writer = imageio.get_writer(out_path, fps=out_fps, codec="libx264",
                                    quality=7, pixelformat="yuv420p", macro_block_size=1,
                                    output_params=["-movflags", "+faststart"])
        pre_ok, pre_t, _pre_fb = video_timebase.seek_with_preroll(cap, c0, fps)
        # the preroll helper already grabbed the first frame — consume it below
        ema_wh = None
        ring_state = {}  # ground-anchor temporal smoothing across frames
        next_out = 0.0        # local CFR output timeline (relative to c0)
        pending = None        # last rendered frame awaiting its output slots
        pending_local = None
        first_grab = (pre_ok, pre_t)
        while True:
            if first_grab is not None:
                ok, t = first_grab
                first_grab = None
            else:
                ok, t, _tb_fb = video_timebase.grab_frame_time_seconds(cap, fps)
            if not ok:
                break
            if t < c0 - 1e-3:
                continue  # keyframe seek landed early — skip up to clip start
            if t > c1:
                break     # stop on actual media time, never a computed frame count
            ok, frame = cap.retrieve()
            if not ok:
                break
            local = t - c0
            # nearest-frame CFR resample (previous/current lookahead): each
            # output slot takes the source frame whose canonical local PTS is
            # closest — never blindly the latest at/before the slot
            while pending is not None and next_out < local - 1e-9:
                if video_timebase.nearest_slot_choice(next_out, pending_local, local):
                    break  # the CURRENT frame is nearer to this CFR slot
                writer.append_data(pending)
                next_out += out_dt
            # marker alpha: visible only inside the VERIFIED window
            a = min(1.0, (t - w0 + eps) / fade_s, (w1 - t + eps) / fade_s)
            a = max(0.0, a) * _risk_alpha(t, risky_windows)
            cx, feet_y, bw, bh = _interp(sm, t)
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
            # horizontal track velocity (px/s) leads the anchor search during sprints
            ta, tb = min(w1, t + 0.15), max(w0, t - 0.15)
            vx_px = (_interp(sm, ta)[0] - _interp(sm, tb)[0]) / max(0.05, ta - tb) * W
            _draw_ring(frame, cx, feet_px / H, bw, bh, a, state=ring_state, vx=vx_px)
            # no label/chip: the grounded ellipse alone is the visual marker
            rendered = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            if pending is None:
                # head-pad: slots before the first real frame duplicate that
                # frame so every later frame keeps its exact canonical offset
                while next_out < local - 1e-9:
                    writer.append_data(rendered)
                    next_out += out_dt
            pending = rendered
            pending_local = local
        # tail: pad with the final frame so the playable duration matches the
        # canonical clip window (c1 - c0) within one output frame —
        # clip_start_ms/clip_end_ms/moment_local_ms describe this timeline
        if pending is not None:
            end_local = c1 - c0
            while next_out < end_local - out_dt / 2 - 1e-9:
                writer.append_data(pending)
                next_out += out_dt
            writer.append_data(pending)
        writer.close()
        writer = None
        if not Path(out_path).exists() or Path(out_path).stat().st_size < 20_000:
            return None
        return {"ok": True, "coverage": round(coverage, 2), "start": round(c0, 2),
                "end": round(c1, 2), "tracked_start": round(w0, 2), "tracked_end": round(w1, 2)}
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
