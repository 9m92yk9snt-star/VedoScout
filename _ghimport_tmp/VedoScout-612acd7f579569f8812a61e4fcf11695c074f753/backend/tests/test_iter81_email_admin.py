"""iter81: Admin send-test emails (11 templates), sample-report route, click redirect."""
import os
import pytest
import requests

def _load_base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    assert v, "REACT_APP_BACKEND_URL must be set"
    return v.rstrip("/")

BASE = _load_base()
ADMIN = {"email": "admin@elitescout.com", "password": "Admin@2026!Elite"}
TEST_TO = "noreply@scoutmeplay.com"

TEMPLATES = [
    "welcome", "activation_24h", "activation_72h",
    "conv_waiting", "conv_discount", "conv_discovery",
    "abandoned_checkout", "discount_campaign",
    "report_ready", "purchase_confirmation", "curve_reminder",
]


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


class TestSendTestEmail:
    def test_no_auth_rejected(self):
        r = requests.post(f"{BASE}/api/admin/emails/send-test",
                          json={"template": "welcome", "to": TEST_TO}, timeout=15)
        assert r.status_code in (401, 403), f"got {r.status_code}"

    def test_invalid_recipient(self, admin_session):
        r = admin_session.post(f"{BASE}/api/admin/emails/send-test",
                               json={"template": "welcome", "to": "not-an-email"}, timeout=30)
        assert r.status_code == 400

    def test_unknown_template(self, admin_session):
        r = admin_session.post(f"{BASE}/api/admin/emails/send-test",
                               json={"template": "does_not_exist", "to": TEST_TO}, timeout=30)
        assert r.status_code == 400

    @pytest.mark.parametrize("template", TEMPLATES)
    def test_template_sends(self, admin_session, template):
        r = admin_session.post(f"{BASE}/api/admin/emails/send-test",
                               json={"template": template, "to": TEST_TO}, timeout=60)
        assert r.status_code == 200, f"{template}: {r.status_code} {r.text[:200]}"
        data = r.json()
        assert data.get("ok") is True
        assert isinstance(data.get("subject"), str) and len(data["subject"]) > 0


class TestSampleReportRoute:
    def test_sample_report_page_loads(self):
        r = requests.get(f"{BASE}/sample-report", timeout=30, allow_redirects=True)
        assert r.status_code == 200
        # SPA — check title/Scout's First Impression may not appear in raw HTML (JS-rendered)
        assert "<html" in r.text.lower() or "<!doctype" in r.text.lower()


class TestEmailClickRedirect:
    def test_click_redirect_to_sample_report(self):
        target = "https://scoutmeplay.com/sample-report"
        r = requests.get(f"{BASE}/api/email/click/anyfakeid",
                         params={"u": target}, allow_redirects=False, timeout=15)
        assert r.status_code == 302
        assert r.headers.get("location", "").startswith(target)

    def test_click_rejects_open_redirect(self):
        r = requests.get(f"{BASE}/api/email/click/anyfakeid",
                         params={"u": "https://evil.example.com/x"},
                         allow_redirects=False, timeout=15)
        assert r.status_code == 302
        # must not redirect to attacker's domain
        loc = r.headers.get("location", "")
        assert "evil.example.com" not in loc
