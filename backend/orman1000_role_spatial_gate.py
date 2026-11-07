"""Fail-closed Orman1000 human-adjudication geometry checks.

Coordinates bind to a documented source video PTS and source frame hash, not a
model-local person id from an older video. Valid boxes and player separation
are NECESSARY conditions, NOT proof that an occluded foot struck the ball.
This pure module never runs a detector or approves a game action by itself.
"""
from math import isfinite

SELECTED_FRAME_MS = 50648
SELECTED_FRAME_ID = "s000050648"
# From Orman1000's verified source-localization receipt, not another video.
SELECTED_BODY_BOX = [0.177, 0.485, 0.103, 0.081]
SELECTED_GROUND = [0.257, 0.564]
SOURCE_BALL_AT_FINISH_MS = [0.363, 0.539]


def valid_rect(box):
    return (isinstance(box, (list, tuple)) and len(box) == 4
            and all(type(v) in (int, float) and isfinite(v) for v in box)
            and box[0] >= 0 and box[1] >= 0
            and 0 < box[2] <= 1 and 0 < box[3] <= 1
            and box[0] + box[2] <= 1 and box[1] + box[3] <= 1)


def intersection_over_union(a, b):
    if not valid_rect(a) or not valid_rect(b):
        raise ValueError("UNVERIFIED_ROLE_BOX")
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[0]+a[2], b[0]+b[2]), min(a[1]+a[3], b[1]+b[3])
    inter = max(0, x1-x0) * max(0, y1-y0)
    union = a[2]*a[3]+b[2]*b[3]-inter
    return inter/union


def review_role_geometry(review):
    """Return (okay, blockers); no identity is inferred by these checks."""
    errors = []
    if not isinstance(review, dict):
        return False, ["ROLE_SPATIAL_REVIEW_MISSING"]
    def check(ok, error):
        if not ok:
            errors.append(error)

    # Must be a fresh current-source visual role review, not a re-labelled
    # older model's p3 or a generic prose claim.
    check(review.get("identity_review_method") == "SOURCE_FRAME_PERSON_SEPARATION",
          "ROLE_REVIEW_METHOD_NOT_FRAME_BOUND")
    check(review.get("finisher_kit_observed") == "WHITE",
          "FINISHER_WHITE_KIT_NOT_OBSERVED")
    check(review.get("finishing_contact_evidence") == "OCCLUDED_BRACKETED",
          "OCCLUDED_CONTACT_UNCERTAINTY_NOT_PRESERVED")
    check(review.get("source_selected_player_frame_id") == SELECTED_FRAME_ID
          and review.get("source_selected_player_box") == SELECTED_BODY_BOX
          and review.get("source_selected_player_ground") == SELECTED_GROUND,
          "ORIGINAL_SELECTED_BODY_POSITION_NOT_BOUND")
    boxes = review.get("source_finisher_boxes")
    check(isinstance(boxes, dict) and set(boxes) == {
          "s000050331", "s000050648"}, "FINISHER_TWO_SOURCE_FRAMES_REQUIRED")
    if not isinstance(boxes, dict) or set(boxes) != {"s000050331","s000050648"}:
        return False, errors
    a, b = boxes["s000050331"],boxes["s000050648"]
    check(valid_rect(a) and valid_rect(b), "FINISHER_SOURCE_BOX_INVALID")
    if valid_rect(a) and valid_rect(b):
        check(intersection_over_union(b, SELECTED_BODY_BOX) < 0.02,
              "FINISHER_OVERLAPS_SELECTED_PLAYER")
        selected_center = (SELECTED_BODY_BOX[0]+SELECTED_BODY_BOX[2]/2,
                           SELECTED_BODY_BOX[1]+SELECTED_BODY_BOX[3]/2)
        finish_center = (b[0]+b[2]/2,b[1]+b[3]/2)
        dx = finish_center[0] - selected_center[0]
        dy = finish_center[1] - selected_center[1]
        check(dx*dx+dy*dy > 0.055**2, "FINISHER_NOT_SEPARATE_SOURCE_BODY")
        # Camera drift / movement is possible, but a wildly displaced
        # candidate between nearby timestamps is not a proven same person.
        old_center = (a[0]+a[2]/2,a[1]+a[3]/2)
        step = ((finish_center[0]-old_center[0])**2
                +(finish_center[1]-old_center[1])**2)**.5
        check(step <= 0.14, "FINISHER_BODY_NOT_TEMPORALLY_LINKED")
        # A reviewed separate finisher must be within a plausible vicinity
        # of the observed outgoing ball; this is only a contradiction gate.
        bx, by = SOURCE_BALL_AT_FINISH_MS
        padding = 0.1
        check(b[0]-padding <= bx <= b[0]+b[2]+padding
              and b[1]-padding <= by <= b[1]+b[3]+padding,
              "FINISHER_UNSUPPORTED_BY_OBSERVED_BALL_AREA")
    return not errors, errors
