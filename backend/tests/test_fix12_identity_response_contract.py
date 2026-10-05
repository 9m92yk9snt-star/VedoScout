"""Malformed model booleans cannot turn a negative verdict into a match."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import identity_verify as identity  # noqa: E402


@pytest.mark.parametrize("field", ["match", "correct", "describes_target"])
@pytest.mark.parametrize("value", ["false", 1, False])
async def test_identity_verdict_requires_json_boolean(monkeypatch, tmp_path, field, value):
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"synthetic image")
    class Chat:
        def __init__(self, **kwargs):
            pass

        def with_model(self, *_args):
            return self

        async def send_message(self, _message):
            return json.dumps({field: value, "confidence": "high"})
    monkeypatch.setattr(identity, "LlmChat", Chat)
    monkeypatch.setattr(identity, "ImageContent", lambda **kw: SimpleNamespace(**kw))
    monkeypatch.setattr(identity, "UserMessage", lambda **kw: SimpleNamespace(**kw))
    if field == "match":
        result = await identity.verify_frame_identity("test", "test", [str(frame)], str(frame))
    elif field == "correct":
        result = await identity.verify_ring_placement("test", "test", [str(frame)], str(frame))
    else:
        result = await identity.verify_preview_summary("test", "test", [str(frame)], [], "visible pass")
    expected = (False if field == "describes_target" else "rejected") if value is False else (
        None if field == "describes_target" else "error")
    assert result == expected
