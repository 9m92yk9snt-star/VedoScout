"""
Iteration 64 - Test payment/access bug fixes:
  - Free user cannot see full_report content without paying (owner)
  - Admin sees full_report (admin bypass kept)
  - generate-full returns 402 for free owner of unpaid report
  - GET /api/admin/users segments: premium (paid txn), granted (prepaid/unlocked but no paid txn), free
  - DELETE /api/admin/payments/{id}: works for admin, 404 unknown, 401/403 without admin
"""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "elite_scout_db")

ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PWD = "Admin@2026!Elite"
FREE_EMAIL = "free@elitescout.com"
FREE_PWD = "Free@2026"

TAG = "iter64-test"


@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    # cleanup all iter64-test tagged docs
    for coll in ["reports", "payment_transactions", "users"]:
        client[DB_NAME][coll].delete_many({"user_email": {"$regex": TAG}})
        client[DB_NAME][coll].delete_many({"email": {"$regex": TAG}})
    client[DB_NAME]["payment_transactions"].delete_many({"metadata.tag": TAG})
    client[DB_NAME]["reports"].delete_many({"_iter64_tag": TAG})
    client.close()


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text[:200]}"
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PWD)


@pytest.fixture(scope="module")
def free_token():
    return _login(FREE_EMAIL, FREE_PWD)


@pytest.fixture(scope="module")
def unpaid_report_with_full(db):
    """Insert a synthetic report owned by free user, unpaid, with full_report content.
    Clones a real ready report to ensure all required fields are present."""
    rid = str(uuid.uuid4())
    free_user = db["users"].find_one({"email": FREE_EMAIL}, {"id": 1})
    assert free_user, "free user not found"
    template = db["reports"].find_one({"analysis_status": "ready", "full_report": {"$ne": None}})
    assert template, "no template ready report available"
    doc = dict(template)
    doc.pop("_id", None)
    doc["id"] = rid
    doc["user_id"] = free_user["id"]
    doc["user_email"] = FREE_EMAIL
    doc["is_paid"] = False
    doc["manually_unlocked"] = False
    doc["paid_at"] = None
    doc["full_report"] = {"summary": "SECRET_FULL_REPORT_CONTENT_iter64", "score": 88,
                          "executive_summary": "SECRET_FULL_REPORT_CONTENT_iter64 exec"}
    doc["_iter64_tag"] = TAG
    db["reports"].insert_one(doc)
    yield rid
    db["reports"].delete_one({"id": rid})


class TestReportAccess:
    def test_admin_login(self, admin_token):
        assert admin_token

    def test_owner_cannot_see_full_report_content(self, free_token, unpaid_report_with_full):
        r = requests.get(f"{API}/reports/{unpaid_report_with_full}",
                         headers={"Authorization": f"Bearer {free_token}"}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        body = r.text
        # secret full_report content must NOT leak
        assert "SECRET_FULL_REPORT_CONTENT_iter64" not in body, \
            f"LEAK: unpaid owner received full_report content! body={body[:500]}"

    def test_admin_can_see_full_report_content(self, admin_token, unpaid_report_with_full):
        r = requests.get(f"{API}/reports/{unpaid_report_with_full}",
                         headers={"Authorization": f"Bearer {admin_token}"}, timeout=15)
        assert r.status_code == 200
        # admin bypass kept intentionally
        assert "SECRET_FULL_REPORT_CONTENT_iter64" in r.text, \
            "Admin should still see full_report (admin bypass kept)"

    def test_generate_full_402_for_free_owner(self, free_token, unpaid_report_with_full):
        r = requests.post(f"{API}/reports/{unpaid_report_with_full}/generate-full",
                          headers={"Authorization": f"Bearer {free_token}"}, timeout=20)
        assert r.status_code == 402, f"expected 402 Payment Required, got {r.status_code}: {r.text[:300]}"


class TestAdminUserSegments:
    def test_get_admin_users_ok(self, admin_token):
        r = requests.get(f"{API}/admin/users", headers={"Authorization": f"Bearer {admin_token}"}, timeout=20)
        assert r.status_code == 200
        data = r.json()
        # accept either list or {users: [...]}
        users = data if isinstance(data, list) else data.get("users") or data.get("items") or []
        assert isinstance(users, list) and len(users) > 0
        # store on module-level attribute
        TestAdminUserSegments._users = users

    def test_free_email_segment_premium(self, admin_token):
        users = getattr(TestAdminUserSegments, "_users", [])
        free = next((u for u in users if u.get("email") == FREE_EMAIL), None)
        assert free is not None, "free@elitescout.com not found in admin/users"
        seg = free.get("segment") or free.get("tier") or free.get("plan")
        # Per spec: free@elitescout.com has a paid txn so segments as 'premium'
        assert seg == "premium", f"expected free@elitescout.com to be segment=premium, got {seg} (fields: {list(free.keys())})"

    def test_admin_email_segment_admin(self, admin_token):
        users = getattr(TestAdminUserSegments, "_users", [])
        adm = next((u for u in users if u.get("email") == ADMIN_EMAIL), None)
        assert adm is not None
        seg = adm.get("segment") or adm.get("tier") or adm.get("plan")
        assert seg == "admin", f"expected admin segment, got {seg}"

    def test_granted_segment_exists_or_reachable(self, admin_token, db):
        """Insert a synthetic user with prepaid_uploads>0 but no paid txn and expect 'granted'."""
        gemail = f"{TAG}-granted@elitescout.com"
        db["users"].delete_many({"email": gemail})
        db["users"].insert_one({
            "id": str(uuid.uuid4()),
            "email": gemail,
            "name": "Iter64 Granted",
            "role": "user",
            "prepaid_uploads": 3,
            "subscription": {"tier": "free"},
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        r = requests.get(f"{API}/admin/users", headers={"Authorization": f"Bearer {admin_token}"}, timeout=20)
        assert r.status_code == 200
        data = r.json()
        users = data if isinstance(data, list) else data.get("users") or []
        u = next((x for x in users if x.get("email") == gemail), None)
        assert u is not None, f"synthetic granted user not returned"
        seg = u.get("segment") or u.get("tier") or u.get("plan")
        assert seg == "granted", f"expected granted, got {seg} (user={u})"


class TestAdminPaymentDelete:
    def test_delete_payment_flow(self, admin_token, db):
        txn_id = str(uuid.uuid4())
        db["payment_transactions"].insert_one({
            "id": txn_id,
            "user_email": f"{TAG}-payer@elitescout.com",
            "amount": 1.0,
            "currency": "usd",
            "payment_status": "initiated",
            "metadata": {"tag": TAG},
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        # delete as admin
        r = requests.delete(f"{API}/admin/payments/{txn_id}",
                            headers={"Authorization": f"Bearer {admin_token}"}, timeout=15)
        assert r.status_code == 200, f"expected 200 delete, got {r.status_code}: {r.text[:200]}"
        # verify gone
        assert db["payment_transactions"].find_one({"id": txn_id}) is None

    def test_delete_payment_unknown_404(self, admin_token):
        r = requests.delete(f"{API}/admin/payments/does-not-exist-{uuid.uuid4()}",
                            headers={"Authorization": f"Bearer {admin_token}"}, timeout=15)
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"

    def test_delete_payment_no_admin_forbidden(self, free_token, db):
        txn_id = str(uuid.uuid4())
        db["payment_transactions"].insert_one({
            "id": txn_id,
            "user_email": f"{TAG}-payer2@elitescout.com",
            "amount": 1.0,
            "currency": "usd",
            "payment_status": "initiated",
            "metadata": {"tag": TAG},
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        r = requests.delete(f"{API}/admin/payments/{txn_id}",
                            headers={"Authorization": f"Bearer {free_token}"}, timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"
        # cleanup
        db["payment_transactions"].delete_one({"id": txn_id})


class TestAdminEndpointsSmoke:
    def test_admin_reports_200(self, admin_token):
        r = requests.get(f"{API}/admin/reports",
                         headers={"Authorization": f"Bearer {admin_token}"}, timeout=20)
        assert r.status_code == 200

    def test_admin_payments_200(self, admin_token):
        r = requests.get(f"{API}/admin/payments",
                         headers={"Authorization": f"Bearer {admin_token}"}, timeout=20)
        assert r.status_code == 200
