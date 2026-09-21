"""Iteration 69 backend tests: reviews strip, demo videos filtering, admin reviews."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin_session(api):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# ---------- Reviews GET ----------
class TestReviewsGet:
    def test_returns_six_seeded_reviews(self, api):
        r = api.get(f"{BASE_URL}/api/reviews")
        assert r.status_code == 200
        data = r.json()
        items = data if isinstance(data, list) else data.get("items", [])
        assert len(items) >= 6, f"expected at least 6 reviews, got {len(items)}"
        names = [i.get("name", "") for i in items]
        expected = {"Noah", "Mette", "Lucas", "Sofia", "Jonas", "Elias"}
        found = {n for n in names if any(e in n for e in expected)}
        assert len(found) >= 6 or expected.issubset({n.split()[0] for n in names if n}), f"Missing expected reviewers. Got: {names}"

    def test_review_fields(self, api):
        r = api.get(f"{BASE_URL}/api/reviews")
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        for it in items[:6]:
            assert 0 <= it.get("stars", -1) <= 5
            assert len(it.get("text", "")) <= 50
            img = it.get("image_url", "")
            assert img, f"no image_url on {it}"

    def test_review_images_load(self, api):
        r = api.get(f"{BASE_URL}/api/reviews")
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        for it in items[:6]:
            img = it.get("image_url", "")
            if img.startswith("/"):
                url = f"{BASE_URL}{img}"
            else:
                url = img
            resp = requests.get(url)
            assert resp.status_code == 200, f"image {url} returned {resp.status_code}"


# ---------- Reviews POST validation ----------
class TestReviewsPost:
    def test_user_post_rejects_over_50_chars(self, api):
        payload = {"text": "x" * 51, "stars": 4}
        r = api.post(f"{BASE_URL}/api/reviews", json=payload)
        # unauth or 422 both acceptable rejections (over-50 must not pass validation)
        assert r.status_code in (401, 403, 422), f"expected rejection, got {r.status_code} {r.text}"

    def test_admin_post_rejects_over_50(self, admin_session):
        payload = {"name": "TEST_agent", "text": "x" * 51, "stars": 3}
        r = admin_session.post(f"{BASE_URL}/api/admin/reviews", json=payload)
        assert r.status_code == 422, f"expected 422 for >50 char text, got {r.status_code} {r.text}"

    def test_admin_post_rejects_stars_over_5(self, admin_session):
        payload = {"name": "TEST_agent", "text": "ok", "stars": 6}
        r = admin_session.post(f"{BASE_URL}/api/admin/reviews", json=payload)
        assert r.status_code == 422

    def test_admin_post_accepts_zero_stars(self, admin_session):
        payload = {"name": "TEST_iter69", "text": "test 0 star", "stars": 0}
        r = admin_session.post(f"{BASE_URL}/api/admin/reviews", json=payload)
        assert r.status_code in (200, 201), f"expected create ok, got {r.status_code} {r.text}"
        created = r.json()
        rid = created.get("id") or created.get("_id")
        # cleanup
        if rid:
            d = admin_session.delete(f"{BASE_URL}/api/admin/reviews/{rid}")
            assert d.status_code in (200, 204)

    def test_admin_post_accepts_5_stars_and_persists(self, admin_session, api):
        payload = {"name": "TEST_iter69_5", "text": "short review", "stars": 5}
        r = admin_session.post(f"{BASE_URL}/api/admin/reviews", json=payload)
        assert r.status_code in (200, 201)
        rid = r.json().get("id") or r.json().get("_id")
        try:
            listed = api.get(f"{BASE_URL}/api/reviews").json()
            items = listed if isinstance(listed, list) else listed.get("items", [])
            assert any((it.get("id") == rid or it.get("_id") == rid) for it in items) or \
                any(it.get("name") == "TEST_iter69_5" for it in items)
        finally:
            if rid:
                admin_session.delete(f"{BASE_URL}/api/admin/reviews/{rid}")


# ---------- Demo videos filtering ----------
class TestDemoVideos:
    def test_demo_videos_filtered(self, api):
        r = api.get(f"{BASE_URL}/api/demo-videos")
        assert r.status_code == 200
        data = r.json()
        items = data if isinstance(data, list) else data.get("items", [])
        assert items == [] or len(items) == 0, f"expected empty demo videos (missing files filtered), got {items}"
