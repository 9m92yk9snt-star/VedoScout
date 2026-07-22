"""movement_metrics.py — measured movement stats derived from the optical
player track (player_tracking.py). Pure math on ground-truth data — no AI."""

from __future__ import annotations

BURST_MIN_PTS = 3     # ≥3 consecutive fast samples (~0.24 s) = one burst
MAX_TRAIL = 90


def _fmt_mmss(t: float) -> str:
    m, s = divmod(int(round(t)), 60)
    return f"{m:02d}:{s:02d}"


def compute_movement_map(track: dict | None) -> dict | None:
    """Return {tracked_seconds, segments, points, bursts, top_speed_t,
    top_speed_idx, intensity, trail:[{t,x,y,tap}]} or None when too little data."""
    pts = (track or {}).get("points") or []
    segs = (track or {}).get("segments") or []
    if len(pts) < 6:
        return None
    centers = [
        {
            "t": p["t"],
            "x": round(p["x"] + p["w"] / 2, 4),
            "y": round(p["y"] + p["h"] / 2, 4),
            "tap": p.get("conf", 0) >= 0.999,
        }
        for p in pts
    ]
    speeds = []
    for a, b in zip(centers, centers[1:]):
        dt = b["t"] - a["t"]
        if 0.01 < dt <= 0.35:
            v = ((b["x"] - a["x"]) ** 2 + (b["y"] - a["y"]) ** 2) ** 0.5 / dt
            speeds.append((b["t"], v))
    if not speeds:
        return None
    sm = []
    for i in range(len(speeds)):
        lo, hi = max(0, i - 1), min(len(speeds), i + 2)
        sm.append((speeds[i][0], sum(v for _, v in speeds[lo:hi]) / (hi - lo)))
    vmax_t, vmax = max(sm, key=lambda s: s[1])
    svals = sorted(v for _, v in sm)
    median_v = svals[len(svals) // 2]
    thr = max(0.4, 1.7 * median_v)
    bursts, run = 0, 0
    for _, v in sm:
        if v > thr:
            run += 1
        else:
            if run >= BURST_MIN_PTS:
                bursts += 1
            run = 0
    if run >= BURST_MIN_PTS:
        bursts += 1
    trail = centers
    if len(trail) > MAX_TRAIL:
        keep = {i for i, p in enumerate(trail) if p["tap"]}
        n_fill = max(1, MAX_TRAIL - len(keep))
        step = len(trail) / n_fill
        keep |= {min(len(trail) - 1, int(i * step)) for i in range(n_fill)}
        trail = [trail[i] for i in sorted(keep)]
    tracked = sum(b - a for a, b in segs)
    return {
        "tracked_seconds": round(tracked, 1),
        "segments": len(segs),
        "points": len(pts),
        "bursts": bursts,
        "top_speed_t": _fmt_mmss(vmax_t),
        "top_speed_idx": min(100, round(vmax * 65)),
        "intensity": min(100, round(median_v * 180)),
        "trail": trail,
    }
