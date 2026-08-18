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
SCALE_SEED_MIN = 0.55     # cumulative scale bounds vs the ORIGINAL tap bbox
SCALE_SEED_MAX = 1.9
AMBIG_RATIO = 0.8         # distinct second peak this close to best = ambiguous
AMBIG_DIST_FRAC = 0.6     # peaks farther apart than this × template dim = distinct
JUMP_BASE_FRAC = 0.5      # teleport allowance = bbox × (base + rate × dt)
JUMP_RATE_FRAC = 2.0


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
