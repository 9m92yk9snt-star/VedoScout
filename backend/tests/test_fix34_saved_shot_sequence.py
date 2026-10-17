"""Saved-shot handoff: one person, a camera pan and a separate spare ball.

These are resolver regressions using labelled observations, not a new model
reading of the reference video.
"""
from copy import deepcopy

import pytest

import dense_event_reconciliation as dense
import evidence_feedback
import sequence_observation_context as context
from test_fix31_temporal_video import motion_trace


def split_actor_trace():
    trace = motion_trace("SHOT", "SAVED")
    obs = trace["action_inspections"][0]
    for frame in trace["decoded_frames"]:
        if frame["media_ms"] >= 1025:
            frame["players"][0]["local_track_id"] = "p004"
            frame["global_target"].update(local_track_id="p004", candidate_local_track_ids=["p004"])
        if frame["media_ms"] >= 1400:  # camera follows the shot; shooter leaves
            frame["players"] = frame["players"][1:]
            frame["global_target"] = {"status": "ABSENT", "proof_eligible": False}
    for row in obs["body_search_regions"]:
        if row["media_ms"] >= 1025:
            row["source_bodies"][0] = {"body_id": "body_4", "local_track_id": "p004"}
        if row["media_ms"] >= 1400:
            row["source_bodies"] = row["source_bodies"][1:]
    obs["video_actions"][0]["actor_observations"] = [
        {"idx": 1, "body_id": "body_1"}, {"idx": 2, "body_id": "body_4"},
        {"idx": 3, "body_id": "body_4"}]
    return trace


def test_saved_shot_keeps_verified_person_across_track_ids_and_camera_pan():
    trace = split_actor_trace()
    result = dense.resolve_motion_observations(trace)
    assert len(result["events"]) == 1
    event = result["events"][0]
    assert (event["canonical_event_type"], event["canonical_outcome"]) == ("SHOT", "SAVED")
    assert event["causal_verified"] and event["actor_local_track_id"] == "p004"
    assert event["proof"]["actor_track_observations"] == [
        {"media_ms": 900, "local_track_id": "p001"},
        {"media_ms": 1025, "local_track_id": "p004"},
        {"media_ms": 1150, "local_track_id": "p004"}]
    assert event["proof"]["video_observation"]["source_frame_indices"] == [1, 2, 3]


@pytest.mark.parametrize("failure", ["unverified_alias", "different_person", "cut", "wrong_clock"])
def test_track_change_does_not_identify_an_unproved_or_different_player(failure):
    trace = split_actor_trace()
    for frame in trace["decoded_frames"]:
        if failure == "unverified_alias" and 1025 <= frame["media_ms"] < 1400:
            frame["global_target"]["proof_eligible"] = False
        elif failure == "different_person" and frame["media_ms"] == 1025:
            frame["global_target"].update(local_track_id="p002", candidate_local_track_ids=["p002"])
        elif failure == "cut" and frame["media_ms"] == 1000:
            frame["cut_barrier"] = True
        elif failure == "wrong_clock" and frame["media_ms"] == 1025:
            frame["time_authority"] = "REQUESTED_TIME"
    assert not any(e["causal_verified"] for e in dense.resolve_motion_observations(trace)["events"])


@pytest.mark.parametrize("outcome", ["SAVED", "GOAL", "BLOCKED", "OFF_TARGET"])
@pytest.mark.parametrize("gap", ["not_visible", "no_outcome_index", "no_evidence"])
def test_known_shot_label_still_requests_its_missing_visible_outcome(outcome, gap):
    trace = motion_trace("SHOT", outcome)
    obs = trace["action_inspections"][0]
    action = deepcopy(obs["video_actions"][0])
    if gap == "not_visible": action["outcome_visible"] = False
    elif gap == "no_outcome_index": action["outcome_idx"] = None
    else: action["outcome_evidence_indices"] = []
    requests = context.motion_review_requests({"actions": [action]},
        obs["motion_clip"]["frame_source_ms"], obs["body_search_regions"])
    assert len(requests) == 1 and requests[0]["question"] == "OUTCOME"
    assert requests[0]["media_ms"] == requests[0]["anchor_media_ms"] == 1150
    assert requests[0]["direction"] == "AFTER" and requests[0]["canonical_authority"] is False
    obs.update(selected=True, center_ms=1150, sequence_reasoning={"review_requests": requests})
    plan = evidence_feedback.build_plan([trace], budget=1)
    assert plan["selected"] == 1
    job = next(j for j in plan["jobs"] if j["selected"])
    assert job["missing_link_question"] == "OUTCOME"
    assert job["start_ms"] <= 1150 < 3025 <= job["end_ms"]


def test_complete_saved_shot_does_not_request_a_second_outcome_reader():
    trace = motion_trace("SHOT", "SAVED")
    obs = trace["action_inspections"][0]
    assert context.motion_review_requests({"actions": obs["video_actions"]},
        obs["motion_clip"]["frame_source_ms"], obs["body_search_regions"]) == []


def test_stationary_spare_in_physical_tracking_does_not_override_observed_save():
    import canonical_event_resolver
    import canonical_output_authority
    import verified_stats
    trace = split_actor_trace()
    # A detector/trajectory can favour the easy stationary ball. A complete
    # source-video save remains its own observation, not a goal-plane crossing.
    trace["ball_trajectory"] = [{"media_ms": f["media_ms"], "state": "MEASURED",
        "proof_eligible": True, "time_authority": "ACTUAL_MEDIA_PTS",
        "box": {"x": .59, "y": .49, "w": .02, "h": .02}}
        for f in trace["decoded_frames"]]
    result = dense.resolve_motion_observations(trace)
    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event["canonical_outcome"] == "SAVED" and canonical_event_resolver.has_motion_proof(event)
    stats = verified_stats.build_verified_stats({"action_timeline": canonical_output_authority.project_timeline(result)}, {})
    assert stats["observed_counts"]["goals"] == 0
    assert stats["observed_counts"]["shots"] == 1
    assert stats["observed_counts"]["shots_on_target"] == 1


def structured_save():
    """Synthetic, source-labelled evidence; not a stored real model response."""
    trace = split_actor_trace()
    obs = trace["action_inspections"][0]
    times = obs["motion_clip"]["frame_source_ms"]
    by_ms = {f["media_ms"]: f for f in trace["decoded_frames"]}
    for region in obs["body_search_regions"]:
        region["source_roi"] = {"x": 0., "y": 0., "w": 1., "h": 1.}
        for body in region["source_bodies"]:
            body["box"] = deepcopy(next(p["box"] for p in by_ms[region["media_ms"]]["players"]
                                        if p["local_track_id"] == body["local_track_id"]))
    raw = deepcopy(obs["video_actions"][0])
    raw.update(outcome="UNKNOWN", outcome_visible=False, outcome_idx=None,
               outcome_evidence_indices=[], save_sequence={"ball_id": "active",
                   "incoming_idx": 12, "keeper_idx": 15, "keeper_body_id": "body_2",
                   "keeper_intervention_visible": True, "aftermath_idx": 18,
                   "aftermath": "DEFLECTED_AWAY", "same_active_ball": True})
    boxes = {3: {"x": .18, "y": .48, "w": .02, "h": .02},
             12: {"x": .45, "y": .35, "w": .02, "h": .02},
             15: {"x": .55, "y": .35, "w": .02, "h": .02},
             18: {"x": .48, "y": .42, "w": .02, "h": .02}}
    frames = [{"idx": i, "balls": [{"ball_id": "spare", "active_ball": False,
        "stationary_spare": True, "confidence": "high",
        "box": {"x": .8, "y": .49, "w": .02, "h": .02}}], "selected_body_ids": []}
        for i in range(1, len(times)+1)]
    for i, box in boxes.items():
        frames[i-1]["balls"].append({"ball_id": "active", "active_ball": True,
            "confidence": "high", "box": box})
    frames[2]["balls"][-1].update(control_body_id="body_4", control_visible=True)
    return trace, {"reviewed_entire_clip": True, "frames": frames, "actions": [raw]}


def connect_save(trace, parsed):
    import saved_shot_sequence
    import fix10a_vision_providers as vision
    obs = trace["action_inspections"][0]
    return saved_shot_sequence.connect(parsed["actions"], parsed["frames"],
        obs["motion_clip"]["frame_source_ms"], obs["body_search_regions"], vision._native_search_box)


def test_source_stages_resolve_save_without_an_outcome_label_and_publish_one_shot():
    import fix10b_runtime
    import verified_stats
    trace, parsed = structured_save()
    original = deepcopy(parsed)
    actions = connect_save(trace, parsed)
    assert parsed == original
    trace["action_inspections"][0]["video_actions"] = actions
    result = fix10b_runtime.reconcile_unified_result({"canonical_events": {}, "sequence_analysis": {}}, {"traces": [trace]})
    assert len(result["canonical_events"]["events"]) == 1
    event = result["canonical_events"]["events"][0]
    assert event["canonical_outcome"] == "SAVED" and event["canonical_ms"] == 1150
    sequence = event["proof"]["video_observation"]["save_sequence"]
    assert sequence["status"] == "OBSERVED" and sequence["physical_certificate"] is False
    assert sequence["keeper_local_track_id"] == "p002" and sequence["ball_id"] == "active"
    assert [s["phase"] for s in sequence["stages"]] == ["STRIKE", "INCOMING", "KEEPER_INTERVENTION", "AFTERMATH"]
    assert sequence["stages"][-1]["media_ms"] > event["end_ms"]
    stats = verified_stats.build_verified_stats(result, result["scoring_scan"])
    assert {k: stats["observed_counts"][k] for k in ["shots", "shots_on_target", "goals"]} == {
        "shots": 1, "shots_on_target": 1, "goals": 0}
    assert len(result["action_timeline"]) == len(result["event_ledger"]["events"]) == 1


@pytest.mark.parametrize("failure", ["spare_only", "switch_ball", "duplicate_id", "no_keeper",
    "keeper_dive_only", "no_aftermath", "backward_time", "invented_index", "bool_index", "missing_roi"])
def test_incomplete_or_other_ball_cannot_create_a_save_from_stages(failure):
    trace, parsed = structured_save()
    seq = parsed["actions"][0]["save_sequence"]
    if failure == "spare_only": seq["ball_id"] = "spare"
    elif failure == "switch_ball": parsed["frames"][17]["balls"][-1]["ball_id"] = "other"
    elif failure == "duplicate_id": parsed["frames"][17]["balls"].append(deepcopy(parsed["frames"][17]["balls"][-1]))
    elif failure == "no_keeper": seq["keeper_body_id"] = "invented_keeper"
    elif failure == "keeper_dive_only": seq["keeper_intervention_visible"] = False
    elif failure == "no_aftermath": seq["aftermath"] = "UNKNOWN"
    elif failure == "backward_time": seq["aftermath_idx"] = 11
    elif failure == "invented_index": seq["keeper_idx"] = 999
    elif failure == "bool_index": seq["incoming_idx"] = True
    elif failure == "missing_roi": trace["action_inspections"][0]["body_search_regions"][14].pop("source_roi")
    action = connect_save(trace, parsed)[0]
    assert action["save_sequence_evidence"]["status"] == "INCOMPLETE"
    assert action["outcome"] == "UNKNOWN" and action["outcome_visible"] is False


def test_contradicting_goal_label_uses_existing_feedback_instead_of_counting_spare_as_goal():
    trace, parsed = structured_save()
    parsed["actions"][0].update(outcome="GOAL", outcome_visible=True, outcome_idx=18, outcome_evidence_indices=[18])
    actions = connect_save(trace, parsed)
    assert actions[0]["save_sequence_evidence"]["status"] == "CONFLICTING_OUTCOME"
    obs = trace["action_inspections"][0]
    requests = context.motion_review_requests({"actions": actions}, obs["motion_clip"]["frame_source_ms"], obs["body_search_regions"])
    assert len(requests) == 1 and requests[0]["question"] == "OUTCOME"
    obs["video_actions"] = actions
    assert not any(e.get("canonical_event_type") == "GOAL" for e in dense.resolve_motion_observations(trace)["events"])


async def test_production_motion_reader_connects_stages_in_its_single_existing_call(monkeypatch):
    import json
    import fix10a_vision_providers as vision
    trace, parsed = structured_save()
    obs = trace["action_inspections"][0]
    calls = []
    async def read(*args, **kwargs):
        calls.append((args, kwargs))
        return {"raw_response": json.dumps(parsed), "video_input": {
            **obs["video_input"], "reference_sha256": []}}
    monkeypatch.setattr(vision.video_model_input, "read_video", read)
    response = await vision.read_action_video_evidence("test-only", "saved", "clip.mp4",
        obs["motion_clip"]["frame_source_ms"], obs["body_search_regions"])
    assert len(calls) == 1
    assert "save_sequence" in calls[0][0][2]
    assert response["video_actions"][0]["outcome"] == "SAVED"
    assert response["sequence_reasoning"]["review_requests"] == []
    assert response["status"] == "COMPLETED"


def test_keeper_missed_by_detector_is_observed_without_inventing_a_track():
    trace, parsed = structured_save()
    obs = trace["action_inspections"][0]
    seq = parsed["actions"][0]["save_sequence"]
    seq.update(keeper_body_id=None, keeper_box={"x": .53, "y": .25, "w": .15, "h": .25})
    # This occurs in the real exported sequence: no measured player remains
    # during the keeper's dive. His observed box is not inserted into tracking.
    for row in obs["body_search_regions"]:
        if row["media_ms"] >= obs["motion_clip"]["frame_source_ms"][14]:
            row["source_bodies"] = []
    for frame in trace["decoded_frames"]:
        if frame["media_ms"] >= obs["motion_clip"]["frame_source_ms"][14]:
            frame["players"] = []
    before = deepcopy(trace["decoded_frames"])
    actions = connect_save(trace, parsed)
    audit = actions[0]["save_sequence_evidence"]
    assert audit["status"] == "OBSERVED" and audit["keeper_local_track_id"] is None
    assert audit["keeper_observation"]["source"] == "SOURCE_VIDEO_VISIBLE_BODY"
    obs["video_actions"] = actions
    events = dense.resolve_motion_observations(trace)["events"]
    assert len(events) == 1 and events[0]["canonical_outcome"] == "SAVED"
    assert trace["decoded_frames"] == before


@pytest.mark.parametrize("failure", ["no_sequence", "spare_same_id", "missing_strike_control",
    "wrong_striker", "strike_far_from_feet", "keeper_far_from_ball", "unlabelled_keeper_without_box",
    "held_without_keeper", "no_continuous_play", "wrong_manifest_clock", "duplicate_frame", "nonfinite_box"])
def test_saved_label_cannot_bypass_missing_or_contradictory_source_stages(failure):
    trace, parsed = structured_save()
    obs = trace["action_inspections"][0]
    action, strike = parsed["actions"][0], parsed["frames"][2]["balls"][-1]
    seq = action["save_sequence"]
    action.update(outcome="SAVED", outcome_visible=True, outcome_idx=18, outcome_evidence_indices=[18])
    if failure == "no_sequence": action.pop("save_sequence")
    elif failure == "spare_same_id": parsed["frames"][0]["balls"][0]["ball_id"] = "active"
    elif failure == "missing_strike_control": strike["control_visible"] = False
    elif failure == "wrong_striker": strike["control_body_id"] = "body_2"
    elif failure == "strike_far_from_feet": strike["box"]["x"] = .8
    elif failure == "keeper_far_from_ball": parsed["frames"][14]["balls"][-1]["box"]["x"] = .9
    elif failure == "unlabelled_keeper_without_box": seq["keeper_body_id"] = None
    elif failure == "held_without_keeper": seq["aftermath"] = "HELD"
    elif failure == "no_continuous_play": action["continuous_visible_sequence"] = False
    elif failure == "wrong_manifest_clock": obs["body_search_regions"][14]["media_ms"] += 1
    elif failure == "duplicate_frame": parsed["frames"].append(deepcopy(parsed["frames"][14]))
    elif failure == "nonfinite_box": parsed["frames"][14]["balls"][-1]["box"]["x"] = float("nan")
    actions = connect_save(trace, parsed)
    assert actions[0]["save_sequence_evidence"]["status"] == "INCOMPLETE"
    assert actions[0]["outcome_visible"] is False
    obs["video_actions"] = actions
    assert not any(e.get("canonical_outcome") == "SAVED" and e.get("causal_verified")
                   for e in dense.resolve_motion_observations(trace)["events"])
    requests = context.motion_review_requests({"actions": actions},
        obs["motion_clip"]["frame_source_ms"], obs["body_search_regions"])
    assert requests and requests[0]["question"] == "OUTCOME"


def test_held_ball_is_bound_to_the_keeper_at_the_later_source_instant():
    trace, parsed = structured_save()
    parsed["actions"][0]["save_sequence"].update(aftermath="HELD",
        aftermath_keeper_box={"x": .45, "y": .25, "w": .15, "h": .25})
    action = connect_save(trace, parsed)[0]
    assert action["outcome"] == "SAVED" and action["outcome_visible"] is True


def test_source_times_are_taken_from_the_input_not_a_reference_shot_time():
    trace, parsed = structured_save()
    obs = trace["action_inspections"][0]
    shift = 48000
    for frame in trace["decoded_frames"]:
        frame["media_ms"] += shift
    for row in obs["body_search_regions"]:
        row["media_ms"] += shift
    for key in ("start_ms", "end_ms"):
        trace["window"][key] += shift
    shifted = [ms+shift for ms in obs["motion_clip"]["frame_source_ms"]]
    obs["motion_clip"]["frame_source_ms"] = shifted
    obs["video_input"]["frame_source_ms"] = shifted
    obs["video_actions"] = connect_save(trace, parsed)
    event, = dense.resolve_motion_observations(trace)["events"]
    assert event["canonical_ms"] == 1150+shift and event["canonical_outcome"] == "SAVED"


def test_raw_model_cannot_supply_its_own_adapter_audit():
    trace, parsed = structured_save()
    action = parsed["actions"][0]
    action.update(save_sequence=None, outcome="SAVED", outcome_visible=True,
                  save_sequence_evidence={"status": "OBSERVED", "physical_certificate": True})
    audit = connect_save(trace, parsed)[0]["save_sequence_evidence"]
    assert audit["status"] == "INCOMPLETE" and audit["physical_certificate"] is False


def test_later_ball_control_reopens_contact_instead_of_calling_an_earlier_dribble_the_shot():
    trace, parsed = structured_save()
    obs = trace["action_inspections"][0]
    parsed["frames"][6]["balls"].append({"ball_id": "active", "active_ball": True,
        "confidence": "high", "control_visible": True, "control_body_id": "body_3",
        "box": {"x": .39, "y": .48, "w": .02, "h": .02}})
    parsed["actions"][0].update(outcome="SAVED", outcome_visible=True)
    action, = connect_save(trace, parsed)
    assert action["outcome_visible"] is False
    assert "LATER_VISIBLE_CONTROL_BEFORE_KEEPER" in action["save_sequence_evidence"]["reasons"]
    request, = context.motion_review_requests({"actions": [action]},
        obs["motion_clip"]["frame_source_ms"], obs["body_search_regions"])
    assert request["question"] == "CONTACT" and request["direction"] == "BEFORE"
    assert request["media_ms"] == obs["motion_clip"]["frame_source_ms"][14]
    assert request["canonical_authority"] is False


def window_export(tmp_path):
    import hashlib
    import json
    trace, parsed = structured_save()
    trace["action_inspections"][0]["video_actions"] = connect_save(trace, parsed)
    video_path = tmp_path/"source.mp4"
    video_path.write_bytes(b"source-fixture-for-driver-test-not-a-video")
    digest = hashlib.sha256(video_path.read_bytes()).hexdigest()
    trace["source_video"]["sha256"] = digest
    trace["action_inspections"][0]["source_video_sha256"] = digest
    root = tmp_path/"export"
    (root/"traces").mkdir(parents=True)
    (root/"traces/000.json").write_text(json.dumps(trace))
    (root/"report.json").write_text(json.dumps({"football_scene_graph": {"scenes": [trace["window"]]}}))
    (root/"anchors.json").write_text(json.dumps({"anchors": [{"t": .9,
        "box": {"x": .1, "y": .2, "w": .1, "h": .3}}], "anchor_time_offset": 0}))
    return root, video_path, trace


def test_focused_driver_uses_one_reader_original_taps_and_no_old_responses(tmp_path, monkeypatch):
    import json
    import fix10a_vision_providers as vision
    from scripts import review_source_window as driver
    root, video, trace = window_export(tmp_path)
    before = (root/"traces/000.json").read_bytes()
    calls, references = [], []
    class Bundle:
        inspection_calls = 0
        def bind_selected_reference(self, authority):
            references.extend(authority["target_points"])
        def _reference_for_window(self, window):
            return {"source": "USER_SELECTED_SOURCE_PIXELS", "source_video_sha256": trace["source_video"]["sha256"],
                    "input_sha256": "crop-fixture", "evidence_ms": [900]}
        def action_evidence_provider(self, path, job, frames):
            calls.append(job)
            self.inspection_calls += 1
            obs = deepcopy(trace["action_inspections"][0])
            obs.update(model="TEST_DOUBLE_NOT_REAL_MODEL", frames=[])
            return obs
    monkeypatch.setattr(vision, "build_shadow_providers", lambda *_: Bundle())
    output = tmp_path/"review"
    result = driver.review(root, video, trace["trace_id"], output, run_model=True, api_key="test-only-secret")
    assert result["new_model_calls"] == len(calls) == 1
    assert calls[0]["start_ms"] == trace["window"]["start_ms"]
    assert calls[0]["end_ms"] == trace["window"]["end_ms"] and calls[0]["has_contact_time"] is False
    assert "expected_outcome" not in calls[0] and calls[0]["source_action_ids"] == []
    assert references[0]["tap_authority"] and references[0]["primary_source"] == "USER_TAP"
    assert result["qualified_events"][0]["canonical_outcome"] == "SAVED"
    assert result["qualified_saved_shot_count"] == 1 and result["fresh_model_response_recorded"]
    assert not result["full_report_latency_measured"] and "test-only-secret" not in json.dumps(result)
    saved = json.loads((output/"fresh_trace.json").read_text())
    assert len(saved["action_inspections"]) == 1
    assert saved["action_inspections"][0]["inspection_id"].startswith("source_window_")
    assert (root/"traces/000.json").read_bytes() == before


@pytest.mark.parametrize("failure", ["wrong_source", "no_key"])
def test_focused_driver_stops_before_model_or_output_on_bad_source_or_missing_key(tmp_path, monkeypatch, failure):
    import fix10a_vision_providers as vision
    from scripts import review_source_window as driver
    root, video, trace = window_export(tmp_path)
    if failure == "wrong_source": video.write_bytes(b"different-source")
    monkeypatch.setattr(vision, "build_shadow_providers", lambda *_: pytest.fail("Reader must not be constructed"))
    expected = "SOURCE_VIDEO_DOES_NOT_MATCH_TRACE" if failure == "wrong_source" else "MODEL_KEY_NOT_CONFIGURED"
    with pytest.raises(ValueError, match=expected):
        driver.review(root, video, trace["trace_id"], tmp_path/"review", run_model=True)
    assert not (tmp_path/"review").exists()
