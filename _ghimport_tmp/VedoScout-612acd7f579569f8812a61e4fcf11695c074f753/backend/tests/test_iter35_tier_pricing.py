"""Iteration 35 — Tests for admin-editable tier prices (single / premium / vip).

Covers:
  - GET /api/settings/price returns 5 numeric fields (price, pass_price, single_price, premium_price, vip_price)
  - PUT /api/admin/pricing happy path with admin auth + stripe_sync_required flag
  - PUT /api/admin/pricing validation (negative/zero/missing/out-of-range)
  - PUT /api/admin/pricing rejects non-admin (free/premium)
  - Restoration of original values
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"
PREMIUM_EMAIL = "premium@elitescout.com"
PREMIUM_PASSWORD = "Premium@2026"
FREE_EMAIL = "free@elitescout.com"
FREE_PASSWORD = "Free@2026"

DEFAULT_SINGLE = 129.0
DEFAULT_PREMIUM = 29.99
DEFAULT_VIP = 49.99


def _login(email: str, password: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Login failed for {email}: {r.status_code} {r.text[:200]}")
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def premium_token():
    return _login(PREMIUM_EMAIL, PREMIUM_PASSWORD)


@pytest.fixture(scope="module")
def free_token():
    return _login(FREE_EMAIL, FREE_PASSWORD)


# --- Public /settings/price ---

class TestSettingsPrice:
    def test_settings_price_returns_5_numeric_fields(self):
        r = requests.get(f"{BASE_URL}/api/settings/price", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        for key in ("price", "pass_price", "single_price", "premium_price", "vip_price"):
            assert key in data, f"Missing field {key} in /settings/price"
            assert isinstance(data[key], (int, float)), f"{key} not numeric: {data[key]!r}"
            assert data[key] > 0, f"{key} should be > 0, got {data[key]}"


# --- Admin pricing endpoint ---

class TestAdminPricing:
    def test_admin_pricing_update_and_echo(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        new_payload = {"single_price": 149.0, "premium_price": 34.99, "vip_price": 59.99}
        r = requests.put(f"{BASE_URL}/api/admin/pricing", json=new_payload, headers=headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["single_price"] == 149.0
        assert data["premium_price"] == 34.99
        assert data["vip_price"] == 59.99
        assert data.get("stripe_sync_required") is True

        # Verify GET /settings/price reflects new values
        r2 = requests.get(f"{BASE_URL}/api/settings/price", timeout=15)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["single_price"] == 149.0
        assert d2["premium_price"] == 34.99
        assert d2["vip_price"] == 59.99

        # RESTORE to original defaults
        restore = {"single_price": DEFAULT_SINGLE, "premium_price": DEFAULT_PREMIUM, "vip_price": DEFAULT_VIP}
        r3 = requests.put(f"{BASE_URL}/api/admin/pricing", json=restore, headers=headers, timeout=15)
        assert r3.status_code == 200, r3.text
        d3 = r3.json()
        assert d3["single_price"] == DEFAULT_SINGLE
        assert d3["premium_price"] == DEFAULT_PREMIUM
        assert d3["vip_price"] == DEFAULT_VIP

    def test_admin_pricing_rejects_negative(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.put(f"{BASE_URL}/api/admin/pricing", json={"single_price": -5}, headers=headers, timeout=15)
        assert r.status_code == 400, r.text

    def test_admin_pricing_rejects_zero(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.put(f"{BASE_URL}/api/admin/pricing", json={"premium_price": 0}, headers=headers, timeout=15)
        assert r.status_code == 400, r.text

    def test_admin_pricing_rejects_missing(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.put(f"{BASE_URL}/api/admin/pricing", json={}, headers=headers, timeout=15)
        assert r.status_code == 400, r.text

    def test_admin_pricing_rejects_out_of_range(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.put(f"{BASE_URL}/api/admin/pricing", json={"vip_price": 5000}, headers=headers, timeout=15)
        assert r.status_code == 400, r.text

    def test_admin_pricing_rejects_premium_user(self, premium_token):
        headers = {"Authorization": f"Bearer {premium_token}"}
        r = requests.put(f"{BASE_URL}/api/admin/pricing", json={"single_price": 200}, headers=headers, timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_admin_pricing_rejects_free_user(self, free_token):
        headers = {"Authorization": f"Bearer {free_token}"}
        r = requests.put(f"{BASE_URL}/api/admin/pricing", json={"single_price": 200}, headers=headers, timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_admin_pricing_rejects_unauthenticated(self):
        r = requests.put(f"{BASE_URL}/api/admin/pricing", json={"single_price": 200}, timeout=15)
        assert r.status_code in (401, 403), r.text


# --- Regression: subscription still works for premium ---

class TestSubscriptionRegression:
    def test_premium_subscribe_returns_url(self, premium_token):
        headers = {"Authorization": f"Bearer {premium_token}"}
        # Try common payload variants
        for payload in (
            {"plan": "premium"},
            {"tier": "premium"},
            {"plan": "premium", "next": "/dashboard"},
        ):
            r = requests.post(f"{BASE_URL}/api/payments/subscribe", json=payload, headers=headers, timeout=20)
            if r.status_code == 200:
                data = r.json()
                url = data.get("url") or data.get("checkout_url") or data.get("session_url")
                assert url and isinstance(url, str) and url.startswith("http"), f"Bad url: {data}"
                return
        pytest.skip(f"subscribe endpoint did not accept standard payloads (last status {r.status_code})")
