"""
Create / refresh two BRAND-NEW test accounts that the user can hand out for
demoing the latest build:

  • testfree-mar@elitescout.com   / Free@2026!   — fresh free preview, never used
  • testpremium-mar@elitescout.com / Premium@2026! — has 1 unlocked premium report (Lukas A. demo)

Re-running this script resets both accounts to their pristine demo state
(free preview not used, premium report unlocked + demo flag).

Usage:
  cd /app/backend && python make_demo_accounts.py
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Reuse the seed file's premium-report payloads + helpers.
sys.path.insert(0, str(Path(__file__).parent))
from seed_test_accounts import (  # noqa: E402
    PREVIEW,
    FULL_REPORT,
    hash_password,
    now_iso,
)

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

NEW_FREE = ("testfree-mar@elitescout.com", "Free@2026!", "Test Free Mar")
NEW_PREMIUM = ("testpremium-mar@elitescout.com", "Premium@2026!", "Test Premium Mar")


async def upsert(db, email, password, name, role="user"):
    existing = await db.users.find_one({"email": email.lower()})
    if existing:
        await db.users.update_one(
            {"email": email.lower()},
            {"$set": {
                "password_hash": hash_password(password),
                "full_name": name,
                "role": role,
            }},
        )
        # Wipe any past reports + payments so the free preview is fresh
        user_id = existing["id"]
        await db.reports.delete_many({"user_id": user_id})
        # Reset payment / preview flags
        await db.users.update_one(
            {"id": user_id},
            {"$unset": {"free_preview_used": "", "prepaid_uploads": ""}},
        )
        return user_id
    user_id = str(uuid.uuid4())
    await db.users.insert_one({
        "id": user_id,
        "email": email.lower(),
        "password_hash": hash_password(password),
        "full_name": name,
        "role": role,
        "created_at": now_iso(),
    })
    return user_id


async def seed_premium(db, user_id, email):
    await db.reports.delete_many({"user_id": user_id})
    rid = str(uuid.uuid4())
    await db.reports.insert_one({
        "id": rid,
        "user_id": user_id,
        "user_email": email.lower(),
        "player_details": {
            "player_name": "Lukas A.",
            "age": 14,
            "position": "Attacking Midfielder",
            "preferred_foot": "left",
            "current_club": "IK Falken U15",
            "video_type": "match",
            "description": "I am number 10 in the white shirt, playing as an attacking midfielder.",
        },
        "video_filename": "demo-sample.mp4",
        "video_size_bytes": 0,
        "preview": PREVIEW,
        "full_report": FULL_REPORT,
        "is_paid": True,
        "manually_unlocked": True,
        "demo": True,
        "created_at": now_iso(),
        "paid_at": now_iso(),
    })
    return rid


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    free_id = await upsert(db, *NEW_FREE)
    premium_id = await upsert(db, *NEW_PREMIUM)
    rid = await seed_premium(db, premium_id, NEW_PREMIUM[0])

    print("\n=== FRESH DEMO ACCOUNTS READY ===\n")
    print(f"FREE     : {NEW_FREE[0]} / {NEW_FREE[1]}")
    print("           → free preview NOT used, NO reports yet")
    print("           → upload now to experience Hero Teaser must-buy reveal\n")
    print(f"PREMIUM  : {NEW_PREMIUM[0]} / {NEW_PREMIUM[1]}")
    print(f"           → 1 unlocked premium demo report: {rid}")
    print("           → dashboard shows the full 'Lukas A.' premium report\n")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
