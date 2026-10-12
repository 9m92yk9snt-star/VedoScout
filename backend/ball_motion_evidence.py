"""Measured ball movement relative to the decoded background camera transform.

Nearness and a change of nearest player cannot show that a stationary ball was
touched. New native frames carry the actual background affine transform, with
its source/destination PTS and pixel units. Missing, malformed or interrupted
camera evidence cannot certify independent ball movement. Legacy traces without
this contract retain their historical interpretation.
"""
from __future__ import annotations

import math
import numpy as np

import frame_geometry
import motion_compensation as camera

MIN_RESIDUAL_PIXELS = 2.0
MIN_RESIDUAL_BALL_RADII = 1.0


def _native(frame):
    if (not isinstance(frame, dict) or frame_geometry.horizontal_scale(frame) is None
            or "frame_dimensions" not in frame or frame.get("used_fallback") is True
            or frame.get("time_authority") != "ACTUAL_MEDIA_PTS"):
        return False
    ms = frame.get("media_ms")
    return isinstance(ms, int) and not isinstance(ms, bool)


def _matrix(row, previous):
    evidence = row.get("camera_motion")
    if (not isinstance(evidence, dict) or evidence.get("source") != "NATIVE_BACKGROUND_AFFINE"
            or evidence.get("units") != "DECODED_PIXELS"
            or any(type(evidence.get(k)) is not int for k in ("from_media_ms", "to_media_ms"))
            or evidence.get("from_media_ms") != previous.get("media_ms")
            or evidence.get("to_media_ms") != row.get("media_ms")
            or row.get("camera_state") != "AFFINE_VERIFIED"):
        return None
    try:
        matrix = np.asarray(evidence.get("matrix"), dtype=float)
    except (TypeError, ValueError, OverflowError):
        return None
    if matrix.shape != (2, 3) or not np.isfinite(matrix).all():
        return None
    linear = matrix[:, :2]
    dims = row["frame_dimensions"]
    estimation = evidence.get("estimation_frame_dimensions")
    if estimation is not None:
        if not isinstance(estimation, dict) or any(type(estimation.get(k)) is not int for k in ("width","height")):
            return None
        native_size = (dims["width"],dims["height"])
        sampled_width = min(dims["width"],camera.PROC_W)
        sampled_size = (sampled_width,round(dims["height"]*sampled_width/dims["width"]))
        if (estimation["width"],estimation["height"]) not in (native_size,sampled_size):
            return None
        # The native matrix is S^-1 M S. Reconstruct the actual estimation
        # view before validating M: portrait-height rounding makes the native
        # linear part slightly anisotropic despite a valid similarity fit.
        scale_x,scale_y = estimation["width"]/dims["width"],estimation["height"]/dims["height"]
        linear = np.diag([scale_x,scale_y]) @ linear @ np.diag([1/scale_x,1/scale_y])
    # Reuse the producer's safe similarity-transform limits, including the
    # absence of shear/reflection. A claimed AFFINE_VERIFIED label is insufficient.
    scale = math.hypot(linear[0, 0], linear[1, 0])
    if (not camera.SCALE_MIN <= scale <= camera.SCALE_MAX
            or not np.allclose(linear.T @ linear, np.eye(2) * scale**2, rtol=1e-6, atol=1e-9)
            or np.linalg.det(linear) <= 0
            or abs(math.degrees(math.atan2(linear[1, 0], linear[0, 0]))) > camera.MAX_ROT_DEG):
        return None
    if math.hypot(*matrix[:, 2]) > camera.MAX_SHIFT_FRAC * math.hypot(dims["width"], dims["height"]):
        return None
    return np.vstack((matrix, [0., 0., 1.]))


def _transform_between(frames, first_ms, last_ms):
    selected = [f for f in frames if first_ms <= f["media_ms"] <= last_ms]
    if (not selected or selected[0]["media_ms"] != first_ms or selected[-1]["media_ms"] != last_ms
            or any(not _native(f) for f in selected)):
        return None
    dimensions = selected[0]["frame_dimensions"]
    scene = selected[0].get("scene_id")
    matrix = np.eye(3)
    for previous, row in zip(selected, selected[1:]):
        if (row["media_ms"] <= previous["media_ms"]
                or row["frame_dimensions"] != dimensions
                or row.get("scene_id") != scene
                or row.get("cut_barrier") is True or row.get("cut") is True):
            return None
        step = _matrix(row, previous)
        if step is None:
            return None
        matrix = step @ matrix
    return matrix


def relative_ball_motion(frames, before, current, after, *, outgoing_start=None):
    """Return legacy/unresolved/measured motion; never touch or identity proof."""
    rows = sorted((f for f in frames or [] if isinstance(f, dict)
                   and isinstance(f.get("media_ms"), int) and not isinstance(f["media_ms"], bool)),
                  key=lambda f: f["media_ms"])
    outgoing_start = current if outgoing_start is None else outgoing_start
    points = (before, current, outgoing_start, after)
    unavailable = {"status": "UNRESOLVED", "reason": "BALL_CAMERA_MOTION_UNAVAILABLE",
                   "resolved_motion": False}
    if not any("camera_motion" in f for f in rows):
        return {"status": "LEGACY", "reason": "NO_NATIVE_CAMERA_MOTION_CONTRACT"}
    if any(not isinstance(p, dict) or type(p.get("media_ms")) is not int for p in points):
        return unavailable
    low, pivot, outgoing_ms, high = (p["media_ms"] for p in points)
    if not low < pivot <= outgoing_ms < high:
        return unavailable
    interval = [f for f in rows if low <= f["media_ms"] <= high]
    prior_matrix = _transform_between(rows, low, pivot)
    following_matrix = _transform_between(rows, pivot, high)
    outgoing_matrix = _transform_between(rows, outgoing_ms, high)
    if prior_matrix is None or following_matrix is None or outgoing_matrix is None:
        return unavailable
    frame = next((f for f in interval if f["media_ms"] == pivot), None)
    if frame is None or not _native(frame):
        return unavailable
    width, height = (frame["frame_dimensions"][k] for k in ("width", "height"))
    centers, radii = [], []
    try:
        for point in points:
            b = point["box"]
            if any(isinstance(b[k], bool) for k in ("x", "y", "w", "h")):
                return unavailable
            x, y, w, h = (float(b[k]) for k in ("x", "y", "w", "h"))
            if (not all(math.isfinite(v) for v in (x, y, w, h)) or not 0 < w <= .25
                    or not 0 < h <= .25 or not -.1 <= x <= 1.1 or not -.1 <= y <= 1.1):
                return unavailable
            centers.append(np.array([(x + w/2)*width, (y + h/2)*height, 1.]))
            radii.append(min(w*width, h*height)/2)
    except (KeyError, TypeError, ValueError, OverflowError):
        return unavailable
    residual_before = (centers[1] - prior_matrix @ centers[0])[:2]
    # Both velocities are expressed in the current frame's pixel axes. Remove
    # the following camera's rotation/zoom as well as its translation.
    residual_after = np.linalg.inv(following_matrix)[:2, :2] @ (centers[3] - outgoing_matrix @ centers[2])[:2]
    travel = max(float(np.linalg.norm(residual_before)), float(np.linalg.norm(residual_after)))
    minimum = max(MIN_RESIDUAL_PIXELS, MIN_RESIDUAL_BALL_RADII * max(radii))
    return {"status": "MEASURED", "reason": "BALL_MOVES_RELATIVE_TO_BACKGROUND" if travel > minimum
            else "BALL_MOVEMENT_BELOW_NATIVE_RESOLUTION",
            "resolved_motion": travel > minimum,
            "before_velocity": (residual_before / height / ((pivot-low)/1000)).tolist(),
            "after_velocity": (residual_after / height / ((high-outgoing_ms)/1000)).tolist(),
            "maximum_residual_px": round(travel, 6), "minimum_residual_px": round(minimum, 6),
            "source": "NATIVE_BACKGROUND_AFFINE", "time_authority": "ACTUAL_MEDIA_PTS"}


def relative_ball_segment(frames, first, last):
    """One measured/support path segment; separation from a player is independent."""
    rows = sorted((f for f in frames or [] if isinstance(f, dict) and type(f.get("media_ms")) is int),
                  key=lambda f: f["media_ms"])
    if not any("camera_motion" in f for f in rows):
        return {"status": "LEGACY", "reason": "NO_NATIVE_CAMERA_MOTION_CONTRACT"}
    unavailable = {"status": "UNRESOLVED", "reason": "BALL_CAMERA_MOTION_UNAVAILABLE", "resolved_motion": False}
    if (not isinstance(first, dict) or not isinstance(last, dict)
            or type(first.get("media_ms")) is not int or type(last.get("media_ms")) is not int
            or first["media_ms"] >= last["media_ms"]):
        return unavailable
    matrix = _transform_between(rows, first["media_ms"], last["media_ms"])
    if matrix is None:
        return unavailable
    frame = next(f for f in rows if f["media_ms"] == first["media_ms"])
    width, height = (frame["frame_dimensions"][k] for k in ("width", "height"))
    centers, radii = [], []
    try:
        for point in (first, last):
            b = point["box"]
            if any(isinstance(b[k], bool) for k in ("x","y","w","h")):
                return unavailable
            x,y,w,h = (float(b[k]) for k in ("x","y","w","h"))
            if (not all(math.isfinite(v) for v in (x,y,w,h)) or not 0 < w <= .25 or not 0 < h <= .25
                    or not -.1 <= x <= 1.1 or not -.1 <= y <= 1.1):
                return unavailable
            centers.append(np.array([(x+w/2)*width, (y+h/2)*height, 1.]))
            radii.append(min(w*width,h*height)/2)
    except (KeyError, TypeError, ValueError, OverflowError):
        return unavailable
    residual = (np.linalg.inv(matrix) @ centers[1] - centers[0])[:2]
    travel = float(np.linalg.norm(residual))
    minimum = max(MIN_RESIDUAL_PIXELS,MIN_RESIDUAL_BALL_RADII*max(radii))
    dt = (last["media_ms"]-first["media_ms"])/1000
    return {"status":"MEASURED", "reason":"BALL_MOVES_RELATIVE_TO_BACKGROUND" if travel > minimum
            else "BALL_MOVEMENT_BELOW_NATIVE_RESOLUTION", "resolved_motion":travel > minimum,
            "velocity":(residual/height/dt).tolist(), "displacement_h":travel/height,
            "maximum_residual_px":round(travel,6), "minimum_residual_px":round(minimum,6),
            "source":"NATIVE_BACKGROUND_AFFINE", "time_authority":"ACTUAL_MEDIA_PTS"}
