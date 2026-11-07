"""Light fabric checks are necessary evidence only, not a finisher predictor."""
import numpy as np
import pytest

from orman1000_role_pixel_gate import white_kit_pixel_ratio, MIN_LIGHT_KIT_FRACTION


def test_white_shirt_pixels_are_distinct_from_blue_and_pitch_colours():
    frame=np.zeros((120,180,3),np.uint8)
    # BGR colours: white clothing, saturated blue jersey, green pitch.
    frame[:,:60]=[225,225,225]
    frame[:,60:120]=[200,80,40]
    frame[:,120:]=[40,130,45]
    assert white_kit_pixel_ratio(frame,[0,0,1/3,1]) > .99
    assert white_kit_pixel_ratio(frame,[1/3,0,1/3,1]) < MIN_LIGHT_KIT_FRACTION
    assert white_kit_pixel_ratio(frame,[2/3,0,1/3,1]) < MIN_LIGHT_KIT_FRACTION


def test_source_pixel_crop_fails_closed_on_invalid_or_empty_boxes():
    frame=np.full((120,180,3),225,np.uint8)
    for box in ([.2,.2,0,.1],[.9,.2,.2,.1],[-.1,.1,.2,.2]):
        with pytest.raises(ValueError,match="SOURCE_ROLE_BOX_OR_PIXELS_INVALID"):
            white_kit_pixel_ratio(frame,box)


def test_light_kit_fraction_does_not_approve_a_goal_scorer():
    frame=np.zeros((100,100,3),np.uint8)
    frame[:60,:60]=[228,232,237]
    measured=white_kit_pixel_ratio(frame,[0,0,.6,.6])
    assert measured > MIN_LIGHT_KIT_FRACTION
    # Passing white/low-saturation appearance is NEVER evidence of a touch.
    assert not hasattr(measured,"finisher_approved")
