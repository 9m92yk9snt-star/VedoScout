"""FIX 04 — deterministic tracking geometry helpers.

Pure image-space geometry assistance for the tap-seeded production tracker:
bounded motion prediction, global camera-motion compensation, conservative
multi-scale adaptation and plausibility/ambiguity gates. No AI, no network,
no identity decisions — identity ground truth remains the user's taps, and
every gate prefers "no data" over guessing a nearby player.
"""
from __future__ import annotations

import cv2
import numpy as np

CAM_MIN_RESPONSE = 0.03   # phase-correlation response below this = unreliable → zero
PRED_MAX_FRAC = 1.2       # max predicted displacement per step, in bbox dims
VEL_ALPHA = 0.5           # EMA smoothing of camera-compensated player velocity
SCALE_STEP = 1.06         # per-acceptance relative scale change (±6%)
SCALE_HYST = 0.02         # non-unit scale must win by this margin (no drift ratchet)
SCALE_SEED_MIN = 0.55     # cumulative scale bounds vs the ORIGINAL tap bbox
SCALE_SEED_MAX = 1.9
AMBIG_RATIO = 0.8         # distinct second peak this close to best = ambiguous
AMBIG_DIST_FRAC = 0.6     # peaks farther apart than this × template dim = distinct
JUMP_BASE_FRAC = 0.5      # teleport allowance = bbox × (base + rate × dt)
JUMP_RATE_FRAC = 2.0
BOOT_FRAC = 0.75          # bounded bootstrap widening (extra margin, in bbox dims)
CONTAM_INNER = 0.25       # single-body mainlobe halfwidth (× template dim)
CONTAM_OUTER = 0.6        # near-field band outer edge (× template dim)
CONTAM_RATIO = 0.75       # rival support this close to best = contaminated
CONTAM_MIN = 0.55         # below this match quality the band is noise, not crowding


def estimate_camera_shift(prev_tiny, cur_tiny):
    """Global camera displacement (dx, dy) between two tiny float32 gray
    frames via phase correlation. Content at (x, y) in prev appears at
    (x+dx, y+dy) in cur. Fails safe to (0, 0) when unreliable."""
    try:
        if prev_tiny is None or cur_tiny is None or prev_tiny.shape != cur_tiny.shape:
            return 0.0, 0.0
        (dx, dy), response = cv2.phaseCorrelate(prev_tiny, cur_tiny)
        h, w = prev_tiny.shape[:2]
        if (not np.isfinite(dx) or not np.isfinite(dy) or response < CAM_MIN_RESPONSE
                or abs(dx) > w * 0.5 or abs(dy) > h * 0.5):
            return 0.0, 0.0
        return float(dx), float(dy)
    except Exception:
        return 0.0, 0.0


def predict_displacement(vel, dt, bw, bh):
    """Bounded constant-velocity displacement over ACTUAL media dt."""
    lx, ly = bw * PRED_MAX_FRAC, bh * PRED_MAX_FRAC
    return (max(-lx, min(lx, vel[0] * dt)), max(-ly, min(ly, vel[1] * dt)))


def update_velocity(vel, prev_center, new_center, cam_acc, dt):
    """EMA of the camera-compensated player residual velocity (px/s).
    A pure camera pan yields residual ≈ 0 — never a false player sprint."""
    if dt <= 1e-6:
        return vel
    rvx = (new_center[0] - prev_center[0] - cam_acc[0]) / dt
    rvy = (new_center[1] - prev_center[1] - cam_acc[1]) / dt
    return (VEL_ALPHA * rvx + (1.0 - VEL_ALPHA) * vel[0],
            VEL_ALPHA * rvy + (1.0 - VEL_ALPHA) * vel[1])


def plausible_motion(rdx, rdy, bw, bh, dt):
    """Geometry teleport gate: residual displacement from the predicted centre
    must stay bbox-relative-plausible for the elapsed media time."""
    ax = bw * (JUMP_BASE_FRAC + JUMP_RATE_FRAC * max(0.0, dt))
    ay = bh * (JUMP_BASE_FRAC + JUMP_RATE_FRAC * max(0.0, dt))
    return abs(rdx) <= ax and abs(rdy) <= ay


def scale_candidates(bw, bh, bw0, bh0):
    """Conservative multi-scale set: current size ±6%, always including 1.0,
    bounded relative to the original tap bbox — no explosion, no collapse."""
    out = [1.0]
    for s in (1.0 / SCALE_STEP, SCALE_STEP):
        nw, nh = bw * s, bh * s
        if (SCALE_SEED_MIN * bw0 <= nw <= SCALE_SEED_MAX * bw0
                and SCALE_SEED_MIN * bh0 <= nh <= SCALE_SEED_MAX * bh0):
            out.append(s)
    return out


def second_peak(res, best_loc, tw, th):
    """Best spatially DISTINCT runner-up in an NCC response map: suppress the
    best peak's neighbourhood, then take the map maximum."""
    r = res.copy()
    sx = max(4, int(tw * AMBIG_DIST_FRAC))
    sy = max(4, int(th * AMBIG_DIST_FRAC))
    x0, y0 = max(0, best_loc[0] - sx), max(0, best_loc[1] - sy)
    x1, y1 = min(r.shape[1], best_loc[0] + sx + 1), min(r.shape[0], best_loc[1] + sy + 1)
    r[y0:y1, x0:x1] = -1.0
    if r.size == 0:
        return 0.0, None
    _mn, mx2, _mnl, ml2 = cv2.minMaxLoc(r)
    return float(mx2), ml2


def is_ambiguous(best, second, floor):
    """Two spatially distinct candidates too close in score → the frame must
    not become authoritative geometry (same-kit crossover safety)."""
    return second >= floor and second >= best * AMBIG_RATIO


def near_rival(res, best_loc, tw, th):
    """Strongest match support in the near-field band around the best peak —
    outside a single body's autocorrelation mainlobe but closer than the
    'spatially distinct' radius. One isolated player leaves this band weak;
    a partially visible overlapping body raises it."""
    ix, iy = max(2, int(tw * CONTAM_INNER)), max(2, int(th * CONTAM_INNER))
    ox, oy = max(ix + 1, int(tw * CONTAM_OUTER)), max(iy + 1, int(th * CONTAM_OUTER))
    x0, y0 = max(0, best_loc[0] - ox), max(0, best_loc[1] - oy)
    x1, y1 = min(res.shape[1], best_loc[0] + ox + 1), min(res.shape[0], best_loc[1] + oy + 1)
    win = res[y0:y1, x0:x1].copy()
    if win.size == 0:
        return 0.0
    mx0, my0 = max(0, best_loc[0] - ix - x0), max(0, best_loc[1] - iy - y0)
    mx1, my1 = min(win.shape[1], best_loc[0] + ix + 1 - x0), min(win.shape[0], best_loc[1] + iy + 1 - y0)
    win[my0:my1, mx0:mx1] = -1.0
    return float(win.max())


def is_contaminated(res, best_loc, tw, th, mx):
    """Deterministic close-crowding gate: SOLID geometry whose near-field
    carries a second strong body support must not be learned or recorded.
    Weak matches are 'lost', not crowded — their band is just noise."""
    return mx >= CONTAM_MIN and near_rival(res, best_loc, tw, th) >= mx * CONTAM_RATIO
