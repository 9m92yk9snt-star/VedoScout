"""FIX10A — shadow runtime persistence/fail-soft regression tests."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import fix10a_shadow_runtime as fsr  # noqa: E402


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
        "jersey_consensus": {},
        "outcome_evidence": [],
        "contradictions": [],
        "unresolved_reasons": [],
    }


async def test_shadow01_default_off_does_nothing(monkeypatch):
    monkeypatch.delenv(fsr.FLAG, raising=False)
    db = _DB()
    out = await fsr.run_shadow(
        report_id="r1", video_path="video.mp4", unified_result=_unified(), db=db,
    )
    assert out["status"] == "disabled"
    assert out["canonical_authority"] is False
    assert db.reports.calls == []


async def test_shadow02_unready_unified_result_is_skipped(monkeypatch):
    monkeypatch.setenv(fsr.FLAG, "1")
    db = _DB()
    out = await fsr.run_shadow(
        report_id="r1", video_path="video.mp4", unified_result=_unified(False), db=db,
    )
    assert out["status"] == "skipped"
    assert db.reports.calls == []


async def test_shadow03_success_persists_compact_summary_and_r2_trace(monkeypatch):
    monkeypatch.setenv(fsr.FLAG, "1")
    monkeypatch.setattr(
        fsr.physical_match_reconstruction,
        "reconstruct_physical_match",
        lambda *_a, **_k: {
            "version": 1, "status": "ok", "timebase": "canonical_media_ms",
            "source_role": "CANONICAL_WEB_VIDEO", "source_video": {"fingerprint": "abc"},
            "windows": [{"status": "ok"}], "trace_summaries": [],
            "traces": [_trace()], "unresolved_reasons": [], "metrics": {"traces": 1},
        },
    )
    db, r2 = _DB(), _R2(True)
    out = await fsr.run_shadow(
        report_id="report/unsafe", video_path="video.mp4", unified_result=_unified(),
        db=db, r2_storage=r2, source_video={"fingerprint": "abc"},
    )
    assert out["status"] == "ok"
    assert out["fix10a_canonical_authority"] is False
    assert len(r2.uploads) == 1
    key, payload, content_type = r2.uploads[0]
    assert key.startswith("reports/report-unsafe/match-intelligence/")
    assert key.endswith(".json.gz")
    assert payload[:2] == b"\x1f\x8b"
    assert content_type == "application/gzip"
    assert len(db.reports.calls) == 1
    persisted = db.reports.calls[0][1]["$set"]
    assert "traces" not in persisted["fix10a_physical_summary"]
    assert persisted["fix10a_canonical_authority"] is False
    assert persisted["fix10a_trace_manifest"][0]["storage"] == "r2"


async def test_shadow04_r2_unavailable_uses_local_diagnostic_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv(fsr.FLAG, "true")
    monkeypatch.setattr(
        fsr.physical_match_reconstruction,
        "reconstruct_physical_match",
        lambda *_a, **_k: {
            "version": 1, "status": "ok", "timebase": "canonical_media_ms",
            "source_role": "CANONICAL_WEB_VIDEO", "source_video": {},
            "windows": [], "trace_summaries": [], "traces": [_trace()],
            "unresolved_reasons": [], "metrics": {},
        },
    )
    db, r2 = _DB(), _R2(False)
    out = await fsr.run_shadow(
        report_id="r1", video_path="video.mp4", unified_result=_unified(),
        db=db, r2_storage=r2, local_dir=tmp_path,
    )
    manifest = out["fix10a_trace_manifest"][0]
    assert manifest["storage"] == "local_diagnostic"
    assert Path(manifest["local_path"]).exists()


async def test_shadow05_physical_exception_is_diagnostic_and_never_raises(monkeypatch):
    monkeypatch.setenv(fsr.FLAG, "1")
    def _boom(*_a, **_k):
        raise RuntimeError("physical failure")
    monkeypatch.setattr(fsr.physical_match_reconstruction, "reconstruct_physical_match", _boom)
    db = _DB()
    out = await fsr.run_shadow(
        report_id="r1", video_path="video.mp4", unified_result=_unified(), db=db,
    )
    assert out["status"] == "error"
    assert out["fix10a_canonical_authority"] is False
    assert "RuntimeError" in out["fix10a_error"]
    assert db.reports.calls[0][1]["$set"]["fix10a_status"] == "error"
