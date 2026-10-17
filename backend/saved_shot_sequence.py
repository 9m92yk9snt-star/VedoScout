"""Keep one source-video save observation; detail boxes are optional audit data.

Selected-person identity is resolved once by the shared actor resolver. This
adapter retains explicit ball/actor contradictions, without demanding native
keeper tracks, four ball detections or pixel-distance recertification.
"""
from copy import deepcopy
import math


def _rows(value):
    return value if isinstance(value, list) else []


def _box(value):
    if not isinstance(value, dict):
        return None
    try:
        result = {k: float(value[k]) for k in ("x", "y", "w", "h")}
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return result if (all(math.isfinite(v) for v in result.values())
        and all(-.05 <= result[k] <= 1.05 for k in ("x", "y"))
        and all(0 < result[k] <= 1.1 for k in ("w", "h"))) else None


def _mapped_box(box, region, convert):
    if _box(box) is None or not isinstance(region.get("source_roi"), dict):
        return None
    try:
        return _box(convert(box, region["source_roi"]))
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        return None


def connect(actions, frames, times, manifest, to_source_box):
    """Source-bound observations can qualify without duplicate physical proof.

    A complete video-reported SAVED outcome does not need an extra stage form.
    Explicit stage observations can also resolve UNKNOWN, without exact boxes.
    Different active balls, a known spare, a different shooter, or a later
    observed contact remain contradictions requiring a focused correction.
    """
    result = deepcopy(actions) if isinstance(actions, list) else []
    frames, manifest = _rows(frames), _rows(manifest)
    by_index = {r["idx"]: r for r in frames if isinstance(r, dict) and type(r.get("idx")) is int}
    clock_valid = (isinstance(times, list) and len(times) == len(manifest) and len(times) >= 2
        and all(type(ms) is int for ms in times) and all(a < b for a, b in zip(times, times[1:]))
        and all(isinstance(r, dict) and r.get("media_ms") == ms for r, ms in zip(manifest, times)))

    def at(index):
        return times[index-1] if clock_valid and type(index) is int and 1 <= index <= len(times) else None

    for action in result:
        if not isinstance(action, dict):
            continue
        action.pop("save_sequence_evidence", None)
        sequence = action.get("save_sequence")
        if action.get("kind") != "SHOT" or not isinstance(sequence, dict):
            continue
        indices = [action.get("contact_idx"), sequence.get("incoming_idx"),
                   sequence.get("keeper_idx"), sequence.get("aftermath_idx")]
        ball_id = sequence.get("ball_id")
        reasons, stages, later_controls = [], [], []
        ordered = all(at(i) is not None for i in indices) and indices[0] <= indices[1] < indices[2] < indices[3]
        if not clock_valid or any(i is not None and at(i) is None for i in indices) or (
                all(at(i) is not None for i in indices) and not ordered):
            reasons.append("INVALID_SOURCE_STAGE_ORDER")
        if sequence.get("same_active_ball") is False:
            reasons.append("DIFFERENT_ACTIVE_BALL")
        if sequence.get("keeper_intervention_visible") is False:
            reasons.append("KEEPER_INTERVENTION_NOT_VISIBLE")
        if isinstance(ball_id, str) and any(b.get("ball_id") == ball_id and b.get("stationary_spare") is True
                for row in frames if isinstance(row, dict) for b in _rows(row.get("balls")) if isinstance(b, dict)):
            reasons.append("ACTIVE_ID_ALSO_IDENTIFIES_SPARE")
        if at(indices[0]) is not None and at(indices[2]) is not None:
            for index, row in by_index.items():
                if indices[0] < index < indices[2] and at(index) is not None and any(
                        isinstance(b, dict) and isinstance(ball_id, str) and b.get("ball_id") == ball_id
                        and b.get("active_ball") is True and b.get("control_visible") is True
                        for b in _rows(row.get("balls"))):
                    later_controls.append(index)
            if later_controls:
                reasons.append("LATER_VISIBLE_CONTROL_BEFORE_KEEPER")
        for phase, index in zip(("STRIKE", "INCOMING", "KEEPER_INTERVENTION", "AFTERMATH"), indices):
            if at(index) is None:
                continue
            balls = [b for b in _rows(by_index.get(index, {}).get("balls")) if isinstance(b, dict)]
            active = [b for b in balls if b.get("active_ball") is True and b.get("stationary_spare") is not True]
            matching = [b for b in active if isinstance(ball_id, str) and b.get("ball_id") == ball_id]
            if isinstance(ball_id, str) and active and not matching:
                reasons.append("DIFFERENT_ACTIVE_BALL")
            ball = matching[0] if matching else {}
            if phase == "STRIKE" and ball.get("control_visible") is True:
                labels = [r.get("body_id") for r in _rows(action.get("actor_observations"))
                          if isinstance(r, dict) and r.get("idx") == index] or [action.get("actor_body_id")]
                if ball.get("control_body_id") is not None and ball["control_body_id"] not in labels:
                    reasons.append("DIFFERENT_SHOOTER_CONTROL")
            stages.append({"phase": phase, "idx": index, "media_ms": at(index), "ball_id": ball_id,
                           "source_box": _mapped_box(ball.get("box"), manifest[index-1], to_source_box)})
        audit = {"authority": "TEMPORAL_VIDEO_OBSERVATION", "physical_certificate": False,
            "status": "INCOMPLETE", "reasons": sorted(set(reasons)), "stages": stages,
            "later_visible_control_indices": sorted(set(later_controls))}
        action["save_sequence_evidence"] = audit
        if reasons:
            action["outcome_visible"] = False
            continue
        reported = action.get("outcome") == "SAVED" and action.get("outcome_visible") is True
        observed = (ordered and isinstance(ball_id, str) and bool(ball_id)
            and sequence.get("same_active_ball") is True and sequence.get("keeper_intervention_visible") is True
            and sequence.get("aftermath") in ("DEFLECTED_AWAY", "HELD"))
        if action.get("continuous_visible_sequence") is not True or not (reported or observed):
            action["outcome_visible"] = False
            continue
        if action.get("outcome") not in (None, "UNKNOWN", "SAVED"):
            audit["status"] = "CONFLICTING_OUTCOME"
            action["outcome_visible"] = False
            continue
        audit.update(status="OBSERVED", aftermath=sequence.get("aftermath"), ball_id=ball_id)
        if at(indices[2]) is not None:
            region = manifest[indices[2]-1]
            keeper = next((b for b in _rows(region.get("source_bodies")) if isinstance(b, dict)
                           and b.get("body_id") == sequence.get("keeper_body_id")), {})
            keeper_box = _box(keeper.get("box")) or _mapped_box(sequence.get("keeper_box"), region, to_source_box)
            audit.update(keeper_local_track_id=keeper.get("local_track_id"), keeper_observation={
                "idx": indices[2], "media_ms": at(indices[2]), "source_box": keeper_box,
                "source": "MEASURED_LOCAL_BODY" if keeper else "SOURCE_VIDEO_VISIBLE_BODY"})
        if observed:
            action.update(outcome="SAVED", outcome_visible=True, outcome_idx=indices[3],
                          outcome_evidence_indices=sorted(set(indices)))
    return result
