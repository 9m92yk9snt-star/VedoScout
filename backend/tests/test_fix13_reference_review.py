"""Human reference cases schedule searches; only physical canonical proof passes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from scripts import reference_action_review as review
from scripts import replay_report_evidence as replay
import test_fix10b_reconciliation as physical_fixture
import test_fix10b_fix11_reconciliation as save_fixture
import test_fix10a_production_runtime as runtime_fixture
import test_fix13_action_inspections as pixels
import test_fix13_evidence_feedback as feedback_fixture


def case(ms=1000, name="goal", kind="GOAL", outcome="GOAL"):
    return {"case_id": name, "reference_ms": ms, "expected_type": kind,
            "expected_outcome": outcome, "tolerance_ms": 1000}


def test_all_five_cases_get_separate_jobs_without_expected_answers():
    cases = json.loads((Path(__file__).resolve().parents[2] / "docs/examples/five_action_reference_cases.json").read_text())
    traces = [feedback_fixture.trace(c["reference_ms"], str(i), str(i)) for i, c in enumerate(cases)]
    plan = review.build_plan(traces, cases)
    assert plan["selected"] == 5 and not plan["unreviewable"] and plan["deferred"] == 0
    changed = [{**c, "expected_type": "GOAL", "expected_outcome": "GOAL", "case_id": str(i)} for i, c in enumerate(cases)]
    assert review.build_plan(traces, changed) == plan
    assert review.search_hints(review.build_plan(traces, changed)) == review.search_hints(plan)
    for job in plan["jobs"]:
        assert not ({"expected_type", "expected_outcome", "case_id", "kind", "expected_jersey_number"} & set(job))
        assert len(pixels.inspection.frame_times(job, traces[job["selection_rank"]]["decoded_frames"])) <= 12


@pytest.mark.parametrize("bad", [[], None, [case(float("nan"))], [case(-1)], [case(True)],
    [case(outcome="UNKNOWN")], [case(), case(1000.2, "second")], [case(), case(2000)],
    [{**case(), "tolerance_ms": 1501}], [case(i, str(i)) for i in range(17)]])
def test_invalid_or_colliding_reference_cases_are_rejected(bad):
    with pytest.raises(ValueError):
        review.validate_cases(bad)


@pytest.mark.parametrize("barrier,value", [("cut_barrier", True), ("used_fallback", True),
    ("time_authority", "REQUESTED_TIME"), ("scene_id", "different")])
def test_reference_jobs_require_actual_unbroken_scene_frames(barrier, value):
    source = feedback_fixture.trace()
    for f in source["decoded_frames"]:
        f[barrier] = value
    plan = review.build_plan([source], [case()])
    assert not plan["jobs"]
    result = review.assess([case()], {"events": []}, {"traces": [source]}, plan)
    assert result["cases"][0]["failure_reason"] == "REFERENCE_FRAMES_UNAVAILABLE"


def test_insufficient_frames_cannot_be_silently_counted_as_a_review():
    source = feedback_fixture.trace()
    source["decoded_frames"] = [pixels.frame()]
    assert review.build_plan([source], [case()])["unreviewable"][0]["reason"] == "REFERENCE_FRAMES_INSUFFICIENT"


@pytest.mark.parametrize("kind,outcome", [("SHOT", "SAVED"), ("GOAL", "GOAL"), ("ASSIST", "TEAMMATE_GOAL")])
def test_reference_acceptance_uses_real_reconciler_proof(kind, outcome):
    target = physical_fixture.strike(1000, "p001", target=True)
    scorer = physical_fixture.strike(2200, "p003")
    if kind in {"GOAL", "SHOT"}:
        original = physical_fixture.trace([physical_fixture.touch(1000, "p001", target=True)], [target],
            [physical_fixture.outcome(target) if kind == "GOAL" else save_fixture._save_outcome(target)])
    else:
        original = physical_fixture.trace([physical_fixture.touch(1000, "p001", target=True), physical_fixture.touch(1500, "p003")],
            [target, scorer], [physical_fixture.outcome(target, goal=False), physical_fixture.outcome(scorer)])
    canonical = physical_fixture.f10b.reconcile_canonical_events(physical_fixture.canonical([]), {"traces": [original]})
    source = feedback_fixture.trace(scene="scene_007")
    plan = review.build_plan([source], [case(kind=kind, outcome=outcome)])
    result = review.assess([case(kind=kind, outcome=outcome)], canonical, {"traces": [source]}, plan)
    assert result["all_verified"] and result["verified"] == 1
    assert result["cases"][0]["event_id"] in {e["event_id"] for e in canonical["events"]}


def qualified_event():
    return {"event_id": "verified", "canonical_ms": 1000, "scene_id": "scene", "global_target_id": "GLOBAL_TARGET",
            "canonical_event_type": "GOAL", "canonical_outcome": "GOAL", "causal_verified": True,
            "proof": {"proof_eligible": True, "fix10b_physical": {"proof_eligible": True}}}


@pytest.mark.parametrize("changes", [{"global_target_id": None}, {"causal_verified": False},
    {"proof": {"proof_eligible": True}}, {"proof": {"proof_eligible": False, "fix10b_physical": {"proof_eligible": True}}},
    {"scene_id": "wrong"}, {"canonical_ms": 3001}, {"canonical_outcome": "SAVED"}])
def test_wrong_player_or_unqualified_story_cannot_pass(changes):
    source = feedback_fixture.trace()
    result = review.assess([case()], {"events": [{**qualified_event(), **changes}]}, {"traces": [source]},
                           review.build_plan([source], [case()]))
    assert result["verified"] == 0 and not result["all_verified"]


def test_one_event_cannot_fill_two_missing_cases():
    source = feedback_fixture.trace()
    cases = [case(), case(1100, "second")]
    result = review.assess(cases, {"events": [qualified_event()]}, {"traces": [source]}, review.build_plan([source], cases))
    assert result["verified"] == 1 and not result["all_verified"]


def evidence_zip(tmp_path, traces, video=None, source_hash=None):
    report = {"id": "test-report", "full_report": {}, "unified_identity_authority": {},
              "football_sequence_analysis": runtime_fixture._unified()["sequence_analysis"], "football_scene_graph": {},
              "canonical_events": runtime_fixture._unified()["canonical_events"], "fix10a_physical_summary": {"recall_coverage": {}}}
    if source_hash:
        report["analysis_run_manifest"] = {"source_video_sha256": source_hash}
    payloads = {"report.json": json.dumps(report).encode(), **{f"traces/{i:03}.json": json.dumps(t).encode() for i, t in enumerate(traces)}}
    if video is not None:
        payloads["video/source.mp4"] = video
    filename = tmp_path / "source.zip"
    with zipfile.ZipFile(filename, "w") as z:
        for name, data in payloads.items():
            z.writestr(name, data)
        z.writestr("SHA256SUMS", "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in payloads.items()))
    return filename


def replay_trace(name="dense_001", ms=1000):
    original = runtime_fixture._trace()
    original.update(trace_id=name, decoded_frames=[pixels.frame(ms), pixels.frame(ms + 200)])
    original["window"].update(scene_id="scene", dense_window_id=name, start_ms=ms-100, end_ms=ms+300)
    return original


def test_offline_case_failures_are_exported_without_model_calls(monkeypatch, tmp_path):
    monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
    result = replay.replay(evidence_zip(tmp_path, [replay_trace()]), output_dir=tmp_path / "out", reference_cases=[case()])
    assert not result["reference_review"]["all_verified"]
    assert result["reference_review"]["cases"][0]["inspection_status"] == "NOT_EXECUTED"
    assert result["model_request_attempts"] == result["db_writes"] == 0
    assert "scripts/reference_action_review.py" in result["replay_backend_sha256"]
    with zipfile.ZipFile(tmp_path / "out/reviewed-evidence.zip") as z:
        assert json.loads(z.read("reference_review.json")) == result["reference_review"]
        assert json.loads(z.read("operator_reference_cases.json")) == [case()]
        for line in z.read("SHA256SUMS").decode().splitlines():
            digest, name = line.split(None, 1)
            assert hashlib.sha256(z.read(name.strip())).hexdigest() == digest


def test_scoped_feedback_preserves_other_windows_and_does_not_spend_on_them():
    left, right = feedback_fixture.trace(name="left"), feedback_fixture.trace(5000, "right")
    out, _, audit = replay.pmr.run_feedback_round([left, right], "unused", {}, {}, {}, {}, feedback_trace_ids={"left"})
    assert out == [left, right] and audit["selected"] == 1
    assert {j["dense_window_id"] for j in audit["jobs"]} == {"left"}


def test_fresh_replay_scopes_readers_and_supplies_feedback_eligibility(monkeypatch, tmp_path):
    calls = {"pixels": [], "roles": [], "goals": [], "feedback": []}
    def inspect(_v, job, _frames):
        calls["pixels"].append(deepcopy(job))
        return {"status": "COMPLETED", "frames": []}
    def roles(_v, window, *_):
        calls["roles"].append(window["dense_window_id"])
        return {}
    bundle = SimpleNamespace(action_evidence_provider=inspect, role_evidence_provider=roles,
        jersey_vote_provider=lambda *_: pytest.fail("No jersey crops were proposed"),
        goal_geometry_provider=lambda _w, s: calls["goals"].append(s) or None)
    monkeypatch.setenv("EMERGENT_LLM_KEY", "injected-test-reader")
    monkeypatch.setattr(replay.fix10a_vision_providers, "LlmChat", object())
    monkeypatch.setattr(replay.fix10a_vision_providers, "build_shadow_providers", lambda *_: bundle)
    monkeypatch.setattr(replay.fix10a_goal_direction, "wrap_goal_geometry_provider", lambda provider, *_: provider)
    monkeypatch.setattr(replay.shot_outcome_engine, "find_strike_releases", lambda *_: [
        {**physical_fixture.strike(1000, "p001", target=True), "scene_id": "scene"}])
    monkeypatch.setattr(replay.shot_outcome_engine, "find_scoring_control_contacts", lambda *_: [])
    monkeypatch.setattr(replay.pmr, "_goal_clarification_eligibility", lambda *_: {
        "eligible": True, "physical_review_id": "same_contact", "lane": "CLARIFICATION"})
    def feedback(traces, *_a, **kw):
        calls["feedback"].append(kw)
        assert kw["feedback_trace_ids"] == {"selected"}
        assert kw["review_jobs"] and all("eligibility" in j for j in kw["review_jobs"])
        return traces, [], {"configured": True, "selected": 0, "jobs": []}
    monkeypatch.setattr(replay.pmr, "run_feedback_round", feedback)
    video = b"no decoder is invoked by injected readers"
    source = evidence_zip(tmp_path, [replay_trace("selected"), replay_trace("unrelated", 5000)],
                          video=video, source_hash=hashlib.sha256(video).hexdigest())
    result = replay.replay(source, support_vision=True, reference_cases=[case()])
    assert len(calls["pixels"]) == len(calls["feedback"]) == 1
    assert calls["roles"] == ["selected"] and calls["goals"]
    assert "expected_outcome" not in json.dumps(calls, default=str)
    assert not result["reference_review"]["all_verified"]  # injected model is no scoring proof


def test_replay_rejects_different_video_before_any_reader(monkeypatch, tmp_path):
    monkeypatch.setenv("EMERGENT_LLM_KEY", "injected-test-reader")
    monkeypatch.setattr(replay.fix10a_vision_providers, "LlmChat", object())
    monkeypatch.setattr(replay.fix10a_vision_providers, "build_shadow_providers", lambda *_: pytest.fail("Wrong video reached reader"))
    source = evidence_zip(tmp_path, [replay_trace()], video=b"wrong", source_hash=hashlib.sha256(b"right").hexdigest())
    with pytest.raises(ValueError, match="analysis source hash"):
        replay.replay(source, support_vision=True, reference_cases=[case()])
