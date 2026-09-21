"""FIX10A1 — dense replay windowing and actual-PTS decoding tests."""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import dense_replay as dr  # noqa: E402


class FakeCapture:
    """OpenCV-like capture whose rows carry explicit media PTS."""

    def __init__(self, rows, fps=30.0):
        # row = {t, frame, optional pos_ms}; t is only used by the fake seek.
        self.rows = list(rows)
        self.fps = float(fps)
        self.next_idx = 0
        self.current_idx = None
        self.released = False

    def isOpened(self):
        return True

    def set(self, prop, value):
        if prop == cv2.CAP_PROP_POS_MSEC:
            target = float(value) / 1000.0
            self.next_idx = next(
                (i for i, row in enumerate(self.rows) if float(row["t"]) >= target - 1e-9),
                len(self.rows),
            )
            self.current_idx = None
        return True

    def get(self, prop):
        if prop == cv2.CAP_PROP_FPS:
            return self.fps
        if prop == cv2.CAP_PROP_POS_MSEC:
            if self.current_idx is None:
                return 0.0
            row = self.rows[self.current_idx]
            return float(row.get("pos_ms", float(row["t"]) * 1000.0))
        if prop == cv2.CAP_PROP_POS_FRAMES:
            return float((self.current_idx + 1) if self.current_idx is not None else self.next_idx)
        return 0.0

    def grab(self):
        if self.next_idx >= len(self.rows):
            return False
        self.current_idx = self.next_idx
        self.next_idx += 1
        return True

    def retrieve(self):
        if self.current_idx is None:
            return False, None
        frame = self.rows[self.current_idx].get("frame")
        if frame is None:
            return False, None
        return True, frame.copy()

    def release(self):
        self.released = True


def _frame(value=20, w=24, h=16):
    return np.full((h, w, 3), int(value), dtype=np.uint8)


def _rows(times, pos_ms=None):
    out = []
    for i, t in enumerate(times):
        row = {"t": float(t), "frame": _frame(20 + i)}
        if pos_ms is not None:
            row["pos_ms"] = pos_ms[i]
        out.append(row)
    return out


def _decode(monkeypatch, times, start_ms, end_ms, fps=30.0, pos_ms=None):
    cap = FakeCapture(_rows(times, pos_ms=pos_ms), fps=fps)
    monkeypatch.setattr(dr.cv2, "VideoCapture", lambda _path: cap)
    return list(dr.iter_dense_frames("fake.mp4", start_ms, end_ms)), cap


def test_a101_25fps_keeps_every_available_frame(monkeypatch):
    times = [1.0 + i / 25.0 for i in range(6)]
    rows, cap = _decode(monkeypatch, times, 1000, 1200, fps=25.0)
    assert [r["media_ms"] for r in rows] == [1000, 1040, 1080, 1120, 1160, 1200]
    assert all(r["time_authority"] == "ACTUAL_MEDIA_PTS" for r in rows)
    assert cap.released is True


def test_a102_2997fps_is_not_rounded_to_25_or_30(monkeypatch):
    times = [1.000000, 1.033367, 1.066733, 1.100100]
    rows, _ = _decode(monkeypatch, times, 1000, 1101, fps=29.97)
    assert [r["media_ms"] for r in rows] == [1000, 1033, 1067, 1100]
    assert len(rows) == len(times)


def test_a103_60fps_keeps_every_available_frame(monkeypatch):
    times = [2.0 + i / 60.0 for i in range(7)]
    rows, _ = _decode(monkeypatch, times, 2000, 2100, fps=60.0)
    assert len(rows) == 7
    assert rows[0]["media_ms"] == 2000
    assert rows[-1]["media_ms"] == 2100


def test_a104_irregular_vfr_pts_are_preserved_in_order(monkeypatch):
    times = [3.001, 3.028, 3.079, 3.111, 3.190]
    rows, _ = _decode(monkeypatch, times, 3000, 3200, fps=30.0)
    assert [r["media_ms"] for r in rows] == [3001, 3028, 3079, 3111, 3190]


def test_a105_critical_windows_never_merge_across_scene_cut():
    plan = {
        "analysis_windows": [
            {"sequence_id": "s1", "scene_id": "scene_001", "start_ms": 0, "end_ms": 1500},
            {"sequence_id": "s2", "scene_id": "scene_002", "start_ms": 1501, "end_ms": 3000},
        ],
        "refinement_windows": [
            {"refinement_id": "r1", "scene_id": "scene_001", "start_ms": 1200, "end_ms": 1500,
             "sequence_ids": ["s1"], "reasons": ["BALL_PROXIMITY"]},
            {"refinement_id": "r2", "scene_id": "scene_002", "start_ms": 1501, "end_ms": 1800,
             "sequence_ids": ["s2"], "reasons": ["BALL_PROXIMITY"]},
        ],
    }
    out = dr.select_critical_windows(plan, {"sequences": []})
    assert len(out) == 2
    assert [r["scene_id"] for r in out] == ["scene_001", "scene_002"]
    assert out[0]["end_ms"] <= 1500
    assert out[1]["start_ms"] >= 1501


def test_a106_overlapping_refinement_windows_merge_without_duplicate_truth():
    plan = {
        "analysis_windows": [
            {"sequence_id": "s1", "scene_id": "scene_001", "start_ms": 0, "end_ms": 5000},
        ],
        "refinement_windows": [
            {"refinement_id": "r1", "scene_id": "scene_001", "start_ms": 1000, "end_ms": 2000,
             "sequence_ids": ["s1"], "reasons": ["A"]},
            {"refinement_id": "r2", "scene_id": "scene_001", "start_ms": 1800, "end_ms": 2600,
             "sequence_ids": ["s1"], "reasons": ["B"]},
        ],
    }
    out = dr.select_critical_windows(plan, {"sequences": []})
    assert len(out) == 1
    assert out[0]["start_ms"] == 1000
    assert out[0]["end_ms"] == 2600
    assert set(out[0]["source_refinement_ids"]) == {"r1", "r2"}


def test_a107_long_window_is_split_not_discarded():
    plan = {
        "analysis_windows": [
            {"sequence_id": "s1", "scene_id": "scene_001", "start_ms": 0, "end_ms": 20000},
        ],
        "refinement_windows": [
            {"refinement_id": "r1", "scene_id": "scene_001", "start_ms": 0, "end_ms": 20000,
             "sequence_ids": ["s1"], "reasons": ["LONG"]},
        ],
    }
    out = dr.select_critical_windows(plan, {"sequences": []})
    assert len(out) == 3
    assert out[0]["start_ms"] == 0
    assert out[-1]["end_ms"] == 20000
    assert all(r["end_ms"] - r["start_ms"] <= dr.MAX_DENSE_WINDOW_MS for r in out)
    assert all(out[i + 1]["start_ms"] == out[i]["end_ms"] + 1 for i in range(len(out) - 1))


def test_a108_fallback_time_is_flagged_and_not_exact_pts(monkeypatch):
    times = [0.0, 0.04, 0.08]
    # First 0ms is valid only for frame index 0. Later zero POS_MSEC forces
    # explicit frame_index/fps fallback in video_timebase.
    rows, _ = _decode(monkeypatch, times, 0, 80, fps=25.0, pos_ms=[0.0, 0.0, 0.0])
    assert [r["media_ms"] for r in rows] == [0, 40, 80]
    assert rows[0]["used_fallback"] is False
    assert rows[0]["time_authority"] == "ACTUAL_MEDIA_PTS"
    assert rows[1]["used_fallback"] is True
    assert rows[1]["time_authority"] == "FRAME_INDEX_FPS_FALLBACK"
    assert "frame_bgr" not in dr.compact_frame_meta(rows[1])
