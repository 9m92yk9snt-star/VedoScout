"""FIX10A8 — bounded event-trace regression tests."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import event_trace as et  # noqa: E402


def _fixture():
    frame = {
        "media_ms": 1000,
        "scene_id": "scene_001",
        "used_fallback": False,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "camera_state": "AFFINE_VERIFIED",
        "frame_bgr": np.zeros((8, 8, 3), dtype=np.uint8),
        "global_target": {"status": "VERIFIED", "local_track_id": "p001", "proof_eligible": True},
        "players": [{"local_track_id": "p001", "box": {"x": .1, "y": .2, "w": .1, "h": .3}}],
        "ball_candidates": [{"box": {"x": .14, "y": .48, "w": .02, "h": .02}, "confidence": .9}],
    }
    trajectory = [{
        "media_ms": 1000, "state": "MEASURED",
        "box": {"x": .14, "y": .48, "w": .02, "h": .02},
        "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False,
    }]
    contact = {
        "accepted": [{"contact_id": "c1", "media_ms": 1000, "player_track_id": "p001", "status": "VERIFIED"}],
        "unresolved": [], "rejected": [], "metrics": {"accepted": 1},
    }
    touch = {"touches": [{"touch_id": "t1", "media_ms": 1000, "player_track_id": "p001", "status": "VERIFIED"}]}
    analysis = {"sequences": [{
        "sequence_id": "seq1", "scene_id": "scene_001", "summary": "model story",
        "actions": [{"action_id": "a1", "kind": "SHOT", "start_ms": 980, "end_ms": 1020, "outcome": "GOAL"}],
    }]}
    window = {"dense_window_id": "d1", "scene_id": "scene_001", "start_ms": 900, "end_ms": 1200, "source_sequence_ids": ["seq1"]}
    return frame, trajectory, contact, touch, analysis, window


def test_a801_trace_contains_pts_player_ball_contact_and_touch_data():
    frame, trajectory, contact, touch, analysis, window = _fixture()
    trace = et.build_event_trace(
        trace_id="trace1", source_video={"role": "canonical_web", "fingerprint": "abc"},
        window=window, dense_frames=[frame], ball_trajectory=trajectory,
        contact_result=contact, touch_graph=touch, sequence_analysis=analysis,
    )
    assert trace["decoded_frames"][0]["media_ms"] == 1000
    assert trace["decoded_frames"][0]["players"][0]["local_track_id"] == "p001"
    assert trace["ball_trajectory"][0]["state"] == "MEASURED"
    assert trace["contacts"]["accepted"][0]["contact_id"] == "c1"
    assert trace["touch_graph"]["touches"][0]["touch_id"] == "t1"


def test_a802_trace_never_persists_raw_image_arrays():
    frame, trajectory, contact, touch, analysis, window = _fixture()
    trace = et.build_event_trace(
        trace_id="trace1", source_video={}, window=window, dense_frames=[frame],
        ball_trajectory=trajectory, contact_result=contact, touch_graph=touch,
        sequence_analysis=analysis,
    )
    assert "frame_bgr" not in trace["decoded_frames"][0]
    encoded = et.encode_trace_gzip(trace)
    assert b"frame_bgr" not in encoded


def test_a803_gzip_roundtrip_is_lossless():
    frame, trajectory, contact, touch, analysis, window = _fixture()
    trace = et.build_event_trace(
        trace_id="trace1", source_video={}, window=window, dense_frames=[frame],
        ball_trajectory=trajectory, contact_result=contact, touch_graph=touch,
        sequence_analysis=analysis,
    )
    assert et.decode_trace_gzip(et.encode_trace_gzip(trace)) == trace


def test_a804_compact_summary_does_not_duplicate_dense_payload():
    frame, trajectory, contact, touch, analysis, window = _fixture()
    trace = et.build_event_trace(
        trace_id="trace1", source_video={}, window=window, dense_frames=[frame] * 20,
        ball_trajectory=trajectory * 20, contact_result=contact, touch_graph=touch,
        sequence_analysis=analysis,
    )
    summary = et.compact_trace_summary(trace)
    assert summary["frames"] == 20
    assert "decoded_frames" not in summary
    assert "ball_trajectory" not in summary
    assert "contacts" not in summary


def test_a805_primary_model_story_is_comparison_only():
    frame, trajectory, contact, touch, analysis, window = _fixture()
    trace = et.build_event_trace(
        trace_id="trace1", source_video={}, window=window, dense_frames=[frame],
        ball_trajectory=trajectory, contact_result=contact, touch_graph=touch,
        sequence_analysis=analysis,
    )
    assert trace["primary_observation"]["role"] == "COMPARISON_ONLY"
    assert trace["primary_observation"]["sequences"][0]["actions"][0]["outcome"] == "GOAL"
    assert trace["contacts"]["accepted"][0]["player_track_id"] == "p001"


def test_a806_trace_hash_and_gzip_are_stable_for_same_payload():
    frame, trajectory, contact, touch, analysis, window = _fixture()
    kwargs = dict(
        trace_id="trace1", source_video={"fingerprint": "same"}, window=window,
        dense_frames=[frame], ball_trajectory=trajectory, contact_result=contact,
        touch_graph=touch, sequence_analysis=analysis,
    )
    left = et.build_event_trace(**kwargs)
    right = et.build_event_trace(**kwargs)
    assert et.trace_sha256(left) == et.trace_sha256(right)
    assert et.encode_trace_gzip(left) == et.encode_trace_gzip(right)
