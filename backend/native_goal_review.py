"""Measure a reviewed ball reappearance locally; text never supplies identity.

The reader supplies geometry and search boxes. This module re-detects balls in
native images, checks competing paths and measures background camera motion.
It performs no decoding, HTTP requests, event writes or trajectory projection.
"""
from __future__ import annotations

from copy import deepcopy
import math
import re

import native_ball_reappearance as native
import goal_reappearance

MAX_AFTER_FRAMES = 6
MAX_BALLS_PER_FRAME = 8
MAX_ASSOCIATION_DIAMETERS = 3.


def _iou(a, b):
    return goal_reappearance._iou(a, b)


def measure_review(review, before, images_by_ms, *, video_sha256,
                   model_sha256, detect_frame, camera_estimator):
    """Callbacks operate only on supplied original pixels, never reader JSON.

    ``detect_frame(image, proposal)`` returns native ``(people, balls)``. The
    proposal is a search ROI only; the full-image search must also be retained.
    ``camera_estimator(current_gray, reference_gray, excluded_pixel_boxes)``
    returns a measured current-to-reference affine or ``(None, reason)``.
    """
    import cv2
    import numpy as np

    unresolved = {"status": "UNRESOLVED", "source": native.SOURCE,
                  "method": native.METHOD, "proof_eligible": False}

    def fail(reason):
        link = {**unresolved, "reason": reason}
        return goal_reappearance.build_audit([], None, link)

    if not isinstance(review, dict) or not isinstance(images_by_ms, dict):
        return fail("NATIVE_GOAL_REVIEW_INPUT_INVALID")
    coverage = review.get("response_coverage")
    occ = review.get("occlusion_crossing_audit")
    if (not isinstance(coverage, dict) or coverage.get("status") != "COMPLETED"
            or not isinstance(occ, dict) or occ.get("status") != "VERIFIED_OCCLUSION"):
        return fail("NATIVE_GOAL_REVIEW_OR_OCCLUSION_INCOMPLETE")
    if not (native._verified_time(before) and before.get("state") == "MEASURED"
            and before.get("proof_eligible") is True and native.box_ok(before.get("box"))
            and isinstance(before.get("scene_id"), str) and before["scene_id"]
            and type(occ.get("occlusion_start_media_ms")) is int
            and before["media_ms"] < occ["occlusion_start_media_ms"]
            and type(occ.get("occlusion_end_media_ms")) is int):
        return fail("CONTACT_BOUND_NATIVE_BALL_REFERENCE_MISSING")
    if not all(isinstance(s, str) and re.fullmatch(r"[0-9a-f]{64}", s)
               for s in (video_sha256, model_sha256)):
        return fail("NATIVE_GOAL_SOURCE_FINGERPRINT_MISSING")
    evidence = review.get("ball_evidence")
    if not isinstance(evidence, list):
        return fail("NATIVE_GOAL_AFTER_OBSERVATIONS_MISSING")
    post = [r for r in evidence if isinstance(r, dict)
            and type(r.get("media_ms")) is int
            and occ["occlusion_end_media_ms"] < r["media_ms"]
            <= before["media_ms"] + native.MAX_GAP_MS
            and r.get("ball_visible") is True and r.get("confidence") == "high"
            and r.get("relation") == "BEYOND_LINE_INSIDE_MOUTH"
            and native.box_ok(r.get("ball_box"))]
    post.sort(key=lambda r: r["media_ms"])
    post = post[:MAX_AFTER_FRAMES]
    times = [r["media_ms"] for r in post]
    if (len(post) < native.MIN_AFTER_SAMPLES
            or any(not 0 < b-a <= 120 for a, b in zip(times, times[1:]))
            or times[-1]-times[0] < native.MIN_AFTER_SPAN_MS):
        return fail("NATIVE_GOAL_AFTER_TIME_COVERAGE_INCOMPLETE")
    selected_times = [before["media_ms"], *times]
    frames = [images_by_ms.get(ms) for ms in selected_times]
    if any(not isinstance(im, np.ndarray) or im.dtype != np.uint8
           or im.ndim != 3 or im.shape[2] != 3 for im in frames):
        return fail("NATIVE_GOAL_ORIGINAL_PIXELS_MISSING")
    if any(im.shape != frames[0].shape for im in frames):
        return fail("NATIVE_GOAL_FRAME_DIMENSIONS_CHANGED")
    height, width = frames[0].shape[:2]
    proposals = [before["box"], *[r["ball_box"] for r in post]]
    detected = {}
    people_by_ms = {}
    try:
        for ms, im, proposal in zip(selected_times, frames, proposals):
            people, balls = detect_frame(im, deepcopy(proposal))
            if not isinstance(people, list) or not isinstance(balls, list):
                return fail("NATIVE_GOAL_DETECTOR_RESULT_INVALID")
            rows = []
            for ball in balls:
                if (not isinstance(ball, dict) or not native.box_ok(ball.get("box"))
                        or not native.number(ball.get("confidence"))
                        or not native.MIN_BALL_CONFIDENCE <= ball["confidence"] <= 1):
                    continue
                # Duplicate full-image/ROI detections are one object. Retain
                # the first native box; never replace it with the reader box.
                if any(_iou(ball["box"], r["box"]) >= .45 for r in rows):
                    continue
                rows.append({"media_ms": ms, "box": deepcopy(ball["box"]),
                    "confidence": float(ball["confidence"]), "class_id": 32,
                    "scene_id": before["scene_id"], "state": "MEASURED",
                    "proof_eligible": False, "time_authority": "ACTUAL_MEDIA_PTS",
                    "used_fallback": False, "cut_barrier": False,
                    "source": "LOCAL_NATIVE_DETECTOR",
                    "classification_source": "LOCAL_NATIVE_CLASS32_DETECTOR",
                    "model_sha256": model_sha256})
            if len(rows) > MAX_BALLS_PER_FRAME:
                return fail("NATIVE_GOAL_COMPETING_BALL_BUDGET_EXCEEDED")
            detected[ms] = rows
            people_by_ms[ms] = people
    except Exception:
        return fail("NATIVE_GOAL_DETECTOR_FAILED")

    ref_ms = before["media_ms"]
    ref_gray = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
    for ms, im in zip(times, frames[1:]):
        excluded = [r["box"] for r in detected[ref_ms] + detected[ms]]
        excluded += [p["box"] for p in people_by_ms[ref_ms] + people_by_ms[ms]
                     if isinstance(p, dict) and native.box_ok(p.get("box"))]
        # People boxes can exceed the ball-specific .2 size limit.
        excluded += [p["box"] for p in people_by_ms[ref_ms] + people_by_ms[ms]
                     if isinstance(p, dict) and isinstance(p.get("box"), dict)
                     and all(native.number(p["box"].get(k)) for k in ("x", "y", "w", "h"))
                     and not native.box_ok(p["box"])]
        excluded_px = [(b["x"]*width, b["y"]*height, b["w"]*width, b["h"]*height)
                       for b in excluded]
        try:
            affine, reason = camera_estimator(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY),
                                             ref_gray, excluded_px)
            if affine is None:
                return fail("NATIVE_GOAL_BACKGROUND_CAMERA_UNMEASURED")
            matrix = np.asarray(affine, dtype=float)
            if matrix.shape != (2, 3) or not np.isfinite(matrix).all():
                return fail("NATIVE_GOAL_BACKGROUND_CAMERA_INVALID")
            for r in detected[ms]:
                r["camera_alignment"] = {"status": "MEASURED", "reference_media_ms": ref_ms,
                    "affine_to_reference": matrix.tolist(), "measurement_reason": str(reason)}
                if native._reference_center(r, width, height) is None:
                    return fail("NATIVE_GOAL_BACKGROUND_CAMERA_INVALID")
        except Exception:
            return fail("NATIVE_GOAL_BACKGROUND_CAMERA_INVALID")

    active, alternatives = [], []
    native_post = []
    for r in post:
        rows = detected[r["media_ms"]]
        matches = [b for b in rows if _iou(b["box"], r["ball_box"]) >= .75]
        if len(matches) != 1:
            return fail("NATIVE_GOAL_REVIEWED_BALL_NOT_INDEPENDENTLY_CLASSIFIED")
        active.append(matches[0])
        alternatives.append([b for b in rows if b is not matches[0]])
        native_post.append({**deepcopy(r), "ball_box": deepcopy(matches[0]["box"]),
                            "box_source": "INDEPENDENT_NATIVE_CLASS32_DETECTION"})
    candidates = [{"track_id": "reviewed-reappearance", "observations": active}]
    # Exhaustive one-to-one association of the other classified balls. Partial
    # or crossing alternatives remain unresolved rather than being dropped.
    if len({len(rows) for rows in alternatives}) != 1:
        return fail("NATIVE_GOAL_ALTERNATIVE_BALL_COVERAGE_INCOMPLETE")
    paths = [[r] for r in alternatives[0]]
    for rows in alternatives[1:]:
        used = set()
        for path in paths:
            previous = native._reference_center(path[-1], width, height)
            diameter = max(path[-1]["box"]["w"]*width, path[-1]["box"]["h"]*height)
            matches = [i for i, r in enumerate(rows) if math.dist(
                previous, native._reference_center(r, width, height)
            ) <= MAX_ASSOCIATION_DIAMETERS*diameter]
            if len(matches) != 1 or matches[0] in used:
                return fail("NATIVE_GOAL_ALTERNATIVE_BALL_ASSOCIATION_AMBIGUOUS")
            used.add(matches[0])
            path.append(rows[matches[0]])
    for i, path in enumerate(paths):
        candidate = {"track_id": f"other-native-ball-{i}", "observations": path}
        center = native._reference_center(path[0], width, height)
        diameter = max(path[0]["box"]["w"]*width, path[0]["box"]["h"]*height)
        prior = [r for r in detected[ref_ms] if math.dist(center, (
            (r["box"]["x"]+r["box"]["w"]/2)*width,
            (r["box"]["y"]+r["box"]["h"]/2)*height)) <= diameter*.5]
        if len(prior) == 1:
            candidate["before_observation"] = prior[0]
        candidates.append(candidate)
    link = native.measure_native_link(before, candidates, images_by_ms,
                                      video_sha256=video_sha256)
    audit = goal_reappearance.build_audit(native_post, occ, link)
    audit["native_sampling_audit"] = {"before_media_ms": ref_ms,
        "after_media_ms": times, "detected_ball_counts": {
            str(ms): len(detected[ms]) for ms in selected_times},
        "original_pixels_only": True, "reader_identity_ignored": True}
    return audit
