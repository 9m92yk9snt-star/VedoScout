"""
Iteration 33 — Backend regression tests after removing $399 12-month
Progress Pass UI and adding the in-dashboard UpgradeBanner.

Validates:
  * GET /api/me/subscription returns null subscription + tiers for free user
  * GET /api/settings/price still returns pass_price (kept for backward compat)
  * POST /api/payments/subscribe still returns a Stripe checkout URL for premium+vip
  * Legacy /api/progress/pass/status still responds with active:false for free user
"""
import os
import pytest
import requests
from pathlib import Path


def _load_backend_url():
    if os.environ.get("REACT_APP_BACKEND_URL"):
        return os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
    env_path = Path("/app/frontend/.env")
    for line in env_path.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not configured")


BASE_URL = _load_backend_url()

FREE_USER = {"email": "testfree-mar@elitescout.com", "password": "Free@2026!"}
PREM_USER = {"email": "testpremium-mar@elitescout.com", "password": "Premium@2026!"}


def _login(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def free_token():
    return _login(FREE_USER)


@pytest.fixture(scope="module")
def prem_token():
    return _login(PREM_USER)


# ---------------- /api/me/subscription ----------------
class TestMeSubscription:
    def test_free_user_subscription_is_null(self, free_token):
        r = requests.get(
            f"{BASE_URL}/api/me/subscription",
            headers={"Authorization": f"Bearer {free_token}"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "subscription" in data
        assert data["subscription"] is None or data["subscription"] == {}
        assert "tiers" in data
        assert "premium" in data["tiers"]
        assert "vip" in data["tiers"]
        assert float(data["tiers"]["premium"]["amount"]) == 29.99
        assert float(data["tiers"]["vip"]["amount"]) == 49.99

    def test_prem_user_subscription_endpoint_ok(self, prem_token):
        r = requests.get(
            f"{BASE_URL}/api/me/subscription",
            headers={"Authorization": f"Bearer {prem_token}"},
            timeout=15,
        )
        assert r.status_code == 200
        assert "tiers" in r.json()


# ---------------- /api/settings/price (backward compat) ----------------
class TestSettingsPrice:
    def test_settings_price_keeps_pass_price(self):
        r = requests.get(f"{BASE_URL}/api/settings/price", timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "price" in data
        # pass_price kept for backward compat with old clients
        assert "pass_price" in data, f"pass_price missing → would break old clients: {data}"
        assert "currency" in data


# ---------------- /api/payments/subscribe ----------------
class TestSubscribe:
    @pytest.mark.parametrize("tier,amount", [("premium", 29.99), ("vip", 49.99)])
    def test_subscribe_returns_stripe_url(self, free_token, tier, amount):
        r = requests.post(
            f"{BASE_URL}/api/payments/subscribe",
            json={"tier": tier, "origin_url": "https://example.com"},
            headers={"Authorization": f"Bearer {free_token}"},
            timeout=30,
        )
        assert r.status_code == 200, f"subscribe failed for {tier}: {r.status_code} {r.text}"
        data = r.json()
        assert "url" in data, data
        assert "checkout.stripe.com" in data["url"], data["url"]
        # tier echo / amount might be present
        if "amount" in data:
            assert float(data["amount"]) == amount

    def test_subscribe_rejects_bad_tier(self, free_token):
        r = requests.post(
            f"{BASE_URL}/api/payments/subscribe",
            json={"tier": "ultra", "origin_url": "https://example.com"},
            headers={"Authorization": f"Bearer {free_token}"},
            timeout=15,
        )
        assert r.status_code in (400, 422), r.text


# ---------------- legacy progress-pass endpoints ----------------
class TestLegacyProgressPass:
    def test_pass_status_free_user(self, free_token):
        r = requests.get(
            f"{BASE_URL}/api/progress/pass/status",
            headers={"Authorization": f"Bearer {free_token}"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("active") is False
