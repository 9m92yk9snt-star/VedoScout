"""Session 126 (iter56) seed helper.

Clones the existing admin report `0153da80-8192-4208-87ac-5e7f6d38eeb5` into
two temporary docs used by the frontend testing agent:

  - `TEST_ITER56_ADMIN_NOGEN`  → owned by admin, NO full_report, unpaid
                                 (used to verify auto-gen + premium branding)
  - `TEST_ITER56_FREE_LOCKED`  → owned by free user, unpaid, no full_report
                                 (used to verify LockedOverlay + PricingCards)

Idempotent: reruns delete + recreate. Provides a `--cleanup` flag that removes
both docs and exits.

Usage:
    python /app/backend/tests/seed_iter56.py           # seed
    python /app/backend/tests/seed_iter56.py --cleanup # cleanup
"""
import os
import sys
import copy
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

SOURCE_REPORT_ID = "0153da80-8192-4208-87ac-5e7f6d38eeb5"
ADMIN_CLONE_ID = "test-iter56-admin-nogen"
FREE_CLONE_ID = "test-iter56-free-locked"


def cleanup(db):
    r1 = db.reports.delete_many({"id": {"$in": [ADMIN_CLONE_ID, FREE_CLONE_ID]}})
    print(f"Cleanup: removed {r1.deleted_count} test clone(s)")


def seed(db):
    src = db.reports.find_one({"id": SOURCE_REPORT_ID})
    if not src:
        print(f"ERROR: source report {SOURCE_REPORT_ID} not found")
        sys.exit(1)
    admin = db.users.find_one({"email": "admin@elitescout.com"})
    free = db.users.find_one({"email": "free@elitescout.com"})
    if not admin or not free:
        print("ERROR: admin or free user not found")
        sys.exit(1)

    def clone(new_id, user):
        c = copy.deepcopy(src)
        c.pop("_id", None)
        c["id"] = new_id
        c["user_id"] = user["id"]
        c["user_email"] = user["email"]
        c["is_paid"] = False
        c["manually_unlocked"] = False
        c["full_report"] = None
        c.pop("full_report_status", None)
        c.pop("full_report_error", None)
        return c

    # Wipe any prior seed
    db.reports.delete_many({"id": {"$in": [ADMIN_CLONE_ID, FREE_CLONE_ID]}})

    admin_clone = clone(ADMIN_CLONE_ID, admin)
    free_clone = clone(FREE_CLONE_ID, free)
    db.reports.insert_many([admin_clone, free_clone])
    print(f"Seeded: {ADMIN_CLONE_ID} (admin), {FREE_CLONE_ID} (free)")


if __name__ == "__main__":
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    if "--cleanup" in sys.argv:
        cleanup(db)
    else:
        seed(db)
