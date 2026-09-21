"""
Elite Football AI Scout - Backend API Tests
Covers: auth, settings, reports (upload+preview), payments, admin endpoints.
"""
import os
import io
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"
SAMPLE_MP4 = "/tmp/sample.mp4"

# Shared state across tests
_state = {}


# ----- Fixtures -----
@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    return s


@pytest.fixture(scope="session")
def admin_token(session):
    r = session.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["user"]["role"] == "admin"
    return data["access_token"]


@pytest.fixture(scope="session")
def user_creds():
    return {
        "email": f"TEST_user_{uuid.uuid4().hex[:8]}@example.com",
        "password": "TestPass123!",
        "full_name": "Test User",
    }


@pytest.fixture(scope="session")
def user_token(session, user_creds):
    r = session.post(f"{API}/auth/signup", json=user_creds)
    assert r.status_code == 200, f"signup failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["user"]["role"] == "user"
    _state["user_id"] = data["user"]["id"]
    return data["access_token"]


def auth_headers(tok):
    return {"Authorization": f"Bearer {tok}"}


# ============== AUTH ==============
class TestAuth:
    def test_health(self, session):
        r = session.get(f"{API}/")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_signup_duplicate(self, session, user_creds, user_token):
        # user_token fixture already created the user
        r = session.post(f"{API}/auth/signup", json=user_creds)
        assert r.status_code == 400
        assert "already" in r.json().get("detail", "").lower()

    def test_admin_login(self, admin_token):
        assert admin_token and isinstance(admin_token, str)

    def test_login_wrong_password(self, session):
        r = session.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-password-xyz"})
        assert r.status_code == 401

    def test_me_with_token(self, session, user_token, user_creds):
        r = session.get(f"{API}/auth/me", headers=auth_headers(user_token))
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == user_creds["email"].lower()
        assert data["role"] == "user"

    def test_me_without_token(self, session):
        r = session.get(f"{API}/auth/me")
        assert r.status_code == 401


# ============== SETTINGS ==============
class TestSettings:
    def test_public_price(self, session):
        r = session.get(f"{API}/settings/price")
        assert r.status_code == 200
        data = r.json()
        assert "price_dkk" in data
        assert data.get("currency") == "dkk"
        assert isinstance(data["price_dkk"], (int, float))


# ============== UPLOAD + PREVIEW (CRITICAL AI FLOW) ==============
class TestUploadPreview:
    def test_upload_video_creates_preview(self, session, user_token):
        if not os.path.exists(SAMPLE_MP4):
            pytest.skip("No sample mp4 available")
        with open(SAMPLE_MP4, "rb") as f:
            files = {"file": ("test.mp4", f, "video/mp4")}
            data = {
                "player_name": "Test Player",
                "age": 17,
                "position": "Midfielder",
                "preferred_foot": "right",
                "current_club": "TEST FC",
                "video_type": "highlight",
                "description": "Player wearing red jersey number 10",
            }
            r = session.post(f"{API}/reports/upload", headers=auth_headers(user_token), files=files, data=data, timeout=300)

        assert r.status_code == 200, f"upload failed: {r.status_code} {r.text[:500]}"
        body = r.json()
        assert "id" in body
        assert body.get("is_paid") is False
        preview = body.get("preview")
        assert isinstance(preview, dict), f"preview not a dict: {preview}"
        # Required preview keys
        for k in ("player_type", "brief_summary", "top_strengths", "area_for_improvement", "sample_section"):
            assert k in preview, f"missing preview key: {k}"
        assert isinstance(preview["top_strengths"], list)
        _state["report_id"] = body["id"]

    def test_my_reports_no_full(self, session, user_token):
        if "report_id" not in _state:
            pytest.skip("upload prerequisite missing")
        r = session.get(f"{API}/reports/mine", headers=auth_headers(user_token))
        assert r.status_code == 200
        reports = r.json()
        assert isinstance(reports, list)
        assert any(rep["id"] == _state["report_id"] for rep in reports)
        # full_report must NOT be leaked
        for rep in reports:
            assert "full_report" not in rep

    def test_get_report_locked_no_full(self, session, user_token):
        if "report_id" not in _state:
            pytest.skip("upload prerequisite missing")
        r = session.get(f"{API}/reports/{_state['report_id']}", headers=auth_headers(user_token))
        assert r.status_code == 200
        d = r.json()
        # not paid → full_report must be absent or None
        assert d.get("is_paid") is False
        assert d.get("full_report") in (None, "", {}, []) or "full_report" not in d

    def test_generate_full_locked_returns_402(self, session, user_token):
        if "report_id" not in _state:
            pytest.skip("upload prerequisite missing")
        r = session.post(f"{API}/reports/{_state['report_id']}/generate-full", headers=auth_headers(user_token))
        assert r.status_code == 402

    def test_pdf_download_locked_returns_402(self, session, user_token):
        if "report_id" not in _state:
            pytest.skip("upload prerequisite missing")
        r = session.get(f"{API}/reports/{_state['report_id']}/pdf", headers=auth_headers(user_token))
        assert r.status_code == 402


# ============== PAYMENTS ==============
class TestPayments:
    def test_create_checkout(self, session, user_token):
        if "report_id" not in _state:
            pytest.skip("upload prerequisite missing")
        payload = {"report_id": _state["report_id"], "origin_url": BASE_URL}
        r = session.post(f"{API}/payments/checkout", headers=auth_headers(user_token), json=payload, timeout=60)
        assert r.status_code == 200, f"checkout failed: {r.status_code} {r.text[:500]}"
        data = r.json()
        assert "url" in data and data["url"].startswith("http")
        assert "session_id" in data
        _state["session_id"] = data["session_id"]

    def test_payment_status_does_not_crash(self, session, user_token):
        if "session_id" not in _state:
            pytest.skip("checkout prerequisite missing")
        r = session.get(f"{API}/payments/status/{_state['session_id']}", headers=auth_headers(user_token), timeout=60)
        assert r.status_code == 200, f"status failed: {r.status_code} {r.text[:500]}"
        data = r.json()
        assert "payment_status" in data


# ============== ADMIN ==============
class TestAdmin:
    def test_stats_requires_admin(self, session, user_token):
        r = session.get(f"{API}/admin/stats", headers=auth_headers(user_token))
        assert r.status_code == 403

    def test_admin_stats(self, session, admin_token):
        r = session.get(f"{API}/admin/stats", headers=auth_headers(admin_token))
        assert r.status_code == 200
        d = r.json()
        for k in ("total_users", "total_uploads", "total_paid_reports", "revenue_dkk"):
            assert k in d

    def test_admin_users_list(self, session, admin_token, user_token):
        r = session.get(f"{API}/admin/users", headers=auth_headers(admin_token))
        assert r.status_code == 200
        # non-admin should 403
        r2 = session.get(f"{API}/admin/users", headers=auth_headers(user_token))
        assert r2.status_code == 403

    def test_admin_reports_list(self, session, admin_token):
        r = session.get(f"{API}/admin/reports", headers=auth_headers(admin_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_payments_list(self, session, admin_token):
        r = session.get(f"{API}/admin/payments", headers=auth_headers(admin_token))
        assert r.status_code == 200

    def test_admin_update_price(self, session, admin_token):
        # change to 499 then restore
        r = session.put(f"{API}/admin/price", headers=auth_headers(admin_token), json={"price_dkk": 499})
        assert r.status_code == 200
        # verify via public endpoint
        r2 = session.get(f"{API}/settings/price")
        assert r2.json()["price_dkk"] == 499
        # restore
        r3 = session.put(f"{API}/admin/price", headers=auth_headers(admin_token), json={"price_dkk": 399})
        assert r3.status_code == 200

    def test_admin_update_price_forbidden_user(self, session, user_token):
        r = session.put(f"{API}/admin/price", headers=auth_headers(user_token), json={"price_dkk": 100})
        assert r.status_code == 403

    def test_admin_unlock_report(self, session, admin_token, user_token):
        if "report_id" not in _state:
            pytest.skip("upload prerequisite missing")
        rid = _state["report_id"]
        r = session.post(f"{API}/admin/reports/{rid}/unlock", headers=auth_headers(admin_token))
        assert r.status_code == 200
        # GET report as user → manually_unlocked=True, full_report still None
        r2 = session.get(f"{API}/reports/{rid}", headers=auth_headers(user_token))
        assert r2.status_code == 200
        d = r2.json()
        assert d.get("manually_unlocked") is True
        # full_report should still be null (needs generation)
        assert d.get("full_report") in (None, "", {})

    def test_admin_delete_report(self, session, admin_token, user_token):
        if "report_id" not in _state:
            pytest.skip("upload prerequisite missing")
        rid = _state["report_id"]
        r = session.delete(f"{API}/admin/reports/{rid}", headers=auth_headers(admin_token))
        assert r.status_code == 200
        # verify gone
        r2 = session.get(f"{API}/reports/{rid}", headers=auth_headers(user_token))
        assert r2.status_code == 404


# ----- Cleanup -----
def teardown_module(module):
    """Best-effort cleanup of TEST_ users."""
    try:
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
        if r.status_code != 200:
            return
        # We don't have a delete-user endpoint, so we leave TEST_ users in DB
        # but reports should already be deleted via admin tests
    except Exception:
        pass
