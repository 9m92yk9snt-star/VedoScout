"""Marker drift must bind matching pixels to their post-decode native PTS."""
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import precision_engine as engine


class Capture:
    """Pre-read PTS is stale; every decoded image encodes its source index."""
    def __init__(self, times, *, pts_override=None, opened=True, approximate_seek=False):
        self.times = times
        self.pts_override = pts_override
        self.opened = opened
        self.approximate_seek = approximate_seek
        self.next_index = 0
        self.decoded_index = None
        self.pts_ms = 0.
        self.released = False

    def get(self, prop):
        if prop == cv2.CAP_PROP_POS_MSEC:
            return self.pts_override(self.decoded_index, self.pts_ms) if self.pts_override else self.pts_ms
        if prop == cv2.CAP_PROP_POS_FRAMES:
            return self.next_index
        if prop == cv2.CAP_PROP_FPS:
            return 20.
        return 0.

    def set(self, prop, value):
        assert prop == cv2.CAP_PROP_POS_MSEC, 'No frame-index seek'
        requested = value / 1000
        if self.approximate_seek and requested > 0:
            self.next_index = min(len(self.times)-1, round(requested*20))
        else:
            self.next_index = min(range(len(self.times)), key=lambda i: abs(self.times[i]-requested))
        self.pts_ms = self.times[max(0, self.next_index-1)]*1000
        return True

    def grab(self):
        if self.next_index >= len(self.times):
            return False
        self.decoded_index = self.next_index
        self.pts_ms = self.times[self.next_index]*1000
        self.next_index += 1
        return True

    def retrieve(self):
        if self.decoded_index is None:
            return False, None
        return True, np.full((120, 160, 3), self.decoded_index, dtype=np.uint8)

    def read(self):
        return self.retrieve() if self.grab() else (False, None)

    def isOpened(self):
        return self.opened

    def release(self):
        self.released = True


def install(monkeypatch, cap, marker_index):
    monkeypatch.setattr(engine.cv2, 'VideoCapture', lambda _: cap)
    monkeypatch.setattr(engine.cv2, 'imread', lambda _: np.full((120, 160, 3), marker_index, np.uint8))
    monkeypatch.setattr(engine.cv2, 'matchTemplate', lambda frame, marker, _method:
        np.array([[1. if frame[0,0] == marker[0,0] else .1]], dtype=np.float32))


@pytest.mark.parametrize('marker_index,t_marker', [(4,1.10), (6,2.25), (7,2.9)])
def test_matching_pixels_keep_their_own_irregular_pts(monkeypatch, marker_index, t_marker):
    times = [0., .04, .11, .51, 1.07, 1.31, 2.2, 3.0, 3.1, 4.2]
    cap = Capture(times)
    install(monkeypatch, cap, marker_index)
    offset, score = engine.estimate_time_offset('source.mp4', 'user.jpg', t_marker)
    assert offset == pytest.approx(times[marker_index]-t_marker)
    assert score == 1.
    assert cap.released


def test_vfr_approximate_seek_cannot_skip_the_match(monkeypatch):
    times = [0., .05, .1, .15, .4, .8, 1.4, 2.2]
    cap = Capture(times, approximate_seek=True)
    install(monkeypatch, cap, 4)
    offset, score = engine.estimate_time_offset('source.mp4', 'user.jpg', .55, search=.15)
    assert offset == pytest.approx(-.15)
    assert score == 1.
    assert cap.released


def test_matching_frame_beyond_window_cannot_borrow_previous_pts(monkeypatch):
    cap = Capture([0., .2, .4, .6, .8])
    install(monkeypatch, cap, 3)
    offset, score = engine.estimate_time_offset('source.mp4', 'user.jpg', .3, search=.2)
    assert offset == 0.
    assert score < .35
    assert cap.released


@pytest.mark.parametrize('invalid', [None, float('nan'), float('inf'), -1., True])
def test_unavailable_pts_never_uses_frame_index_or_fps(monkeypatch, invalid):
    cap = Capture([0., .2, .4, .8], pts_override=lambda _i,_ms: invalid)
    install(monkeypatch, cap, 2)
    assert engine.estimate_time_offset('source.mp4', 'user.jpg', .4) == (0., 0.)
    assert cap.released


@pytest.mark.parametrize('times', [[0., .2, .2, .6], [0., .2, .1, .6]])
def test_repeated_or_decreasing_pts_invalidates_calibration(monkeypatch, times):
    cap = Capture(times)
    install(monkeypatch, cap, 1)
    assert engine.estimate_time_offset('source.mp4', 'user.jpg', .2) == (0., 0.)
    assert cap.released


def test_zero_is_valid_for_the_first_source_frame(monkeypatch):
    cap = Capture([0., .2, .4])
    install(monkeypatch, cap, 0)
    assert engine.estimate_time_offset('source.mp4', 'user.jpg', .05) == (-.05, 1.)
    assert cap.released


def test_unopened_capture_is_released(monkeypatch):
    cap = Capture([0., .2], opened=False)
    install(monkeypatch, cap, 1)
    assert engine.estimate_time_offset('source.mp4', 'user.jpg', .2) == (0., 0.)
    assert cap.released


def test_scoring_exception_does_not_leak_capture(monkeypatch):
    cap = Capture([0., .2])
    install(monkeypatch, cap, 1)
    def broken(*_):
        raise ValueError('Unreadable pixels')
    monkeypatch.setattr(engine.cv2, 'matchTemplate', broken)
    assert engine.estimate_time_offset('source.mp4', 'user.jpg', .2) == (0., 0.)
    assert cap.released
