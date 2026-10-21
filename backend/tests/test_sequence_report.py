"""Real retained model evidence + orchestration failure boundaries, no model spend."""
import asyncio
import ast
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import subprocess
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sequence_report_adapter as adapter
import sequence_report_runtime as runtime
from scripts.run_sequence_report_trial import server_harness
from evidence_authority import apply_fail_closed_proof_authority, compute_proof_frame_verified

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def retained():
    return json.loads((ROOT / "docs/examples/cold-whole-source-approval-receipts.json").read_text())


def bundle(p):
    return adapter.canonical_bundle(p["result"], p["replay_context"], p["receipts"])


def test_real_receipts_preserve_scoring_roles_brackets_and_partial_coverage(retained):
    b = bundle(retained)
    f = adapter.build_report({"summary": "Observed football actions", "match_stats": {"goals": 99},
                              "video_comments": [{"comment": "invented"}], "speed_metrics": {"max": 99}}, b)
    assert f["match_stats"]["observed_goals"] == 1
    assert f["match_stats"]["observed_assists"] == 3
    assert f["match_stats"]["shots"] == f["match_stats"]["shots_on_target"] == 2
    assert f["verified_stats"]["goals"] is None
    assert f["verified_stats"]["goals_assists_available"] is False
    assert f["match_stats"]["coverage_status"] == "PARTIAL"
    assert "speed_metrics" not in f
    assert f["match_stats"]["dribbles_attempted"] is None
    assert f["match_stats"]["successful_dribbles"] is None
    assert f["match_stats"]["recoveries"] == 1
    assert f["match_stats"]["pass_completion_pct"] is None
    assert f["match_stats"]["duels_won"] is None
    assert all(c["sequence_event_native"] and c["proof_verified"] for c in f["video_comments"])
    assert not any(e["actor_spatial_verified"] for e in f["action_timeline"])
    shot = next(e for e in b["events"] if e["canonical_outcome"] == "SAVED")
    assert shot["contact_ms"] is None and shot["contact_interval_ms"] == [23682, 23749]
    assert all(e["foot"] == "UNKNOWN" for e in b["events"])
    positive_ids = {e["event_id"] for e in b["events"] if e["canonical_event_type"] in {"GOAL", "ASSIST", "SHOT"}}
    assert positive_ids <= {c["event_id"] for c in f["video_comments"]}


@pytest.mark.parametrize("change,code", [
    (lambda p: p["result"].update(source_video_sha256="other"), "SOURCE_MISMATCH"),
    (lambda p: p["receipts"][0].update(raw_response="altered"), "RESPONSE_CHANGED"),
    (lambda p: p["receipts"].pop(), "RECEIPTS_MISSING"),
    (lambda p: p["result"].update(status="PARTIAL_MODEL_RUN"), "RUN_INCOMPLETE"),
    (lambda p: p["result"].update(historical_action_results_used=True), "HISTORY_NOT_ALLOWED"),
    (lambda p: p["result"]["target_events"][0].update(actor_evidence_frames=["invented"]), "FRAME_MISSING"),
])
def test_changed_missing_and_partial_evidence_fails_closed(retained, change, code):
    change(retained)
    with pytest.raises(ValueError, match=code):
        bundle(retained)


def test_teammate_finish_cannot_be_assigned_to_the_passer(retained):
    event = next(e for e in retained["result"]["target_events"] if e["event_type"] == "ASSIST")
    event["finisher"] = event["actor"]
    with pytest.raises(ValueError, match="ASSIST_ROLE"):
        bundle(retained)


def test_event_citation_cannot_authorize_weak_foot_grade(retained):
    b = bundle(retained)
    event = next(e for e in b["events"] if e["canonical_event_type"] == "ASSIST")
    prose = {"summary": "Actions", "technical": {"weak_foot": {
        "score": 8, "evidence": [{"event_id": event["event_id"], "timestamp": "00:50", "what": "Pass"}]}}}
    f = adapter.build_report(prose, b)
    assert f["technical"]["weak_foot"]["score"] is None
    assert f["technical"]["weak_foot"]["cannot_evaluate"] is True


def test_empty_retained_proofs_prevent_ready_before_encoding(tmp_path):
    async def publish(*args):
        pytest.fail("Empty evidence must not publish or become ready")
    with pytest.raises(ValueError, match="SOURCE_PROOFS_MISSING"):
        asyncio.run(runtime.persist_assets(None, {"full_report": {}}, tmp_path / "absent.mp4", tmp_path, publish))


def synthetic_report_worker(pipe, job, provider, model, timeout):
    assert provider == "emergent" and model in {"gemini-2.5-pro", "gpt-6-astra"} and timeout >= 179
    if model == "gpt-6-astra":
        assert job["reasoning_effort"] == "low"
    assert job["max_output_tokens"] == 12288
    section = int(job["packet_id"].rsplit("_", 1)[1])
    prose = {k: {} for k in runtime.WRITER_SECTIONS[section-1]}
    if section == 1:
        prose["executive_summary"] = "Synthetic assessment; no model request"
    else:
        assert "COMPLETED ASSESSMENT" in job["items"][0]["text"]
        assert "Synthetic assessment; no model request" in job["items"][0]["text"]
    pipe.send({"status": "COMPLETED", "packet_id": job["packet_id"],
               "raw_response": json.dumps(prose)})
    pipe.close()


@pytest.mark.parametrize("model", ["gemini-2.5-pro", "gpt-6-astra"])
def test_writer_180_second_budget_reaches_owned_transport_without_network(monkeypatch, model):
    monkeypatch.setenv("SEQUENCE_REPORT_WRITER_MODEL", model)
    real = runtime.transport.run_jobs
    def synthetic_jobs(jobs, provider, model, **kwargs):
        return real(jobs, provider, model, **kwargs, worker=synthetic_report_worker)
    monkeypatch.setattr(runtime.transport, "run_jobs", synthetic_jobs)
    result = asyncio.run(runtime.write_facts("Synthetic test; no model request"))
    assert result["report"]["executive_summary"] == "Synthetic assessment; no model request"
    assert len(result["receipts"]) == 2
    assert set(result["report"]) == set(sum(runtime.WRITER_SECTIONS, ()))
    with pytest.raises(ValueError, match="INVALID_EXECUTION_BUDGET"):
        real([], "emergent", "gemini-2.5-pro", deadline=time.monotonic()+1, per_call_s=211)
    _, payload, _ = runtime.transport.build_request("emergent", "gemini-2.5-pro",
        [{"type": "text", "text": "Synthetic report"}], max_output_tokens=32768)
    assert json.loads(payload)["max_tokens"] == 32768
    with pytest.raises(ValueError, match="INVALID_OUTPUT_TOKEN_BUDGET"):
        runtime.transport.build_request("emergent", "gemini-2.5-pro", [], max_output_tokens=32769)


@pytest.mark.parametrize("failure", ["ERROR", "MISSING_KEYS"])
def test_second_writer_section_failure_retains_first_receipt_without_partial_report(monkeypatch, failure):
    calls = []
    def jobs(jobs, *args, **kwargs):
        calls.append(jobs[0])
        if len(calls) == 1:
            prose = {k: {} for k in runtime.WRITER_SECTIONS[0]}
            return [{"status": "COMPLETED", "raw_response": json.dumps(prose)}]
        if failure == "ERROR":
            return [{"status": "ERROR", "error": "MODEL_WALL_DEADLINE_EXCEEDED"}]
        return [{"status": "COMPLETED", "raw_response": "{}"}]
    monkeypatch.setattr(runtime.transport, "run_jobs", jobs)
    with pytest.raises(runtime.ReportWriterFailure) as exc:
        asyncio.run(runtime.write_facts("Synthetic test; no network"))
    assert len(calls) == len(exc.value.receipts) == 2
    assert exc.value.receipts[0]["status"] == "COMPLETED"
    assert not hasattr(exc.value, "report")


def actual_section_reports():
    actual = json.loads((ROOT / "docs/examples/sequence-report-sections-receipts.json").read_text())
    checkpoint = json.loads((ROOT / "docs/examples/sequence-report-source-checkpoint.json").read_text())
    return actual, checkpoint["canonical_events"]


def test_actual_writer_presentation_cannot_retain_level_after_aggregate_withheld():
    actual, canonical = actual_section_reports()
    prose = {}
    for receipt in actual["writer_receipts"]:
        prose.update(json.loads(receipt["raw_response"]))
    assert "Strong Club" in prose["scout_outlook"]["current_level_label"]
    full = adapter.build_report(prose, canonical)
    assert full["overall_benchmark"]["tier"] is None
    assert full["potential_assessment"]["current_level"].startswith("Insufficient verified evidence")
    assert full["scout_outlook"]["current_level_dots"] is None
    assert full["scout_outlook"]["potential_level_dots"] is None
    assert "Strong Club" not in full["scout_outlook"]["current_level_label"]
    assert full["technical"]["weak_foot"]["score"] is None
    assert full["match_stats"]["observed_assists"] == 3


def test_actual_saved_shot_location_is_not_a_goal_claim():
    from report_fact_authority import _supports
    actual, canonical = actual_section_reports()
    prose = {}
    for receipt in actual["writer_receipts"]:
        prose.update(json.loads(receipt["raw_response"]))
    full = adapter.build_report(prose, canonical)
    saved = next(e for e in canonical["events"] if e["canonical_outcome"] == "SAVED")
    assert {row["event_id"] for row in full["technical"]["shooting"]["evidence"]} == {
        saved["event_id"], next(e["event_id"] for e in canonical["events"] if e["canonical_event_type"] == "GOAL")}
    assert full["technical"]["shooting"]["observations_used"] == 2
    assert full["report_fact_authority"]["unbound_skill_observations"] == 0
    assert _supports("The goalkeeper parries the shot outside the goal.", [saved])
    assert not _supports("He scores a goal and the goalkeeper parries outside the goal.", [saved])
    assert not _supports("The ball enters the goal after a save outside the goal.", [saved])
    assert not _supports("The goalkeeper parries the shot outside the goal.", [])


def test_presentation_writer_consumes_actual_reconciled_assessment(monkeypatch):
    actual, canonical = actual_section_reports()
    calls = []
    def jobs(jobs, *args, **kwargs):
        calls.append(jobs[0])
        if len(calls) == 2:
            checked = json.loads(jobs[0]["items"][0]["text"].split(
                "COMPLETED ASSESSMENT (authoritative for scores, uncertainty and advice): ", 1)[1])
            assert checked["overall_benchmark"]["tier"] is None
            assert checked["scores"]["overall_development"] is None
            assert checked["technical"]["weak_foot"]["cannot_evaluate"] is True
        return [deepcopy(actual["writer_receipts"][len(calls)-1])]
    monkeypatch.setattr(runtime.transport, "run_jobs", jobs)
    result = asyncio.run(runtime.write_facts("Synthetic replay; no network", canonical=canonical))
    assert len(calls) == 2
    assert result["report"]["overall_benchmark"]["tier"] is None


def current_code_checkpoint():
    # Unit scenario: a complete same-code checkpoint. Original published
    # fixture provenance remains unchanged on disk.
    doc = json.loads((ROOT / "docs/examples/sequence-report-source-checkpoint.json").read_text())
    doc["sequence_audit"]["result"]["code_sha256"] = runtime.code_fingerprint()
    return doc


@pytest.mark.parametrize("change", [
    lambda d: d.update(analysis_engine="LEGACY"),
    lambda d: d.update(full_report_status="ready"),
    lambda d: d["sequence_audit"].update(source_video_sha256="changed"),
    lambda d: d["sequence_audit"].update(original_selection_values_sha256="changed"),
    lambda d: d["sequence_audit"]["result"]["code_sha256"].update({"sequence_pilot.py": "changed"}),
    lambda d: d["sequence_audit"]["result"].update(identity_mode="INFERRED_PROFILE"),
    lambda d: d["sequence_audit"]["result"].update(status="PARTIAL_MODEL_RUN"),
])
def test_changed_or_unfinished_checkpoint_cannot_resume(change):
    doc = current_code_checkpoint()
    source = doc["sequence_audit"]["source_video_sha256"]
    selections = doc["sequence_audit"]["original_selection_values_sha256"]
    change(doc)
    assert runtime.retained_source(doc, source, selections) is None


def test_corrupted_checkpoint_fails_before_writer_or_new_paid_discovery():
    doc = current_code_checkpoint()
    audit = doc["sequence_audit"]
    audit["receipts"][0]["raw_response"] = "altered"
    with pytest.raises(ValueError, match="RESPONSE_CHANGED"):
        runtime.retained_source(doc, audit["source_video_sha256"], audit["original_selection_values_sha256"])


@pytest.mark.parametrize("status", ["failed", "generating"])
def test_failed_report_resumes_source_with_zero_new_source_calls(tmp_path, monkeypatch, status):
    doc = current_code_checkpoint()
    doc["full_report_status"] = status  # claim() changes failed to generating before execution
    video = tmp_path / "source.mp4"
    digest = runtime.pilot.digest
    monkeypatch.setattr(runtime.pilot, "digest", lambda p: doc["sequence_audit"]["source_video_sha256"]
                        if Path(p) == video else digest(p))
    async def forbidden(*args, **kwargs):
        pytest.fail("Same-code complete source checkpoint must not start model/preparation workers")
    monkeypatch.setattr(runtime, "owned_process", forbidden)
    actual, _ = actual_section_reports()
    async def writer(prompt):
        prose = {}
        for r in actual["writer_receipts"]:
            prose.update(json.loads(r["raw_response"]))
        return {"report": prose, "receipts": actual["writer_receipts"]}
    ns, _, _, _ = server_harness(video, doc, tmp_path)
    result = asyncio.run(runtime.generate(video, doc, template=ns["FULL_REPORT_PROMPT"], writer=writer))
    assert result["sequence_timings"]["source_phase_reused"] is True
    assert result["sequence_timings"]["retained_source_analysis_seconds"] == 518.498
    assert len(result["sequence_audit"]["receipts"]) == 13
    assert result["full_report"]["match_stats"]["observed_assists"] == 3


def test_actual_server_retry_preserves_source_again_when_writer_fails(tmp_path, monkeypatch):
    doc = current_code_checkpoint()
    video = tmp_path / "source.mp4"
    video.touch()
    digest = runtime.pilot.digest
    monkeypatch.setattr(runtime.pilot, "digest", lambda p: doc["sequence_audit"]["source_video_sha256"]
                        if Path(p) == video else digest(p))
    async def forbidden(*args, **kwargs):
        pytest.fail("Server retry must not rediscover source or encode assets after writer failure")
    async def writer(prompt):
        raise runtime.ReportWriterFailure("SYNTHETIC_WRITER_FAILURE", [{"status": "ERROR"}])
    async def generate(*args, **kwargs):
        return await runtime.generate(*args, **kwargs, writer=writer)
    monkeypatch.setattr(runtime, "owned_process", forbidden)
    engine = SimpleNamespace(enabled=lambda: True, generate=generate, persist_assets=forbidden)
    ns, store, _, _ = server_harness(video, doc, tmp_path, runtime=engine)
    asyncio.run(ns["generate_full_report_task"](doc["id"]))
    assert store.doc["full_report_status"] == "failed"
    assert store.doc["sequence_audit"]["source_checkpoint_reused"] is True
    assert store.doc["sequence_audit"]["original_source_analysis_seconds"] == 518.498
    assert len(store.doc["sequence_audit"]["receipts"]) == 13
    assert store.states == ["generating", "failed"]


def test_writer_failure_keeps_paid_source_receipts_before_temp_cleanup(tmp_path, retained, monkeypatch):
    raw = json.loads((ROOT / "testdata/sequence-pilot-orman400/anchors.json").read_text())["raw_marker_anchors"]
    monkeypatch.setattr(runtime.pilot, "digest", lambda _: retained["source_video_sha256"])
    async def discovery(*args):
        return retained["result"], retained["replay_context"], retained["receipts"]
    async def writer(prompt):
        raise runtime.ReportWriterFailure("SYNTHETIC_WRITER_FAILURE", [
            {"status": "ERROR", "error": "MODEL_QUOTA_OR_RATE_LIMIT", "http_status": 429}])
    saved = []
    async def checkpoint(values):
        saved.append(deepcopy(values))
    ns, _, _, _ = server_harness(tmp_path / "video.mp4", {"id": "test"}, tmp_path)
    with pytest.raises(RuntimeError, match="SYNTHETIC_WRITER_FAILURE"):
        asyncio.run(runtime.generate(tmp_path / "video.mp4", {"raw_marker_anchors": raw},
                    template=ns["FULL_REPORT_PROMPT"], discovery=discovery, writer=writer, checkpoint=checkpoint))
    assert len(saved) == 3
    assert len(saved[-1]["sequence_audit"]["receipts"]) == 13
    assert any(s.get("canonical_events", {}).get("events") for s in saved)
    assert saved[-1]["sequence_audit"]["writer_receipts"][0]["http_status"] == 429
    assert "full_report" not in saved[-1]


def test_normal_report_lists_omit_bulk_model_receipts():
    doc = {"id": "test", "user_id": "owner", "full_report": {"summary": "ready"},
           "sequence_audit": {"raw_response": "x"*1_000_000}, "sequence_retry": {"raw_response": "bulk"}}
    class Cursor:
        def __init__(self, projection):
            self.projection = projection
        def sort(self, *args):
            return self
        async def to_list(self, _):
            return [{k: v for k, v in doc.items() if self.projection.get(k) != 0}]
    collection = SimpleNamespace(find=lambda query, projection: Cursor(projection))
    tree = ast.parse((ROOT / "backend/server.py").read_text())
    selected = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name in {"my_reports", "admin_reports"}]
    for node in selected:
        node.decorator_list = []
        node.args.defaults = [ast.Constant(None)]
    ns = {"db": SimpleNamespace(reports=collection), "_resolve_video_url": lambda _: "/video",
          "_resolve_poster_url": lambda _: "/poster"}
    exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])), "report-list-routes", "exec"), ns)
    for rows in (asyncio.run(ns["my_reports"]({"id": "owner"})), asyncio.run(ns["admin_reports"]())):
        assert rows[0]["id"] == "test" and rows[0]["video_url"] == "/video"
        assert "sequence_audit" not in rows[0] and "full_report" not in rows[0]
        assert "sequence_retry" not in rows[0]


def test_unbound_comment_and_inexact_source_image_are_not_proof(retained):
    f = adapter.build_report({"summary": "Actions"}, bundle(retained))
    row = f["video_comments"][0]
    row.update(frame_url="/image.jpg", identity_verified=True, frame_time_ms=row["evidence_time_ms"])
    assert not compute_proof_frame_verified(row)
    row["frame_time_authority"] = "ACTUAL_MEDIA_PTS"
    assert compute_proof_frame_verified(row)
    row["frame_time_ms"] += 1
    assert not compute_proof_frame_verified(row)
    row["source_video_sha256"] = "other"
    apply_fail_closed_proof_authority(f)
    assert not row["proof_verified"]


def test_verified_skill_uses_exact_event_id_despite_rounded_display_time(retained):
    b = bundle(retained)
    event = next(e for e in b["events"] if e["canonical_event_type"] == "ASSIST")
    prose = {"summary": "Actions", "technical": {"passing": {"score": 7, "evidence": [
        {"event_id": event["event_id"], "timestamp": "00:44", "what": "Assist"}]}},
        "snapshot_moments": [{"event_id": event["event_id"], "timestamp": "00:44", "what": "Invented",
                              "canonical_event_ids": [event["event_id"]], "identity_verified": True}]}
    f = adapter.build_report(prose, b)
    row = f["technical"]["passing"]["evidence"][0]
    image = next(c for c in f["video_comments"] if c["event_id"] == event["event_id"])
    assert row["evidence_id"] == image["evidence_id"] and row["proof_verified"] is True
    assert row["evidence_time_ms"] == image["evidence_time_ms"]
    assert f["snapshot_moments"][0]["proof_verified"] is False


@pytest.mark.parametrize("configured", [None, "legacy", "sequence_v1", "", "unknown"])
def test_new_full_reports_always_select_sequence_engine(monkeypatch, configured):
    if configured is None:
        monkeypatch.delenv("FULL_REPORT_ENGINE", raising=False)
    else:
        monkeypatch.setenv("FULL_REPORT_ENGINE", configured)
    assert runtime.enabled() is True


@pytest.mark.parametrize("fail_assets", [False, True])
def test_actual_server_bypasses_legacy_and_never_readies_failed_assets(tmp_path, retained, monkeypatch, fail_assets):
    monkeypatch.delenv("FULL_REPORT_ENGINE", raising=False)
    b = bundle(retained)
    full = adapter.build_report({"summary": "Actions"}, b)
    calls = []

    async def generate(*args, **kwargs):
        calls.append("sequence_generate")
        return {"analysis_engine": "SEQUENCE_V1", "canonical_events": b, "full_report": full}

    async def assets(collection, doc, *args):
        calls.append("sequence_assets")
        if fail_assets:
            raise RuntimeError("SEQUENCE_ASSET_PUBLISH_FAILED")
        await collection.update_one({"id": doc["id"]}, {"$set": {"identity_gate_done": True}})
        return {"checked": 8, "hard_rejected": 0}

    rt = SimpleNamespace(enabled=runtime.enabled, generate=generate, persist_assets=assets)
    video = tmp_path / "source.mp4"
    video.write_bytes(b"video-exists")
    doc = {"id": "test", "gt_track": {"old": True}, "pace_metrics": {"old": True}}
    ns, store, trace, notifications = server_harness(video, doc, tmp_path, runtime=rt)
    asyncio.run(ns["generate_full_report_task"]("test"))
    assert calls == ["sequence_generate", "sequence_assets"]
    assert store.doc["full_report_status"] == ("failed" if fail_assets else "ready")
    assert ("ready" in store.states) is not fail_assets
    assert "gt_track" not in store.doc and "pace_metrics" not in store.doc
    assert len(notifications) == (0 if fail_assets else 2)  # sandbox suppresses both


def test_sequence_recovery_only_rebuilds_assets_and_never_rediscovers(tmp_path, retained):
    async def forbidden(*args, **kwargs):
        pytest.fail("A retained report must not run discovery again")

    async def assets(collection, doc, *args):
        return {"checked": 8, "hard_rejected": 0}

    rt = SimpleNamespace(generate=forbidden, persist_assets=assets)
    video = tmp_path / "video.mp4"
    video.touch()
    doc = {"id": "test", "analysis_engine": "SEQUENCE_V1", "full_report_status": "failed",
           "full_report": adapter.build_report({"summary": "Actions"}, bundle(retained))}
    ns, store, _, _ = server_harness(video, doc, tmp_path, runtime=rt)
    asyncio.run(ns["generate_full_report_task"]("test"))
    assert store.doc["full_report_status"] == "ready"


def test_missing_original_taps_stops_before_discovery(tmp_path):
    async def forbidden(*args):
        pytest.fail("No model calls without original positive selections")
    with pytest.raises(ValueError, match="ORIGINAL_SELECTIONS_REQUIRED"):
        asyncio.run(runtime.generate(tmp_path / "none.mp4", {}, template="unused", discovery=forbidden))


def test_unknown_writer_configuration_stops_before_paid_source_work(tmp_path, monkeypatch):
    monkeypatch.setenv("SEQUENCE_REPORT_WRITER_MODEL", "unapproved-model")
    async def forbidden(*args):
        pytest.fail("Invalid writer configuration must stop before discovery")
    with pytest.raises(ValueError, match="WRITER_MODEL_NOT_VALIDATED"):
        asyncio.run(runtime.generate(tmp_path / "none.mp4", {}, template="unused", discovery=forbidden))


def test_owned_process_timeout_reaps_the_child(tmp_path):
    with pytest.raises(TimeoutError):
        asyncio.run(runtime.owned_process([sys.executable, "-c", "import time; time.sleep(30)"],
                                          timeout_s=.1, log_path=tmp_path / "process.log"))


def test_owned_process_nonzero_keeps_exit_status_without_stderr(tmp_path):
    with pytest.raises(runtime.SequenceProcessFailure) as caught:
        asyncio.run(runtime.owned_process([sys.executable, "-c", "import sys; print('private-provider-body'); sys.exit(3)"],
                                          timeout_s=3, log_path=tmp_path / "process.log"))
    assert caught.value.diagnostics == {"returncode": 3, "timeout": False}
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("timeout", [False, True])
def test_discovery_checkpoints_before_process_finishes_and_preserves_failure(tmp_path, monkeypatch, timeout):
    async def scenario():
        saved, received = [], asyncio.Event()
        source = tmp_path / "source.mp4"; source.write_bytes(b"synthetic")
        async def process(args, **kwargs):
            if args[2] == "prepare":
                runtime.pilot.write_json(tmp_path / "prepared/manifest.json", {
                    "source_video_sha256": "source", "original_taps_sha256": "selection"})
                return
            runtime.pilot.write_json(tmp_path / "observations/responses/sequence_001.json", {
                "packet_id": "sequence_001", "status": "COMPLETED", "raw_response": "retained reply"})
            # The source process cannot finish until the server has persisted its receipt.
            await asyncio.wait_for(received.wait(), 3)
            runtime.pilot.write_json(tmp_path / "observations/result.json", {
                "status": "PARTIAL_MODEL_RUN", "model_jobs": [
                    {"status": "COMPLETED"}, {"status": "ERROR", "error": "MODEL_QUOTA_OR_RATE_LIMIT",
                                               "raw_response": "secret", "provider_message": "secret"}]})
            error = runtime.SequenceProcessTimeout if timeout else runtime.SequenceProcessFailure
            raise error({"returncode": -9 if timeout else 3, "timeout": timeout})
        async def checkpoint(value):
            saved.append(deepcopy(value))
            if value["receipts"]: received.set()
        monkeypatch.setattr(runtime, "owned_process", process)
        monkeypatch.setattr(runtime.pilot, "original_taps", lambda _: [])
        with pytest.raises((runtime.SequenceProcessFailure, runtime.SequenceProcessTimeout)) as caught:
            await runtime.discover(source, {}, tmp_path, checkpoint=checkpoint)
        assert saved[-1]["receipts"][0]["raw_response"] == "retained reply"
        info = caught.value.diagnostics
        assert info["phase"] == "observations" and info["timeout"] is timeout
        assert info["completed_receipts"] == 1 and info["error_codes"] == ["MODEL_QUOTA_OR_RATE_LIMIT"]
        assert "secret" not in json.dumps(info)
    asyncio.run(scenario())


def test_retry_does_not_erase_checkpoint_or_failure_history_before_new_work(tmp_path):
    video = tmp_path / "source.mp4"; video.write_bytes(b"synthetic")
    existing = {"code_sha256": "test", "receipts": [{"packet_id": "completed"}]}
    doc = {"id": "test", "analysis_engine": "SEQUENCE_V1", "full_report_status": "failed",
           "sequence_retry": existing, "sequence_failures": [{"phase": "preparation"}]}
    async def generate(*args, **kwargs):
        assert store.doc["sequence_retry"] == existing
        assert len(store.doc["sequence_failures"]) == 1
        raise runtime.SequenceProcessFailure({"phase": "observations", "returncode": 3, "error_codes": []})
    ns, store, _, _ = server_harness(video, doc, tmp_path,
        runtime=SimpleNamespace(enabled=lambda: True, generate=generate))
    asyncio.run(ns["generate_full_report_task"]("test"))
    assert store.doc["full_report_status"] == "failed"
    assert store.doc["sequence_retry"] == existing and len(store.doc["sequence_failures"]) == 2
    assert store.doc["sequence_failures"][-1]["returncode"] == 3


@pytest.mark.parametrize("change", [None, "claimed", "report", "source", "selection", "code", "status", "engine"])
def test_partial_retry_is_bound_to_this_failed_report_source_selection_and_code(change):
    retry = {"report_id": "one", "source_video_sha256": "source", "original_selection_values_sha256": "selection",
             "code_sha256": runtime.code_fingerprint(), "receipts": []}
    doc = {"id": "one", "analysis_engine": "SEQUENCE_V1", "full_report_status": "failed", "sequence_retry": retry}
    if change == "report": doc["id"] = "other"
    if change == "claimed": doc["full_report_status"] = "generating"
    if change == "source": retry["source_video_sha256"] = "other"
    if change == "selection": retry["original_selection_values_sha256"] = "other"
    if change == "code": retry["code_sha256"] = {}
    if change == "status": doc["full_report_status"] = "ready"
    if change == "engine": doc["analysis_engine"] = "LEGACY"
    resumed = runtime.retained_retry(doc, "source", "selection")
    assert (resumed is not None) is (change in {None, "claimed"})
    if resumed is not None:
        resumed["receipts"].append("mutation")
        assert retry["receipts"] == []


def test_incomplete_or_unverified_retry_cannot_be_published(retained):
    result = retained["result"]
    result.update(fresh_end_to_end_run=False, execution_mode="EXACT_REQUEST_RETRY",
                  retry_reused_packet_ids=[retained["receipts"][0]["packet_id"]], retry_reused_jobs=1)
    with pytest.raises(ValueError, match="RUN_INCOMPLETE"):
        bundle(retained)
    retained["receipts"][0]["retry_payload_verified"] = True
    assert bundle(retained)["events"]
    result["status"] = "PARTIAL_MODEL_RUN"
    with pytest.raises(ValueError, match="RUN_INCOMPLETE"):
        bundle(retained)


def test_existing_frontend_shows_verified_counts_and_joins_only_matching_proofs(tmp_path, retained):
    full = adapter.build_report({"summary": "Actions"}, bundle(retained))
    for c in full["video_comments"]:
        c.update(frame_url="/frames/"+c["evidence_id"]+".jpg", tele_clip_url="/clips/"+c["evidence_id"]+".mp4",
                 proof_frame_verified=True, identity_verified=True)
    joins = (ROOT / "frontend/src/lib/authorityJoin.mjs").as_uri()
    derive = (ROOT / "frontend/src/components/report-v2/derive.js").read_text().replace(
        '"../../lib/authorityJoin.mjs"', json.dumps(joins))
    module = tmp_path / "derive.mjs"
    module.write_text(derive)
    script = f'''
      import {{deriveV2}} from {json.dumps(module.as_uri())};
      import {{resolveProofClip}} from {json.dumps(joins)};
      let input='';for await (const chunk of process.stdin) input+=chunk;
      const full=JSON.parse(input), view=deriveV2({{full_report:full}});
      const clip=resolveProofClip(full.video_comments,{{eventId:full.video_comments[0].event_id}},true);
      const wrong=resolveProofClip(full.video_comments,{{eventId:'absent',timestamp:full.video_comments[0].timestamp}},true);
      console.log(JSON.stringify({{stats:view.matchStats,clip:clip?.event_id,wrong,highlight:view.videoHighlight}}));
    '''
    result = subprocess.run(["node", "--input-type=module", "-e", script], input=json.dumps(full),
                            text=True, capture_output=True, check=True)
    view = json.loads(result.stdout)
    stats = {r["label"]: r["value"] for r in view["stats"]}
    assert stats["Verified Goals"] == 1 and stats["Verified Assists"] == 3 and stats["Shots"] == 2
    assert view["clip"] == full["video_comments"][0]["event_id"] and view["wrong"] is None
    assert view["highlight"]["thumbVerified"] is True
