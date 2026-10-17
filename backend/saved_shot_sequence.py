"""Bind visible shot/save stages to source pixels in the existing video read.

These remain model observations, not native measurements or a second event
authority. The shared resolver still establishes player identity and continuity.
No reference times, player numbers or expected outcomes are inputs.
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
    if (not all(math.isfinite(v) for v in result.values())
            or not all(-.05 <= result[k] <= 1.05 for k in ("x", "y"))
            or not all(0 < result[k] <= 1.1 for k in ("w", "h"))):
        return None
    return result


def _mapped_box(box, region, convert):
    if _box(box) is None or not isinstance(region.get("source_roi"), dict):
        return None
    try:
        return _box(convert(box, region["source_roi"]))
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        return None


def _body(region, label):
    matches = [b for b in _rows(region.get("source_bodies")) if isinstance(b, dict)
               and isinstance(label, str) and b.get("body_id") == label
               and isinstance(b.get("local_track_id"), str) and _box(b.get("box"))]
    return {**matches[0], "box": _box(matches[0]["box"])} if len(matches) == 1 else None


def _near_body(ball, body, *, feet=False):
    x, y = ball["x"] + ball["w"]/2, ball["y"] + ball["h"]/2
    return (body["x"] - .5*body["w"] <= x <= body["x"] + 1.5*body["w"]
            and body["y"] + (.4 if feet else -.5)*body["h"] <= y <= body["y"] + 1.5*body["h"])


def connect(actions, frames, times, manifest, to_source_box):
    """One response-local active ball must connect strike, keeper and aftermath.

    Each box is mapped independently, so raw screen displacement during a pan
    is never mistaken for ball motion. A keeper missed by the native detector
    can be visibly located in the full scene without inventing a local track.
    A SAVED label alone cannot replace missing stages in a new video response.
    """
    result = deepcopy(actions) if isinstance(actions, list) else []
    frames, manifest = _rows(frames), _rows(manifest)
    by_index = {r["idx"]: r for r in frames if isinstance(r, dict) and type(r.get("idx")) is int}
    clock_valid = (isinstance(times, list) and len(times) == len(manifest) and len(times) >= 2
                   and all(type(ms) is int for ms in times)
                   and all(a < b for a, b in zip(times, times[1:]))
                   and all(isinstance(r, dict) and r.get("media_ms") == ms for r, ms in zip(manifest, times))
                   and len(by_index) == len(frames))

    def at(index):
        return times[index-1] if clock_valid and type(index) is int and 1 <= index <= len(times) else None

    for action in result:
        if not isinstance(action, dict):
            continue
        action.pop("save_sequence_evidence", None)  # Only this adapter supplies the audit.
        if action.get("kind") != "SHOT":
            continue
        sequence = action.get("save_sequence")
        if not isinstance(sequence, dict) and action.get("outcome") != "SAVED":
            continue
        sequence = sequence if isinstance(sequence, dict) else {}
        indices = [action.get("contact_idx"), sequence.get("incoming_idx"),
                   sequence.get("keeper_idx"), sequence.get("aftermath_idx")]
        ball_id = sequence.get("ball_id")
        reasons, stages, later_controls = [], [], []
        if not (all(at(i) is not None for i in indices)
                and indices[0] <= indices[1] < indices[2] < indices[3]):
            reasons.append("INVALID_SOURCE_STAGE_ORDER")
        if not (isinstance(ball_id, str) and bool(ball_id) and sequence.get("same_active_ball") is True
                and sequence.get("keeper_intervention_visible") is True
                and sequence.get("aftermath") in ("DEFLECTED_AWAY", "HELD")
                and action.get("continuous_visible_sequence") is True):
            reasons.append("SAVE_CONNECTION_NOT_VISIBLE")
        if isinstance(ball_id, str) and any(b.get("ball_id") == ball_id and b.get("stationary_spare") is True
                for row in frames if isinstance(row, dict) for b in _rows(row.get("balls")) if isinstance(b, dict)):
            reasons.append("ACTIVE_ID_ALSO_IDENTIFIES_SPARE")
        if at(indices[0]) is not None and at(indices[2]) is not None:
            for index, row in by_index.items():
                if not indices[0] < index < indices[2] or at(index) is None:
                    continue
                region = manifest[index-1]
                for ball in _rows(row.get("balls")):
                    if not (isinstance(ball, dict) and ball.get("ball_id") == ball_id
                            and ball.get("active_ball") is True and ball.get("control_visible") is True):
                        continue
                    body = _body(region, ball.get("control_body_id"))
                    box = _mapped_box(ball.get("box"), region, to_source_box)
                    if body and box and _near_body(box, body["box"], feet=True):
                        later_controls.append(index)
            if later_controls:
                reasons.append("LATER_VISIBLE_CONTROL_BEFORE_KEEPER")
        strike_ball = None
        for phase, index in zip(("STRIKE", "INCOMING", "KEEPER_INTERVENTION", "AFTERMATH"), indices):
            if at(index) is None:
                continue
            candidates = [b for b in _rows(by_index.get(index, {}).get("balls"))
                          if isinstance(b, dict) and b.get("ball_id") == ball_id]
            ball = candidates[0] if len(candidates) == 1 else {}
            box = _mapped_box(ball.get("box"), manifest[index-1], to_source_box)
            if (box is None or ball.get("active_ball") is not True or ball.get("stationary_spare") is True
                    or ball.get("confidence") not in ("high", "medium")):
                reasons.append("MISSING_" + phase + "_ACTIVE_BALL")
                continue
            stages.append({"phase": phase, "idx": index, "media_ms": at(index),
                           "ball_id": ball_id, "source_box": box})
            if phase == "STRIKE":
                strike_ball = ball
        keeper, keeper_box = None, None
        if at(indices[2]) is not None:
            region = manifest[indices[2]-1]
            keeper = _body(region, sequence.get("keeper_body_id"))
            if sequence.get("keeper_body_id") is not None and keeper is None:
                reasons.append("UNKNOWN_KEEPER_BODY_LABEL")
            keeper_box = (_box(keeper["box"]) if keeper else
                          _mapped_box(sequence.get("keeper_box"), region, to_source_box))
        intervention = next((s for s in stages if s["phase"] == "KEEPER_INTERVENTION"), None)
        if keeper_box is None or intervention is None or not _near_body(intervention["source_box"], keeper_box):
            reasons.append("KEEPER_BALL_INTERVENTION_UNBOUND")
        if strike_ball:
            actor_rows = action.get("actor_observations")
            labels = ([r.get("body_id") for r in actor_rows if isinstance(r, dict) and r.get("idx") == indices[0]]
                      if isinstance(actor_rows, list) else [action.get("actor_body_id")])
            shooter = _body(manifest[indices[0]-1], strike_ball.get("control_body_id"))
            strike = next(s for s in stages if s["phase"] == "STRIKE")
            if (strike_ball.get("control_visible") is not True or strike_ball.get("control_body_id") not in labels
                    or shooter is None or not _near_body(strike["source_box"], shooter["box"], feet=True)):
                reasons.append("SHOOTER_ACTIVE_BALL_CONTACT_UNBOUND")
            if keeper and shooter and keeper["local_track_id"] == shooter["local_track_id"]:
                reasons.append("KEEPER_IS_SHOOTER")
        if sequence.get("aftermath") == "HELD" and at(indices[3]) is not None:
            held_box = _mapped_box(sequence.get("aftermath_keeper_box"), manifest[indices[3]-1], to_source_box)
            after = next((s for s in stages if s["phase"] == "AFTERMATH"), None)
            if held_box is None or after is None or not _near_body(after["source_box"], held_box):
                reasons.append("HELD_BALL_UNBOUND")
        if len(stages) != 4:
            reasons.append("INCOMPLETE_SOURCE_STAGES")
        audit = {"authority": "TEMPORAL_VIDEO_OBSERVATION", "physical_certificate": False,
                 "status": "INCOMPLETE" if reasons else "OBSERVED", "reasons": sorted(set(reasons)), "stages": stages,
                 "later_visible_control_indices": sorted(set(later_controls))}
        action["save_sequence_evidence"] = audit
        if reasons:
            action["outcome_visible"] = False
            continue
        audit.update(keeper_local_track_id=keeper["local_track_id"] if keeper else None,
                     keeper_observation={"idx": indices[2], "media_ms": at(indices[2]), "source_box": keeper_box,
                         "source": "MEASURED_LOCAL_BODY" if keeper else "SOURCE_VIDEO_VISIBLE_BODY"},
                     aftermath=sequence["aftermath"], ball_id=ball_id)
        outcome = action.get("outcome")
        if outcome is not None and (not isinstance(outcome, str) or outcome not in {"UNKNOWN", "SAVED"}):
            audit["status"] = "CONFLICTING_OUTCOME"
            action["outcome_visible"] = False
            continue
        action.update(outcome="SAVED", outcome_visible=True, outcome_idx=indices[3],
                      outcome_evidence_indices=sorted(set(indices)))
    return result
