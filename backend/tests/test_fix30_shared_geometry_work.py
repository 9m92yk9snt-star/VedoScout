"""Shared observations survive transport without repeating their pixel work."""
from copy import deepcopy
import json
from types import SimpleNamespace

import numpy as np
import pytest
import cv2

import ball_contact_engine as contacts
import dense_track_refinement as dense
import fix10a_ball_proof_gate as ball_gate
import fix10a_goal_direction as direction
import fix10a_vision_providers as vision
import shot_outcome_engine as outcomes
import temporal_ball_search as temporal
import native_ball_reappearance as native
import short_occlusion_contact_recovery as occlusion


def scene_payload(times):
    return {
        "field_side_protocol": "VISIBLE_PLAYABLE_PITCH_V1",
        "frames": [{"idx": i, "visible": True, "confidence": "high",
            "p1": {"x": .9, "y": .3}, "p2": {"x": .9, "y": .7},
            "field_side_visible": True, "field_side": {"x": .7, "y": .5},
            "field_side_confidence": "high"} for i in range(1, len(times)+1)],
        "ball_evidence": [{"idx": i, "ball_visible": True, "confidence": "high",
            "relation": "FIELD_SIDE" if i <= (2 if len(times) > 3 else 1) else "BEYOND_LINE_INSIDE_MOUTH" if i == len(times)
                        else "ON_OR_STRADDLING_LINE",
            "ball_box": {"x": .8 if i <= (2 if len(times) > 3 else 1) else .94 if i == len(times) else .89,
                         "y": .48, "w": .02, "h": .02}} for i in range(1, len(times)+1)],
        "same_ball_continuity": True, "first_crossing_idx": len(times),
        "crossing": "CROSSED", "crossing_confidence": "high",
    }


@pytest.mark.usefixtures("inline_support_vision")
def test_one_image_read_supplies_goal_and_field_geometry_through_to_physical_outcome(monkeypatch):
    image = np.zeros((80, 120, 3), np.uint8)
    calls = []
    def frames(_video, times):
        return {ms: (ms, image) for ms in times}
    async def reader(_key, _session, _paths, times):
        calls.append(times)
        return vision.parse_goal_scene_response(json.dumps(scene_payload(times)), times)
    monkeypatch.setattr(vision, "_read_frames", frames)
    monkeypatch.setattr(vision, "read_goal_scene_evidence", reader)
    assert not hasattr(direction, "_read_frames")  # duplicate decoder/reader is retired
    bundle = vision.build_shadow_providers("key", "session", "video.mp4")
    provider = direction.GoalDirectionProvider(bundle.goal_geometry_provider, "key", "session", "video.mp4")
    strike = {"media_ms": 1000, "scene_id": "scene"}
    geometry = provider({"dense_window_id": "w", "end_ms": 2000}, strike)
    assert geometry["field_side_status"] == "VERIFIED"
    assert provider.field_side_calls == 0 and len(calls) == 1
    physical = outcomes.reconstruct_post_strike_outcome(strike, [], {"touches": []}, goal_geometry=geometry)
    physical = direction.apply_direction_gate(physical, [], geometry)
    physical = ball_gate.apply_ball_proof_gate(physical, [])
    assert physical["goal_plane_crossing"]["status"] == "VERIFIED", physical["goal_plane_crossing"]
    assert physical["direction_gate"]["status"] == "VERIFIED"
    assert provider({"dense_window_id": "w", "end_ms": 2000}, strike)["review_delivery"]["status"] == "REUSED"
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["hidden", "low_confidence", "nan", "outside", "boolean", "no_goal"])
def test_shared_pitch_observation_cannot_be_guessed_from_a_goal_verdict(failure):
    data = scene_payload([1000, 1100, 1200])
    for row in data["frames"]:
        if failure == "hidden": row["field_side_visible"] = False
        elif failure == "low_confidence": row["field_side_confidence"] = "low"
        elif failure == "nan": row["field_side"]["x"] = float("nan")
        elif failure == "outside": row["field_side"]["x"] = 1.1
        elif failure == "boolean": row["field_side"]["x"] = True
        elif failure == "no_goal": row["visible"] = False
    result = vision.parse_goal_scene_response(json.dumps(data), [1000, 1100, 1200])
    assert result["field_side_status"] == "UNRESOLVED" and not result["field_side_by_ms"]
    provider = direction.GoalDirectionProvider(lambda *_: {**result, "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW"},
                                               "key", "session", "video.mp4")
    # A completed image read with hidden pitch is not repeated under a second prompt.
    result = provider({}, {"media_ms": 1000})
    assert result["field_side_status"] == "UNRESOLVED" and provider.field_side_calls == 0


def test_native_goal_search_reuses_raw_pixels_and_keeps_proposal_dependent_roi_work(monkeypatch, tmp_path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"source fingerprint only; no decoding")
    detector = SimpleNamespace(ok=True, model_sha256="a" * 64)
    forwards, regions = [], []
    monkeypatch.setattr(dense, "_default_detector", lambda: detector)
    def detect(_detector, image, include_a7_support=False):
        forwards.append(image.shape)
        return ([{"box": {"x": .2, "y": .3, "w": .1, "h": .2}}], [], [])
    monkeypatch.setattr(dense, "_detect_dense_people_and_ball", detect)
    monkeypatch.setattr(vision, "_native_ball_roi", lambda _d, _im, box: (regions.append(box.copy()) or [], None))
    bundle = vision.build_shadow_providers("key", "session", str(video))
    read = bundle._native_goal_context()["detect_frame"]
    image = np.zeros((80, 120, 3), np.uint8)
    first = read(image, {"x": .2})
    first[0][0]["box"]["x"] = .9
    assert read(image.copy(), {"x": .3})[0][0]["box"]["x"] == .2
    assert len(forwards) == 1 and regions == [{"x": .2}, {"x": .3}]
    image[0, 0, 0] = 1
    read(image, {"x": .2})
    assert len(forwards) == 2


def test_ball_holder_work_is_shared_across_candidate_players_without_changing_contacts(monkeypatch):
    players = [{"local_track_id": f"p{i}", "association_state": "VERIFIED_LOCAL",
                "box": {"x": .1+i*.09, "y": .2, "w": .08, "h": .3}} for i in range(8)]
    frames = [{"media_ms": ms, "scene_id": "scene", "players": players,
               "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False} for ms in (960, 1000, 1040)]
    balls = [{"media_ms": ms, "state": "MEASURED", "proof_eligible": True,
              "time_authority": "ACTUAL_MEDIA_PTS", "box": {"x": x, "y": .48, "w": .02, "h": .02}}
             for ms, x in ((960, .13), (1000, .13), (1040, .23))]
    original = deepcopy((frames, balls))
    reads = []
    holder = contacts._likely_holder
    monkeypatch.setattr(contacts, "_likely_holder", lambda *args: reads.append(1) or holder(*args))
    cached = contacts.detect_contact_candidates(frames, balls)
    shared_reads = len(reads)
    transition = contacts._possession_transition
    monkeypatch.setattr(contacts, "_possession_transition", lambda *args, **_kw: transition(*args))
    reads.clear()
    assert contacts.detect_contact_candidates(frames, balls) == cached
    assert len(reads) >= shared_reads*4
    assert (frames, balls) == original


def test_identical_native_sizes_do_not_repeat_pixel_descriptors(monkeypatch):
    from test_fix15_native_goal_reappearance import canvas_with
    box = {"x": .5, "y": .5, "w": .015, "h": .02}
    image = canvas_with(box)
    patch = native._crop(image, box)
    reference = native._descriptor(patch)
    calls = []
    original = native._descriptor
    def descriptor(pixels):
        calls.append((pixels.__array_interface__["data"][0], pixels.shape))
        return original(pixels)
    monkeypatch.setattr(native, "_descriptor", descriptor)
    monkeypatch.setattr(temporal, "SCALES", (.4, .55, .75))
    repeated_sizes = temporal._proposals(image, [reference], box, [patch])
    assert repeated_sizes and len(calls) == len(set(calls))
    repeated_work = len(calls)
    calls.clear()
    monkeypatch.setattr(temporal, "SCALES", (.4,))
    assert temporal._proposals(image, [reference], box, [patch]) == repeated_sizes
    assert len(calls) == repeated_work


def test_identical_appearance_templates_share_one_correlation_without_changing_candidates(monkeypatch):
    from test_fix15_native_goal_reappearance import canvas_with
    box = {"x": .5, "y": .5, "w": .03, "h": .04}
    image = canvas_with(box)
    patch = native._crop(image, box)
    reference = native._descriptor(patch)
    calls = []
    original = cv2.matchTemplate
    monkeypatch.setattr(cv2, "matchTemplate", lambda *args, **kw: calls.append(1) or original(*args, **kw))
    repeated = temporal._proposals(image, [reference]*3, box, [patch, patch.copy(), patch.copy()])
    repeat_work = len(calls)
    calls.clear()
    assert temporal._proposals(image, [reference], box, [patch]) == repeated
    assert len(calls) == repeat_work and repeat_work > 0


@pytest.mark.parametrize("mode", ["exact_tap", "continuous_tap"])
def test_flow_does_not_decode_when_no_existing_detector_endpoint_can_use_it(monkeypatch, mode):
    import test_fix10a4_short_occlusion_recovery as fixture
    frames = fixture._exact_tap_fixture(a3_reacquisition=False) if mode == "exact_tap" else fixture._tap_continuity_release_fixture()
    if mode == "continuous_tap":
        for frame in frames:
            for candidate in frame["a7_ball_support_candidates"]:
                candidate.update(a3_eligible=False, support_only=True)
    monkeypatch.setattr(occlusion, "_track_support_with_flow", lambda *a, **k: pytest.fail("unusable video decode"))
    recover = occlusion._exact_tap_support_recoveries if mode == "exact_tap" else occlusion._tap_continuity_support_recoveries
    verified, _diagnostic = recover(frames, fixture._empty_contacts(), "unused.mp4")
    assert not verified


@pytest.mark.parametrize("first_failure", [False, True])
def test_repeated_release_rows_reuse_completed_flow_but_retry_transient_failure(monkeypatch, first_failure):
    import test_fix10a4_short_occlusion_recovery as fixture
    frames, contact_rows = fixture._exact_tap_measured_release_fixture()
    duplicate = deepcopy(contact_rows["contacts"][-1])
    duplicate["contact_id"] += "-overlap"
    contact_rows["contacts"].append(duplicate)
    original = occlusion._track_support_with_flow
    calls = []
    def track(*args, **kwargs):
        calls.append(1)
        if first_failure and len(calls) == 1:
            return {"status": "UNRESOLVED", "reason": "TRANSIENT_TEST_READER_FAILURE"}
        return original(*args, **kwargs)
    monkeypatch.setattr(occlusion, "_track_support_with_flow", track)
    verified, _diagnostic = occlusion._exact_tap_measured_release_recoveries(
        frames, contact_rows, "synthetic.mp4", fixture._flow_provider())
    assert len(verified) == 1
    assert len(calls) == (3 if first_failure else 2)
