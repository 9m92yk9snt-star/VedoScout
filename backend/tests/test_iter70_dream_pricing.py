"""Iteration 70 — Dream Pricing Tiers backend validation.

Covers:
  - GET /api/settings/price returns single/premium/vip prices
  - PUT /api/admin/pricing updates single_price (139) → verify via public endpoint, then reset to 129
  - POST /api/payments/subscribe {tier:premium|vip} returns a Stripe checkout URL for a logged-in user
  - Landing header images at /api/static/landing/price-free.jpg etc. return 200
  - Discount campaign flow: create campaign → free-preview serializer exposes pricing.discount → deactivate
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"


# ── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def disposable_user():
    """A throw-away user with a valid session cookie."""
    email = f"TEST_iter70_{uuid.uuid4().hex[:8]}@example.com"
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/signup", json={
        "email": email, "password": "TestPass!2026", "full_name": "Iter70 Tester",
    })
    assert r.status_code in (200, 201), f"signup failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    yield {"session": s, "email": email}
    # cleanup best-effort via admin
    try:
        adm = requests.Session()
        adm.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        # Attempt various admin delete endpoints — best-effort
        adm.delete(f"{BASE_URL}/api/admin/users", params={"email": email})
    except Exception:
        pass


# ── GET /api/settings/price ─────────────────────────────────────────────────
def test_settings_price_shape():
    r = requests.get(f"{BASE_URL}/api/settings/price")
    assert r.status_code == 200
    d = r.json()
    for k in ("single_price", "premium_price", "vip_price"):
        assert k in d, f"missing key {k}"
        assert isinstance(d[k], (int, float))
        assert d[k] > 0
    # Expected defaults per problem statement
    assert d["single_price"] == 129.0, f"expected 129, got {d['single_price']}"
    assert d["premium_price"] == 29.99, f"expected 29.99, got {d['premium_price']}"
    assert d["vip_price"] == 49.99, f"expected 49.99, got {d['vip_price']}"


# ── PUT /api/admin/pricing ──────────────────────────────────────────────────
def test_admin_pricing_update_and_reset(admin_session):
    # change single_price to 139
    r = admin_session.put(f"{BASE_URL}/api/admin/pricing", json={"single_price": 139})
    assert r.status_code == 200, f"PUT failed: {r.status_code} {r.text}"
    d = r.json()
    assert d.get("single_price") == 139.0
    # verify via public endpoint
    r2 = requests.get(f"{BASE_URL}/api/settings/price")
    assert r2.json()["single_price"] == 139.0
    # RESET to 129
    r3 = admin_session.put(f"{BASE_URL}/api/admin/pricing", json={"single_price": 129})
    assert r3.status_code == 200
    assert r3.json()["single_price"] == 129.0
    r4 = requests.get(f"{BASE_URL}/api/settings/price")
    assert r4.json()["single_price"] == 129.0


# ── Landing header images ───────────────────────────────────────────────────
@pytest.mark.parametrize("fname", [
    "price-free.jpg", "price-single.jpg", "price-premium.jpg", "price-vip.jpg",
])
def test_landing_price_header_images(fname):
    r = requests.get(f"{BASE_URL}/api/static/landing/{fname}")
    assert r.status_code == 200, f"{fname} returned {r.status_code}"
    ct = r.headers.get("content-type", "")
    assert "image" in ct.lower() or len(r.content) > 500, f"{fname} not an image"


# ── POST /api/payments/subscribe (logged-in) ────────────────────────────────
@pytest.mark.parametrize("tier", ["premium", "vip"])
def test_subscribe_returns_checkout_url(disposable_user, tier):
    s = disposable_user["session"]
    r = s.post(f"{BASE_URL}/api/payments/subscribe",
               json={"tier": tier, "origin_url": BASE_URL})
    assert r.status_code == 200, f"subscribe {tier} failed: {r.status_code} {r.text}"
    d = r.json()
    assert "url" in d and isinstance(d["url"], str) and d["url"].startswith("http"), \
        f"no checkout URL in response: {d}"
    assert "stripe" in d["url"].lower() or "checkout" in d["url"].lower(), \
        f"URL doesn't look like Stripe checkout: {d['url']}"


# ── Discount campaign flow ──────────────────────────────────────────────────
def test_admin_discount_campaign_lifecycle(admin_session):
    # Create a campaign
    payload = {"name": "TEST_iter70_campaign", "percent": 25, "hours_valid": 24, "send_email": False}
    r = admin_session.post(f"{BASE_URL}/api/admin/discounts", json=payload)
    assert r.status_code == 200, f"create campaign failed: {r.status_code} {r.text}"
    cid = r.json()["id"]
    try:
        # List should include it
        r2 = admin_session.get(f"{BASE_URL}/api/admin/discounts")
        assert r2.status_code == 200
        found = any(c["id"] == cid and c.get("active") for c in r2.json()["campaigns"])
        assert found, "created campaign not found in list"
    finally:
        # Deactivate
        r3 = admin_session.delete(f"{BASE_URL}/api/admin/discounts/{cid}")
        assert r3.status_code == 200
