"""FIX10A0 — regression tests for canonical motion-frame ingestion.

These tests isolate the decoder/timebase contract.  They do not exercise the
camera estimator itself; FIX06 camera-transform safety semantics remain covered
by the existing suite and are intentionally unchanged by A0.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import motion_compensation as mc  # noqa: E402


class FakeCapture:
    """Small OpenCV-like capture with explicit irregular media PTS."""

    def __init__(self, rows, fps=30.0):
        # rows: [(seconds, frame_or_none), ...]
        self.rows = list(rows)
        self.fps = float(fps)
        self.next_idx = 0
        self.current_idx = None
        self.grab_calls = 0
        self.retrieve_times = []
        self.released = False

    def isOpened(self):
        return True

    def set(self, prop, value):
        if prop == cv2.CAP_PROP_POS_MSEC:
            target = float(value) / 1000.0
            self.next_idx = next(
                (i for i, (t, _frame) in enumerate(self.rows) if t >= target - 1e-9),
                len(self.rows),
            )
            self.current_idx = None
            return True
        return True

    def get(self, prop):
        if prop == cv2.CAP_PROP_FPS:
            return self.fps
        if prop == cv2.CAP_PROP_POS_MSEC:
            if self.current_idx is None:
                return 0.0
            return float(self.rows[self.current_idx][0]) * 1000.0
        if prop == cv2.CAP_PROP_POS_FRAMES:
            # OpenCV reports position AFTER the grabbed frame.
            return float((self.current_idx + 1) if self.current_idx is not None else self.next_idx)
        return 0.0

    def grab(self):
        if self.next_idx >= len(self.rows):
            return False
        self.current_idx = self.next_idx
        self.next_idx += 1
        self.grab_calls += 1
        return True

    def retrieve(self):
        if self.current_idx is None:
            return False, None
        t, frame = self.rows[self.current_idx]
        self.retrieve_times.append(float(t))
        if frame is None:
            return False, None
        return True, frame.copy()

    def release(self):
        self.released = True


def _frame(value):
    return np.full((8, 12, 3), int(value), dtype=np.uint8)


def _point(t):
    return {"t": float(t), "x": 0.2, "y": 0.2, "w": 0.1, "h": 0.3, "conf": 0.9}


def _capture_frames(monkeypatch, cap):
    """Return decoded grayscale frames without invoking camera estimation."""
    monkeypatch.setattr(mc.cv2, "VideoCapture", lambda _path: cap)
    seen = {}

    def capture(frames, points):
        seen["frames"] = frames
        seen["points"] = points
        return {"w": 12, "h": 8, "samples": []}

    monkeypatch.setattr(mc, "samples_from_frames", capture)
    return seen


def test_a001_one_grab_per_decoded_pts_never_double_grab(monkeypatch):
    times = [round(i / 10.0, 3) for i in range(13)]  # 0.0 .. 1.2
    cap = FakeCapture([(t, _frame(round(t * 100))) for t in times], fps=10.0)
    seen = _capture_frames(monkeypatch, cap)

    mc.compute_motion_samples("fake.mp4", {"points": [_point(1.0), _point(1.1), _point(1.2)]})

    # seek_with_preroll grabs 0.0 once; every later source frame is advanced
    # once.  The old bug performed an extra cap.grab() before the timebase grab.
    assert cap.grab_calls == len(times)
    assert cap.retrieve_times == [1.0, 1.1, 1.2]
    assert all(frame is not None for frame in seen["frames"])


def test_a002_grab_frame_tuple_is_unpacked_as_ok_time_fallback(monkeypatch):
    cap = FakeCapture([
        (0.50, _frame(50)),
        (1.00, _frame(100)),
        (1.10, _frame(110)),
    ], fps=10.0)
    seen = _capture_frames(monkeypatch, cap)

    out = mc.compute_motion_samples("fake.mp4", {"points": [_point(1.0), _point(1.1)]})

    assert out["samples"] == []
    assert [int(f[0, 0]) for f in seen["frames"]] == [100, 110]


def test_a003_retrieve_frame_is_the_frame_that_established_pts(monkeypatch):
    cap = FakeCapture([
        (0.50, _frame(5)),
        (0.90, _frame(9)),
        (1.00, _frame(10)),
        (1.10, _frame(11)),
        (1.20, _frame(12)),
    ], fps=10.0)
    seen = _capture_frames(monkeypatch, cap)

    mc.compute_motion_samples("fake.mp4", {"points": [_point(1.0), _point(1.1), _point(1.2)]})

    assert cap.retrieve_times == [1.0, 1.1, 1.2]
    assert [int(f[0, 0]) for f in seen["frames"]] == [10, 11, 12]


def test_a004_decode_miss_stays_none_and_rejects_adjacent_intervals(monkeypatch):
    cap = FakeCapture([
        (1.00, _frame(10)),
        (1.10, None),
        (1.20, _frame(12)),
    ], fps=10.0)
    monkeypatch.setattr(mc.cv2, "VideoCapture", lambda _path: cap)
    monkeypatch.setattr(
        mc,
        "estimate_camera",
        lambda _a, _b, _boxes: (np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]), 20),
    )

    out = mc.compute_motion_samples(
        "fake.mp4", {"points": [_point(1.0), _point(1.1), _point(1.2)]}
    )

    assert len(out["samples"]) == 2
    assert [s["reason"] for s in out["samples"]] == ["decode", "decode"]
    assert all(s["ok"] is False for s in out["samples"])


def test_a005_irregular_vfr_pts_are_not_retimed_by_frame_index(monkeypatch):
    times = [0.501, 0.777, 1.011, 1.087, 1.204]
    values = [51, 77, 101, 108, 120]
    cap = FakeCapture(list(zip(times, [_frame(v) for v in values])), fps=30.0)
    seen = _capture_frames(monkeypatch, cap)
    points = [_point(1.011), _point(1.087), _point(1.204)]

    mc.compute_motion_samples("fake-vfr.mp4", {"points": points})

    assert cap.retrieve_times == [1.011, 1.087, 1.204]
    assert [int(f[0, 0]) for f in seen["frames"]] == [101, 108, 120]
    assert [p["t"] for p in seen["points"]] == [1.011, 1.087, 1.204]
