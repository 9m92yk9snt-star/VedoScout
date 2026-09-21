"""Iter73: Newsletter + Blog Studio + Social follow tests."""
import os
import time
import requests
import pytest

def _load_base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        for line in open("/app/frontend/.env"):
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

BASE = _load_base()
ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"

TEST_EMAIL = "TEST_newsletter_iter73@example.com"
_created_sub_ids = []
_created_post_slug = None


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def admin(s):
    r = s.post(f"{BASE}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    session = requests.Session()
    if tok:
        session.headers["Authorization"] = f"Bearer {tok}"
    session.cookies.update(s.cookies)
    return session


# ── Social follow ─────────────────────────────────────────────────────
def test_social_follow_public(s):
    r = s.get(f"{BASE}/api/social-follow")
    assert r.status_code == 200
    d = r.json()
    assert "instagram" in d and "facebook" in d


# ── Newsletter ────────────────────────────────────────────────────────
def test_newsletter_invalid_email(s):
    r = s.post(f"{BASE}/api/newsletter/subscribe", json={"email": "not-an-email", "source": "test"})
    assert r.status_code == 400


def test_newsletter_subscribe_and_duplicate(s):
    r = s.post(f"{BASE}/api/newsletter/subscribe", json={"email": TEST_EMAIL, "source": "test"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("ok") is True

    r2 = s.post(f"{BASE}/api/newsletter/subscribe", json={"email": TEST_EMAIL, "source": "test"})
    assert r2.status_code == 200
    assert r2.json().get("already") is True


def test_admin_newsletter_list_and_delete(admin):
    r = admin.get(f"{BASE}/api/admin/newsletter")
    assert r.status_code == 200, r.text
    d = r.json()
    assert "items" in d
    subs = [i for i in d["items"] if i.get("email") == TEST_EMAIL.lower()]
    assert subs, "TEST subscriber not present"
    sid = subs[0]["id"]

    # delete cleanup
    dr = admin.delete(f"{BASE}/api/admin/newsletter/{sid}")
    assert dr.status_code == 200
    assert dr.json().get("ok") is True

    # verify deleted
    r2 = admin.get(f"{BASE}/api/admin/newsletter")
    assert not [i for i in r2.json()["items"] if i.get("email") == TEST_EMAIL.lower()]


# ── Blog Studio config ────────────────────────────────────────────────
def test_blog_studio_config_toggle(admin):
    # baseline
    r = admin.get(f"{BASE}/api/blog-studio/config")
    assert r.status_code == 200, r.text
    original = bool(r.json().get("auto_weekly"))

    # ON
    r1 = admin.put(f"{BASE}/api/blog-studio/config", json={"auto_weekly": True})
    assert r1.status_code == 200
    assert admin.get(f"{BASE}/api/blog-studio/config").json()["auto_weekly"] is True

    # OFF (restore off — safe default per rules)
    r2 = admin.put(f"{BASE}/api/blog-studio/config", json={"auto_weekly": False})
    assert r2.status_code == 200
    assert admin.get(f"{BASE}/api/blog-studio/config").json()["auto_weekly"] is False


# ── Blog Studio generate (LLM, one shot) ──────────────────────────────
def test_blog_studio_generate_once(admin):
    global _created_post_slug
    r = admin.post(
        f"{BASE}/api/blog-studio/generate",
        json={"topic": "How to help your child bounce back after a tough match", "keyword": ""},
    )
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]

    deadline = time.time() + 180
    job = None
    while time.time() < deadline:
        time.sleep(5)
        rj = admin.get(f"{BASE}/api/blog-studio/jobs")
        items = rj.json().get("items", [])
        job = next((j for j in items if j.get("id") == job_id), None)
        if job and job.get("status") in ("done", "failed"):
            break

    assert job is not None, "job not found"
    assert job.get("status") == "done", f"job did not complete: {job}"
    slug = job.get("slug")
    assert slug
    _created_post_slug = slug

    # Fetch draft from admin list
    posts = admin.get(f"{BASE}/api/blog/admin/posts").json()
    plist = posts if isinstance(posts, list) else posts.get("items") or posts.get("posts") or []
    match = next((p for p in plist if p.get("slug") == slug), None)
    assert match, f"created post not in admin list: slug={slug}"
    assert match.get("status") == "draft"
    body = match.get("content_md") or ""
    words = len(body.split())
    assert words >= 700, f"body too short: {words} words"
    assert match.get("meta_title")
    assert match.get("meta_description")
    assert match.get("category") in ("Training", "Scouting Tips", "Parent's Guide", "Pro Player Path")
    # voice rule assertions
    import re
    assert not re.search(r"\bAI\b", body), "body contains standalone 'AI'"
    assert "percentile" not in body.lower(), "body contains 'percentile'"


# ── Blog published listing regression ─────────────────────────────────
def test_blog_public_list(s):
    r = s.get(f"{BASE}/api/blog/posts")
    assert r.status_code == 200
    d = r.json()
    posts = d if isinstance(d, list) else d.get("items") or d.get("posts") or []
    assert len(posts) >= 1


def test_report_created_slug():
    # informational
    print(f"CREATED_DRAFT_SLUG={_created_post_slug}")
