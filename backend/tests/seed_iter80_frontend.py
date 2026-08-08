"""Persistent seed for iter80 frontend premium report test.
Creates user + unlocked report. Prints EMAIL / PW / TOKEN / REPORT_ID.
Cleaned up by delete_iter80_seed.py."""
import asyncio, os, uuid, sys
from datetime import datetime, timezone
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"] if os.environ.get("REACT_APP_BACKEND_URL") else "https://scout-ai-pro-1.preview.emergentagent.com"
EMAIL = f"smtest.iter80.fe_{uuid.uuid4().hex[:6]}@example.com"
PW = "Test@2026!Iter80FE"

async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # Direct DB insert (avoid signup rate limit)
    import bcrypt
    pw_hash = bcrypt.hashpw(PW.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    uid = str(uuid.uuid4())
    await db.users.insert_one({
        "id": uid, "email": EMAIL.lower(), "password_hash": pw_hash,
        "full_name": "Iter80 FE", "role": "user",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    # Login to get token
    r = requests.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PW})
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")

    now = datetime.now(timezone.utc).isoformat()
    rid = str(uuid.uuid4())
    full = {
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
            {"timestamp": "00:58", "title": "Shot on target", "description": "Curled effort.", "action_type": "shot", "rating": 7, "outcome": "neutral", "tracking_verified": True, "identity_confidence": "high"},
            {"timestamp": "01:32", "title": "Scan then switch", "description": "Diagonal switch.", "action_type": "pass", "rating": 8, "outcome": "positive", "tracking_verified": True, "identity_confidence": "high"},
            {"timestamp": "02:40", "title": "Weak-foot slip", "description": "Left-foot control failed.", "action_type": "first_touch", "rating": 4, "outcome": "negative", "tracking_verified": True, "identity_confidence": "high"},
        ],
        "video_comments": [
            {"timestamp": "00:15", "frame_url": "/api/uploads/demo-frame-dribble.jpg", "identity_verified": True, "comment": "Wing burst"},
        ],
        "technical": {"dribbling": {"score": 8.2, "notes": "Excellent balance", "confidence": "high", "tier_for_age": "pro_academy", "evidence": [{"timestamp": "00:15"}]}},
        "match_stats": {"total_actions": 40, "successful_dribbles": 6, "key_passes": 3, "shots": 2, "duels_won": "5/8", "minutes_analysed": 20},
    }
    report = {
        "id": rid, "user_id": uid, "created_at": now,
        "is_paid": True, "manually_unlocked": False, "unlocked": True,
        "demo": False, "status": "completed",
        "player_details": {"player_name": "Test Player", "position": "Winger", "age": 12, "foot": "Right", "club": "TestFC"},
        "poster_url": "/api/uploads/demo-frame-dribble.jpg",
        "full_report": full,
        "identity_stats": {"checked": 5, "verified": 4},
    }
    await db.reports.insert_one(report)

    with open("/tmp/iter80_fe_seed.txt", "w") as f:
        f.write(f"{EMAIL}\n{PW}\n{tok}\n{uid}\n{rid}\n")
    print(f"EMAIL={EMAIL}\nPW={PW}\nTOKEN={tok}\nUID={uid}\nRID={rid}")

if __name__ == "__main__":
    asyncio.run(main())
