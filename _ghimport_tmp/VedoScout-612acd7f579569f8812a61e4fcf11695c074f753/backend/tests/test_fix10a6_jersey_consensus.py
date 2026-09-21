"""FIX10A6 — jersey-number reader and multi-frame consensus tests."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import identity_verify as iv  # noqa: E402
import jersey_consensus as jc  # noqa: E402


def _vote(ms, number=None, confidence="high", readable=True, reason="visible"):
    return {
        "media_ms": int(ms),
        "readable": bool(readable),
        "number": number,
        "confidence": confidence,
        "reason": reason,
    }


def test_a601_three_number10_votes_outweigh_one_weak_number18_vote():
    result = jc.aggregate_jersey_votes([
        _vote(1000, "10", "high"),
        _vote(1200, "10", "high"),
        _vote(1400, "10", "medium"),
        _vote(1600, "18", "low"),
    ])
    assert result["status"] == "VERIFIED"
    assert result["number"] == "10"
    assert result["agreeing_frames"] == 3
    assert result["posterior"]["10"] > result["posterior"]["18"]
    assert len(result["votes"]) == 4


def test_a602_conflicting_number10_and_number12_votes_stay_unresolved():
    result = jc.aggregate_jersey_votes([
        _vote(1000, "10", "high"),
        _vote(1200, "10", "high"),
        _vote(1400, "12", "high"),
        _vote(1600, "12", "high"),
    ])
    assert result["status"] == "UNRESOLVED"
    assert result["number"] is None
    assert result["reason"] == "CONFLICTING_JERSEY_NUMBER_VOTES"
    assert abs(result["posterior"]["10"] - result["posterior"]["12"]) < 1e-9


def test_a603_single_clear_frame_is_supporting_not_verified_consensus():
    result = jc.aggregate_jersey_votes([_vote(1000, "10", "high")])
    assert result["status"] == "SUPPORTING"
    assert result["number"] is None
    assert result["leading_number"] == "10"
    assert result["agreeing_frames"] == 1


def test_a604_unreadable_frames_return_unknown_without_inventing_number():
    result = jc.aggregate_jersey_votes([
        _vote(1000, None, "low", readable=False, reason="back turned"),
        _vote(1300, None, "medium", readable=False, reason="blurred"),
    ])
    assert result["status"] == "UNKNOWN"
    assert result["number"] is None
    assert result["posterior"] == {}


async def test_a605_non_target_reader_has_no_expected_number_hint(monkeypatch, tmp_path):
    # The API itself accepts no expected/known jersey-number parameter.
    assert list(inspect.signature(iv.read_visible_jersey_number).parameters) == [
        "api_key", "session_id", "crop_path"
    ]
    crop = tmp_path / "teammate.jpg"
    crop.write_bytes(b"not-a-real-image-but-reader-only-base64s-it")
    captured = {}

    class FakeChat:
        def __init__(self, **kwargs):
            captured["system"] = kwargs.get("system_message")

        def with_model(self, provider, model):
            captured["provider"] = provider
            captured["model"] = model
            return self

        async def send_message(self, msg):
            captured["prompt"] = msg.text
            return '{"readable":true,"number":"10","confidence":"high","reason":"digits clear"}'

    monkeypatch.setattr(iv, "LlmChat", FakeChat)
    monkeypatch.setattr(
        iv, "UserMessage",
        lambda text, file_contents: SimpleNamespace(text=text, file_contents=file_contents),
    )
    monkeypatch.setattr(
        iv, "ImageContent",
        lambda image_base64: SimpleNamespace(image_base64=image_base64),
    )
    result = await iv.read_visible_jersey_number("key", "jersey-p010", str(crop))
    assert result["readable"] is True
    assert result["number"] == "10"
    prompt = captured["prompt"].lower()
    assert "family states" not in prompt
    assert "expected number" not in prompt
    assert "target wears" not in prompt


def test_a606_jersey_consensus_cannot_change_global_target_authority():
    frames = [{
        "media_ms": 1000,
        "global_target": {
            "status": "HYPOTHESES",
            "local_track_id": None,
            "candidate_local_track_ids": ["p010", "p012"],
            "proof_eligible": False,
        },
        "players": [
            {"local_track_id": "p010", "box": {"x": .2, "y": .2, "w": .1, "h": .3},
             "association_state": "VERIFIED_LOCAL"},
            {"local_track_id": "p012", "box": {"x": .35, "y": .2, "w": .1, "h": .3},
             "association_state": "VERIFIED_LOCAL"},
        ],
    }]
    graph = {"touches": [
        {"touch_id": "t10", "player_track_id": "p010", "global_target_id": None},
    ]}
    original_target = dict(frames[0]["global_target"])
    out = jc.apply_jersey_consensus(
        frames,
        graph,
        {"p010": [_vote(1000, "10"), _vote(1300, "10")]},
    )
    assert out["consensus_by_track"]["p010"]["status"] == "VERIFIED"
    assert out["window_evidence"][0]["global_target"] == original_target
    assert out["touch_graph"]["touches"][0]["global_target_id"] is None
    assert out["touch_graph"]["touches"][0]["jersey_posterior"]["number"] == "10"
