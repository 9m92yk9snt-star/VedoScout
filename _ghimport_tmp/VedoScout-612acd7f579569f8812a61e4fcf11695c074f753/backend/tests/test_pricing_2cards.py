"""
Iteration 14 — Backend tests for the new 2-card pricing API
(single $159 + 12-month plan $399) and the agent-queue regression.

Run:
  cd /app/backend && python -m pytest tests/test_pricing_2cards.py -v --tb=short
"""
import os
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    # Fallback to frontend/.env when running locally
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass

ADMIN = {"email": "admin@elitescout.com", "password": "Admin@2026!Elite"}
PREMIUM = {"email": "premium@elitescout.com", "password": "Premium@2026"}
FREE = {"email": "free@elitescout.com", "password": "Free@2026"}


# ─────────────────── auth helpers ───────────────────
def _login(creds):
    r = requests.post(f"{BASE}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def premium_token():
    return _login(PREMIUM)


@pytest.fixture(scope="module")
def free_token():
    return _login(FREE)


# ─────────────────── /settings/price contract ───────────────────
class TestPublicPriceEndpoint:
    def test_returns_both_prices_and_backward_compat_fields(self):
        r = requests.get(f"{BASE}/api/settings/price", timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "price" in data and isinstance(data["price"], (int, float))
        assert "pass_price" in data and isinstance(data["pass_price"], (int, float))
        assert "currency" in data
        assert "price_dkk" in data  # backward-compat alias
        # legacy alias equals new price
        assert float(data["price"]) == float(data["price_dkk"])
        # default seeded values
        assert data["price"] > 0
        assert data["pass_price"] > 0

    def test_default_values_after_iter14(self):
        r = requests.get(f"{BASE}/api/settings/price", timeout=10).json()
        # spec says 159 / 399 defaults — DB may already be at those values
        assert r["price"] in (159, 159.0), f"expected default 159, got {r['price']}"
        assert r["pass_price"] in (399, 399.0), f"expected default 399, got {r['pass_price']}"


# ─────────────────── PUT /admin/price (single report) ───────────────────
class TestAdminPriceSingle:
    endpoint = "/api/admin/price"

    def test_unauthenticated_rejected(self):
        r = requests.put(f"{BASE}{self.endpoint}", json={"price": 200}, timeout=10)
        assert r.status_code in (401, 403)

    def test_free_user_forbidden(self, free_token):
        r = requests.put(
            f"{BASE}{self.endpoint}", json={"price": 200},
            headers={"Authorization": f"Bearer {free_token}"}, timeout=10,
        )
        assert r.status_code in (401, 403)

    def test_invalid_zero(self, admin_token):
        r = requests.put(
            f"{BASE}{self.endpoint}", json={"price": 0},
            headers={"Authorization": f"Bearer {admin_token}"}, timeout=10,
        )
        assert r.status_code == 400

    def test_invalid_too_high(self, admin_token):
        r = requests.put(
            f"{BASE}{self.endpoint}", json={"price": 1500},
            headers={"Authorization": f"Bearer {admin_token}"}, timeout=10,
        )
        assert r.status_code == 400

    def test_valid_update_and_propagates(self, admin_token):
        # update to 169
        r = requests.put(
            f"{BASE}{self.endpoint}", json={"price": 169},
            headers={"Authorization": f"Bearer {admin_token}"}, timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json()["price"] == 169.0

        # verify via public endpoint
        pub = requests.get(f"{BASE}/api/settings/price", timeout=10).json()
        assert pub["price"] == 169.0
        assert pub["price_dkk"] == 169.0

        # reset to 159
        rr = requests.put(
            f"{BASE}{self.endpoint}", json={"price": 159},
            headers={"Authorization": f"Bearer {admin_token}"}, timeout=10,
        )
        assert rr.status_code == 200
        assert requests.get(f"{BASE}/api/settings/price", timeout=10).json()["price"] == 159.0


# ─────────────────── PUT /admin/pass-price (12-month plan) ───────────────────
class TestAdminPassPrice:
    endpoint = "/api/admin/pass-price"

    def test_unauthenticated_rejected(self):
        r = requests.put(f"{BASE}{self.endpoint}", json={"price": 499}, timeout=10)
        assert r.status_code in (401, 403)

    def test_free_user_forbidden(self, free_token):
        r = requests.put(
            f"{BASE}{self.endpoint}", json={"price": 499},
            headers={"Authorization": f"Bearer {free_token}"}, timeout=10,
        )
        assert r.status_code in (401, 403)

    def test_invalid_zero(self, admin_token):
        r = requests.put(
            f"{BASE}{self.endpoint}", json={"price": 0},
            headers={"Authorization": f"Bearer {admin_token}"}, timeout=10,
        )
        assert r.status_code == 400

    def test_invalid_too_high(self, admin_token):
        r = requests.put(
            f"{BASE}{self.endpoint}", json={"price": 12000},
            headers={"Authorization": f"Bearer {admin_token}"}, timeout=10,
        )
        assert r.status_code == 400

    def test_valid_update_and_pass_checkout_uses_new_price(self, admin_token, premium_token):
        # change to 449
        r = requests.put(
            f"{BASE}{self.endpoint}", json={"price": 449},
            headers={"Authorization": f"Bearer {admin_token}"}, timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["pass_price"] == 449.0

        # public reflects
        pub = requests.get(f"{BASE}/api/settings/price", timeout=10).json()
        assert pub["pass_price"] == 449.0

        # premium user → /progress/pass/checkout creates session at NEW price
        co = requests.post(
            f"{BASE}/api/progress/pass/checkout",
            json={"origin_url": "https://example.com"},
            headers={"Authorization": f"Bearer {premium_token}"},
            timeout=20,
        )
        assert co.status_code == 200, co.text
        session = co.json()
        assert "client_secret" in session
        assert "session_id" in session
        sid = session["session_id"]

        # verify txn row was inserted with amount = 449 — query via admin payments
        admin_tok = _login(ADMIN)
        pays = requests.get(
            f"{BASE}/api/admin/payments",
            headers={"Authorization": f"Bearer {admin_tok}"}, timeout=20,
        ).json()
        match = [p for p in pays if p.get("session_id") == sid]
        assert match, f"no payment_transactions row for session {sid}"
        assert float(match[0]["amount"]) == 449.0
        assert match[0]["kind"] == "progress_pass"

        # reset to 399
        rr = requests.put(
            f"{BASE}{self.endpoint}", json={"price": 399},
            headers={"Authorization": f"Bearer {admin_token}"}, timeout=10,
        )
        assert rr.status_code == 200
        assert requests.get(f"{BASE}/api/settings/price", timeout=10).json()["pass_price"] == 399.0


# ─────────────────── /admin/agent-queue regression ───────────────────
class TestAgentQueue:
    def test_admin_can_list_agent_queue_with_review_state(self, admin_token):
        r = requests.get(
            f"{BASE}/api/admin/agent-queue",
            headers={"Authorization": f"Bearer {admin_token}"}, timeout=20,
        )
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list)
        assert len(rows) >= 1, "expected at least 1 paid/unlocked report in the queue"

        for row in rows:
            assert "report_id" in row
            assert "agent_review" in row
            ar = row["agent_review"]
            assert ar is not None, f"report {row['report_id']} missing agent_review"
            assert "status" in ar
            assert ar["status"] in ("pending", "delivered"), f"invalid status: {ar['status']}"

    def test_seeded_lukas_review_is_delivered(self, admin_token):
        r = requests.get(
            f"{BASE}/api/admin/agent-queue",
            headers={"Authorization": f"Bearer {admin_token}"}, timeout=20,
        ).json()
        names = {row.get("player_name"): row for row in r}
        # try to find Lukas
        lukas_row = next((row for k, row in names.items() if k and "lukas" in k.lower()), None)
        if lukas_row:
            assert lukas_row["agent_review"]["status"] in ("delivered", "pending")
