"""FIX09B production-detector ownership and shadow isolation."""
import hashlib
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

import cv_detect
import football_scene_graph as fsg
import player_identity_timeline as pit
import video_timebase


BACKEND = Path(__file__).resolve().parents[1]


class _ModelPath:
    def exists(self):
        return True

    def stat(self):
        return SimpleNamespace(st_size=2_000_000)

    def __str__(self):
        return "/tmp/test-yolov8n.onnx"


class _Cap:
    def __init__(self, *, width=1280, height=720):
        self.width = width
        self.height = height
        self.released = False

    def isOpened(self):
        return True

    def get(self, prop):
        if prop == cv2.CAP_PROP_FPS:
            return 25.0
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return float(self.width)
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(self.height)
        return 0.0

    def release(self):
        self.released = True


def test_explicit_production_enable_overrides_legacy_shadow_switch(monkeypatch):
    loaded = []
    monkeypatch.setattr(cv_detect, "DETECTOR_ENABLED", False)
    monkeypatch.setattr(cv_detect, "MODEL_PATH", _ModelPath())
    monkeypatch.setattr(
        cv_detect.cv2.dnn, "readNetFromONNX",
        lambda path: loaded.append(path) or object(),
    )

    assert cv_detect.PersonDetector().ok is False
    assert cv_detect.PersonDetector(enabled=False).ok is False
    production = cv_detect.PersonDetector(enabled=True)
    assert production.ok is True
    assert production.enabled is True
    assert loaded == ["/tmp/test-yolov8n.onnx"]


def test_repository_onnx_model_loads_and_matches_parser_contract():
    """Real checkout smoke: pinned bytes load and the shared parser can run."""
    model = cv_detect.MODEL_PATH
    assert model.is_file()
    data = model.read_bytes()
    assert len(data) == 12_851_145
    git_blob = hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data,
        usedforsecurity=False,
    ).hexdigest()
    assert git_blob == "0d750ad826a94e490db3371571bd0ddab084bf83"

    detector = cv_detect.PersonDetector(enabled=True)
    assert detector.ok is True
    people, balls = fsg._detect_people_and_ball(
        detector, np.zeros((360, 640, 3), dtype=np.uint8))
    assert isinstance(people, list)
    assert isinstance(balls, list)


def test_scene_graph_uses_its_own_detector_gate(monkeypatch):
    seen = []

    class Detector:
        def __init__(self, *, enabled=None):
            seen.append(enabled)
            self.ok = bool(enabled)

    monkeypatch.setattr(cv_detect, "PersonDetector", Detector)
    monkeypatch.setattr(cv2, "VideoCapture", lambda _path: _Cap())
    monkeypatch.setattr(
        video_timebase, "grab_frame_time_seconds", lambda _cap, _fps: (False, 0.0, 0),
    )
    monkeypatch.setattr(fsg, "DETECTOR_ENABLED", True)

    result = fsg.build_scene_graph("video.mp4", {})
    assert seen == [True]
    assert result["status"] == "empty"


def test_scene_graph_reports_intentional_production_disable(monkeypatch):
    class Detector:
        def __init__(self, *, enabled=None):
            self.ok = bool(enabled)

    monkeypatch.setattr(cv_detect, "PersonDetector", Detector)
    monkeypatch.setattr(cv2, "VideoCapture", lambda _path: _Cap())
    monkeypatch.setattr(fsg, "DETECTOR_ENABLED", False)

    result = fsg.build_scene_graph("video.mp4", {})
    assert result == {"version": fsg.VERSION, "status": "skipped",
                      "reason": "detector_disabled"}


def test_identity_timeline_never_inherits_shadow_detector_disable(monkeypatch):
    seen = []

    class Detector:
        def __init__(self, *, enabled=None):
            seen.append(enabled)
            self.ok = True

    monkeypatch.setattr(cv_detect, "PersonDetector", Detector)
    monkeypatch.setattr(cv2, "VideoCapture", lambda _path: _Cap())
    monkeypatch.setattr(
        __import__("cv_shadow"), "_build_tap_references",
        lambda *_args, **_kwargs: ([], []),
    )

    result = pit.build_identity_timeline(
        "video.mp4", {"anchors": [{"t": 1.0, "box": {"x": .1, "y": .1,
                                                        "w": .1, "h": .3}}]},
    )
    assert seen == [True]
    assert result["reason"] == "too_few_references"


def test_server_skips_redundant_shadow_pass_after_unified_preparation():
    src = (BACKEND / "server.py").read_text()
    body = src.split("async def generate_full_report_task", 1)[1].split("\nasync def ", 1)[0]
    assert "cv_shadow.SHADOW_ENABLED and _unified_prepared is None" in body
