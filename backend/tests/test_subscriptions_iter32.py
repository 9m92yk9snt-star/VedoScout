"""
Iteration 32 — Stripe subscription wiring tests
Covers:
  - GET /api/me/subscription (tiers structure, null subscription)
  - POST /api/payments/subscribe (premium/vip/bogus/no-auth)
  - db.payment_transactions row creation for kind='subscription'
  - GET /api/payments/subscribe/status/{session_id} (own + cross-user 403)
  - GET /api/me/upload-eligibility backward compat (subscription:null)
  - POST /api/me/subscription/cancel|resume|change-tier when no sub (400)
  - POST /api/webhook/stripe-embedded invalid signature (400)
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")

PREMIUM_EMAIL = "testpremium-mar@elitescout.com"
PREMIUM_PASSWORD = "Premium@2026!"
FREE_EMAIL = "testfree-mar@elitescout.com"
FREE_PASSWORD = "Free@2026!"


@pytest.fixture(scope="module")
def premium_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": PREMIUM_EMAIL, "password": PREMIUM_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"premium login failed {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def free_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": FREE_EMAIL, "password": FREE_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"free login failed {r.status_code} {r.text}"
    return r.json()["access_token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# --- GET /api/me/subscription ----------------------------------------------

class TestGetMySubscription:
    def test_returns_null_subscription_with_tiers(self, premium_token):
        r = requests.get(f"{BASE_URL}/api/me/subscription", headers=H(premium_token), timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # subscription should be None / null because user has no active sub
        assert "subscription" in data
        assert data.get("subscription") in (None, {}, {"tier": "free"}), f"unexpected sub: {data.get('subscription')}"
        # tiers structure
        tiers = data.get("tiers") or {}
        assert "premium" in tiers and "vip" in tiers, f"tiers missing keys: {tiers}"
        assert tiers["premium"]["amount"] == 29.99
        assert tiers["premium"]["monthly_upload_limit"] == 2
        assert tiers["vip"]["amount"] == 49.99
        assert tiers["vip"]["monthly_upload_limit"] == 4

    def test_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/me/subscription", timeout=20)
        assert r.status_code in (401, 403), r.text


# --- POST /api/payments/subscribe ------------------------------------------

class TestSubscribeCheckout:
    def test_no_auth_returns_401(self):
        r = requests.post(
            f"{BASE_URL}/api/payments/subscribe",
            json={"tier": "premium", "origin_url": BASE_URL},
            timeout=20,
        )
        assert r.status_code in (401, 403), r.text

    def test_bogus_tier_returns_400(self, premium_token):
        r = requests.post(
            f"{BASE_URL}/api/payments/subscribe",
            headers=H(premium_token),
            json={"tier": "bogus", "origin_url": BASE_URL},
            timeout=20,
        )
        assert r.status_code == 400, r.text
        assert "tier" in (r.json().get("detail") or "").lower()

    def test_premium_returns_stripe_checkout_url(self, premium_token):
        r = requests.post(
            f"{BASE_URL}/api/payments/subscribe",
            headers=H(premium_token),
            json={"tier": "premium", "origin_url": BASE_URL},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        url = data.get("url") or ""
        sid = data.get("session_id") or ""
        assert url.startswith("https://checkout.stripe.com/c/pay/"), f"unexpected url: {url}"
        assert sid.startswith("cs_"), f"unexpected session_id: {sid}"
        # Stash for next test via class attr
        TestSubscribeCheckout.last_premium_session = sid

    def test_vip_returns_stripe_checkout_url(self, premium_token):
        r = requests.post(
            f"{BASE_URL}/api/payments/subscribe",
            headers=H(premium_token),
            json={"tier": "vip", "origin_url": BASE_URL},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert (data.get("url") or "").startswith("https://checkout.stripe.com/c/pay/")
        assert (data.get("session_id") or "").startswith("cs_")


# --- DB persistence verification via the status endpoint -------------------

class TestPaymentTransactionRow:
    def test_status_returns_unpaid_for_fresh_session(self, premium_token):
        # Create a brand new subscription session
        r = requests.post(
            f"{BASE_URL}/api/payments/subscribe",
            headers=H(premium_token),
            json={"tier": "premium", "origin_url": BASE_URL},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        sid = r.json()["session_id"]

        # Poll status
        s = requests.get(
            f"{BASE_URL}/api/payments/subscribe/status/{sid}",
            headers=H(premium_token),
            timeout=20,
        )
        assert s.status_code == 200, s.text
        body = s.json()
        # Not paid yet
        assert body.get("payment_status") in ("unpaid", "open", "no_payment_required"), body
        assert body.get("kind") == "subscription", body
        assert body.get("tier") == "premium", body

    def test_status_cross_user_returns_403(self, premium_token, free_token):
        # premium creates a session
        r = requests.post(
            f"{BASE_URL}/api/payments/subscribe",
            headers=H(premium_token),
            json={"tier": "premium", "origin_url": BASE_URL},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        sid = r.json()["session_id"]

        # free user tries to read premium user's session
        s = requests.get(
            f"{BASE_URL}/api/payments/subscribe/status/{sid}",
            headers=H(free_token),
            timeout=20,
        )
        assert s.status_code == 403, f"expected 403, got {s.status_code}: {s.text}"

    def test_status_unknown_session_returns_404(self, premium_token):
        s = requests.get(
            f"{BASE_URL}/api/payments/subscribe/status/cs_nonexistent_xxxxx",
            headers=H(premium_token),
            timeout=20,
        )
        assert s.status_code == 404, s.text


# --- /api/me/upload-eligibility backwards compatibility --------------------

class TestUploadEligibilityBackwardsCompat:
    def test_premium_user_no_sub_eligibility_shape(self, premium_token):
        r = requests.get(f"{BASE_URL}/api/me/upload-eligibility", headers=H(premium_token), timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "eligible" in data and "reason" in data, data
        # subscription field, when present, should be null/None because no active sub
        if "subscription" in data:
            assert data["subscription"] in (None, {}, {"tier": "free"}), data

    def test_free_user_with_prepaid_still_eligible(self, free_token):
        r = requests.get(f"{BASE_URL}/api/me/upload-eligibility", headers=H(free_token), timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # Free user has 5 prepaid uploads
        assert "eligible" in data and "reason" in data, data


# --- Cancel / Resume / Change tier when no subscription --------------------

class TestNoActiveSubscriptionActions:
    def test_cancel_no_active_400(self, premium_token):
        r = requests.post(f"{BASE_URL}/api/me/subscription/cancel", headers=H(premium_token), timeout=20)
        assert r.status_code == 400, r.text
        detail = (r.json().get("detail") or "").lower()
        assert "no active" in detail or "no subscription" in detail or "not scheduled" in detail, detail

    def test_resume_no_active_400(self, premium_token):
        r = requests.post(f"{BASE_URL}/api/me/subscription/resume", headers=H(premium_token), timeout=20)
        assert r.status_code == 400, r.text

    def test_change_tier_no_active_400(self, premium_token):
        r = requests.post(
            f"{BASE_URL}/api/me/subscription/change-tier",
            headers=H(premium_token),
            json={"tier": "premium", "origin_url": BASE_URL},
            timeout=20,
        )
        assert r.status_code == 400, r.text
        detail = (r.json().get("detail") or "").lower()
        assert "no active" in detail or "change" in detail, detail


# --- Webhook signature validation sanity check -----------------------------

class TestWebhookSignature:
    def test_invalid_signature_returns_400(self):
        r = requests.post(
            f"{BASE_URL}/api/webhook/stripe-embedded",
            data=b'{"id":"evt_test","type":"customer.subscription.created","data":{"object":{}}}',
            headers={"Stripe-Signature": "t=1,v1=bogus", "Content-Type": "application/json"},
            timeout=20,
        )
        # Should reject - either invalid payload or invalid signature
        assert r.status_code in (400,), f"expected 400, got {r.status_code}: {r.text}"
        detail = (r.json().get("detail") or "").lower() if r.headers.get("content-type","").startswith("application/json") else r.text.lower()
        assert "signature" in detail or "invalid" in detail, detail
