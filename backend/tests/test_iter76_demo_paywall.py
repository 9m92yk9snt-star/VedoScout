"""
Iteration 76 backend tests: public demo report, email log, preview paywall,
regression on /api/reports auth, conversion-sweep dry-run.
"""
import os
import sys
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback read from /app/frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    return r.json().get("access_token") or r.json().get("token")


# ---------- Public demo report ----------
def test_demo_report_public_no_auth():
    r = requests.get(f"{BASE_URL}/api/demo-report", timeout=15)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert "full_report" in data and isinstance(data["full_report"], dict)
    # sanity — should have scores/technical or similar keys
    fr = data["full_report"]
    assert len(fr.keys()) > 3


# ---------- Email log ----------
def test_email_log_requires_auth():
    r = requests.get(f"{BASE_URL}/api/admin/email-log", timeout=10)
    assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


def test_email_log_admin_returns_expected(admin_token):
    r = requests.get(f"{BASE_URL}/api/admin/email-log",
                     headers={"Authorization": f"Bearer {admin_token}"},
                     timeout=15)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert "items" in data and "total" in data and "opened" in data
    assert data["total"] >= 3, f"expected >=3 sent, got {data['total']}"
    assert data["opened"] >= 1, f"expected >=1 opened, got {data['opened']}"


def test_email_open_pixel_public():
    r = requests.get(f"{BASE_URL}/api/email/open/anything.png", timeout=10)
    assert r.status_code == 200
    assert "image" in r.headers.get("content-type", "").lower()


# ---------- Reports auth regression ----------
def test_reports_get_requires_auth():
    r = requests.get(f"{BASE_URL}/api/reports/does-not-exist", timeout=10)
    assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


# ---------- Conversion sweep dry-run ----------
def test_conversion_sweep_dry_run(admin_token):
    r = requests.post(
        f"{BASE_URL}/api/admin/conversion-sweep?dry_run=true",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    # must contain both keys per spec
    assert "results" in data, f"missing 'results': {list(data.keys())}"
    assert "activation" in data, f"missing 'activation': {list(data.keys())}"
    assert isinstance(data["results"], list)
    assert isinstance(data["activation"], list)


# ---------- Preview paywall (server must not leak full_report) ----------
@pytest.fixture(scope="module")
def paywall_user_and_report():
    """Signup a disposable @example.com user, insert a fresh report doc,
    cleanup after tests."""
    sys.path.insert(0, "/app/backend")
    from motor.motor_asyncio import AsyncIOMotorClient  # noqa
    import asyncio, datetime  # noqa

    email = f"paywalltest_{uuid.uuid4().hex[:6]}@example.com"
    password = "Test@2026!pw"
    r = requests.post(f"{BASE_URL}/api/auth/signup",
                      json={"email": email, "password": password,
                            "full_name": "Paywall Test"},
                      timeout=15)
    assert r.status_code in (200, 201), f"signup failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    token = body.get("access_token") or body.get("token")
    user = body.get("user") or {}
    user_id = user.get("id") or body.get("user_id") or body.get("id")

    # login to fetch user id if missing
    if not user_id:
        lr = requests.post(f"{BASE_URL}/api/auth/login",
                           json={"email": email, "password": password}, timeout=10)
        assert lr.status_code == 200
        lb = lr.json()
        token = lb.get("access_token") or token
        user_id = (lb.get("user") or {}).get("id") or lb.get("user_id")

    assert token and user_id, f"could not get token/user_id: token={bool(token)} uid={user_id}"

    # Insert report directly into Mongo
    from seed_demo_report import FULL_REPORT

    async def _seed():
        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME")
        client = AsyncIOMotorClient(mongo_url)
        db = client[db_name]
        rid = f"paywall-{uuid.uuid4().hex[:10]}"
        doc = {
            "id": rid,
            "user_id": user_id,
            "user_email": email,
            "is_paid": False,
            "analysis_status": "ready",
            "status": "complete",
            "created_at": datetime.datetime.utcnow(),
            "updated_at": datetime.datetime.utcnow(),
            "player_details": {"player_name": "Testspiller Paywall",
                               "age": "12", "position": "Winger"},
            "preview": {"teaser_score": 70, "headline": "x", "summary": "y"},
            "full_report": FULL_REPORT,
        }
        await db.reports.insert_one(doc)
        client.close()
        return rid

    report_id = asyncio.get_event_loop().run_until_complete(_seed())

    yield {"token": token, "email": email, "user_id": user_id, "report_id": report_id}

    # Cleanup
    async def _cleanup():
        client = AsyncIOMotorClient(os.environ.get("MONGO_URL"))
        db = client[os.environ.get("DB_NAME")]
        await db.reports.delete_one({"id": report_id})
        await db.users.delete_one({"id": user_id})
        await db.users.delete_one({"email": email})
        client.close()
    try:
        asyncio.get_event_loop().run_until_complete(_cleanup())
    except Exception as e:
        print(f"cleanup warning: {e}")


def test_report_no_full_leak_for_free_user(paywall_user_and_report):
    d = paywall_user_and_report
    r = requests.get(
        f"{BASE_URL}/api/reports/{d['report_id']}",
        headers={"Authorization": f"Bearer {d['token']}"},
        timeout=15,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    # is_paid False → server MUST NOT include full_report
    assert body.get("is_paid") in (False, None)
    assert "full_report" not in body or body.get("full_report") in (None, {}), \
        f"LEAK: free user got full_report in response! keys={list(body.keys())}"
