"""Geometry constraints are necessary evidence, never invisible-foot proof."""
from copy import deepcopy
from orman1000_role_spatial_gate import (
    review_role_geometry, valid_rect, intersection_over_union
)


def valid_synthetic_role():
    return {
        "identity_review_method":"SOURCE_FRAME_PERSON_SEPARATION",
        "finisher_kit_observed":"WHITE",
        "finishing_contact_evidence":"OCCLUDED_BRACKETED",
        "source_selected_player_frame_id":"s000050648",
        "source_selected_player_box":[0.177,0.485,0.103,0.081],
        "source_selected_player_ground":[0.257,0.564],
        "source_finisher_boxes":{
            "s000050331":[0.320,0.460,0.090,0.100],
            "s000050648":[0.335,0.470,0.080,0.095],
        },
    }


def test_synthetic_distinct_body_necessary_but_not_an_identity_approval():
    entry = valid_synthetic_role()
    assert review_role_geometry(entry) == (True, [])
    assert intersection_over_union(
        entry["source_finisher_boxes"]["s000050648"],
        entry["source_selected_player_box"]
    ) == 0.0
    assert valid_rect(entry["source_finisher_boxes"]["s000050331"])
    # The role must still be approved by an independent source-frame review.
    assert "status" not in entry


def test_disagreeing_appearance_motion_or_real_selected_body_must_fail():
    entry = valid_synthetic_role()
    for key, value, reason in [
        ("finisher_kit_observed", "BLUE", "FINISHER_WHITE_KIT_NOT_OBSERVED"),
        ("finishing_contact_evidence", "DIRECT_VISIBLE", "OCCLUDED_CONTACT_UNCERTAINTY_NOT_PRESERVED"),
        ("source_selected_player_frame_id", "prior_video", "ORIGINAL_SELECTED_BODY_POSITION_NOT_BOUND"),
    ]:
        candidate=deepcopy(entry)
        candidate[key]=value
        assert reason in review_role_geometry(candidate)[1]


def test_missing_bad_or_conflicting_source_boxes_do_not_pass():
    baseline=valid_synthetic_role()
    tests=[
        ({"s000050331":[.3,.46,.09,.1]},"FINISHER_TWO_SOURCE_FRAMES_REQUIRED"),
        ({"s000050331":[.32,.46,.09,.1], "s000050648":[.18,.485,.103,.081]},"FINISHER_OVERLAPS_SELECTED_PLAYER"),
        ({"s000050331":[.32,.46,.09,.1], "s000050648":[.92,.87,.12,.12]},"FINISHER_SOURCE_BOX_INVALID"),
        ({"s000050331":[.32,.46,.09,.1], "s000050648":[.63,.47,.08,.09]},"FINISHER_BODY_NOT_TEMPORALLY_LINKED"),
        ({"s000050331":[.32,.46,.09,.1], "s000050648":[.65,.47,.08,.09]},"FINISHER_UNSUPPORTED_BY_OBSERVED_BALL_AREA"),
    ]
    for boxes,code in tests:
        candidate=deepcopy(baseline)
        candidate["source_finisher_boxes"]=boxes
        assert code in review_role_geometry(candidate)[1]
