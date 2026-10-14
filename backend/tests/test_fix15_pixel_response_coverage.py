"""Reader cardinality and bounded recovery, independent of desired actions."""
from copy import deepcopy
import json

import pytest

import evidence_feedback as feedback
import fix10a_vision_providers as vision
from test_fix13_evidence_feedback import trace


def row(index):
    return {"idx": index, "balls": [], "selected_body_ids": []}


def test_all_empty_images_are_a_complete_observation_not_a_missing_response():
    result = vision._action_pixel_response({"frames": [row(i) for i in range(12, 0, -1)]},
                                           list(range(1000, 2200, 100)))
    assert result["status"] == "COMPLETED"
    assert result["missing_media_ms"] == result["protocol_errors"] == []
    assert [r["idx"] for r in result["frames"]] == list(range(1, 13))


def test_one_returned_image_cannot_complete_a_twelve_image_review():
    times = list(range(1000, 2200, 100))
    result = vision._action_pixel_response({"frames": [row(7)]}, times)
    assert result["status"] == "PARTIAL_RESPONSE"
    assert result["frames"] == [row(7)]
    assert result["input_frame_count"] == 12
    assert result["returned_frame_indices"] == [7]
    assert result["missing_media_ms"] == times[:6] + times[7:]


@pytest.mark.parametrize("bad", [row(True), row(0), row(3), row(1.5),
                                   row("1"), row(1), {"idx": 2, "balls": None}, None])
def test_malformed_or_duplicate_index_cannot_rebind_proposals_to_an_image(bad):
    result = vision._action_pixel_response({"frames": [row(1), bad]}, [1000, 1100])
    assert result["status"] == "INVALID_RESPONSE"
    assert result["frames"] == [] and result["protocol_errors"]


@pytest.mark.parametrize("parsed", [None, [], {}, {"frames": {}}, {"frames": "1"}])
def test_non_frame_response_fails_closed(parsed):
    result = vision._action_pixel_response(parsed, [1000])
    assert result["status"] == "INVALID_RESPONSE" and result["frames"] == []


@pytest.mark.asyncio
async def test_reader_requires_every_image_and_audits_a_partial_response(monkeypatch, tmp_path):
    sent = []
    class Chat:
        def __init__(self, **_kwargs): pass
        def with_model(self, *_args): return self
        def with_params(self, **_kwargs): return self
        async def send_message(self, message):
            sent.append(message.text)
            return json.dumps({"frames": [row(1)]})
    paths = []
    for i in range(12):
        path = tmp_path / f"{i}.jpg"
        path.write_bytes(b"pixels")
        paths.append(str(path))
    monkeypatch.setattr(vision, "LlmChat", Chat)
    result = await vision.read_action_pixel_evidence("key", "test", paths, list(range(1000, 2200, 100)))
    assert result["status"] == "PARTIAL_RESPONSE" and len(sent) == 1
    assert "exactly 12 frame rows" in sent[0] and "EVERY input image" in sent[0]
    assert result["missing_frame_indices"] == list(range(2, 13))
    assert len(result["input_sha256"]) == len(result["response_sha256"]) == 64


@pytest.mark.asyncio
async def test_mismatched_image_timestamps_never_open_a_reader(monkeypatch):
    class Chat:
        def __init__(self, **_kwargs):
            raise AssertionError("mismatched inputs reached reader")
    monkeypatch.setattr(vision, "LlmChat", Chat)
    result = await vision.read_action_pixel_evidence("key", "test", ["not-opened"], [1000, 1100])
    assert result["status"] == "INVALID_INPUT" and result["frames"] == []


def test_partial_response_recovery_uses_missing_images_even_with_no_other_gap():
    source = trace()
    for frame in source["decoded_frames"]:
        frame["global_target"] = {"proof_eligible": True}
    source["ball_trajectory"] = [{"media_ms": f["media_ms"], "proof_eligible": True}
                                  for f in source["decoded_frames"]]
    source["contacts"] = {"accepted": [{"media_ms": 1000}], "unresolved": []}
    source["action_inspections"][0].update(status="PARTIAL_RESPONSE", missing_media_ms=[1550, 1600])
    plan = feedback.build_plan([source], budget=1)
    job = plan["jobs"][0]
    assert job["selected"] and job["reason"] == "PIXEL_RESPONSE_COVERAGE_GAP"
    assert job["center_ms"] == 1550 and job["before"]["uninspected_frames"] == 2
    assert job["end_ms"] - job["start_ms"] <= 1050
    updated = deepcopy(source)
    updated["evidence_feedback"] = {"round": 1}
    assert not feedback.build_plan([updated], budget=1)["jobs"]
