"""Iter 85 seed: temp user + 2 reports with feature_consent for admin featured-clips test.

Usage:
  python seed_iter85.py seed
  python seed_iter85.py withdraw     # set temp user consent to withdrawn
  python seed_iter85.py grant        # reset temp user consent to granted
  python seed_iter85.py clean        # delete temp user + reports
  python seed_iter85.py reset_admin  # reset admin@elitescout.com to withdrawn
"""
import os, sys, uuid, datetime, bcrypt
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

EMAIL = "smtest.iter85@example.com"
PASSWORD = "TestIter85!"
REPORT_FULL = "iter85-fc-full-report"
REPORT_PREVIEW = "iter85-fc-preview-report"
TEXT_VERSION = "2026-06-v1"


def _now():
    return datetime.datetime.utcnow().isoformat() + "Z"


def seed():
    hashed = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
    user_id = str(uuid.uuid4())
    now_iso = _now()
    DB.users.delete_many({"email": EMAIL})
    DB.users.insert_one({
        "id": user_id,
        "email": EMAIL,
        "password_hash": hashed,
        "full_name": "Iter85 Tester",
        "role": "free",
        "is_active": True,
        "email_verified": True,
        "created_at": now_iso,
        "feature_consent": {
            "status": "granted",
            "updated_at": now_iso,
            "text_version": TEXT_VERSION,
        },
    })
    DB.reports.delete_many({"id": {"$in": [REPORT_FULL, REPORT_PREVIEW]}})
    common = {
        "user_id": user_id,
        "user_email": EMAIL,
        "player_details": {"player_name": "Iter85 Player", "age": 13, "position": "Winger", "preferred_foot": "left"},
        "video_url_override": "/api/uploads/demo-player.jpg",
        "poster_url_override": "/api/uploads/demo-player.jpg",
        "marker_url_override": "/api/uploads/demo-player.jpg",
        "anchors": [{"i": i, "t": 6.0 + i * 4.0, "box": {"x": 0.5, "y": 0.5, "w": 0.03, "h": 0.08}} for i in range(1, 7)],
        "feature_consent": {"granted": True, "at": now_iso, "text_version": TEXT_VERSION},
        "created_at": now_iso,
    }
    # Full report doc (clip ready)
    DB.reports.insert_one({
        "_id": REPORT_FULL, "id": REPORT_FULL, **common,
        "full_report": {
            "scores": {"technical": 8.4, "tactical": 8.0, "physical": 7.9, "mentality": 8.2},
            "snapshot_moments": [{"t": 10.0, "label": "Great pass"}],
        },
        "analysis_status": "complete",
    })
    # Preview only (no full_report)
    DB.reports.insert_one({
        "_id": REPORT_PREVIEW, "id": REPORT_PREVIEW, **common,
        "preview": {"player_type": "Attacker", "brief_summary": "Preview only."},
        "analysis_status": "preview_ready",
    })
    print(f"SEEDED user_id={user_id} full={REPORT_FULL} preview={REPORT_PREVIEW}")


def withdraw():
    DB.users.update_one({"email": EMAIL}, {"$set": {"feature_consent": {"status": "withdrawn", "updated_at": _now(), "text_version": TEXT_VERSION}}})
    print("withdrawn")


def grant():
    DB.users.update_one({"email": EMAIL}, {"$set": {"feature_consent": {"status": "granted", "updated_at": _now(), "text_version": TEXT_VERSION}}})
    print("granted")


def clean():
    ur = DB.users.delete_many({"email": EMAIL})
    rr = DB.reports.delete_many({"id": {"$in": [REPORT_FULL, REPORT_PREVIEW]}})
    print(f"DELETED users={ur.deleted_count} reports={rr.deleted_count}")


def reset_admin():
    r = DB.users.update_one({"email": "admin@elitescout.com"}, {"$set": {"feature_consent": {"status": "withdrawn", "updated_at": _now(), "text_version": TEXT_VERSION}}})
    print(f"admin reset matched={r.matched_count}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "seed"
    {"seed": seed, "withdraw": withdraw, "grant": grant, "clean": clean, "reset_admin": reset_admin}[cmd]()
