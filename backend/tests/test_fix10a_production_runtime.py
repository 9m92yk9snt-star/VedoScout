"""FIX10A synchronous production runtime regression tests."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import fix10a_runtime as fxr  # noqa: E402


class _Reports:
    def __init__(self):
        self.calls = []

    async def update_one(self, query, update):
        self.calls.append((query, update))
        return None


class _DB:
    def __init__(self):
        self.reports = _Reports()


class _R2:
    def __init__(self, configured=True):
        self.configured = configured
        self.uploads = []

    def is_configured(self):
        return self.configured

    def upload_bytes(self, key, data, content_type):
        self.uploads.append((key, bytes(data), content_type))
        return "https://storage.example/" + key


def _unified(ready=True):
    return {
        "status": "ok" if ready else "partial_coverage",
        "sequence_plan": {"analysis_windows": []},
        "sequence_analysis": {"coverage_complete": bool(ready), "sequences": []},
        "scene_graph": {},
        "identity_authority": {},
        "canonical_events": {
            "version": 1,
            "status": "ok",
            "global_target_id": "GLOBAL_TARGET",
            "timebase": "canonical_media_ms",
            "events": [],
            "unresolved": [],
            "rejected": [],
            "counts": {},
            "metrics": {
                "observations_total": 0,
                "events_accepted": 0,
                "observations_unresolved": 0,
                "observations_rejected": 0,
                "goals": 0,
                "assists": 0,
                "shots": 0,
            },
        },
        "metrics": {"coverage_complete": bool(ready), "events_accepted": 0},
    }


def _trace():
    return {
        "version": 1,
        "trace_id": "dense_001",
        "window": {"start_ms": 1000, "end_ms": 1200},
        "decoded_frames": [],
        "ball_trajectory": [],
        "contacts": {"accepted": [], "unresolved": []},
        "touch_graph": {"touches": []},
        "strike_evidence": [],
        "jersey_consensus": {},
        "outcome_evidence": [],
        "contradictions": [],
        "unresolved_reasons": [],
    }


def _physical(trace=True):
    return {
        "version": 1,
        "status": "ok",
        "timebase": "canonical_media_ms",
        "source_role": "CANONICAL_WEB_VIDEO",
        "source_video": {"fingerprint": "abc"},
        "windows": [{"status": "ok"}],
        "trace_summaries": [],
        "traces": [_trace()] if trace else [],
        "unresolved_reasons": [],
        "metrics": {"traces": 1 if trace else 0},
    }


def _persisted_states(db):
    return [call[1]["$set"].get("fix10a_status") for call in db.reports.calls]


def test_fix10a_production01_has_no_shadow_scheduler_or_shadow_flag():
    assert not hasattr(fxr, "spawn_shadow")
    assert not hasattr(fxr, "shadow_enabled")
    assert not hasattr(fxr, "FLAG")


async def test_fix10a_production02_unready_result_skips_without_persistence():
    db = _DB()
    out = await fxr.run(
        report_id="r1",
        video_path="video.mp4",
        unified_result=_unified(False),
        db=db,
    )
    assert out["status"] == "skipped"
    assert out["mode"] == "production"
    assert db.reports.calls == []


async def test_fix10a_production03_success_is_awaitable_and_builds_authoritative_candidate(monkeypatch):
    monkeypatch.setenv(fxr.SUPPORT_VISION_FLAG, "0")
    monkeypatch.setattr(
        fxr.physical_match_reconstruction,
        "reconstruct_physical_match",
        lambda *_a, **_k: _physical(True),
    )
    db, r2 = _DB(), _R2(True)
    out = await fxr.run(
        report_id="report/unsafe",
        video_path="video.mp4",
        unified_result=_unified(),
        db=db,
        r2_storage=r2,
        source_video={"fingerprint": "abc"},
    )
    assert out["status"] == "ok"
    assert out["mode"] == "production"
    assert out["_fix10b_candidate"]["enabled"] is True
    assert out["_fix10b_candidate"]["mode"] == "production"
    assert len(r2.uploads) == 1
    key, payload, content_type = r2.uploads[0]
    assert key.startswith("reports/report-unsafe/match-intelligence/")
    assert key.endswith(".json.gz")
    assert payload[:2] == b"\x1f\x8b"
    assert content_type == "application/gzip"
    assert _persisted_states(db) == ["running", "ok"]
    persisted = db.reports.calls[-1][1]["$set"]
    assert persisted["fix10a_mode"] == "production"
    assert persisted["fix10a_reconciliation_authority"] == "FIX10B"
    assert all(k.startswith("fix10a_") for k in persisted)


async def test_fix10a_production04_r2_unavailable_uses_local_trace_storage(monkeypatch, tmp_path):
    monkeypatch.setenv(fxr.SUPPORT_VISION_FLAG, "0")
    monkeypatch.setattr(
        fxr.physical_match_reconstruction,
        "reconstruct_physical_match",
        lambda *_a, **_k: _physical(True),
    )
    db, r2 = _DB(), _R2(False)
    out = await fxr.run(
        report_id="r1",
        video_path="video.mp4",
        unified_result=_unified(),
        db=db,
        r2_storage=r2,
        local_dir=tmp_path,
    )
    manifest = out["fix10a_trace_manifest"][0]
    assert manifest["storage"] == "local_diagnostic"
    assert Path(manifest["local_path"]).exists()
    assert _persisted_states(db) == ["running", "ok"]


async def test_fix10a_production05_physical_exception_fails_closed(monkeypatch):
    monkeypatch.setenv(fxr.SUPPORT_VISION_FLAG, "0")

    def boom(*_a, **_k):
        raise RuntimeError("physical failure")

    monkeypatch.setattr(
        fxr.physical_match_reconstruction,
        "reconstruct_physical_match",
        boom,
    )
    db = _DB()
    out = await fxr.run(
        report_id="r1",
        video_path="video.mp4",
        unified_result=_unified(),
        db=db,
    )
    assert out["status"] == "error"
    assert out["mode"] == "production"
    assert "RuntimeError" in out["fix10a_error"]
    assert _persisted_states(db) == ["running", "error"]
    assert all(
        key.startswith("fix10a_")
        for _, update in db.reports.calls
        for key in update["$set"]
    )
