"""
FIX 00B — Finalization / READY contract regression tests.

Lifecycle: generating → verifying → finalizing → ready.
READY must never lie: it is written once, by _finalize_full_report, at the
true end of the pipeline. Deterministic — NO live LLM, no video decode, no
real Mongo writes (FakeDB), no test/integration agents.

Run: cd /app/backend && python -m pytest tests/test_fix00b_ready_contract.py -v
"""
import asyncio
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import server


# ── fakes ─────────────────────────────────────────────────────────────────
class FakeReports:
    def __init__(self, doc=None, fail_on=None):
        self.doc = doc
        self.updates = []
        self.calls = []
        self.fail_on = fail_on or (lambda u: False)
        self.last_find_query = None

    async def find_one(self, q, *a, **k):
        return dict(self.doc) if self.doc else None

    async def update_one(self, q, u, **k):
        if self.fail_on(u):
            raise RuntimeError("simulated required-finalization DB failure")
        self.updates.append((q, u))
        s = u.get("$set") or {}
        self.calls.append(("db_set", sorted(s.keys()), s.get("full_report_status")))
        if self.doc is not None:
            self.doc.update(s)
        return SimpleNamespace(modified_count=1)

    def find(self, q, *a, **k):
        self.last_find_query = q

        async def _gen():
            if False:
                yield None
        return _gen()


def _ready_writes(fake):
    return [u for _, u in fake.updates
            if (u.get("$set") or {}).get("full_report_status") == "ready"]


def _wire(monkeypatch, fake, persist_raises=False):
    monkeypatch.setattr(server, "db", SimpleNamespace(reports=fake))

    async def fake_persist(report_id, video_path):
        fake.calls.append(("persist_frames", report_id))
        if persist_raises:
            raise RuntimeError("simulated frame persist failure")
        return {"checked": 3, "hard_rejected": 0}

    async def fake_email(report_id):
        fake.calls.append(("email", report_id))

    async def fake_notify(report_id, kind):
        fake.calls.append(("notify", kind))

    monkeypatch.setattr(server, "_persist_video_frames", fake_persist)
    monkeypatch.setattr(server, "_send_report_ready_email", fake_email)
    monkeypatch.setattr(server, "_notify_dashboard_report", fake_notify)


def _tmp_video():
    f = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    f.write(b"x")
    f.close()
    return Path(f.name)


# ── TEST 1: full_report exists, moved to verification → NOT ready ─────────
def test_1_resume_verifying_is_not_instant_ready(monkeypatch):
    doc = {"id": "r1", "full_report": {"scores": {}}, "full_report_status": "verifying"}
    fake = FakeReports(doc)
    _wire(monkeypatch, fake)
    vid = _tmp_video()
    finalized = []

    async def fake_finalize(report_id, file_path, persist_frames=True):
        finalized.append((report_id, persist_frames))

    async def fake_local(report_id):
        return vid

    monkeypatch.setattr(server, "_finalize_full_report", fake_finalize)
    monkeypatch.setattr(server, "_ensure_report_video_local", fake_local)
    try:
        asyncio.run(server.generate_full_report_task("r1"))
        assert finalized == [("r1", True)], "resume must run finalization, not skip it"
        assert not _ready_writes(fake), "the resume path must never write ready directly"
    finally:
        vid.unlink(missing_ok=True)


# ── TEST 2: verification done, finalization still running → NOT ready ─────
def test_2_resume_finalizing_is_not_instant_ready(monkeypatch):
    doc = {"id": "r2", "full_report": {"scores": {}}, "full_report_status": "finalizing"}
    fake = FakeReports(doc)
    _wire(monkeypatch, fake)
    vid = _tmp_video()
    finalized = []

    async def fake_finalize(report_id, file_path, persist_frames=True):
        finalized.append(report_id)

    async def fake_local(report_id):
        return vid

    monkeypatch.setattr(server, "_finalize_full_report", fake_finalize)
    monkeypatch.setattr(server, "_ensure_report_video_local", fake_local)
    try:
        asyncio.run(server.generate_full_report_task("r2"))
        assert finalized == ["r2"]
        assert not _ready_writes(fake)
    finally:
        vid.unlink(missing_ok=True)


# ── legacy: complete doc without lifecycle states stays instant-ready ─────
def test_legacy_complete_doc_sets_ready_without_finalize(monkeypatch):
    doc = {"id": "r3", "full_report": {"scores": {}}}  # no status — pre-lifecycle
    fake = FakeReports(doc)
    _wire(monkeypatch, fake)
    called = []

    async def fake_finalize(*a, **k):
        called.append(1)

    monkeypatch.setattr(server, "_finalize_full_report", fake_finalize)
    asyncio.run(server.generate_full_report_task("r3"))
    assert len(_ready_writes(fake)) == 1
    assert not called, "legacy complete docs must not re-run finalization"


# ── TEST 3 + 4 + 9: ready only after ALL required finalization, only once ─
def test_3_4_9_ready_written_once_after_finalization(monkeypatch):
    doc = {"id": "r4", "is_paid": True, "full_report": {"scores": {}},
           "full_report_status": "finalizing", "paid_at": None}
    fake = FakeReports(doc)
    _wire(monkeypatch, fake)
    vid = _tmp_video()
    try:
        asyncio.run(server._finalize_full_report("r4", vid, persist_frames=True))
        ready = _ready_writes(fake)
        assert len(ready) == 1, "ready must be written exactly once"
        order = [c[0] if c[0] != "db_set" else (c[2] or "set") for c in fake.calls]
        i_frames = order.index("persist_frames")
        i_ready = order.index("ready")
        assert i_frames < i_ready, "frames/clips must complete before ready"
        agent_sets = [i for i, c in enumerate(fake.calls)
                      if c[0] == "db_set" and "agent_review" in c[1]]
        assert agent_sets and agent_sets[0] < i_ready, "agent review queued before ready"
        assert order.index("email") > i_ready and order.index("notify") > i_ready, \
            "notifications are optional and run after the authoritative ready"
        assert fake.doc["full_report_status"] == "ready"
    finally:
        vid.unlink(missing_ok=True)


# ── optional asset failure: existing safe-omission behaviour preserved ────
def test_optional_frame_failure_does_not_block_ready(monkeypatch):
    doc = {"id": "r5", "full_report": {"scores": {}}, "full_report_status": "finalizing"}
    fake = FakeReports(doc)
    _wire(monkeypatch, fake, persist_raises=True)
    vid = _tmp_video()
    try:
        asyncio.run(server._finalize_full_report("r5", vid, persist_frames=True))
        assert len(_ready_writes(fake)) == 1, \
            "frame persist keeps its existing fail-open/self-heal contract"
    finally:
        vid.unlink(missing_ok=True)


# ── TEST 8: required finalization failure → ready is NEVER written ────────
def test_8_required_failure_never_writes_ready(monkeypatch):
    doc = {"id": "r6", "full_report": {"scores": {}}, "full_report_status": "finalizing"}
    fail_on = lambda u: (u.get("$set") or {}).get("full_report_status") == "ready"
    fake = FakeReports(doc, fail_on=fail_on)
    _wire(monkeypatch, fake)
    vid = _tmp_video()
    try:
        with pytest.raises(RuntimeError):
            asyncio.run(server._finalize_full_report("r6", vid, persist_frames=True))
        assert not _ready_writes(fake)
        assert fake.doc["full_report_status"] == "finalizing", \
            "failure must propagate to the caller's failure contract, not fake ready"
        assert not any(c[0] == "email" for c in fake.calls), \
            "no ready-notification when ready was never reached"
    finally:
        vid.unlink(missing_ok=True)


# ── watchdog rescue covers the new in-flight states ───────────────────────
def test_watchdog_query_covers_new_states(monkeypatch):
    fake = FakeReports(None)
    monkeypatch.setattr(server, "db", SimpleNamespace(reports=fake))
    asyncio.run(server._sweep_stuck_full_reports(include_fresh=True))
    q = fake.last_find_query
    assert set(q["full_report_status"]["$in"]) == {"generating", "verifying", "finalizing"}


# ── TEST 9 supplement: no early ready write inside the pipeline body ─────
def test_9_supplement_single_ready_write_site():
    src = (BACKEND / "server.py").read_text()
    task = src.split("async def generate_full_report_task(")[1].split("\nasync def ")[0]
    assert '"full_report_status": "ready"' not in task.split('if st != "ready":')[1].split("return")[1], \
        "pipeline body must not write ready directly"
    # the full_report persistence point stores finalizing, not ready
    persist_block = task.split('"full_report": full,')[1][:400]
    assert '"full_report_status": "finalizing"' in persist_block
    finalize = src.split("async def _finalize_full_report(")[1].split("\nasync def ")[0]
    assert finalize.count('"full_report_status": "ready"') == 1


# ── TESTS 5, 6, 7: frontend completion helper behaviour ──────────────────
def test_5_6_7_frontend_completion_helper():
    script = (
        "import('/app/frontend/src/lib/reportReady.mjs').then(m => {"
        "const f = m.isFullReportReady;"
        "console.log(JSON.stringify({"
        "verifying: f({has_full_report: true, full_report_status: 'verifying'}),"
        "finalizing: f({has_full_report: true, full_report_status: 'finalizing'}),"
        "generating: f({full_report_status: 'generating'}),"
        "failed: f({has_full_report: true, full_report_status: 'failed'}),"
        "ready: f({full_report_status: 'ready'}),"
        "readyNoBody: f({full_report_status: 'ready', has_full_report: false}),"
        "legacyStatus: f({has_full_report: true}),"
        "legacyDoc: f({full_report: {scores: {}}}),"
        "empty: f({}), nul: f(null)"
        "}));"
        "}).catch(e=>{console.error(e);process.exit(1);});"
    )
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout.strip())
    assert r["verifying"] is False, "TEST 5: has_full_report + verifying → keep polling"
    assert r["finalizing"] is False, "TEST 6: has_full_report + finalizing → keep polling"
    assert r["generating"] is False and r["failed"] is False
    assert r["ready"] is True and r["readyNoBody"] is True, "TEST 7: ready → stop polling"
    assert r["legacyStatus"] is True and r["legacyDoc"] is True, "legacy docs stay openable"
    assert r["empty"] is False and r["nul"] is False


def test_frontend_wiring_uses_the_helper():
    rp = Path("/app/frontend/src/pages/ReportPage.jsx").read_text()
    assert "if (isFullReportReady(data)) return data;" in rp, "polling gate"
    assert "unlocked && full_report && isFullReportReady(report)" in rp, "render gate"
    assert "!isFullReportReady(report)" in rp, "auto-generate/poll trigger gate"
    assert "data?.has_full_report) return data" not in rp, \
        "has_full_report alone must no longer stop polling"
