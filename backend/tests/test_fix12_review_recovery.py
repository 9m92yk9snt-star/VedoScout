"""Afklaringsreviews must never bypass canonical attribution/proof gates."""
from copy import deepcopy
import asyncio
import threading
from types import SimpleNamespace
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fix10a_goal_direction as direction  # noqa: E402
import fix10a_runtime as runtime  # noqa: E402
import fix10b_reconciliation as reconciliation  # noqa: E402
import physical_match_reconstruction as physical  # noqa: E402
import unified_analysis_engine as unified  # noqa: E402
import jersey_consensus as jersey  # noqa: E402
import fix10a_vision_providers as vision  # noqa: E402
import full_video_event_recall as recall  # noqa: E402
import scoring_evidence_coverage as coverage  # noqa: E402
import analysis_jobs  # noqa: E402


def strike(ms=1000, target=None):
    return {"strike_id": f"s{ms}", "touch_id": f"t{ms}", "scene_id": "scene",
            "media_ms": ms, "player_track_id": "p1", "global_target_id": target,
            "status": "VERIFIED_PHYSICAL_RELEASE", "proof_eligible": True,
            "active_ball_anchor": {"media_ms": ms, "box": {"x": .4, "y": .6, "w": .01, "h": .01},
                "proof_eligible": True, "state": "MEASURED", "time_authority": "ACTUAL_MEDIA_PTS"}}


def test_uncertain_owner_gets_review_without_target_registration():
    release = strike()
    window = {"scene_id": "scene", "recall_window": True}
    owner = physical._goal_review_eligibility(release, [release], {})
    review = physical._goal_clarification_eligibility(release, [release], {}, window)
    assert not owner["eligible"] and review["eligible"] and review["lane"] == "CLARIFICATION"
    trace = {"strike_evidence": [release], "touch_graph": {"touches": []}, "outcome_evidence": [{
        "strike_id": release["strike_id"], "goal_plane_crossing": {"status": "VERIFIED"},
        "physical_outcome": "GOAL_PLANE_CROSSING", "goal_review_decision": review,
    }]}
    assert reconciliation.proposals_from_trace(trace) == []


def test_downstream_unknown_team_is_reviewable_but_opponent_is_excluded():
    target, receiver = strike(1000, "GLOBAL_TARGET"), strike(2000)
    graph = {"touches": [{"touch_id": "t2000", "status": "VERIFIED", "proof_eligible": True,
                          "team_relation": {"team": None, "status": "UNRESOLVED"}}]}
    window = {"recall_window": True}
    assert physical._goal_clarification_eligibility(receiver, [target, receiver], graph, window)["eligible"]
    graph["touches"][0]["team_relation"] = {"team": "opponent", "confidence": .9, "status": "SUPPORTING"}
    assert not physical._goal_clarification_eligibility(receiver, [target, receiver], graph, window)["eligible"]
    receiver["proof_eligible"] = False
    assert not physical._goal_clarification_eligibility(receiver, [target, receiver], {}, window)["eligible"]


def test_shared_budget_reuses_overlap_and_has_no_reserved_identity_lane(monkeypatch):
    monkeypatch.setattr(direction, "MAX_GOAL_CLARIFICATIONS_PER_REPORT", 1)
    calls = []
    provider = direction.GoalDirectionProvider(lambda w, s: calls.append(s["media_ms"]) or {"status": "UNRESOLVED"},
                                               "", "test", "unused", max_reviews=2)
    w = {"scene_id": "scene", "dense_window_id": "w1", "start_ms": 0, "end_ms": 8000}
    first = {**strike(), "_review_lane": "CLARIFICATION"}
    provider(w, first)
    provider({**w, "dense_window_id": "w2"}, first)
    assert len(calls) == 1 and provider.clarification_calls == 1
    second = {**strike(2000), "_review_lane": "CLARIFICATION"}
    provider(w, second)
    provider(w, {**second, "_review_lane": "VERIFIED_CHAIN"})  # same physical pixels reuse the result
    assert calls == [1000, 2000] and provider.clarification_calls == 2
    assert provider(w, {**strike(3000), "_review_lane": "VERIFIED_CHAIN"})["reason"] == "GOAL_REVIEW_BUDGET_EXHAUSTED"


def test_longer_context_is_not_replaced_by_short_window_cache():
    calls = []
    provider = direction.GoalDirectionProvider(lambda w, s: calls.append(w["end_ms"]) or {"status": "UNRESOLVED"},
                                               "", "test", "unused", max_reviews=2)
    provider({"scene_id": "scene", "start_ms": 0, "end_ms": 1500}, strike())
    provider({"scene_id": "scene", "start_ms": 0, "end_ms": 4000}, strike())
    assert calls == [1500, 4000]


def test_provider_exception_is_distinct_from_unreadable_and_missing():
    diagnostics = []
    def fail():
        raise RuntimeError("transport detail that must not be persisted")
    assert physical._safe_provider(fail, diagnostics=diagnostics) is None
    assert physical._safe_provider(None, diagnostics=diagnostics) is None
    assert physical._safe_provider(lambda: None, diagnostics=diagnostics) is None
    assert [r["status"] for r in diagnostics] == ["ERROR", "UNAVAILABLE", "NO_EVIDENCE"]
    assert "transport detail" not in str(diagnostics)


def test_same_frame_reads_cannot_verify_number_or_role():
    vote = {"media_ms": 1000, "readable": True, "number": "15", "confidence": "high"}
    assert jersey.aggregate_jersey_votes([vote, vote])["status"] == "SUPPORTING"
    assert jersey.aggregate_jersey_votes([{**vote, "media_ms": None}, vote])["status"] == "SUPPORTING"
    conflict = jersey.aggregate_jersey_votes([vote, {**vote, "number": "7"}])
    assert conflict["status"] != "VERIFIED"
    assert jersey.aggregate_jersey_votes([vote, {**vote, "media_ms": 1200}])["status"] == "VERIFIED"
    role = {"media_ms": 1000, "role": "GOALKEEPER", "confidence": "high"}
    assert vision.aggregate_role_votes([role, role])["status"] == "UNRESOLVED"
    assert vision.aggregate_role_votes([role, {**role, "media_ms": 1200}])["status"] == "VERIFIED"


@pytest.mark.usefixtures("inline_support_vision")
def test_jersey_cache_rebinds_local_track_without_another_model_call(monkeypatch):
    import numpy as np
    calls = []
    monkeypatch.setattr(vision, "_read_frames", lambda *_: {1000: (1007, np.zeros((200, 200, 3), dtype=np.uint8))})
    async def reader(*args):
        calls.append(args)
        return {"readable": True, "number": "15", "confidence": "high"}
    monkeypatch.setattr(vision.identity_verify, "read_visible_jersey_number", reader)
    provider = vision.ShadowVisionProviders("test-key", "test")
    request = {"media_ms": 1000, "track_id": "p1", "box": {"x": .2, "y": .2, "w": .2, "h": .4}}
    first = provider.jersey_vote_provider("unused", [request])
    second = provider.jersey_vote_provider("unused", [{**request, "track_id": "p99"}])
    assert len(calls) == provider.jersey_calls == 1
    assert first["p1"][0]["media_ms"] == second["p99"][0]["media_ms"] == 1007
    assert second["p99"][0]["reused"] is True


def test_unresolved_target_candidate_opens_replay_without_identity_upgrade():
    frame = {"media_ms": 1000, "scene_id": "scene", "global_target": {
        "status": "UNRESOLVED", "candidate_local_track_ids": ["p1"], "proof_eligible": False},
        "possession": {"holder_local_track_id": "p1", "target_relation": "TARGET_POSSESSION_CANDIDATE"}}
    original = deepcopy(frame)
    assert recall._graph_trigger(frame, None)[0] is True
    assert frame == original
    assert not recall._graph_trigger({**frame, "global_target": {"status": "UNRESOLVED"}}, None)[0]


def test_provider_failures_and_unpersisted_traces_prevent_complete_counts():
    result = {"traces": [{"decoded_frames": [{"media_ms": 1000, "global_target": {"proof_eligible": True}}],
                          "provider_diagnostics": [{"provider": "jersey", "status": "ERROR"}]}]}
    assessed = coverage.assess(result)
    assert not assessed["complete"] and assessed["provider_error_reasons"] == ["jersey"]
    assert "SUPPORTING_REVIEW_UNAVAILABLE_OR_FAILED" in assessed["reasons"]


def test_semantic_contract_alone_does_not_certify_full_video_totals():
    from verified_stats import scoring_totals_available
    scan = unified._scoring_scan({"metrics": {"goals": 1}}, {"coverage_complete": True})
    assert scan["performed"] and scan["verified_goals"] == 1
    assert not scoring_totals_available(scan)


def test_unselected_source_identity_gap_is_not_hidden_by_successful_window():
    evidence = {"traces": [{"decoded_frames": [{"media_ms": 1000, "scene_id": "s1",
                        "global_target": {"proof_eligible": True}}]}]}
    graph = {"frames": [{"media_ms": 5000, "scene_id": "s1",
                          "global_target": {"status": "UNRESOLVED"}}]}
    result = coverage.assess(evidence, graph)
    assert not result["complete"] and result["source_identity_gap_observations"] == 1
    assert "SOURCE_TARGET_COVERAGE_GAPS" in result["reasons"]
    graph["frames"][0]["media_ms"] = 1017
    assert coverage.assess(evidence, graph)["source_identity_gap_observations"] == 0
    graph["frames"][0]["scene_id"] = "s2"
    assert coverage.assess(evidence, graph)["source_identity_gap_observations"] == 1


def test_missing_ball_proof_cannot_certify_an_empty_scoring_total():
    evidence = {"traces": [{"decoded_frames": [{"media_ms": 1000,
                    "global_target": {"proof_eligible": True}}],
                    "ball_trajectory": [{"media_ms": 1000, "state": "PREDICTED_SHORT_GAP", "proof_eligible": False}]}]}
    result = coverage.assess(evidence)
    assert not result["complete"] and result["target_ball_gap_observations"] == 1


async def test_semantic_provider_failure_does_not_disable_safe_physical_plan():
    async def unavailable():
        raise RuntimeError("sensitive transport context")
    observation, error = await analysis_jobs.optional_observation(unavailable())
    assert observation == {} and error == "RuntimeError"
    context = {"sequence_plan": {"analysis_windows": [{"sequence_id": "s1", "scene_id": "scene",
                                                       "start_ms": 0, "end_ms": 5000}]},
               "scene_graph": {}, "authority": {}}
    result = unified.finalise_analysis(observation, context)
    assert not unified.is_production_ready(result)
    assert unified.can_run_physical(result)
    assert not result["canonical_events"]["events"]


def partial_result():
    return {"status": "partial_coverage", "sequence_analysis": {"coverage_complete": False},
            "sequence_plan": {"analysis_windows": [{"scene_id": "scene", "start_ms": 0, "end_ms": 5000}]},
            "canonical_events": {"status": "empty", "events": [], "unresolved": [], "metrics": {}},
            "metrics": {"sequence_windows": 1}}


def test_partial_model_contract_allows_safe_physical_work_without_promoting_completeness():
    result = partial_result()
    assert not unified.is_production_ready(result) and unified.can_run_physical(result)
    result["sequence_plan"]["analysis_windows"][0]["end_ms"] = float("nan")
    assert not unified.can_run_physical(result)


async def test_storage_failure_preserves_candidate_and_marks_coverage(monkeypatch):
    physical_result = {"status": "ok", "traces": [{"trace_id": "d", "decoded_frames": []}],
                       "metrics": {}, "windows": [], "recall_coverage": {}}
    monkeypatch.setattr(runtime, "support_vision_enabled", lambda: False)
    monkeypatch.setattr(runtime.physical_match_reconstruction, "reconstruct_physical_match", lambda *a, **k: deepcopy(physical_result))
    async def failed_storage(*args):
        raise RuntimeError("storage failed")
    monkeypatch.setattr(runtime, "_persist_trace", failed_storage)
    result = await runtime.run(report_id="r", video_path="unused", unified_result=partial_result(), db=None)
    assert result["status"] == "partial"
    assert result["_fix10b_candidate"]["enabled"] is True
    assert result["fix10a_trace_storage_status"] == "partial"
    assert result["fix10a_sequence_contract_complete"] is False
    scan = result["_fix10b_candidate"]["unified_result"]["scoring_scan"]
    assert not scan["physical_recall_verification_complete"]
    assert "TRACE_AUDIT_STORAGE_INCOMPLETE" in scan["physical_evidence_coverage"]["reasons"]


async def test_completed_window_is_stored_before_reconstruction_finishes(monkeypatch):
    monkeypatch.setattr(runtime, "support_vision_enabled", lambda: False)
    produced, release = threading.Event(), threading.Event()
    writes, uploads = [], []
    trace = {"trace_id": "first", "decoded_frames": [], "strike_evidence": [], "outcome_evidence": []}
    def reconstruct(*_args, trace_callback=None, **_kwargs):
        trace_callback(trace)
        produced.set()
        assert release.wait(3), "test did not release the CV boundary"
        return {"status": "ok", "traces": [trace]}
    async def upload(_rid, value, *_args):
        uploads.append(value["trace_id"])
        return {"trace_id": value["trace_id"], "storage": "local_diagnostic"}
    async def update(query, value):
        writes.append(value)
    monkeypatch.setattr(runtime.physical_match_reconstruction, "reconstruct_physical_match", reconstruct)
    monkeypatch.setattr(runtime, "_persist_trace", upload)
    task = asyncio.create_task(runtime.run(report_id="r", video_path="unused", unified_result=partial_result(),
                    db=SimpleNamespace(reports=SimpleNamespace(update_one=update))))
    try:
        assert await asyncio.to_thread(produced.wait, 1)
        for _ in range(100):
            if any("$push" in write for write in writes):
                break
            await asyncio.sleep(.01)
        assert any(write.get("$push", {}).get("fix10a_trace_manifest", {}).get("trace_id") == "first" for write in writes)
        assert not task.done()
    finally:
        release.set()
    result = await task
    assert uploads == ["first"] and result["fix10a_completed_windows"] == 1


async def test_cancelled_runtime_stops_worker_before_next_provider(monkeypatch):
    import analysis_jobs
    import physical_match_reconstruction as reconstruction

    monkeypatch.setattr(runtime, "support_vision_enabled", lambda: False)
    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
    calls = []

    def reconstruct(*_args, **_kwargs):
        try:
            entered.set()
            assert release.wait(3)
            reconstruction._safe_provider(lambda: calls.append("paid reader"))
        finally:
            stopped.set()

    monkeypatch.setattr(reconstruction, "reconstruct_physical_match", reconstruct)
    task = asyncio.create_task(runtime.run(report_id="r", video_path="unused",
                                           unified_result=partial_result(), db=None))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
    assert await asyncio.to_thread(stopped.wait, 1)
    assert calls == []
    assert analysis_jobs.CURRENT_STOP.get() is None


def test_cancelled_frame_stream_closes_decoder_without_reading_next_frame():
    import analysis_jobs

    stop = threading.Event()
    token = analysis_jobs.CURRENT_STOP.set(stop)
    decoded, closed = [], []

    def frames():
        try:
            for index in range(3):
                decoded.append(index)
                yield index
        finally:
            closed.append(True)

    stream = analysis_jobs.cancellable_frames(frames())
    try:
        assert next(stream) == 0
        stop.set()
        with pytest.raises(asyncio.CancelledError):
            next(stream)
        assert decoded == [0] and closed == [True]
    finally:
        analysis_jobs.CURRENT_STOP.reset(token)


def test_cancelled_provider_result_does_not_continue_to_next_reader():
    import analysis_jobs
    import physical_match_reconstruction as reconstruction

    stop = threading.Event()
    token = analysis_jobs.CURRENT_STOP.set(stop)
    calls = []

    def in_flight():
        stop.set()  # Owner was cancelled while this bounded call was running.
        return {"status": "COMPLETED"}

    try:
        with pytest.raises(asyncio.CancelledError):
            reconstruction._safe_provider(in_flight)
            reconstruction._safe_provider(lambda: calls.append("next reader"))
        assert calls == []
    finally:
        analysis_jobs.CURRENT_STOP.reset(token)
