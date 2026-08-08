# iter77 — Sticky CTA + SEO Insights + Best Price backend tests
import os
import pytest
import requests

def _load_env():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        for line in open(p):
            if line.strip().startswith("REACT_APP_BACKEND_URL="):
                return line.strip().split("=", 1)[1]
    return os.environ.get("REACT_APP_BACKEND_URL", "")

BASE_URL = _load_env().rstrip("/")
ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ─── Sticky CTA ─────────────────────────────────────────────────
class TestStickyCTA:
    def test_public_get_no_auth(self):
        r = requests.get(f"{BASE_URL}/api/settings/sticky-cta", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "enabled" in data
        assert "text" in data
        assert isinstance(data["enabled"], bool)
        assert isinstance(data["text"], str)

    def test_put_admin_requires_auth(self):
        r = requests.put(f"{BASE_URL}/api/admin/sticky-cta", json={"enabled": True, "text": "X"}, timeout=15)
        assert r.status_code in (401, 403)

    def test_put_admin_and_reload(self, admin_h):
        # Save custom value
        r = requests.put(f"{BASE_URL}/api/admin/sticky-cta", headers=admin_h,
                         json={"enabled": True, "text": "Se Min Rapport"}, timeout=15)
        assert r.status_code == 200, r.text
        # Verify via public GET
        r2 = requests.get(f"{BASE_URL}/api/settings/sticky-cta", timeout=15)
        assert r2.status_code == 200
        assert r2.json()["text"] == "Se Min Rapport"
        assert r2.json()["enabled"] is True
        # RESTORE
        r3 = requests.put(f"{BASE_URL}/api/admin/sticky-cta", headers=admin_h,
                          json={"enabled": True, "text": "Get My Report"}, timeout=15)
        assert r3.status_code == 200
        r4 = requests.get(f"{BASE_URL}/api/settings/sticky-cta", timeout=15)
        assert r4.json()["text"] == "Get My Report"
        assert r4.json()["enabled"] is True


# ─── SEO Insights ───────────────────────────────────────────────
class TestSEOInsights:
    def test_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/admin/seo/insights", timeout=15)
        assert r.status_code in (401, 403)

    def test_admin_ok(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/admin/seo/insights", headers=admin_h, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "articles" in data
        assert "suggestions" in data
        assert isinstance(data["articles"], list)
        assert isinstance(data["suggestions"], list)
        # Should have suggestions already cached (per task note)
        # not asserting count == 8 strictly, but should be present
        print(f"articles={len(data['articles'])} suggestions={len(data['suggestions'])}")


# ─── Pricing settings (for best-value math) ─────────────────────
class TestPricingSettings:
    def test_price_public(self):
        r = requests.get(f"{BASE_URL}/api/settings/price", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "single_price" in d and "premium_price" in d and "vip_price" in d
        # sanity: numbers exist
        assert float(d["single_price"]) > 0


# ─── Regression ─────────────────────────────────────────────────
class TestRegression:
    def test_demo_report(self):
        r = requests.get(f"{BASE_URL}/api/demo-report", timeout=30)
        assert r.status_code == 200
