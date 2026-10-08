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


def _color_hist(hsv, box_px_gray, scale: float, mask=None):
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
    owned = None
    if mask is not None:
        full_height = max(1, int((box_px_gray[3] - box_px_gray[1]) * scale))
        owned = cv2.resize(mask, (roi.shape[1], full_height), interpolation=cv2.INTER_NEAREST)[:roi.shape[0]]
        if int((owned > 0).sum()) < 10:
            return None
    hist = cv2.calcHist([roi], [0, 1], owned, [30, 32], [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
    return hist


def _color_sim(ref_hist, hsv, box_px_gray, scale: float, mask=None) -> float | None:
    cand = _color_hist(hsv, box_px_gray, scale, mask)
    if cand is None or ref_hist is None:
        return None
    return float(cv2.compareHist(ref_hist, cand, cv2.HISTCMP_CORREL))


def _record(out: dict, t: float, cur, W: int, H: int, conf: float, pose_degrees: float = 0.0):
    key = round(t, 2)
    rec = {
        "t": key,
        "x": round(cur[0] / W, 4), "y": round(cur[1] / H, 4),
        "w": round((cur[2] - cur[0]) / W, 4), "h": round((cur[3] - cur[1]) / H, 4),
        "conf": round(float(conf), 3),
    }
    if pose_degrees:
        rec.update(matching_method="masked_pose", pose_degrees=round(float(pose_degrees), 1))
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


_DOUBT_REASONS = {
    "lost": "player lost — no confident match",
    "ambiguous": "two similar players — identity ambiguous",
    "contaminated": "player overlap — geometry ambiguous",
    "jump": "implausible jump — geometry rejected",
    "colour": "kit-colour change — possible player crossover",
}


def _masked_ncc(region, template, mask):
    """Zero-mean NCC over selected pixels; background contributes no votes."""
    weight = (mask > 0).astype(np.float32)
    count = float(weight.sum())
    if count < 20:
        return np.full((region.shape[0] - template.shape[0] + 1, region.shape[1] - template.shape[1] + 1), -1, np.float32)
    source, target = region.astype(np.float32), template.astype(np.float32)
    centered = (target - float((target * weight).sum() / count)) * weight
    energy = float((centered * centered).sum())
    sums = cv2.matchTemplate(source, weight, cv2.TM_CCORR)
    squares = cv2.matchTemplate(source * source, weight, cv2.TM_CCORR)
    numerator = cv2.matchTemplate(source, centered, cv2.TM_CCORR)
    denominator = np.sqrt(np.maximum(0, squares - sums * sums / count) * energy)
    return np.clip(np.divide(numerator, denominator, out=np.full_like(numerator, -1), where=denominator > 1e-4), -1, 1)


def _pose_templates(template, mask):
    """Bounded tilt hypotheses using only original, selected foreground pixels.

    No current-frame pixels are learned. Premultiplied warping prevents the
    background from bleeding into a tilted foreground template. Clipped
    hypotheses must retain at least 90% of the original foreground support.
    """
    yield template, mask, 0.0
    weight = (mask > 0).astype(np.float32)
    ys, xs = np.nonzero(weight)
    if len(xs) < 20:
        return
    height, width = template.shape
    centre = (float(xs.mean()), float(ys.mean()))
    for angle in (-15.0, -7.5, 7.5, 15.0):
        transform = cv2.getRotationMatrix2D(centre, angle, 1.0)
        alpha = cv2.warpAffine(weight, transform, (width, height))
        owned = (alpha >= 0.5).astype(np.uint8) * 255
        if int((owned > 0).sum()) < len(xs) * 0.9:
            continue
        pixels = cv2.warpAffine(template.astype(np.float32) * weight, transform, (width, height))
        tilted = np.divide(pixels, alpha, out=np.zeros_like(pixels), where=alpha > 1e-6)
        yield tilted.clip(0, 255).astype(np.uint8), owned, angle


def _match_region(g, tmpl, bw, bh, bw0, bh0, pcx, pcy, gx, gy, seed_mask=None, pose_search=False):
    """Bounded multi-scale NCC search around (pcx, pcy)."""
    H, W = g.shape[:2]
    sx0, sy0 = max(0, int(pcx - bw / 2.0 - gx)), max(0, int(pcy - bh / 2.0 - gy))
    sx1, sy1 = min(W, int(pcx + bw / 2.0 + gx)), min(H, int(pcy + bh / 2.0 + gy))
    region = g[sy0:sy1, sx0:sx1]
    variants = list(_pose_templates(tmpl, seed_mask)) if pose_search and seed_mask is not None else None
    best = None
    unit = None
    for s in tracking_geometry.scale_candidates(bw, bh, bw0, bh0):
        tw = max(6, int(round(tmpl.shape[1] * s)))
        th = max(6, int(round(tmpl.shape[0] * s)))
        if region.shape[0] <= th or region.shape[1] <= tw:
            continue
        tm = tmpl if (tw, th) == (tmpl.shape[1], tmpl.shape[0]) else cv2.resize(tmpl, (tw, th))
        if variants is None:
            res = cv2.matchTemplate(region, tm, cv2.TM_CCOEFF_NORMED) if seed_mask is None else _masked_ncc(
                region, tm, cv2.resize(seed_mask, (tw, th), interpolation=cv2.INTER_NEAREST))
            _mn, mx, _mnl, ml = cv2.minMaxLoc(res)
            cand = (mx, ml, tw, th, res, sx0, sy0)
        else:
            masks, responses = [], []
            for source, owned, _angle in variants:
                candidate_mask = cv2.resize(owned, (tw, th), interpolation=cv2.INTER_NEAREST)
                masks.append(candidate_mask)
                responses.append(_masked_ncc(region, cv2.resize(source, (tw, th)), candidate_mask))
            stack = np.stack(responses)
            # All orientations vote in one response map. A rival at another
            # orientation must remain visible to ambiguity/crowding gates.
            res = stack.max(axis=0)
            _mn, mx, _mnl, ml = cv2.minMaxLoc(res)
            winner = int(stack[:, ml[1], ml[0]].argmax())
            cand = (mx, ml, tw, th, res, sx0, sy0, masks[winner], variants[winner][2])
        if s == 1.0:
            unit = cand
        if best is None or mx > best[0]:
            best = cand
    # a non-unit scale must win by a real margin — noise must not ratchet
    # the bbox smaller/larger frame after frame (scale drift)
    if best is not None and unit is not None and best is not unit \
            and best[0] < unit[0] + tracking_geometry.SCALE_HYST:
        best = unit
    return best


def _judge_candidate(best, ref_hist, hsv, scale, pcx, pcy, exp, dtp, lcx, lcy, cam_acc, bw, bh, dt, seed_mask=None):
    """Run every safety gate on a matched candidate.

    Returns (verdict, cand_box, payload):
      accept / confirm — authoritative geometry
      hold             — bounded direction-change candidate (provisional)
      ambiguous / contaminated / colour / jump — rejection reasons
    """
    mx, ml, tw, th, res, sx0, sy0 = best[:7]
    if len(best) > 7:
        seed_mask = best[7]
    # same-kit crossover safety: a spatially distinct near-equal rival means
    # this frame is NOT authoritative geometry
    mx2, _ml2 = tracking_geometry.second_peak(res, ml, tw, th)
    if tracking_geometry.is_ambiguous(mx, mx2, MATCH_MIN):
        return "ambiguous", None, None
    # close-crowding gate: merged/overlapping bodies contaminate the match
    # support — do not learn or record it
    if tracking_geometry.is_contaminated(res, ml, tw, th, mx):
        return "contaminated", None, None
    cand_box = [sx0 + ml[0], sy0 + ml[1], sx0 + ml[0] + tw, sy0 + ml[1] + th]
    ccx, ccy = (cand_box[0] + cand_box[2]) / 2.0, (cand_box[1] + cand_box[3]) / 2.0
    # colour veto (every candidate, provisional ones included)
    # The same selected-pixel footprint must vote on both sides. Comparing a
    # masked jersey reference to the whole candidate adds grass/opponent votes
    # only to the candidate and can veto the correct player. This footprint is
    # matching assistance; it is not a new ownership mask for that frame.
    csim = _color_sim(ref_hist, hsv, cand_box, scale, seed_mask) if seed_mask is not None else _color_sim(ref_hist, hsv, cand_box, scale)
    if csim is not None and csim < COLOR_MIN:
        return "colour", None, None
    payload = {"mx": mx, "tw": tw, "th": th}
    if len(best) > 8:
        payload["pose_degrees"] = best[8]
    # spatial ownership: prediction is assistance, not a hard identity prior
    if tracking_geometry.plausible_motion(ccx - pcx, ccy - pcy, bw, bh, dt):
        return "accept", cand_box, payload
    if exp is not None and tracking_geometry.plausible_motion(
            ccx - exp[0], ccy - exp[1], bw, bh, dtp):
        return "confirm", cand_box, payload  # this frame confirmed the held trajectory
    if (abs(ccx - lcx - cam_acc[0]) <= bw * (0.45 + tracking_geometry.BOOT_FRAC)
            and abs(ccy - lcy - cam_acc[1]) <= bh * (0.45 + tracking_geometry.BOOT_FRAC)):
        pv = max(dt, 1e-6)
        return "hold", cand_box, {"cx": ccx, "cy": ccy, "t": None,
                                  "vx": (ccx - lcx - cam_acc[0]) / pv,
                                  "vy": (ccy - lcy - cam_acc[1]) / pv,
                                  "cam": (cam_acc[0], cam_acc[1])}
    return "jump", None, None


def _distinct(b1, b2, bw, bh):
    """True when two candidate boxes are spatially distinct bodies."""
    if b1 is None or b2 is None:
        return False
    dx = abs((b1[0] + b1[2]) - (b2[0] + b2[2])) / 2.0
    dy = abs((b1[1] + b1[3]) - (b2[1] + b2[3])) / 2.0
    return dx > bw * 0.5 or dy > bh * 0.5


def _provisional_from(v2, box2, pay2, prov_old, cam_acc, dtp, lcx, lcy, dt, t):
    """Build/extend the held provisional trajectory from a safe recovery
    candidate — kept for prediction only, never recorded or learned."""
    if v2 == "hold":
        pay2["t"] = t
        return pay2
    ccx, ccy = (box2[0] + box2[2]) / 2.0, (box2[1] + box2[3]) / 2.0
    if v2 == "confirm" and prov_old is not None:
        pv = max(dtp, 1e-6)
        return {"cx": ccx, "cy": ccy, "t": t,
                "vx": (ccx - prov_old["cx"] - cam_acc[0] + prov_old["cam"][0]) / pv,
                "vy": (ccy - prov_old["cy"] - cam_acc[1] + prov_old["cam"][1]) / pv,
                "cam": (cam_acc[0], cam_acc[1])}
    pv = max(dt, 1e-6)
    return {"cx": ccx, "cy": ccy, "t": t,
            "vx": (ccx - lcx - cam_acc[0]) / pv,
            "vy": (ccy - lcy - cam_acc[1]) / pv,
            "cam": (cam_acc[0], cam_acc[1])}


def _run_direction(frames, i0: int, box_px, out: dict, direction: int, doubts: list | None = None,
                   cuts: list | None = None, seed_mask=None):
    _t0, g0, hsv0, tiny0 = frames[i0]
    tmpl0 = _crop(g0, box_px)
    if tmpl0 is None:
        return
    if seed_mask is not None:
        seed_mask = cv2.resize(seed_mask, (tmpl0.shape[1], tmpl0.shape[0]), interpolation=cv2.INTER_NEAREST)
    tmpl = tmpl0
    bw0, bh0 = box_px[2] - box_px[0], box_px[3] - box_px[1]  # seed size = scale bounds
    bw, bh = float(bw0), float(bh0)
    H, W = g0.shape[:2]
    scale = hsv0.shape[1] / float(W)  # gray-px → colour-px
    ref_hist = _color_hist(hsv0, box_px, scale, seed_mask)  # FIXED selected-pixel signature
    steps = 0
    streak = 0        # unified budget: consecutive frames with NO accepted geometry
    tally: dict = {}  # rejection reasons inside the current streak (diagnostics)
    last_reason = "lost"
    lock_ts: list = []  # timestamps of the current near-perfect-match streak
    cur = list(box_px)
    vel = (0.0, 0.0)          # camera-compensated player velocity (gray px/s)
    t_last = frames[i0][0]    # media time of the last ACCEPTED geometry
    cam_acc = [0.0, 0.0]      # camera shift accumulated since last accept (gray px)
    prov = None               # provisional candidate — held, never recorded/learned
    prev_tiny = tiny0
    tiny_scale = W / float(tiny0.shape[1])
    end = len(frames) if direction > 0 else -1

    def _reject(reason: str, t: float) -> bool:
        """Unified conservative miss budget: reset ONLY by a full accept."""
        nonlocal streak, last_reason
        streak += 1
        last_reason = reason
        tally[reason] = tally.get(reason, 0) + 1
        if streak >= MAX_MISSES:
            top = max(tally, key=lambda k: (tally[k], 1 if k == last_reason else 0))
            _doubt(doubts, t, cur, W, H, _DOUBT_REASONS[top])
            return True
        return False

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
        lcx, lcy = (cur[0] + cur[2]) / 2.0, (cur[1] + cur[3]) / 2.0
        # ── bounded motion prediction: search follows camera + player motion ──
        pdx, pdy = tracking_geometry.predict_displacement(vel, dt, bw, bh)
        pcx, pcy = lcx + cam_acc[0] + pdx, lcy + cam_acc[1] + pdy
        # camera-compensated continuation of a held provisional trajectory
        exp = None
        dtp = 0.0
        if prov is not None:
            dtp = abs(t - prov["t"])
            exp = (prov["cx"] + prov["vx"] * dtp + cam_acc[0] - prov["cam"][0],
                   prov["cy"] + prov["vy"] * dtp + cam_acc[1] - prov["cam"][1])
        # ── pass 1: narrow prediction-centred search (normal path) ──
        ex = min(abs(pdx) * 0.5 + abs(cam_acc[0]) * 0.25, bw * 0.6)
        ey = min(abs(pdy) * 0.5 + abs(cam_acc[1]) * 0.25, bh * 0.6)
        kwargs = {"seed_mask": seed_mask} if seed_mask is not None else {}
        best = _match_region(g, tmpl, bw, bh, bw0, bh0, pcx, pcy, bw * 0.45 + ex, bh * 0.45 + ey, **kwargs)
        # ── candidate evaluation with dual-hypothesis arbitration (C02):
        # prediction is geometry assistance — it must NEVER become identity
        # authority. An unsafe primary verdict (lost/colour/jump) allows ONE
        # bounded recovery pass; a primary accept that leans on stale velocity
        # (provisional trajectory alive, or large displacement) must also be
        # arbitrated against the recovery hypothesis before it may become
        # authoritative. Ambiguity/contamination never triggers recovery —
        # withholding IS the correct response to crowded geometry. ──
        v1, box1, pay1 = "lost", None, None
        if best is not None and best[0] >= MATCH_MIN:
            v1, box1, pay1 = _judge_candidate(
                best, ref_hist, hsv, scale, pcx, pcy, exp, dtp,
                lcx, lcy, cam_acc, bw, bh, dt, **kwargs)
        need_recovery = v1 in ("lost", "colour", "jump")
        if v1 == "accept":
            c1x, c1y = (box1[0] + box1[2]) / 2.0, (box1[1] + box1[3]) / 2.0
            far = not tracking_geometry.plausible_motion(
                c1x - lcx - cam_acc[0], c1y - lcy - cam_acc[1], bw, bh, dt)
            need_recovery = prov is not None or far
        v2, box2, pay2 = "lost", None, None
        solid2 = False
        if need_recovery:
            # bounded recovery — NOT a global search; all gates re-apply
            bcx, bcy = exp if exp is not None else (lcx + cam_acc[0], lcy + cam_acc[1])
            reach = 0.45 + tracking_geometry.BOOT_FRAC
            recovery_kwargs = {**kwargs, "pose_search": True} if seed_mask is not None and ref_hist is not None and v1 == "lost" else kwargs
            best2 = _match_region(g, tmpl, bw, bh, bw0, bh0, bcx, bcy, bw * reach, bh * reach, **recovery_kwargs)
            if best2 is not None and best2[0] >= MATCH_MIN:
                v2, box2, pay2 = _judge_candidate(
                    best2, ref_hist, hsv, scale, pcx, pcy, exp, dtp,
                    lcx, lcy, cam_acc, bw, bh, dt, **kwargs)
                # only a SOLID recovery match is a credible second hypothesis;
                # junk-level background peaks must not veto a safe primary
                solid2 = best2[0] >= tracking_geometry.CONTAM_MIN
        verdict, cand_box, payload = v1, box1, pay1
        if v1 == "accept" and need_recovery:
            if v2 in ("accept", "confirm", "hold") and solid2 and _distinct(box1, box2, bw, bh):
                # C: two spatially distinct safe hypotheses → identity is NOT
                # selectable this frame. Record neither, learn neither; the
                # recovery trajectory stays alive — a stale-velocity candidate
                # must not erase it.
                prov = _provisional_from(v2, box2, pay2, prov, cam_acc, dtp, lcx, lcy, dt, t)
                if _reject("ambiguous", t):
                    break
                continue
            if v2 in ("ambiguous", "contaminated") and solid2:
                # the recovery region is genuinely crowded — fail closed
                prov = None
                if _reject(v2, t):
                    break
                continue
            # A: only the primary hypothesis is safe (or the same body twice)
        elif v1 == "jump":
            if v2 == "confirm":
                verdict, cand_box, payload = v2, box2, pay2
            elif v2 in ("accept", "hold"):
                # a safe recovery hypothesis next to a distinct unsafe primary
                # candidate is HELD, never instantly authoritative
                prov = _provisional_from(v2, box2, pay2, prov, cam_acc, dtp, lcx, lcy, dt, t)
                if _reject("jump", t):
                    break
                continue
            else:
                prov = None
                reason = v2 if v2 in ("ambiguous", "contaminated", "colour") else "jump"
                if _reject(reason, t):
                    break
                continue
        elif v1 in ("lost", "colour"):
            if v2 in ("accept", "confirm"):
                verdict, cand_box, payload = v2, box2, pay2
            elif v2 == "hold":
                prov = _provisional_from(v2, box2, pay2, prov, cam_acc, dtp, lcx, lcy, dt, t)
                if _reject("jump", t):
                    break
                continue
            else:
                prov = None
                reason = v2 if v2 in ("ambiguous", "contaminated", "colour") else v1
                if _reject(reason, t):
                    break
                continue
        if verdict in ("lost", "ambiguous", "contaminated", "colour"):
            prov = None
            if _reject(verdict, t):
                break
            continue
        if verdict == "hold":
            # bounded direction-change / bootstrap candidate: HOLD as
            # provisional — not recorded, not learned, no identity switch
            payload["t"] = t
            prov = payload
            if _reject("jump", t):
                break
            continue
        if verdict == "jump":
            prov = None
            if _reject("jump", t):
                break
            continue
        mx, tw, th = payload["mx"], payload["tw"], payload["th"]
        ccx, ccy = (cand_box[0] + cand_box[2]) / 2.0, (cand_box[1] + cand_box[3]) / 2.0
        # ── ACCEPT (or CONFIRM a held direction change: velocity resets to the
        # newly confirmed trajectory instead of the stale prediction) ──
        if verdict == "confirm":
            pv = max(dtp, 1e-6)
            vel = ((ccx - prov["cx"] - cam_acc[0] + prov["cam"][0]) / pv,
                   (ccy - prov["cy"] - cam_acc[1] + prov["cam"][1]) / pv)
        else:
            vel = tracking_geometry.update_velocity(vel, (lcx, lcy), (ccx, ccy), cam_acc, dt)
        prov = None
        streak = 0
        tally = {}
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
            drift = float((cv2.matchTemplate(c0, tmpl0, cv2.TM_CCOEFF_NORMED) if seed_mask is None else _masked_ncc(c0, tmpl0, seed_mask))[0][0])
            if drift < DRIFT_MIN:
                _doubt(doubts, t, cur, W, H, "visual drift — tracker no longer certain")
                break  # drifted away from the original tap content — stop honestly
        if mx >= tracking_geometry.CONTAM_MIN and seed_mask is None:
            # template learning ONLY from solid accepted geometry — a weak
            # (possibly blended) match may be recorded but never learned
            tmpl = cand
        _record(out, t, cur, W, H, mx, pose_degrees=payload.get("pose_degrees", 0.0))


def track_player(video_path: str, anchors: list, t_off: float = 0.0, span: float = SPAN) -> dict:
    """Track the tapped player around every tap. Returns
    {points: [{t,x,y,w,h,conf}...], segments: [[t0,t1]...], t_off, hz}."""
    from player_selection import full_body_anchors, decode_mask
    seeds = [
        (float(a["t"]) + float(t_off or 0.0), a["box"], decode_mask(a.get("visible_mask")))
        for a in full_body_anchors((anchors or [])[:MAX_TRACKER_SEEDS])
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
        for t_seed, b, mask in seeds:
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
            kwargs = {"seed_mask": mask} if mask is not None else {}
            _run_direction(frames, i0, box_px, points, +1, doubts, cuts, **kwargs)
            _run_direction(frames, i0, box_px, points, -1, doubts, cuts, **kwargs)
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
    seed_times = [t for t, _b, _mask in seeds]
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
