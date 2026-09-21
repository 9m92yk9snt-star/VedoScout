"""Quality Engine tests (iter 93) — ScoutMePlay QC covering auth, duplicates,
overview, blog QC (with cover), blog apply+restore, carousel QC + apply+restore,
SEO apply+restore, stale detection. LLM-economical: max 1 blog + 1 carousel +
0-1 SEO re-run (reuse stored results whenever possible via GET /latest).
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


# ── Auth gating ────────────────────────────────────────────────────────────
class TestAuthGating:
    def test_overview_unauth(self):
        r = requests.get(f"{BASE}/api/admin/quality/overview", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"

    def test_duplicates_scan_unauth(self):
        r = requests.post(f"{BASE}/api/admin/quality/duplicates/scan", timeout=15)
        assert r.status_code in (401, 403)

    def test_seo_check_unauth(self):
        r = requests.post(f"{BASE}/api/admin/quality/seo/check", timeout=15)
        assert r.status_code in (401, 403)

    def test_latest_unauth(self):
        r = requests.get(f"{BASE}/api/admin/quality/latest", params={"kind": "seo", "target_id": "site"}, timeout=15)
        assert r.status_code in (401, 403)


# ── Overview & Duplicates (no LLM) ─────────────────────────────────────────
class TestOverviewAndDuplicates:
    def test_overview(self, admin_session):
        r = admin_session.get(f"{BASE}/api/admin/quality/overview", timeout=30)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        for k in ("blog", "carousel", "seo", "duplicates"):
            assert k in data, f"missing {k}"
        # ensure no ObjectId leakage
        assert "_id" not in str(data)

    def test_duplicates_scan(self, admin_session):
        r = admin_session.post(f"{BASE}/api/admin/quality/duplicates/scan", timeout=60)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert "warnings" in d and "counts" in d and "scores" in d
        assert isinstance(d["warnings"], list)
        assert "overall" in d["scores"]
        assert "passed" in d

    def test_duplicates_latest(self, admin_session):
        r = admin_session.get(f"{BASE}/api/admin/quality/latest",
                              params={"kind": "duplicates", "target_id": "site"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("found") is True
        assert d.get("status") == "ready"


# ── Blog QC ────────────────────────────────────────────────────────────────
def _poll_latest(sess, kind, target_id, timeout=180):
    """Poll GET latest until status ready/error, return final doc."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = sess.get(f"{BASE}/api/admin/quality/latest",
                     params={"kind": kind, "target_id": target_id}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            if d.get("found") and d.get("status") in ("ready", "error"):
                return d
        time.sleep(5)
    return None


@pytest.fixture(scope="module")
def blog_with_cover(admin_session):
    r = admin_session.get(f"{BASE}/api/blog/admin/posts", timeout=30)
    assert r.status_code == 200, r.text[:200]
    posts = r.json()
    posts = posts if isinstance(posts, list) else posts.get("posts") or posts.get("items") or []
    # prefer published + local cover
    for p in posts:
        cov = p.get("cover_image_url") or ""
        if p.get("status") == "published" and ("/api/blog/uploads/" in cov or "/api/media/blog/" in cov):
            return p
    # fallback any with local cover
    for p in posts:
        cov = p.get("cover_image_url") or ""
        if "/api/blog/uploads/" in cov or "/api/media/blog/" in cov:
            return p
    pytest.skip("no blog post with local cover available")


class TestBlogQC:
    def test_blog_check_with_cover(self, admin_session, blog_with_cover):
        pid = blog_with_cover["id"]
        # Check if a fresh ready result already exists to avoid burning an LLM call
        r = admin_session.get(f"{BASE}/api/admin/quality/latest",
                              params={"kind": "blog", "target_id": pid}, timeout=15)
        latest = r.json() if r.status_code == 200 else {}
        if not (latest.get("found") and latest.get("status") == "ready" and not latest.get("stale")):
            r = admin_session.post(f"{BASE}/api/admin/quality/blog/{pid}/check", timeout=30)
            assert r.status_code == 200, r.text[:200]
            assert r.json().get("status") == "checking"
            latest = _poll_latest(admin_session, "blog", pid, timeout=180)
            assert latest is not None, "blog QC did not complete in time"
        assert latest.get("status") == "ready", f"status={latest.get('status')} err={latest.get('error')}"
        checks = latest.get("checks") or []
        assert len(checks) == 17, f"expected 17 checks, got {len(checks)}"
        groups = {c["group"] for c in checks}
        assert groups >= {"text", "seo", "image"}
        scores = latest.get("scores") or {}
        for k in ("text", "seo", "overall"):
            assert isinstance(scores.get(k), int), f"{k} not int"
        # image score should be int since cover is attached
        assert isinstance(scores.get("image"), int), f"image score expected int with cover, got {scores.get('image')!r}"
        assert latest.get("image_classification") in ("AUTHENTIC", "REVIEW", "TOO_GENERIC", "NONE")
        assert "current" in latest and isinstance(latest["current"], dict)
        # store on module for downstream apply test
        pytest._blog_pid = pid  # type: ignore[attr-defined]
        pytest._blog_original_alt = latest["current"].get("cover_image_alt")  # type: ignore[attr-defined]

    def test_blog_apply_and_restore(self, admin_session):
        pid = getattr(pytest, "_blog_pid", None)
        if not pid:
            pytest.skip("no pid from previous test")
        original_alt = getattr(pytest, "_blog_original_alt", None)
        test_alt = "test alt from QA"
        r = admin_session.post(f"{BASE}/api/admin/quality/blog/{pid}/apply",
                               json={"fields": {"cover_image_alt": test_alt}}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert r.json().get("ok") is True

        # verify persisted
        r = admin_session.get(f"{BASE}/api/blog/admin/posts/{pid}", timeout=30)
        assert r.status_code == 200
        assert r.json().get("cover_image_alt") == test_alt

        # verify stale detection after apply
        r = admin_session.get(f"{BASE}/api/admin/quality/latest",
                              params={"kind": "blog", "target_id": pid}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("stale") is True, "stale should be true after content change"

        # restore
        restore_val = original_alt if (original_alt and original_alt.strip()) else "QC-test alt text — young footballer training"
        r = admin_session.post(f"{BASE}/api/admin/quality/blog/{pid}/apply",
                               json={"fields": {"cover_image_alt": restore_val}}, timeout=30)
        assert r.status_code == 200

    def test_blog_apply_invalid_field(self, admin_session):
        pid = getattr(pytest, "_blog_pid", None)
        if not pid:
            pytest.skip("no pid")
        r = admin_session.post(f"{BASE}/api/admin/quality/blog/{pid}/apply",
                               json={"fields": {"slug": "bad-slug"}}, timeout=30)
        assert r.status_code == 400


# ── Carousel QC ────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def carousel_done(admin_session):
    r = admin_session.get(f"{BASE}/api/carousel/jobs", timeout=30)
    assert r.status_code == 200, r.text[:200]
    jobs = r.json()
    jobs = jobs if isinstance(jobs, list) else jobs.get("jobs") or jobs.get("items") or []
    done = [j for j in jobs if j.get("status") == "done"]
    if not done:
        pytest.skip("no done carousel job")
    return done[0]


class TestCarouselQC:
    def test_carousel_check(self, admin_session, carousel_done):
        jid = carousel_done["id"]
        # reuse existing ready result if possible
        r = admin_session.get(f"{BASE}/api/admin/quality/latest",
                              params={"kind": "carousel", "target_id": jid}, timeout=15)
        latest = r.json() if r.status_code == 200 else {}
        if not (latest.get("found") and latest.get("status") == "ready" and not latest.get("stale")):
            r = admin_session.post(f"{BASE}/api/admin/quality/carousel/{jid}/check", timeout=30)
            assert r.status_code == 200, r.text[:200]
            latest = _poll_latest(admin_session, "carousel", jid, timeout=180)
            assert latest is not None, "carousel QC did not complete"
        assert latest.get("status") == "ready", f"status={latest.get('status')} err={latest.get('error')}"
        checks = latest.get("checks") or []
        assert len(checks) == 8
        scores = latest.get("scores") or {}
        for k in ("text", "image", "overall"):
            assert isinstance(scores.get(k), int)
        assert "current" in latest and "caption" in latest["current"]
        pytest._carousel_jid = jid  # type: ignore[attr-defined]
        pytest._carousel_original_caption = latest["current"].get("caption") or ""  # type: ignore[attr-defined]

    def test_carousel_apply_and_restore(self, admin_session):
        jid = getattr(pytest, "_carousel_jid", None)
        if not jid:
            pytest.skip("no jid")
        orig = getattr(pytest, "_carousel_original_caption", "")
        r = admin_session.post(f"{BASE}/api/admin/quality/carousel/{jid}/apply",
                               json={"caption": "test caption QA"}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert r.json().get("ok") is True

        # verify
        r = admin_session.get(f"{BASE}/api/carousel/jobs", timeout=30)
        body = r.json()
        jobs = body if isinstance(body, list) else (body.get("items") or body.get("jobs") or [])
        job = next((j for j in jobs if j.get("id") == jid), None)
        assert job and job.get("caption") == "test caption QA"

        # restore (skip if orig is empty which would 400)
        if orig.strip():
            r = admin_session.post(f"{BASE}/api/admin/quality/carousel/{jid}/apply",
                                   json={"caption": orig}, timeout=30)
            assert r.status_code == 200


# ── SEO QC (reuse stored result, only test apply+restore) ─────────────────
class TestSeoQC:
    def test_seo_latest_ready(self, admin_session):
        r = admin_session.get(f"{BASE}/api/admin/quality/latest",
                              params={"kind": "seo", "target_id": "site"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        if not (d.get("found") and d.get("status") == "ready"):
            pytest.skip("no stored SEO result — main agent said one exists; skipping to save LLM calls")
        pages = d.get("pages") or {}
        assert isinstance(pages, dict) and pages
        # validate structure of one page
        first = next(iter(pages.values()))
        for k in ("checks", "score", "passed", "current"):
            assert k in first, f"missing {k} in seo page"
        assert isinstance(d.get("scores", {}).get("overall"), int)

    def test_seo_apply_and_restore(self, admin_session):
        # apply on signup keywords only
        r = admin_session.post(f"{BASE}/api/admin/quality/seo/apply",
                               json={"pages": {"signup": {"keywords": "qa test kw"}}}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert "signup" in (r.json().get("applied") or [])

        # verify via public seo pages
        r = requests.get(f"{BASE}/api/seo/pages", timeout=15)
        if r.status_code == 200:
            pages = r.json()
            if isinstance(pages, dict) and "pages" in pages:
                pages = pages["pages"]
            signup = None
            if isinstance(pages, list):
                signup = next((p for p in pages if p.get("key") == "signup"), None)
            elif isinstance(pages, dict):
                signup = pages.get("signup")
            if signup:
                assert "qa test kw" in (signup.get("keywords") or "")

        # restore
        r = admin_session.post(f"{BASE}/api/admin/quality/seo/apply",
                               json={"pages": {"signup": {"keywords": "create account, free football report, sign up football analysis"}}},
                               timeout=30)
        assert r.status_code == 200

    def test_seo_apply_unknown_key_400(self, admin_session):
        r = admin_session.post(f"{BASE}/api/admin/quality/seo/apply",
                               json={"pages": {"nonexistent_page_xyz": {"title": "x"}}}, timeout=30)
        assert r.status_code == 400
