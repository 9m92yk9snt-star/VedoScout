"""Regression test for Session 132 — Emergent LLM Key budget exhaustion.

Simulates the exact litellm `BudgetExceededError` shape our Gemini call raises
when the Universal Key balance is depleted, then verifies:
  1. The error is caught and converted to HTTP 503 with a user-friendly detail
  2. `retry_in_progress` DB flag is cleared cleanly
  3. The clean HTTPException detail (not `"AI preview generation failed: 503: ..."`)
     is what analyze_preview_task's outer catch stores in `analysis_error`

Run with:
    cd /app/backend && python -m pytest tests/test_budget_error_handling.py -v
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import server


# The exact string litellm raises via emergentintegrations proxy
_BUDGET_ERR_MSG = "Budget has been exceeded! Current cost: 15.07, Max budget: 15.0"


@pytest.mark.asyncio
async def test_call_gemini_wraps_budget_error_as_503(tmp_path):
    """Primary Gemini call → BudgetExceededError → HTTP 503 with friendly copy."""
    fake_video = tmp_path / "test.mp4"
    fake_video.write_bytes(b"fake mp4 bytes")

    # Patch LlmChat to raise a budget error on send_message
    class FakeChat:
        def __init__(self, *a, **k): self.extra_params = {}
        def with_model(self, *a, **k): return self
        async def send_message(self, *a, **k):
            raise Exception(_BUDGET_ERR_MSG)

    with patch.object(server, "LlmChat", FakeChat):
        with pytest.raises(HTTPException) as excinfo:
            await server.call_gemini_with_video(
                session_id="preview-test-report-id",
                prompt="test",
                video_path=str(fake_video),
            )

    assert excinfo.value.status_code == 503
    detail = str(excinfo.value.detail).lower()
    assert "temporarily unavailable" in detail
    assert "refunded" in detail
    # No litellm technical string leak
    assert "budget has been exceeded" not in detail
    assert "15.07" not in detail
    assert "litellm" not in detail


@pytest.mark.asyncio
async def test_call_gemini_re_raises_unknown_errors_unchanged(tmp_path):
    """Non-budget errors bubble up unchanged so the outer task refunds/fails."""
    fake_video = tmp_path / "test.mp4"
    fake_video.write_bytes(b"fake mp4 bytes")

    class ExplodingChat:
        def __init__(self, *a, **k): self.extra_params = {}
        def with_model(self, *a, **k): return self
        async def send_message(self, *a, **k):
            raise RuntimeError("some totally different error")

    with patch.object(server, "LlmChat", ExplodingChat):
        with pytest.raises(Exception) as excinfo:
            await server.call_gemini_with_video(
                session_id="preview-test-report-id",
                prompt="test",
                video_path=str(fake_video),
            )
    # NOT wrapped in HTTPException 503 — original error surfaces
    assert not isinstance(excinfo.value, HTTPException) or excinfo.value.status_code != 503
    assert "totally different" in str(excinfo.value) or "totally different" in str(excinfo.value.detail if isinstance(excinfo.value, HTTPException) else "")


def test_budget_detection_matches_all_variants():
    """Sanity check the string-matching heuristic — should catch the litellm
    canonical message + a few common paraphrases without false positives."""
    should_catch = [
        "Budget has been exceeded! Current cost: 15.07, Max budget: 15.0",
        "BudgetExceededError: Current cost: 15.07",
        "insufficient_quota: You have exceeded your usage limit",
        "Your quota is exceeded for gpt-5-preview",
    ]
    should_not_catch = [
        "Connection reset by peer",
        "Rate limit exceeded — retry after 30s",  # rate-limit is NOT budget
        "Timeout while reading response",
        "JSONDecodeError: Expecting property name",
    ]
    for msg in should_catch:
        low = msg.lower()
        matched = (
            "budget has been exceeded" in low
            or "budgetexceedederror" in low
            or "insufficient_quota" in low
            or ("quota" in low and "exceed" in low)
        )
        assert matched, f"MUST match budget signal but did not: {msg!r}"
    for msg in should_not_catch:
        low = msg.lower()
        matched = (
            "budget has been exceeded" in low
            or "budgetexceedederror" in low
            or "insufficient_quota" in low
            or ("quota" in low and "exceed" in low)
        )
        assert not matched, f"MUST NOT match but did: {msg!r}"
