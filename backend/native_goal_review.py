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
MAX_GAP_ASSOCIATION_DIAMETERS = 1.5


def inspect_gap(before, images_by_ms, *, model_sha256, video_sha256,
                detect_frame, camera_estimator):
    """Bounded native search through a path loss, without semantic promotion.

    Keeps literal detector observations, camera-compensated candidate segments
    and their native identity checks. An image feature or reader assertion is
    never changed into a classified ball. This packet cannot certify a goal.
    """
    import cv2
    import numpy as np
    packet = {"status": "SEARCH_ONLY", "proof_eligible": False,
              "source": "BOUNDED_NATIVE_GOAL_GAP_INSPECTION", "rows": [],
              "candidate_identity_checks": [], "canonical_events_applied": 0}
    if not (native._verified_time(before) and before.get("proof_eligible") is True
            and before.get("state") == "MEASURED" and native.box_ok(before.get("box"))
            and isinstance(before.get("scene_id"), str) and before["scene_id"]
            and isinstance(images_by_ms, dict)
            and all(isinstance(s, str) and re.fullmatch(r"[0-9a-f]{64}", s)
                    for s in (model_sha256, video_sha256))):
        return {**packet, "reason": "NATIVE_GAP_REFERENCE_OR_PROVENANCE_INVALID"}
    ref_ms = before["media_ms"]
    times = sorted(ms for ms in images_by_ms if type(ms) is int
                   and ref_ms <= ms <= ref_ms+native.MAX_GAP_MS)
    if not times or times[0] != ref_ms or len(times) > 56:
        return {**packet, "reason": "NATIVE_GAP_FRAME_BUDGET_OR_REFERENCE_INVALID"}
    ref_image = images_by_ms[ref_ms]
    if (not isinstance(ref_image, np.ndarray) or ref_image.dtype != np.uint8
            or ref_image.ndim != 3 or ref_image.shape[2] != 3):
        return {**packet, "reason": "NATIVE_GAP_REFERENCE_PIXELS_MISSING"}
    h, w = ref_image.shape[:2]
    packet["native_frame_dimensions"] = {"width": w, "height": h}
    packet["camera_alignments"] = {str(ref_ms): {
        "status": "MEASURED", "reference_media_ms": ref_ms,
        "affine_to_reference": [[1.,0.,0.],[0.,1.,0.]],
        "measurement_reason": "EXACT_REFERENCE_FRAME"}}
    ref_gray = cv2.cvtColor(ref_image, cv2.COLOR_BGR2GRAY)
    detections, people_by_ms = {}, {}
    for ms in times:
        image = images_by_ms[ms]
        if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.shape != ref_image.shape:
            return {**packet, "reason": "NATIVE_GAP_ORIGINAL_FRAME_DIMENSIONS_CHANGED"}
        try:
            people, balls = detect_frame(image, deepcopy(before["box"]))
            if not isinstance(people, list) or not isinstance(balls, list):
                return {**packet, "reason": "NATIVE_GAP_DETECTOR_RESULT_INVALID"}
            qualified = []
            for ball in balls:
                if (not isinstance(ball, dict) or not native.box_ok(ball.get("box"))
                        or not native.number(ball.get("confidence"))
                        or not native.MIN_BALL_CONFIDENCE <= ball["confidence"] <= 1):
                    continue
                if any(_iou(ball["box"], r["box"]) >= .45 for r in qualified):
                    continue
                qualified.append({"media_ms": ms, "box": deepcopy(ball["box"]),
                    "confidence": float(ball["confidence"]), "class_id": 32,
                    "scene_id": before["scene_id"], "state": "MEASURED",
                    "proof_eligible": False, "time_authority": "ACTUAL_MEDIA_PTS",
                    "used_fallback": False, "cut_barrier": False,
                    "source": "LOCAL_NATIVE_DETECTOR",
                    "classification_source": "LOCAL_NATIVE_CLASS32_DETECTOR",
                    "model_sha256": model_sha256})
            if len(qualified) > MAX_BALLS_PER_FRAME:
                return {**packet, "reason": "NATIVE_GAP_COMPETING_BALL_BUDGET_EXCEEDED"}
            detections[ms], people_by_ms[ms] = qualified, people
            packet["rows"].append({"media_ms": ms, "time_authority": "ACTUAL_MEDIA_PTS",
                "source_bgr_pixel_sha256": native._sha(image),
                "raw_class32_candidate_count": len(balls),
                "qualified_ball_count": len(qualified), "qualified_balls": qualified})
        except Exception:
            return {**packet, "reason": "NATIVE_GAP_DETECTION_FAILED"}
    for ms in times[1:]:
        exclude = [p["box"] for p in people_by_ms[ms]+people_by_ms[ref_ms]
                   if isinstance(p, dict) and isinstance(p.get("box"), dict)
                   and all(native.number(p["box"].get(k)) for k in ("x", "y", "w", "h"))]
        exclude += [r["box"] for r in detections[ms]+detections[ref_ms]]
        try:
            matrix, reason = camera_estimator(cv2.cvtColor(images_by_ms[ms], cv2.COLOR_BGR2GRAY),
                ref_gray, [(b["x"]*w,b["y"]*h,b["w"]*w,b["h"]*h) for b in exclude])
            if matrix is None:
                return {**packet, "reason": "NATIVE_GAP_BACKGROUND_CAMERA_UNMEASURED"}
            matrix = np.asarray(matrix, dtype=float)
            if matrix.shape != (2,3) or not np.isfinite(matrix).all():
                return {**packet, "reason": "NATIVE_GAP_BACKGROUND_CAMERA_INVALID"}
            packet["camera_alignments"][str(ms)] = {
                "status":"MEASURED","reference_media_ms":ref_ms,
                "affine_to_reference":matrix.tolist(),"measurement_reason":str(reason)}
            for r in detections[ms]:
                r["camera_alignment"] = {"status":"MEASURED","reference_media_ms":ref_ms,
                    "affine_to_reference":matrix.tolist(),"measurement_reason":str(reason)}
                if native._reference_center(r,w,h) is None:
                    return {**packet, "reason": "NATIVE_GAP_BACKGROUND_CAMERA_INVALID"}
        except Exception:
            return {**packet, "reason": "NATIVE_GAP_BACKGROUND_CAMERA_INVALID"}
    paths = []
    for ms in times[1:]:
        candidates = []
        for r in detections[ms]:
            center = native._reference_center(r,w,h)
            matches = [i for i,path in enumerate(paths)
                if 0 < ms-path[-1]["media_ms"] <= 120 and math.dist(center,
                    native._reference_center(path[-1],w,h)) <= MAX_GAP_ASSOCIATION_DIAMETERS*max(
                        r["box"]["w"]*w,r["box"]["h"]*h)]
            candidates.append((r,matches))
        claimed = [i for _r, matches in candidates for i in matches]
        for r,matches in candidates:
            if len(matches)>1 or (matches and claimed.count(matches[0])>1):
                return {**packet, "reason": "NATIVE_GAP_BALL_ASSOCIATION_AMBIGUOUS"}
            if matches: paths[matches[0]].append(r)
            else: paths.append([r])
    complete = []
    for i,path in enumerate(paths):
        candidate = {"track_id":f"native-gap-{i}","observations":path}
        if len(path) >= native.MIN_AFTER_SAMPLES and path[-1]["media_ms"]-path[0]["media_ms"] >= native.MIN_AFTER_SPAN_MS:
            center = native._reference_center(path[0],w,h)
            diameter = max(path[0]["box"]["w"]*w,path[0]["box"]["h"]*h)
            priors = [r for r in detections[ref_ms] if math.dist(center, (
                (r["box"]["x"]+r["box"]["w"]/2)*w,
                (r["box"]["y"]+r["box"]["h"]/2)*h)) <= diameter*.5]
            if len(priors)==1: candidate["before_observation"]=priors[0]
            complete.append(candidate)
    # Keep every competing complete/partial path in each time-overlap check.
    # A short or unclassified alternative never becomes a verified reserve.
    for candidate in complete:
        first,last = candidate["observations"][0]["media_ms"],candidate["observations"][-1]["media_ms"]
        overlapping = [c for i,p in enumerate(paths) if p[0]["media_ms"] <= last and p[-1]["media_ms"] >= first
                       for c in [{"track_id":f"native-gap-{i}","observations":[r for r in p if first<=r["media_ms"]<=last]}]]
        for c in overlapping:
            original = next((p for p in complete if p["track_id"]==c["track_id"]),None)
            if original and "before_observation" in original:c["before_observation"]=original["before_observation"]
        check = native.measure_native_link(before, overlapping, images_by_ms,video_sha256=video_sha256)
        packet["candidate_identity_checks"].append({"candidate_track_id":candidate["track_id"],"check":check})
    packet["sample_count"] = len(times)
    packet["reason"] = "NATIVE_GAP_SEARCH_COMPLETE_GOAL_GEOMETRY_STILL_REQUIRED"
    return packet


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
