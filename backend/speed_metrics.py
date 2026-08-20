"""speed_metrics.py — deterministic pace estimates from optical-tracking data.

FIX06: physical speed/distance is derived ONLY from camera-compensated player
residual samples (motion_compensation.py) — never from raw screen displacement.
Pixel residual is converted to metres using the player's robust local bbox
height (age-typical body height as the metre reference) on the ACTUAL frame
geometry — no aspect-ratio assumption. Honest by design: this remains a
camera-compensated optical estimate (not GPS/pitch-calibrated), unsafe camera
intervals are skipped rather than approximated, and when too little of the
track is physically measurable we return None instead of fabricating numbers.
"""

from __future__ import annotations

import statistics

MAX_KMH = 34.0            # FINAL physical outlier ceiling — not a substitute
                          # for camera compensation
MIN_POINTS = 40
MIN_TRACKED_S = 4.0
MOVING_KMH = 4.0
MAX_INTERVAL_S = 0.35     # a missing/rejected interval breaks continuity
MIN_SAMPLES = 20          # conservative low-coverage gates: below these,
MIN_METRIC_S = 3.0        # no physical claim is published
MIN_COVERAGE = 0.4

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


def compute_speed_metrics(track: dict, age, trusted_windows: list[float] | None = None,
                          motion: dict | None = None) -> dict | None:
    """Returns pace estimates or None when the track is too thin — or too
    little of it is camera-compensated — to be honest.
    trusted_windows — absolute video seconds of the user's taps: the headline
    top speed is then the fastest smoothed compensated sample within ±2 s of a
    tap (value and time are the SAME sample).
    motion — camera-compensated residual samples from motion_compensation.
    Without them no physical metric is published (no raw fallback)."""
    pts = (track or {}).get("points") or []
    segs = (track or {}).get("segments") or []
    tracked_s = round(sum(b - a for a, b in segs), 1)
    if len(pts) < MIN_POINTS or tracked_s < MIN_TRACKED_S:
        return None
    if not motion or not motion.get("samples"):
        return None

    height_m = _height_for_age(age)
    # contiguous SAFE runs — every rejected interval (camera fail, missing
    # decode, outlier, gap, invalid dt) BREAKS continuity; nothing is smoothed
    # or sustained across a break (C02)
    runs = []           # list of runs; each run = [(t1, kmh, dist_m), ...]
    cur = []
    skipped = 0
    metric_s = 0.0
    eligible_s = 0.0    # duration of ALL eligible original intervals
    prev_t1 = None
    for s in motion["samples"]:
        eligible_s += float(s["dt"])
        contiguous = prev_t1 is not None and abs(float(s["t0"]) - prev_t1) <= 1e-9
        prev_t1 = float(s["t1"])
        if not s.get("ok"):
            skipped += 1
            if cur:
                runs.append(cur)
                cur = []
            continue
        dist_m = (s["rx"] ** 2 + s["ry"] ** 2) ** 0.5 / max(1e-6, s["h_px"]) * height_m
        kmh = dist_m / s["dt"] * 3.6
        if kmh > MAX_KMH:  # final outlier protection only — also breaks continuity
            skipped += 1
            if cur:
                runs.append(cur)
                cur = []
            continue
        if cur and not contiguous:
            runs.append(cur)
            cur = []
        cur.append((float(s["t1"]), kmh, dist_m))
        metric_s += float(s["dt"])
    if cur:
        runs.append(cur)

    used = sum(len(r) for r in runs)
    # honest duration-based coverage: measurable seconds over ALL eligible
    # interval seconds (decode/camera failures included, never extrapolated)
    coverage = metric_s / eligible_s if eligible_s > 0 else 0.0
    if used < MIN_SAMPLES or metric_s < MIN_METRIC_S or coverage < MIN_COVERAGE:
        return None  # low coverage → no physical claim

    # median-smooth speeds (window 5) WITHIN each safe run only
    smooth_runs = []
    for r in runs:
        sp = [x[1] for x in r]
        smooth_runs.append([statistics.median(sp[max(0, i - 2):i + 3])
                            for i in range(len(sp))])
    samples = [x for r in runs for x in r]
    smooth = [v for sr in smooth_runs for v in sr]

    # robust top: the 97th-percentile SAMPLE — value and time from the SAME
    # accepted compensated sample
    order = sorted(range(len(smooth)), key=lambda i: smooth[i])
    i_top = order[min(len(order) - 1, int(len(order) * 0.97))]
    top_kmh, top_t = smooth[i_top], samples[i_top][0]
    top_trust = None

    # Identity-anchored headline: fastest smoothed moment within ±2 s of a tap
    # (max() keeps value and time paired — one sample).
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
    for r, sr in zip(runs, smooth_runs):
        # sustained duration is only valid WITHIN a safe run — a rejected
        # interval breaks the sprint, it is never silently filled
        run_start = None
        for (t, _kmh, _d), sp in zip(r, sr):
            if sp >= thr:
                if run_start is None:
                    run_start = t
            else:
                if run_start is not None and t - run_start >= 0.8:
                    sprints += 1
                run_start = None
        if run_start is not None and r[-1][0] - run_start >= 0.8:
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
        "camera_compensated": True,
        "metric_samples_used": used,
        "metric_samples_skipped": skipped,
        "metric_seconds": round(metric_s, 1),
        "metric_coverage_ratio": round(coverage, 2),
        "scale_source": "age-height-local-bbox",
        "method": "camera-compensated-optical-estimate",
    }
