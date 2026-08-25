"""FIX10A structured multi-frame whole-ball goal proof regressions."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import fix10a_ball_proof_gate as ball_gate  # noqa: E402
import fix10a_goal_direction as direction  # noqa: E402
import fix10a_vision_providers as vision  # noqa: E402
import shot_outcome_engine as outcome_engine  # noqa: E402


def _line():
    return {"p1": {"x": .90, "y": .30}, "p2": {"x": .90, "y": .70}}


def _audit(*, continuity=True, proof_ready=True):
    return {
        "status": "VERIFIED_CROSSING",
        "confidence": "high",
        "proof_ready": proof_ready,
        "same_ball_continuity": continuity,
        "first_crossing_media_ms": 1200,
        "field_side_before_media_ms": 1000,
        "beyond_line_media_ms": 1200,
        "structured_evidence": [
            {"idx": 1, "media_ms": 1000, "ball_visible": True,
             "relation": "FIELD_SIDE", "confidence": "high"},
            {"idx": 2, "media_ms": 1100, "ball_visible": True,
             "relation": "ON_OR_STRADDLING_LINE", "confidence": "medium"},
            {"idx": 3, "media_ms": 1200, "ball_visible": True,
             "relation": "BEYOND_LINE_INSIDE_MOUTH", "confidence": "high"},
        ],
    }


def _geometry(*, field_side=True, audit=None):
    line = _line()
    out = {
        "status": "VERIFIED",
        "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
        "line": line,
        "line_by_ms": [
            {"media_ms": 1000, "line": line, "confidence": "high"},
            {"media_ms": 1200, "line": line, "confidence": "high"},
        ],
        "visual_crossing_audit": audit if audit is not None else _audit(),
    }
    if field_side:
        out.update({
            "field_side_status": "VERIFIED",
            "field_side_by_ms": [
                {"media_ms": 1000, "point": {"x": .70, "y": .50}, "confidence": "high"},
                {"media_ms": 1200, "point": {"x": .70, "y": .50}, "confidence": "high"},
            ],
        })
    return out


def _strike():
    return {
        "strike_id": "strike-target", "touch_id": "touch-target", "media_ms": 900,
        "scene_id": "s1", "player_track_id": "p015", "global_target_id": "GLOBAL_TARGET",
        "status": "VERIFIED_PHYSICAL_RELEASE",
    }


def test_svgp01_structured_visual_whole_ball_proof_survives_all_fail_closed_gates_without_detector_rows():
    geometry = _geometry()
    out = outcome_engine.reconstruct_post_strike_outcome(
        _strike(), [], {"touches": []}, goal_geometry=geometry, role_evidence={}
    )
    assert out["physical_outcome"] == "GOAL_PLANE_CROSSING"
    assert out["goal_plane_crossing"]["status"] == "VERIFIED"
    assert out["goal_plane_crossing"]["reason"] == "INDEPENDENT_MULTI_FRAME_WHOLE_BALL_CROSSING"
    assert out["goal_plane_crossing"]["evidence"][0]["proof_lane"] == "STRUCTURED_VISUAL_WHOLE_BALL"

    out = direction.apply_direction_gate(out, [], geometry)
    assert out["goal_plane_crossing"]["direction_status"] == "VERIFIED"
    assert out["goal_plane_crossing"]["direction"] == "FIELD_TO_GOAL"
    assert out["direction_gate"]["reason"] == "STRUCTURED_VISUAL_FIELD_TO_GOAL_DIRECTION_VERIFIED"

    out = ball_gate.apply_ball_proof_gate(out, [])
    assert out["goal_plane_crossing"]["status"] == "VERIFIED"
    assert out["ball_proof_gate"]["status"] == "VERIFIED"
    assert out["ball_proof_gate"]["reason"] == "STRUCTURED_VISUAL_WHOLE_BALL_CROSSING_PROOF"
    assert out["canonical_event_type"] is None


def test_svgp02_bare_visual_crossed_label_cannot_create_physical_crossing():
    geometry = _geometry(audit={"status": "VERIFIED_CROSSING", "confidence": "high"})
    out = outcome_engine.reconstruct_post_strike_outcome(
        _strike(), [], {"touches": []}, goal_geometry=geometry, role_evidence={}
    )
    assert out["goal_plane_crossing"]["status"] == "UNRESOLVED"
    assert out["physical_outcome"] != "GOAL_PLANE_CROSSING"


def test_svgp03_same_ball_continuity_is_mandatory():
    geometry = _geometry(audit=_audit(continuity=False))
    out = outcome_engine.reconstruct_post_strike_outcome(
        _strike(), [], {"touches": []}, goal_geometry=geometry, role_evidence={}
    )
    assert out["goal_plane_crossing"]["status"] == "UNRESOLVED"


def test_svgp04_independent_field_side_orientation_is_mandatory():
    geometry = _geometry(field_side=False)
    out = outcome_engine.reconstruct_post_strike_outcome(
        _strike(), [], {"touches": []}, goal_geometry=geometry, role_evidence={}
    )
    out = direction.apply_direction_gate(out, [], geometry)
    assert out["goal_plane_crossing"]["status"] == "UNRESOLVED"
    assert out["goal_plane_crossing"]["reason"] == "FIELD_SIDE_ORIENTATION_UNAVAILABLE"


def test_svgp05_ball_proof_rejects_structured_lane_without_verified_direction():
    geometry = _geometry()
    out = outcome_engine.reconstruct_post_strike_outcome(
        _strike(), [], {"touches": []}, goal_geometry=geometry, role_evidence={}
    )
    out = ball_gate.apply_ball_proof_gate(out, [])
    assert out["goal_plane_crossing"]["status"] == "UNRESOLVED"
    assert out["goal_plane_crossing"]["reason"] == "STRUCTURED_VISUAL_WHOLE_BALL_PROOF_INVALID"


class _FakeChat:
    def __init__(self, payload):
        self.payload = payload

    def with_model(self, *_args, **_kwargs):
        return self

    async def send_message(self, _message):
        return json.dumps(self.payload)


def _provider_payload():
    return {
        "geometry_status": "VERIFIED",
        "frames": [
            {"idx": 1, "visible": True, "p1": {"x": .20, "y": .80}, "p2": {"x": .80, "y": .80}, "confidence": "high"},
            {"idx": 2, "visible": True, "p1": {"x": .20, "y": .80}, "p2": {"x": .80, "y": .80}, "confidence": "high"},
            {"idx": 3, "visible": True, "p1": {"x": .20, "y": .80}, "p2": {"x": .80, "y": .80}, "confidence": "high"},
        ],
        "ball_evidence": [
            {"idx": 1, "ball_visible": True, "relation": "FIELD_SIDE", "confidence": "high"},
            {"idx": 2, "ball_visible": True, "relation": "ON_OR_STRADDLING_LINE", "confidence": "medium"},
            {"idx": 3, "ball_visible": True, "relation": "BEYOND_LINE_INSIDE_MOUTH", "confidence": "high"},
        ],
        "same_ball_continuity": True,
        "first_crossing_idx": 3,
        "crossing": "CROSSED",
        "crossing_confidence": "high",
        "reason": "continuous visible whole-ball transition",
    }


async def test_svgp06_provider_parser_requires_structured_continuous_path(monkeypatch, tmp_path):
    payload = _provider_payload()
    monkeypatch.setattr(vision, "LlmChat", lambda **_kwargs: _FakeChat(payload))
    paths = []
    for idx in range(3):
        path = tmp_path / f"frame-{idx}.jpg"
        path.write_bytes(b"frame-bytes")
        paths.append(str(path))
    out = await vision.read_goal_scene_evidence("key", "session", paths, [1000, 1100, 1200])
    assert out["proof_ready"] is True
    assert out["field_side_before_media_ms"] == 1000
    assert out["first_crossing_media_ms"] == 1200
    assert out["beyond_line_media_ms"] == 1200


async def test_svgp07_provider_parser_fails_closed_when_intermediate_ball_frame_is_missing(monkeypatch, tmp_path):
    payload = _provider_payload()
    payload["ball_evidence"] = [payload["ball_evidence"][0], payload["ball_evidence"][2]]
    monkeypatch.setattr(vision, "LlmChat", lambda **_kwargs: _FakeChat(payload))
    paths = []
    for idx in range(3):
        path = tmp_path / f"frame-{idx}.jpg"
        path.write_bytes(b"frame-bytes")
        paths.append(str(path))
    out = await vision.read_goal_scene_evidence("key", "session", paths, [1000, 1100, 1200])
    assert out["proof_ready"] is False
    assert out["proof_reason"] == "STRUCTURED_WHOLE_BALL_CROSSING_NOT_PROVEN"
