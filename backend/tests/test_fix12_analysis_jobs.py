"""Concurrent admission, heartbeat recovery, and stale-owner publication tests."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BACKEND), str(BACKEND / "scripts")]
import analysis_jobs as jobs  # noqa: E402
from audit_analysis_control_flow import load_function  # noqa: E402


def matches(doc, query):
    for key, value in query.items():
        if key == "$and":
            if not all(matches(doc, q) for q in value):
                return False
        elif key == "$or":
            if not any(matches(doc, q) for q in value):
                return False
        elif isinstance(value, dict):
            actual = doc.get(key)
            for op, expected in value.items():
                if op == "$in" and actual not in expected:
                    return False
                if op == "$nin" and actual in expected:
                    return False
                if op == "$exists" and (key in doc) != expected:
                    return False
                if op == "$lt" and (actual is None or actual >= expected):
                    return False
                if op == "$gt" and (actual is None or actual <= expected):
                    return False
        elif doc.get(key) != value:
            return False
    return True


class Reports:
    def __init__(self, doc):
        self.doc = deepcopy(doc)
        self.lock = asyncio.Lock()
        self.writes = []

    async def find_one(self, *_args, **_kwargs):
        await asyncio.sleep(0)
        return deepcopy(self.doc)

    def find(self, query, *_args):
        async def rows():
            if matches(self.doc, query):
                yield deepcopy(self.doc)
        return rows()

    async def update_one(self, query, update, *args, **kwargs):
        async with self.lock:
            if not matches(self.doc, query):
                return SimpleNamespace(matched_count=0, modified_count=0)
            self.doc.update(deepcopy(update.get("$set") or {}))
            for key, value in (update.get("$inc") or {}).items():
                self.doc[key] = self.doc.get(key, 0) + value
            for key in update.get("$unset") or {}:
                self.doc.pop(key, None)
            self.writes.append(deepcopy(update))
            return SimpleNamespace(matched_count=1, modified_count=1)

    async def find_one_and_update(self, query, update, **kwargs):
        result = await self.update_one(query, update)
        return deepcopy(self.doc) if result.matched_count else None


async def test_parallel_admission_schedules_one_owner():
    reports = Reports({"id": "r", "is_paid": True})
    leases = await asyncio.gather(*(jobs.claim(reports, "r") for _ in range(8)))
    assert sum(lease is not None for lease in leases) == 1
    assert reports.doc["full_report_run_id"] == next(lease.run_id for lease in leases if lease)


@pytest.mark.parametrize("startup", [False, True])
@pytest.mark.parametrize("retries", [0, 2])
async def test_watchdog_never_restarts_fresh_heartbeat_even_at_limit(startup, retries):
    now = datetime.now(timezone.utc)
    reports = Reports({"id": "r", "full_report_status": "generating", "full_report_retries": retries,
                       "full_report_started_at": (now - timedelta(minutes=52)).isoformat(),
                       "last_progress_at": now.isoformat()})
    scheduled = []
    fn = load_function("server.py", "_sweep_stuck_full_reports", {
        "datetime": datetime, "timezone": timezone, "analysis_jobs": jobs, "uuid": uuid,
        "FULL_REPORT_STALL_SECONDS": 1200, "FULL_REPORT_MAX_RETRIES": 2,
        "db": SimpleNamespace(reports=reports), "logger": logging.getLogger("test"),
        "asyncio": SimpleNamespace(create_task=scheduled.append),
    })
    assert await fn(include_fresh=startup) == 0
    assert not scheduled and reports.doc["full_report_status"] == "generating"


async def test_recovery_is_atomic_and_revokes_old_owner(monkeypatch):
    clock = datetime.now(timezone.utc)
    monkeypatch.setattr(jobs, "utc_now", lambda: clock)
    reports = Reports({"id": "r"})
    old = await jobs.claim(reports, "r", stall_seconds=60)
    clock += timedelta(seconds=61)
    leases = await asyncio.gather(*(jobs.claim(reports, "r", stall_seconds=60, recover=True) for _ in range(4)))
    assert sum(lease is not None for lease in leases) == 1
    assert reports.doc["full_report_retries"] == 1
    current = next(lease for lease in leases if lease)
    with pytest.raises(jobs.LeaseLost):
        await jobs.heartbeat(reports, old)
    fenced = jobs.FencedReports(reports)
    token = jobs.CURRENT_RUN.set(old)
    try:
        with pytest.raises(jobs.LeaseLost):
            await fenced.update_one({"id": "r"}, {"$set": {"full_report": "stale", "full_report_status": "ready"}})
    finally:
        jobs.CURRENT_RUN.reset(token)
    assert reports.doc["full_report_run_id"] == current.run_id
    assert "full_report" not in reports.doc


async def test_healthy_lease_and_completed_report_cannot_be_reclaimed():
    reports = Reports({"id": "r"})
    lease = await jobs.claim(reports, "r")
    await jobs.heartbeat(reports, lease)
    assert await jobs.claim(reports, "r", recover=True) is None
    token = jobs.CURRENT_RUN.set(lease)
    try:
        await jobs.FencedReports(reports).update_one({"id": "r"}, {"$set": {"full_report_status": "ready"}})
    finally:
        jobs.CURRENT_RUN.reset(token)
    assert await jobs.claim(reports, "r") is None


@pytest.mark.parametrize("counter", [None, ""])
async def test_expired_legacy_null_retry_counter_can_be_recovered(counter):
    now = datetime.now(timezone.utc)
    reports = Reports({"id": "r", "full_report_status": "generating", "full_report_retries": counter,
                       "last_progress_at": (now - timedelta(minutes=25)).isoformat()})
    lease = await jobs.claim(reports, "r", recover=True, now=now)
    assert lease is not None and reports.doc["full_report_retries"] == 1


async def test_manual_start_uses_same_atomic_heartbeat_path():
    reports = Reports({"id": "r", "user_id": "owner", "is_paid": True})
    queues = []

    async def video(_rid):
        return SimpleNamespace(exists=lambda: True)

    fn = load_function("server.py", "generate_full_report", {
        "db": SimpleNamespace(reports=reports), "analysis_jobs": jobs,
        "_ensure_report_video_local": video, "_full_report_with_heartbeat": "leased_runner",
    })
    background = SimpleNamespace(add_task=lambda *args: queues.append(args))
    results = await asyncio.gather(*(fn("r", background, {"id": "owner"}) for _ in range(4)))
    assert len(queues) == 1 and queues[0][0] == "leased_runner"
    assert sum(r["status"] == "generating" for r in results) == 1


async def test_run_scope_copies_into_background_tasks_and_threads():
    lease = jobs.RunLease("r", "run", 1200)
    token = jobs.CURRENT_RUN.set(lease)
    try:
        async def read_context():
            return jobs.CURRENT_RUN.get()
        assert await asyncio.create_task(read_context()) == lease
        assert await asyncio.to_thread(jobs.CURRENT_RUN.get) == lease
    finally:
        jobs.CURRENT_RUN.reset(token)


async def test_run_audit_preserves_outputs_after_next_run_claim():
    reports = Reports({"id": "r"})
    old = await jobs.claim(reports, "r")
    runs = Reports({"run_id": old.run_id})
    fenced = jobs.FencedReports(reports, runs)
    token = jobs.CURRENT_RUN.set(old)
    try:
        await fenced.update_one({"id": "r"}, {"$set": {"football_sequence_raw": {"sequence": "original"},
                                                          "canonical_events": {"events": []}}})
    finally:
        jobs.CURRENT_RUN.reset(token)
    await reports.update_one({"id": "r"}, {"$set": {"full_report_status": "failed"}})
    fresh = await jobs.claim(reports, "r")
    assert fresh.run_id != old.run_id
    assert runs.doc["outputs.football_sequence_raw"] == {"sequence": "original"}
    token = jobs.CURRENT_RUN.set(old)
    try:
        with pytest.raises(jobs.LeaseLost):
            await fenced.update_one({"id": "r"}, {"$set": {"canonical_events": {"events": ["stale"]}}})
    finally:
        jobs.CURRENT_RUN.reset(token)
    assert runs.doc["outputs.canonical_events"] == {"events": []}


def test_manifest_records_actual_bytes_and_original_taps(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"canonical video")
    taps = [{"t": 1.23, "box": {"x": .1, "y": .2, "w": .1, "h": .3}, "verify": False}]
    monkeypatch.setenv("DEPLOYED_GIT_SHA", "not-a-commit")
    monkeypatch.delenv("GIT_SHA", raising=False)
    result = jobs.manifest(video, taps, {"identity_timeline_hz": 5})
    assert result["deployed_git_sha"] is None
    assert result["source_video_sha256"] == jobs.file_sha256(video)
    assert result["original_tap_count"] == 1
    assert result["backend_source_sha256"]["analysis_jobs.py"] == jobs.file_sha256(BACKEND / "analysis_jobs.py")
    changed = jobs.manifest(video, [{**taps[0], "verify": True}], {})
    assert changed["original_taps_sha256"] != result["original_taps_sha256"]


async def test_heartbeat_does_not_keep_a_hung_job_alive_forever():
    reports = Reports({"id": "r"})
    lease = await jobs.claim(reports, "r")
    cancelled = asyncio.Event()
    async def hung(_rid):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    async def trace(*_args):
        pass
    runs = Reports({"run_id": lease.run_id})
    wrapper = load_function("server.py", "_full_report_with_heartbeat", {
        "analysis_jobs": jobs, "asyncio": asyncio, "logger": logging.getLogger("test"),
        "db": SimpleNamespace(reports=jobs.FencedReports(reports), analysis_runs=runs),
        "generate_full_report_task": hung, "_trace": trace, "FULL_REPORT_MAX_RUN_SECONDS": .01,
        "now_iso": lambda: datetime.now(timezone.utc).isoformat(),
    })
    await wrapper("r", lease)
    assert cancelled.is_set() and reports.doc["full_report_status"] == "failed"
    assert "time limit" in reports.doc["full_report_error"]
    assert jobs.CURRENT_RUN.get() is None


def test_evidence_asset_directories_are_owned_by_run(tmp_path):
    fn = load_function("server.py", "_analysis_frames_dir", {"UPLOAD_DIR": tmp_path, "analysis_jobs": jobs})
    first, second = jobs.RunLease("r", "one", 1200), jobs.RunLease("r", "two", 1200)
    token = jobs.CURRENT_RUN.set(first)
    try:
        path1 = fn("r")
        jobs.CURRENT_RUN.set(second)
        path2 = fn("r")
    finally:
        jobs.CURRENT_RUN.reset(token)
    assert path1 != path2 and path1 == tmp_path / "frames/r/one"
    assert fn("r") == tmp_path / "frames/r"


@pytest.mark.parametrize("failure", [False, True])
async def test_model_audit_retains_malformed_response_and_safe_error_type(tmp_path, failure):
    video = tmp_path / "model.mp4"
    video.write_bytes(b"model rendition")
    collection = Reports({})
    # Call IDs are generated inside the adapter; this boundary records writes.
    async def persist(query, update, **kwargs):
        collection.doc.update(update["$set"])
    collection.update_one = persist
    class Chat:
        async def send_message(self, _message):
            if failure:
                raise RuntimeError("private transport detail")
            return "malformed JSON model response"
    token = jobs.CURRENT_RUN.set(jobs.RunLease("r", "run", 1200))
    try:
        call = jobs.model_call(collection, Chat(), object(), session_id="sequence-retry",
                               video_path=video, prompt="observe actual actions", timeout_s=1)
        if failure:
            with pytest.raises(RuntimeError):
                await call
            assert collection.doc["status"] == "error" and collection.doc["error_type"] == "RuntimeError"
            assert "private transport detail" not in str(collection.doc)
        else:
            assert await call == "malformed JSON model response"
            assert collection.doc["raw_response"] == "malformed JSON model response"
            assert collection.doc["status"] == "responded" and not collection.doc["raw_response_truncated"]
        assert collection.doc["run_id"] == "run" and collection.doc["video_sha256"] == jobs.file_sha256(video)
    finally:
        jobs.CURRENT_RUN.reset(token)
    assert jobs.CURRENT_RUN.get() is None
