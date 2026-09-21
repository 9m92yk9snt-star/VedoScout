"""Seed disposable free user + LOCKED report for iter78 free-preview snapshots testing."""
import asyncio, os, uuid, sys
from datetime import datetime, timezone
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient
import requests

BASE = "https://scout-ai-pro-1.preview.emergentagent.com"
EMAIL = "smtest.iter78@example.com"
PW = "Test@2026!Iter78"

async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # Cleanup any pre-existing
    u = await db.users.find_one({"email": EMAIL})
    if u:
        await db.reports.delete_many({"user_id": u["id"]})
        await db.users.delete_one({"id": u["id"]})

    # Signup via API
    r = requests.post(f"{BASE}/api/auth/signup", json={"email": EMAIL, "password": PW, "full_name": "Iter78 Parent"})
    print("signup:", r.status_code, r.text[:200])
    assert r.status_code in (200, 201)
    tok = r.json().get("access_token") or r.json().get("token")
    user = await db.users.find_one({"email": EMAIL})
    uid = user["id"]

    now = datetime.now(timezone.utc).isoformat()
    rid = str(uuid.uuid4())
    locked_report = {
        "id": rid,
        "user_id": uid,
        "created_at": now,
        "unlocked": False,
        "demo": False,
        "status": "completed",
        "player_details": {"player_name": "Test Player", "position": "Winger", "age": 12, "foot": "Right", "club": "Test FC"},
        "poster_url": "/api/uploads/demo-frame-dribble.jpg",
        "marker_url": "/api/uploads/demo-frame-dribble.jpg",
        "anchors": [
            {"t": 15, "type": "dribble"}, {"t": 58, "type": "shot"}, {"t": 92, "type": "pass"},
            {"t": 120, "type": "duel"}, {"t": 160, "type": "run"},
        ],
        "preview": {
            "top_strengths": ["Explosive 1v1 dribbling", "Scanning before receiving", "Timing of runs"],
        },
        "teaser": {"overall_potential": 78},
        "score_meaning_teaser": {"locked_count": 24},
        "pricing": {"amount": 1900, "currency": "usd"},
        "full_report": {},
        "identity_stats": {"checked": 5, "verified": 4},
    }
    await db.reports.insert_one(locked_report)
    print(f"seeded locked report id={rid} for user_id={uid}")
    print(f"EMAIL={EMAIL}")
    print(f"PW={PW}")
    print(f"REPORT_ID={rid}")

    # Also seed an UNLOCKED (premium) real-report for premium testing
    rid2 = str(uuid.uuid4())
    full = {
        "player_type": "Winger",
        "scores": {"overall_development": 7.5},
        "overall_benchmark": {"tier": "strong_club", "tier_label": "Strong Club", "age_bracket_used": "U12"},
        "potential_assessment": {"development_potential": "High"},
        "scout_view": {"key_strengths": ["Dribbling on outside", "Composure with ball"], "development_priorities": ["Weak foot"]},
        "snapshot": {
            "biggest_strength": "Explosive dribbling down the wing",
            "biggest_development_area": "Weak-foot finishing under pressure",
            "hidden_talent": "Sharp pre-scan before receiving",
        },
        "action_timeline": [
            {"timestamp": "00:15", "title": "Wing burst past defender", "description": "Cuts inside on right, beats fullback with change of pace.", "action_type": "dribble", "rating": 8, "outcome": "positive", "tracking_verified": True, "identity_confidence": "high"},
            {"timestamp": "00:58", "title": "Shot on target", "description": "Curled effort from edge of box, saved low.", "action_type": "shot", "rating": 7, "outcome": "neutral", "tracking_verified": True, "identity_confidence": "high"},
            {"timestamp": "01:32", "title": "Scan then switch", "description": "Head-check before receiving; opens up play with a diagonal.", "action_type": "pass", "rating": 8, "outcome": "positive", "tracking_verified": True, "identity_confidence": "high"},
            {"timestamp": "02:40", "title": "Weak-foot slip", "description": "Left-foot control failed under pressure, gave possession back.", "action_type": "first_touch", "rating": 4, "outcome": "negative", "tracking_verified": True, "identity_confidence": "high"},
        ],
        "video_comments": [
            {"timestamp": "00:15", "frame_url": "/api/uploads/demo-frame-dribble.jpg", "identity_verified": True, "comment": "Wing burst"},
            {"timestamp": "01:32", "frame_url": "/api/uploads/demo-frame-scan.jpg", "identity_verified": True, "comment": "Scan"},
        ],
        "technical": {"dribbling": {"score": 8.2, "notes": "Excellent balance", "confidence": "high", "tier_for_age": "pro_academy", "evidence": [{"timestamp": "00:15"}]}},
        "match_stats": {"total_actions": 40, "successful_dribbles": 6, "key_passes": 3, "shots": 2, "duels_won": "5/8", "minutes_analysed": 20},
    }
    unlocked_report = {
        "id": rid2, "user_id": uid, "created_at": now, "unlocked": True, "demo": False, "status": "completed",
        "player_details": {"player_name": "Test Player", "position": "Winger", "age": 12, "foot": "Right", "club": "Test FC"},
        "poster_url": "/api/uploads/demo-frame-dribble.jpg",
        "full_report": full,
        "identity_stats": {"checked": 5, "verified": 4},
    }
    await db.reports.insert_one(unlocked_report)
    print(f"UNLOCKED_REPORT_ID={rid2}")

    with open("/tmp/iter78_ids.txt", "w") as f:
        f.write(f"{uid}\n{rid}\n{rid2}\n{tok}\n")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    asyncio.run(main())
