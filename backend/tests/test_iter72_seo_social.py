"""Iter72 — SEO manager + Social-follow tests."""
import os
import re
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# ── /api/seo/pages ─────────────────────────────────────────────────
class TestSeoPages:
    def test_public_seo_pages(self):
        r = requests.get(f"{API}/seo/pages", timeout=30)
        assert r.status_code == 200
        pages = r.json().get("pages", {})
        expected = {"home", "upload", "about", "methodology", "blog", "scouts", "privacy", "terms", "signup", "login"}
        assert expected.issubset(set(pages.keys())), f"Missing keys: {expected - set(pages.keys())}"
        for k, p in pages.items():
            assert p.get("path")
            assert p.get("title")
            assert p.get("description")
            assert p.get("keywords")

    def test_admin_seo_get(self, admin_session):
        r = admin_session.get(f"{API}/admin/seo", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json().get("pages"), list)

    def test_admin_seo_put_override_and_reset(self, admin_session):
        # Override home
        payload = {"pages": {"home": {"title": "TEST SEO TITLE", "description": "test desc", "keywords": "a,b"}}}
        r = admin_session.put(f"{API}/admin/seo", json=payload, timeout=30)
        assert r.status_code == 200
        # Verify public reflects it
        pub = requests.get(f"{API}/seo/pages", timeout=30).json()["pages"]["home"]
        assert pub["title"] == "TEST SEO TITLE"
        assert pub["description"] == "test desc"

        # Reset by sending empty strings
        r2 = admin_session.put(f"{API}/admin/seo", json={"pages": {"home": {"title": "", "description": "", "keywords": ""}}}, timeout=30)
        assert r2.status_code == 200
        pub2 = requests.get(f"{API}/seo/pages", timeout=30).json()["pages"]["home"]
        assert pub2["title"] == "Discover Your True Football Level"

    def test_admin_seo_autofill(self, admin_session):
        r = admin_session.post(f"{API}/admin/seo/autofill", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        pages = data.get("pages") or {}
        assert len(pages) == 10
        # After autofill, reset home again to keep DB clean
        admin_session.put(f"{API}/admin/seo", json={"pages": {k: {"title": "", "description": "", "keywords": ""} for k in pages.keys()}}, timeout=30)


# ── /api/social-follow ─────────────────────────────────────────────
class TestSocialFollow:
    def test_public_social_follow(self):
        r = requests.get(f"{API}/social-follow", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "enabled" in d
        assert "instagram" in d and "url" in d["instagram"] and "followers" in d["instagram"]
        assert "facebook" in d and "url" in d["facebook"] and "followers" in d["facebook"]

    def test_admin_put_social_follow_persists_then_reset(self, admin_session):
        payload = {
            "enabled": True,
            "instagram": {"url": "https://www.instagram.com/scoutmeplay", "followers": 12500},
            "facebook": {"url": "https://www.facebook.com/scoutmeplay", "followers": 8300},
        }
        r = admin_session.put(f"{API}/admin/social-follow", json=payload, timeout=30)
        assert r.status_code == 200
        pub = requests.get(f"{API}/social-follow", timeout=30).json()
        assert pub["instagram"]["followers"] == 12500
        assert pub["facebook"]["followers"] == 8300
        assert pub["instagram"]["url"] == "https://www.instagram.com/scoutmeplay"
        assert pub["facebook"]["url"] == "https://www.facebook.com/scoutmeplay"

        # Reset followers to 0 (URLs kept)
        reset = {
            "enabled": True,
            "instagram": {"url": "https://www.instagram.com/scoutmeplay", "followers": 0},
            "facebook": {"url": "https://www.facebook.com/scoutmeplay", "followers": 0},
        }
        r2 = admin_session.put(f"{API}/admin/social-follow", json=reset, timeout=30)
        assert r2.status_code == 200
        pub2 = requests.get(f"{API}/social-follow", timeout=30).json()
        assert pub2["instagram"]["followers"] == 0
        assert pub2["facebook"]["followers"] == 0


# ── /api/sitemap.xml, robots.txt, rss.xml ──────────────────────────
class TestSitemapRobotsRss:
    def test_sitemap(self):
        r = requests.get(f"{API}/sitemap.xml", timeout=30)
        assert r.status_code == 200
        body = r.text
        for path in ["/", "/upload", "/about", "/methodology", "/scouts", "/privacy", "/terms", "/blog", "/signup", "/login"]:
            # Ensure this exact loc exists
            assert f"<loc>" in body and re.search(rf"<loc>[^<]*{re.escape(path)}</loc>", body), f"missing {path} in sitemap"

    def test_robots(self):
        r = requests.get(f"{API}/robots.txt", timeout=30)
        assert r.status_code == 200
        body = r.text
        assert "Disallow: /upload" not in body
        assert "Sitemap:" in body and "/api/sitemap.xml" in body

    def test_rss(self):
        r = requests.get(f"{API}/rss.xml", timeout=30)
        assert r.status_code == 200
        body = r.text
        assert "<rss" in body and "<channel>" in body
        assert "ScoutMePlay Blog" in body
