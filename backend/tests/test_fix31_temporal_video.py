"""Temporal video input, source clocks and shared action-chain regressions."""
from copy import deepcopy
import json

import pytest

import video_model_input as video
import action_evidence_review as inspection


def test_native_rate_is_on_the_video_part_and_preserves_other_media():
    contents = [{"parts": [{"text": "observe"}, {"inline_data": {"mime_type": "image/jpeg", "data": "reference"}},
        {"inline_data": {"mime_type": "video/mp4", "data": "video"},
         "video_metadata": {"startOffset": "1s", "endOffset": "3s"}}]}]
    original = deepcopy(contents)
    assert video.attach_sampling(contents, 8) == [{"startOffset": "1s", "endOffset": "3s", "fps": 8.0}]
    assert contents[0]["parts"][:2] == original[0]["parts"][:2]
    assert contents[0]["parts"][2]["inline_data"]["data"] == "video"
    assert "video_metadata" not in contents[0]["parts"][2]


@pytest.mark.parametrize("fps", [0, -1, True, float("nan"), float("inf"), 31, "8"])
def test_invalid_rate_cannot_be_reported_as_prepared(fps):
    with pytest.raises(ValueError, match="INVALID_VIDEO_SAMPLING_RATE"):
        video.attach_sampling([], fps)


def test_old_converter_is_scoped_and_restored_even_on_failure():
    class Parent:
        def _transform_messages(self, **_kwargs):
            return [{"parts": [{"inline_data": {"mime_type": "video/mp4", "data": "pixels"}}]}]
    class Child(Parent):
        pass
    audit = {}
    with pytest.raises(RuntimeError):
        with video.native_sampling(Child, 8, audit):
            assert Child()._transform_messages()[0]["parts"][0]["videoMetadata"]["fps"] == 8
            assert "videoMetadata" not in Parent()._transform_messages()[0]["parts"][0]
            raise RuntimeError("cancelled")
    assert "_transform_messages" not in Child.__dict__
    assert audit["sampling_attached_to_provider_payload"] is True


def test_deployed_litellm_converter_serializes_native_fps_without_network(monkeypatch):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    litellm = pytest.importorskip("litellm")
    import socket
    monkeypatch.setattr(socket.socket, "connect", lambda *_: pytest.fail("unexpected network"))
    messages = [{"role": "user", "content": [{"type": "file", "file": {
        "file_data": "data:video/mp4;base64,c291cmNlLXZpZGVv", "format": "video/mp4"}},
        {"type": "text", "text": "Observe the action"}]}]
    audit = {}
    with video.native_sampling(litellm.GoogleAIStudioGeminiConfig, 8, audit):
        body = {"contents": litellm.GoogleAIStudioGeminiConfig()._transform_messages(messages=messages)}
        serialized = json.loads(json.dumps(body))
    native = next(p for c in serialized["contents"] for p in c["parts"] if "videoMetadata" in p)
    assert native["videoMetadata"] == {"fps": 8.0}
    assert audit["native_video_metadata"] == [{"fps": 8.0}]


async def test_isolated_adapter_passes_exact_source_and_crops_once(monkeypatch, tmp_path):
    calls = []
    def run(reader, batch, **kwargs):
        calls.append((reader, batch, kwargs))
        return [{"raw_response": '{"sequences":[]}', "video_input": {
            "sampling_attached_to_provider_payload": True, "requested_fps": 8}}]
    monkeypatch.setattr(video.support_vision_runner, "run_support_vision", run)
    chat = video.IsolatedVideoChat("not-a-real-key", "session", tmp_path/"clip.mp4", [tmp_path/"selected.jpg"], timeout_s=30)
    assert await chat.send_message("Observe video") == '{"sequences":[]}'
    assert len(calls) == 1 and calls[0][0] is video.read_video
    args, kwargs = calls[0][1][0]
    assert args[2] == "Observe video" and args[3].endswith("clip.mp4")
    assert len(args[4]) == 1 and kwargs["fps"] == 8
    assert calls[0][2]["limit"] == 1
    assert chat.video_input_audit["sampling_attached_to_provider_payload"]


def test_motion_sampling_covers_the_whole_window_without_contact_hints():
    frames = [{"media_ms": ms, "scene_id": "scene", "time_authority": "ACTUAL_MEDIA_PTS"}
              for ms in range(12000, 20001, 17)]
    job = {"scene_id": "scene", "start_ms": 12000, "end_ms": 20000, "center_ms": 13000}
    times = inspection.motion_frame_times(job, frames)
    assert len(times) == 65 and times[0] == 12000 and times[-1] == frames[-1]["media_ms"]
    assert max(b-a for a, b in zip(times, times[1:])) <= 136
    assert set(times).issubset({f["media_ms"] for f in frames})
    job["center_ms"] = 19000
    assert inspection.motion_frame_times(job, frames) == times
    frames[10]["cut_barrier"] = True
    assert frames[10]["media_ms"] not in inspection.motion_frame_times(job, frames)


@pytest.mark.usefixtures("inline_support_vision")
def test_production_action_adapter_sends_one_actual_video_with_the_source_clock(monkeypatch):
    import cv2
    import numpy as np
    import fix10a_vision_providers as vision
    import test_fix29_connected_sequences as fixtures
    from types import SimpleNamespace
    frames = [fixtures.frame(ms) for ms in range(0, 2001, 20)]
    calls = []
    async def reader(_key, _session, clip_path, times, manifest, **kwargs):
        cap = cv2.VideoCapture(clip_path)
        try:
            assert cap.isOpened() and cap.get(cv2.CAP_PROP_FPS) == 1
            assert cap.get(cv2.CAP_PROP_FRAME_COUNT) == len(times)
        finally:
            cap.release()
        calls.append(times)
        assert all(row["source_bodies"] for row in manifest)
        return {"status": "COMPLETED", "frames": [{"idx": i+1, "balls": [], "selected_body_ids": []}
                for i in range(len(times))], "target_observations": [], "video_actions": [],
                "observation_protocol": "SOURCE_INDEXED_MOTION_CLIP_V1"}
    monkeypatch.setattr(vision, "read_action_video_evidence", reader)
    monkeypatch.setattr(vision, "_read_frames", lambda _path, times: {
        ms: (ms, np.full((160, 100, 3), 64, np.uint8)) for ms in times})
    bundle = vision.ShadowVisionProviders("fake", "motion")
    bundle._native_goal_detector = SimpleNamespace(ok=False)
    result = bundle.action_evidence_provider("video.mp4", {"scene_id": "scene", "start_ms": 0,
        "end_ms": 2000, "inspection_id": "job", "center_ms": 1000}, frames)
    assert len(calls) == 1 and len(calls[0]) == 17
    assert result["motion_clip"]["frame_source_ms"] == result["decoded_media_ms"]
    assert result["motion_clip"]["max_source_gap_ms"] <= 140
    assert bundle.inspection_calls == 1


def motion_trace(kind="PASS", outcome="TEAMMATE_GOAL", offset=0, scene="scene_001"):
    import test_fix09b3_canonical_event_resolver as fixture
    import football_scene_graph as graph
    times = list(range(offset+900, offset+3901, 125))
    frames = []
    for ms in range(offset+900, offset+3901, 25):
        f = fixture.frame(ms, holder="p001" if ms < offset+1400 else "p003")
        f.update(scene_id=scene, time_authority="ACTUAL_MEDIA_PTS")
        for p in f["players"]:
            p.update(association_state="VERIFIED_LOCAL", team_source=graph.DENSE_TEAM_SOURCE)
        frames.append(f)
    by_ms = {f["media_ms"]: f for f in frames}
    raw = {"kind": kind, "start_idx": 1, "contact_idx": 3, "end_idx": 4,
        "actor_body_id": "body_1", "actor_evidence_indices": [1,3], "contact_visibility": "VISIBLE", "foot": "RIGHT",
        "outcome": outcome, "outcome_visible": True, "outcome_idx": 18, "outcome_evidence_indices": [18,19],
        "continuous_visible_sequence": True, "receiver_body_id": "body_3" if kind == "PASS" else None,
        "receiver_idx": 7 if kind == "PASS" else None, "finisher_body_id": "body_3" if kind == "PASS" else None,
        "shot_idx": 13 if kind == "PASS" else None, "details": ["Observed source-indexed action"]}
    obs = {"observation_protocol": "SOURCE_INDEXED_MOTION_CLIP_V1", "status": "COMPLETED", "clip_review_complete": True,
        "motion_clip": {"frame_source_ms": times, "clip_sha256": "clip"},
        "video_input": {"sampling_attached_to_provider_payload": False, "model_video_sha256": "clip", "requested_fps": 1,
            "sampling_prepared_for_provider": True, "sampling_strategy": "SOURCE_INDEXED_1FPS_PLAYBACK",
            "frame_source_ms": times, "playback_fps": 1, "source_sampling_fps": 8},
        "source_video_sha256": "source", "input_sha256": "input"+str(offset), "response_sha256": "response", "video_actions": [raw],
        "body_search_regions": [{"media_ms": ms, "source_bodies": [{"body_id": "body_"+p["local_track_id"][-1],
             "local_track_id": p["local_track_id"]} for p in by_ms[ms]["players"]]} for ms in times]}
    return {"trace_id": "trace"+str(offset), "source_video": {"sha256": "source"},
        "window": {"scene_id": scene, "start_ms": times[0], "end_ms": times[-1]},
        "decoded_frames": frames, "action_inspections": [obs], "touch_graph": {"touches": []}, "ball_trajectory": []}


@pytest.mark.parametrize("kind,outcome,expected", [("SHOT","SAVED","SHOT"),("SHOT","GOAL","GOAL"),
    ("PASS","TEAMMATE_GOAL","ASSIST")])
def test_complete_video_observation_uses_existing_identity_team_and_causal_resolver(kind,outcome,expected):
    import dense_event_reconciliation as dense
    trace = motion_trace(kind,outcome)
    result = dense.resolve_motion_observations(trace)
    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event["canonical_event_type"] == expected and event["canonical_outcome"] == outcome
    assert event["causal_verified"] and event["global_target_id"] == "GLOBAL_TARGET"
    assert event["proof"]["video_observation"]["input_sha256"] == "input0"
    assert event["proof"]["video_observation"]["source_video_sha256"] == "source"


def test_five_complete_sequences_publish_one_goal_three_assists_one_saved_shot_without_a_number():
    import dense_event_reconciliation as dense
    import fix10b_runtime as runtime
    import verified_stats
    from scripts import reference_action_review as reference
    physical = {"traces": [motion_trace(kind, outcome, i*5000, f"scene_{i}") for i, (kind,outcome) in enumerate(
        [("SHOT","SAVED"),("SHOT","GOAL"),("PASS","TEAMMATE_GOAL"),("PASS","TEAMMATE_GOAL"),("PASS","TEAMMATE_GOAL")])]}
    result = dense.recover({"events": [], "unresolved": [], "rejected": []}, {}, physical, {})
    assert result["counts"] == {"SHOT": 1, "GOAL": 1, "ASSIST": 3}
    assert len(result["events"]) == 5 and all(e["causal_verified"] for e in result["events"])
    unified = runtime.reconcile_unified_result({"canonical_events": {}, "sequence_analysis": {}}, physical)
    assert unified["canonical_events"]["counts"] == result["counts"]
    assert len(unified["action_timeline"]) == len(unified["event_ledger"]["events"]) == 5
    stats = verified_stats.build_verified_stats(unified, unified["scoring_scan"])
    assert stats["observed_counts"]["goals"] == 1 and stats["observed_counts"]["assists"] == 3
    assert stats["observed_counts"]["shots"] == 2 and stats["goals_assists_available"] is False
    cases = [{"case_id": str(i), "reference_ms": e["canonical_ms"], "expected_type": e["canonical_event_type"],
        "expected_outcome": e["canonical_outcome"]} for i, e in enumerate(result["events"])]
    plan = reference.build_plan(physical["traces"], cases)
    assert reference.assess(cases, unified["canonical_events"], physical, plan)["all_verified"]


@pytest.mark.parametrize("failure", ["wrong_actor", "source_mismatch", "no_native_metadata", "wrong_clip", "invented_index",
    "cut", "missing_outcome_evidence", "different_finisher", "opponent_receiver", "no_ball_transfer"])
def test_video_chain_cannot_approve_a_wrong_player_or_missing_causal_link(failure):
    import dense_event_reconciliation as dense
    trace = motion_trace()
    obs = trace["action_inspections"][0]
    action = obs["video_actions"][0]
    if failure == "wrong_actor": action["actor_body_id"] = "body_2"
    elif failure == "source_mismatch": obs["source_video_sha256"] = "other"
    elif failure == "no_native_metadata": obs["video_input"]["sampling_prepared_for_provider"] = False
    elif failure == "wrong_clip": obs["video_input"]["model_video_sha256"] = "other"
    elif failure == "invented_index": action["contact_idx"] = 999
    elif failure == "cut": trace["decoded_frames"][40]["cut_barrier"] = True
    elif failure == "missing_outcome_evidence": action["outcome_evidence_indices"] = []
    elif failure == "different_finisher": action["finisher_body_id"] = "body_2"
    elif failure == "opponent_receiver":
        for f in trace["decoded_frames"]: f["players"][2]["team"] = "opponent"
    elif failure == "no_ball_transfer":
        for f in trace["decoded_frames"]: f.pop("possession", None)
    events = dense.resolve_motion_observations(trace)["events"]
    assert not any(e["canonical_event_type"] == "ASSIST" for e in events)


def test_motion_feedback_is_idempotent_and_conflicting_outcomes_do_not_overwrite_each_other():
    import dense_event_reconciliation as dense
    trace = motion_trace("SHOT", "GOAL")
    physical = {"traces": [trace]}
    first = dense.merge_motion_observations({}, physical)
    assert dense.merge_motion_observations(first, physical) == first
    disagree = deepcopy(trace)
    disagree["action_inspections"][0]["video_actions"][0]["outcome"] = "SAVED"
    disagree["action_inspections"][0]["input_sha256"] = "other-clip-view"
    physical["traces"].append(disagree)
    conflicted = dense.merge_motion_observations({}, physical)
    assert not conflicted["events"] and conflicted["unresolved"][0]["reason"] == "CONFLICTING_VIDEO_OUTCOMES"
    assert dense.merge_motion_observations(conflicted, physical) == conflicted


def test_rejected_motion_actor_keeps_the_exact_failure_and_source_provenance():
    import dense_event_reconciliation as dense
    trace = motion_trace()
    trace["action_inspections"][0]["video_actions"][0]["actor_body_id"] = "body_2"
    physical = {"traces": [trace]}
    result = dense.merge_motion_observations({}, physical)
    diagnostics = result.get("unresolved", []) + result.get("rejected", [])
    assert diagnostics and diagnostics[0]["video_observation"]["input_sha256"] == "input0"
    assert diagnostics[0].get("reason") or diagnostics[0].get("actor_resolution")
    assert dense.merge_motion_observations(result, physical) == result


def test_reference_gallery_uses_existing_nearby_user_views_without_an_expected_number():
    import base64
    import fix10a_vision_providers as vision
    bundle = vision.ShadowVisionProviders("fake", "gallery")
    bundle._reference_gallery = {"source": "USER_SELECTED_SOURCE_PIXELS", "source_video_sha256": "source",
        "evidence_ms": [1000,10000,20000,30000,40000,50000],
        "images": [base64.b64encode(str(i).encode()).decode() for i in range(6)]}
    early = bundle._reference_for_window({"start_ms": 0, "end_ms": 5000})
    late = bundle._reference_for_window({"start_ms": 45000, "end_ms": 51000})
    assert early["evidence_ms"] == [1000,10000,20000] and late["evidence_ms"] == [30000,40000,50000]
    assert early["input_sha256"] != late["input_sha256"] and late["number_required"] is False
    assert len(bundle._reference_gallery["images"]) == 6


def test_writer_retains_report_schema_but_receives_facts_instead_of_identity_rediscovery():
    import ast
    from pathlib import Path
    import report_fact_authority as facts
    tree = ast.parse((Path(__file__).parents[1]/"server.py").read_text())
    template = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "FULL_REPORT_PROMPT" for t in n.targets))
    import dense_event_reconciliation as dense
    canonical = dense.merge_motion_observations({}, {"traces": [motion_trace()]})
    prompt = facts.assessment_prompt(template, canonical, {"age": 11}, {"content_type": "match"})
    assert "No video or images are attached" in prompt and "re-identify the player at that exact moment" not in prompt
    assert "mandatory before EVERY cited timestamp" not in prompt
    assert "TEMPORAL" not in prompt  # report users do not need transport implementation details
    assert "ASSIST" in prompt and "TEAMMATE_GOAL" in prompt and "scanning" in prompt and "U11–U12" in prompt
    assert '"parent_corner"' in prompt and '"technical"' in prompt and '"mentality"' in prompt


async def test_report_model_audit_does_not_open_video_or_make_another_video_call(monkeypatch):
    import analysis_jobs as jobs
    from test_fix12_analysis_jobs import Reports
    store = Reports({})
    async def save(_query, update, **_kwargs):
        store.doc.update(update["$set"])
    store.update_one = save
    monkeypatch.setattr(jobs, "file_sha256", lambda *_: pytest.fail("report writer reopened the video"))
    class Chat:
        async def send_message(self, prompt):
            assert prompt == "resolved observations"
            return "{}"
    token = jobs.CURRENT_RUN.set(jobs.RunLease("r", "run", 1200))
    try:
        assert await jobs.model_call(store, Chat(), "resolved observations", session_id="full-r", video_path=None,
                                     prompt="resolved observations", timeout_s=1) == "{}"
    finally:
        jobs.CURRENT_RUN.reset(token)
    assert store.doc["input_type"] == "CANONICAL_FACTS" and store.doc["video_sha256"] is None


def test_shared_clip_limits_repeated_geometry_but_keeps_unresolved_actions_and_native_recall():
    import goal_review_scheduler as scheduler
    jobs = [{"window": {"dense_window_id": "w"}, "strike": {"media_ms": ms},
        "review": {"physical_review_id": str(ms)}, "motion_review": {"complete": True,
        "unresolved_contact_ms": [1000,3000]}} for ms in (0,1000,1100,1300,3000,3100,7000)]
    original = deepcopy(jobs)
    selected, deferred = scheduler.motion_fallback_requests(jobs)
    assert [j["strike"]["media_ms"] for j in selected] == [0,1000,3000] and len(deferred) == 4
    assert jobs == original
    for job in jobs: job["motion_review"]["complete"] = False
    assert scheduler.motion_fallback_requests(jobs) == (jobs, [])


def test_shared_video_outcome_binds_both_assist_roles_but_not_another_player_or_scene():
    import dense_event_reconciliation as dense
    import physical_match_reconstruction as physical
    events = dense.resolve_motion_observations(motion_trace())["events"]
    event = events[0]
    shot = {"media_ms": event["causal_chain"]["teammate_shot_ms"], "player_track_id": "p003", "scene_id": "scene_001"}
    assert physical._motion_event_for_strike(shot, events)["canonical_event_type"] == "ASSIST"
    assert physical._motion_event_for_strike({**shot, "player_track_id": "p002"}, events) is None
    assert physical._motion_event_for_strike({**shot, "scene_id": "other"}, events) is None


def test_fresh_pass_chain_corrects_an_old_shot_role_through_the_complete_production_bridge():
    import dense_event_reconciliation as dense
    import fix10b_runtime as runtime
    trace = motion_trace()
    assist = dense.resolve_motion_observations(trace)["events"][0]
    old = deepcopy(assist)
    old.update(event_id="old-shot", canonical_action_type="SHOT", canonical_event_type="SHOT", canonical_outcome="OFF_TARGET")
    old["proof"].pop("video_observation")
    unified = runtime.reconcile_unified_result({"canonical_events": {"events": [old]}}, {"traces": [trace]})
    assert [e["canonical_event_type"] for e in unified["canonical_events"]["events"]] == ["ASSIST"]
    assert unified["fix10b_summary"]["shot_role_conflicts_reopened"] == 1
    # A pre-existing independently proved target shot must not be removed as a
    # semantic role correction (a teammate may subsequently score a rebound).
    old["reconciliation_authority"] = "FIX10B_PHYSICAL_RECONCILIATION"
    unified = runtime.reconcile_unified_result({"canonical_events": {"events": [old]}}, {"traces": [trace]})
    assert {e["canonical_event_type"] for e in unified["canonical_events"]["events"]} == {"SHOT", "ASSIST"}


def test_selected_person_appearance_refreshes_both_pooled_and_local_team_models():
    import dense_track_refinement as dense
    from test_fix10a2_dense_track_refinement import _changing_light_team_frames
    frames = _changing_light_team_frames()
    for f in frames:
        target = f["global_target"]
        if target.get("authority_tap"):
            target.update(reason="MULTI_FRAME_SELECTED_APPEARANCE", authority_tap=False,
                appearance_evidence={"source": "USER_SELECTED_SOURCE_PIXELS", "source_video_sha256": "source", "input_sha256": "crops"})
    result = dense._apply_dense_team_labels(frames)
    assert result["status"] == "partial" and len(result["local_models"]) == 2
    assert all(f["players"][1]["team"] == "target_team" and f["players"][4]["team"] == "opponent" for f in frames)
    for f in frames:
        (f["global_target"].get("appearance_evidence") or {}).pop("input_sha256", None)
    assert dense._dense_target_kit_samples(frames) == []


def test_video_active_ball_uses_native_pixels_even_when_global_tracking_follows_a_spare():
    import dense_event_reconciliation as dense
    trace = motion_trace()
    obs = trace["action_inspections"][0]
    obs["frames"] = []
    for f in trace["decoded_frames"]:
        f.pop("possession", None)
        trace["ball_trajectory"].append({"media_ms": f["media_ms"], "state": "MEASURED", "proof_eligible": True,
            "time_authority": "ACTUAL_MEDIA_PTS", "box": {"x": .59, "y": .49, "w": .02, "h": .02}})
        if f["media_ms"] in obs["motion_clip"]["frame_source_ms"]:
            x = .14 if f["media_ms"] < 1400 else .39
            box = {"x": x, "y": .49, "w": .02, "h": .02}
            obs["frames"].append({"media_ms": f["media_ms"], "ball_candidates": [{"box": box, "proposal_box": box,
                "confidence": .8, "pixel_corroborated": True, "source": "NATIVE_REVIEW_ROI_DETECTOR", "video_active_ball": True}]})
            trace["touch_graph"]["touches"].append({"media_ms": f["media_ms"], "representative_ms": f["media_ms"],
                "player_track_id": "p002", "status": "VERIFIED", "proof_eligible": True})
    before = deepcopy(trace)
    result = dense.resolve_motion_observations(trace)
    assert any(e["canonical_event_type"] == "ASSIST" for e in result["events"])
    assert trace == before  # the global physical path is not rewritten
    for row in obs["frames"]:
        row["ball_candidates"][0]["pixel_corroborated"] = False
    assert not any(e["canonical_event_type"] == "ASSIST" for e in dense.resolve_motion_observations(trace)["events"])


@pytest.mark.parametrize("field,value", [("video_actions", None),("video_actions", {}),("video_actions", [None]),
    ("actor_evidence_indices", None),("outcome_evidence_indices", {}),("contact_idx", True),("outcome_idx", 999)])
def test_malformed_model_actions_cannot_crash_or_approve_an_assist(field, value):
    import dense_event_reconciliation as dense
    trace = motion_trace()
    obs = trace["action_inspections"][0]
    if field == "video_actions": obs[field] = value
    else: obs["video_actions"][0][field] = value
    assert not any(e["canonical_event_type"] == "ASSIST" for e in dense.resolve_motion_observations(trace)["events"])


async def test_proxy_route_keeps_source_sampling_without_claiming_unobserved_native_conversion(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    import cv2
    import numpy as np
    path = tmp_path/"source.jpg"
    cv2.imwrite(str(path), np.zeros((160, 100, 3), np.uint8))
    clock = [1000,1125,1250]
    clip = tmp_path/"motion.mp4"
    video.write_motion_clip([path]*3, clock, clip)
    class Payload:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
    class ProxyChat:
        def __init__(self, **kwargs): pass
        def with_model(self, *_args): return self
        async def send_message(self, message):
            assert message.file_contents[-1].file_path == str(clip)
            return "{}"  # no LOCAL Gemini converter: the proxy owns conversion
    monkeypatch.setitem(sys.modules, "emergentintegrations.llm.chat", SimpleNamespace(
        LlmChat=ProxyChat, UserMessage=Payload, FileContentWithMimeType=Payload))
    result = await video.read_video("dummy", "session", "Observe the labelled frames", clip, source_clock=clock)
    audit = result["video_input"]
    assert audit["provider_conversion"] == "PROXY_UNCONFIRMED" and audit["provider_receipt_confirmed"] is False
    assert audit["sampling_attached_to_provider_payload"] is False
    assert audit["sampling_prepared_for_provider"] and audit["source_sampling_fps"] == 8
    assert audit["playback_fps"] == audit["requested_fps"] == 1 and audit["frame_source_ms"] == clock


def test_model_error_categories_preserve_budget_and_timeout_without_exposing_upstream_text():
    marker = "sensitive-fixture-do-not-return"
    failures = [(Exception("Budget has been exceeded: "+marker), "BUDGET", RuntimeError),
        (TimeoutError(marker), "TIMEOUT", TimeoutError), (Exception(marker), "REQUEST_FAILED", RuntimeError)]
    for exc, code, expected in failures:
        row = video.model_failure(exc)
        assert row == {"error_code": code} and marker not in json.dumps(row)
        with pytest.raises(expected) as error:
            video.response_text(row)
        assert marker not in str(error.value)


def test_resolved_source_clip_outcome_is_reused_by_physical_orchestration(monkeypatch):
    import physical_match_reconstruction as pmr
    import fix10b_runtime as runtime
    from test_fix10a_physical_reconstruction import _patch_window, _base_inputs, _contact_result, _accepted_contact
    source = motion_trace("SHOT", "GOAL")
    frames = source["decoded_frames"]
    _patch_window(monkeypatch, frames=frames, contact=_contact_result(accepted=[_accepted_contact("p001", 1150)]))
    window = {**source["window"], "dense_window_id": source["trace_id"], "source_sequence_ids": ["seq1"]}
    monkeypatch.setattr(pmr.dense_replay, "select_critical_windows", lambda *_a: [window])
    strike = {"strike_id": "release", "touch_id": "touch", "media_ms": 1150, "scene_id": window["scene_id"],
        "player_track_id": "p001", "global_target_id": "GLOBAL_TARGET", "status": "VERIFIED_PHYSICAL_RELEASE", "proof_eligible": True}
    monkeypatch.setattr(pmr.shot_outcome_engine, "find_strike_releases", lambda *_a: [deepcopy(strike)])
    monkeypatch.setattr(pmr.evidence_feedback, "build_plan", lambda *_a, **_kw: {"jobs": []})
    def repeated(*_args, **_kwargs):
        pytest.fail("already resolved clip caused a second goal/role model call")
    monkeypatch.setattr(pmr, "_strike_ball_paths", repeated)
    monkeypatch.setattr(pmr.post_strike_intervention, "detect_post_strike_intervention", repeated)
    plan, analysis, graph, authority = _base_inputs()
    physical = pmr.reconstruct_physical_match("video.mp4", plan, analysis, graph, authority,
        source_video={"sha256": "source"}, action_evidence_provider=lambda *_a: deepcopy(source["action_inspections"][0]),
        goal_geometry_provider=repeated, role_evidence_provider=repeated)
    assert physical["windows"][0]["status"] == "ok", physical["windows"]
    trace = physical["traces"][0]
    assert trace["motion_observation_summary"]["outcomes_reused"] == 1
    assert trace["outcome_evidence"][0]["goal_plane_crossing"]["status"] == "UNRESOLVED"
    unified = runtime.reconcile_unified_result({}, physical)
    assert unified["canonical_events"]["counts"] == {"GOAL": 1}


def test_feedback_does_not_request_an_outcome_already_resolved_from_video():
    import evidence_feedback as feedback
    trace = motion_trace("SHOT", "GOAL")
    trace["strike_evidence"] = [{"strike_id": "release", "media_ms": 1150,
        "global_target_id": "GLOBAL_TARGET", "status": "VERIFIED_PHYSICAL_RELEASE", "proof_eligible": True}]
    trace["outcome_evidence"] = [{"strike_id": "release", "media_ms": 1150, "physical_outcome": "UNRESOLVED",
        "goal_geometry_evidence": {"reason": "OUTCOME_ALREADY_RESOLVED_FROM_SOURCE_CLIP"}}]
    assert feedback.gaps(trace)["unresolved_outcomes"] == 0
    assert all(j["reason"] != "OUTCOME_CONTACT_GAP" for j in feedback.build_plan([trace])["jobs"])


def test_motion_body_identity_does_not_require_jersey_isolation_during_a_duel():
    import dense_identity_continuity as identity
    import dense_event_reconciliation as dense
    trace = motion_trace("SHOT", "GOAL")
    for f in trace["decoded_frames"]:
        f["global_target"] = {"status": "UNRESOLVED", "proof_eligible": False, "local_track_id": None, "reason": "target_absent"}
        f["players"][1]["box"]["x"] = .15  # distinct body, overlapping torso crop
        for p in f["players"]:
            p["jersey_crop_quality"] = {"source": "NATIVE_TORSO_PIXELS", "isolated": False}
    obs = trace["action_inspections"][0]
    obs.update(selected_reference={"source": "USER_SELECTED_SOURCE_PIXELS", "source_video_sha256": "source", "input_sha256": "references"},
        target_observations=[{"media_ms": ms, "local_track_id": "p001", "confidence": "high", "features": ["hair","boots"]}
            for ms in (900,1150)])
    frame = trace["decoded_frames"][0]
    assert "p001" not in {b["local_track_id"] for b in inspection.measured_body_candidates(frame)}
    assert "p001" in {b["local_track_id"] for b in inspection.motion_body_candidates(frame)}
    # Legacy static comparisons cannot borrow the stronger temporal protocol.
    legacy = {**obs, "observation_protocol": None}
    assert not any(f["global_target"].get("proof_eligible") for f in identity.apply_reference_matches(trace["decoded_frames"], legacy))
    trace["decoded_frames"] = identity.apply_reference_matches(trace["decoded_frames"], obs)
    assert [f["media_ms"] for f in trace["decoded_frames"] if f["global_target"].get("proof_eligible")] == [900,1150]
    events = dense.resolve_motion_observations(trace)["events"]
    assert events[0]["canonical_event_type"] == "GOAL" and events[0]["causal_verified"]


@pytest.mark.parametrize("failure", [None,"missing_controls","wrong_body","invisible","low_confidence","wrong_source"])
def test_complete_visual_transfer_does_not_require_a_duplicate_physical_ball_certificate(failure):
    import dense_event_reconciliation as dense
    import fix10b_runtime as runtime
    trace = motion_trace()
    for f in trace["decoded_frames"]:
        f.pop("possession", None)
    controls = [{"media_ms": ms, "local_track_id": track, "confidence": "high", "control_visible": True,
        "source": "SOURCE_VIDEO_VISIBLE_BALL_CONTROL", "ball_box": {"x": x,"y": .49,"w": .02,"h": .02}}
        for ms,track,x in [(1150,"p001",.14),(1650,"p003",.39)]]
    if failure == "missing_controls": controls = []
    if failure == "wrong_body": controls[1]["local_track_id"] = "p002"
    if failure == "invisible": controls[1]["control_visible"] = False
    if failure == "low_confidence": controls[1]["confidence"] = "low"
    if failure == "wrong_source": controls[1]["source"] = "ACTION_LABEL_ONLY"
    trace["action_inspections"][0]["video_control_observations"] = controls
    unified = runtime.reconcile_unified_result({}, {"traces": [trace]})
    assists = [e for e in unified["canonical_events"]["events"] if e["canonical_event_type"] == "ASSIST"]
    if failure:
        assert not assists
    else:
        assert len(assists) == 1
        assert "fix10b_physical" not in assists[0]["proof"]
        assert assists[0]["receiver_team_resolution"]["actor_ball_relation"]["evidence"][0]["source"] == "SOURCE_VIDEO_VISIBLE_BALL_CONTROL"


def test_short_feedback_clip_cannot_claim_coverage_of_the_entire_window():
    import sequence_observation_context as context
    trace = motion_trace()
    observation = trace["action_inspections"][0]
    assert context.motion_window_complete(observation, trace["decoded_frames"], trace["window"])
    observation["motion_clip"]["frame_source_ms"] = observation["motion_clip"]["frame_source_ms"][:9]
    observation["video_input"]["frame_source_ms"] = observation["motion_clip"]["frame_source_ms"]
    observation["video_actions"] = []
    assert context.video_observations(observation, trace["decoded_frames"], trace["window"])["sequences"]
    assert not context.motion_window_complete(observation, trace["decoded_frames"], trace["window"])
