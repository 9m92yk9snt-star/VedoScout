"""speed_metrics.py — deterministic pace estimates from optical-tracking data.

Speeds are derived purely from the tracked bounding boxes: pixel displacement
is converted to metres using the player's own box height as the local scale
reference (age-typical body height). Honest by design: metrics are labelled
as estimates, jitter above a physical ceiling is discarded, and when there is
too little tracked data we return None instead of fabricating numbers.
"""

from __future__ import annotations

import statistics

ASPECT = 16.0 / 9.0
MAX_KMH = 34.0            # physical ceiling — anything above is tracking jitter
MIN_POINTS = 40
MIN_TRACKED_S = 4.0
MOVING_KMH = 4.0

AGE_HEIGHT_M = {
    5: 1.12, 6: 1.18, 7: 1.24, 8: 1.30, 9: 1.36, 10: 1.41, 11: 1.47,
    12: 1.53, 13: 1.60, 14: 1.66, 15: 1.71, 16: 1.74, 17: 1.76, 18: 1.78,
}


def _sprint_threshold(age) -> float:
    try:
        a = int(age)
    except (TypeError, ValueError):
        return 17.0
    if a <= 9:
        return 14.0
    if a <= 12:
        return 16.0
    if a <= 15:
        return 18.0
    return 20.0


def _height_for_age(age) -> float:
    try:
        a = max(5, min(18, int(age)))
        return AGE_HEIGHT_M[a]
    except (TypeError, ValueError):
        return 1.60


def _rolling_median(vals: list[float], i: int, half: int = 4) -> float:
    lo, hi = max(0, i - half), min(len(vals), i + half + 1)
    return statistics.median(vals[lo:hi])


def compute_speed_metrics(track: dict, age, trusted_windows: list[float] | None = None) -> dict | None:
    """Returns pace estimates or None when the track is too thin to be honest.
    trusted_windows — absolute video seconds of the user's taps. When given, the
    headline top speed is the fastest smoothed moment within ±2 s of a tap
    (identity-anchored) instead of the global percentile moment."""
    pts = (track or {}).get("points") or []
    segs = (track or {}).get("segments") or []
    tracked_s = round(sum(b - a for a, b in segs), 1)
    if len(pts) < MIN_POINTS or tracked_s < MIN_TRACKED_S:
        return None

    height_m = _height_for_age(age)
    heights = [max(1e-4, float(p["h"])) for p in pts]

    samples = []  # (t, kmh, dist_m)
    for i in range(1, len(pts)):
        p0, p1 = pts[i - 1], pts[i]
        dt = float(p1["t"]) - float(p0["t"])
        if dt <= 0 or dt > 0.35:  # different segment / gap
            continue
        h_local = _rolling_median(heights, i)
        m_per_norm = height_m / h_local  # metres per normalised-y unit
        cx0, cy0 = p0["x"] + p0["w"] / 2, p0["y"] + p0["h"] / 2
        cx1, cy1 = p1["x"] + p1["w"] / 2, p1["y"] + p1["h"] / 2
        dist_m = (((cx1 - cx0) * ASPECT) ** 2 + (cy1 - cy0) ** 2) ** 0.5 * m_per_norm
        kmh = dist_m / dt * 3.6
        if kmh > MAX_KMH:
            continue
        samples.append((float(p1["t"]), kmh, dist_m))

    if len(samples) < 20:
        return None

    # median-smooth speeds (window 5)
    speeds = [s[1] for s in samples]
    smooth = [statistics.median(speeds[max(0, i - 2):i + 3]) for i in range(len(speeds))]

    ordered = sorted(smooth)
    top_kmh = ordered[min(len(ordered) - 1, int(len(ordered) * 0.97))]
    top_t = samples[smooth.index(max(smooth))][0]
    top_trust = None

    # Identity-anchored headline: fastest smoothed moment within ±2 s of a tap.
    if trusted_windows:
        anchored = [
            (sp, samples[i][0])
            for i, sp in enumerate(smooth)
            if any(abs(samples[i][0] - tt) <= 2.0 for tt in trusted_windows)
        ]
        if anchored:
            top_kmh, top_t = max(anchored)
            top_trust = "tap"

    thr = _sprint_threshold(age)
    sprints = 0
    run_start = None
    for (t, _kmh, _d), sp in zip(samples, smooth):
        if sp >= thr:
            if run_start is None:
                run_start = t
        else:
            if run_start is not None and t - run_start >= 0.8:
                sprints += 1
            run_start = None
    if run_start is not None and samples[-1][0] - run_start >= 0.8:
        sprints += 1

    distance_m = sum(d for _t, _k, d in samples)
    moving = [sp for sp in smooth if sp >= MOVING_KMH]

    return {
        "top_speed_kmh": round(top_kmh, 1),
        "top_speed_t": round(top_t, 1),
        "top_trust": top_trust,
        "sprint_count": sprints,
        "sprint_threshold_kmh": thr,
        "distance_tracked_m": round(distance_m),
        "tracked_seconds": tracked_s,
        "avg_moving_kmh": round(statistics.median(moving), 1) if moving else None,
        "assumed_height_m": height_m,
        "method": "optical-estimate",
    }
