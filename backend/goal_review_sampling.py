"""Inspect a native ball-path loss; sampling itself has no proof authority."""
from copy import deepcopy
import math

import ball_trajectory


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
    path = contact_bound_native_path(strike, job.get("shot_track"))
    if path is not None:
        strike["_goal_review_ball_path"] = path
    return strike
