"""Convert independently normalised x/y coordinates to a common image metric.

Body-relative distances use frame-height units: dx is multiplied by W/H.
Dimensions come from the decoded image, not report metadata. Legacy evidence
without dimensions retains its old metric; malformed or mixed native metadata
cannot supply geometry proof.
"""
from __future__ import annotations

import math


def horizontal_scale(frame):
    if not isinstance(frame, dict) or "frame_dimensions" not in frame:
        return 1.0
    dims = frame["frame_dimensions"]
    if not isinstance(dims, dict) or dims.get("source") != "DECODED_NATIVE_PIXELS":
        return None
    width, height = dims.get("width"), dims.get("height")
    if any(not isinstance(v, int) or isinstance(v, bool) or v <= 0 for v in (width, height)):
        return None
    try:
        scale = width / height
    except (OverflowError, ZeroDivisionError):
        return None
    return scale if math.isfinite(scale) and scale > 0 else None


def compatible_scale(*frames):
    if not frames or any(not isinstance(f, dict) for f in frames):
        return None
    native = ["frame_dimensions" in f for f in frames]
    if any(native) and not all(native):
        return None
    scales = [horizontal_scale(f) for f in frames]
    if any(s is None for s in scales):
        return None
    if any(not math.isclose(s, scales[0], rel_tol=1e-9) for s in scales[1:]):
        return None
    return scales[0]
