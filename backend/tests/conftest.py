"""
Shared pytest fixtures + auto-loaded environment for the backend test suite.
Ensures `MONGO_URL` and `DB_NAME` are populated from /app/backend/.env so the
test suite is runnable with a bare `pytest` invocation.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load /app/backend/.env so tests that touch Mongo / settings work out of the box.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)
