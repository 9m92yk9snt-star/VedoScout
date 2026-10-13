"""Local ball reidentification across a bounded body occlusion.

Compares native pixels after independent ball detections exist on both sides.
User circles and appearance-only optical flow are search hints, not classified
ball measurements. This module cannot create an event or make a model API call.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import math
import re

VERSION = 1
SOURCE = "LOCAL_NATIVE_BALL_REIDENTIFICATION"
METHOD = "CLASSIFIED_APPEARANCE_CAMERA_MOTION"
MAX_GAP_MS = 900
MIN_AFTER_SAMPLES = 3
MIN_AFTER_SPAN_MS = 80
MIN_BALL_CONFIDENCE = 0.25
MIN_SIMILARITY = 0.90
MIN_ALTERNATIVE_MARGIN = 0.12
MIN_MOTION_DIAMETERS = 0.75
MIN_INTERIOR_STD = 8.
_SHA = re.compile(r"^[0-9a-f]{64}$")


def number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def box_ok(box):
    if not isinstance(box, dict) or not all(number(box.get(k)) for k in ("x", "y", "w", "h")):
        return False
    x, y, w, h = (float(box[k]) for k in ("x", "y", "w", "h"))
    return 0 <= x < 1 and 0 <= y < 1 and 0 < w < .2 and 0 < h < .2 and x+w <= 1 and y+h <= 1


def _crop(frame, box):
    import numpy as np
    if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
        return None
    if not box_ok(box):
        return None
    h, w = frame.shape[:2]
    x0, y0 = math.floor(box["x"]*w), math.floor(box["y"]*h)
    x1, y1 = math.ceil((box["x"]+box["w"])*w), math.ceil((box["y"]+box["h"])*h)
    patch = frame[y0:y1, x0:x1]
    return patch if min(patch.shape[:2]) >= 4 else None


def _descriptor(patch):
    """Deterministic interior descriptor; no surrounding body pixels."""
    import cv2
    import numpy as np
    p = cv2.resize(patch, (24, 24), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(p, cv2.COLOR_BGR2HSV)
    yy, xx = np.mgrid[:24, :24]
    mask = (((xx-11.5)**2+(yy-11.5)**2) <= 10.5**2).astype(np.uint8)
    hue = cv2.calcHist([hsv], [0], mask, [12], [0, 180]).ravel()
    saturation = cv2.calcHist([hsv], [1], mask, [8], [0, 256]).ravel()
    gray = cv2.cvtColor(p, cv2.COLOR_BGR2GRAY).astype(np.float32)
    interior = gray[mask.astype(bool)]
    if float(interior.std()) < MIN_INTERIOR_STD:
        return None
    normal = np.clip((gray-float(interior.mean()))/max(float(interior.std()), 12), -3, 3)
    normal[mask == 0] = 0
    texture = cv2.resize(normal, (8, 8), interpolation=cv2.INTER_AREA).ravel()
    parts = []
    for v in (hue, saturation, texture):
        parts.append(v/max(float(np.linalg.norm(v)), 1e-9))
    vector = np.concatenate(parts)
    return vector/max(float(np.linalg.norm(vector)), 1e-9)


def _sha(patch):
    return hashlib.sha256(patch.tobytes()).hexdigest()


def _verified_time(row):
    return (
        isinstance(row, dict) and type(row.get("media_ms")) is int
        and row["media_ms"] >= 0 and row.get("time_authority") == "ACTUAL_MEDIA_PTS"
        and row.get("used_fallback") is not True and row.get("cut_barrier") is not True
        and row.get("cut") is not True and row.get("support_only") is not True
        and row.get("source") not in {"USER_ANNOTATION", "USER_OBSERVATION", "SEARCH_HINT"}
    )


def _reference_center(row, width, height):
    """Apply a measured affine, not a guessed camera correction."""
    transform = row.get("camera_alignment")
    if not isinstance(transform, dict) or transform.get("status") != "MEASURED":
        return None
    matrix = transform.get("affine_to_reference")
    if (not isinstance(matrix, (list, tuple)) or len(matrix) != 2
            or any(not isinstance(r, (list, tuple)) or len(r) != 3 for r in matrix)
            or not all(number(v) for r in matrix for v in r)):
        return None
    # A singular/reflected affine can make any moving object look stationary.
    import numpy as np
    linear = np.asarray(matrix, dtype=float)[:, :2]
    scales = np.linalg.svd(linear, compute_uv=False)
    if np.linalg.det(linear) <= 0 or scales.min() < .5 or scales.max() > 2:
        return None
    x = (row["box"]["x"]+row["box"]["w"]/2)*width
    y = (row["box"]["y"]+row["box"]["h"]/2)*height
    return [matrix[0][0]*x+matrix[0][1]*y+matrix[0][2],
            matrix[1][0]*x+matrix[1][1]*y+matrix[1][2]]


def _classified(row, scene_id):
    if (isinstance(row,dict) and row.get('classification_source')=='INDEPENDENT_MULTI_FRAME_IMAGE_BALL_CLASSIFICATION'):
        import independent_ball_review
        return bool(_verified_time(row) and box_ok(row.get('box')) and row.get('scene_id')==scene_id
                    and type(row.get('class_id')) is int and row['class_id']==32
                    and independent_ball_review.classified(row))
    return (
        _verified_time(row) and box_ok(row.get("box"))
        and type(row.get("class_id")) is int and row["class_id"] == 32
        and number(row.get("confidence")) and MIN_BALL_CONFIDENCE <= row["confidence"] <= 1
        and row.get("scene_id") == scene_id
        and row.get("classification_source") == "LOCAL_NATIVE_CLASS32_DETECTOR"
        and isinstance(row.get("model_sha256"), str) and bool(_SHA.fullmatch(row["model_sha256"]))
    )


def _preexisting_stationary(candidate, before, frame, centers, diameter):
    """A stopped active ball is not a reserve: measure its earlier presence."""
    import numpy as np
    row = candidate.get("before_observation")
    if not _classified(row, before["scene_id"]) or row["media_ms"] != before["media_ms"]:
        return None
    crop = _crop(frame, row["box"])
    if (row.get('classification_source')=='INDEPENDENT_MULTI_FRAME_IMAGE_BALL_CLASSIFICATION'
            and crop is not None and row.get('native_pixel_sha256')!=_sha(crop)):
        return None
    desc = _descriptor(crop) if crop is not None else None
    if desc is None:
        return None
    h, w = frame.shape[:2]
    center = [(row["box"]["x"]+row["box"]["w"]/2)*w,
              (row["box"]["y"]+row["box"]["h"]/2)*h]
    active = [(before["box"]["x"]+before["box"]["w"]/2)*w,
              (before["box"]["y"]+before["box"]["h"]/2)*h]
    if (math.dist(center, active) <= diameter
            or max(math.dist(center, p) for p in centers) > diameter*.5):
        return None
    return {"before_observation": deepcopy(row), "before_crop_sha256": _sha(crop),
            "before_reference_center": center, "before_descriptor": desc}


def measure_native_link(before, candidates, frames_by_ms, *, video_sha256,reference_history=()):
    """Measure identity, not a goal label; fail closed on spare-ball ambiguity.

    The before row is an already proof-eligible contact-bound ball. Candidate
    paths contain fresh classified class-32 observations and measured camera
    transforms to the same before-frame coordinates.
    """
    import numpy as np
    unresolved = {"status": "UNRESOLVED", "source": SOURCE, "method": METHOD,
                  "proof_eligible": False, "reason": "NATIVE_REAPPEARANCE_LINK_NOT_PROVEN"}
    if not isinstance(frames_by_ms, dict) or not isinstance(candidates, list):
        return {**unresolved, "reason": "NATIVE_CANDIDATE_INPUT_INVALID"}
    if not (
        _verified_time(before) and before.get("state") == "MEASURED"
        and before.get("proof_eligible") is True and box_ok(before.get("box"))
        and isinstance(before.get("scene_id"), str) and bool(before["scene_id"])
        and isinstance(video_sha256, str) and _SHA.fullmatch(video_sha256)
    ):
        return {**unresolved, "reason": "CONTACT_BOUND_NATIVE_BALL_REFERENCE_MISSING"}
    patch = _crop(frames_by_ms.get(before["media_ms"]), before["box"])
    if patch is None:
        return {**unresolved, "reason": "NATIVE_REFERENCE_PIXELS_MISSING"}
    ref = _descriptor(patch)
    if ref is None:
        return {**unresolved, "reason": "NATIVE_REFERENCE_APPEARANCE_UNINFORMATIVE"}
    references=[ref];history_hashes=[]
    for entry in list(reference_history or ())[:6]:
        if not isinstance(entry,(tuple,list)) or len(entry)!=2:continue
        row,image=entry
        if (not _verified_time(row) or row.get('state')!='MEASURED' or row.get('proof_eligible') is not True
                or row.get('scene_id')!=before['scene_id'] or not before['media_ms']-500<=row['media_ms']<before['media_ms']):continue
        p=_crop(image,row.get('box'));v=_descriptor(p) if p is not None else None
        if v is not None:references.append(v);history_hashes.append({'media_ms':row['media_ms'],'crop_sha256':_sha(p)})
    ranked, stationary, rejected = [], [], []
    seen_tracks = set()
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            rejected.append({"track_id": None, "reason": "CANDIDATE_PATH_INCOMPLETE"})
            continue
        track = candidate.get("track_id")
        rows = candidate.get("observations")
        if (not isinstance(track, str) or not track or track in seen_tracks
                or not isinstance(rows, list) or len(rows) < MIN_AFTER_SAMPLES):
            rejected.append({"track_id": track, "reason": "CANDIDATE_PATH_INCOMPLETE"})
            continue
        seen_tracks.add(track)
        if any(not _classified(row, before["scene_id"]) for row in rows):
            rejected.append({"track_id": track, "reason": "INDEPENDENT_BALL_CLASSIFICATION_MISSING"})
            continue
        times = [row["media_ms"] for row in rows]
        if (any(a >= b or b-a > 120 for a, b in zip(times, times[1:]))
                or not 0 < times[0]-before["media_ms"] <= MAX_GAP_MS
                or times[-1]-times[0] < MIN_AFTER_SPAN_MS):
            rejected.append({"track_id": track, "reason": "CANDIDATE_TIME_COVERAGE_INVALID"})
            continue
        similarities, descriptors, hashes, centers, diameters = [], [], [], [], []
        for row in rows:
            frame = frames_by_ms.get(row["media_ms"])
            crop = _crop(frame, row["box"])
            if crop is None:
                break
            if (row.get('classification_source')=='INDEPENDENT_MULTI_FRAME_IMAGE_BALL_CLASSIFICATION'
                    and row.get('native_pixel_sha256')!=_sha(crop)):
                break
            alignment = row.get("camera_alignment", {})
            if not isinstance(alignment, dict) or alignment.get("reference_media_ms") != before["media_ms"]:
                break
            h, w = frame.shape[:2]
            center = _reference_center(row, w, h)
            if center is None:
                break
            desc = _descriptor(crop)
            if desc is None:
                break
            visual=row.get('classification_source')=='INDEPENDENT_MULTI_FRAME_IMAGE_BALL_CLASSIFICATION'
            similarities.append(max(float(np.clip(np.dot(r,desc),-1.,1.)) for r in references)
                                if visual else float(np.clip(np.dot(ref, desc), -1., 1.)))
            descriptors.append(desc)
            hashes.append(_sha(crop))
            centers.append(center)
            diameters.append(max(row["box"]["w"]*w, row["box"]["h"]*h))
        if len(centers) != len(rows):
            rejected.append({"track_id": track, "reason": "NATIVE_PIXELS_OR_CAMERA_ALIGNMENT_MISSING"})
            continue
        displacement = max(math.hypot(p[0]-centers[0][0], p[1]-centers[0][1]) for p in centers)
        diameter = float(np.median(diameters))
        motion = displacement/max(diameter, 1)
        item = {"track_id": track, "similarity": float(np.median(similarities)),
                "motion_diameters": motion, "rows": deepcopy(rows),
                "crop_sha256": hashes, "reference_centers": centers}
        if motion < MIN_MOTION_DIAMETERS:
            prior = _preexisting_stationary(candidate, before, frames_by_ms[before["media_ms"]], centers, diameter)
            if prior is not None:
                persistence = float(np.median([np.clip(np.dot(prior["before_descriptor"], d), -1, 1)
                                               for d in descriptors]))
            else:
                persistence = 0.
            if prior is not None and persistence >= MIN_SIMILARITY:
                prior.pop("before_descriptor")
                stationary.append({"track_id": track, "motion_diameters": motion,
                                   "reason": "CLASSIFIED_PREEXISTING_STATIONARY_BALL",
                                   "persistence_similarity": persistence, **prior})
            else:
                stationary.append({"track_id": track, "motion_diameters": motion,
                                   "reason": "STATIONARY_CANDIDATE_NOT_PROVEN_PREEXISTING"})
                rejected.append({"track_id": track, "reason": "STATIONARY_BALL_IDENTITY_UNRESOLVED"})
        else:
            ranked.append(item)
    ranked.sort(key=lambda p: (-p["similarity"], p["track_id"]))
    if not ranked:
        return {**unresolved, "reason": "NO_CLASSIFIED_MOVING_REAPPEARANCE",
                "stationary_ball_controls": stationary, "rejected_candidates": rejected}
    best = ranked[0]
    alternative = ranked[1]["similarity"] if len(ranked) > 1 else 0.
    if best["similarity"] < MIN_SIMILARITY or best["similarity"]-alternative < MIN_ALTERNATIVE_MARGIN:
        return {**unresolved, "reason": "NATIVE_BALL_APPEARANCE_AMBIGUOUS",
                "best_similarity": best["similarity"], "alternative_similarity": alternative,
                "stationary_ball_controls": stationary, "rejected_candidates": rejected}
    if rejected:
        return {**unresolved, "reason": "ALTERNATIVE_BALL_PATH_COVERAGE_UNRESOLVED",
                "stationary_ball_controls": stationary, "rejected_candidates": rejected}
    return {
        "status": "VERIFIED_SAME_BALL", "source": SOURCE, "method": METHOD,
        "proof_eligible": True, "source_video_sha256": video_sha256,
        "before_media_ms": before["media_ms"], "before_box": deepcopy(before["box"]),
        "scene_id": before["scene_id"],
        "before_crop_sha256": _sha(patch), "after_track_id": best["track_id"],
        "after_observations": best["rows"], "after_crop_sha256": best["crop_sha256"],
        "after_reference_centers": best["reference_centers"],
        "appearance_similarity": best["similarity"], "alternative_similarity": alternative,
        "appearance_margin": best["similarity"]-alternative,
        "motion_diameters": best["motion_diameters"],
        "stationary_ball_controls": stationary, "rejected_candidates": [],
        "reference_history":history_hashes,
        "reason": "CLASSIFIED_MOVING_BALL_MATCHES_CONTACT_BOUND_NATIVE_APPEARANCE",
    }
