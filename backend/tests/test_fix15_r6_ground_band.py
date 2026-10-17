"""Synthetic detector-only regressions; no video or expected event labels."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
import ball_trajectory as bt
import dense_track_refinement as dense


def prediction(*objects):
    raw = np.zeros((1, 84, max(1, len(objects))), dtype=np.float32)
    for index, (geometry, class_id, confidence) in enumerate(objects):
        raw[0, :4, index] = geometry
        raw[0, 4 + class_id, index] = confidence
    return raw


PERSON = ([160, 300, 60, 100], 0, .9)
SPARE = ([10, 350, 8, 8], 32, .4)
DETAIL = ([400, 100, 10, 10], 32, .08)


class Net:
    def __init__(self, *outputs):
        self.outputs = iter(outputs)
        self.calls = 0

    def setInput(self, blob):
        assert blob.shape == (1, 3, 640, 640)

    def forward(self):
        self.calls += 1
        return next(self.outputs)


class Detector:
    ok = True

    def __init__(self, *outputs):
        self.net = Net(*outputs)


def portrait():
    return np.zeros((1280, 640, 3), np.uint8)


def test_person_refinement_keeps_person_outputs_while_ball_only_detail_discards_unused_people():
    raw = prediction(PERSON, DETAIL)
    person_detector, ball_detector = Detector(raw), Detector(raw)
    people, balls = dense._detect_dense_people_and_ball(person_detector, portrait(), _detail_pass=True)
    unused, same_balls = dense._detect_dense_people_and_ball(ball_detector, portrait(),
        _detail_pass=True, _ball_only=True)
    assert len(people) == 1 and unused == []
    assert same_balls == balls and len(balls) == 1
    assert person_detector.net.calls == ball_detector.net.calls == 1


def test_other_whole_frame_ball_does_not_skip_detail_search():
    detector = Detector(prediction(PERSON, SPARE), prediction(DETAIL))
    people, balls = dense._detect_dense_people_and_ball(detector, portrait())
    assert len(people) == 1
    assert len(balls) == 2
    assert detector.net.calls == 2
    assert "source" not in balls[0]
    assert balls[1]["source"] == "NATIVE_GROUND_BAND_DETECTOR"
    assert balls[0]["box"]["x"] < .05
    assert balls[1]["box"]["x"] > .6
    assert not any("global_target_id" in b or "event" in b for b in balls)


def test_detail_coordinates_map_back_to_full_portrait():
    detector = Detector(prediction(PERSON), prediction(DETAIL))
    _, balls = dense._detect_dense_people_and_ball(detector, portrait())
    box = balls[0]["box"]
    assert box == pytest.approx({"x": 395 / 640, "y": (597 + 95) / 1280,
                                 "w": 10 / 640, "h": 10 / 1280})
    assert detector.net.calls == 2


def test_cross_pass_duplicate_keeps_original_coordinates_and_confidence():
    duplicate = ([20, 99, 16, 16], 32, .95)
    detector = Detector(prediction(PERSON, SPARE), prediction(duplicate))
    _, balls = dense._detect_dense_people_and_ball(detector, portrait())
    assert len(balls) == 1
    assert balls[0]["confidence"] == pytest.approx(.4)
    assert balls[0]["box"] == pytest.approx(
        {"x": 6 / 320, "y": 346 / 640, "w": 8 / 320, "h": 8 / 640})
    assert "source" not in balls[0]
    assert detector.net.calls == 2


@pytest.mark.parametrize("confidence, expected", [(.029, 0), (.04, 1)])
def test_detail_preserves_existing_native_ball_floor(confidence, expected):
    detector = Detector(prediction(PERSON),
                        prediction((DETAIL[0], 32, confidence)))
    _, balls = dense._detect_dense_people_and_ball(detector, portrait())
    assert len(balls) == expected
    assert dense.DENSE_BALL_CONF_T == .03


def test_detail_other_top_class_does_not_supply_ball_truth():
    second = prediction(([400, 100, 10, 10], 0, .8))
    second[0, 4 + 32, 0] = .09
    detector = Detector(prediction(PERSON), second)
    _, balls = dense._detect_dense_people_and_ball(detector, portrait())
    assert balls == []


def test_detail_pass_cannot_recurse():
    detector = Detector(prediction(PERSON, SPARE))
    _, balls = dense._detect_dense_people_and_ball(detector, portrait(), _detail_pass=True)
    assert len(balls) == 1
    assert detector.net.calls == 1


@pytest.mark.parametrize("shape", [(640, 640, 3), (480, 1280, 3)])
def test_non_portrait_has_only_one_forward(shape):
    detector = Detector(prediction(PERSON, SPARE))
    dense._detect_dense_people_and_ball(detector, np.zeros(shape, np.uint8))
    assert detector.net.calls == 1


def test_no_detected_players_has_only_one_forward():
    detector = Detector(prediction(SPARE))
    _, balls = dense._detect_dense_people_and_ball(detector, portrait())
    assert len(balls) == 1
    assert detector.net.calls == 1


def test_unbounded_player_ground_band_is_not_searched():
    people = (([160, 80, 50, 80], 0, .9),
              ([160, 560, 50, 80], 0, .9))
    detector = Detector(prediction(*people))
    _, balls = dense._detect_dense_people_and_ball(detector, portrait())
    assert balls == []
    assert detector.net.calls == 1


@pytest.mark.parametrize("geometry", [
    [400, 100, 70, 10],  # too wide
    [400, 100, 10, 70],  # too tall
    [650, 100, 10, 10],  # padded area, off the native image
])
def test_detail_non_ball_sized_or_off_image_box_is_rejected(geometry):
    detector = Detector(prediction(PERSON), prediction((geometry, 32, .7)))
    _, balls = dense._detect_dense_people_and_ball(detector, portrait())
    assert balls == []


def test_a7_weak_support_stays_separate_from_both_native_passes():
    weak = ([250, 350, 8, 8], 32, .01)
    detector = Detector(prediction(PERSON, SPARE, weak), prediction(DETAIL))
    _, balls, support = dense._detect_dense_people_and_ball(
        detector, portrait(), include_a7_support=True)
    assert len(balls) == 2
    assert len(support) == 2
    assert all(b["confidence"] > .03 for b in balls)
    assert all(b["proof_eligible"] is False for b in support)
    weak_row = min(support, key=lambda b: b["confidence"])
    assert weak_row["support_only"] is True
    assert weak_row["a3_eligible"] is False


def test_competing_measured_proposals_do_not_gain_same_ball_authority():
    anchor = {"media_ms": 1000, "state": "MEASURED", "proof_eligible": True,
              "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False,
              "box": {"x": .45, "y": .5, "w": .02, "h": .01},
              "confidence": .5}
    frames = [{"media_ms": ms, "scene_id": "s", "camera_state": "AFFINE_VERIFIED",
               "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False,
               "ball_candidates": [
                   {"box": {"x": x, "y": .5, "w": .02, "h": .01},
                    "confidence": conf}
                   for x, conf in ((.43, .95), (.47, .08))]}
              for ms in (1017, 1034, 1051, 1085)]
    path = bt.reconstruct_ball_trajectory_from_release_anchor(frames, anchor, scene_id="s")
    assert [r["media_ms"] for r in path] == [1000]
