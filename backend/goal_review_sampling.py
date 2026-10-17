"""Inspect a native ball-path loss; sampling itself has no proof authority."""
from copy import deepcopy
import math

import ball_trajectory

NATIVE_REAPPEARANCE_HORIZON_MS = 900
MAX_NATIVE_REAPPEARANCE_FRAMES = 56
MAX_DENSE_READER_FRAMES = 64


def has_contact_reference(strike, window):
    """The geometry adapter cannot bind a contact without its measured ball.

    Skip that dead-end request before decoding or spending a model budget.
    Legacy geometry-only callers without a physical status remain supported.
    """
    if strike.get("status") not in {"VERIFIED_PHYSICAL_RELEASE", "VERIFIED_PHYSICAL_SCORING_CONTACT"}:
        return True
    anchor = strike.get("active_ball_anchor") or {}
    return bool(ball_trajectory._proof_measured_ball(anchor)
                and type(anchor.get("media_ms")) is int
                and anchor.get("time_authority") == "ACTUAL_MEDIA_PTS"
                and not anchor.get("used_fallback")
                and window.get("start_ms", 0) <= anchor["media_ms"] <= window.get("end_ms", float("inf")))


def dense_reader_times(original, strike, path, scan, images_by_ms, *, budget, start_ms, end_ms):
    """Retain a complete, already decoded short loss in one reader call.

    Sparse uniform sampling cannot reliably observe a 100 ms reappearance.
    This plan has search authority only and never uses an expected goal time.
    Return None when complete native coverage cannot fit or bind to pixels.
    """
    import hashlib
    import numpy as np
    valid = contact_bound_native_path(strike, path)
    if (valid is None or not isinstance(original, list) or not original
            or any(type(ms) is not int for ms in original)
            or type(start_ms) is not int or type(end_ms) is not int
            or not 0 <= start_ms <= end_ms
            or type(budget) is not int or not 1 <= budget <= MAX_DENSE_READER_FRAMES
            or not isinstance(images_by_ms, dict) or not isinstance(scan, dict)
            or scan.get('source') != 'BOUNDED_NATIVE_GOAL_GAP_INSPECTION'
            or scan.get('status') != 'SEARCH_ONLY' or scan.get('proof_eligible') is not False
            or scan.get('canonical_events_applied') != 0
            or scan.get('reason') != 'NATIVE_GAP_SEARCH_COMPLETE_GOAL_GEOMETRY_STILL_REQUIRED'):
        return None
    rows = scan.get('rows')
    if (not isinstance(rows, list) or not 2 <= len(rows) <= MAX_NATIVE_REAPPEARANCE_FRAMES
            or scan.get('sample_count') != len(rows)):
        return None
    times = [r.get('media_ms') if isinstance(r, dict) else None for r in rows]
    first = valid['rows'][-1]['media_ms']
    if (any(type(ms) is not int or not start_ms <= ms <= end_ms for ms in times)
            or times != sorted(set(times)) or times[0] != first
            or times[-1] > first + NATIVE_REAPPEARANCE_HORIZON_MS
            or any(b-a > 35 for a,b in zip(times,times[1:]))):
        return None
    dims = scan.get('native_frame_dimensions')
    if (not isinstance(dims, dict)
            or any(type(dims.get(k)) is not int or dims[k] <= 0 for k in ('width','height'))):
        return None
    for ms, row in zip(times, rows):
        image = images_by_ms.get(ms)
        if (row.get('time_authority') != 'ACTUAL_MEDIA_PTS'
                or not isinstance(image, np.ndarray) or image.dtype != np.uint8
                or image.shape != (dims['height'], dims['width'], 3)
                or hashlib.sha256(image.tobytes()).hexdigest() != row.get('source_bgr_pixel_sha256')):
            return None
    selected = set(times) | {original[0], original[-1], strike['media_ms'], valid['seed_ms']}
    selected.update(r['media_ms'] for r in valid['rows'][-6:])
    if (len(selected) > budget or any(not start_ms <= ms <= end_ms or ms not in images_by_ms for ms in selected)):
        return None
    return sorted(selected)


def refocus_reader_times(original,strike,path,appearance,*,budget,start_ms,end_ms):
    """Use unclassified local candidates to inspect pixels, never to label events."""
    if (not isinstance(original,list) or not original
            or any(type(ms) is not int for ms in original)
            or type(start_ms) is not int or type(end_ms) is not int or not 0<=start_ms<=end_ms):
        return list(original) if isinstance(original,list) else []
    valid=contact_bound_native_path(strike,path)
    if (valid is None or not isinstance(appearance,dict)
            or appearance.get('source')!='TEMPORAL_NATIVE_APPEARANCE_SEARCH'
            or appearance.get('status')!='SEARCH_ONLY' or appearance.get('proof_eligible') is not False
            or appearance.get('canonical_events_applied')!=0 or type(budget) is not int or budget<=0):
        return list(original)
    suggestions=appearance.get('suggested_review_ms')
    if (not isinstance(suggestions,list) or not suggestions or len(suggestions)>6
            or any(type(ms) is not int or not start_ms<=ms<=end_ms for ms in suggestions)
            or any(not valid['rows'][-1]['media_ms']<ms<=valid['rows'][-1]['media_ms']+NATIVE_REAPPEARANCE_HORIZON_MS
                   for ms in suggestions)):
        return list(original)
    # A before/after comparison needs the last three independently measured
    # before positions. Retaining only the last one would make the airborne
    # depth audit impossible once appearance candidates replace reader slots.
    protected={original[0],original[-1],strike['media_ms'],valid['seed_ms']}
    protected.update(row['media_ms'] for row in valid['rows'][-3:])
    if any(not start_ms<=ms<=end_ms for ms in protected):return list(original)
    if len(protected)>budget:return list(original)
    selected=set(protected)
    # Appearance proposals are unclassified. Keep temporal coverage from the
    # original plan even when two noisy tracks propose all six extra images.
    # Otherwise a true short reappearance can disappear from the reader input.
    baseline_slots=min(3,len(set(original)-protected))
    suggestion_slots=max(0,budget-len(protected)-baseline_slots)
    for ms in suggestions[:suggestion_slots]:
        selected.add(ms)
    remaining=set(original)-selected
    while remaining and len(selected)<budget:
        ms=max(remaining,key=lambda ms:(min(abs(ms-p) for p in selected),-ms))
        selected.add(ms);remaining.remove(ms)
    return sorted(selected)


def native_reappearance_times(strike, path, *, start_ms, end_ms):
    """Inspect a short loss at about native 60 fps without more reader images.

    The existing twelve-image reader budget can sample only one frame of a
    100 ms reappearance. Local decoding/detection uses a separate bounded plan;
    none of its requested times has proof or event authority.
    """
    valid = contact_bound_native_path(strike, path)
    if (valid is None or type(start_ms) is not int or type(end_ms) is not int
            or not 0 <= start_ms <= end_ms):
        return []
    return native_gap_times(valid["rows"][-1]["media_ms"],start_ms=start_ms,end_ms=end_ms)


def native_gap_times(last_visible_ms, *, start_ms, end_ms):
    """Time planning only; callers must independently validate the ball path."""
    if (type(last_visible_ms) is not int or type(start_ms) is not int or type(end_ms) is not int
            or not 0<=start_ms<=end_ms):
        return []
    first = last_visible_ms
    if not start_ms <= first < end_ms:
        return []
    last = min(first + NATIVE_REAPPEARANCE_HORIZON_MS, end_ms)
    intervals = min(MAX_NATIVE_REAPPEARANCE_FRAMES - 1,
                    max(1, math.ceil((last-first) / (1000/60))))
    return sorted({first + round((last-first)*i/intervals)
                   for i in range(intervals+1)})


def contact_bound_native_path(strike, path):
    """Copy only an exact, independently contact-bound native measured path.

    The orchestrator supplies its current shot track. Global tracks, saved
    search proposals and unbound/rejected anchors cannot choose review focus.
    This does not certify a goal, bridge a gap or create a ball measurement.
    """
    if not isinstance(strike, dict) or not isinstance(path, dict):
        return None
    anchor = strike.get("active_ball_anchor")
    binding = path.get("contact_binding")
    rows = path.get("rows")
    if (strike.get("status") not in {"VERIFIED_PHYSICAL_RELEASE", "VERIFIED_PHYSICAL_SCORING_CONTACT"}
            or strike.get("proof_eligible") is not True or type(strike.get("media_ms")) is not int
            or path.get("source") != "VERIFIED_RELEASE_ANCHOR"
            or not isinstance(anchor, dict) or not ball_trajectory._proof_measured_ball(anchor)
            or anchor.get("identity_rejection") is not None or anchor.get("remote_spare_ball_used") is not False
            or type(anchor.get("media_ms")) is not int or path.get("seed_ms") != anchor["media_ms"]
            or not isinstance(binding, dict) or binding.get("status") != "VERIFIED"
            or binding.get("reason") != "MEASURED_CONTACT_TO_EXACT_RELEASE_ANCHOR"
            or binding.get("contact_ms") != strike["media_ms"] or binding.get("seed_ms") != anchor["media_ms"]
            or not 0 <= anchor["media_ms"] - strike["media_ms"] <= ball_trajectory.CONTACT_RELEASE_MAX_MS
            or not isinstance(rows, list) or len(rows) < 2):
        return None
    scene = strike.get("scene_id")
    if not isinstance(scene, str) or anchor.get("scene_id") != scene:
        return None
    previous_ms = None
    for row in rows:
        dims = row.get("frame_dimensions") if isinstance(row, dict) else None
        if (not ball_trajectory._proof_measured_ball(row) or type(row.get("media_ms")) is not int
                or row.get("scene_id") != scene or row.get("support_only") is True
                or row.get("provenance") != "RELEASE_ANCHORED_NATIVE_CAMERA_MOTION"
                or not isinstance(dims, dict) or dims.get("source") != "DECODED_NATIVE_PIXELS"
                or any(type(dims.get(k)) is not int or dims[k] <= 0 for k in ("width", "height"))
                or not isinstance(row.get("confidence"), (int, float)) or isinstance(row["confidence"], bool)
                or not math.isfinite(row["confidence"])
                or not ball_trajectory.RELEASE_REACQUIRE_MIN_CONFIDENCE <= row["confidence"] <= 1
                or previous_ms is not None and not 0 < row["media_ms"] - previous_ms <= ball_trajectory.RELEASE_MAX_MEASURED_GAP_MS):
            return None
        previous_ms = row["media_ms"]
    if rows[0]["media_ms"] != anchor["media_ms"] or rows[0]["box"] != anchor["box"]:
        return None
    return deepcopy(path)


def provider_strike(job):
    """Bind the current job path on normal and feedback provider calls alike."""
    strike = deepcopy(job["strike"])
    strike.pop("_goal_review_ball_path", None)
    strike.pop("_sequence_context", None)
    if isinstance(job.get("sequence_context"), dict):
        strike["_sequence_context"] = deepcopy(job["sequence_context"])
    path = contact_bound_native_path(strike, job.get("shot_track"))
    if path is not None:
        strike["_goal_review_ball_path"] = path
    return strike
