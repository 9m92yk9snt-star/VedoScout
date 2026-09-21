"""
Shared pytest fixtures + auto-loaded environment for the backend test suite.
Ensures `MONGO_URL` and `DB_NAME` are populated from /app/backend/.env so the
test suite is runnable with a bare `pytest` invocation.
"""
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load /app/backend/.env so tests that touch Mongo / settings work out of the box.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)


def pytest_collection_modifyitems(config, items):
    """Auto-mark every `async def test_*` with @pytest.mark.asyncio so the
    plugin actually schedules them on an event loop. Saves us from decorating
    every single test manually."""
    for item in items:
        if getattr(item, "obj", None) is not None:
            import inspect
            if inspect.iscoroutinefunction(item.obj):
                item.add_marker(pytest.mark.asyncio)
