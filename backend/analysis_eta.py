"""Read-only, bounded estimates from comparable completed production runs.

No fallback stopwatch or invented duration. Source/configuration, video length,
stage, retries and observed spread determine whether a range can be shown.
"""
import asyncio
import hashlib
import json
import math
import time
from datetime import datetime, timedelta, timezone

_CACHE = {}
_CORE = ("player_tracking.py", "fix10a_runtime.py", "fix10b_runtime.py", "football_sequence_intelligence.py", "server.py")


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp()
    except (ValueError, TypeError, OverflowError):
        return None


def _signature(doc):
    manifest = doc.get("analysis_run_manifest") or {}
    if not isinstance(manifest, dict):
        return None
    hashes = manifest.get("backend_source_sha256") or {}
    if not isinstance(hashes, dict):
        return None
    if any(not hashes.get(name) for name in _CORE):
        return None
    try:
        return hashlib.sha256(json.dumps({"sources": {name: hashes[name] for name in _CORE},
                                     "configuration": manifest.get("configuration"),
                                     "runtime": manifest.get("runtime_versions")}, sort_keys=True).encode()).hexdigest()
    except (TypeError, ValueError):
        return None


def estimate_from_history(doc, history, now=None):
    now = now or datetime.now(timezone.utc)
    unknown = {"status": "unavailable"}
    if doc.get("full_report_status") not in ("generating", "verifying", "finalizing") or doc.get("retry_in_progress"):
        return unknown
    signature = _signature(doc)
    try:
        duration = float(doc.get("video_duration_sec") or 0)
    except (TypeError, ValueError):
        return unknown
    if not signature or not math.isfinite(duration) or duration <= 0:
        return unknown
    stage = doc.get("full_pipeline_stage") or "queued"
    # Queue and human-confirmation delays have no defensible countdown.
    if stage in ("queued", "full_start"):
        return unknown
    anchor = next((_timestamp(x.get("at")) for x in reversed(doc.get("full_pipeline_trace") or [])
                   if isinstance(x, dict) and x.get("stage", x.get("s")) == stage), None)
    if anchor is None or anchor > now.timestamp():
        return unknown
    samples = []
    for row in history:
        try:
            length = float(row.get("video_duration_sec") or 0)
            finish = _timestamp(row.get("full_report_run_finished_at"))
            start = _timestamp(row.get("full_report_started_at"))
            at = next((_timestamp(x.get("at")) for x in reversed(row.get("full_pipeline_trace") or [])
                       if isinstance(x, dict) and x.get("stage", x.get("s")) == stage), None)
            if (_signature(row) != signature or row.get("full_report_status") != "ready"
                    or row.get("full_report_retries") or row.get("doubt_moments")
                    or not duration * .75 <= length <= duration * 1.25
                    or None in (finish, start, at) or not start <= at < finish <= now.timestamp()
                    or finish < (now - timedelta(days=3)).timestamp()
                    or not 10 <= finish - start <= 7200):
                continue
            samples.append(finish - at)
        except (ValueError, TypeError, OverflowError):
            continue
    if len(samples) < 5:
        return unknown
    samples.sort()
    low = samples[int((len(samples) - 1) * .2)]
    high = samples[math.ceil((len(samples) - 1) * .85)]
    if low <= 0 or high / low > 4:
        return unknown  # heterogeneous runs cannot support a useful range
    iso = lambda seconds: datetime.fromtimestamp(seconds, timezone.utc).isoformat()
    return {"status": "overdue" if anchor + high <= now.timestamp() else "estimated",
            "earliest_at": iso(anchor + low), "latest_at": iso(anchor + high),
            "sample_count": len(samples), "calculated_at": now.isoformat()}


async def completion_estimate(collection, doc):
    """Cache only timing projections; never expose other reports or model data."""
    unknown = {"status": "unavailable"}
    if not _signature(doc) or doc.get("full_report_status") not in ("generating", "verifying", "finalizing"):
        return unknown
    cache_key = id(collection)
    cached = _CACHE.get(cache_key)
    if not cached or time.monotonic() - cached[0] > 120:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        projection = {"_id": 0, "full_report_started_at": 1, "full_report_run_finished_at": 1,
                      "full_report_status": 1, "full_report_retries": 1, "doubt_moments": 1,
                      "video_duration_sec": 1, "full_pipeline_trace": 1, "analysis_run_manifest": 1}
        try:
            query = collection.find({"full_report_status": "ready", "full_report": {"$exists": True, "$nin": [None, {}]},
                                     "full_report_run_finished_at": {"$gte": cutoff}}, projection)
            rows = await asyncio.wait_for(query.sort("full_report_run_finished_at", -1).limit(60).to_list(length=60), 2)
            # Bound worker memory even if a collection handle changes.
            if len(_CACHE) >= 8:
                _CACHE.clear()
            cached = (time.monotonic(), rows)
            _CACHE[cache_key] = cached
        except Exception:
            return unknown  # estimation failure never blocks status/readiness
    try:
        return estimate_from_history(doc, cached[1])
    except (TypeError, ValueError, OverflowError):
        return unknown
