"""FIX10A trace-runner safety tests."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import event_trace  # noqa: E402
import golden_fixture_validator as gfv  # noqa: E402
import run_real_video_golden as runner  # noqa: E402


def _manifest(path: Path, sha: str):
    payload = {
        "schema": "FIX10_REAL_VIDEO_GOLDEN_V1",
        "fixture_id": "runner_test",
        "source": {"sha256": sha},
        "cases": [{
            "case_id": "saved",
            "window_ms": [1000, 2000],
            "physical_gate": {
                "require_target_release": True,
                "must_not_assert_physical_outcome": ["GOAL_PLANE_CROSSING"],
            },
        }],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _trace():
    return {
        "trace_id": "dense_test",
        "window": {"start_ms": 1000, "end_ms": 2000},
        "touch_graph": {"touches": []},
        "strike_evidence": [{
            "strike_id": "s1", "media_ms": 1500,
            "status": "VERIFIED_PHYSICAL_RELEASE",
            "global_target_id": "GLOBAL_TARGET",
        }],
        "outcome_evidence": [],
    }


def test_runner01_source_mismatch_fails_before_trace_validation(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fixture-video")
    manifest = tmp_path / "manifest.json"
    _manifest(manifest, "0" * 64)
    result = runner.run_validation(
        manifest_path=str(manifest), video_path=str(video), trace_paths=[]
    )
    assert result["status"] == gfv.FAIL
    assert result["reason"] == "REFERENCE_VIDEO_FINGERPRINT_MISMATCH"


def test_runner02_correct_source_with_no_traces_is_unresolved(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fixture-video")
    sha = hashlib.sha256(video.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    _manifest(manifest, sha)
    result = runner.run_validation(
        manifest_path=str(manifest), video_path=str(video), trace_paths=[]
    )
    assert result["source"]["status"] == gfv.PASS
    assert result["status"] == gfv.UNRESOLVED


def test_runner03_gzip_trace_can_produce_pass(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fixture-video")
    sha = hashlib.sha256(video.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    _manifest(manifest, sha)
    trace_path = tmp_path / "trace.json.gz"
    trace_path.write_bytes(event_trace.encode_trace_gzip(_trace()))
    result = runner.run_validation(
        manifest_path=str(manifest), video_path=str(video), trace_paths=[str(trace_path)]
    )
    assert result["source"]["status"] == gfv.PASS
    assert result["status"] == gfv.PASS
    assert result["trace_files"] == 1
