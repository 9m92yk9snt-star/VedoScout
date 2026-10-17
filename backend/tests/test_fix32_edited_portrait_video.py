"""Edited portrait input: source coverage, synchronized views and missing links."""
from copy import deepcopy

import pytest

import action_evidence_review as inspection


def source_frames():
    return [{"media_ms": ms, "scene_id": "scene", "time_authority": "ACTUAL_MEDIA_PTS"}
            for ms in range(0, 8001, 17)]


def test_contact_detail_keeps_complete_overview_and_both_contact_neighborhoods():
    frames = source_frames()
    job = {"scene_id": "scene", "start_ms": 0, "end_ms": 8000,
           "has_contact_time": True, "search_centers_ms": [1500, 6000]}
    baseline = inspection.motion_frame_times({**job, "has_contact_time": False, "search_centers_ms": []}, frames)
    plan = inspection.motion_sampling_plan(job, frames)
    times = plan["media_ms"]
    assert set(baseline).issubset(times) and len(baseline) < len(times) <= 97
    assert times[0] == 0 and times[-1] == frames[-1]["media_ms"]
    assert set(times).issubset({f["media_ms"] for f in frames})
    assert max(b-a for a, b in zip(times, times[1:])) <= 136
    for center in (1500, 6000):
        detail = [ms for ms in times if abs(ms-center) <= 200]
        assert len(detail) >= 9 and max(b-a for a,b in zip(detail, detail[1:])) <= 51
    assert plan["canonical_authority"] is False


def test_detail_does_not_invent_frames_or_accept_a_foreign_scene():
    frames = source_frames()
    for f in frames:
        if 1400 <= f["media_ms"] <= 1600:
            f["scene_id"] = "foreign"
    job = {"scene_id": "scene", "start_ms": 0, "end_ms": 8000,
           "has_contact_time": True, "center_ms": 1500}
    times = inspection.motion_frame_times(job, frames)
    assert all(not 1400 <= ms <= 1600 for ms in times)


def test_early_contact_list_cannot_starve_a_later_measured_contact():
    frames = source_frames()
    job = {"scene_id": "scene", "start_ms": 0, "end_ms": 8000,
        "sequence_context": {"verified_contacts": [{"media_ms": ms} for ms in [200, 550, 900, 1250, 7000]]}}
    plan = inspection.motion_sampling_plan(job, frames)
    assert any(abs(ms-7000) < 20 for ms in plan["focuses"])
    assert len(plan["media_ms"]) <= 97


def test_portrait_views_retain_the_goal_and_map_both_panels_to_same_source_ball():
    import cv2
    import numpy as np
    import fix10a_vision_providers as vision
    image = np.full((960, 540, 3), 70, dtype=np.uint8)
    image[-20:, -20:] = (20, 100, 240)  # goal-side pixels outside the player crop
    candidate = {"body_id": "body_1", "local_track_id": "p1",
                 "box": {"x": .4, "y": .3, "w": .1, "h": .4}}
    frame = {"global_target": {"local_track_id": "p1"}, "players": [candidate]}
    canvas, maps, bodies = vision.motion_search_view(image, frame, [candidate])
    assert np.array_equal(canvas[-10, 530], image[-10, 530])
    assert [v["view_id"] for v in maps["views"]] == ["OVERVIEW", "DETAIL"]
    assert bodies[0]["box"]["x"] < candidate["box"]["x"]
    native = {"x": .43, "y": .68, "w": .012, "h": .009}
    for view in maps["views"]:
        roi, viewport = view["source_roi"], view["canvas_roi"]
        displayed = {"x": viewport["x"]+(native["x"]-roi["x"])/roi["w"]*viewport["w"],
            "y": viewport["y"]+(native["y"]-roi["y"])/roi["h"]*viewport["h"],
            "w": native["w"]/roi["w"]*viewport["w"], "h": native["h"]/roi["h"]*viewport["h"]}
        assert vision._native_search_box(displayed, maps) == pytest.approx(native)
    edge = maps["views"][0]["canvas_roi"]["w"]
    assert vision._native_search_box({"x": edge-.01, "y": .5, "w": .02, "h": .01}, maps) is None


def test_wide_video_keeps_the_existing_single_view():
    import numpy as np
    import fix10a_vision_providers as vision
    image = np.zeros((100, 180, 3), dtype=np.uint8)
    view, roi, _ = vision.motion_search_view(image, {}, [])
    assert view.shape == image.shape and "views" not in roi


def test_reference_gallery_selects_source_quality_and_variation_across_cuts():
    import base64
    import fix10a_vision_providers as vision
    bundle = vision.ShadowVisionProviders("fake", "references")
    times = [100, 200, 300, 40000, 45000]
    bundle._reference_gallery = {"source": "USER_SELECTED_SOURCE_PIXELS", "source_video_sha256": "source",
        "evidence_ms": times, "images": [base64.b64encode(str(t).encode()).decode() for t in times],
        "_reference_descriptors": [{"sharpness": 100, "native_height_px": 240,
            "aspect": .4, "descriptor": [v, v]} for v in [0, 0, 0, 1, -1]]}
    result = bundle._reference_for_window({"start_ms": 0, "end_ms": 200})
    assert result["evidence_ms"] == [100, 40000, 45000]
    assert result["number_required"] is False
    assert result["selection_strategy"] == "SOURCE_QUALITY_DIVERSITY_PROXIMITY"
    assert "_reference_descriptors" not in result
    assert len(bundle._reference_gallery["images"]) == 5


def test_sped_up_acceleration_retains_native_search_without_fabricating_physical_proof():
    import ball_trajectory as ball
    from test_fix15_r6_multiball_search import native_frames
    frames = native_frames()
    for i, (f, x) in enumerate(zip(frames, [.1, .11, .13, .178])):
        f["media_ms"] = 1000+20*i
        if f.get("camera_motion"):
            f["camera_motion"].update(from_media_ms=980+20*i, to_media_ms=1000+20*i)
        f["ball_candidates"][0]["box"]["x"] = x
    result = ball.reconstruct_ball_trajectory(frames)
    assert result[-1]["state"] == "PREDICTED_SHORT_GAP" and not result[-1]["proof_eligible"]
    search = result[-1]["search_candidates"]
    assert len(search) == 1 and search[0]["search_observations"] == 4
    assert search[0]["search_first_ms"] == 1000 and search[0]["proof_eligible"] is False
    assert result[-1]["motion_time_basis"] == "UPLOADED_MEDIA_SECONDS"
    assert result[-1]["real_time_speed_calibrated"] is False


def test_scene_change_resets_ball_tracks_even_without_a_duplicate_cut_flag():
    import ball_trajectory as ball
    from test_fix15_r6_multiball_search import native_frames
    frames = native_frames()
    frames[-1]["scene_id"] = "next_scene"
    result = ball.reconstruct_ball_trajectory(frames)
    assert result[-1]["cut_barrier"] and result[-1]["velocity"] is None
    assert all(c["search_observations"] == 1 for c in result[-1]["search_candidates"])


@pytest.mark.parametrize("missing,question", [("receiver", "RECEIVER"), ("shot", "SHOT"), ("outcome", "OUTCOME")])
def test_missing_video_link_requests_only_that_connection_with_full_existing_context(missing, question):
    import evidence_feedback as feedback
    import sequence_observation_context as context
    from test_fix31_temporal_video import motion_trace
    trace = motion_trace()
    obs = trace["action_inspections"][0]
    action = obs["video_actions"][0]
    if missing == "receiver":
        action.update(receiver_idx=None, receiver_body_id=None)
    elif missing == "shot":
        action.update(shot_idx=None, finisher_body_id=None)
    action.update(outcome_idx=None, outcome="UNKNOWN", outcome_visible=False, outcome_evidence_indices=[])
    requests = context.motion_review_requests({"actions": [action]}, obs["motion_clip"]["frame_source_ms"], obs["body_search_regions"])
    assert len(requests) == 1 and requests[0]["question"] == question
    assert requests[0]["canonical_authority"] is False
    obs["sequence_reasoning"] = {"review_requests": requests}
    result = feedback.build_plan([trace])
    assert result["selected"] == 1
    job = result["jobs"][0]
    assert job["missing_link_question"] == question
    assert job["start_ms"] <= requests[0]["anchor_media_ms"]
    assert job["end_ms"] == trace["decoded_frames"][-1]["media_ms"]
    assert job["end_ms"]-job["start_ms"] <= 8000
    assert len(job["requested_media_ms"]) <= 97


def test_missing_link_search_cannot_bridge_a_camera_cut():
    import evidence_feedback as feedback
    import sequence_observation_context as context
    from test_fix31_temporal_video import motion_trace
    trace = motion_trace()
    obs = trace["action_inspections"][0]
    action = obs["video_actions"][0]
    action.update(outcome_idx=None, outcome="UNKNOWN", outcome_visible=False, outcome_evidence_indices=[])
    obs["sequence_reasoning"] = {"review_requests": context.motion_review_requests(
        {"actions": [action]}, obs["motion_clip"]["frame_source_ms"], obs["body_search_regions"])}
    trace["decoded_frames"][84]["cut_barrier"] = True  # 3000 ms
    result = feedback.build_plan([trace])
    assert result["selected"] == 1 and result["jobs"][0]["end_ms"] < 3000


def test_complete_observed_scoring_chain_does_not_request_another_read():
    import sequence_observation_context as context
    from test_fix31_temporal_video import motion_trace
    obs = motion_trace()["action_inspections"][0]
    assert context.motion_review_requests({"actions": obs["video_actions"]},
        obs["motion_clip"]["frame_source_ms"], obs["body_search_regions"]) == []


def test_a_new_missing_link_question_can_reuse_the_same_context_frames_once():
    import evidence_feedback as feedback
    import sequence_observation_context as context
    from test_fix31_temporal_video import motion_trace
    trace = motion_trace()
    obs = trace["action_inspections"][0]
    action = obs["video_actions"][0]
    action.update(outcome_idx=None, outcome="UNKNOWN", outcome_visible=False, outcome_evidence_indices=[])
    obs["sequence_reasoning"] = {"review_requests": context.motion_review_requests(
        {"actions": [action]}, obs["motion_clip"]["frame_source_ms"], obs["body_search_regions"])}
    first = feedback.build_plan([trace])["jobs"][0]
    obs["requested_media_ms"] = first["requested_media_ms"]
    plan = feedback.build_plan([trace])
    assert plan["selected"] == 1 and plan["jobs"][0]["missing_link_question"] == "OUTCOME"
    trace["evidence_feedback"] = {"round": 1}
    assert feedback.build_plan([trace])["selected"] == 0


@pytest.mark.usefixtures("inline_support_vision")
def test_production_portrait_control_is_mapped_back_to_the_original_pixels(monkeypatch):
    import numpy as np
    from types import SimpleNamespace
    import fix10a_vision_providers as vision
    from test_fix29_connected_sequences import frame
    frames = [frame(ms) for ms in range(0, 2001, 20)]
    native = {"x": .43, "y": .68, "w": .012, "h": .009}
    async def reader(_key, _session, _clip, times, manifest, **_kwargs):
        rows = []
        for i, geometry in enumerate(manifest):
            overview = geometry["source_roi"]["views"][0]["canvas_roi"]
            source_box = {**native, "x": native["x"]*overview["w"], "w": native["w"]*overview["w"]}
            rows.append({"idx": i+1, "balls": [{"box": source_box, "confidence": "high", "active_ball": True,
                "control_visible": True, "control_body_id": geometry["source_bodies"][0]["body_id"]}], "selected_body_ids": []})
        return {"status": "COMPLETED", "frames": rows, "observation_protocol": "SOURCE_INDEXED_MOTION_CLIP_V1"}
    monkeypatch.setattr(vision, "read_action_video_evidence", reader)
    monkeypatch.setattr(vision, "_read_frames", lambda _path, times: {
        ms: (ms, np.full((240, 140, 3), 64, dtype=np.uint8)) for ms in times})
    bundle = vision.ShadowVisionProviders("fake", "portrait-control")
    bundle._native_goal_detector = SimpleNamespace(ok=False)
    result = bundle.action_evidence_provider("video.mp4", {"scene_id": "scene", "start_ms": 0,
        "end_ms": 2000, "inspection_id": "job", "center_ms": 1000}, frames)
    assert result["video_control_observations"]
    assert all(r["ball_box"] == pytest.approx(native) for r in result["video_control_observations"])
