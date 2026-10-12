"""The jersey reader must retain side digits and exclude another body's pixels."""
from pathlib import Path
import sys
from copy import deepcopy

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jersey_pixels as pixels
import dense_track_refinement as dense
import fix10a_vision_providers as vision

BOX = {"x": .2, "y": .2, "w": .2, "h": .5}


def test_full_width_torso_retains_a_first_digit_at_the_body_edge():
    image = np.zeros((200, 200, 3), np.uint8)
    image[70:95, 42:44] = 255  # A side digit in the body's first twelve percent.
    crop = pixels.native_torso_crop(image, BOX)
    assert crop.shape[1:] == (40, 3) and crop.shape[0] >= 40
    assert np.count_nonzero(crop[:, :5]) > 0
    # The old central quality rectangle entirely removed these printed pixels.
    assert not image[58:98, 45:75, :].any()


@pytest.mark.parametrize("shape", [(200,200), (1080,1920), (1920,1080)])
def test_pixels_outside_the_body_cannot_change_the_reader_crop(shape):
    h, w = shape
    rng = np.random.default_rng(31)
    image = rng.integers(0,256,(*shape,3),dtype=np.uint8)
    changed = image.copy()
    outside = np.ones(shape, bool)
    x0, x1 = int(np.ceil(BOX["x"]*w)), int(np.floor((BOX["x"]+BOX["w"])*w))
    y0, y1 = int(np.ceil(BOX["y"]*h)), int(np.floor((BOX["y"]+BOX["h"])*h))
    outside[y0:y1,x0:x1] = False
    changed[outside] = 255-changed[outside]
    assert np.array_equal(pixels.native_torso_crop(image, BOX), pixels.native_torso_crop(changed, BOX))


def test_quality_and_reader_use_identical_native_pixels_before_interpolation():
    gray = np.indices((200,200)).sum(axis=0).astype(np.uint8)%2*255
    p = {"box":BOX}
    quality = dense._jersey_crop_quality(gray, p, [p])
    crop = pixels.native_torso_crop(gray, BOX)
    assert (quality["height_px"],quality["width_px"]) == crop.shape
    assert quality["isolated"] is True
    assert quality["canonical_identity_authority"] is False


@pytest.mark.parametrize("box", [None, {}, {**BOX,"x":float('nan')}, {**BOX,"h":0},
                                    {**BOX,"w":True}, {**BOX,"x":2}, {**BOX,"y":1.02}])
def test_invalid_or_invisible_boxes_cannot_supply_reader_pixels(box):
    assert pixels.native_torso_crop(np.zeros((200,200,3),np.uint8), box) is None


def test_partial_frame_intersection_is_clipped_inside_the_visible_body():
    image = np.indices((100,100)).sum(axis=0).astype(np.uint8)
    box = {"x":-.05,"y":-.05,"w":.20,"h":.60}
    assert pixels.torso_bounds(image, box) == (0,6,15,33)
    assert np.array_equal(pixels.native_torso_crop(image,box),image[6:33,0:15])


def test_crop_is_a_copy_and_cannot_modify_the_original_frame():
    image = np.zeros((200,200,3),np.uint8)
    pixels.native_torso_crop(image,BOX)[:] = 255
    assert not image.any()


def test_jersey_provider_uses_bounded_torso_and_never_passes_an_expected_number(monkeypatch):
    image = np.indices((200,200)).sum(axis=0).astype(np.uint8)%2*255
    image = np.repeat(image[:,:,None],3,axis=2)
    captured = []
    monkeypatch.setattr(vision,"_read_frames",lambda *_a:{1000:(1000,image)})
    monkeypatch.setattr(vision,"_write_jpg",lambda path,crop: captured.append(crop.copy()) or True)
    def support(_reader,jobs,**kwargs):
        assert all(len(args)==3 and not kwargs for args,kwargs in jobs)
        return [{"readable":False,"number":None,"confidence":"low"} for _ in jobs]
    monkeypatch.setattr(vision.support_vision_runner,"run_support_vision",support)
    request={"track_id":"actor","media_ms":1000,"box":deepcopy(BOX),"expected_jersey_number":"99"}
    result=vision.ShadowVisionProviders("test-only","offline").jersey_vote_provider("unused",[request])
    assert len(captured)==1
    assert np.array_equal(captured[0],pixels.native_torso_crop(image,BOX))
    assert result["actor"][0]["readable"] is False
