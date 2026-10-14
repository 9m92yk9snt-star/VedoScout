"""Native jersey reader pixels bounded by the measured body, at its full width."""
from __future__ import annotations

import math

TORSO_TOP = .18
TORSO_BOTTOM = .64


def torso_bounds(frame, box):
    if frame is None or not hasattr(frame, "shape") or len(frame.shape) < 2 or not isinstance(box, dict):
        return None
    try:
        if any(isinstance(box[k], bool) for k in ("x", "y", "w", "h")):
            return None
        x, y, w, h = (float(box[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if (not all(math.isfinite(v) for v in (x, y, w, h)) or not -.05 <= x <= 1.05
            or not -.05 <= y <= 1.05 or not 0 < w <= 1.1 or not 0 < h <= 1.1):
        return None
    height, width = frame.shape[:2]
    # Inward rounding includes only pixels inside the measured rectangle.
    # A turned player's first digit can lie outside the old central 76% crop.
    x0, x1 = max(0, math.ceil(x*width)), min(width, math.floor((x+w)*width))
    y0 = max(0, math.ceil((y+TORSO_TOP*h)*height))
    y1 = min(height, math.floor((y+TORSO_BOTTOM*h)*height))
    return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None


def native_torso_crop(frame, box):
    bounds = torso_bounds(frame, box)
    if bounds is None:
        return None
    x0, y0, x1, y1 = bounds
    if x1-x0 < 8 or y1-y0 < 12:
        return None
    return frame[y0:y1, x0:x1].copy()
