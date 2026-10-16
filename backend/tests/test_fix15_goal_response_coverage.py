"""Goal replies must explicitly cover geometry and ball for every input image."""
from copy import deepcopy
import json

import pytest

import fix10a_vision_providers as vision


def hidden_payload(count):
    return {
        "geometry_status": "UNRESOLVED",
        "frames": [{"idx": i, "visible": False} for i in range(1, count + 1)],
        "ball_evidence": [{"idx": i, "ball_visible": False, "relation": "UNRESOLVED"}
                          for i in range(1, count + 1)],
        "crossing": "UNRESOLVED", "crossing_confidence": "low",
        "reason": "goal and ball not visible",
    }


def test_all_hidden_images_are_complete_observations_in_both_streams():
    payload = hidden_payload(12)
    payload["frames"].reverse()
    result = vision._goal_scene_response_coverage(payload, list(range(1000, 2200, 100)))
    assert result["status"] == "COMPLETED"
    assert result["returned_frame_indices"] == {field: list(range(1, 13)) for field in ("frames", "ball_evidence")}
    assert result["missing_media_ms"] == result["protocol_errors"] == []


def test_geometry_and_ball_omissions_are_audited_separately_at_actual_media_times():
    payload = hidden_payload(12)
    payload["frames"] = payload["frames"][:1]
    payload["ball_evidence"] = payload["ball_evidence"][:9]
    times = list(range(1000, 2200, 100))
    result = vision._goal_scene_response_coverage(payload, times)
    assert result["status"] == "PARTIAL_RESPONSE"
    assert result["missing_frame_indices"] == {"frames": list(range(2, 13)), "ball_evidence": [10, 11, 12]}
    assert result["missing_media_ms"] == times[1:]


@pytest.mark.parametrize("field", ["frames", "ball_evidence"])
@pytest.mark.parametrize("bad_index", [True, 0, 4, 1.5, "1", 1])
def test_invalid_or_duplicate_indices_cannot_alias_an_image(field, bad_index):
    payload = hidden_payload(3)
    payload[field][1]["idx"] = bad_index
    result = vision._goal_scene_response_coverage(payload, [1000, 1100, 1200])
    assert result["status"] == "INVALID_RESPONSE" and result["protocol_errors"]


@pytest.mark.parametrize("field", ["frames", "ball_evidence"])
@pytest.mark.parametrize("rows", [None, {}, "1", [None]])
def test_non_object_rows_or_missing_streams_are_invalid(field, rows):
    payload = hidden_payload(3)
    payload[field] = rows
    result = vision._goal_scene_response_coverage(payload, [1000, 1100, 1200])
    assert result["status"] == "INVALID_RESPONSE" and result["protocol_errors"]


@pytest.mark.parametrize("field, key, value", [
    ("frames", "visible", "false"),
    ("ball_evidence", "ball_visible", None),
    ("ball_evidence", "relation", None),
])
def test_presence_of_index_does_not_replace_required_observation(field, key, value):
    payload = hidden_payload(3)
    payload[field][0][key] = value
    assert vision._goal_scene_response_coverage(payload, [1000, 1100, 1200])["status"] == "INVALID_RESPONSE"


async def invoke_reader(monkeypatch, tmp_path, payload):
    calls = []
    class Chat:
        def __init__(self, **_kwargs): pass
        def with_model(self, *_args): return self
        def with_params(self, **_kwargs): return self
        async def send_message(self, message):
            calls.append(message.text)
            return json.dumps(payload)
    monkeypatch.setattr(vision, "LlmChat", Chat)
    times = list(range(1000, 2200, 100))
    paths = []
    for i in range(len(times)):
        path = tmp_path / f"frame-{i}.jpg"
        path.write_bytes(b"synthetic-pixels")
        paths.append(str(path))
    return await vision.read_goal_scene_evidence("key", "test", paths, times), calls


@pytest.mark.asyncio
async def test_complete_but_hidden_response_stays_unresolved_without_retry(monkeypatch, tmp_path):
    result, calls = await invoke_reader(monkeypatch, tmp_path, hidden_payload(12))
    assert len(calls) == 1 and "exactly 12 frames rows AND exactly 12 ball_evidence rows" in calls[0]
    assert result["response_coverage"]["status"] == "COMPLETED"
    assert result["proof_ready"] is False and result["geometry_status"] == "UNRESOLVED"
    assert result["reason"] == "goal and ball not visible"
    assert len(result["ball_evidence"]) == 12
    assert result["field_side_source"] == "SHARED_GOAL_SCENE_PLAYABLE_PITCH"
    assert result["field_side_status"] == "UNRESOLVED" and result["field_side_by_ms"] == []


@pytest.mark.parametrize("field", ["frames", "ball_evidence"])
@pytest.mark.asyncio
async def test_partial_reply_cannot_admit_any_crossing_occlusion_or_reaction_claim(field, monkeypatch, tmp_path):
    payload = hidden_payload(12)
    payload.update(geometry_status="VERIFIED", crossing="CROSSED", crossing_confidence="high",
                   same_ball_continuity=True, first_crossing_idx=3)
    payload["frames"] = [{"idx": i, "visible": True, "p1": {"x": .2, "y": .8},
                          "p2": {"x": .8, "y": .8}, "confidence": "high"} for i in range(1, 13)]
    payload["ball_evidence"][:3] = [
        {"idx": i, "ball_visible": True, "relation": relation, "confidence": "high"}
        for i, relation in enumerate(["FIELD_SIDE", "ON_OR_STRADDLING_LINE", "BEYOND_LINE_INSIDE_MOUTH"], 1)
    ]
    complete = deepcopy(payload)
    payload[field].pop()
    result, calls = await invoke_reader(monkeypatch, tmp_path, payload)
    assert len(calls) == 1 and result["response_coverage"]["status"] == "PARTIAL_RESPONSE"
    assert result["proof_reason"] == "GOAL_SCENE_PIXEL_RESPONSE_COVERAGE_GAP"
    assert result["frames"] == result["ball_evidence"] == []
    assert result["crossing"] == "UNRESOLVED" and result["proof_ready"] is False
    assert result["occlusion_crossing_audit"]["status"] == "UNRESOLVED"
    assert result["reaction_support_evidence"]["status"] == "UNRESOLVED"
    assert len(result["model_review_audit"]["response_sha256"]) == 64
    # The same literal crossing with all observations retains the existing strict proof.
    verified, _ = await invoke_reader(monkeypatch, tmp_path, complete)
    assert verified["response_coverage"]["status"] == "COMPLETED" and verified["proof_ready"] is True


@pytest.mark.parametrize("kind", ["count_mismatch", "missing_path", "invalid_time"])
@pytest.mark.asyncio
async def test_invalid_input_cannot_silently_reduce_the_images_reviewed(kind, monkeypatch, tmp_path):
    def no_chat(**_kwargs):
        raise AssertionError("invalid input reached a model")
    monkeypatch.setattr(vision, "LlmChat", no_chat)
    path = tmp_path / "image.jpg"
    path.write_bytes(b"synthetic-pixels")
    paths, times = [str(path)] * 3, [1000, 1100, 1200]
    if kind == "count_mismatch": times.pop()
    if kind == "missing_path": paths[1] = str(tmp_path / "missing.jpg")
    if kind == "invalid_time": times[1] = None
    result = await vision.read_goal_scene_evidence("key", "test", paths, times)
    assert result["reason"] in {"goal_scene_input_count_mismatch", "goal_scene_invalid_input"}
    assert result["proof_ready"] is False and result["frames"] == []


@pytest.mark.usefixtures("inline_support_vision")
def test_provider_preserves_partial_coverage_diagnostics_and_rejects_geometry(monkeypatch):
    import numpy as np
    monkeypatch.setattr(vision, "_read_frames", lambda _video, requested: {
        ms: (ms, np.zeros((40, 60, 3), dtype=np.uint8)) for ms in requested})
    async def partial(_key, _session, _paths, times, **_kwargs):
        coverage = vision._goal_scene_response_coverage(hidden_payload(1), times)
        return {"frames": [], "response_coverage": coverage,
                "reason": "goal_scene_pixel_response_coverage_gap",
                "proof_reason": "GOAL_SCENE_PIXEL_RESPONSE_COVERAGE_GAP"}
    monkeypatch.setattr(vision, "read_goal_scene_evidence", partial)
    provider = vision.build_shadow_providers("key", "test", "synthetic.mp4")
    result = provider.goal_geometry_provider({"dense_window_id": "generic", "start_ms": 0, "end_ms": 4000},
                                             {"media_ms": 1000})
    assert result["status"] == "UNRESOLVED" and result["line_by_ms"] == []
    assert result["response_coverage"]["status"] == "PARTIAL_RESPONSE"
    assert result["visual_crossing_audit"]["proof_reason"] == "GOAL_SCENE_PIXEL_RESPONSE_COVERAGE_GAP"
