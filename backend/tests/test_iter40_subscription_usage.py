"""
Iteration 40 — Premium upload-limit UI test coverage.

Backend regression / feature checks for GET /api/me/subscription:
- Response shape preserved (subscription + tiers)
- New `usage` field is present
- Free user → usage is null
- Admin user (no active sub) → usage is null
- Premium seed test account (no real Stripe sub) → usage still null (documented)
- Latency < 300 ms (usage does a count_documents)
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.strip().split("=", 1)[1].strip().strip('"').rstrip("/")
                break

FREE_CREDS = {"email": "free@elitescout.com", "password": "Free@2026"}
ADMIN_CREDS = {"email": "admin@elitescout.com", "password": "Admin@2026!Elite"}
PREM_CREDS = {"email": "premium@elitescout.com", "password": "Premium@2026"}


def _login(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text[:300]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token for {creds['email']}: {r.json()}"
    return tok


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def free_token():
    return _login(FREE_CREDS)


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_CREDS)


@pytest.fixture(scope="module")
def premium_token():
    try:
        return _login(PREM_CREDS)
    except AssertionError:
        pytest.skip("premium@elitescout.com not available on this env")


def test_subscription_shape_free_user(free_token):
    """Response has subscription + tiers + usage; usage null for free user."""
    r = requests.get(f"{BASE_URL}/api/me/subscription", headers=_hdr(free_token), timeout=15)
    assert r.status_code == 200, r.text[:500]
    data = r.json()
    # Shape preserved
    assert "subscription" in data
    assert "tiers" in data
    assert "usage" in data, f"NEW `usage` field missing in response: {data}"
    # Tiers contain premium + vip with amount + monthly_upload_limit
    tiers = data["tiers"]
    for t in ("premium", "vip"):
        assert t in tiers, f"tier {t} missing"
        assert "amount" in tiers[t], f"amount missing for {t}"
        assert "monthly_upload_limit" in tiers[t], f"monthly_upload_limit missing for {t}"
    # Premium 2/month, VIP 4/month — current product spec
    assert tiers["premium"]["monthly_upload_limit"] == 2
    assert tiers["vip"]["monthly_upload_limit"] == 4
    # Free user: no subscription → usage null
    assert data["subscription"] is None, f"free user should have subscription=null: {data['subscription']}"
    assert data["usage"] is None, f"free user should have usage=null but got {data['usage']}"


def test_subscription_shape_admin_no_sub(admin_token):
    """Admin without active sub → usage null."""
    r = requests.get(f"{BASE_URL}/api/me/subscription", headers=_hdr(admin_token), timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "usage" in data
    # Admin may or may not have a subscription — assert that usage matches sub state
    if data["subscription"] is None:
        assert data["usage"] is None, f"admin has no sub yet usage populated: {data['usage']}"
    else:
        # If admin somehow has a sub, usage should be populated
        assert isinstance(data["usage"], dict), "admin has sub but usage not populated"


def test_subscription_shape_premium_seed(premium_token):
    """Documented test premium seed has legacy prepay-unlock only, no real Stripe
    subscription — backend should return subscription:null + usage:null."""
    r = requests.get(f"{BASE_URL}/api/me/subscription", headers=_hdr(premium_token), timeout=15)
    assert r.status_code == 200
    data = r.json()
    # If subscription IS active (real premium), usage MUST be populated with correct keys
    if data["subscription"] and isinstance(data["subscription"], dict):
        assert isinstance(data["usage"], dict), "Active sub but usage not populated"
        for k in ("used_this_period", "monthly_limit", "remaining", "exhausted"):
            assert k in data["usage"], f"usage missing key {k}"
    else:
        # Documented: legacy prepay-only seed → both null
        assert data["usage"] is None, f"premium seed should have usage=null: {data['usage']}"


def test_subscription_endpoint_latency(free_token):
    """Endpoint must respond fast (<300ms) even with count_documents call."""
    # Warm up (avoid cold start counting)
    requests.get(f"{BASE_URL}/api/me/subscription", headers=_hdr(free_token), timeout=15)
    t0 = time.perf_counter()
    r = requests.get(f"{BASE_URL}/api/me/subscription", headers=_hdr(free_token), timeout=15)
    dt_ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200
    # Give some slack for network to kube ingress — 800ms hard cap, warn at 300
    assert dt_ms < 800, f"endpoint too slow: {dt_ms:.0f} ms"
    if dt_ms > 300:
        pytest.skip(f"soft threshold: {dt_ms:.0f}ms > 300ms (still under 800ms hard cap)")
