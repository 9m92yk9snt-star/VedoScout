"""FIX10A production runtime — physical match reconstruction for canonical reconciliation.

FIX10A now runs synchronously inside the production report pipeline. There is
no shadow feature flag, no background task and no fire-and-forget lifecycle.
FIX10A itself is a physical-evidence producer; FIX10B is the deterministic
canonical reconciliation authority that consumes its result.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import os
import re
import time
from pathlib import Path

import event_trace
import fix10a_goal_direction
import fix10a_vision_providers
import fix10b_runtime
import physical_match_reconstruction

logger = logging.getLogger("elite-scout")

VERSION = 2
SUPPORT_VISION_FLAG = "FIX10A_SUPPORT_VISION_ENABLED"


def support_vision_enabled() -> bool:
    return str(os.environ.get(SUPPORT_VISION_FLAG, "1")).strip().lower() in {
        "1", "true", "yes", "on"
    }


def _safe_component(value, fallback="trace") -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip(".-_")
    return text[:100] or fallback


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _persist_fix10a_fields(db, report_id: str, fields: dict) -> None:
    """Best-effort operational persistence; never allowed to corrupt a report."""
    if db is None or not isinstance(fields, dict):
        return
    safe = {k: v for k, v in fields.items() if str(k).startswith("fix10a_")}
    if not safe:
        return
    try:
        await db.reports.update_one({"id": report_id}, {"$set": safe})
    except Exception:
        logger.exception("[fix10a] %s: diagnostic persistence failed", report_id)


def _compact_physical_result(result: dict | None) -> dict:
    row = result if isinstance(result, dict) else {}
    return {
        "version": row.get("version"),
        "status": row.get("status"),
        "timebase": row.get("timebase"),
        "source_role": row.get("source_role"),
        "source_video": row.get("source_video") or {},
        "windows": row.get("windows") or [],
        "trace_summaries": row.get("trace_summaries") or [],
        "unresolved_reasons": row.get("unresolved_reasons") or [],
        "metrics": row.get("metrics") or {},
        "dense_traces_persisted_in_mongo": False,
        "mode": "production",
        "canonical_authority": False,
        "reconciliation_authority": "FIX10B",
    }


def _trace_key(report_id: str, trace: dict) -> tuple[str, str, bytes]:
    trace_id = _safe_component(trace.get("trace_id"), "trace")
    digest = event_trace.trace_sha256(trace)
    payload = event_trace.encode_trace_gzip(trace)
    key = (
        f"reports/{_safe_component(report_id, 'report')}/match-intelligence/"
        f"{trace_id}-{digest[:12]}.json.gz"
    )
    return key, digest, payload


async def _persist_trace(report_id: str, trace: dict, r2_storage, local_dir) -> dict:
    key, digest, payload = _trace_key(report_id, trace)
    summary = event_trace.compact_trace_summary(trace)
    manifest = {
        "trace_id": trace.get("trace_id"),
        "sha256": digest,
        "bytes_gzip": len(payload),
        "content_type": "application/gzip",
        "summary": summary,
        "storage": "unpersisted",
        "object_key": None,
        "url": None,
        "local_path": None,
    }
    configured = False
    try:
        configured = bool(r2_storage is not None and r2_storage.is_configured())
    except Exception:
        configured = False
    if configured:
        url = await asyncio.to_thread(
            r2_storage.upload_bytes, key, payload, "application/gzip"
        )
        manifest.update({"storage": "r2", "object_key": key, "url": url})
        return manifest

    if local_dir is not None:
        root = Path(local_dir) / _safe_component(report_id, "report") / "match-intelligence"
        await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)
        path = root / Path(key).name
        await asyncio.to_thread(path.write_bytes, payload)
        manifest.update({"storage": "local_diagnostic", "local_path": str(path)})
    return manifest


async def run(*, report_id: str, video_path: str, unified_result: dict,
              db, r2_storage=None, source_video: dict | None = None,
              local_dir=None, jersey_vote_provider=None,
              goal_geometry_provider=None, role_evidence=None,
              role_evidence_provider=None, vision_api_key: str | None = None) -> dict:
    """Run production FIX10A and return a proof-gated FIX10B candidate.

    The call is awaited by the main report pipeline. If reconstruction fails,
    the caller keeps the already verified FIX09B result as the fail-closed
    canonical fallback; no fabricated event is introduced.
    """
    result = unified_result if isinstance(unified_result, dict) else {}
    sequence = (
        result.get("sequence_analysis")
        if isinstance(result.get("sequence_analysis"), dict)
        else {}
    )
    if result.get("status") != "ok" or sequence.get("coverage_complete") is not True:
        logger.info(
            "[fix10a] %s: production SKIP reason=UNIFIED_RESULT_NOT_PRODUCTION_READY",
            report_id,
        )
        return {
            "version": VERSION,
            "status": "skipped",
            "reason": "UNIFIED_RESULT_NOT_PRODUCTION_READY",
            "mode": "production",
            "canonical_authority": False,
        }

    started_at = _utc_now()
    started_monotonic = time.monotonic()
    await _persist_fix10a_fields(db, report_id, {
        "fix10a_status": "running",
        "fix10a_version": VERSION,
        "fix10a_mode": "production",
        "fix10a_started_at": started_at,
        "fix10a_finished_at": None,
        "fix10a_elapsed_seconds": 0.0,
        "fix10a_error": None,
        "fix10a_canonical_authority": False,
        "fix10a_reconciliation_authority": "FIX10B",
    })
    logger.info("[fix10a] %s: production START", report_id)

    try:
        support_mode = {
            "enabled": False,
            "jersey_provider": bool(jersey_vote_provider),
            "goal_provider": bool(goal_geometry_provider),
            "goal_direction_provider": False,
            "role_provider": bool(role_evidence_provider),
        }
        if support_vision_enabled():
            api_key = str(vision_api_key or os.environ.get("EMERGENT_LLM_KEY") or "")
            if api_key:
                session_prefix = f"fix10a-{_safe_component(report_id, 'report')}"
                bundle = fix10a_vision_providers.build_shadow_providers(
                    api_key,
                    session_prefix,
                    str(video_path),
                )
                if jersey_vote_provider is None:
                    jersey_vote_provider = bundle.jersey_vote_provider
                if goal_geometry_provider is None:
                    goal_geometry_provider = fix10a_goal_direction.wrap_goal_geometry_provider(
                        bundle.goal_geometry_provider,
                        api_key,
                        session_prefix,
                        str(video_path),
                    )
                if role_evidence_provider is None:
                    role_evidence_provider = bundle.role_evidence_provider
                support_mode.update({
                    "enabled": True,
                    "jersey_provider": bool(jersey_vote_provider),
                    "goal_provider": bool(goal_geometry_provider),
                    "goal_direction_provider": isinstance(
                        goal_geometry_provider,
                        fix10a_goal_direction.GoalDirectionProvider,
                    ),
                    "role_provider": bool(role_evidence_provider),
                })

        physical = await asyncio.to_thread(
            physical_match_reconstruction.reconstruct_physical_match,
            str(video_path),
            result.get("sequence_plan") or {},
            sequence,
            result.get("scene_graph") or {},
            result.get("identity_authority") or {},
            jersey_vote_provider,
            source_video=source_video or {},
            goal_geometry_provider=goal_geometry_provider,
            role_evidence=role_evidence or {},
            role_evidence_provider=role_evidence_provider,
        )

        fix10b_candidate = fix10b_runtime.build_candidate(result, physical)

        manifests = []
        for trace in physical.get("traces") or []:
            if isinstance(trace, dict):
                manifests.append(
                    await _persist_trace(report_id, trace, r2_storage, local_dir)
                )

        compact = _compact_physical_result(physical)
        status = str(physical.get("status") or "unknown")
        elapsed = round(max(0.0, time.monotonic() - started_monotonic), 3)
        update = {
            "fix10a_status": status,
            "fix10a_version": VERSION,
            "fix10a_mode": "production",
            "fix10a_started_at": started_at,
            "fix10a_finished_at": _utc_now(),
            "fix10a_elapsed_seconds": elapsed,
            "fix10a_physical_summary": compact,
            "fix10a_trace_manifest": manifests,
            "fix10a_supporting_vision": support_mode,
            "fix10a_fix10b_summary": fix10b_candidate.get("summary") or {},
            "fix10a_error": None,
            "fix10a_canonical_authority": False,
            "fix10a_reconciliation_authority": "FIX10B",
        }
        await _persist_fix10a_fields(db, report_id, update)
        logger.info(
            "[fix10a] %s: production SUCCESS status=%s traces=%d "
            "support_vision=%s elapsed=%.3fs fix10b_proposals=%d",
            report_id,
            status,
            len(manifests),
            support_mode.get("enabled"),
            elapsed,
            int((fix10b_candidate.get("summary") or {}).get("proposals_applied") or 0),
        )
        return {
            **update,
            "status": status,
            "mode": "production",
            "_fix10b_candidate": fix10b_candidate,
        }
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:200]}"
        elapsed = round(max(0.0, time.monotonic() - started_monotonic), 3)
        logger.exception(
            "[fix10a] %s: production ERROR %s elapsed=%.3fs",
            report_id,
            error,
            elapsed,
        )
        update = {
            "fix10a_status": "error",
            "fix10a_version": VERSION,
            "fix10a_mode": "production",
            "fix10a_started_at": started_at,
            "fix10a_finished_at": _utc_now(),
            "fix10a_elapsed_seconds": elapsed,
            "fix10a_error": error,
            "fix10a_canonical_authority": False,
            "fix10a_reconciliation_authority": "FIX10B",
        }
        await _persist_fix10a_fields(db, report_id, update)
        return {**update, "status": "error", "mode": "production"}
