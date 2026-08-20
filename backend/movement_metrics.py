"""movement_metrics.py — measured movement stats derived from the optical
player track (player_tracking.py). Pure math on ground-truth data — no AI."""

from __future__ import annotations

BURST_MIN_PTS = 3     # ≥3 consecutive fast samples (~0.24 s) = one burst
MAX_TRAIL = 90
NEAR_TAP_S = 2.0      # a moment ≤2 s from a user tap counts as identity-anchored


def fmt_mmss(t: float) -> str:
    m, s = divmod(int(round(t)), 60)
    return f"{m:02d}:{s:02d}"


_fmt_mmss = fmt_mmss  # back-compat alias


def compute_movement_map(track: dict | None, tap_times: list[float] | None = None,
                         motion: dict | None = None) -> dict | None:
    """Return {tracked_seconds, segments, passages, track_start_*, points, bursts,
    top_speed_*, intensity, fast_candidates, fast_near_tap, trail} or None when
    too little data. tap_times = absolute video seconds of the user's taps
    (incl. time offset) — used for identity-safe fastest-moment candidates.
    motion — FIX06 camera-compensated residual samples: when provided, all
    speed-derived fields (top speed, bursts, intensity, fast candidates)
    consume the compensated series instead of raw screen displacement."""
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
    if motion is not None:
        # FIX06: camera pan/tilt/zoom removed — only the player residual
        # (normalized to the actual frame geometry) counts as movement.
        speeds = [(float(s["t1"]), float(s["v_norm"]))
                  for s in (motion.get("samples") or []) if s.get("ok")]
    else:
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
    # Fastest-moment candidates (top-5 by speed) + best sample near a user tap.
    ranked = sorted(sm, key=lambda s: s[1], reverse=True)
    fast_candidates = [{"t": round(t, 2), "v": round(v, 4)} for t, v in ranked[:5]]
    fast_near_tap = None
    if tap_times:
        near = [(t, v) for t, v in sm if any(abs(t - tt) <= NEAR_TAP_S for tt in tap_times)]
        if near:
            bt, bv = max(near, key=lambda s: s[1])
            fast_near_tap = {"t": round(bt, 2), "v": round(bv, 4)}
    trail = centers
    if len(trail) > MAX_TRAIL:
        keep = {i for i, p in enumerate(trail) if p["tap"]}
        n_fill = max(1, MAX_TRAIL - len(keep))
        step = len(trail) / n_fill
        keep |= {min(len(trail) - 1, int(i * step)) for i in range(n_fill)}
        trail = [trail[i] for i in sorted(keep)]
    tracked = sum(b - a for a, b in segs)
    track_start_s = segs[0][0] if segs else None
    return {
        "tracked_seconds": round(tracked, 1),
        "segments": len(segs),
        "passages": [[fmt_mmss(a), fmt_mmss(b)] for a, b in segs[:6]],
        "track_start_s": round(track_start_s, 1) if track_start_s is not None else None,
        "track_start_t": fmt_mmss(track_start_s) if track_start_s is not None else None,
        "points": len(pts),
        "bursts": bursts,
        "top_speed_t": fmt_mmss(vmax_t),
        "top_video_s": round(vmax_t, 1),
        "top_speed_idx": min(100, round(vmax * 65)),
        "top_after_start": round(vmax_t - track_start_s, 1) if track_start_s is not None else None,
        "intensity": min(100, round(median_v * 180)),
        "fast_candidates": fast_candidates,
        "fast_near_tap": fast_near_tap,
        "trail": trail,
    }
