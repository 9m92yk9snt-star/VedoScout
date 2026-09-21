"""Iter80 — Snapshot Card sharing endpoints (public + auth).

Covers:
  - GET /api/demo-report/snapshot-card/{key}.png (public):
       200 image/png for {strength, noticed, hidden, develop}
       404 for unknown key
  - GET /api/reports/{id}/snapshot-card/{key}.png (auth):
       401/403 without token
       403 for another user's report
       402 for a locked (unpaid) report
       200 image/png for the owner of an unlocked report
       PNG magic bytes valid + reasonable size (>50KB)

Seeds disposable users + reports and cleans them up at the end.
"""
import os
import sys
import uuid
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")

# Load env for Mongo direct access (seed unlocked report with is_paid=True)
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/app/backend/.env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
import asyncio  # noqa: E402

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

SNAP_KEYS = ["strength", "noticed", "hidden", "develop"]

OWNER_EMAIL = f"smtest.iter80.owner_{uuid.uuid4().hex[:6]}@example.com"
OWNER_PW = "Test@2026!Iter80"
OTHER_EMAIL = f"smtest.iter80.other_{uuid.uuid4().hex[:6]}@example.com"
OTHER_PW = "Test@2026!Iter80"


def _full_report_sample():
    return {
        "player_type": "Winger",
        "scores": {"overall_development": 7.5},
        "overall_benchmark": {"tier": "strong_club", "tier_label": "Strong Club", "age_bracket_used": "U12"},
        "potential_assessment": {"development_potential": "High"},
        "scout_view": {"key_strengths": ["Dribbling", "Composure"], "development_priorities": ["Weak foot"]},
        "snapshot": {
            "biggest_strength": "Explosive dribbling down the wing",
            "biggest_development_area": "Weak-foot finishing under pressure",
            "hidden_talent": "Sharp pre-scan before receiving",
        },
        "action_timeline": [
            {"timestamp": "00:15", "title": "Wing burst", "description": "Cuts inside.", "action_type": "dribble", "rating": 8, "outcome": "positive", "tracking_verified": True, "identity_confidence": "high"},
        ],
        "video_comments": [
            {"timestamp": "00:15", "frame_url": "/api/uploads/demo-frame-dribble.jpg", "identity_verified": True, "comment": "Wing burst"},
        ],
        "technical": {"dribbling": {"score": 8.2, "notes": "Excellent", "confidence": "high", "tier_for_age": "pro_academy", "evidence": [{"timestamp": "00:15"}]}},
        "match_stats": {"total_actions": 40, "successful_dribbles": 6},
    }


@pytest.fixture(scope="module")
def seeded():
    """Create owner + other user, one locked + one unlocked report, return handles."""
    state = {
        "owner_token": None, "owner_id": None,
        "other_token": None, "other_id": None,
        "locked_id": None, "unlocked_id": None,
    }

    # Signup owner
    r = requests.post(f"{BASE_URL}/api/auth/signup", json={
        "email": OWNER_EMAIL, "password": OWNER_PW, "full_name": "Iter80 Owner"
    })
    assert r.status_code in (200, 201), f"owner signup: {r.status_code} {r.text[:200]}"
    state["owner_token"] = r.json().get("access_token") or r.json().get("token")

    # Signup other
    r = requests.post(f"{BASE_URL}/api/auth/signup", json={
        "email": OTHER_EMAIL, "password": OTHER_PW, "full_name": "Iter80 Other"
    })
    assert r.status_code in (200, 201), f"other signup: {r.status_code} {r.text[:200]}"
    state["other_token"] = r.json().get("access_token") or r.json().get("token")

    async def _seed():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        owner = await db.users.find_one({"email": OWNER_EMAIL})
        other = await db.users.find_one({"email": OTHER_EMAIL})
        state["owner_id"] = owner["id"]
        state["other_id"] = other["id"]

        now = datetime.now(timezone.utc).isoformat()
        # LOCKED report (unpaid)
        locked_id = str(uuid.uuid4())
        locked = {
            "id": locked_id, "user_id": owner["id"], "created_at": now,
            "is_paid": False, "manually_unlocked": False, "demo": False, "status": "completed",
            "player_details": {"player_name": "Locked Player", "position": "Winger", "age": 12, "foot": "Right", "club": "TestFC"},
            "poster_url": "/api/uploads/demo-frame-dribble.jpg",
            "full_report": _full_report_sample(),
        }
        # UNLOCKED report (paid)
        unlocked_id = str(uuid.uuid4())
        unlocked = {
            "id": unlocked_id, "user_id": owner["id"], "created_at": now,
            "is_paid": True, "manually_unlocked": False, "demo": False, "status": "completed",
            "player_details": {"player_name": "Unlocked Player", "position": "Winger", "age": 12, "foot": "Right", "club": "TestFC"},
            "poster_url": "/api/uploads/demo-frame-dribble.jpg",
            "full_report": _full_report_sample(),
        }
        await db.reports.insert_many([locked, unlocked])
        state["locked_id"] = locked_id
        state["unlocked_id"] = unlocked_id
        client.close()

    asyncio.run(_seed())
    yield state

    # Cleanup
    async def _cleanup():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        for uid_key in ("owner_id", "other_id"):
            uid = state.get(uid_key)
            if uid:
                await db.reports.delete_many({"user_id": uid})
                await db.users.delete_one({"id": uid})
        client.close()

    asyncio.run(_cleanup())


# --------- Public demo endpoint ---------
class TestDemoSnapshotCard:
    @pytest.mark.parametrize("key", SNAP_KEYS)
    def test_demo_valid_keys_return_png(self, key):
        r = requests.get(f"{BASE_URL}/api/demo-report/snapshot-card/{key}.png", timeout=30)
        assert r.status_code == 200, f"{key}: {r.status_code} {r.text[:200]}"
        assert r.headers.get("content-type", "").startswith("image/png")
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n", f"{key}: bad PNG magic bytes"
        assert len(r.content) > 50 * 1024, f"{key}: PNG too small ({len(r.content)} bytes)"

    def test_demo_invalid_key_404(self):
        r = requests.get(f"{BASE_URL}/api/demo-report/snapshot-card/hack.png", timeout=15)
        assert r.status_code == 404


# --------- Authenticated report endpoint ---------
class TestReportSnapshotCardAuth:
    def test_no_token_returns_401_or_403(self, seeded):
        r = requests.get(f"{BASE_URL}/api/reports/{seeded['unlocked_id']}/snapshot-card/strength.png", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_other_user_forbidden_403(self, seeded):
        r = requests.get(
            f"{BASE_URL}/api/reports/{seeded['unlocked_id']}/snapshot-card/strength.png",
            headers={"Authorization": f"Bearer {seeded['other_token']}"}, timeout=15,
        )
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"

    def test_locked_report_402(self, seeded):
        r = requests.get(
            f"{BASE_URL}/api/reports/{seeded['locked_id']}/snapshot-card/strength.png",
            headers={"Authorization": f"Bearer {seeded['owner_token']}"}, timeout=15,
        )
        assert r.status_code == 402, f"expected 402, got {r.status_code} {r.text[:200]}"

    def test_owner_unlocked_bad_key_404(self, seeded):
        r = requests.get(
            f"{BASE_URL}/api/reports/{seeded['unlocked_id']}/snapshot-card/hack.png",
            headers={"Authorization": f"Bearer {seeded['owner_token']}"}, timeout=15,
        )
        assert r.status_code == 404

    @pytest.mark.parametrize("key", SNAP_KEYS)
    def test_owner_unlocked_returns_png(self, seeded, key):
        r = requests.get(
            f"{BASE_URL}/api/reports/{seeded['unlocked_id']}/snapshot-card/{key}.png",
            headers={"Authorization": f"Bearer {seeded['owner_token']}"}, timeout=45,
        )
        assert r.status_code == 200, f"{key}: {r.status_code} {r.text[:200]}"
        assert r.headers.get("content-type", "").startswith("image/png")
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
        # Seeded reports have minimal content -> smaller PNGs than demo. Just sanity-check size.
        assert len(r.content) > 20 * 1024, f"{key}: PNG too small ({len(r.content)} bytes)"
