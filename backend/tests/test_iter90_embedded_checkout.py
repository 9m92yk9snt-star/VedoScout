"""
Iteration 90 — Embedded (in-page) branded Stripe checkout tests.

Covers:
  - POST /api/payments/guest/embedded  (single/premium/vip, invalid tier)
  - GET  /api/payments/guest/status/{session_id}  (embedded unpaid + 404)
  - POST /api/payments/embedded/subscribe  (auth required, invalid tier, admin)
  - POST /api/payments/embedded/prepay-upload  (regression + new amount/currency)

Cleans up any payment_transactions rows it inserts.
"""
import os
import time
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ORIGIN = BASE_URL

ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "elite_scout_db")

_created_session_ids: list[str] = []


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    # cleanup
    if _created_session_ids:
        c[DB_NAME].payment_transactions.delete_many({"session_id": {"$in": _created_session_ids}})
    c.close()


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- Guest embedded ----------
@pytest.mark.parametrize("tier,expected", [
    ("single", 129.0),
    ("premium", 29.99),
    ("vip", 49.99),
])
def test_guest_embedded_creates_session(tier, expected, mongo):
    r = requests.post(f"{API}/payments/guest/embedded",
                      json={"tier": tier, "origin_url": ORIGIN}, timeout=30)
    assert r.status_code == 200, f"{tier}: {r.status_code} {r.text}"
    data = r.json()
    assert "client_secret" in data and data["client_secret"].startswith("cs_"), data
    assert "session_id" in data and data["session_id"].startswith("cs_"), data
    assert data.get("currency") in ("usd", "USD", "eur", "EUR"), data
    # Amount should equal admin-configured price
    assert float(data["amount"]) == pytest.approx(expected, abs=0.01), f"{tier} amount={data['amount']} expected {expected}"
    _created_session_ids.append(data["session_id"])

    # DB row present
    doc = mongo.payment_transactions.find_one({"session_id": data["session_id"]})
    assert doc is not None
    expected_kind = "guest_subscription" if tier in ("premium", "vip") else "guest_single"
    assert doc["kind"] == expected_kind
    assert doc["ui_mode"] == "embedded"
    assert doc["tier"] == tier


def test_guest_embedded_invalid_tier():
    r = requests.post(f"{API}/payments/guest/embedded",
                      json={"tier": "platinum", "origin_url": ORIGIN}, timeout=30)
    assert r.status_code == 400, r.text


# ---------- Guest status ----------
def test_guest_status_embedded_unpaid():
    # Create fresh single embedded session
    r = requests.post(f"{API}/payments/guest/embedded",
                      json={"tier": "single", "origin_url": ORIGIN}, timeout=30)
    assert r.status_code == 200
    sid = r.json()["session_id"]
    _created_session_ids.append(sid)

    time.sleep(1)
    s = requests.get(f"{API}/payments/guest/status/{sid}", timeout=30)
    assert s.status_code == 200, f"{s.status_code} {s.text}"
    body = s.json()
    # embedded ui_mode single must be handled via _arm_real_stripe branch
    assert body.get("payment_status") in ("unpaid", "no_payment_required"), body
    assert body.get("status") in ("open", "complete"), body


def test_guest_status_unknown_404():
    r = requests.get(f"{API}/payments/guest/status/cs_test_does_not_exist_zzz", timeout=30)
    assert r.status_code == 404, r.text


# ---------- Logged-in subscribe ----------
def test_embedded_subscribe_no_auth():
    r = requests.post(f"{API}/payments/embedded/subscribe",
                      json={"tier": "premium", "origin_url": ORIGIN}, timeout=30)
    assert r.status_code in (401, 403), r.text


def test_embedded_subscribe_invalid_tier(admin_headers):
    r = requests.post(f"{API}/payments/embedded/subscribe",
                      json={"tier": "wat", "origin_url": ORIGIN},
                      headers=admin_headers, timeout=30)
    assert r.status_code == 400, r.text


def test_embedded_subscribe_admin_premium(admin_headers, mongo):
    r = requests.post(f"{API}/payments/embedded/subscribe",
                      json={"tier": "premium", "origin_url": ORIGIN},
                      headers=admin_headers, timeout=30)
    if r.status_code == 409:
        pytest.skip("Admin already has active subscription — 409 correctly returned.")
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    data = r.json()
    assert data["client_secret"].startswith("cs_")
    assert data["session_id"].startswith("cs_")
    assert float(data["amount"]) == pytest.approx(29.99, abs=0.01)
    _created_session_ids.append(data["session_id"])
    doc = mongo.payment_transactions.find_one({"session_id": data["session_id"]})
    assert doc and doc["kind"] == "subscription" and doc["ui_mode"] == "embedded" and doc["tier"] == "premium"


# ---------- Prepay upload regression + new fields ----------
def test_embedded_prepay_upload_regression(admin_headers, mongo):
    r = requests.post(f"{API}/payments/embedded/prepay-upload",
                      json={"origin_url": ORIGIN},
                      headers=admin_headers, timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    data = r.json()
    assert data["client_secret"].startswith("cs_")
    assert data["session_id"].startswith("cs_")
    # New fields
    assert "amount" in data and float(data["amount"]) > 0
    assert data.get("currency") in ("usd", "USD", "eur", "EUR")
    _created_session_ids.append(data["session_id"])
