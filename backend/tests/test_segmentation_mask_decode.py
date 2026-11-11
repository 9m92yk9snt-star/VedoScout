"""Exact mask parity, including threshold edges and noncontiguous arrays."""
import numpy as np
import pytest
from native_player_segmentation import _bounded_threshold_mask


def legacy(probabilities, bounds):
    mask = (probabilities >= .5).astype(np.uint8)
    result = np.zeros_like(mask)
    x0, y0, x1, y1 = bounds
    result[y0:y1, x0:x1] = mask[y0:y1, x0:x1]
    return result


@pytest.mark.parametrize('shape', [(1, 1), (19, 31), (640, 360), (360, 640), (1920, 1080)])
@pytest.mark.parametrize('fraction', [0, .1, .5, 1])
def test_threshold_only_retained_box_is_bit_exact(shape, fraction):
    rng = np.random.default_rng(87)
    a = rng.random(shape, dtype=np.float32)
    a.flat[:min(a.size, 6)] = np.array([.5, np.nextafter(np.float32(.5), np.float32(0)),
        np.nextafter(np.float32(.5), np.float32(1)), np.nan, np.inf, -np.inf])[:min(a.size, 6)]
    h,w = shape
    bounds = (0, 0, int(w*fraction), int(h*fraction))
    expected=legacy(a,bounds);before=a.copy();actual=_bounded_threshold_mask(a,bounds)
    np.testing.assert_array_equal(actual,expected)
    np.testing.assert_array_equal(a,before)
    assert actual.dtype == np.uint8 and actual.flags.c_contiguous
    assert not np.shares_memory(actual,a)


def test_noncontiguous_input_offset_box_and_result_mutation():
    a=np.random.default_rng(5).random((64,96),dtype=np.float32)[::2,::2]
    bounds=(3,7,29,23)
    first=_bounded_threshold_mask(a,bounds);second=_bounded_threshold_mask(a,bounds)
    np.testing.assert_array_equal(first,legacy(a,bounds))
    first[:]=0
    np.testing.assert_array_equal(second,legacy(a,bounds))
