"""FIX14 recovery contracts; expected results never supply event proof."""
from copy import deepcopy
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import action_evidence_review as inspection
import dense_track_refinement as dense
import fix10a_vision_providers as vision
import football_sequence_intelligence as sequence
import report_fact_authority as facts
import verified_stats as stats
import unified_identity_authority as authority
import jersey_consensus as jersey
from test_fix13_action_inspections import frame, window, action
from test_fix09b2_sequence_intelligence import frame as broad_frame, graph
from test_fix10a2_dense_track_refinement import _frame, _graph, _det, BASE
from test_fix09b0_unified_identity_authority import _jersey_handoff_fixture


def test_missing_semantic_scene_inspects_the_entire_physical_window_with_same_budget():
    plan = inspection.build_plan([window(start=19466, end=25466)], {}, budget=1)
    job = plan["jobs"][0]
    times = inspection.frame_times(job, [frame(ms) for ms in range(19466, 25467, 10)])
    assert plan["selected"] == 1
    assert times[0] == 19466 and times[-1] == 25466
    assert any(ms > 23680 for ms in times)
    assert len(times) == inspection.MAX_ACTION_FRAMES
    assert not job["source_action_ids"] and not job["has_contact_time"]


def test_later_model_shot_hint_does_not_exclude_the_earlier_scoring_pass():
    analysis = {"sequences": [{"scene_id": "scene", "actions": [action(49600, 52000, "SHOT", 50000)]}]}
    plan = inspection.build_plan([window(start=47331, end=52931)], analysis, budget=1)
    job = plan["jobs"][0]
    times = inspection.frame_times(job, [frame(ms) for ms in range(47331, 52932, 10)])
    assert (job["start_ms"], job["end_ms"]) == (47331, 52931)
    assert job["center_ms"] == 50000 and 47331 in times and 52931 in times
    assert any(ms < 49000 for ms in times)
    assert len(times) <= inspection.MAX_ACTION_FRAMES and plan["selected"] == 1
    assert "kind" not in job and "expected_outcome" not in job


def test_semantic_identity_gap_is_searched_without_granting_player_identity():
    frames = [broad_frame(ms, scene="missing", target_status="UNRESOLVED", target_id=None, candidates=[])
              for ms in range(19466, 25467, 1000)]
    before = deepcopy(frames)
    plan = sequence.build_sequence_plan(graph(frames))
    assert [(w["start_ms"], w["end_ms"]) for w in plan["analysis_windows"]] == [(19466, 25466)]
    assert plan["analysis_windows"][0]["coverage_reason"] == "TARGET_IDENTITY_GAP_RECALL"
    assert plan["analysis_windows"][0]["verified_frames"] == 0
    assert frames == before


def test_scene_tail_after_target_loss_has_search_coverage_and_cannot_cross_cut():
    frames = [broad_frame(0), broad_frame(1000)] + [
        broad_frame(ms, target_status="UNRESOLVED", target_id=None, candidates=[])
        for ms in (4000, 8000, 12000)] + [broad_frame(12200, scene="next")]
    plan = sequence.build_sequence_plan(graph(frames))
    first = [w for w in plan["analysis_windows"] if w["scene_id"] == "scene_001"]
    assert first[0]["start_ms"] == 0 and first[-1]["end_ms"] == 12000
    assert all(a["end_ms"] >= b["start_ms"] for a, b in zip(first, first[1:]))
    assert all(w["end_ms"] <= 12000 for w in first)
    assert all(w["end_ms"] - w["start_ms"] <= sequence.MAX_ANALYSIS_WINDOW_MS for w in first)


def test_index_selection_uses_exact_native_body_and_still_requires_independent_number_reader(monkeypatch):
    original = [frame(1000), frame(1300)]
    calls = []
    monkeypatch.setattr(inspection, "frame_times", lambda *_: [1000, 1300])
    monkeypatch.setattr(vision, "_read_frames", lambda _v, times: {
        ms: (ms, np.zeros((120, 120, 3), np.uint8)) for ms in times})
    monkeypatch.setattr(vision, "_write_jpg", lambda path, _image: path.write_bytes(b"annotated"))
    async def read(_key, _session, paths, times, body_candidates):
        calls.append(body_candidates)
        assert all(set(b) == {"body_id", "box"} for row in body_candidates for b in row["bodies"])
        return {"status": "COMPLETED", "frames": [{"idx": i + 1,
            "selected_body_ids": ["body_1", "body_1", "body_999"],
            "jersey_bodies": [{"box": {"x": .8, "y": .8, "w": .1, "h": .1}}],
            "player_number": "15", "goal": True} for i in range(len(times))]}
    monkeypatch.setattr(vision, "read_action_pixel_evidence", read)
    bundle = vision.ShadowVisionProviders("test", "ids")
    job = {"inspection_id": "ids", "scene_id": "scene", "start_ms": 900, "end_ms": 1500}
    observed = bundle.action_evidence_provider("unused", job, original)
    applied = inspection.apply_observations(original, observed, "ids")
    assert len(applied["jersey_requests"]) == 2 and not applied["binding_rejections"]
    assert all(r["box"] == original[0]["players"][0]["box"] for r in applied["jersey_requests"])
    assert all(r["expected_jersey_number"] is None for r in applied["jersey_requests"])
    assert all(f["global_target"]["proof_eligible"] is False for f in applied["frames"])
    assert not applied["added_ball_candidates"]
    assert bundle.action_evidence_provider("unused", job, original) == observed
    assert len(calls) == 1
    moved = deepcopy(original)
    moved[0]["players"][0]["box"]["x"] += .01
    bundle.action_evidence_provider("unused", job, moved)
    assert len(calls) == 2  # old IDs must not be rebound to changed geometry


def test_portrait_search_roi_maps_ball_and_body_coordinates_to_exact_native_pixels():
    image = np.zeros((1920, 1080, 3), np.uint8)
    source = frame()
    source["players"][0]["box"] = {"x": .2, "y": .5, "w": .1, "h": .1}
    candidates = inspection.measured_body_candidates(source)
    view, roi, displayed = vision._action_search_view(image, source, candidates)
    assert view.shape[1] == 1080 and view.shape[0] < 1920
    assert vision._native_search_box(displayed[0]["box"], roi) == pytest.approx(candidates[0]["box"])
    native_ball = {"x": .4, "y": .6, "w": .01, "h": .005}
    displayed_ball = {**native_ball, "y": (native_ball["y"] - roi["y"]) / roi["h"],
                      "h": native_ball["h"] / roi["h"]}
    assert vision._native_search_box(displayed_ball, roi) == pytest.approx(native_ball)
    assert vision._native_search_box({k: str(v) for k, v in displayed_ball.items()}, roi) == pytest.approx(native_ball)
    assert vision._native_search_box({**displayed_ball, "x": float("nan")}, roi) is None
    assert vision._native_search_box(None, roi) is None
    assert not image.any()  # annotations cannot leak into independent readers
    _, full_roi, _ = vision._action_search_view(image, {}, [])
    assert full_roi == {"x": 0., "y": 0., "w": 1., "h": 1.}
    _, landscape_roi, _ = vision._action_search_view(np.zeros((720, 1080, 3), np.uint8), source, candidates)
    assert landscape_roi == full_roi


def test_pixel_provider_remaps_search_ball_before_native_corroboration(monkeypatch):
    frames = [frame(1000), frame(1300)]
    for f in frames: f["players"][0]["box"] = {"x": .2, "y": .5, "w": .1, "h": .1}
    monkeypatch.setattr(inspection, "frame_times", lambda *_: [1000, 1300])
    monkeypatch.setattr(vision, "_read_frames", lambda _v, times: {
        ms: (ms, np.zeros((1920, 1080, 3), np.uint8)) for ms in times})
    monkeypatch.setattr(vision, "_write_jpg", lambda *_: True)
    roi_seen, proposals = [], []
    async def reader(_key, _session, _paths, _times, body_candidates):
        roi_seen.extend(r["source_roi"] for r in body_candidates)
        return {"status": "COMPLETED", "frames": [{"idx": 1, "balls": [
            {"confidence": "high", "box": {"x": .4, "y": .5, "w": .01, "h": .01}}]}]}
    monkeypatch.setattr(vision, "read_action_pixel_evidence", reader)
    monkeypatch.setattr(vision, "corroborate_ball_pixels", lambda _d, image, box: proposals.append((image.shape, box)) or [])
    result = vision.ShadowVisionProviders("test", "roi").action_evidence_provider("unused", {
        "inspection_id": "roi", "scene_id": "scene", "start_ms": 900, "end_ms": 1400}, frames)
    assert proposals[0][0] == (1920, 1080, 3)
    assert proposals[0][1]["y"] == pytest.approx(roi_seen[0]["y"] + .5 * roi_seen[0]["h"])
    assert proposals[0][1]["h"] == pytest.approx(.01 * roi_seen[0]["h"])
    assert not result["frames"][0]["ball_candidates"]  # a proposal is not native proof


@pytest.mark.parametrize("change", ["overlap", "ambiguous", "duplicate"])
def test_unsafe_measured_body_is_not_an_indexed_crop_candidate(change):
    row = frame()
    if change == "ambiguous":
        row["players"][0]["association_state"] = "HYPOTHESES"
    else:
        other = deepcopy(row["players"][0])
        other["local_track_id"] = "p2"
        if change == "overlap": other["box"]["x"] += .02
        row["players"].append(other)
    assert inspection.measured_body_candidates(row) == []


@pytest.mark.parametrize("reverse", [False, True])
def test_two_tracks_competing_for_one_body_cannot_choose_identity_by_order(monkeypatch, reverse):
    source = _graph()
    second = deepcopy(source["frames"][0]["players"][0])
    second["local_track_id"] = "p002"
    source["frames"][0]["players"].append(second)
    if reverse: source["frames"][0]["players"].reverse()
    monkeypatch.setattr(dense.uia, "resolve_target_at", lambda *_a, **_k: (None, "TARGET_GAP"))
    result = dense.refine_window([_frame(1050)], source, {}, "scene_001",
        detector_fn=lambda _image: ([_det(BASE)], []),
        camera_estimator=lambda *_: (np.array([[1., 0., 0.], [0., 1., 0.]]), "ok"))
    player = result["frames"][0]["players"][0]
    assert player["association_state"] == "HYPOTHESES"
    assert player["local_track_id"] is None
    assert player["candidate_local_track_ids"] == ["p001", "p002"]
    assert not result["frames"][0]["global_target"]["proof_eligible"]


def test_same_clip_with_different_scene_numbering_can_bind_independent_jersey_proof():
    source, frames, graph, votes = _jersey_handoff_fixture()
    frames[0]["scene_id"] = graph["touches"][0]["scene_id"] = "physical_scene_004"
    before = deepcopy(source)
    result = authority.apply_verified_jersey_handoff(source, frames, graph, votes)
    assert result["touches"][0]["global_target_id"] == authority.GLOBAL_TARGET_ID
    assert result["touches"][0]["global_target_resolution"]["scene_binding"] == "CANONICAL_TIME_BOUNDS_AND_PHYSICAL_CUTS"
    assert source == before


@pytest.mark.parametrize("barrier", ["canonical_cut", "physical_scene", "physical_cut", "unknown_bounds"])
def test_scene_mapping_correction_cannot_reidentify_across_cut_or_unknown_scene(barrier):
    source, frames, graph, votes = _jersey_handoff_fixture()
    frames[0]["scene_id"] = graph["touches"][0]["scene_id"] = "physical_scene_004"
    if barrier == "canonical_cut":
        source["scenes"] = [{"scene_id": "old", "start_ms": 0, "end_ms": 3000},
                            {"scene_id": "new", "start_ms": 3100, "end_ms": 8000}]
    elif barrier == "physical_scene":
        frames.insert(0, {"media_ms": 1000, "scene_id": "physical_scene_003", "players": []})
    elif barrier == "physical_cut":
        frames[0]["cut_barrier"] = True
    else:
        source["scenes"] = []
    result = authority.apply_verified_jersey_handoff(source, frames, graph, votes)
    assert result["touches"][0]["global_target_id"] is None


def test_uninvolved_pixel_crops_cannot_spend_the_two_release_actor_reads(monkeypatch):
    body = frame()["players"][0]["box"]
    pixels = [{"track_id": f"spectator{i}", "media_ms": ms, "box": body,
               "request_id": f"other{i}_{ms}", "selection_rank": 1, "review_priority": -1}
              for i in range(20) for ms in (1000, 1300)]
    pixels += [{"track_id": "release", "media_ms": ms, "box": body,
                "request_id": f"release{ms}", "selection_rank": 1, "review_priority": -1}
               for ms in (1000, 1300)]
    touches = {"touches": [{"player_track_id": "release", "media_ms": 1100,
                           "contact_role": {"status": "VERIFIED", "role": "RELEASE"}}]}
    original = deepcopy(pixels)
    requests = jersey.merge_jersey_review_requests(pixels, [], touches)
    monkeypatch.setattr(vision, "MAX_JERSEY_REQUESTS", 2)
    # Exercise the actual capped provider; unavailable readers expose exactly
    # which tracks got a request without supplying successful mock evidence.
    result = vision.ShadowVisionProviders(None, "budget").jersey_vote_provider("unused", requests)
    assert set(result) == {"release"}
    first = [r for r in requests if r["track_id"] == "release"]
    assert [r["selection_rank"] for r in first] == [1, 2]
    assert all(r["expected_jersey_number"] is None for r in requests)
    assert pixels == original


def test_merged_crop_requests_do_not_double_count_reused_or_nearby_frames():
    body = frame()["players"][0]["box"]
    requests = [{"track_id": "p1", "media_ms": ms, "box": body} for ms in (1000, 1017, 1300)]
    merged = jersey.merge_jersey_review_requests(requests, requests, {})
    assert [r["media_ms"] for r in merged] == [1000, 1300]
    assert all(r["review_priority"] == 3 for r in merged)


def test_bounded_camera_transform_remaps_native_points_and_excludes_bodies(monkeypatch):
    image = np.zeros((1919, 1080), np.uint8)
    captured = []
    small_matrix = np.array([[1.01, -.01, 4.], [.01, 1.01, 3.]])
    def estimate(a, b, boxes):
        captured.append((a.shape, boxes))
        return small_matrix, "verified"
    monkeypatch.setattr(dense.motion_compensation, "estimate_camera", estimate)
    matrix, reason = dense._default_camera_estimator(image, image, [(100, 400, 80, 160)])
    sh, sw = captured[0][0]
    sx, sy = sw / 1080, sh / 1919
    point = np.array([123., 456.])
    expected = (small_matrix[:, :2] @ (point * [sx, sy]) + small_matrix[:, 2]) / [sx, sy]
    assert matrix[:, :2] @ point + matrix[:, 2] == pytest.approx(expected)
    assert captured[0][1][0] == pytest.approx((100 * sx, 400 * sy, 80 * sx, 160 * sy))
    assert sw == dense.motion_compensation.PROC_W and reason == "verified"
    assert small_matrix[0, 2] == 4  # do not change another caller's matrix
    monkeypatch.setattr(dense.motion_compensation, "estimate_camera", lambda *_: (None, "inliers"))
    assert dense._default_camera_estimator(image, image, []) == (None, "inliers")
    assert dense._default_camera_estimator(image[:-1], image, []) == (None, "frame_shape_changed")


@pytest.mark.parametrize("text", [
    "No shots were observed, meaning a key part of his attacking game is not yet developed or was not shown.",
    "He did not attempt a shot. This is a weakness in his game.",
    "Shooting was not observed. He needs improvement.",
    "Ingen skud blev observeret, og det er en svaghed.",
])
def test_partial_detection_never_becomes_player_weakness_in_advice_or_summary(text):
    source = {"analysis_authority": {"output": "FIX09C"}, "action_timeline": [],
        "_scoring_scan": {"performed": True, "physical_recall_verification_complete": False},
        "executive_summary": text, "training_plan": {"reason": text, "exercise": "Practice shooting from both feet."},
        "parent_tips": [{"text": text}], "development_priorities_detailed": {"shooting": text}}
    result = stats.apply_verified_stats_authority(deepcopy(source))
    assert result["executive_summary"] == facts.MISSING_ACTIONS
    assert result["training_plan"]["reason"] == facts.MISSING_ACTIONS
    assert result["parent_tips"][0]["text"] == facts.MISSING_ACTIONS
    assert result["development_priorities_detailed"]["shooting"] == facts.MISSING_ACTIONS
    assert result["training_plan"]["exercise"] == source["training_plan"]["exercise"]
    assert result["report_fact_authority"]["status"] == "REVIEW_REQUIRED"
    assert result["verified_stats"]["goals"] is None


def test_complete_empty_scan_can_state_absence_but_cannot_grade_missing_skill():
    source = {"verified_stats": {"goals_assists_available": True},
              "executive_summary": "No shots were observed.",
              "training_plan": {"reason": "No shots were observed, meaning shooting is not yet developed."}}
    result = facts.apply(source, {"events": []})
    assert result["executive_summary"] == source["executive_summary"]
    assert result["training_plan"]["reason"] == facts.NEUTRAL


def test_republishing_retains_neutral_explanation_and_withheld_claim_audit():
    report = {"verified_stats": {"goals_assists_available": False},
              "executive_summary": "No shots were observed. This is a weakness."}
    first = facts.apply(report, {"events": []})
    second = facts.apply(first, {"events": []})
    assert second["executive_summary"] == first["executive_summary"] == facts.MISSING_ACTIONS
    assert second["report_fact_authority"]["unsupported_claim_paths"] == first["report_fact_authority"]["unsupported_claim_paths"]


def test_offline_identity_restoration_preserves_only_actual_user_taps_and_barriers():
    from scripts import replay_report_evidence as replay
    source = {"identity_profile": {"stated_jersey_number": "15"}, "scenes": [],
              "unresolved_intervals": [{"start_ms": 2000, "end_ms": 3000, "reason": "reid_failed"}]}
    anchors = {"anchor_time_offset": -.016666, "anchors": [
        {"t": 1., "box": {"x": .2, "y": .3, "w": .1, "h": .2}},
        {"t": 2., "box": {"x": .2, "y": .3, "w": .1, "h": .2}, "visibility": "partial"}]}
    result, diagnostic = replay.restore_direct_taps(source, anchors)
    assert [p["media_ms"] for p in result["target_points"]] == [983, 1983]
    assert [p["proof_eligible"] for p in result["target_points"]] == [True, False]
    assert all(p["primary_source"] == "USER_TAP" for p in result["target_points"])
    assert result["unresolved_intervals"] == source["unresolved_intervals"]
    assert result["identity_profile"] == source["identity_profile"]
    assert not diagnostic["continuous_identity_restored"]
    assert "target_points" not in source
    assert replay.restore_direct_taps(result, anchors)[1]["status"] == "ALREADY_EXPORTED"
    assert replay.restore_direct_taps(source, None) == (source, {"status": "DIRECT_TAPS_NOT_EXPORTED", "restored_points": 0})
