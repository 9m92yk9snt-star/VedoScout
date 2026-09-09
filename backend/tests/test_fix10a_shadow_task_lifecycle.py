"""Regression tests for FIX10A shadow task lifecycle (shadow-only).

Proves the fire-and-forget drop bug is fixed:
  * the task stays strongly referenced while running,
  * it is removed from the registry on completion,
  * exceptions and cancellation are observable via logs,
  * scheduling is non-blocking (main analysis is not blocked),
  * FIX10A only ever writes fix10a_* diagnostic fields (cannot mutate canonical).
"""
import asyncio
import logging

import fix10a_shadow_runtime as mod


class _FakeReports:
    def __init__(self):
        self.sets = []

    async def update_one(self, flt, update):
        self.sets.append((flt, update))


class _FakeDB:
    def __init__(self):
        self.reports = _FakeReports()


def test_task_referenced_while_running_then_removed(monkeypatch):
    async def scenario():
        mod._SHADOW_TASKS.clear()
        release = asyncio.Event()

        async def fake_run(**kwargs):
            await release.wait()
            return {"status": "ok"}

        monkeypatch.setattr(mod, "run_shadow", fake_run)
        task = mod.spawn_shadow(report_id="R1")
        assert isinstance(task, asyncio.Task)
        assert not task.done()
        assert task in mod._SHADOW_TASKS
        release.set()
        await asyncio.wait_for(task, timeout=1)
        await asyncio.sleep(0)
        assert task not in mod._SHADOW_TASKS
        assert len(mod._SHADOW_TASKS) == 0

    asyncio.run(scenario())


def test_uncaught_exception_is_logged_and_removed(monkeypatch, caplog):
    async def scenario():
        mod._SHADOW_TASKS.clear()

        async def boom(**kwargs):
            raise ValueError("kaboom")

        monkeypatch.setattr(mod, "run_shadow", boom)
        with caplog.at_level(logging.WARNING, logger="elite-scout"):
            task = mod.spawn_shadow(report_id="R2")
            await asyncio.sleep(0.05)
        assert task not in mod._SHADOW_TASKS
        msgs = " ".join(r.getMessage() for r in caplog.records)
        assert "R2" in msgs and "ERROR" in msgs

    asyncio.run(scenario())


def test_cancelled_is_logged_and_removed(monkeypatch, caplog):
    async def scenario():
        mod._SHADOW_TASKS.clear()

        async def hang(**kwargs):
            await asyncio.sleep(10)

        monkeypatch.setattr(mod, "run_shadow", hang)
        with caplog.at_level(logging.WARNING, logger="elite-scout"):
            task = mod.spawn_shadow(report_id="R3")
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0.05)
        assert task.cancelled()
        assert task not in mod._SHADOW_TASKS
        msgs = " ".join(r.getMessage() for r in caplog.records)
        assert "R3" in msgs and "CANCELLED" in msgs

    asyncio.run(scenario())


def test_shadow_only_writes_fix10a_fields(monkeypatch):
    """Real run_shadow: proves it can only emit fix10a_* diagnostics."""

    async def scenario():
        monkeypatch.setenv("FIX10A_SHADOW_ENABLED", "1")
        monkeypatch.setenv("FIX10A_SUPPORT_VISION_ENABLED", "0")
        monkeypatch.setattr(
            mod.physical_match_reconstruction,
            "reconstruct_physical_match",
            lambda *a, **k: {"status": "ok", "timebase": "canonical_media_ms", "traces": []},
        )
        db = _FakeDB()
        unified = {
            "status": "ok",
            "sequence_analysis": {"coverage_complete": True},
            "sequence_plan": {},
            "scene_graph": {},
            "identity_authority": {},
        }
        out = await mod.run_shadow(
            report_id="R-CANON",
            video_path="/tmp/x.mp4",
            unified_result=unified,
            db=db,
        )
        assert out["fix10a_canonical_authority"] is False
        assert len(db.reports.sets) >= 2, "shadow should persist running and terminal diagnostics"

        first_flt, first_update = db.reports.sets[0]
        assert first_flt == {"id": "R-CANON"}
        assert set(first_update.keys()) == {"$set"}
        first_doc = first_update["$set"]
        assert first_doc["fix10a_status"] == "running"
        assert first_doc["fix10a_finished_at"] is None
        assert first_doc["fix10a_canonical_authority"] is False
        assert all(k.startswith("fix10a_") for k in first_doc)

        flt, update = db.reports.sets[-1]
        assert flt == {"id": "R-CANON"}
        assert set(update.keys()) == {"$set"}
        set_doc = update["$set"]
        assert all(k.startswith("fix10a_") for k in set_doc)
        assert set_doc["fix10a_status"] == "ok"
        assert isinstance(set_doc["fix10a_started_at"], str)
        assert isinstance(set_doc["fix10a_finished_at"], str)
        assert float(set_doc["fix10a_elapsed_seconds"]) >= 0.0
        assert set_doc["fix10a_canonical_authority"] is False

    asyncio.run(scenario())


def test_skip_path_persists_nothing(monkeypatch):
    async def scenario():
        monkeypatch.setenv("FIX10A_SHADOW_ENABLED", "1")
        db = _FakeDB()
        unified = {
            "status": "partial_coverage",
            "sequence_analysis": {"coverage_complete": False},
        }
        out = await mod.run_shadow(
            report_id="R4",
            video_path="/tmp/x.mp4",
            unified_result=unified,
            db=db,
        )
        assert out["status"] == "skipped"
        assert out["canonical_authority"] is False
        assert db.reports.sets == []

    asyncio.run(scenario())
