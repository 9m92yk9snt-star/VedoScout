"""Source-bound movement observations; never infer a take-on or scorer from them."""
from copy import deepcopy


GOAL_INSTRUCTION = """GOAL-ATTRIBUTION REVIEW PRIORITY. Independently assess the
selected player's attack and the active ball's visible goal outcome. Prioritize
whether a selected-player goal or direct assist is supported; preserve the
other observed actions. There is no expected scorer or required answer. Keep
the supplied plays/actions/people/questions JSON contract. Evaluate separately
(1) the releasing actor from approach, body/limb motion and ball departure,
(2) continuity of that active ball into the goal, (3) any goalkeeper or defender
intervention and its visible effect. Follow the sequence before and after each
occlusion. Distinguish an observed touch from a hypothetical possible touch,
and a failed clearance from controlled opponent possession or a decisive
redirection. An exact boot-ball frame, unknown striking foot, keeper movement
or brief occlusion alone neither proves nor disproves attribution. If a later
touch is unclear, assess whether the images establish the ball was already
travelling into the goal before it. Do not assume every possible brush changes
the scorer, or assume an obscured intervention is harmless. Return GOAL and
contact_actor_unique=true only when supported by the source sequence; otherwise
retain the specific uncertainty. Cite release, ball-path and intervention
frames in the action's contact_evidence and outcome_evidence, and describe the
strongest competing attribution in details. Do not invent a contact or a
goal-line crossing time. Celebration cannot establish the scorer. Anatomical
side is separate and must not delay an otherwise established goal or assist.
"""

MOVEMENT_INSTRUCTION = """Within each observed DRIBBLE or CARRY, inspect visible
protective turns and changes of direction, including movements before a later
loss. You may add movement_observations:[{actor:the action actor,
type:SHIELD_TURN|DIRECTION_CHANGE|DIRECTION_REVERSAL|PROTECTIVE_TURN,
decision:SUPPORTED|UNCERTAIN,before_frame:source_id,movement_frames:[source_id],
after_frame:source_id,visible_movement:concrete body and ball motion,
opponent_response:visible response or UNKNOWN,
outcome:PROGRESSES|RETAINS|PASSES|LOSES|UNKNOWN}]. Keep each observation local to
the movement and cite the approach, movement and immediate result. A later loss
does not erase an earlier observed turn. A direction change is not proof of
deception, a named trick or an opponent beaten. Do not infer successful take-ons
or their totals from these observations. Use UNCERTAIN if the movement or actor
is unclear. Do not guess a foot, scanning, intention or academy level. Report
only what the supplied frames establish; no expected times or counts exist.
"""

MOVEMENT_TEXT = {
    "SHIELD_TURN": "Turns while shielding the ball.",
    "DIRECTION_CHANGE": "Changes direction with the ball.",
    "DIRECTION_REVERSAL": "Reverses direction with the ball.",
    "PROTECTIVE_TURN": "Turns to protect the ball.",
}


def supported_movements(rows, *, actor, frames, bounds):
    """Validate citations/chronology, not independent visual correctness."""
    if not isinstance(rows, list) or len(rows) > 20:
        return []
    result, seen = [], set()
    for row in rows:
        if (not isinstance(row, dict) or row.get("actor") != actor
                or row.get("decision") != "SUPPORTED"
                or not isinstance(row.get("type"), str) or row["type"] not in MOVEMENT_TEXT
                or not isinstance(row.get("outcome"), str)
                or row["outcome"] not in {"PROGRESSES", "RETAINS", "PASSES", "LOSES", "UNKNOWN"}
                or any(not isinstance(row.get(k), str) or not row[k].strip()
                       for k in ("visible_movement", "opponent_response"))):
            continue
        middle = row.get("movement_frames")
        if not isinstance(middle, list) or not 1 <= len(middle) <= 12:
            continue
        cited = [row.get("before_frame"), *middle, row.get("after_frame")]
        if any(not isinstance(f, str) or f not in frames for f in cited):
            continue
        before, after = frames[cited[0]], frames[cited[-1]]
        if (not bounds[0] <= before < after <= bounds[1]
                or not all(before < frames[f] < after for f in middle)):
            continue
        key = (row["type"], before, after)
        if key not in seen:
            result.append({**deepcopy(row), "source_interval_ms": [before, after]})
            seen.add(key)
    return result
