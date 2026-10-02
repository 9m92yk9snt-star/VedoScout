"""FIX11 physical-recall planner regression tests."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import full_video_event_recall as recall  # noqa: E402


def _scene_graph(end_ms=8000, frames=None):
    return {
        "scenes": [{"scene_id": "scene_1", "start_ms": 0, "end_ms": end_ms}],
        "frames": list(frames or []),
    }


def _plan(reasons=None, trigger_ms=1000, end_ms=8000):
    reasons = list(reasons or ["TARGET_POSSESSION", "BALL_NEAR_TARGET"])
    return {
        "analysis_windows": [{
            "sequence_id": "seq_1", "scene_id": "scene_1",
            "start_ms": 0, "end_ms": end_ms,
        }],
        "refinement_windows": [{
            "refinement_id": "ref_1", "scene_id": "scene_1",
            "start_ms": max(0, trigger_ms - 1400),
            "end_ms": min(end_ms, trigger_ms + 1800),
            "trigger_ms": [trigger_ms],
            "reasons": reasons,
            "sequence_ids": ["seq_1"],
        }],
    }


def _frame(ms, relation="TARGET_LIKELY_POSSESSION", holder="p001"):
    return {
        "media_ms": ms,
        "scene_id": "scene_1",
        "global_target": {
            "status": "VERIFIED",
            "local_track_id": "p001",
            "candidate_local_track_ids": ["p001"],
            "proof_eligible": True,
        },
        "possession": {
            "holder_local_track_id": holder,
            "target_relation": relation,
        },
    }


def test_fix11_recall_extends_target_ball_trigger_through_scoring_horizon():
    out = recall.build_physical_recall_windows(
        _plan(trigger_ms=1000),
        _scene_graph(8000),
    )
    assert out["scan_complete"] is True
    assert out["windows"]
    window = out["windows"][0]
    assert window["recall_window"] is True
    assert window["start_ms"] == 0
    assert window["end_ms"] >= 1000 + recall.RECALL_POST_MS
    assert "FIX11_PHYSICAL_RECALL" in window["reasons"]
    assert "BALL_NEAR_TARGET" in window["reasons"]


def test_fix11_recall_does_not_open_physical_window_for_pressure_only_trigger():
    out = recall.build_physical_recall_windows(
        _plan(reasons=["CLOSE_PRESSURE", "TARGET_MOTION_CHANGE"]),
        _scene_graph(8000),
    )
    assert out["windows"] == []


def test_fix11_recall_never_crosses_hard_scene_end():
    out = recall.build_physical_recall_windows(
        _plan(trigger_ms=4200, end_ms=5000),
        _scene_graph(5000),
    )
    assert out["windows"]
    assert max(w["end_ms"] for w in out["windows"]) <= 5000


def test_fix11_scene_graph_fallback_works_without_refinement_metadata():
    frames = [_frame(1000), _frame(1250), _frame(1500)]
    out = recall.build_physical_recall_windows(
        {
            "analysis_windows": [{
                "sequence_id": "seq_1", "scene_id": "scene_1",
                "start_ms": 0, "end_ms": 8000,
            }],
            "refinement_windows": [],
        },
        _scene_graph(8000, frames),
    )
    assert out["metrics"]["graph_trigger_frames"] == 3
    assert out["windows"]
    assert any("TARGET_POSSESSION" in w["reasons"] for w in out["windows"])


def test_fix11_union_merges_overlap_without_losing_recall_authority():
    existing = [{
        "dense_window_id": "dense_old",
        "scene_id": "scene_1",
        "start_ms": 500,
        "end_ms": 2500,
        "reasons": ["ACTION_CONTACT"],
        "source_sequence_ids": ["seq_1"],
    }]
    new = [{
        "dense_window_id": "recall_new",
        "scene_id": "scene_1",
        "start_ms": 1000,
        "end_ms": 6500,
        "reasons": ["FIX11_PHYSICAL_RECALL", "TARGET_POSSESSION"],
        "source_sequence_ids": ["seq_1"],
        "recall_window": True,
    }]
    rows = recall.union_dense_windows(existing, new)
    assert len(rows) == 1
    assert rows[0]["recall_window"] is True
    assert rows[0]["start_ms"] == 500
    assert rows[0]["end_ms"] == 6500
    assert {"ACTION_CONTACT", "FIX11_PHYSICAL_RECALL"}.issubset(set(rows[0]["reasons"]))
