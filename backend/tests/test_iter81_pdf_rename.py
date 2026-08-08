"""iter81 — verify PDF contains 'Scout's First Impression' and NOT 'Parent Summary'.

Seeds a disposable user + unlocked paid report, downloads the PDF, extracts text
with PyMuPDF fitz, then cleans up.
"""
import os
import sys
import uuid
import asyncio
from datetime import datetime, timezone

import pytest
import requests
import fitz  # PyMuPDF

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


def _load_base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    v = line.split("=", 1)[1].strip()
                    break
    return v.rstrip("/")


BASE = _load_base()
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

EMAIL = f"smtest.iter81.pdf_{uuid.uuid4().hex[:6]}@example.com"
PW = "Test@2026!Iter81"


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
    state = {"token": None, "user_id": None, "report_id": None}

    r = requests.post(f"{BASE}/api/auth/signup",
                      json={"email": EMAIL, "password": PW, "full_name": "Iter81 PDF"}, timeout=30)
    assert r.status_code in (200, 201), f"signup: {r.status_code} {r.text[:200]}"
    state["token"] = r.json().get("access_token") or r.json().get("token")

    async def _seed():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        u = await db.users.find_one({"email": EMAIL})
        state["user_id"] = u["id"]
        rid = str(uuid.uuid4())
        state["report_id"] = rid
        await db.reports.insert_one({
            "id": rid, "user_id": u["id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_paid": True, "manually_unlocked": False, "demo": False, "status": "completed",
            "player_details": {"player_name": "PDF Test Player", "position": "Winger", "age": 12, "foot": "Right", "club": "TestFC"},
            "poster_url": "/api/uploads/demo-frame-dribble.jpg",
            "full_report": _full_report_sample(),
        })
        client.close()

    asyncio.run(_seed())
    yield state

    async def _cleanup():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        if state["user_id"]:
            await db.reports.delete_many({"user_id": state["user_id"]})
            await db.users.delete_one({"id": state["user_id"]})
        client.close()

    asyncio.run(_cleanup())


def test_pdf_contains_scouts_first_impression_and_no_parent_summary(seeded):
    r = requests.get(
        f"{BASE}/api/reports/{seeded['report_id']}/pdf",
        headers={"Authorization": f"Bearer {seeded['token']}"},
        timeout=120,
    )
    assert r.status_code == 200, f"pdf download: {r.status_code} {r.text[:200]}"
    assert r.headers.get("content-type", "").startswith("application/pdf")
    pdf_bytes = r.content
    assert pdf_bytes[:4] == b"%PDF", "not a PDF"

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    all_text = "\n".join(p.get_text() for p in doc)
    doc.close()
    # save for debugging
    with open("/app/test_reports/pdf_iter81_text.txt", "w") as f:
        f.write(all_text)

    lower = all_text.lower()
    assert "scout" in lower and "first impression" in lower, \
        "'Scout's First Impression' not found in PDF text"
    assert "parent summary" not in lower, \
        "PDF still contains legacy 'Parent Summary' title"
