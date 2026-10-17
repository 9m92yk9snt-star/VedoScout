"""Reuse must preserve source pixels, clock, decisions and failure recovery."""
from copy import deepcopy
import asyncio
import sys
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from scripts import detector_runtime_probe as detector_runtime
import source_frame_cache as pixels
import physical_match_reconstruction as physical
import sequence_observation_context as context
import evidence_feedback
from test_fix31_temporal_video import motion_trace


@pytest.mark.usefixtures("inline_support_vision")
@pytest.mark.parametrize("reader", ["jersey", "role"])
@pytest.mark.parametrize("times", [[1000], [1000, 1300]])
def test_identical_crops_in_one_batch_are_read_once_without_inventing_independent_frames(monkeypatch, reader, times):
    import fix10a_vision_providers as vision
    import jersey_consensus
    image = np.zeros((240, 160, 3), np.uint8)
    box = {"x": .2, "y": .2, "w": .2, "h": .5}
    requests = [{"media_ms": ms, "track_id": track, "box": deepcopy(box), "request_id": f"{track}-{ms}"}
                for ms in times for track in ("first-label", "second-label")]
    monkeypatch.setattr(vision, "_read_frames", lambda _v, wanted: {ms: (ms, image) for ms in wanted})
    monkeypatch.setattr(vision, "_write_jpg", lambda *_: True)
    calls = []
    async def read(*_args):
        calls.append(1)
        return {"readable": True, "number": "7", "role": "GOALKEEPER", "confidence": "high"}
    owner = vision.ShadowVisionProviders("test-only", "dedupe")
    if reader == "jersey":
        monkeypatch.setattr(vision.identity_verify, "read_visible_jersey_number", read)
        result = owner.jersey_vote_provider("source.mp4", requests)
        assert {v["request_id"] for votes in result.values() for v in votes} == {r["request_id"] for r in requests}
        statuses = [jersey_consensus.aggregate_jersey_votes(votes)["status"] for votes in result.values()]
    else:
        monkeypatch.setattr(vision, "_role_review_requests", lambda *_: deepcopy(requests))
        monkeypatch.setattr(vision, "read_visible_player_role", read)
        result = owner.role_evidence_provider("source.mp4", {}, [], {}, [], [])
        statuses = [row["status"] for row in result.values()]
    assert len(calls) == len(times)
    assert set(result) == {"first-label", "second-label"}
    assert all((status == "VERIFIED") == (len(times) == 2) for status in statuses)


@pytest.mark.parametrize("status", ["COMPLETED", "ERROR"])
def test_feedback_without_new_inputs_does_not_repeat_physical_or_support_work(monkeypatch, status):
    import test_fix10a_physical_reconstruction as fixture
    frames = [fixture._frame(ms) for ms in range(900, 3301, 50)]
    fixture._patch_window(monkeypatch, frames=frames, contact=fixture._contact_result())
    window = {**fixture.WINDOW, "end_ms": 3300}
    monkeypatch.setattr(physical.dense_replay, "select_critical_windows", lambda *_: [deepcopy(window)])
    monkeypatch.setattr(physical.shot_outcome_engine, "find_strike_releases", lambda *_: [])
    monkeypatch.setattr(physical.shot_outcome_engine, "find_scoring_control_contacts", lambda *_: [])
    counts = {"contacts": 0, "jersey": 0, "role": 0}
    def resolve(*_):
        counts["contacts"] += 1
        return fixture._contact_result()
    monkeypatch.setattr(physical.ball_contact_engine, "resolve_contacts", resolve)
    phases = []
    def inspect(_video, job, rows):
        phases.append(job.get("phase", "INITIAL"))
        return {"status": status if job.get("phase") == "FEEDBACK" else "COMPLETED", "frames": [],
                "requested_media_ms": [f["media_ms"] for f in rows]}
    def jersey(*_):
        counts["jersey"] += 1
        return {}
    def role(*_):
        counts["role"] += 1
        return {}
    plan, analysis, graph, authority = fixture._base_inputs()
    result = physical.reconstruct_physical_match("source.mp4", plan, analysis, graph, authority,
        action_evidence_provider=inspect, jersey_vote_provider=jersey, role_evidence_provider=role,
        source_video={"sha256": "same-source"})
    assert result["status"] == "ok" and phases == ["INITIAL", "FEEDBACK"]
    assert counts == {"contacts": 1, "jersey": 1, "role": 1}
    retained, = result["traces"]
    assert retained["physical_evidence_reused"] is True
    assert retained["contacts"] == retained["first_pass_evidence"]["contacts"]
    assert len(retained["action_inspections"]) == 2


def test_reusing_physical_evidence_still_publishes_the_fresh_video_observation(monkeypatch):
    import fix10b_runtime
    trace = motion_trace("SHOT", "SAVED")
    observation = trace["action_inspections"].pop()
    trace["window"]["dense_window_id"] = trace["trace_id"]
    trace.update(contacts={"accepted": [], "unresolved": [], "rejected": []},
                 strike_evidence=[], outcome_evidence=[], role_evidence={}, jersey_consensus={}, unresolved_reasons=[])
    # This isolates physical-work reuse; selected-person evidence is already
    # present in the shared source graph, as in the other motion fixtures.
    monkeypatch.setattr(physical.dense_identity_continuity, "apply", lambda rows, *_: {"frames": deepcopy(rows)})
    monkeypatch.setattr(physical.ball_trajectory, "reconstruct_ball_trajectory", lambda *_: pytest.fail("unchanged native pass reran"))
    result = physical.reconstruct_physical_match("source.mp4", {}, {}, {}, {},
        action_evidence_provider=lambda *_: deepcopy(observation), source_video={"sha256": "source"},
        _feedback_context={"traces": {trace["trace_id"]: trace}, "jobs": [{**trace["window"],
            "inspection_id": "fresh-video", "selected": True, "phase": "FEEDBACK"}],
            "window_rows": {trace["trace_id"]: {"dense_window_id": trace["trace_id"], "status": "ok"}}})
    assert result["traces"][0]["physical_evidence_reused"] is True
    final = fix10b_runtime.reconcile_unified_result({}, result)
    event, = final["canonical_events"]["events"]
    assert event["canonical_outcome"] == "SAVED" and event["causal_verified"] is True


def test_source_cache_preserves_actual_pts_and_isolates_mutable_images(tmp_path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"source fingerprint")
    calls = []
    original = np.arange(24, dtype=np.uint8).reshape(2, 4, 3)
    def load(path, times):
        calls.append(times)
        return {ms: (ms+7, original.copy()) for ms in times}
    cache = pixels.SourceFrameCache()
    first = cache.read(video, [100, 200], load)
    first[100][1][:] = 0
    second = cache.read(video, [100, 200], load)
    assert calls == [[100, 200]]
    assert second[100][0] == 107 and second[200][0] == 207
    np.testing.assert_array_equal(second[100][1], original)
    second[100][1][:] = 1
    np.testing.assert_array_equal(cache.read(video, [100], load)[100][1], original)


def test_source_cache_is_bounded_and_invalidates_changed_source(tmp_path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"first source")
    calls = []
    def load(path, times):
        calls.extend(times)
        return {ms: (ms, np.full((2, 2, 3), ms, np.uint8)) for ms in times}
    cache = pixels.SourceFrameCache(max_bytes=24, max_entries=2)
    cache.read(video, [1, 2, 3], load)
    assert cache.metrics()["pixel_bytes"] == 24 and cache.metrics()["evictions"] == 1
    cache.read(video, [1], load)
    assert calls == [1, 2, 3, 1]
    video.write_bytes(b"different source bytes")
    cache.read(video, [1], load)
    assert calls == [1, 2, 3, 1, 1]


def test_missing_frame_is_retried_and_caches_are_run_local(tmp_path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"source")
    calls = []
    def load(path, times):
        calls.append(times)
        return {} if len(calls) == 1 else {1: (1, np.zeros((2, 2, 3), np.uint8))}
    first, other = pixels.SourceFrameCache(), pixels.SourceFrameCache()
    assert first.read(video, [1], load) == {}
    assert first.read(video, [1], load)[1][0] == 1
    other.read(video, [1], load)
    assert len(calls) == 3


async def test_frame_cache_is_inherited_by_worker_without_leaking_to_other_run():
    cache = pixels.SourceFrameCache()
    token = pixels.CURRENT.set(cache)
    try:
        assert await asyncio.to_thread(pixels.CURRENT.get) is cache
    finally:
        pixels.CURRENT.reset(token)
    assert pixels.CURRENT.get() is None


def test_cpu_runtime_uses_same_input_and_falls_back_on_runtime_failure(monkeypatch):
    seen = []
    class Options:
        pass
    class Session:
        def __init__(self, *args, **kwargs):
            seen.append(kwargs)
        def get_inputs(self):
            return [SimpleNamespace(name="images", shape=[1, 3, 640, 640])]
        def get_outputs(self):
            return [SimpleNamespace(name="output")]
        def run(self, outputs, feed):
            seen.append(feed["images"])
            if len(seen) > 2:
                raise RuntimeError("runtime unavailable")
            return [np.zeros((1, 84, 8400), np.float32)]
    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(SessionOptions=Options, InferenceSession=Session))
    class Fallback:
        def setInput(self, tensor):
            seen.append(tensor)
        def forward(self):
            return "fallback result"
    monkeypatch.setattr(detector_runtime.cv2.dnn, "readNetFromONNX", lambda _path: Fallback())
    net = detector_runtime.OnnxDetector("model.onnx")
    tensor = np.zeros((1, 3, 640, 640), np.float32)
    net.setInput(tensor)
    assert net.forward().shape == (1, 84, 8400)
    assert seen[1] is tensor
    assert net.forward() == "fallback result" and seen[-1] is tensor
    assert net.backend == "opencv_dnn_fallback"


def test_optional_runtime_load_failure_keeps_existing_detector(monkeypatch):
    def fail(_path):
        raise ImportError("optional runtime absent")
    marker = object()
    monkeypatch.setattr(detector_runtime, "OnnxDetector", fail)
    monkeypatch.setattr(detector_runtime.cv2.dnn, "readNetFromONNX", lambda _path: marker)
    assert detector_runtime.load_network("model.onnx") is marker


def test_runtime_keeps_original_engine_near_integer_box_boundary():
    raw = np.zeros((1, 84, 1), np.float32)
    raw[0, :4, 0] = [100.5, 100.5, 10.25, 10.25]
    raw[0, 4, 0] = .8
    assert detector_runtime.OnnxDetector.needs_original_rounding(raw) is False
    raw[0, 2, 0] = 10.00001
    assert detector_runtime.OnnxDetector.needs_original_rounding(raw) is True


def test_resolved_selected_person_is_reused_after_local_track_id_changes():
    event = {"scene_id": "s", "canonical_event_type": "GOAL", "causal_verified": True,
             "proof": {"video_observation": {"input_sha256": "input"}},
             "actor_local_track_id": "video-track", "global_target_id": "GLOBAL_TARGET", "contact_ms": 2000}
    strike = {"scene_id": "s", "player_track_id": "native-track", "global_target_id": "GLOBAL_TARGET", "media_ms": 2025}
    assert physical._motion_event_for_strike(strike, [event]) is event
    for change in ({"global_target_id": None}, {"scene_id": "other"}, {"media_ms": 2400}):
        assert physical._motion_event_for_strike({**strike, **change}, [event]) is None
    # The receiver/finisher of an assist is not thereby the selected passer.
    assist = {**event, "canonical_event_type": "ASSIST", "causal_chain": {
        "finisher_local_track_id": "finisher", "teammate_shot_ms": 3000}}
    assert physical._motion_event_for_strike({**strike, "media_ms": 3000}, [assist]) is None


def test_stage_clock_records_elapsed_work_without_deciding_events(monkeypatch):
    ticks = iter([10., 10., 12., 15.])
    monkeypatch.setattr(physical.time, "monotonic", lambda: next(ticks))
    clock = physical.StageClock()
    assert clock.enter("pixels") == "pixels"
    clock.enter("contacts")
    assert clock.finish() == {"pixels": 2., "contacts": 3.}


@pytest.mark.parametrize("outcome", ["GOAL", "SAVED"])
def test_missing_contact_opens_backward_search_without_creating_event(outcome):
    import dense_event_reconciliation
    trace = motion_trace("SHOT", outcome)
    obs = trace["action_inspections"][0]
    obs["video_actions"][0].update(contact_idx=None, actor_evidence_indices=[])
    original = deepcopy(trace)
    requests = context.motion_review_requests({"actions": obs["video_actions"]},
        obs["motion_clip"]["frame_source_ms"], obs["body_search_regions"])
    assert trace == original
    assert requests[0]["question"] == "CONTACT" and requests[0]["direction"] == "BEFORE"
    assert requests[0]["canonical_authority"] is False
    assert dense_event_reconciliation.resolve_motion_observations(trace)["events"] == []
    obs["sequence_reasoning"] = {"review_requests": requests}
    plan = evidence_feedback.build_plan([trace])
    job = next(j for j in plan["jobs"] if j["selected"])
    assert job["missing_link_question"] == "CONTACT"
    assert job["start_ms"] <= original["window"]["start_ms"]
    assert job["end_ms"] >= requests[0]["media_ms"]
    assert job["has_contact_time"] is False


class GoalOwner:
    def __init__(self):
        self.prepared, self.finished = [], []

    def goal_review_steps(self, window, strike):
        self.prepared.append((strike["media_ms"], threading.get_ident()))
        reply = yield ("reader", [((strike["media_ms"],), {})], 10., "test-goal")
        self.finished.append((strike["media_ms"], threading.get_ident()))
        return {"status": "UNRESOLVED", "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
                "field_side_source": "SHARED_GOAL_SCENE_PLAYABLE_PITCH", "line_by_ms": [], "token": reply}

    def goal_geometry_provider(self, window, strike):
        import ordered_vision_reviews
        return ordered_vision_reviews.single_reader(self.goal_review_steps(window, strike))


def goal_jobs(times):
    return [({"dense_window_id": "w", "scene_id": "scene", "start_ms": 0, "end_ms": 10000},
             {"media_ms": ms, "scene_id": "scene"}) for ms in times]


def test_only_remote_goal_readers_overlap_and_results_match_serial(monkeypatch):
    import fix10a_goal_direction as direction
    import support_vision_runner
    owner = GoalOwner()
    main_thread = threading.get_ident()
    lock = threading.Lock()
    active, peak = 0, 0
    def reader(_function, calls, **kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(.04)
            return [calls[0][0][0]]
        finally:
            with lock:
                active -= 1
    monkeypatch.setattr(support_vision_runner, "run_support_vision", reader)
    provider = direction.GoalDirectionProvider(owner.goal_geometry_provider, None, "test", "unused", max_reviews=4)
    jobs = goal_jobs([1000, 2000, 3000, 4000])
    batch = list(provider.review_many(jobs))
    assert peak == 2 and provider.calls == 4
    assert [row["token"] for row in batch] == [1000, 2000, 3000, 4000]
    assert all(thread == main_thread for _ms, thread in owner.prepared+owner.finished)
    sequential = direction.GoalDirectionProvider(GoalOwner().goal_geometry_provider, None, "test", "unused", max_reviews=4)
    assert batch == [sequential(*job) for job in jobs]


def test_inflight_duplicate_reuses_goal_result_and_preserves_report_budget(monkeypatch):
    import fix10a_goal_direction as direction
    import support_vision_runner
    calls = []
    def reader(_fn, jobs, **kwargs):
        calls.append(jobs[0][0][0])
        time.sleep(.02)
        return [calls[-1]]
    monkeypatch.setattr(support_vision_runner, "run_support_vision", reader)
    provider = direction.GoalDirectionProvider(GoalOwner().goal_geometry_provider, None, "test", "unused", max_reviews=2)
    values = list(provider.review_many(goal_jobs([1000, 1000, 2000, 3000])))
    assert sorted(calls) == [1000, 2000] and provider.calls == 2
    assert values[1]["review_delivery"]["status"] == "REUSED"
    assert values[2]["token"] == 2000
    assert values[3]["reason"] == "GOAL_REVIEW_BUDGET_EXHAUSTED"


def test_one_remote_goal_error_does_not_drop_later_jobs(monkeypatch):
    import fix10a_goal_direction as direction
    import support_vision_runner
    def reader(_fn, jobs, **kwargs):
        ms = jobs[0][0][0]
        if ms == 1000:
            raise TimeoutError("reader timed out")
        return [ms]
    monkeypatch.setattr(support_vision_runner, "run_support_vision", reader)
    provider = direction.GoalDirectionProvider(GoalOwner().goal_geometry_provider, None, "test", "unused", max_reviews=3)
    values = list(provider.review_many(goal_jobs([1000, 2000, 3000])))
    assert values[0]["reason"] == "goal_geometry_reader_error"
    assert [v["token"] for v in values[1:]] == [2000, 3000]


def test_cancelled_goal_batch_does_not_start_later_readers(monkeypatch):
    import analysis_jobs
    import fix10a_goal_direction as direction
    import support_vision_runner
    stop = threading.Event()
    calls = []
    def reader(_fn, jobs, **kwargs):
        calls.append(jobs[0][0][0])
        stop.set()
        return [0]
    monkeypatch.setattr(support_vision_runner, "run_support_vision", reader)
    token = analysis_jobs.CURRENT_STOP.set(stop)
    provider = direction.GoalDirectionProvider(GoalOwner().goal_geometry_provider, None, "test", "unused", max_reviews=4)
    try:
        with pytest.raises(asyncio.CancelledError):
            list(provider.review_many(goal_jobs([1000, 2000, 3000, 4000])))
        assert calls == [1000]
    finally:
        analysis_jobs.CURRENT_STOP.reset(token)


@pytest.mark.usefixtures("inline_support_vision")
def test_production_goal_adapter_keeps_geometry_when_readers_overlap(monkeypatch):
    import json
    import fix10a_goal_direction as direction
    import fix10a_vision_providers as vision
    from test_fix30_shared_geometry_work import scene_payload
    image = np.zeros((80, 120, 3), np.uint8)
    main_thread = threading.get_ident()
    readers, completions = [], []
    monkeypatch.setattr(vision, "_read_frames", lambda _video, times: {ms: (ms, image) for ms in times})
    async def reader(_key, _session, _paths, times):
        readers.append(threading.get_ident())
        await asyncio.sleep(.02)
        return vision.parse_goal_scene_response(json.dumps(scene_payload(times)), times)
    monkeypatch.setattr(vision, "read_goal_scene_evidence", reader)
    def no_native_link(self, review, path, images):
        completions.append(threading.get_ident())
        return None
    monkeypatch.setattr(vision.ShadowVisionProviders, "_measure_goal_reappearance", no_native_link)
    owner = vision.build_shadow_providers("fake-key", "test", "unused")
    provider = direction.GoalDirectionProvider(owner.goal_geometry_provider, "fake-key", "test", "unused", max_reviews=2)
    jobs = goal_jobs([1000, 2000])
    values = list(provider.review_many(jobs))
    assert len(readers) == 2 and all(thread != main_thread for thread in readers)
    assert completions == [main_thread, main_thread]
    assert all(v["field_side_status"] == "VERIFIED" for v in values)
    assert provider.field_side_calls == 0 and owner.goal_calls == 2
    sequential_owner = vision.build_shadow_providers("fake-key", "test", "unused")
    sequential = direction.GoalDirectionProvider(sequential_owner.goal_geometry_provider, "fake-key", "test", "unused", max_reviews=2)
    assert values == [sequential(*job) for job in jobs]
