"""Measured deadline ranges never imply completion or restart analysis."""
import asyncio
import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import analysis_eta as eta


def fixture(now=None):
    now = now or datetime.now(timezone.utc)
    manifest = {"backend_source_sha256": {k: "same-source" for k in eta._CORE},
                "configuration": {"model": "real-model", "budget": 16}, "runtime_versions": {"numpy": "same"}}
    iso = lambda seconds: (now + timedelta(seconds=seconds)).isoformat()
    current = {"full_report_status": "generating", "video_duration_sec": 76, "analysis_run_manifest": manifest,
               "full_pipeline_stage": "sequence_model_start", "full_pipeline_trace": [{"stage": "sequence_model_start", "at": iso(-60)}]}
    rows = [{"full_report_status": "ready", "video_duration_sec": 76, "analysis_run_manifest": copy.deepcopy(manifest),
             "full_report_started_at": iso(-2000), "full_report_run_finished_at": iso(-1000),
             "full_pipeline_trace": [{"stage": "sequence_model_start", "at": iso(-1000-remaining)}]}
            for remaining in [300, 320, 340, 360, 380, 400]]
    return current, rows, now


def test_range_comes_from_same_stage_of_completed_comparable_runs():
    doc, rows, now = fixture(); before = copy.deepcopy((doc, rows))
    result = eta.estimate_from_history(doc, rows, now)
    assert result["status"] == "estimated" and result["sample_count"] == 6
    assert datetime.fromisoformat(result["earliest_at"]).timestamp() == now.timestamp() + 260
    assert datetime.fromisoformat(result["latest_at"]).timestamp() == now.timestamp() + 340
    assert (doc, rows) == before
    assert not {"report_id", "analysis_complete", "percentage"}.intersection(result)


@pytest.mark.parametrize("change", [
    {"full_report_status": "failed"}, {"full_report_status": "verifying"},
    {"video_duration_sec": 190}, {"full_report_retries": 1}, {"doubt_moments": [{}]},
    {"full_report_run_finished_at": "invalid"}, {"full_report_started_at": "invalid"},
    {"full_pipeline_trace": []}, {"analysis_run_manifest": {}},
])
def test_insufficient_or_incomparable_history_never_fabricates_time(change):
    doc, rows, now = fixture()
    for row in rows[:2]: row.update(change)
    assert eta.estimate_from_history(doc, rows, now) == {"status": "unavailable"}


@pytest.mark.parametrize("change", [
    {"full_report_status": "awaiting_confirmation"}, {"full_report_status": "ready"},
    {"full_pipeline_stage": "queued"}, {"retry_in_progress": True},
    {"video_duration_sec": float("nan")}, {"video_duration_sec": "bad"},
    {"full_pipeline_trace": []}, {"analysis_run_manifest": {}},
])
def test_unknown_work_and_human_delays_have_no_countdown(change):
    doc, rows, now = fixture(); doc.update(change)
    assert eta.estimate_from_history(doc, rows, now) == {"status": "unavailable"}


def test_expired_prediction_is_overdue_not_a_five_second_floor():
    doc, rows, now = fixture()
    doc["full_pipeline_trace"][0]["at"] = (now-timedelta(seconds=500)).isoformat()
    result = eta.estimate_from_history(doc, rows, now)
    assert result["status"] == "overdue"
    assert datetime.fromisoformat(result["latest_at"]) < now


def test_different_source_or_configuration_cannot_supply_an_estimate():
    doc, rows, now = fixture()
    rows[0]["analysis_run_manifest"]["backend_source_sha256"]["server.py"] = "different"
    rows[1]["analysis_run_manifest"]["configuration"]["budget"] = 2
    assert eta.estimate_from_history(doc, rows, now)["status"] == "unavailable"


def test_old_and_future_runs_and_excessive_variance_are_excluded():
    doc, rows, now = fixture()
    for row in rows:
        row["full_report_run_finished_at"] = (now+timedelta(seconds=10)).isoformat()
    assert eta.estimate_from_history(doc, rows, now)["status"] == "unavailable"
    doc, rows, now = fixture()
    for row in rows:
        row["full_report_run_finished_at"] = (now-timedelta(days=4)).isoformat()
    assert eta.estimate_from_history(doc, rows, now)["status"] == "unavailable"
    doc, rows, now = fixture()
    for i,row in enumerate(rows):
        row["full_pipeline_trace"][0]["at"] = (datetime.fromisoformat(row["full_report_run_finished_at"])-timedelta(seconds=20 if i<3 else 500)).isoformat()
    assert eta.estimate_from_history(doc, rows, now)["status"] == "unavailable"


def test_history_lookup_is_bounded_cached_and_optional():
    eta._CACHE.clear(); doc, rows, _ = fixture(); calls=[]
    class Cursor:
        def sort(self, *args): calls.append(("sort",args)); return self
        def limit(self, value): calls.append(("limit",value)); return self
        async def to_list(self, length): calls.append(("length",length)); return rows
    def find(query, projection):
        calls.append(("find",query,projection)); return Cursor()
    collection = SimpleNamespace(find=find)
    for _ in range(2): assert asyncio.run(eta.completion_estimate(collection,doc))["status"]=="estimated"
    assert sum(x[0]=="find" for x in calls)==1
    assert ("limit",60) in calls and ("length",60) in calls
    assert not {"video_url", "user_id", "player_details", "full_report"}.intersection(calls[0][2])
    eta._CACHE.clear()
    def broken(*args): raise RuntimeError("unavailable")
    fallback = asyncio.run(eta.completion_estimate(SimpleNamespace(find=broken),doc))
    assert fallback["status"] == "estimated" and fallback["provisional"] is True
    eta._CACHE.clear()


def test_sequence_has_a_starting_estimate_without_legacy_manifest_or_history():
    now = datetime.now(timezone.utc)
    doc = {"analysis_engine": "SEQUENCE_V1", "is_paid": True, "video_duration_sec": 77,
           "full_report_status": "generating", "full_report_started_at": now.isoformat()}
    result = eta.workload_estimate(doc, now)
    assert result["provisional"] and result["sample_count"] == 1
    assert 600 < (datetime.fromisoformat(result["earliest_at"])-now).total_seconds() < 700
    assert 1100 < (datetime.fromisoformat(result["latest_at"])-now).total_seconds() < 1300
    assert "report_id" not in result and "analysis_complete" not in result


def test_estimate_updates_from_completed_work_then_writer_and_assets():
    now = datetime.now(timezone.utc)
    doc = {"analysis_engine": "SEQUENCE_V1", "full_report_status": "generating",
           "sequence_progress": {"phase": "source", "updated_at": now.isoformat(), "initial_total": 10,
                                 "initial_completed": 2, "mean_job_seconds": 85}}
    first = eta.workload_estimate(doc, now)
    doc["sequence_progress"]["initial_completed"] = 8
    later = eta.workload_estimate(doc, now)
    assert datetime.fromisoformat(later["latest_at"]) < datetime.fromisoformat(first["latest_at"])
    doc["sequence_progress"] = {"phase": "writer", "started_at": now.isoformat()}
    writer = eta.workload_estimate(doc, now)
    doc["sequence_progress"]["phase"] = "assets"
    assert datetime.fromisoformat(eta.workload_estimate(doc, now)["latest_at"]) < datetime.fromisoformat(writer["latest_at"])


def test_provisional_time_expiring_never_marks_a_report_ready():
    now = datetime.now(timezone.utc)
    doc = {"is_paid": True, "full_report_status": "generating", "full_report_started_at": (now-timedelta(hours=1)).isoformat()}
    assert eta.workload_estimate(doc, now)["status"] == "overdue"
    assert doc["full_report_status"] == "generating"
    doc["full_report_status"] = "failed"
    assert eta.workload_estimate(doc, now) == {"status": "unavailable"}
