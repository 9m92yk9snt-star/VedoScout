"""Iter 84 seed: create temp user + free-preview report; cleanup at end.

Usage:
  python seed_iter84.py seed   # creates user + report, prints report_id
  python seed_iter84.py clean  # deletes them
"""
import os, sys, uuid, datetime, bcrypt
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

EMAIL = "smtest.iter84@example.com"
PASSWORD = "TestIter84!"
REPORT_ID = "iter84-fp-test-report"


def seed():
    # user
    hashed = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
    user_id = str(uuid.uuid4())
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"
    DB.users.delete_many({"email": EMAIL})
    DB.users.insert_one({
        "id": user_id,
        "email": EMAIL,
        "password_hash": hashed,
        "full_name": "Iter84 Tester",
        "role": "free",
        "is_active": True,
        "email_verified": True,
        "created_at": now_iso,
    })
    DB.reports.delete_many({"id": REPORT_ID})
    anchors = [
        {"i": i, "t": 6.18 + i * 4.0, "box": {"x": 0.5, "y": 0.5, "w": 0.03, "h": 0.08}}
        for i in range(1, 7)
    ]
    DB.reports.insert_one({
        "_id": REPORT_ID,
        "id": REPORT_ID,
        "user_id": user_id,
        "user_email": EMAIL,
        "player_details": {
            "player_name": "Iter84 Player",
            "age": 12,
            "position": "Midfielder",
            "preferred_foot": "right",
        },
        # Use override fields so backend resolves URL directly to a served demo asset
        "video_url_override": "/api/uploads/demo-player.jpg",
        "poster_url_override": "/api/uploads/demo-player.jpg",
        "marker_url_override": "/api/uploads/demo-player.jpg",
        "anchors": anchors,
        "preview": {
            "player_type": "Creative Midfielder",
            "brief_summary": "A promising young midfielder with excellent vision.",
            "top_strengths": [
                "Precise short passing under pressure",
                "Excellent field awareness and scanning",
                "Composed decision-making in tight spaces",
            ],
            "area_for_improvement": "Physical duels and aerial ability",
            "confidence": "high",
        },
        "teaser": {"overall_potential": 84},
        "full_report": {"scores": {"technical": 8.4, "tactical": 8.4, "physical": 8.4, "mentality": 8.4}},
        "is_paid": False,
        "manually_unlocked": False,
        "analysis_status": "preview_ready",
        "created_at": now_iso,
    })
    print(f"SEEDED user_id={user_id} report_id={REPORT_ID}")


def clean():
    ur = DB.users.delete_many({"email": EMAIL})
    rr = DB.reports.delete_many({"id": REPORT_ID})
    print(f"DELETED users={ur.deleted_count} reports={rr.deleted_count}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "seed"
    if cmd == "seed":
        seed()
    elif cmd == "clean":
        clean()
    else:
        print("usage: seed_iter84.py seed|clean")
