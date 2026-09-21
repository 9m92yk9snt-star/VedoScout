"""
ScoutMePlay backend tests — focused on:
  • USD currency conversion (price + admin stats)
  • Admin dynamic price editing
  • Legacy redirect-style Stripe endpoints (prepay-upload, checkout) under sk_test_emergent
  • NEW embedded-Stripe endpoints — must gracefully 503 while real keys are unset
  • Webhook still exists & rejects unsigned POST
  • Auth still works for admin / free / premium
  • Upload eligibility for FREE user
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL, ADMIN_PASSWORD = "admin@elitescout.com", "Admin@2026!Elite"
FREE_EMAIL, FREE_PASSWORD = "free@elitescout.com", "Free@2026"
PREMIUM_EMAIL, PREMIUM_PASSWORD = "premium@elitescout.com", "Premium@2026"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:300]}"
    return r.json()["access_token"], r.json()["user"]


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------------- Fixtures ----------------
@pytest.fixture(scope="session")
def admin_token():
    tok, u = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert u["role"] == "admin"
    return tok


@pytest.fixture(scope="session")
def free_token():
    tok, _ = _login(FREE_EMAIL, FREE_PASSWORD)
    return tok


@pytest.fixture(scope="session")
def premium_token():
    tok, _ = _login(PREMIUM_EMAIL, PREMIUM_PASSWORD)
    return tok


# ---------------- AUTH ----------------
class TestAuth:
    def test_admin_login(self, admin_token):
        assert admin_token

    def test_free_login(self, free_token):
        assert free_token

    def test_premium_login(self, premium_token):
        assert premium_token


# ---------------- PRICE (USD) ----------------
class TestPriceUSD:
    def test_public_price_default_usd(self):
        r = requests.get(f"{API}/settings/price", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        # New USD shape
        assert d.get("currency") == "usd", d
        assert d.get("price") == 1.0, d
        # Backward-compat alias still present
        assert d.get("price_dkk") == 1.0, d

    def test_admin_update_price_then_restore(self, admin_token):
        # Bump to 5.0
        r = requests.put(f"{API}/admin/price", headers=_auth(admin_token),
                         json={"price": 5.0}, timeout=20)
        assert r.status_code == 200, r.text
        # Verify reflected
        r2 = requests.get(f"{API}/settings/price", timeout=20)
        assert r2.json()["price"] == 5.0
        assert r2.json()["price_dkk"] == 5.0  # alias mirrors USD value
        assert r2.json()["currency"] == "usd"
        # Restore to 1.0
        r3 = requests.put(f"{API}/admin/price", headers=_auth(admin_token),
                          json={"price": 1.0}, timeout=20)
        assert r3.status_code == 200
        assert requests.get(f"{API}/settings/price").json()["price"] == 1.0

    def test_admin_update_price_legacy_payload_key(self, admin_token):
        """Older clients may still POST `price_dkk` — server should accept it."""
        r = requests.put(f"{API}/admin/price", headers=_auth(admin_token),
                         json={"price_dkk": 2.0}, timeout=20)
        assert r.status_code == 200, r.text
        # Restore
        requests.put(f"{API}/admin/price", headers=_auth(admin_token),
                     json={"price": 1.0}, timeout=20)

    def test_admin_update_price_forbidden_for_user(self, free_token):
        r = requests.put(f"{API}/admin/price", headers=_auth(free_token),
                         json={"price": 9.0}, timeout=20)
        assert r.status_code == 403


# ---------------- ADMIN STATS ----------------
class TestAdminStats:
    def test_admin_stats_usd(self, admin_token):
        r = requests.get(f"{API}/admin/stats", headers=_auth(admin_token), timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("total_users", "total_uploads", "total_paid_reports",
                  "revenue_usd", "revenue_dkk", "currency"):
            assert k in d, f"missing key {k} in {d}"
        assert d["currency"] == "USD"
        assert isinstance(d["revenue_usd"], (int, float))
        assert isinstance(d["revenue_dkk"], (int, float))  # legacy alias

    def test_admin_stats_forbidden_for_free_user(self, free_token):
        r = requests.get(f"{API}/admin/stats", headers=_auth(free_token), timeout=20)
        assert r.status_code == 403


# ---------------- /config/stripe (PUBLIC) ----------------
class TestStripeConfig:
    def test_stripe_config_public_no_auth(self):
        r = requests.get(f"{API}/config/stripe", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "publishable_key" in d
        assert "embedded_available" in d
        # Keys intentionally empty in .env right now
        assert d["publishable_key"] == ""
        assert d["embedded_available"] is False


# ---------------- EMBEDDED CHECKOUT — must 503 ----------------
class TestEmbeddedCheckoutGracefulDisabled:
    def test_embedded_prepay_503(self, free_token):
        r = requests.post(f"{API}/payments/embedded/prepay-upload",
                          headers=_auth(free_token),
                          json={"origin_url": BASE_URL}, timeout=20)
        assert r.status_code == 503, r.text
        assert "Embedded checkout not configured" in r.json().get("detail", "")

    def test_embedded_unlock_503(self, free_token):
        # report_id required by schema; pass a dummy — should still 503 before lookup
        r = requests.post(f"{API}/payments/embedded/unlock",
                          headers=_auth(free_token),
                          json={"report_id": "nonexistent", "origin_url": BASE_URL}, timeout=20)
        assert r.status_code == 503, r.text
        assert "Embedded checkout not configured" in r.json().get("detail", "")

    def test_embedded_status_nonexistent_session_404(self, free_token):
        sid = f"cs_test_{uuid.uuid4().hex}"
        r = requests.get(f"{API}/payments/embedded/status/{sid}",
                         headers=_auth(free_token), timeout=20)
        assert r.status_code == 404, r.text

    def test_embedded_endpoints_require_auth(self):
        r = requests.post(f"{API}/payments/embedded/prepay-upload",
                         json={"origin_url": BASE_URL}, timeout=20)
        assert r.status_code in (401, 403), r.text


# ---------------- LEGACY REDIRECT-STYLE PAYMENTS ----------------
class TestLegacyPayments:
    def test_legacy_checkout_no_report_returns_404(self, free_token):
        r = requests.post(f"{API}/payments/checkout", headers=_auth(free_token),
                          json={"report_id": "definitely-missing-id", "origin_url": BASE_URL},
                          timeout=30)
        assert r.status_code == 404, r.text

    def test_legacy_prepay_upload_creates_stripe_url_with_usd(self, free_token):
        """The FREE user's prepay-upload route should always work (it's a fresh purchase, not gated on free_preview_used).
        Verify amount/currency are stored in USD in payment_transactions via the response and admin payments list.
        """
        r = requests.post(f"{API}/payments/prepay-upload", headers=_auth(free_token),
                          json={"origin_url": BASE_URL}, timeout=60)
        # On the Emergent stub this should return a Stripe URL.
        assert r.status_code == 200, f"prepay-upload failed: {r.status_code} {r.text[:400]}"
        data = r.json()
        assert "url" in data and data["url"].startswith("http"), data
        assert "session_id" in data and data["session_id"].startswith("cs_"), data
        # Stash for admin verification
        pytest.session_id_holder = data["session_id"]

    def test_payment_transaction_recorded_in_usd(self, admin_token):
        sid = getattr(pytest, "session_id_holder", None)
        if not sid:
            pytest.skip("prepay-upload test did not run / session missing")
        r = requests.get(f"{API}/admin/payments", headers=_auth(admin_token), timeout=20)
        assert r.status_code == 200
        rows = r.json()
        match = next((row for row in rows if row.get("session_id") == sid), None)
        assert match is not None, f"transaction {sid} not found in admin payments list"
        assert match.get("currency") == "usd", match
        assert match.get("amount") == 1.0, match
        assert match.get("kind") == "prepay_upload"


# ---------------- WEBHOOK ----------------
class TestWebhook:
    def test_webhook_route_exists_and_rejects_bare_post(self):
        r = requests.post(f"{API}/webhook/stripe", data=b"{}", timeout=20)
        # No Stripe-Signature header -> emergentintegrations verification should fail.
        # Accept 400 or 4xx — what matters is route exists and isn't a 404.
        assert r.status_code != 404, r.text
        assert r.status_code in (400, 401, 403, 422, 500), r.status_code


# ---------------- UPLOAD ELIGIBILITY ----------------
class TestUploadEligibility:
    def test_free_user_upload_eligibility_shape(self, free_token):
        r = requests.get(f"{API}/me/upload-eligibility", headers=_auth(free_token), timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("eligible", "reason", "free_preview_used", "prepaid_uploads"):
            assert k in d, f"missing {k} in {d}"
        assert isinstance(d["eligible"], bool)
        assert d["reason"] in ("free_preview", "prepaid", "prepay_required", "admin")
        assert isinstance(d["prepaid_uploads"], int)
