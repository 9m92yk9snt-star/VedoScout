"""Real retained model evidence + orchestration failure boundaries, no model spend."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import sys

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
