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

BOX = {"x": 0.4, "y": 0.4, "w": 0.05, "h": 0.12}


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


def _wire(monkeypatch, fake, persist_raises=False, persist_stats=None):
    monkeypatch.setattr(server, "db", SimpleNamespace(reports=fake))

    async def fake_persist(report_id, video_path):
        fake.calls.append(("persist_frames", report_id))
        if persist_raises:
            raise RuntimeError("simulated frame persist failure")
        return dict(persist_stats) if persist_stats else {"checked": 3, "hard_rejected": 0}

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


# ── A + B: TOP-LEVEL persist failure → ready NEVER written, failed wins ──
def test_A_B_toplevel_persist_failure_never_ready(monkeypatch):
    """Resume path with the REAL _finalize_full_report: a top-level
    _persist_video_frames exception must propagate into the existing failure
    contract — the report ends failed, ready is never written."""
    doc = {"id": "r5", "full_report": {"scores": {}}, "full_report_status": "finalizing"}
    fake = FakeReports(doc)
    _wire(monkeypatch, fake, persist_raises=True)
    vid = _tmp_video()

    async def fake_local(report_id):
        return vid

    monkeypatch.setattr(server, "_ensure_report_video_local", fake_local)
    try:
        asyncio.run(server.generate_full_report_task("r5"))
        assert not _ready_writes(fake), "top-level persist failure must never become ready"
        assert fake.doc["full_report_status"] == "failed"
        assert not any(c[0] == "email" for c in fake.calls)
    finally:
        vid.unlink(missing_ok=True)


def test_A_supplement_normal_path_persist_not_swallowed():
    src = (BACKEND / "server.py").read_text()
    task = src.split("async def generate_full_report_task(")[1].split("\nasync def ")[0]
    assert "identity_stats = None" not in task, \
        "normal path must not swallow a top-level persist failure"
    assert "identity_stats = await _persist_video_frames(" in task
    finalize = src.split("async def _finalize_full_report(")[1].split("\nasync def ")[0]
    assert "except Exception" not in finalize.split("agent_review")[0], \
        "resume-path persist must not be wrapped in a swallow"


# ── C: corrective pass — replacement report requires final persistence ──
def test_C_retry_persist_failure_propagates():
    src = (BACKEND / "server.py").read_text()
    helper = src.split("async def _run_identity_corrective_pass(")[1].split("\nasync def ")[0]
    before_persist, after_persist = helper.split("persisted = True")[1:3] if False else (
        helper.split("persisted = True")[0], helper.split("persisted = True")[1])
    assert '"full_report": retry' in before_persist, \
        "flag must be set immediately after the replacement report is persisted"
    assert "stats2 = await _persist_video_frames(" in after_persist.split("except Exception")[0]
    handler = after_persist.split("except Exception:")[1]
    assert "if persisted:" in handler and "raise" in handler.split("logger.exception")[0], \
        "a live replacement report must not be declared ready when its evidence persistence fails"


# ── D: failed + full_report → never instant-ready, resume tail instead ───
def test_D_failed_plus_full_report_not_instant_ready(monkeypatch):
    doc = {"id": "r7", "full_report": {"scores": {}}, "full_report_status": "failed"}
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
        asyncio.run(server.generate_full_report_task("r7"))
        assert finalized == [("r7", True)], "failed+body must resume the finalization tail"
        assert not _ready_writes(fake), "failed must NEVER be promoted directly to ready"
        assert fake.doc["full_report_status"] == "finalizing", \
            "recovery must be visible as an in-flight state"
    finally:
        vid.unlink(missing_ok=True)


# ── E: failed retry — no unnecessary full-report Gemini REGENERATION ─────
def test_E_failed_retry_no_full_gemini_regeneration(monkeypatch):
    """Proves the recovery path never re-runs the full-report Gemini
    generation. NOTE: this does not claim zero model work overall —
    _persist_video_frames contains its own identity/proof verification seams
    (mocked here)."""
    doc = {"id": "r8", "is_paid": True, "paid_at": None,
           "full_report": {"scores": {}}, "full_report_status": "failed"}
    fake = FakeReports(doc)
    _wire(monkeypatch, fake)
    vid = _tmp_video()
    llm_calls = []

    async def forbidden_gemini(*a, **k):
        llm_calls.append(1)
        raise AssertionError("full Gemini generation must NOT run for a finalization retry")

    async def fake_local(report_id):
        return vid

    monkeypatch.setattr(server, "call_gemini_with_video", forbidden_gemini)
    monkeypatch.setattr(server, "_ensure_report_video_local", fake_local)
    try:
        asyncio.run(server.generate_full_report_task("r8"))
        assert llm_calls == [], "credit control: no full-report Gemini regeneration"
        assert len(_ready_writes(fake)) == 1, "finalization-only recovery reaches ready"
        assert fake.doc["full_report_status"] == "ready"
    finally:
        vid.unlink(missing_ok=True)


# ── F: explicit awaiting_confirmation + full_report → never promoted ─────
def test_F_awaiting_confirmation_never_promoted(monkeypatch):
    doc = {"id": "r9", "full_report": {"scores": {}},
           "full_report_status": "awaiting_confirmation"}
    fake = FakeReports(doc)
    _wire(monkeypatch, fake)
    called = []

    async def fake_finalize(*a, **k):
        called.append(1)

    monkeypatch.setattr(server, "_finalize_full_report", fake_finalize)
    asyncio.run(server.generate_full_report_task("r9"))
    assert not _ready_writes(fake) and not called
    assert fake.doc["full_report_status"] == "awaiting_confirmation"


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
    # exactly ONE direct ready write in the task body — the TRUE-legacy fallback
    assert task.count('"full_report_status": "ready"') == 1
    legacy_branch = task.split("if not st:")[1].split("return")[0]
    assert '"full_report_status": "ready"' in legacy_branch, \
        "the only direct ready write must be the no-status legacy fallback"
    # the full_report persistence point stores finalizing, not ready
    persist_block = task.split('"full_report": full,')[1][:500]
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


# ══ RECOVERY IDENTITY-GATE PARITY (final review correction) ═══════════════

def _fake_local(vid):
    async def f(report_id):
        return vid
    return f


def test_parity_threshold_helper_unchanged():
    f = server._identity_gate_required
    assert f({"checked": 4, "hard_rejected": 3}) is True
    assert f({"checked": 4, "hard_rejected": 2}) is True   # exactly 0.5 boundary
    assert f({"checked": 4, "hard_rejected": 1}) is False
    assert f({"checked": 1, "hard_rejected": 1}) is False  # checked >= 2 guard
    assert f({"checked": 0, "hard_rejected": 0}) is False
    assert f(None) is False
    # BOTH the normal pipeline and the shared corrective pass use this definition
    src = (BACKEND / "server.py").read_text()
    task = src.split("async def generate_full_report_task(")[1].split("\nasync def ")[0]
    assert "if _identity_gate_required(identity_stats):" in task
    helper = src.split("async def _run_identity_corrective_pass(")[1].split("\nasync def ")[0]
    assert "if _identity_gate_required(stats2):" in helper
    finalize = src.split("async def _finalize_full_report(")[1].split("\nasync def ")[0]
    assert "if _identity_gate_required(stats):" in finalize


def test_R1_recovery_clean_stats_reaches_ready(monkeypatch):
    doc = {"id": "p1", "full_report": {"scores": {}}, "full_report_status": "failed"}
    fake = FakeReports(doc)
    _wire(monkeypatch, fake, persist_stats={"checked": 4, "hard_rejected": 0})
    vid = _tmp_video()
    monkeypatch.setattr(server, "_ensure_report_video_local", _fake_local(vid))
    try:
        asyncio.run(server.generate_full_report_task("p1"))
        assert len(_ready_writes(fake)) == 1
        assert fake.doc["full_report_status"] == "ready"
        assert fake.doc.get("identity_gate_done") is True, "checkpoint persisted"
        assert not fake.doc.get("identity_flagged") and not fake.doc.get("identity_regen_required")
    finally:
        vid.unlink(missing_ok=True)


def test_R2_recovery_bad_stats_without_correction_blocks_ready(monkeypatch):
    doc = {"id": "p2", "full_report": {"scores": {}}, "full_report_status": "failed"}
    fake = FakeReports(doc)
    _wire(monkeypatch, fake, persist_stats={"checked": 4, "hard_rejected": 3})
    vid = _tmp_video()
    monkeypatch.setattr(server, "_ensure_report_video_local", _fake_local(vid))
    try:
        asyncio.run(server.generate_full_report_task("p2"))
        assert not _ready_writes(fake), \
            "recovery must NOT bypass the corrective identity requirement"
        assert fake.doc["full_report_status"] == "failed"
        assert fake.doc.get("identity_regen_required") is True
        assert not fake.doc.get("identity_gate_done")
        assert not any(c[0] == "email" for c in fake.calls)
    finally:
        vid.unlink(missing_ok=True)


def _regen_doc(rid, retry_done=False):
    d = {"id": rid, "full_report_status": "generating", "identity_regen_required": True,
         "full_report": {"scores": {}, "video_comments": [
             {"timestamp": "00:36", "identity_hard_reject": True}]},
         "player_details": {"player_name": "Test Player", "age": 12},
         "content_gate": {"content_type": "match"},
         "anchors": [{"i": 1, "t": 1.0, "box": dict(BOX)}],
         "player_track": {"points": [], "t_off": 0.0},
         "anchor_time_offset": 0.0,
         "audio_events_full": [{"t": 3.0, "peak_db": -8.0, "kind": "cheer"}]}
    if retry_done:
        d["identity_retry_done"] = True
    return d


def _wire_corrective(monkeypatch, fake, vid, gemini_raises=False):
    """Mocks the corrective seams; records every Gemini session_id."""
    sessions = []

    async def fake_gemini(session_id=None, **k):
        sessions.append(session_id)
        if gemini_raises:
            raise RuntimeError("simulated corrective Gemini failure")
        return {"scores": {}, "video_comments": [], "_replacement": True}

    async def fake_cross_verify(*a, **k):
        fake.calls.append(("cross_verify",))

    async def fake_local(report_id):
        return vid

    monkeypatch.setattr(server, "call_gemini_with_video", fake_gemini)
    monkeypatch.setattr(server, "scrub_hedging", lambda r: r)
    monkeypatch.setattr(server, "_filter_low_identity_evidence", lambda r, rid: r)
    monkeypatch.setattr(server, "_apply_tracking_verification", lambda *a, **k: None)
    monkeypatch.setattr(server, "_cross_verify_full_report", fake_cross_verify)
    monkeypatch.setattr(server, "_ensure_report_video_local", fake_local)
    return sessions


# ── CORRECTIVE-ONLY RECOVERY (final credit correction) ────────────────────

def test_CR1_CR2_regen_recovery_uses_only_the_corrective_call(monkeypatch):
    """TEST 1: zero standard full-{id} calls. TEST 2: exactly one
    full-retry-{id} call."""
    doc = _regen_doc("q1")
    fake = FakeReports(doc)
    _wire(monkeypatch, fake, persist_stats={"checked": 4, "hard_rejected": 0})
    vid = _tmp_video()
    sessions = _wire_corrective(monkeypatch, fake, vid)
    try:
        asyncio.run(server.generate_full_report_task("q1"))
        assert "full-q1" not in sessions, "standard full-report generation must NOT run"
        assert sessions.count("full-retry-q1") == 1, "exactly one corrective call"
        assert sessions == ["full-retry-q1"]
    finally:
        vid.unlink(missing_ok=True)


def test_CR3_corrective_pass_success_reaches_ready_once(monkeypatch):
    doc = _regen_doc("q2")
    fake = FakeReports(doc)
    _wire(monkeypatch, fake, persist_stats={"checked": 4, "hard_rejected": 0})
    vid = _tmp_video()
    _wire_corrective(monkeypatch, fake, vid)
    try:
        asyncio.run(server.generate_full_report_task("q2"))
        assert fake.doc["full_report"].get("_replacement") is True, \
            "replacement full_report persisted"
        assert fake.doc.get("identity_gate_done") is True
        assert fake.doc.get("identity_regen_required") is False
        assert len(_ready_writes(fake)) == 1
        assert fake.doc["full_report_status"] == "ready"
        assert fake.doc.get("identity_retry_done") is True
    finally:
        vid.unlink(missing_ok=True)


def test_CR4_corrective_still_failing_flags_before_ready(monkeypatch):
    doc = _regen_doc("q3")
    fake = FakeReports(doc)
    _wire(monkeypatch, fake, persist_stats={"checked": 4, "hard_rejected": 3})
    vid = _tmp_video()
    _wire_corrective(monkeypatch, fake, vid)
    try:
        asyncio.run(server.generate_full_report_task("q3"))
        assert fake.doc.get("identity_flagged") is True
        flag_idx = next(i for i, (_, u) in enumerate(fake.updates)
                        if (u.get("$set") or {}).get("identity_flagged") is True)
        ready_idx = next(i for i, (_, u) in enumerate(fake.updates)
                         if (u.get("$set") or {}).get("full_report_status") == "ready")
        assert flag_idx < ready_idx, "identity_flagged must be set BEFORE ready"
        assert len(_ready_writes(fake)) == 1
    finally:
        vid.unlink(missing_ok=True)


def test_CR5_corrective_gemini_failure_keeps_requirement(monkeypatch):
    doc = _regen_doc("q4")
    fake = FakeReports(doc)
    _wire(monkeypatch, fake, persist_stats={"checked": 4, "hard_rejected": 0})
    vid = _tmp_video()
    _wire_corrective(monkeypatch, fake, vid, gemini_raises=True)
    try:
        asyncio.run(server.generate_full_report_task("q4"))
        assert not _ready_writes(fake)
        assert fake.doc["full_report_status"] == "failed"
        assert fake.doc.get("identity_regen_required") is True, \
            "transient corrective failure must not lose the recovery requirement"
        assert not fake.doc.get("identity_corrective_persisted")
        assert fake.doc.get("identity_retry_done") is False, \
            "pre-persist failure must re-arm the corrective marker"
    finally:
        vid.unlink(missing_ok=True)


def test_CR5b_corrective_persistence_failure_keeps_requirement(monkeypatch):
    doc = _regen_doc("q5")
    fake = FakeReports(doc)
    _wire(monkeypatch, fake, persist_raises=True)  # post-replacement persist fails
    vid = _tmp_video()
    _wire_corrective(monkeypatch, fake, vid)
    try:
        asyncio.run(server.generate_full_report_task("q5"))
        assert not _ready_writes(fake)
        assert fake.doc["full_report_status"] == "failed"
        assert fake.doc.get("identity_regen_required") is True
        assert fake.doc["full_report"].get("_replacement") is True, \
            "replacement was persisted — its evidence persistence failure must block ready"
    finally:
        vid.unlink(missing_ok=True)


def test_CR6_regen_with_retry_done_reverifies_without_gemini(monkeypatch):
    """After a post-persist failure, the next recovery must not repeat the
    one-shot corrective Gemini call: it re-evaluates evidence via the
    finalization gate (identity_retry_done=True → flag semantics)."""
    doc = _regen_doc("q6", retry_done=True)
    doc["identity_corrective_persisted"] = True  # post-persist failure state
    fake = FakeReports(doc)
    _wire(monkeypatch, fake, persist_stats={"checked": 4, "hard_rejected": 3})
    vid = _tmp_video()
    sessions = _wire_corrective(monkeypatch, fake, vid)
    try:
        asyncio.run(server.generate_full_report_task("q6"))
        assert sessions == [], "no Gemini call of any kind"
        assert fake.doc.get("identity_flagged") is True
        assert len(_ready_writes(fake)) == 1
        assert fake.doc.get("identity_regen_required") is False
    finally:
        vid.unlink(missing_ok=True)


def test_CR7_normal_pipeline_uses_same_corrective_helper():
    src = (BACKEND / "server.py").read_text()
    # ONE corrective algorithm: the full-retry session string exists only in the helper
    assert src.count('session_id=f"full-retry-{report_id}"') == 1
    helper = src.split("async def _run_identity_corrective_pass(")[1].split("\nasync def ")[0]
    assert 'session_id=f"full-retry-{report_id}"' in helper
    # exactly two call sites: normal pipeline identity gate + corrective-only recovery
    assert src.count("await _run_identity_corrective_pass(") == 2
    task = src.split("async def generate_full_report_task(")[1].split("\nasync def ")[0]
    assert "await _run_identity_corrective_pass(" in task
    recovery = src.split("async def _corrective_only_recovery(")[1].split("\nasync def ")[0]
    assert "await _run_identity_corrective_pass(" in recovery
    # identity_retry_done semantics preserved inside the shared helper
    assert '"identity_retry_done": True' in helper and "identity_retry_done" in helper


def test_R3_recovery_after_correction_flags_and_reaches_ready(monkeypatch):
    doc = {"id": "p4", "full_report": {"scores": {}}, "full_report_status": "failed",
           "identity_retry_done": True}
    fake = FakeReports(doc)
    _wire(monkeypatch, fake, persist_stats={"checked": 4, "hard_rejected": 3})
    vid = _tmp_video()
    monkeypatch.setattr(server, "_ensure_report_video_local", _fake_local(vid))
    try:
        asyncio.run(server.generate_full_report_task("p4"))
        assert fake.doc.get("identity_flagged") is True, \
            "existing identity_flagged semantics preserved before ready"
        assert len(_ready_writes(fake)) == 1
        assert fake.doc["full_report_status"] == "ready"
    finally:
        vid.unlink(missing_ok=True)


def test_R4_checkpoint_skips_expensive_reverification(monkeypatch):
    doc = {"id": "p5", "full_report": {"scores": {}}, "full_report_status": "finalizing",
           "identity_gate_done": True}
    fake = FakeReports(doc)
    _wire(monkeypatch, fake)
    vid = _tmp_video()
    monkeypatch.setattr(server, "_ensure_report_video_local", _fake_local(vid))
    try:
        asyncio.run(server.generate_full_report_task("p5"))
        assert not any(c[0] == "persist_frames" for c in fake.calls), \
            "completed identity gate must not be repeated"
        assert len(_ready_writes(fake)) == 1
        assert fake.doc["full_report_status"] == "ready"
    finally:
        vid.unlink(missing_ok=True)


def test_R5_helper_toplevel_persist_failure_propagates(monkeypatch):
    """Direct behavioural proof on the shared finalization seam (used by both
    the normal tail and recovery): a top-level persist failure raises out of
    _finalize_full_report — never swallowed into READY."""
    doc = {"id": "p6", "full_report": {"scores": {}}, "full_report_status": "finalizing"}
    fake = FakeReports(doc)
    _wire(monkeypatch, fake, persist_raises=True)
    vid = _tmp_video()
    try:
        with pytest.raises(RuntimeError):
            asyncio.run(server._finalize_full_report("p6", vid, persist_frames=True))
        assert not _ready_writes(fake)
    finally:
        vid.unlink(missing_ok=True)


# ══ TRANSIENT CORRECTIVE RECOVERY — two-invocation proofs ═════════════════

def _wire_two_phase(monkeypatch, fake, vid, behavior, sessions):
    """Corrective seams whose behaviour can change between task invocations."""
    monkeypatch.setattr(server, "db", SimpleNamespace(reports=fake))

    async def fake_gemini(session_id=None, **k):
        sessions.append(session_id)
        if behavior.get("gemini_raise"):
            raise RuntimeError("transient Gemini failure")
        return {"scores": {}, "video_comments": [], "_replacement": True}

    async def fake_persist(report_id, video_path):
        fake.calls.append(("persist_frames", report_id))
        if behavior.get("persist_raise"):
            raise RuntimeError("evidence persistence failure")
        return {"checked": 4, "hard_rejected": 0}

    async def _noop(*a, **k):
        return None

    async def fake_local(report_id):
        return vid

    monkeypatch.setattr(server, "call_gemini_with_video", fake_gemini)
    monkeypatch.setattr(server, "scrub_hedging", lambda r: r)
    monkeypatch.setattr(server, "_filter_low_identity_evidence", lambda r, rid: r)
    monkeypatch.setattr(server, "_apply_tracking_verification", lambda *a, **k: None)
    monkeypatch.setattr(server, "_cross_verify_full_report", _noop)
    monkeypatch.setattr(server, "_persist_video_frames", fake_persist)
    monkeypatch.setattr(server, "_send_report_ready_email", _noop)
    monkeypatch.setattr(server, "_notify_dashboard_report", _noop)
    monkeypatch.setattr(server, "_ensure_report_video_local", fake_local)


def test_TA_pre_persist_failure_then_retry_succeeds(monkeypatch):
    """TEST A — same report, two sequential invocations: a pre-persist Gemini
    failure must allow the REQUIRED corrective call to run again later."""
    doc = _regen_doc("t1")
    fake = FakeReports(doc)
    vid = _tmp_video()
    sessions = []
    behavior = {"gemini_raise": True}
    _wire_two_phase(monkeypatch, fake, vid, behavior, sessions)
    try:
        # FIRST invocation — corrective fails BEFORE replacement persistence
        asyncio.run(server.generate_full_report_task("t1"))
        assert fake.doc["full_report_status"] == "failed"
        assert not _ready_writes(fake)
        assert fake.doc.get("identity_regen_required") is True
        assert not fake.doc.get("identity_corrective_persisted"), \
            "corrective replacement must NOT be marked persisted"
        assert fake.doc.get("identity_retry_done") is False, "marker re-armed"
        assert sessions == ["full-retry-t1"]

        # SECOND invocation — corrective succeeds
        behavior["gemini_raise"] = False
        asyncio.run(server.generate_full_report_task("t1"))
        assert sessions == ["full-retry-t1", "full-retry-t1"], \
            "the required corrective call must actually run again"
        assert "full-t1" not in sessions, "standard full-{id} stays at ZERO"
        assert fake.doc["full_report"].get("_replacement") is True
        assert fake.doc.get("identity_corrective_persisted") is True
        assert fake.doc.get("identity_gate_done") is True
        assert fake.doc.get("identity_regen_required") is False
        assert len(_ready_writes(fake)) == 1
        assert fake.doc["full_report_status"] == "ready"
    finally:
        vid.unlink(missing_ok=True)


def test_TB_post_persist_failure_then_reverify_without_new_gemini(monkeypatch):
    """TEST B — replacement persisted, later evidence persistence fails: the
    next recovery must reverify/finalize the EXISTING replacement, never
    repeat the corrective Gemini call."""
    doc = _regen_doc("t2")
    fake = FakeReports(doc)
    vid = _tmp_video()
    sessions = []
    behavior = {"persist_raise": True}
    _wire_two_phase(monkeypatch, fake, vid, behavior, sessions)
    try:
        # FIRST invocation — corrective succeeds, evidence persistence raises
        asyncio.run(server.generate_full_report_task("t2"))
        assert fake.doc["full_report_status"] == "failed"
        assert not _ready_writes(fake)
        assert fake.doc.get("identity_corrective_persisted") is True, \
            "the replacement WAS produced — that fact must be remembered"
        assert fake.doc.get("identity_regen_required") is True
        assert fake.doc["full_report"].get("_replacement") is True
        assert sessions == ["full-retry-t2"]

        # SECOND invocation — no new Gemini; reverify + finalize the replacement
        behavior["persist_raise"] = False
        asyncio.run(server.generate_full_report_task("t2"))
        assert sessions == ["full-retry-t2"], "corrective Gemini count must NOT increase"
        assert any(c[0] == "persist_frames" for c in fake.calls), \
            "existing replacement reverified via evidence persistence"
        assert fake.doc.get("identity_regen_required") is False
        assert fake.doc.get("identity_gate_done") is True
        assert len(_ready_writes(fake)) == 1
        assert fake.doc["full_report_status"] == "ready"
    finally:
        vid.unlink(missing_ok=True)


# ══ NORMAL-PATH READY BLOCKER — full normal run, corrective fails ═════════

def test_TC_normal_run_corrective_failure_then_corrective_only_recovery(monkeypatch):
    """NORMAL FIRST RUN: initial full analysis succeeds, evidence stats hit the
    corrective threshold, corrective full-retry raises pre-persist → the run
    must FAIL (never ready). SECOND invocation: corrective-only recovery
    succeeds WITHOUT calling standard full-{id} again."""
    doc = {"id": "n1", "is_paid": True, "paid_at": None,
           "player_details": {"player_name": "Test Player", "age": 12},
           "content_gate": {"content_type": "match"},
           "anchors": [{"i": 1, "t": 1.0, "box": dict(BOX)}]}
    fake = FakeReports(doc)
    vid = _tmp_video()
    sessions = []
    behavior = {"retry_raise": True}

    monkeypatch.setattr(server, "db", SimpleNamespace(reports=fake))

    async def fake_gemini(session_id=None, **k):
        sessions.append(session_id)
        if session_id.startswith("full-retry-") and behavior["retry_raise"]:
            raise RuntimeError("transient corrective Gemini failure")
        return {"scores": {}, "video_comments": [],
                "_replacement": session_id.startswith("full-retry-")}

    async def fake_persist(report_id, video_path):
        fake.calls.append(("persist_frames", report_id))
        if fake.doc["full_report"].get("_replacement"):
            return {"checked": 4, "hard_rejected": 0}  # corrected report verifies
        return {"checked": 4, "hard_rejected": 3}      # first report fails the gate

    async def _noop(*a, **k):
        return None

    async def fake_local(report_id):
        return vid

    def fake_track(*a, **k):
        return {"points": [], "segments": [], "doubt_moments": [], "t_off": 0.0,
                "hz": 12.5, "seed_count": 1}

    monkeypatch.setattr(server, "call_gemini_with_video", fake_gemini)
    monkeypatch.setattr(server, "scrub_hedging", lambda r: r)
    monkeypatch.setattr(server, "_filter_low_identity_evidence", lambda r, rid: r)
    monkeypatch.setattr(server, "_apply_tracking_verification", lambda *a, **k: None)
    monkeypatch.setattr(server, "_cross_verify_full_report", _noop)
    monkeypatch.setattr(server, "_persist_video_frames", fake_persist)
    monkeypatch.setattr(server, "_send_report_ready_email", _noop)
    monkeypatch.setattr(server, "_notify_dashboard_report", _noop)
    monkeypatch.setattr(server, "_ensure_report_video_local", fake_local)
    monkeypatch.setattr(server, "track_player", fake_track)
    monkeypatch.setattr(server, "extract_audio_events", lambda *a, **k: [])
    monkeypatch.setattr(server, "compute_movement_map", lambda *a, **k: None)
    monkeypatch.setattr(server, "compute_speed_metrics", lambda *a, **k: {})
    monkeypatch.setattr(server, "_video_duration_seconds", lambda p: 60.0)
    monkeypatch.setattr(server, "_validate_grow_your_game", lambda *a, **k: 0)
    monkeypatch.setattr(server, "_validate_parent_corner", lambda *a, **k: None)
    monkeypatch.setattr(server.cv_shadow, "SHADOW_ENABLED", False)
    try:
        # FIRST invocation — the FULL normal pipeline
        asyncio.run(server.generate_full_report_task("n1"))
        # FIX 08 — ONE discovery pass precedes the standard full analysis.
        assert sessions[:3] == ["discover-n1", "full-n1", "full-retry-n1"]
        assert fake.doc["full_report_status"] == "failed"
        assert not _ready_writes(fake), "READY must never be written"
        assert fake.doc.get("identity_gate_done") is False
        assert fake.doc.get("identity_regen_required") is True
        assert not fake.doc.get("identity_corrective_persisted")

        # SECOND invocation — corrective-only recovery
        behavior["retry_raise"] = False
        asyncio.run(server.generate_full_report_task("n1"))
        assert sessions.count("full-n1") == 1, "standard full-{id} must NOT run again"
        assert sessions.count("discover-n1") == 1, "discovery is never re-run by recovery"
        assert sessions.count("full-retry-n1") == 2
        assert fake.doc["full_report"].get("_replacement") is True
        assert fake.doc.get("identity_corrective_persisted") is True
        assert fake.doc.get("identity_gate_done") is True
        assert fake.doc.get("identity_regen_required") is False
        assert len(_ready_writes(fake)) == 1
        assert fake.doc["full_report_status"] == "ready"
    finally:
        vid.unlink(missing_ok=True)
