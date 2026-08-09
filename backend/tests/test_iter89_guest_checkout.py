"""iter89 — Guest (logged-out) direct-to-Stripe checkout backend tests.

Covers:
- POST /api/payments/guest/checkout for single/premium/vip and invalid tier.
- GET /api/payments/guest/status/{session_id} for fresh unpaid and unknown session.
- Regression: logged-in /payments/subscribe still works.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASS = "Admin@2026!Elite"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# ---------- Guest checkout create ----------

def test_guest_checkout_single_returns_cs_test(s):
    r = s.post(f"{BASE_URL}/api/payments/guest/checkout",
               json={"tier": "single", "origin_url": BASE_URL})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "url" in data and "session_id" in data
    assert data["session_id"].startswith("cs_test"), f"Expected cs_test, got {data['session_id']}"
    # url should be a Stripe checkout URL
    assert "stripe.com" in data["url"]


def test_guest_checkout_premium_returns_cs_live(s):
    r = s.post(f"{BASE_URL}/api/payments/guest/checkout",
               json={"tier": "premium", "origin_url": BASE_URL})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["session_id"].startswith("cs_live"), f"Expected cs_live, got {data['session_id']}"
    assert "checkout.stripe.com" in data["url"]


def test_guest_checkout_vip_returns_cs_live(s):
    r = s.post(f"{BASE_URL}/api/payments/guest/checkout",
               json={"tier": "vip", "origin_url": BASE_URL})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["session_id"].startswith("cs_live"), f"Expected cs_live, got {data['session_id']}"
    assert "checkout.stripe.com" in data["url"]


def test_guest_checkout_invalid_tier_400(s):
    r = s.post(f"{BASE_URL}/api/payments/guest/checkout",
               json={"tier": "bogus", "origin_url": BASE_URL})
    assert r.status_code == 400


# ---------- Guest status ----------

def test_guest_status_unknown_session_404(s):
    r = s.get(f"{BASE_URL}/api/payments/guest/status/cs_test_nonexistent_xyz_{int(time.time())}")
    assert r.status_code == 404


def test_guest_status_fresh_single_is_unpaid(s):
    # create fresh single session
    r = s.post(f"{BASE_URL}/api/payments/guest/checkout",
               json={"tier": "single", "origin_url": BASE_URL})
    assert r.status_code == 200
    sid = r.json()["session_id"]

    r2 = s.get(f"{BASE_URL}/api/payments/guest/status/{sid}")
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data.get("payment_status") in ("unpaid", "open", None), data
    assert data.get("status") in ("open", "unpaid"), data
    assert data.get("kind") == "guest_single"


def test_guest_status_fresh_premium_is_unpaid(s):
    r = s.post(f"{BASE_URL}/api/payments/guest/checkout",
               json={"tier": "premium", "origin_url": BASE_URL})
    assert r.status_code == 200
    sid = r.json()["session_id"]

    r2 = s.get(f"{BASE_URL}/api/payments/guest/status/{sid}")
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data.get("payment_status") in ("unpaid", "open", None), data


# ---------- Regression: logged-in subscribe still works ----------

def test_login_admin_and_subscribe_endpoint_unchanged(s):
    lr = s.post(f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert lr.status_code == 200, lr.text
    token = lr.json().get("access_token")
    assert token
    headers = {"Authorization": f"Bearer {token}"}
    # /payments/subscribe (authenticated) — call with premium; should return a Stripe URL, no error
    sr = s.post(f"{BASE_URL}/api/payments/subscribe",
                json={"tier": "premium", "origin_url": BASE_URL},
                headers=headers)
    # Admin may already have subscription. Accept 200 with url OR a documented business error (4xx).
    assert sr.status_code in (200, 400, 409), sr.text
    if sr.status_code == 200:
        d = sr.json()
        assert "url" in d or "session_id" in d
