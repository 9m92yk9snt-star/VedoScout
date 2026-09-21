"""
analysis_watchdog.py — Session 131

Recurring root cause: `background.add_task(...)` and `asyncio.create_task(...)`
are IN-MEMORY only. When the FastAPI worker restarts (deploy rollout, hot-
reload on code edit, OOM kill, k8s pod cycle, `sudo supervisorctl restart
backend`), any in-flight `analyze_preview_task` disappears. The Mongo
report doc stays at `analysis_status="analyzing"` + `progress_step=4`
forever, with no recovery path — the user sees an eternal spinner.

This module adds three layers of defence, all idempotent:

  1. **Heartbeat** — every `progress_step` update also writes a
     `last_progress_at` ISO timestamp so a sweeper can detect stalls
     without waiting the full 15-min hard timeout.
  2. **Startup sweep** — on every FastAPI boot, scan for reports
     `status=analyzing` whose `last_progress_at` is older than
     STALL_THRESHOLD_SECONDS (default 5 min). Mark them `failed` with a
     recoverable error message + refund the user's upload eligibility.
  3. **Periodic watchdog** — an asyncio background loop wakes every 60 s
     and does the same sweep. Belt + suspenders for reports that stall
     while the worker was up (e.g. Gemini network stall + task cancelled
     externally).

Public API (imported by server.py):
    heartbeat(report_id: str) -> dict         # $set fragment for update_one
    stamp_progress(db, report_id, step)       # convenience combined update
    sweep_stalled_reports(db, refund_cb)      # one-shot idempotent sweep
    start_watchdog(db, refund_cb)             # kicks off the periodic loop
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# ── Tunables ───────────────────────────────────────────────────────────────
STALL_THRESHOLD_SECONDS = 300  # 5 minutes with no heartbeat -> declare stall
WATCHDOG_INTERVAL_SECONDS = 60  # sweep cadence

# Backwards-compat: legacy reports written before Session 131 didn't record a
# `last_progress_at` field. To avoid flagging every historic report as stalled
# on the first boot after this deploy, also require `created_at` to be older
# than this and status still analyzing.
LEGACY_ANALYZING_AGE_SECONDS = 900  # 15 min — after this any analyzing report
                                    # is definitionally lost (matches the hard
                                    # timeout in `_analyze_preview_task_with_timeout`)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def heartbeat(step: Optional[int] = None) -> dict:
    """Return the $set fragment to merge into a report update to record a
    heartbeat. When `step` is provided it is written too — makes the common
    "advance progress + heartbeat" case a one-liner."""
    frag: dict = {"last_progress_at": _utcnow_iso()}
    if step is not None:
        frag["progress_step"] = int(step)
    return frag


async def stamp_progress(db, report_id: str, step: Optional[int] = None, **extra) -> None:
    """Convenience: update `progress_step` + heartbeat + any extra fields in a
    single Mongo call. Safe to call every stage without race conditions."""
    frag = heartbeat(step)
    frag.update(extra)
    try:
        await db.reports.update_one({"id": report_id}, {"$set": frag})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[watchdog] heartbeat write failed for {report_id}: {e}")


async def _mark_stalled(
    db,
    report_id: str,
    refund_cb: Optional[Callable[[str], Awaitable[None]]],
    requeue_cb: Optional[Callable[[str], Awaitable[None]]] = None,
) -> None:
    """Idempotently handle a stalled report: REQUEUE it once (pod restarts on
    production kill the background task — the video survives in R2, so a
    second attempt usually succeeds), then mark failed + refund if it stalls
    again. compareAndSwap-style guards keep every step race-free."""
    if requeue_cb is not None:
        claimed = await db.reports.find_one_and_update(
            {"id": report_id, "analysis_status": "analyzing",
             "$or": [{"analysis_requeues": {"$exists": False}},
                     {"analysis_requeues": {"$lt": 1}}]},
            {"$inc": {"analysis_requeues": 1},
             "$set": {"last_progress_at": _utcnow_iso(), "requeued_at": _utcnow_iso()}},
        )
        if claimed is not None:
            logger.warning(f"[watchdog] STALLED — requeuing analysis for {report_id} (attempt 2)")
            try:
                await requeue_cb(report_id)
                return
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[watchdog] requeue_cb failed for {report_id}: {e}")
    result = await db.reports.update_one(
        {"id": report_id, "analysis_status": "analyzing"},
        {"$set": {
            "analysis_status": "failed",
            "analysis_error": (
                "Analysis was interrupted (worker restarted mid-processing). "
                "Please try uploading again — your credit has been restored."
            ),
            "progress_step": 5,
            "stalled_at": _utcnow_iso(),
            "last_progress_at": _utcnow_iso(),
        }},
    )
    if result.modified_count == 0:
        # Someone else already flipped the status — nothing to do.
        return
    logger.error(f"[watchdog] STALLED REPORT DETECTED — marked failed: {report_id}")
    if refund_cb:
        try:
            await refund_cb(report_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[watchdog] refund_cb failed for {report_id}: {e}")


async def sweep_stalled_reports(
    db,
    refund_cb: Optional[Callable[[str], Awaitable[None]]] = None,
    requeue_cb: Optional[Callable[[str], Awaitable[None]]] = None,
) -> int:
    """Scan the `reports` collection for stalled entries and mark them failed.
    Returns the number of reports rescued. Safe to call any time — every step
    is idempotent (per-doc compareAndSwap on `status=analyzing`)."""
    now = datetime.now(timezone.utc)
    stall_cutoff = (now - timedelta(seconds=STALL_THRESHOLD_SECONDS)).isoformat()
    legacy_cutoff = (now - timedelta(seconds=LEGACY_ANALYZING_AGE_SECONDS)).isoformat()

    # A report is "stalled" if it's still analyzing AND either:
    #   (a) its heartbeat is older than STALL_THRESHOLD_SECONDS, OR
    #   (b) it has NO heartbeat at all and its `created_at` is older than the
    #       legacy timeout (i.e. it belongs to a pre-S131 build that never
    #       recorded heartbeats — 15 min is our hard timeout there).
    query = {
        "analysis_status": "analyzing",
        "$or": [
            {"last_progress_at": {"$lt": stall_cutoff}},
            {
                "last_progress_at": {"$in": [None, ""]},
                "created_at": {"$lt": legacy_cutoff},
            },
            {
                "last_progress_at": {"$exists": False},
                "created_at": {"$lt": legacy_cutoff},
            },
        ],
    }
    rescued = 0
    async for doc in db.reports.find(query, {"id": 1, "last_progress_at": 1, "created_at": 1}):
        rid = doc.get("id")
        if not rid:
            continue
        await _mark_stalled(db, rid, refund_cb, requeue_cb)
        rescued += 1
    if rescued:
        logger.warning(f"[watchdog] sweep completed — {rescued} stalled report(s) rescued")
    return rescued


async def _watchdog_loop(
    db,
    refund_cb: Optional[Callable[[str], Awaitable[None]]],
    interval: int,
    requeue_cb: Optional[Callable[[str], Awaitable[None]]] = None,
) -> None:
    """Never-ending sweep loop. Cancellation-safe — a `CancelledError`
    propagates out cleanly on shutdown."""
    logger.info(f"[watchdog] loop started (interval={interval}s, stall_threshold={STALL_THRESHOLD_SECONDS}s)")
    while True:
        try:
            await asyncio.sleep(interval)
            await sweep_stalled_reports(db, refund_cb, requeue_cb)
        except asyncio.CancelledError:
            logger.info("[watchdog] loop cancelled — shutting down cleanly")
            raise
        except Exception as e:  # noqa: BLE001
            # Never let a single sweep failure kill the loop.
            logger.exception(f"[watchdog] sweep raised (loop continues): {e}")


def start_watchdog(
    db,
    refund_cb: Optional[Callable[[str], Awaitable[None]]] = None,
    interval: int = WATCHDOG_INTERVAL_SECONDS,
    requeue_cb: Optional[Callable[[str], Awaitable[None]]] = None,
) -> asyncio.Task:
    """Kick off the periodic watchdog and return its Task. The FastAPI startup
    hook should await one initial `sweep_stalled_reports(...)` first, THEN
    call this to keep the loop running."""
    return asyncio.create_task(
        _watchdog_loop(db, refund_cb, interval, requeue_cb),
        name="analysis_watchdog_loop",
    )
