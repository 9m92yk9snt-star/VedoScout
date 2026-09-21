"""
ScoutMePlay backend tests for EMBEDDED Stripe checkout — assumes REAL test keys
(`pk_test_...` and `sk_test_...`) are now configured in /app/backend/.env.

Validates:
  • GET /api/config/stripe returns full pk_test publishable_key and embedded_available=true
  • POST /api/payments/embedded/prepay-upload (free user, prepay_required state) returns 200 + client_secret + session_id
  • GET /api/payments/embedded/status/{session_id} returns payment_status=unpaid, status=open right after creation
  • Stripe session metadata via SDK: brand=ScoutMePlay, company=Mentalkids, source=scoutmeplay_website
  • Legacy /api/payments/prepay-upload still works under Emergent stub
  • Admin price update flow: PUT /api/admin/price -> 5.0 -> new embedded session unit_amount=500 -> reset to 1.0
  • /api/payments/embedded/unlock: skipped unless an unpaid report exists for free user
"""
import os
import pytest
import requests
import stripe as stripe_sdk

# Load backend .env to access STRIPE_SECRET_KEY for metadata verification
from pathlib import Path

_BACKEND_ENV = Path("/app/backend/.env")
if _BACKEND_ENV.exists():
    for line in _BACKEND_ENV.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")

ADMIN_EMAIL, ADMIN_PASSWORD = "admin@elitescout.com", "Admin@2026!Elite"
FREE_EMAIL, FREE_PASSWORD = "free@elitescout.com", "Free@2026"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="session")
def free_token():
    return _login(FREE_EMAIL, FREE_PASSWORD)


# ------------------ /config/stripe ------------------
class TestStripeConfigPublic:
    def test_returns_real_publishable_key_and_embedded_true(self):
        r = requests.get(f"{API}/config/stripe", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("embedded_available") is True, d
        pk = d.get("publishable_key", "")
        assert pk.startswith("pk_test_"), f"expected pk_test_ key, got: {pk[:20]}"
        # Should match what's in backend .env
        assert pk == STRIPE_PUBLISHABLE_KEY, "publishable_key differs from .env"


# ------------------ EMBEDDED PREPAY-UPLOAD ------------------
class TestEmbeddedPrepay:
    def test_free_user_prepay_returns_client_secret(self, free_token):
        r = requests.post(
            f"{API}/payments/embedded/prepay-upload",
            headers=_auth(free_token),
            json={"origin_url": BASE_URL},
            timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        d = r.json()
        assert "client_secret" in d and d["client_secret"], d
        assert "session_id" in d and d["session_id"].startswith("cs_"), d
        # Stash for downstream tests
        pytest.embedded_session_id = d["session_id"]
        pytest.embedded_client_secret = d["client_secret"]

    def test_status_endpoint_unpaid_open(self, free_token):
        sid = getattr(pytest, "embedded_session_id", None)
        if not sid:
            pytest.skip("no session_id from prepay test")
        r = requests.get(
            f"{API}/payments/embedded/status/{sid}",
            headers=_auth(free_token),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["payment_status"] == "unpaid", d
        assert d["status"] == "open", d

    def test_session_metadata_via_stripe_sdk(self):
        sid = getattr(pytest, "embedded_session_id", None)
        if not sid:
            pytest.skip("no session_id from prepay test")
        stripe_sdk.api_key = STRIPE_SECRET_KEY
        session = stripe_sdk.checkout.Session.retrieve(sid)
        md = session.metadata or {}
        assert md.get("brand") == "ScoutMePlay", md
        assert md.get("company") == "Mentalkids", md
        assert md.get("source") == "scoutmeplay_website", md
        assert md.get("kind") == "prepay_upload", md
        # ui_mode + amount sanity
        assert session.ui_mode == "embedded"
        assert session.amount_total == 100, f"expected 100 cents (=$1), got {session.amount_total}"
        assert session.currency == "usd"


# ------------------ EMBEDDED UNLOCK (skip if no unpaid report) ------------------
class TestEmbeddedUnlock:
    def test_unlock_endpoint_reachable_or_skip(self, free_token):
        # Try to find an unpaid report owned by the free user
        r = requests.get(f"{API}/reports", headers=_auth(free_token), timeout=20)
        if r.status_code != 200:
            pytest.skip(f"/api/reports not accessible: {r.status_code}")
        reports = r.json() if isinstance(r.json(), list) else r.json().get("reports", [])
        unpaid = [rep for rep in reports if not rep.get("is_paid")]
        if not unpaid:
            pytest.skip("No unpaid report exists for free user — endpoint code path not exercised, but configured")
        report_id = unpaid[0]["id"]
        r2 = requests.post(
            f"{API}/payments/embedded/unlock",
            headers=_auth(free_token),
            json={"report_id": report_id, "origin_url": BASE_URL},
            timeout=30,
        )
        assert r2.status_code == 200, f"{r2.status_code} {r2.text[:400]}"
        d = r2.json()
        assert d.get("client_secret"), d
        assert d.get("session_id", "").startswith("cs_"), d


# ------------------ CRITICAL BUG REPRO: emergentintegrations mutates global stripe.api_base ------------------
class TestEmergentIntegrationsPollutesGlobalStripeBase:
    """Documents critical regression: after the legacy /payments/prepay-upload endpoint runs
    (which uses emergentintegrations.StripeCheckout with sk_test_emergent), it mutates the
    GLOBAL `stripe.api_base` to https://integrations.emergentagent.com/stripe.
    Because the embedded endpoints share the same `stripe` module (imported as `stripe_sdk`),
    every embedded session created AFTER any legacy call goes through Emergent's stub proxy
    instead of api.stripe.com — even though stripe.api_key is reset to the real sk_test_51S...
    The returned client_secret is therefore unusable by the real Stripe.js iframe on the frontend.
    """

    def test_embedded_session_unusable_after_legacy_call(self, free_token):
        # Make a legacy call to pollute stripe.api_base in the backend worker
        rl = requests.post(
            f"{API}/payments/prepay-upload",
            headers=_auth(free_token),
            json={"origin_url": BASE_URL},
            timeout=60,
        )
        assert rl.status_code == 200
        # Now create an embedded session
        re = requests.post(
            f"{API}/payments/embedded/prepay-upload",
            headers=_auth(free_token),
            json={"origin_url": BASE_URL},
            timeout=30,
        )
        assert re.status_code == 200
        sid = re.json()["session_id"]
        # The session WILL appear in backend's own /status endpoint (it polls the same proxy)
        rs = requests.get(f"{API}/payments/embedded/status/{sid}",
                          headers=_auth(free_token), timeout=20)
        assert rs.status_code == 200  # proxy still answers
        # But on REAL Stripe (using same sk_test from .env), the session does NOT exist.
        stripe_sdk.api_key = STRIPE_SECRET_KEY
        try:
            stripe_sdk.api_base = "https://api.stripe.com"  # force real Stripe
            stripe_sdk.checkout.Session.retrieve(sid)
            real_stripe_found = True
        except Exception:
            real_stripe_found = False
        # THIS IS THE BUG — the session is NOT on real Stripe, so the frontend iframe will fail.
        assert real_stripe_found, (
            f"BUG: Embedded session {sid} is NOT on real Stripe — "
            "emergentintegrations.StripeCheckout polluted stripe.api_base globally. "
            "Fix: in /api/payments/embedded/* endpoints, reset `stripe_sdk.api_base = 'https://api.stripe.com'` "
            "before each session.create / retrieve call, OR isolate the two clients."
        )


# ------------------ LEGACY PREPAY (Emergent stub) ------------------
class TestLegacyPrepayStillWorks:
    def test_legacy_redirect_prepay_url(self, free_token):
        r = requests.post(
            f"{API}/payments/prepay-upload",
            headers=_auth(free_token),
            json={"origin_url": BASE_URL},
            timeout=60,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        d = r.json()
        assert d.get("url", "").startswith("http"), d
        assert d.get("session_id", "").startswith("cs_"), d


# ------------------ ADMIN PRICE FLOW ------------------
class TestAdminPriceUpdateEmbeddedAmount:
    def test_update_price_to_5_then_session_unit_amount_500(self, admin_token, free_token):
        # Bump price to 5.0
        r = requests.put(
            f"{API}/admin/price",
            headers=_auth(admin_token),
            json={"price": 5.0},
            timeout=20,
        )
        assert r.status_code == 200, r.text

        try:
            # Create a new embedded session
            r2 = requests.post(
                f"{API}/payments/embedded/prepay-upload",
                headers=_auth(free_token),
                json={"origin_url": BASE_URL},
                timeout=30,
            )
            assert r2.status_code == 200, r2.text
            sid = r2.json()["session_id"]

            # Fetch via SDK and assert unit_amount = 500 (retry for eventual consistency)
            stripe_sdk.api_key = STRIPE_SECRET_KEY
            import time
            session = None
            last_err = None
            for _ in range(5):
                try:
                    session = stripe_sdk.checkout.Session.retrieve(sid)
                    break
                except Exception as e:
                    last_err = e
                    time.sleep(1.0)
            assert session is not None, f"Could not retrieve session {sid}: {last_err}"
            assert session.amount_total == 500, f"expected 500 cents, got {session.amount_total}"
            assert session.currency == "usd"
            # Also assert via line items (more direct)
            line_items = stripe_sdk.checkout.Session.list_line_items(sid)
            assert line_items.data[0].amount_total == 500
        finally:
            # Always restore to 1.0
            requests.put(
                f"{API}/admin/price",
                headers=_auth(admin_token),
                json={"price": 1.0},
                timeout=20,
            )
            after = requests.get(f"{API}/settings/price", timeout=20).json()
            assert after["price"] == 1.0
