"""Appearance evidence must be invariant to pixels outside the accepted body box."""
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv_shadow as cv

GREEN = (40, 150, 40)
BOX = (40, 30, 24, 100)


def scene(box=BOX):
    image = np.full((180, 120, 3), GREEN, np.uint8)
    x, y, w, h = box
    image[y:y + h, x:x + w] = (240, 240, 240)
    return image


def outside_variant(image, box, colour):
    changed = np.full_like(image, colour)
    x, y, w, h = box
    changed[y:y + h, x:x + w] = image[y:y + h, x:x + w]
    return changed


def assert_same_embedding(a, b):
    assert a is not None and b is not None
    for key in ("scale", "zone_support", "aspect", "merged", "px_h", "owned"):
        assert a[key] == b[key], key
    for za, zb in zip(a["zones"], b["zones"]):
        np.testing.assert_array_equal(za, zb)
    assert cv._sim(a, b) == cv._sim(a, a)
    assert cv._profile_sim(b, [{"emb": a, "weight": 1.}]) == cv._sim(a, a)
    assert cv._sim_relaxed(b, [{"emb": a}]) == cv._sim_relaxed(a, [{"emb": a}])


@pytest.mark.parametrize("colour", [(240, 240, 240), (255, 0, 0), (0, 0, 255), (0, 0, 0)])
def test_connected_outside_pixels_cannot_change_geometry_zones_or_similarity(colour):
    original = scene()
    changed = outside_variant(original, BOX, colour)
    # The supplied pitch reference is held fixed: this tests crop ownership,
    # independently of the separate frame-wide illumination estimator.
    assert_same_embedding(cv._zone_embedding(original, BOX, 140),
                          cv._zone_embedding(changed, BOX, 140))


def test_arbitrary_outside_texture_cannot_change_component_choice():
    original = scene()
    changed = np.random.default_rng(6).integers(0, 256, original.shape, dtype=np.uint8)
    x, y, w, h = BOX
    changed[y:y + h, x:x + w] = original[y:y + h, x:x + w]
    assert_same_embedding(cv._zone_embedding(original, BOX, 140),
                          cv._zone_embedding(changed, BOX, 140))


@pytest.mark.parametrize("box", [BOX, (0, 0, 24, 100), (96, 80, 24, 100)])
def test_selected_component_and_returned_origin_stay_inside_body_box(box):
    image = np.full((180, 120, 3), (240, 240, 240), np.uint8)
    crop, mask, merged, (gx, gy) = cv._comp_mask_crop(image, box)
    assert (gx, gy) == box[:2]
    assert crop.shape[:2] == (box[3], box[2])
    assert mask.shape == crop.shape[:2]
    assert np.all(mask == 255)
    assert merged is False


@pytest.mark.parametrize("box,expected", [
    ((-5, 20, 25, 100), (0, 20, 20, 100)),
    ((20, -10, 25, 100), (20, 0, 25, 90)),
    ((110, 20, 25, 100), (110, 20, 10, 100)),
    ((20, 170, 25, 100), (20, 170, 25, 10)),
])
def test_partial_body_box_is_clipped_to_visible_image_without_padding(box, expected):
    image = np.full((180, 120, 3), (240, 240, 240), np.uint8)
    crop, mask, _merged, origin = cv._comp_mask_crop(image, box)
    assert origin == expected[:2]
    assert crop.shape[:2] == (expected[3], expected[2])
    assert mask.shape == crop.shape[:2]


@pytest.mark.parametrize("box", [
    (120, 20, 24, 100), (-30, 20, 20, 100),
    (20, 180, 24, 100), (20, -110, 24, 100),
    (20, 20, 0, 100), (20, 20, 24, 0),
    (20, 20, -3, 100), (20, 20, 24, -3),
])
def test_empty_or_offscreen_body_cannot_borrow_nearby_pixels(box):
    image = np.full((180, 120, 3), (240, 240, 240), np.uint8)
    assert cv._zone_embedding(image, box, 140) is None


def test_no_component_fallback_still_contains_only_accepted_body_pixels():
    original = np.full((180, 120, 3), GREEN, np.uint8)
    original[70:72, 50:52] = (240, 240, 240)  # below the 30-pixel component gate
    changed = outside_variant(original, BOX, (255, 0, 0))
    crop, mask, merged, origin = cv._comp_mask_crop(changed, BOX)
    assert merged is True
    assert origin == BOX[:2]
    assert crop.shape[:2] == (100, 24)
    assert np.all(mask == 255)
    assert_same_embedding(cv._zone_embedding(original, BOX, 140),
                          cv._zone_embedding(changed, BOX, 140))


def test_separable_second_body_inside_box_is_still_excluded():
    image = np.full((180, 120, 3), GREEN, np.uint8)
    image[30:130, 48:64] = (240, 240, 240)  # centred body
    image[30:130, 40:44] = (255, 0, 0)  # separable opponent, inside loose box
    crop, mask, merged, origin = cv._comp_mask_crop(image, BOX)
    assert merged is False
    assert origin == (48, 30)
    assert crop.shape[:2] == (100, 16)
    assert np.all(crop == 240) and np.all(mask == 255)


@pytest.mark.parametrize("ownership", [False, True])
def test_crop_boundary_preserves_same_frame_masks_and_occlusion_rejection(ownership):
    original = scene()
    changed = outside_variant(original, BOX, (0, 0, 255))
    kwargs = {"occluders": [(40, 30, 24, 85)]}
    if ownership:
        mask = np.zeros(original.shape[:2], np.uint8)
        mask[30:130, 40:64] = 255
        kwargs["ownership_mask"] = mask
    a = cv._zone_embedding(original, BOX, 140, **kwargs)
    b = cv._zone_embedding(changed, BOX, 140, **kwargs)
    assert_same_embedding(a, b)
    assert a["owned"] is False and cv._sim(a, b) == 0.


def test_interior_colour_changes_remain_visible_to_identity_comparison():
    original = scene()
    opponent = original.copy()
    opponent[30:130, 40:64] = (255, 0, 0)
    a = cv._zone_embedding(original, BOX, 140)
    b = cv._zone_embedding(opponent, BOX, 140)
    assert cv._sim(a, a) == 1.
    assert cv._sim(a, b) < cv.SIM_T
