"""FIX10A3 — dense football trajectory reconstruction.

Consumes every ball candidate from FIX10A2 dense frames and reconstructs a
bounded set of physically plausible trajectories.  Detection confidence is
only one signal: temporal continuity, size consistency and bounded acceleration
must also agree.  Missing/ambiguous frames remain explicit and never become
contact/event authority.
"""
from __future__ import annotations

import math
from copy import deepcopy

VERSION = 1
MAX_HYPOTHESES = 3
SCORE_MARGIN = 0.12
MAX_SPEED_NORM_S = 4.0
BASE_JUMP_NORM = 0.025
MAX_ACCEL_NORM_S2 = 36.0
SHORT_GAP_MS = 180
HYPOTHESIS_DECAY = 0.88


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _valid_box(box) -> bool:
    if not isinstance(box, dict):
        return False
    try:
        x, y, w, h = (float(box[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return False
    return -0.05 <= x <= 1.05 and -0.05 <= y <= 1.05 and 0 < w <= 0.25 and 0 < h <= 0.25


def _box(box):
    return {k: float(box[k]) for k in ("x", "y", "w", "h")}


def _center(box):
    return float(box["x"]) + float(box["w"]) / 2.0, float(box["y"]) + float(box["h"]) / 2.0


def _area_scale(box):
    return math.sqrt(max(1e-12, float(box["w"]) * float(box["h"])))


def _predict_box(hyp: dict, media_ms: int) -> dict:
    last = hyp["box"]
    dt = max(0.0, (int(media_ms) - int(hyp["media_ms"])) / 1000.0)
    vx, vy = hyp.get("velocity") or (0.0, 0.0)
    return {
        "x": float(last["x"]) + float(vx) * dt,
        "y": float(last["y"]) + float(vy) * dt,
        "w": float(last["w"]),
        "h": float(last["h"]),
    }


def _candidate_from_prior(candidate: dict, prior: dict | None, media_ms: int) -> dict | None:
    if not _valid_box(candidate.get("box")):
        return None
    box = _box(candidate["box"])
    conf = max(0.0, min(1.0, float(candidate.get("confidence") or 0.0)))
    if prior is None:
        return {
            "box": box, "confidence": conf, "score": 0.50 * conf,
            "velocity": None, "acceleration": None,
            "last_measured_ms": int(media_ms),
            "provenance": "LOCAL_DENSE_DETECTOR",
        }
    dt = (int(media_ms) - int(prior["media_ms"])) / 1000.0
    if dt <= 0:
        return None
    pred = _predict_box(prior, media_ms)
    pcx, pcy = _center(pred); cx, cy = _center(box)
    dist = math.hypot(cx - pcx, cy - pcy)
    max_dist = BASE_JUMP_NORM + MAX_SPEED_NORM_S * dt
    if dist > max_dist:
        return None
    continuity = max(0.0, 1.0 - dist / max(max_dist, 1e-9))
    prev_scale, cur_scale = _area_scale(prior["box"]), _area_scale(box)
    scale_ratio = min(prev_scale, cur_scale) / max(prev_scale, cur_scale, 1e-9)
    if scale_ratio < 0.35:
        return None
    px, py = _center(prior["box"])
    velocity = ((cx - px) / dt, (cy - py) / dt)
    accel = None
    acceleration_score = 1.0
    if prior.get("velocity") is not None:
        pvx, pvy = prior["velocity"]
        accel = ((velocity[0] - pvx) / dt, (velocity[1] - pvy) / dt)
        accel_mag = math.hypot(accel[0], accel[1])
        if accel_mag > MAX_ACCEL_NORM_S2 * 1.75:
            return None
        acceleration_score = max(0.0, 1.0 - accel_mag / MAX_ACCEL_NORM_S2)
    score = 0.50 * conf + 0.27 * continuity + 0.13 * scale_ratio + 0.10 * acceleration_score
    return {
        "box": box,
        "confidence": conf,
        "score": score,
        "velocity": velocity,
        "acceleration": accel,
        "last_measured_ms": int(media_ms),
        "provenance": "LOCAL_DENSE_DETECTOR",
    }


def _rank_candidates(candidates, hypotheses, media_ms):
    ranked = []
    for ci, candidate in enumerate(candidates):
        if not isinstance(candidate, dict) or not _valid_box(candidate.get("box")):
            continue
        options = []
        for hi, prior in enumerate(hypotheses):
            row = _candidate_from_prior(candidate, prior, media_ms)
            if row is not None:
                row["prior_hypothesis"] = hi
                options.append(row)
        bootstrap = _candidate_from_prior(candidate, None, media_ms)
        if bootstrap is not None:
            bootstrap["prior_hypothesis"] = None
            options.append(bootstrap)
        if not options:
            continue
        best = max(options, key=lambda r: r["score"])
        best["candidate_index"] = ci
        ranked.append(best)
    ranked.sort(reverse=True, key=lambda r: r["score"])
    return ranked


def _hypothesis_from_ranked(row: dict, media_ms: int) -> dict:
    return {
        "media_ms": int(media_ms),
        "last_measured_ms": int(row.get("last_measured_ms") or media_ms),
        "box": _box(row["box"]),
        "velocity": tuple(row["velocity"]) if row.get("velocity") is not None else None,
        "score": float(row.get("score") or 0.0),
        "confidence": float(row.get("confidence") or 0.0),
    }


def trajectory_features(points) -> list[dict]:
    """Attach selected-trajectory velocity/acceleration from actual media dt."""
    rows = [deepcopy(p) for p in (points or []) if isinstance(p, dict)]
    prev = None
    prev_velocity = None
    for row in rows:
        if row.get("cut_barrier") is True or not _valid_box(row.get("box")):
            row["velocity"] = None
            row["acceleration"] = None
            row["direction"] = None
            prev = None
            prev_velocity = None
            continue
        if prev is None:
            row["velocity"] = None
            row["acceleration"] = None
            row["direction"] = None
            prev = row
            continue
        dt = (int(row["media_ms"]) - int(prev["media_ms"])) / 1000.0
        if dt <= 0:
            row["velocity"] = None
            row["acceleration"] = None
            row["direction"] = None
            prev = row
            prev_velocity = None
            continue
        x0, y0 = _center(prev["box"]); x1, y1 = _center(row["box"])
        velocity = {"x": (x1 - x0) / dt, "y": (y1 - y0) / dt}
        speed = math.hypot(velocity["x"], velocity["y"])
        row["velocity"] = velocity
        row["direction"] = (
            {"x": velocity["x"] / speed, "y": velocity["y"] / speed}
            if speed > 1e-9 else {"x": 0.0, "y": 0.0}
        )
        if prev_velocity is not None:
            row["acceleration"] = {
                "x": (velocity["x"] - prev_velocity["x"]) / dt,
                "y": (velocity["y"] - prev_velocity["y"]) / dt,
            }
        else:
            row["acceleration"] = None
        prev_velocity = velocity
        prev = row
    return rows


def reconstruct_ball_trajectory(dense_frames) -> list[dict]:
    """Reconstruct one fail-closed ball trajectory with bounded alternatives."""
    hypotheses = []
    rows = []
    for frame in dense_frames or []:
        if not isinstance(frame, dict) or not _num(frame.get("media_ms")):
            continue
        media_ms = int(round(float(frame["media_ms"])))
        cut = frame.get("cut_barrier") is True or frame.get("cut") is True
        if cut:
            hypotheses = []
        raw_candidates = [
            deepcopy(c) for c in (frame.get("ball_candidates") or [])
            if isinstance(c, dict) and _valid_box(c.get("box"))
        ]
        ranked = _rank_candidates(raw_candidates, hypotheses, media_ms)
        used_fallback = bool(frame.get("used_fallback"))
        common = {
            "media_ms": media_ms,
            "used_fallback": used_fallback,
            "time_authority": frame.get("time_authority") or (
                "FRAME_INDEX_FPS_FALLBACK" if used_fallback else "ACTUAL_MEDIA_PTS"
            ),
            "cut_barrier": bool(cut),
        }

        if ranked:
            top = ranked[0]
            ambiguous = len(ranked) > 1 and top["score"] - ranked[1]["score"] < SCORE_MARGIN
            kept = ranked[:MAX_HYPOTHESES]
            hypotheses = [_hypothesis_from_ranked(r, media_ms) for r in kept]
            candidate_rows = [
                {
                    "box": _box(r["box"]),
                    "confidence": round(float(r["confidence"]), 4),
                    "trajectory_score": round(float(r["score"]), 4),
                    "prior_hypothesis": r.get("prior_hypothesis"),
                }
                for r in kept
            ]
            if ambiguous:
                rows.append({
                    **common,
                    "state": "AMBIGUOUS",
                    "box": None,
                    "confidence": round(float(top["confidence"]), 4),
                    "candidates": candidate_rows,
                    "proof_eligible": False,
                    "provenance": "BOUNDED_COMPETING_TRAJECTORIES",
                })
            else:
                rows.append({
                    **common,
                    "state": "MEASURED",
                    "box": _box(top["box"]),
                    "confidence": round(float(top["confidence"]), 4),
                    "candidates": candidate_rows,
                    "proof_eligible": not used_fallback,
                    "provenance": "LOCAL_DENSE_DETECTOR",
                })
            continue

        # No measured candidate.  A bounded kinematic continuation is useful
        # for search/context only, never for proof/contact authority.
        if hypotheses:
            best = max(hypotheses, key=lambda h: h.get("score", 0.0))
            age = media_ms - int(best.get("last_measured_ms") or best["media_ms"])
            if 0 < age <= SHORT_GAP_MS:
                predicted = _predict_box(best, media_ms)
                best = {
                    **best,
                    "media_ms": media_ms,
                    "box": predicted,
                    "score": float(best.get("score") or 0.0) * HYPOTHESIS_DECAY,
                    "confidence": float(best.get("confidence") or 0.0) * HYPOTHESIS_DECAY,
                }
                hypotheses = [best]
                rows.append({
                    **common,
                    "state": "PREDICTED_SHORT_GAP",
                    "box": _box(predicted),
                    "confidence": round(float(best["confidence"]), 4),
                    "candidates": [],
                    "proof_eligible": False,
                    "provenance": "KINEMATIC_SHORT_GAP",
                })
                continue
        hypotheses = []
        rows.append({
            **common,
            "state": "MISSING",
            "box": None,
            "confidence": 0.0,
            "candidates": [],
            "proof_eligible": False,
            "provenance": "NO_PHYSICAL_BALL_EVIDENCE",
        })

    return trajectory_features(rows)
