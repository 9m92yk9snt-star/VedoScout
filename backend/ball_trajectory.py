"""FIX10A3 — dense football trajectory reconstruction.

Consumes every ball candidate from FIX10A2 dense frames and reconstructs a
bounded set of physically plausible trajectories.  Detection confidence is
only one signal: temporal continuity, size consistency and bounded acceleration
must also agree.  Missing/ambiguous frames remain explicit and never become
contact/event authority.
"""
from __future__ import annotations

import math
import hashlib
from copy import deepcopy
import numpy as np

import frame_geometry
import ball_motion_evidence

VERSION = 1
MAX_HYPOTHESES = 3
MAX_SEARCH_HYPOTHESES = 6
SCORE_MARGIN = 0.12
MAX_SPEED_NORM_S = 4.0
BASE_JUMP_NORM = 0.025
MAX_ACCEL_NORM_S2 = 36.0
SHORT_GAP_MS = 180
DORMANT_REACQUIRE_MS = 450
DORMANT_MAX_RESIDUAL_NORM = 0.18
DORMANT_PLAYER_SUPPORT_H = 0.32
DORMANT_PLAYER_SUPPORTED_SCALE_MIN = 0.25
HYPOTHESIS_DECAY = 0.88
RELEASE_REACQUIRE_MAX_JUMP_NORM = 0.25
RELEASE_REACQUIRE_MIN_CONFIDENCE = 0.04
RELEASE_REACQUIRE_CONFIRM_MAX_GAP_MS = 80
RELEASE_MAX_MEASURED_GAP_MS = 80
RELEASE_MIN_MOTION_SUPPORT = 0.50
CONTACT_RELEASE_MAX_MS = 300


def _num(value) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


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
    # Predict from the last *measured* observation, not from the last synthetic
    # predicted frame.  Otherwise each missing frame resets dt and makes a
    # legitimate re-acquisition look like an impossible teleport.
    last = hyp.get("last_measured_box") or hyp["box"]
    base_ms = int(hyp.get("last_measured_ms") if _num(hyp.get("last_measured_ms")) else hyp["media_ms"])
    dt = max(0.0, (int(media_ms) - base_ms) / 1000.0)
    vx, vy = hyp.get("velocity") or (0.0, 0.0)
    return {
        "x": float(last["x"]) + float(vx) * dt,
        "y": float(last["y"]) + float(vy) * dt,
        "w": float(last["w"]),
        "h": float(last["h"]),
    }


def _nearest_player_foot_h(candidate_box: dict, players, x_scale=1.0) -> float | None:
    """Supporting-only geometry for trajectory re-acquisition.

    This signal may help A3 decide whether a discontinuous detector proposal is
    physically plausible near a player's lower body.  It is never touch/event
    authority; A4 still independently verifies actual contact.
    """
    if x_scale is None or not _valid_box(candidate_box):
        return None
    bx, by = _center(candidate_box)
    best = None
    for player in players or []:
        if not isinstance(player, dict) or not _valid_box(player.get("box")):
            continue
        if str(player.get("association_state") or "") == "HYPOTHESES":
            continue
        pb = player["box"]
        fx = float(pb["x"]) + float(pb["w"]) / 2.0
        fy = float(pb["y"]) + float(pb["h"])
        dist_h = math.hypot((bx - fx) * x_scale, by - fy) / max(float(pb["h"]), 1e-6)
        if best is None or dist_h < best:
            best = dist_h
    return best


def _candidate_from_prior(candidate: dict, prior: dict | None, media_ms: int,
                          *, geometry=None) -> dict | None:
    if (not _valid_box(candidate.get("box"))
            or candidate.get("proof_eligible") is False or candidate.get("used_fallback") is True
            or candidate.get("state") not in {None,"MEASURED","MEASURED_REACQUISITION"}
            or candidate.get("time_authority") not in {None,"ACTUAL_MEDIA_PTS"}):
        return None
    box = _box(candidate["box"])
    confidence = candidate.get("confidence", 0.0)
    if not _num(confidence):
        return None
    conf = max(0.0, min(1.0, float(confidence)))
    if prior is None:
        return {
            "box": box, "confidence": conf, "score": 0.50 * conf,
            "velocity": None, "acceleration": None,
            "last_measured_ms": int(media_ms),
            "provenance": "LOCAL_DENSE_DETECTOR",
        }
    last_measured_ms = int(
        prior.get("last_measured_ms")
        if _num(prior.get("last_measured_ms")) else prior["media_ms"]
    )
    dt = (int(media_ms) - last_measured_ms) / 1000.0
    if dt <= 0:
        return None
    # Native background motion belongs in association, not only in the later
    # contact gate. Otherwise a camera acceleration can reject the SAME ball
    # and make a stationary reserve appear to change its physical velocity.
    native = isinstance(geometry, dict) and geometry.get("native") is True
    if native and geometry.get("transform") is None:
        return None
    pred = _predict_box(prior, media_ms)
    if native:
        pred = geometry["predict_box"](prior, media_ms)
        if pred is None:
            return None
    pcx, pcy = _center(pred); cx, cy = _center(box)
    x_scale = geometry["x_scale"] if native else 1.0
    dist = math.hypot((cx - pcx) * x_scale, cy - pcy)
    foot_h = candidate.get("_nearest_player_foot_h")
    player_supported = _num(foot_h) and float(foot_h) <= DORMANT_PLAYER_SUPPORT_H
    age_from_measurement_ms = int(media_ms) - last_measured_ms
    max_dist = BASE_JUMP_NORM + MAX_SPEED_NORM_S * dt
    # After the ordinary short-gap horizon the hypothesis is dormant.  Default
    # re-acquisition is deliberately tight, but a detector proposal very close
    # to a verified local player's foot may use the normal physical speed
    # envelope because genuine football touches can change direction abruptly.
    # This is trajectory support only; it never verifies a touch.
    if age_from_measurement_ms > SHORT_GAP_MS and not player_supported:
        max_dist = min(max_dist, DORMANT_MAX_RESIDUAL_NORM)
    if dist > max_dist:
        return None
    continuity = max(0.0, 1.0 - dist / max(max_dist, 1e-9))
    prev_scale = _area_scale(pred if native else (prior.get("last_measured_box") or prior["box"]))
    cur_scale = _area_scale(box)
    scale_ratio = min(prev_scale, cur_scale) / max(prev_scale, cur_scale, 1e-9)
    min_scale_ratio = (
        DORMANT_PLAYER_SUPPORTED_SCALE_MIN
        if age_from_measurement_ms > SHORT_GAP_MS and player_supported
        else 0.35
    )
    if scale_ratio < min_scale_ratio:
        return None
    measured_box = prior.get("last_measured_box") or prior["box"]
    px, py = _center(measured_box)
    if native:
        px, py = geometry["transform"](measured_box, last_measured_ms)
    velocity = ((cx - px) / dt, (cy - py) / dt)
    accel = None
    acceleration_score = 1.0
    if prior.get("velocity") is not None:
        pvx, pvy = prior["velocity"]
        if native:
            pvx, pvy = geometry["transform_velocity"](prior["velocity"], last_measured_ms)
        accel = ((velocity[0] - pvx) / dt, (velocity[1] - pvy) / dt)
        accel_mag = math.hypot(accel[0] * x_scale, accel[1])
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


def _rank_candidates(candidates, hypotheses, media_ms, *, geometry=None):
    ranked = []
    for ci, candidate in enumerate(candidates):
        if not isinstance(candidate, dict) or not _valid_box(candidate.get("box")):
            continue
        options = []
        for hi, prior in enumerate(hypotheses):
            row = _candidate_from_prior(candidate, prior, media_ms, geometry=geometry)
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


def _native_association_geometry(frames, index):
    """Native association only; no camera guess or legacy fallback in a mixed trace."""
    if not any("camera_motion" in f for f in frames):
        return None
    frame = frames[index]
    scale = frame_geometry.horizontal_scale(frame)
    unavailable = {"native": True, "transform": None}
    if scale is None or not ball_motion_evidence._native(frame):
        return unavailable
    width, height = (frame["frame_dimensions"][k] for k in ("width", "height"))
    matrices = {}

    def matrix(ms):
        if ms not in matrices:
            matrices[ms] = ball_motion_evidence._transform_between(
                frames, int(ms), frame["media_ms"])
        return matrices[ms]

    def transform(box, ms):
        m = matrix(ms)
        if m is None:
            return None
        x, y = _center(box)
        p = m @ np.array([x*width, y*height, 1.])
        return p[0]/width, p[1]/height

    def transform_velocity(velocity, ms):
        m = matrix(ms)
        if m is None:
            return None
        v = m[:2, :2] @ np.array([velocity[0]*width, velocity[1]*height])
        return v[0]/width, v[1]/height

    def predict_box(prior, media_ms):
        measured = prior.get("last_measured_box") or prior["box"]
        ms = int(prior.get("last_measured_ms", prior["media_ms"]))
        center = transform(measured, ms)
        velocity = transform_velocity(prior.get("velocity") or (0., 0.), ms)
        if center is None or velocity is None:
            return None
        dt = (media_ms-ms)/1000
        # Transform all four corners, retaining measured size under camera zoom.
        m = matrix(ms)
        corners = np.array([
            [measured["x"]*width, measured["y"]*height, 1.],
            [(measured["x"]+measured["w"])*width, measured["y"]*height, 1.],
            [measured["x"]*width, (measured["y"]+measured["h"])*height, 1.],
            [(measured["x"]+measured["w"])*width, (measured["y"]+measured["h"])*height, 1.]])
        projected = (m @ corners.T).T
        w = float(projected[:, 0].max()-projected[:, 0].min())/width
        h = float(projected[:, 1].max()-projected[:, 1].min())/height
        return {"x": center[0]+velocity[0]*dt-w/2,
                "y": center[1]+velocity[1]*dt-h/2, "w": w, "h": h}

    return {"native": True, "transform": transform,
            "transform_velocity": transform_velocity, "predict_box": predict_box,
            "x_scale": scale}


def _search_hypotheses(candidates, previous, media_ms, geometry):
    """Retain new objects while a linked reserve wins; these are NEVER proof.

    The authoritative trajectory and this bounded search channel are separate.
    Repeated detector observations, a high score or a nearby player cannot
    silently promote a search object into a verified contact or release seed.
    """
    previous = [h for h in previous if 0 < media_ms-h["last_measured_ms"] <= SHORT_GAP_MS]
    pairs = []
    scale = geometry["x_scale"] if geometry and geometry.get("transform") is not None else 1.0
    for ci, candidate in enumerate(candidates):
        for hi, prior in enumerate(previous):
            row = _candidate_from_prior(candidate, prior, media_ms, geometry=geometry)
            if row is None:
                continue
            predicted = (geometry["predict_box"](prior, media_ms)
                         if geometry else _predict_box(prior, media_ms))
            if predicted is None:
                continue
            px, py = _center(predicted); cx, cy = _center(row["box"])
            residual = math.hypot((cx-px)*scale, cy-py)
            sigma = max(BASE_JUMP_NORM, min(predicted["w"]*scale, predicted["h"]))
            a, b = _area_scale(predicted), _area_scale(row["box"])
            support = math.exp(-0.5*(residual/sigma)**2)*min(a,b)/max(a,b)
            if support >= RELEASE_MIN_MOTION_SUPPORT:
                pairs.append((support, hi, ci, row))
    pairs.sort(key=lambda p: (-p[0], p[1], p[2]))
    used = set()
    matched = {}
    for support, hi, ci, row in pairs:
        if hi in used or ci in matched:
            continue
        # BOTH sides must be unique. Confidence cannot choose between two
        # plausible balls, nor inflate one old object into two confirmations.
        rivals = [p[0] for p in pairs if (p[1] == hi or p[2] == ci)
                  and (p[1],p[2]) != (hi,ci)]
        if rivals and support-max(rivals) < SCORE_MARGIN:
            continue
        used.add(hi)
        matched[ci] = {**row, "prior_hypothesis": hi, "candidate_index": ci,
                       "search_motion_support": float(support)}
    linked = sorted(matched.values(), key=lambda r: -r["search_motion_support"])[:MAX_HYPOTHESES]
    fresh = []
    for ci, candidate in enumerate(candidates):
        if ci in matched:
            continue
        row = _candidate_from_prior(candidate, None, media_ms)
        if row is not None:
            fresh.append({**row,"prior_hypothesis":None,"candidate_index":ci})
    fresh.sort(key=lambda r: (-r["score"],tuple(r["box"][k] for k in ("x","y","w","h"))))
    ranked = linked+fresh[:MAX_HYPOTHESES]
    used = set()
    kept = []
    for row in ranked:
        prior_index = row.get("prior_hypothesis")
        if prior_index is not None:
            used.add(prior_index)
        hyp = _hypothesis_from_ranked(row, media_ms)
        prior = previous[prior_index] if row.get("prior_hypothesis") is not None else None
        hyp["search_observations"] = (prior.get("search_observations", 1)+1) if prior else 1
        hyp["search_first_ms"] = prior.get("search_first_ms", media_ms) if prior else media_ms
        seed = repr((media_ms,tuple(row["box"][k] for k in ("x","y","w","h")))).encode()
        hyp["search_track_id"] = prior["search_track_id"] if prior else "ball_search_"+hashlib.sha256(seed).hexdigest()[:16]
        hyp["search_motion_support"] = row.get("search_motion_support")
        kept.append(hyp)
        if len(kept) == MAX_SEARCH_HYPOTHESES:
            break
    # Missing search measurements stay INTERNAL for a bounded interval. They
    # are not exported as if measured again in the current frame.
    remaining = sorted((h for i, h in enumerate(previous) if i not in used),
                       key=lambda h: (h["last_measured_ms"], h["search_observations"]), reverse=True)
    return (kept+remaining)[:MAX_SEARCH_HYPOTHESES]


def _hypothesis_from_ranked(row: dict, media_ms: int) -> dict:
    measured = _box(row["box"])
    return {
        "media_ms": int(media_ms),
        "last_measured_ms": int(row.get("last_measured_ms") or media_ms),
        "last_measured_box": measured,
        "box": measured,
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
    search = []
    rows = []
    frames = [frame for frame in dense_frames or []
              if isinstance(frame, dict) and _num(frame.get("media_ms"))]
    for index, frame in enumerate(frames):
        media_ms = int(round(float(frame["media_ms"])))
        cut = frame.get("cut_barrier") is True or frame.get("cut") is True
        if cut:
            hypotheses = []
            search = []
        raw_candidates = []
        for candidate in frame.get("ball_candidates") or []:
            if not isinstance(candidate, dict) or not _valid_box(candidate.get("box")):
                continue
            row = deepcopy(candidate)
            row["_nearest_player_foot_h"] = _nearest_player_foot_h(
                row["box"], frame.get("players") or [], frame_geometry.horizontal_scale(frame)
            )
            raw_candidates.append(row)
        geometry = _native_association_geometry(frames, index)
        ranked = _rank_candidates(raw_candidates, hypotheses, media_ms, geometry=geometry)
        # Independent search sees EVERY proposal, including one that the
        # authoritative ranker mis-associated. Nothing flows back into proof.
        search = _search_hypotheses(raw_candidates, search, media_ms, geometry)
        used_fallback = bool(frame.get("used_fallback"))
        common = {
            "media_ms": media_ms,
            "used_fallback": used_fallback,
            "time_authority": frame.get("time_authority") or (
                "FRAME_INDEX_FPS_FALLBACK" if used_fallback else "ACTUAL_MEDIA_PTS"
            ),
            "cut_barrier": bool(cut),
        }
        if "frame_dimensions" in frame:
            common["frame_dimensions"] = deepcopy(frame["frame_dimensions"])
        common["search_candidates"] = [
            {"box": _box(h["box"]), "confidence": round(h["confidence"], 4),
             "search_observations": h["search_observations"],
             "search_first_ms": h["search_first_ms"], "media_ms": media_ms,
             "search_track_id": h["search_track_id"],
             "search_motion_support": h["search_motion_support"],
             "proof_eligible": False, "state": "SEARCH_ONLY",
             "provenance": "BOUNDED_INDEPENDENT_BALL_SEARCH"}
            for h in search if h["last_measured_ms"] == media_ms
        ]

        # A discontinuous one-frame detector proposal must not immediately
        # replace an active trajectory.  Prefer candidates linked to an existing
        # hypothesis; if none link, keep the old trajectory alive for the bounded
        # short-gap interval and treat the new proposal as untrusted bootstrap.
        if ranked and hypotheses:
            linked = [r for r in ranked if r.get("prior_hypothesis") is not None]
            if linked:
                ranked = linked
            else:
                best = max(hypotheses, key=lambda h: h.get("score", 0.0))
                age = media_ms - int(best.get("last_measured_ms") or best["media_ms"])
                if 0 < age <= DORMANT_REACQUIRE_MS:
                    if age <= SHORT_GAP_MS:
                        predicted = (geometry["predict_box"](best, media_ms)
                                     if geometry and geometry.get("transform") is not None
                                     else _predict_box(best, media_ms) if geometry is None else None)
                        if predicted is None:
                            rows.append({**common, "state": "MISSING", "box": None,
                                         "confidence": 0.0, "candidates": [], "proof_eligible": False,
                                         "provenance": "NATIVE_CAMERA_ASSOCIATION_UNAVAILABLE"})
                            continue
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
                            "provenance": "KINEMATIC_SHORT_GAP_DISCONTINUITY_REJECTED",
                        })
                    else:
                        # Preserve the last measured hypothesis internally, but
                        # expose no synthetic box beyond the short proof/search
                        # horizon.  A nearby future measurement may re-acquire it.
                        hypotheses = [best]
                        rows.append({
                            **common, "state": "MISSING", "box": None,
                            "confidence": 0.0, "candidates": [],
                            "proof_eligible": False,
                            "provenance": "DORMANT_REACQUIRE_DISCONTINUITY_REJECTED",
                        })
                    continue

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
                    "player_foot_support_h": (
                        round(float(raw_candidates[r["candidate_index"]].get("_nearest_player_foot_h")), 4)
                        if _num(raw_candidates[r["candidate_index"]].get("_nearest_player_foot_h")) else None
                    ),
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
            if 0 < age <= DORMANT_REACQUIRE_MS:
                if age <= SHORT_GAP_MS:
                    predicted = (geometry["predict_box"](best, media_ms)
                                 if geometry and geometry.get("transform") is not None
                                 else _predict_box(best, media_ms) if geometry is None else None)
                    if predicted is None:
                        rows.append({**common, "state": "MISSING", "box": None,
                                     "confidence": 0.0, "candidates": [], "proof_eligible": False,
                                     "provenance": "NATIVE_CAMERA_ASSOCIATION_UNAVAILABLE"})
                        continue
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
                else:
                    hypotheses = [best]
                    rows.append({
                        **common, "state": "MISSING", "box": None,
                        "confidence": 0.0, "candidates": [],
                        "proof_eligible": False,
                        "provenance": "DORMANT_REACQUIRE_WAIT",
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


def _proof_measured_ball(row) -> bool:
    return bool(
        isinstance(row, dict)
        and _num(row.get("media_ms"))
        and row.get("proof_eligible") is True
        and row.get("time_authority") == "ACTUAL_MEDIA_PTS"
        and row.get("used_fallback") is not True
        and row.get("cut_barrier") is not True
        and row.get("cut") is not True
        and row.get("state") in {"MEASURED", "MEASURED_REACQUISITION"}
        and _valid_box(row.get("box"))
    )


def reconstruct_ball_trajectory_from_release_anchor(
    dense_frames, anchor: dict, scene_id: str | None = None,
    max_duration_ms: int = 3000,
) -> list[dict]:
    """Re-track one shot from its independently verified post-contact ball.

    The global trajectory may have stayed attached to a competing ball. A
    verified release anchor can seed a separate, shot-local path, but it cannot
    by itself bridge a detector jump: a player-supported jump must be confirmed
    by a second nearby, actual-PTS ball observation before either point becomes
    measured path evidence. Established measured motion, not proximity to the
    last box or detector confidence, disambiguates competing objects. A loss
    beyond the bounded measured-gap horizon ends this identity; it cannot grow
    an arbitrary reattachment radius. No predicted point becomes proof.
    """
    if not _proof_measured_ball(anchor):
        return []

    seed_ms = int(anchor["media_ms"])
    rows = [{
        "media_ms": seed_ms, "scene_id": scene_id, "state": "MEASURED",
        "box": _box(anchor["box"]),
        "confidence": float(anchor.get("confidence") or 0.0),
        "proof_eligible": True, "time_authority": "ACTUAL_MEDIA_PTS",
        "used_fallback": False, "cut_barrier": False,
        "provenance": "VERIFIED_RELEASE_CONTACT_BALL_AFTER", "candidates": [],
    }]
    last = rows[0]
    pending = None
    jump_supported = False
    velocity = None
    source_frames = sorted(
        (f for f in dense_frames or [] if isinstance(f, dict) and _num(f.get("media_ms"))),
        key=lambda f: int(f["media_ms"]),
    )

    for index, frame in enumerate(source_frames):
        ms = int(frame["media_ms"])
        if ms <= seed_ms:
            continue
        if ms - seed_ms > max(0, int(max_duration_ms)):
            break
        frame_scene = frame.get("scene_id")
        if frame.get("cut_barrier") is True or frame.get("cut") is True:
            break
        if scene_id is not None and frame_scene not in {None, scene_id}:
            break
        # A label is not a transform. Explicitly unresolved camera geometry
        # ends this image-space identity; a later label cannot repair the gap.
        # Missing labels retain the legacy measured-coordinate contract.
        if frame.get("camera_state") not in {None, "AFFINE_VERIFIED"}:
            break
        if frame.get("used_fallback") is True or frame.get("time_authority") != "ACTUAL_MEDIA_PTS":
            continue
        if pending and ms - pending["media_ms"] > RELEASE_REACQUIRE_CONFIRM_MAX_GAP_MS:
            break
        if not pending and ms - int(last["media_ms"]) > RELEASE_MAX_MEASURED_GAP_MS:
            break
        candidates = []
        for candidate in frame.get("ball_candidates") or []:
            if not isinstance(candidate, dict) or not _valid_box(candidate.get("box")):
                continue
            if (candidate.get("used_fallback") is True or candidate.get("proof_eligible") is False
                    or candidate.get("state") not in {None, "MEASURED", "MEASURED_REACQUISITION"}
                    or candidate.get("time_authority") not in {None, "ACTUAL_MEDIA_PTS"}):
                continue
            if not _num(candidate.get("confidence")) or not math.isfinite(candidate["confidence"]):
                continue
            confidence = float(candidate.get("confidence") or 0.0)
            if confidence < RELEASE_REACQUIRE_MIN_CONFIDENCE:
                continue
            candidate_box = _box(candidate["box"])
            reference_box = (pending or last)["box"]
            scale_ratio = min(_area_scale(candidate_box), _area_scale(reference_box)) / max(
                _area_scale(candidate_box), _area_scale(reference_box))
            if scale_ratio >= 0.35:
                candidates.append({"box": candidate_box, "confidence": confidence})
        if not candidates:
            continue

        geometry = _native_association_geometry(source_frames, index)
        if geometry is not None:
            # A camera label alone cannot reconnect a shot identity. Native
            # paths use exact background transforms and the SAME speed,
            # acceleration, scale, measured-gap and support thresholds as A3.
            # They never fall back to an unmeasured image-space jump.
            if geometry.get("transform") is None:
                break
            prior = {"media_ms": last["media_ms"], "last_measured_ms": last["media_ms"],
                     "box": last["box"], "last_measured_box": last["box"], "velocity": velocity}
            prediction = geometry["predict_box"](prior, ms)
            if prediction is None:
                break
            pcx, pcy = _center(prediction)
            x_scale = geometry["x_scale"]
            sigma = max(BASE_JUMP_NORM,
                        math.sqrt(prediction["w"]*x_scale*prediction["h"]))
            supported = []
            for candidate in candidates:
                row = _candidate_from_prior(candidate, prior, ms, geometry=geometry)
                if row is None:
                    continue
                cx, cy = _center(row["box"])
                residual = math.hypot((cx-pcx)*x_scale, cy-pcy)
                a, b = _area_scale(prediction), _area_scale(row["box"])
                support = math.exp(-0.5*(residual/sigma)**2)*min(a,b)/max(a,b)
                supported.append((support,row))
            supported.sort(key=lambda pair: pair[0], reverse=True)
            if (not supported
                    or (velocity is not None and supported[0][0] < RELEASE_MIN_MOTION_SUPPORT)
                    or (len(supported)>1 and supported[0][0]-supported[1][0] < SCORE_MARGIN)):
                continue
            chosen = supported[0][1]
            row = {"media_ms": ms, "scene_id": scene_id, "state": "MEASURED",
                   "box": chosen["box"], "confidence": chosen["confidence"],
                   "proof_eligible": True, "time_authority": "ACTUAL_MEDIA_PTS",
                   "used_fallback": False, "cut_barrier": False,
                   "provenance": "RELEASE_ANCHORED_NATIVE_CAMERA_MOTION", "candidates": [],
                   "frame_dimensions": deepcopy(frame["frame_dimensions"])}
            rows.append(row)
            velocity = chosen["velocity"]
            last = row
            continue

        previous = pending if pending else last
        dt = (ms - int(previous["media_ms"])) / 1000.0
        if dt <= 0:
            continue
        px, py = _center(previous["box"])
        ranked = sorted(
            ((math.hypot(_center(c["box"])[0] - px, _center(c["box"])[1] - py), c)
             for c in candidates), key=lambda pair: pair[0],
        )
        nearest_dist, nearest = ranked[0]
        next_dist = ranked[1][0] if len(ranked) > 1 else float("inf")
        ordinary_limit = BASE_JUMP_NORM + MAX_SPEED_NORM_S * dt

        if pending:
            if nearest_dist > ordinary_limit or next_dist - nearest_dist < SCORE_MARGIN:
                pending = None
                continue
            first = pending
            rows.append({
                "media_ms": first["media_ms"], "scene_id": scene_id,
                "state": "MEASURED", "box": first["box"],
                "confidence": first["confidence"], "proof_eligible": True,
                "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False,
                "cut_barrier": False,
                "provenance": "RELEASE_ANCHOR_REACQUISITION_CONFIRMED", "candidates": [],
            })
            row = {
                "media_ms": ms, "scene_id": scene_id, "state": "MEASURED",
                "box": nearest["box"], "confidence": nearest["confidence"],
                "proof_eligible": True, "time_authority": "ACTUAL_MEDIA_PTS",
                "used_fallback": False, "cut_barrier": False,
                "provenance": "RELEASE_ANCHOR_REACQUISITION_CONFIRMED", "candidates": [],
            }
            rows.append(row)
            fx, fy = _center(first["box"])
            nx, ny = _center(row["box"])
            velocity = ((nx - fx) / dt, (ny - fy) / dt)
            last, pending, jump_supported = row, None, True
            continue

        if velocity is not None:
            prior = {"media_ms": last["media_ms"], "last_measured_ms": last["media_ms"],
                     "box": last["box"], "last_measured_box": last["box"], "velocity": velocity}
            prediction = _predict_box(prior, ms)
            pcx, pcy = _center(prediction)
            # SCORE_MARGIN remains a dimensionless support margin, not a raw
            # 12%-of-image distance. Confidence cannot overrule ball identity.
            sigma = max(BASE_JUMP_NORM, _area_scale(last["box"]))
            motion_ranked = []
            for c in candidates:
                cx, cy = _center(c["box"])
                if math.hypot(cx - px, cy - py) > ordinary_limit:
                    continue
                supported = _candidate_from_prior(c, prior, ms)
                if supported is None:
                    continue
                residual = math.hypot(cx - pcx, cy - pcy)
                scale_ratio = min(_area_scale(last["box"]), _area_scale(c["box"])) / max(
                    _area_scale(last["box"]), _area_scale(c["box"]))
                support = math.exp(-0.5 * (residual / sigma) ** 2) * scale_ratio
                motion_ranked.append((support, supported))
            motion_ranked.sort(key=lambda item: item[0], reverse=True)
            if (not motion_ranked or motion_ranked[0][0] < RELEASE_MIN_MOTION_SUPPORT
                    or (len(motion_ranked) > 1
                    and motion_ranked[0][0] - motion_ranked[1][0] < SCORE_MARGIN)):
                continue
            nearest = motion_ranked[0][1]
            row = {
                "media_ms": ms, "scene_id": scene_id, "state": "MEASURED",
                "box": nearest["box"], "confidence": nearest["confidence"],
                "proof_eligible": True, "time_authority": "ACTUAL_MEDIA_PTS",
                "used_fallback": False, "cut_barrier": False,
                "provenance": "RELEASE_ANCHORED_MEASURED_MOTION", "candidates": [],
            }
            rows.append(row)
            velocity = nearest["velocity"]
            last = row
            continue

        if nearest_dist <= ordinary_limit:
            if next_dist - nearest_dist < SCORE_MARGIN:
                continue
            row = {
                "media_ms": ms, "scene_id": scene_id, "state": "MEASURED",
                "box": nearest["box"], "confidence": nearest["confidence"],
                "proof_eligible": True, "time_authority": "ACTUAL_MEDIA_PTS",
                "used_fallback": False, "cut_barrier": False,
                "provenance": "RELEASE_ANCHORED_DENSE_TRAJECTORY", "candidates": [],
            }
            rows.append(row)
            nx, ny = _center(row["box"])
            velocity = ((nx - px) / dt, (ny - py) / dt)
            last = row
            continue

        # Permit a discontinuous recovery only as a pending hypothesis near a
        # verified local player's foot. It becomes usable after confirmation.
        if (
            not jump_supported and nearest_dist <= RELEASE_REACQUIRE_MAX_JUMP_NORM
            and next_dist - nearest_dist >= SCORE_MARGIN
            and _nearest_player_foot_h(nearest["box"], frame.get("players") or []) is not None
            and _nearest_player_foot_h(nearest["box"], frame.get("players") or []) <= DORMANT_PLAYER_SUPPORT_H
        ):
            pending = {"media_ms": ms, "box": nearest["box"], "confidence": nearest["confidence"]}

    return rows


def release_anchor_contact_binding(dense_frames, contact_ball, anchor, scene_id) -> dict:
    """Check the measured contact-to-seed path independently of the global path.

    A peer's OLD coordinates cannot establish permanent object identity. Start
    from the physically verified contact ball and require a bounded sequence
    of unique native measurements to the EXACT post-contact observation. This
    never infers a missing camera transform, a touch, or an event label.
    """
    rejected = {"status": "REJECTED", "reason": "CONTACT_TO_RELEASE_ANCHOR_UNPROVEN",
                "measured_times_ms": []}
    if not _proof_measured_ball(contact_ball):
        return {**rejected, "reason": "CONTACT_BALL_NOT_PROOF_ELIGIBLE"}
    if not _proof_measured_ball(anchor):
        return {**rejected, "reason": "RELEASE_ANCHOR_NOT_PROOF_ELIGIBLE"}
    contact_ms, seed_ms = int(contact_ball["media_ms"]), int(anchor["media_ms"])
    if not 0 <= seed_ms - contact_ms <= CONTACT_RELEASE_MAX_MS:
        return {**rejected, "reason": "CONTACT_TO_RELEASE_TIME_INVALID"}
    for point in (contact_ball, anchor):
        if scene_id is not None and point.get("scene_id") not in {None, scene_id}:
            return {**rejected, "reason": "CONTACT_TO_RELEASE_SCENE_MISMATCH"}
    # Mixed/fallback observations are not a missing image that can be silently
    # bridged. They cannot certify this specific contact-to-seed contract.
    for frame in dense_frames or []:
        if not isinstance(frame, dict) or not _num(frame.get("media_ms")):
            continue
        if contact_ms < frame["media_ms"] <= seed_ms and (
            frame.get("used_fallback") is True
            or frame.get("time_authority") != "ACTUAL_MEDIA_PTS"
        ):
            return {**rejected, "reason": "CONTACT_TO_RELEASE_TIME_AUTHORITY_INVALID"}
    bridge = reconstruct_ball_trajectory_from_release_anchor(
        dense_frames, contact_ball, scene_id, max_duration_ms=seed_ms - contact_ms)
    measured_seed = next((r for r in bridge if r["media_ms"] == seed_ms), None)
    if measured_seed is None or not all(
        math.isclose(float(measured_seed["box"][k]), float(anchor["box"][k]),
                     rel_tol=0.0, abs_tol=1e-9) for k in ("x", "y", "w", "h")
    ):
        return {**rejected, "measured_times_ms": [r["media_ms"] for r in bridge]}
    return {"status": "VERIFIED", "reason": "MEASURED_CONTACT_TO_EXACT_RELEASE_ANCHOR",
            "contact_ms": contact_ms, "seed_ms": seed_ms,
            "measured_times_ms": [r["media_ms"] for r in bridge]}


def qualify_native_release_seed(dense_frames, contact_ball, provisional_anchor, scene_id):
    """Choose an eligible seed BEFORE binding a fresh, weak native proposal.

    A3 accepts proposals down to .03, while the unchanged release tracker needs
    .04. Do not ask that tracker to certify an observation it must discard.
    Instead, require a unique measured path FROM the verified contact, and
    choose its earliest eligible post-contact observation. The weak proposal
    must also be consistent with that path; it never becomes path proof.

    This is not a retry for an explicitly rejected/required anchor. Callers
    must restrict it to a fresh ball_after produced by the current touch.
    No global/search/predicted trajectory, actor label or event label is used.
    """
    if (not _proof_measured_ball(contact_ball) or not _proof_measured_ball(provisional_anchor)
            or provisional_anchor.get("identity_rejection") is not None
            or any(type(p.get("media_ms")) is not int for p in (contact_ball, provisional_anchor))
            or not _num(contact_ball.get("confidence")) or not 0 <= contact_ball["confidence"] <= 1
            or not _num(provisional_anchor.get("confidence"))
            or not 0 <= provisional_anchor["confidence"] < RELEASE_REACQUIRE_MIN_CONFIDENCE):
        return None
    contact_ms, original_ms = contact_ball["media_ms"], provisional_anchor["media_ms"]
    if not 0 < original_ms-contact_ms <= CONTACT_RELEASE_MAX_MS:
        return None
    if any(scene_id is not None and p.get("scene_id") not in {None, scene_id}
           for p in (contact_ball, provisional_anchor)):
        return None
    frames = sorted((f for f in dense_frames or [] if isinstance(f, dict)
                     and type(f.get("media_ms")) is int), key=lambda f: f["media_ms"])
    originals = [f for f in frames if f["media_ms"] == original_ms]
    if (len(originals) != 1 or "camera_motion" not in originals[0]
            or not ball_motion_evidence._native(originals[0])):
        return None
    original = originals[0]
    proposals = [c for c in original.get("ball_candidates") or [] if isinstance(c, dict)
                 and _valid_box(c.get("box")) and _num(c.get("confidence"))
                 and c.get("proof_eligible") is not False and c.get("used_fallback") is not True
                 and c.get("state") in {None, "MEASURED", "MEASURED_REACQUISITION"}
                 and c.get("time_authority") in {None, "ACTUAL_MEDIA_PTS"}]
    matching = [c for c in proposals if all(math.isclose(float(c["box"][k]),
                float(provisional_anchor["box"][k]), rel_tol=0., abs_tol=1e-9)
                for k in ("x", "y", "w", "h"))]
    if len(matching) != 1 or not 0 <= matching[0]["confidence"] < RELEASE_REACQUIRE_MIN_CONFIDENCE:
        return None

    bridge = reconstruct_ball_trajectory_from_release_anchor(
        frames, contact_ball, scene_id, max_duration_ms=CONTACT_RELEASE_MAX_MS)
    seed = next((p for p in bridge if p["media_ms"] > original_ms
                 and p.get("provenance") == "RELEASE_ANCHORED_NATIVE_CAMERA_MOTION"
                 and _num(p.get("confidence"))
                 and p["confidence"] >= RELEASE_REACQUIRE_MIN_CONFIDENCE), None)
    if seed is None:
        return None
    binding = release_anchor_contact_binding(frames, contact_ball, seed, scene_id)
    if binding["status"] != "VERIFIED":
        return None

    # Interpolation is SUPPORT ONLY, used to exclude a weak remote competitor.
    # Both endpoints and every camera transform are independently measured.
    before = ball_motion_evidence._transform_between(frames, contact_ms, original_ms)
    after = ball_motion_evidence._transform_between(frames, original_ms, seed["media_ms"])
    if before is None or after is None:
        return None
    width, height = (original["frame_dimensions"][k] for k in ("width", "height"))
    def project_box(box, matrix):
        corners = np.array([[box["x"]*width, box["y"]*height, 1.],
            [(box["x"]+box["w"])*width, box["y"]*height, 1.],
            [box["x"]*width, (box["y"]+box["h"])*height, 1.],
            [(box["x"]+box["w"])*width, (box["y"]+box["h"])*height, 1.]])
        pixels = (matrix @ corners.T).T
        low, high = pixels[:, :2].min(axis=0), pixels[:, :2].max(axis=0)
        return np.array([low[0]/width, low[1]/height,
                         (high[0]-low[0])/width, (high[1]-low[1])/height])
    fraction = (original_ms-contact_ms)/(seed["media_ms"]-contact_ms)
    expected = ((1-fraction)*project_box(contact_ball["box"], before)
                + fraction*project_box(seed["box"], np.linalg.inv(after)))
    expected_box = dict(zip(("x", "y", "w", "h"), expected))
    px, py = _center(expected_box)
    x_scale = width/height
    sigma = max(BASE_JUMP_NORM, math.sqrt(expected_box["w"]*x_scale*expected_box["h"]))
    def support(box):
        cx, cy = _center(box)
        a, b = _area_scale(box), _area_scale(expected_box)
        return math.exp(-.5*(math.hypot((cx-px)*x_scale, cy-py)/sigma)**2)*min(a,b)/max(a,b)
    original_support = support(matching[0]["box"])
    rivals = [support(c["box"]) for c in proposals if c is not matching[0]]
    if (original_support < RELEASE_MIN_MOTION_SUPPORT
            or (rivals and original_support-max(rivals) < SCORE_MARGIN)):
        return None
    return {"anchor": {**deepcopy(seed), "source": provisional_anchor.get("source"),
                       "remote_spare_ball_used": False},
            "audit": {"status": "QUALIFIED", "reason": "FRESH_NATIVE_SEED_BELOW_RELEASE_CONFIDENCE_FLOOR",
                "original_anchor": deepcopy(provisional_anchor), "qualified_seed_ms": seed["media_ms"],
                "release_confidence_floor": RELEASE_REACQUIRE_MIN_CONFIDENCE,
                "contact_binding": binding, "provisional_consistency": {
                    "source": "MEASURED_ENDPOINT_CAMERA_INTERPOLATION_SUPPORT_ONLY",
                    "proof_eligible": False, "motion_support": float(original_support)}}}


def qualify_produced_contact_seed(dense_frames, touch, anchor, scene_id):
    """Share fresh producer seed selection before either role or shot binding.

    The anchor must still be the unchanged ball_after of a verified physical
    touch. An external required seed or a previously rejected identity cannot
    be replaced. Qualification measures a new seed; it never raises the weak
    observation's confidence or changes the original touch.
    """
    after = touch.get("ball_after") if isinstance(touch, dict) else None
    if (not isinstance(touch, dict) or not isinstance(anchor, dict) or not isinstance(after, dict)
            or touch.get("status") != "VERIFIED" or touch.get("proof_eligible") is not True
            or anchor.get("remote_spare_ball_used") is True or after.get("remote_spare_ball_used") is True
            or anchor.get("source") not in {"VERIFIED_RELEASE_CONTACT_BALL_AFTER",
                                            "VERIFIED_SCORING_CONTROL_BALL_AFTER",
                                            "VERIFIED_CONTACT_ROLE_BALL_AFTER"}
            or any(anchor.get(k) != after.get(k) for k in
                   ("media_ms", "box", "confidence", "state", "proof_eligible", "time_authority"))):
        return None
    return qualify_native_release_seed(dense_frames, touch.get("ball_at_contact"), anchor, scene_id)


def select_release_ball_trajectory(dense_frames, anchor, scene_id, global_trajectory,
                                   *, anchor_required=False, max_duration_ms=3000,
                                   contact_ball=None, contact_required=False) -> dict:
    """One shared fail-closed policy for live, contact-role and replay callers.

    Explicit/rejected anchors never fall back to an unrelated global object.
    Legacy callers with no anchor contract retain their previous global path.
    """
    if anchor is not None or anchor_required:
        binding = None
        if contact_ball is not None or contact_required:
            binding = release_anchor_contact_binding(dense_frames, contact_ball, anchor, scene_id)
            if binding["status"] != "VERIFIED":
                return {"rows": [], "source": "REJECTED_RELEASE_ANCHOR", "seed_ms": None,
                        "contact_binding": binding}
        if binding is not None:
            # Keep the measured contact prefix while tracking forward. Resetting
            # at the after-contact seed discards already established velocity
            # and can make a nearby, stationary competitor look equally valid.
            seed_ms = int(anchor["media_ms"])
            rows = reconstruct_ball_trajectory_from_release_anchor(
                dense_frames, contact_ball, scene_id,
                seed_ms - int(contact_ball["media_ms"]) + max(0, int(max_duration_ms)))
            rows = [row for row in rows if row["media_ms"] >= seed_ms]
        else:
            rows = reconstruct_ball_trajectory_from_release_anchor(
                dense_frames, anchor, scene_id, max_duration_ms)
        return {"rows": rows,
                "source": "VERIFIED_RELEASE_ANCHOR" if rows else "REJECTED_RELEASE_ANCHOR",
                "seed_ms": int(anchor["media_ms"]) if rows else None,
                **({"contact_binding": binding} if binding is not None else {})}
    return {"rows": global_trajectory or [], "source": "WINDOW_GLOBAL_TRAJECTORY", "seed_ms": None}
