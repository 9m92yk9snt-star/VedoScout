"""Atomic full-analysis admission and run-scoped report writes.

No worker can take a live lease, including at application startup. A heartbeat
extends the lease; an expired owner can neither publish nor renew after takeover.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import uuid
import hashlib
import json
import os
import logging
import asyncio
from importlib import metadata
from pathlib import Path

IN_FLIGHT = ("generating", "verifying", "finalizing", "awaiting_confirmation")
CURRENT_RUN = ContextVar("full_analysis_run", default=None)
logger = logging.getLogger("elite-scout")


def audit_fields(fields):
    """Persist actual run outputs as they arrive, including interrupted runs."""
    return {k: v for k, v in fields.items() if k.startswith(("fix10a_", "fix10b_", "unified_", "football_sequence_"))
            or k in {"analysis_run_manifest", "canonical_events", "event_ledger", "football_scene_graph",
                     "identity_timeline", "identity_timeline_compare", "full_report_status", "full_report_error"}}


class LeaseLost(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest(video_path, anchors, configuration):
    """Record actual sources/configuration; never infer a deployed commit."""
    backend = Path(__file__).resolve().parent
    source_hashes = {p.name: file_sha256(p) for p in sorted(backend.glob("*.py"))}
    raw_sha = os.environ.get("DEPLOYED_GIT_SHA") or os.environ.get("GIT_SHA") or ""
    git_sha = raw_sha if len(raw_sha) == 40 and all(c in "0123456789abcdef" for c in raw_sha.lower()) else None
    taps = [{k: a[k] for k in ("t", "box", "segment", "verify") if k in a}
            for a in anchors or [] if isinstance(a, dict)]
    versions = {}
    for package in ("numpy", "opencv-python", "opencv-python-headless"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            pass
    detector = backend / "models" / "yolov8n.onnx"
    return {"deployed_git_sha": git_sha, "backend_source_sha256": source_hashes,
            "runtime_versions": versions, "person_detector_sha256": file_sha256(detector) if detector.is_file() else None,
            "source_video_sha256": file_sha256(video_path), "source_video_role": "CANONICAL_WEB_VIDEO",
            "original_taps_sha256": hashlib.sha256(json.dumps(taps, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "original_tap_count": len(taps), "configuration": configuration}


async def model_call(collection, chat, message, *, session_id, video_path, prompt, timeout_s):
    """Retain responses before parsing, including malformed JSON and retries.

    One bounded document per call avoids growing the run document without
    limit. No API keys or transport error strings are copied into the audit.
    Failure to store an audit never replaces a successful model response.
    """
    lease = CURRENT_RUN.get()
    call_id = uuid.uuid4().hex

    async def persist(fields):
        if lease is None or collection is None:
            return
        try:
            await collection.update_one({"call_id": call_id}, {"$set": {
                "run_id": lease.run_id, "report_id": lease.report_id,
                "session_id": session_id, "model": "gemini-2.5-pro", **fields}}, upsert=True)
        except Exception:
            logger.exception("[analysis-run] %s/%s model audit persistence failed", lease.report_id, lease.run_id)

    if lease:
        try:
            source_hash = await asyncio.to_thread(file_sha256, video_path)
        except Exception:
            source_hash = None
        await persist({"status": "started", "started_at": utc_now().isoformat(),
                       "video_sha256": source_hash, "video_role": "MODEL_RENDITION",
                       "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()})
    try:
        response = await asyncio.wait_for(chat.send_message(message), timeout=timeout_s)
    except BaseException as exc:
        await persist({"status": "cancelled" if isinstance(exc, asyncio.CancelledError) else "error",
                       "error_type": type(exc).__name__, "finished_at": utc_now().isoformat()})
        raise
    if lease:
        payload = (response if isinstance(response, str) else str(response)).encode()
        await persist({"status": "responded", "finished_at": utc_now().isoformat(),
                       "response_sha256": hashlib.sha256(payload).hexdigest(), "response_bytes": len(payload),
                       "raw_response": payload[:8 * 1024 * 1024].decode(errors="ignore"),
                       "raw_response_truncated": len(payload) > 8 * 1024 * 1024})
    return response


async def optional_observation(awaitable):
    """An unavailable semantic observer cannot veto independent physical work."""
    try:
        result = await awaitable
        return (result, None) if isinstance(result, dict) else ({}, "ModelResponseNotObject")
    except LeaseLost:
        raise
    except Exception as exc:
        return {}, type(exc).__name__


def expired_query(now, stall_seconds):
    """Lease-first expiry, heartbeat-first compatibility for pre-lease jobs."""
    cutoff = (now - timedelta(seconds=stall_seconds)).isoformat()
    return {"$or": [
        {"full_report_lease_expires_at": {"$lt": now.isoformat(), "$nin": [None, ""]}},
        {"full_report_lease_expires_at": {"$in": [None, ""]}, "$or": [
            {"last_progress_at": {"$lt": cutoff, "$nin": [None, ""]}},
            {"last_progress_at": {"$in": [None, ""]}, "$or": [
                {"full_report_started_at": {"$lt": cutoff, "$nin": [None, ""]}},
                {"full_report_started_at": {"$in": [None, ""]}},
            ]},
        ]},
    ]}


@dataclass(frozen=True)
class RunLease:
    report_id: str
    run_id: str
    stall_seconds: int

    def query(self):
        return {"id": self.report_id, "full_report_run_id": self.run_id,
                "full_report_lease_expires_at": {"$gt": utc_now().isoformat()}}


async def claim(reports, report_id, *, stall_seconds=1200, recover=False, max_retries=2, now=None):
    now = now or utc_now()
    lease = RunLease(report_id, uuid.uuid4().hex, stall_seconds)
    query = {"id": report_id}
    update = {"$set": {
        "full_report_run_id": lease.run_id, "full_report_status": "generating",
        "full_report_error": None, "full_report_started_at": now.isoformat(),
        "last_progress_at": now.isoformat(), "full_report_heartbeat_at": now.isoformat(),
        "full_report_lease_expires_at": (now + timedelta(seconds=stall_seconds)).isoformat(),
        "full_pipeline_stage": "queued", "full_pipeline_trace": [],
    }}
    if recover:
        query.update({"full_report_status": {"$in": list(IN_FLIGHT)}, **expired_query(now, stall_seconds)})
        # Old documents may explicitly store null/empty counters. Mongo $inc
        # cannot increment null; normalize only while the same job is expired.
        # This does not claim ownership, and cannot alter a renewed/taken lease.
        await reports.update_one({**query, "full_report_retries": {"$in": [None, ""]}},
                                 {"$set": {"full_report_retries": 0}})
        query["$and"] = [{"$or": [{"full_report_retries": {"$lt": max_retries}},
                                  {"full_report_retries": {"$exists": False}}]}]
        update["$inc"] = {"full_report_retries": 1}
    else:
        query["full_report_status"] = {"$nin": [*IN_FLIGHT, "ready"]}
        update["$set"]["full_report_retries"] = 0
    # ReturnDocument.AFTER is True; keeping this module independent of Motor
    # makes the concurrency contract testable without server startup.
    doc = await reports.find_one_and_update(query, update, return_document=True)
    return lease if doc else None


async def heartbeat(reports, lease):
    now = utc_now()
    result = await reports.update_one(lease.query(), {"$set": {
        "last_progress_at": now.isoformat(), "full_report_heartbeat_at": now.isoformat(),
        "full_report_lease_expires_at": (now + timedelta(seconds=lease.stall_seconds)).isoformat(),
    }})
    if result.matched_count != 1:
        raise LeaseLost("Full analysis lease expired or superseded")


class FencedReports:
    """Motor collection delegate; only writes to the current run are fenced.

    The context is copied by asyncio tasks and to_thread. Unrelated requests
    and collections keep their ordinary behavior. Upserts are forbidden for
    a run write so a superseded owner cannot recreate a report.
    """
    def __init__(self, reports, runs=None):
        self.raw = reports
        self.runs = runs

    def __getattr__(self, name):
        return getattr(self.raw, name)

    async def update_one(self, query, update, *args, **kwargs):
        lease = CURRENT_RUN.get()
        if lease and query.get("id") == lease.report_id:
            if kwargs.get("upsert") or (args and args[0]):
                raise ValueError("Analysis writes cannot upsert")
            query = {"$and": [query, lease.query()]}
            result = await self.raw.update_one(query, update, *args, **kwargs)
            if result.matched_count != 1:
                raise LeaseLost("Superseded analysis report write rejected")
            fields = audit_fields(update.get("$set") or {})
            pushes = audit_fields(update.get("$push") or {})
            if self.runs is not None and (fields or pushes):
                try:
                    audit_update = {"$set": {"report_id": lease.report_id, "updated_at": utc_now().isoformat(),
                                             **{f"outputs.{k}": v for k, v in fields.items()}}}
                    if pushes:
                        audit_update["$push"] = {f"outputs.{k}": v for k, v in pushes.items()}
                    await self.runs.update_one(
                        {"run_id": lease.run_id}, audit_update, upsert=True)
                except Exception:
                    logger.exception("[analysis-run] %s/%s audit persistence failed", lease.report_id, lease.run_id)
            return result
        return await self.raw.update_one(query, update, *args, **kwargs)


class FencedDatabase:
    def __init__(self, database):
        self.raw = database
        self.reports = FencedReports(database.reports, database.analysis_runs)

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def __getitem__(self, name):
        return self.reports if name == "reports" else self.raw[name]
