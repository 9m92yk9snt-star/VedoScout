"""Real retained model evidence + orchestration failure boundaries, no model spend."""
import asyncio
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
    assert provider == "emergent" and model == "gemini-2.5-pro" and timeout >= 179
    pipe.send({"status": "COMPLETED", "packet_id": job["packet_id"],
               "raw_response": json.dumps({"summary": "Synthetic transport boundary test",
                    "technical": {}, "tactical": {}, "physical": {}, "mentality": {}, "scores": {}})})
    pipe.close()


def test_writer_180_second_budget_reaches_owned_transport_without_network(monkeypatch):
    real = runtime.transport.run_jobs
    def synthetic_jobs(jobs, provider, model, **kwargs):
        return real(jobs, provider, model, **kwargs, worker=synthetic_report_worker)
    monkeypatch.setattr(runtime.transport, "run_jobs", synthetic_jobs)
    result = asyncio.run(runtime.write_facts("Synthetic test; no model request"))
    assert result["report"]["summary"] == "Synthetic transport boundary test"
    assert len(result["receipts"]) == 1
    with pytest.raises(ValueError, match="INVALID_EXECUTION_BUDGET"):
        real([], "emergent", "gemini-2.5-pro", deadline=time.monotonic()+1, per_call_s=211)


def test_writer_failure_keeps_paid_source_receipts_before_temp_cleanup(tmp_path, retained, monkeypatch):
    raw = json.loads((ROOT / "testdata/sequence-pilot-orman400/anchors.json").read_text())["raw_marker_anchors"]
    monkeypatch.setattr(runtime.pilot, "digest", lambda _: retained["source_video_sha256"])
    async def discovery(*args):
        return retained["result"], retained["replay_context"], retained["receipts"]
    async def writer(prompt):
        raise RuntimeError("SYNTHETIC_WRITER_FAILURE")
    saved = []
    async def checkpoint(values):
        saved.append(deepcopy(values))
    ns, _, _, _ = server_harness(tmp_path / "video.mp4", {"id": "test"}, tmp_path)
    with pytest.raises(RuntimeError, match="SYNTHETIC_WRITER_FAILURE"):
        asyncio.run(runtime.generate(tmp_path / "video.mp4", {"raw_marker_anchors": raw},
                    template=ns["FULL_REPORT_PROMPT"], discovery=discovery, writer=writer, checkpoint=checkpoint))
    assert len(saved) == 2
    assert len(saved[-1]["sequence_audit"]["receipts"]) == 13
    assert saved[-1]["canonical_events"]["events"]
    assert "full_report" not in saved[-1]


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


@pytest.mark.parametrize("fail_assets", [False, True])
def test_actual_server_bypasses_legacy_and_never_readies_failed_assets(tmp_path, retained, monkeypatch, fail_assets):
    monkeypatch.setenv("FULL_REPORT_ENGINE", "sequence_v1")
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


def test_owned_process_timeout_reaps_the_child(tmp_path):
    with pytest.raises(TimeoutError):
        asyncio.run(runtime.owned_process([sys.executable, "-c", "import time; time.sleep(30)"],
                                          timeout_s=.1, log_path=tmp_path / "process.log"))


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
