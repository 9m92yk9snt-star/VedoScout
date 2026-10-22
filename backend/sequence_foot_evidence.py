"""Validate model-cited anatomical side without inferring a side from a profile.

This is a source-evidence contract, not an independent visual classifier. It
cannot promote a probable model observation to a supported one.
"""
from copy import deepcopy
import re

SIDE_TEXT = {
    "LEFT": re.compile(r"\bleft[ -]?(?:foot(?:ed)?|boot|leg)\b|\bvenstre[ -]?(?:fod(?:s)?|ben|støvle)\b", re.I),
    "RIGHT": re.compile(r"\bright[ -]?(?:foot(?:ed)?|boot|leg)\b|\bhøjre[ -]?(?:fod(?:s)?|ben|støvle)\b", re.I),
}


def foot_text_supported(text, sides):
    return all(side in sides or not pattern.search(text) for side, pattern in SIDE_TEXT.items())


def strip_foot_modifiers(text, sides):
    """Remove an unsupported foot modifier without discarding a known action."""
    for side in SIDE_TEXT:
        if side in sides:
            continue
        text = re.sub(rf"\s+(?:with|using)\s+(?:(?:his|her|their|the|a)\s+)?{side.lower()}[ -]?foot\b",
                      "", text, flags=re.I)
        text = re.sub(rf"\b{side.lower()}-footed\s+(?=(?:shot|finish|strike|pass|goal)\b)",
                      "", text, flags=re.I)
    return text


def filter_foot_prose(text, side):
    """Keep uncertain foot claims in audit, outside player-facing action prose."""
    text = strip_foot_modifiers(text, {side})
    return " ".join(part for part in re.split(r"(?<=[.!?])\s+", text)
                    if foot_text_supported(part, {side}))


INSTRUCTION = """Assess anatomical foot separately from actor and outcome. For a
SHOT/PASS/CROSS you may add anatomical_foot={actor:the action actor,
side:LEFT|RIGHT|UNKNOWN,assessment:SUPPORTED|PROBABLE|UNCERTAIN,
basis:DIRECT_CONTACT|CONTINUOUS_LEG_SEQUENCE,
other_contact_actors_excluded:true|false,
orientation_evidence:[{frame:source_id,fact:visible torso/hip orientation}],
right_leg_evidence:[{frame:source_id,fact:right hip/knee/ankle continuity}],
left_leg_evidence:[{frame:source_id,fact:left hip/knee/ankle continuity}],
contact_evidence:[{frame:source_id,fact:the identified foot and ball motion}]}.
Trace both physical legs from the approach through release, accounting for body
rotation, crossings and occlusion. The identifiable opposite/support leg can
establish the striking side when continuous motion excludes alternatives even
if one exact boot-ball instant is hidden. Cite actual source frames: orientation
and each leg before contact, each leg at/after contact, and the contacting limb
and ball's departure. Screen-left/right, boot colour, preferred foot, celebration
or a later goal alone cannot establish anatomical side. SUPPORTED requires a
unique actor and limb; use PROBABLE or UNCERTAIN if another touching actor/limb
remains plausible. Do not return a supported side to satisfy an expected answer.
Use question reason FOOT only for anatomical-side uncertainty, separately from
IDENTITY/CONTACT/RECEIVER/OUTCOME. A FOOT question must contain only that issue.
Any doubt about who touches the ball, a goalkeeper/defender touch affecting the
outcome, whether the shot was goalbound before a deflection, or goal attribution
remains CONTACT or OUTCOME and blocks the affected event. Do not hide mixed
contact or scorer questions in FOOT. Unknown foot alone does not invalidate an
otherwise established action. Omit anatomical_foot if there is no limb evidence.
"""


def assess_foot(claim, *, actor, interval, frames, bounds):
    """Only complete supported source sequences yield a publishable side."""
    unknown = {"foot": "UNKNOWN", "foot_verification": "ANATOMICAL_SIDE_NOT_VERIFIED"}
    if not isinstance(claim, dict):
        return unknown
    assessment = claim.get("assessment")
    candidate = claim.get("side") if isinstance(claim.get("side"), str) else "UNKNOWN"
    assessment = assessment if isinstance(assessment, str) else "UNCERTAIN"
    result = {**unknown, "foot_review": {"candidate_side": candidate if candidate in {"LEFT", "RIGHT"} else "UNKNOWN",
               "assessment": assessment if assessment in {"SUPPORTED", "PROBABLE", "UNCERTAIN"} else "UNCERTAIN",
               "reason": "ANATOMICAL_EVIDENCE_INCOMPLETE"}}
    if (assessment != "SUPPORTED" or candidate not in {"LEFT", "RIGHT"}
            or claim.get("actor") != actor or claim.get("other_contact_actors_excluded") is not True
            or not isinstance(claim.get("basis"), str)
            or claim["basis"] not in {"DIRECT_CONTACT", "CONTINUOUS_LEG_SEQUENCE"}
            or not isinstance(interval, list) or len(interval) != 2
            or any(type(t) is not int for t in interval)
            or not bounds[0] <= interval[0] <= interval[1] <= bounds[1]):
        return result
    before, after = interval
    groups = {}
    for key in ("orientation_evidence", "right_leg_evidence", "left_leg_evidence", "contact_evidence"):
        rows = claim.get(key)
        if not isinstance(rows, list) or not 1 <= len(rows) <= 12:
            return result
        if any(not isinstance(r, dict) or not isinstance(r.get("frame"), str)
               or r["frame"] not in frames or not isinstance(r.get("fact"), str)
               or not r["fact"].strip() or not bounds[0] <= frames[r["frame"]] <= bounds[1]
               for r in rows):
            return result
        groups[key] = sorted({frames[r["frame"]] for r in rows})
    if not any(before-2000 <= t <= before for t in groups["orientation_evidence"]):
        return result
    for key in ("right_leg_evidence", "left_leg_evidence"):
        times = groups[key]
        if (len(times) < 2 or not any(before-2000 <= t <= before for t in times)
                or not any(after <= t <= after+500 for t in times)):
            return result
    contacts = groups["contact_evidence"]
    if (not any(before-250 <= t <= before for t in contacts)
            or not any(after <= t <= after+250 for t in contacts)):
        return result
    result.update(foot=candidate, foot_verification="SOURCE_ANATOMICAL_SEQUENCE_SUPPORTED",
                  foot_evidence=deepcopy(claim))
    result["foot_review"]["reason"] = "SUPPORTED_SOURCE_SEQUENCE"
    return result
