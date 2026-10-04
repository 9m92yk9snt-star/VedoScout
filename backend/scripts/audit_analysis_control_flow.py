"""Read-only reproductions of analysis orchestration gaps, without server startup.

Execute selected functions from the actual source against synthetic boundaries.
No Mongo connection, video decoding, model call, upload, or production mutation.
These reproduce control flow; they are not end-to-end or video acceptance tests.
"""
from __future__ import annotations

import ast
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import sys
import time
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
import fix10b_runtime  # noqa: E402
import verified_stats  # noqa: E402


def load_function(filename, name, namespace):
    namespace.setdefault("Depends", lambda dependency: None)
    namespace.setdefault("get_current_user", None)
    source = ast.parse((BACKEND / filename).read_text())
    node = next(n for n in source.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    node.decorator_list = []
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future, node], type_ignores=[]))
    exec(compile(module, str(BACKEND / filename), "exec"), namespace)
    return namespace[name]


class Reports:
    def __init__(self, doc, parallel_reads=False):
        self.doc = deepcopy(doc)
        self.writes = []
        self.parallel_reads = parallel_reads
        self.read_count = 0
        self.read_barrier = asyncio.Event()

    async def find_one(self, query, *args):
        snapshot = deepcopy(self.doc)
        if self.parallel_reads:
            self.read_count += 1
            if self.read_count == 2:
                self.read_barrier.set()
            await self.read_barrier.wait()
        return snapshot

    def find(self, query, *args):
        eligible = self.doc.get("full_report_status") in query["full_report_status"]["$in"]
        if "$or" in query:
            cutoff = query["$or"][0]["full_report_started_at"]["$lt"]
            eligible = eligible and self.doc["full_report_started_at"] < cutoff

        async def rows():
            if eligible:
                yield deepcopy(self.doc)
        return rows()

    async def update_one(self, query, update):
        self.writes.append((deepcopy(query), deepcopy(update)))
        self.doc.update(update.get("$set") or {})
        return SimpleNamespace(modified_count=1)


async def watchdog_case(retries):
    now = datetime.now(timezone.utc)
    reports = Reports({"id": "synthetic", "full_report_status": "generating",
                       "full_report_started_at": (now - timedelta(minutes=30)).isoformat(),
                       "last_progress_at": now.isoformat(), "full_report_retries": retries})
    scheduled = []

    def create_task(coro):
        task = asyncio.create_task(coro)
        scheduled.append(task)
        return task

    async def job(report_id):
        return report_id

    fn = load_function("server.py", "_sweep_stuck_full_reports", {
        "datetime": datetime, "timezone": timezone, "timedelta": timedelta,
        "FULL_REPORT_STALL_SECONDS": 1200, "FULL_REPORT_MAX_RETRIES": 2,
        "db": SimpleNamespace(reports=reports), "logger": logging.getLogger("audit"),
        "asyncio": SimpleNamespace(create_task=create_task), "_full_report_with_heartbeat": job,
    })
    await fn(include_fresh=False)
    await asyncio.gather(*scheduled)
    return {"fresh_heartbeat": True, "initial_retries": retries,
            "jobs_scheduled": len(scheduled), "result_status": reports.doc["full_report_status"]}


async def parallel_request_case():
    reports = Reports({"id": "synthetic", "user_id": "owner", "is_paid": True}, parallel_reads=True)

    async def video(report_id):
        return SimpleNamespace(exists=lambda: True)

    fn = load_function("server.py", "generate_full_report", {
        "db": SimpleNamespace(reports=reports), "_ensure_report_video_local": video,
        "generate_full_report_task": object(), "now_iso": lambda: "synthetic-time",
    })
    queues = [SimpleNamespace(tasks=[], add_task=None) for _ in range(2)]
    for queue in queues:
        queue.add_task = lambda *args, queue=queue: queue.tasks.append(args)
    await asyncio.gather(*(fn("synthetic", queue, {"id": "owner", "role": "user"}) for queue in queues))
    return {"simultaneous_requests": 2, "queued_jobs": sum(len(q.tasks) for q in queues)}


async def trace_status_case():
    reports = Reports({"id": "synthetic", "user_id": "owner", "analysis_status": "analyzing",
                       "pipeline_trace": [{"s": "transcode_start", "at": "synthetic-time"}]})
    fn = load_function("server.py", "get_report_status", {"db": SimpleNamespace(reports=reports)})
    result = await fn("synthetic", {"id": "owner", "role": "user"})
    return {"saved_stage": "transcode_start", "returned_stage": result["pipeline_stage"]}


def evidence_stats_case():
    physical = {"recall_coverage": {"scan_complete": True, "verification_complete": True},
                "traces": [{"decoded_frames": [{"media_ms": 1000, "global_target": {
                    "proof_eligible": False}}], "strike_evidence": [], "outcome_evidence": []}]}
    scan = fix10b_runtime._scoring_scan({"metrics": {}}, {"coverage_complete": True}, physical)
    full = {"action_timeline": [], "cross_verification": {"status": "canonical_authority"}, "_scoring_scan": scan}
    verified_stats.apply_verified_stats_authority(full)
    return {"scan_coverage": scan["coverage_status"],
            "evidence_complete": scan["physical_recall_verification_complete"],
            "stats_available": full["verified_stats"]["goals_assists_available"],
            "displayed_stat_line": full.get("verified_stat_line")}


def ready_case():
    fn = load_function("unified_analysis_engine.py", "is_production_ready", {})
    return {"zero_accepted_events_ready": fn({"status": "ok", "sequence_analysis": {
        "coverage_complete": True}, "metrics": {"sequence_windows": 1}, "canonical_events": {"status": "empty"}})}


def provider_case():
    fn = load_function("physical_match_reconstruction.py", "_safe_provider", {})

    def fail(*args):
        raise RuntimeError("synthetic reader failure")
    return {"reader_exception_result": fn(fail, default=None)}


async def storage_failure_case():
    writes = []

    async def persist(db, report_id, fields):
        writes.append(fields)

    async def fail_trace(*args):
        raise RuntimeError("synthetic trace storage failure")

    fn = load_function("fix10a_runtime.py", "run", {
        "VERSION": 2, "_utc_now": lambda: "synthetic-time", "time": time,
        "asyncio": asyncio, "logger": logging.getLogger("audit"),
        "_persist_fix10a_fields": persist, "support_vision_enabled": lambda: False,
        "physical_match_reconstruction": SimpleNamespace(reconstruct_physical_match=lambda *args, **kwargs: {
            "status": "ok", "traces": [{"trace_id": "synthetic"}]}),
        "fix10b_runtime": SimpleNamespace(build_candidate=lambda *args: {"enabled": True}),
        "_persist_trace": fail_trace,
    })
    result = await fn(report_id="synthetic", video_path="synthetic-video", db=None,
                      unified_result={"status": "ok", "sequence_analysis": {"coverage_complete": True}})
    return {"reconstruction_succeeded": True, "trace_storage_succeeded": False,
            "returned_status": result["status"], "candidate_returned": "_fix10b_candidate" in result}


async def main():
    result = {
        "method": "actual-source functions with synthetic DB/task boundaries; not live integration",
        "active_watchdog": await watchdog_case(0),
        "active_watchdog_at_retry_limit": await watchdog_case(2),
        "parallel_generate_requests": await parallel_request_case(),
        "pipeline_stage": await trace_status_case(),
        "partial_evidence_stats": evidence_stats_case(),
        "empty_canonical_readiness": ready_case(),
        "support_provider_failure": provider_case(),
        "trace_storage_failure": await storage_failure_case(),
    }
    assert result["active_watchdog"]["jobs_scheduled"] == 1
    assert result["active_watchdog_at_retry_limit"]["result_status"] == "failed"
    assert result["parallel_generate_requests"]["queued_jobs"] == 2
    assert result["pipeline_stage"]["returned_stage"] is None
    assert result["partial_evidence_stats"]["displayed_stat_line"] == "0 goals · 0 assists · 0 shots"
    assert result["empty_canonical_readiness"]["zero_accepted_events_ready"] is True
    assert result["support_provider_failure"]["reader_exception_result"] is None
    assert result["trace_storage_failure"]["candidate_returned"] is False
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
