"""Regression tests for Session 131 — analysis pipeline watchdog.

Ensures the recurring "stuck at step 4" bug can never silently re-appear:
  - Heartbeats are written at every stage transition
  - The sweeper reliably detects orphaned `analyzing` reports
  - The compareAndSwap prevents the sweeper from racing a legitimately-
    completing task and clobbering `ready` state

Run with:
    cd /app/backend && python -m pytest tests/test_analysis_watchdog.py -v
"""
from datetime import datetime, timedelta, timezone

import pytest

from analysis_watchdog import (
    STALL_THRESHOLD_SECONDS,
    LEGACY_ANALYZING_AGE_SECONDS,
    _mark_stalled,
    heartbeat,
    stamp_progress,
    sweep_stalled_reports,
)


class FakeUpdateResult:
    def __init__(self, matched=1, modified=1):
        self.matched_count = matched
        self.modified_count = modified


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class FakeReportsCollection:
    def __init__(self, docs):
        self.docs = docs
        self.update_calls = []

    def find(self, query, projection=None):
        # naive matcher — only supports the exact query shape our sweeper uses
        matched = []
        stall_cutoff = query.get("$or", [{}])[0].get("last_progress_at", {}).get("$lt")
        legacy_cutoff = None
        for sub in query.get("$or", []):
            if "created_at" in sub:
                legacy_cutoff = sub["created_at"].get("$lt")
                break
        for d in self.docs:
            if d.get("analysis_status") != "analyzing":
                continue
            lp = d.get("last_progress_at")
            ca = d.get("created_at")
            if lp and stall_cutoff and lp < stall_cutoff:
                matched.append(d)
            elif not lp and ca and legacy_cutoff and ca < legacy_cutoff:
                matched.append(d)
        return FakeCursor(matched)

    async def update_one(self, filter_q, update):
        self.update_calls.append((filter_q, update))
        # Simulate compareAndSwap on analysis_status
        want_status = filter_q.get("analysis_status")
        for d in self.docs:
            if d.get("id") == filter_q.get("id"):
                if want_status and d.get("analysis_status") != want_status:
                    return FakeUpdateResult(matched=0, modified=0)
                d.update(update.get("$set", {}))
                return FakeUpdateResult(matched=1, modified=1)
        return FakeUpdateResult(matched=0, modified=0)


class FakeDb:
    def __init__(self, docs):
        self.reports = FakeReportsCollection(docs)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _now():
    return datetime.now(timezone.utc)


# ─── Tests ────────────────────────────────────────────────────────────────

def test_heartbeat_writes_step_and_timestamp():
    frag = heartbeat(step=4)
    assert frag["progress_step"] == 4
    assert "last_progress_at" in frag
    # ISO timestamp round-trips
    parsed = datetime.fromisoformat(frag["last_progress_at"])
    assert (datetime.now(timezone.utc) - parsed).total_seconds() < 2


def test_heartbeat_without_step_only_updates_timestamp():
    frag = heartbeat()
    assert "progress_step" not in frag
    assert "last_progress_at" in frag


@pytest.mark.asyncio
async def test_sweeper_rescues_stalled_heartbeat_reports():
    old = _iso(_now() - timedelta(seconds=STALL_THRESHOLD_SECONDS + 60))
    docs = [
        {"id": "r-stalled", "analysis_status": "analyzing", "last_progress_at": old, "created_at": old},
        {"id": "r-healthy", "analysis_status": "analyzing", "last_progress_at": _iso(_now())},
        {"id": "r-ready",   "analysis_status": "ready", "last_progress_at": old},
    ]
    db = FakeDb(docs)
    refunds = []

    async def fake_refund(rid):
        refunds.append(rid)

    rescued = await sweep_stalled_reports(db, refund_cb=fake_refund)
    assert rescued == 1
    stalled = next(d for d in docs if d["id"] == "r-stalled")
    assert stalled["analysis_status"] == "failed"
    assert "worker restarted" in stalled["analysis_error"].lower()
    assert stalled["progress_step"] == 5
    healthy = next(d for d in docs if d["id"] == "r-healthy")
    assert healthy["analysis_status"] == "analyzing"  # untouched
    assert refunds == ["r-stalled"]


@pytest.mark.asyncio
async def test_sweeper_rescues_legacy_reports_without_heartbeat():
    """Pre-S131 reports have no `last_progress_at`. If they've been analyzing
    for > LEGACY_ANALYZING_AGE_SECONDS they must be swept."""
    legacy_old = _iso(_now() - timedelta(seconds=LEGACY_ANALYZING_AGE_SECONDS + 300))
    fresh = _iso(_now() - timedelta(seconds=60))
    docs = [
        {"id": "r-legacy-stalled", "analysis_status": "analyzing", "created_at": legacy_old},
        {"id": "r-legacy-fresh",   "analysis_status": "analyzing", "created_at": fresh},
    ]
    db = FakeDb(docs)
    rescued = await sweep_stalled_reports(db, refund_cb=None)
    assert rescued == 1
    assert docs[0]["analysis_status"] == "failed"
    assert docs[1]["analysis_status"] == "analyzing"  # too fresh


@pytest.mark.asyncio
async def test_mark_stalled_is_compare_and_swap():
    """If the report has ALREADY transitioned to `ready`, _mark_stalled must
    NOT flip it back to `failed`. This prevents race conditions where the
    watchdog fires the same tick a legitimately-completing task writes ready."""
    docs = [{"id": "r-just-completed", "analysis_status": "ready"}]
    db = FakeDb(docs)
    await _mark_stalled(db, "r-just-completed", refund_cb=None)
    assert docs[0]["analysis_status"] == "ready"


@pytest.mark.asyncio
async def test_stamp_progress_merges_extra_fields():
    docs = [{"id": "r-1", "analysis_status": "analyzing"}]
    db = FakeDb(docs)
    await stamp_progress(db, "r-1", step=3, video_filename="foo.mp4")
    assert docs[0]["progress_step"] == 3
    assert docs[0]["video_filename"] == "foo.mp4"
    assert "last_progress_at" in docs[0]
