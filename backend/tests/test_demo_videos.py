"""Backend tests for the new Demo Videos feature (Session 111).

Covers:
- GET /api/demo-videos (public) returns { items: [] } when nothing active
- GET /api/admin/demo-videos requires admin auth
- POST /api/admin/demo-videos/upload-video accepts an mp4 payload
- Full CRUD (create -> update -> delete) + file cleanup on delete
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def tiny_mp4(tmp_path_factory):
    p = tmp_path_factory.mktemp("uploads") / "test.mp4"
    # ~500 KB random bytes (backend only checks content-type, not real container)
    with p.open("wb") as f:
        f.write(os.urandom(500 * 1024))
    return str(p)


# ── PUBLIC ENDPOINT ────────────────────────────────────────────────

def test_public_list_returns_json_200():
    r = requests.get(f"{BASE_URL}/api/demo-videos", timeout=10)
    assert r.status_code == 200
    assert "application/json" in r.headers.get("Content-Type", "")
    body = r.json()
    assert "items" in body
    assert isinstance(body["items"], list)


# ── ADMIN AUTH GUARD ───────────────────────────────────────────────

def test_admin_list_requires_auth():
    r = requests.get(f"{BASE_URL}/api/admin/demo-videos", timeout=10)
    assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


def test_admin_list_returns_items(admin_headers):
    r = requests.get(f"{BASE_URL}/api/admin/demo-videos", headers=admin_headers, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body.get("items"), list)


# ── UPLOAD + FULL CRUD FLOW ────────────────────────────────────────

def test_full_demo_video_flow(admin_headers, tiny_mp4):
    # 1. Snapshot count before
    before = requests.get(f"{BASE_URL}/api/demo-videos", timeout=10).json()["items"]
    before_ids = {i["id"] for i in before}

    # 2. Upload video file
    with open(tiny_mp4, "rb") as f:
        files = {"file": ("test.mp4", f, "video/mp4")}
        up = requests.post(
            f"{BASE_URL}/api/admin/demo-videos/upload-video",
            headers=admin_headers,
            files=files,
            timeout=60,
        )
    assert up.status_code == 200, f"upload failed: {up.status_code} {up.text}"
    up_body = up.json()
    assert up_body.get("ok") is True
    assert up_body["url"].startswith("/api/uploads/demo_videos/")
    assert up_body["size_bytes"] > 0
    assert up_body["content_type"] == "video/mp4"
    video_url = up_body["url"]

    # 3. Create demo video row
    payload = {
        "title": "TEST_DemoVideo_E2E",
        "subtitle": "pytest end-to-end",
        "video_url": video_url,
        "order": 999,
        "status": "active",
    }
    cr = requests.post(
        f"{BASE_URL}/api/admin/demo-videos",
        headers=admin_headers,
        json=payload,
        timeout=15,
    )
    assert cr.status_code == 200, f"create failed: {cr.status_code} {cr.text}"
    created = cr.json()
    assert created["title"] == payload["title"]
    assert created["video_url"] == video_url
    assert created["status"] == "active"
    assert "id" in created
    vid = created["id"]

    try:
        # 4. Public list should now include this active row
        pub = requests.get(f"{BASE_URL}/api/demo-videos", timeout=10).json()["items"]
        pub_ids = {i["id"] for i in pub}
        assert vid in pub_ids, "newly created active demo video missing from public list"

        # 5. Update — change title + status to draft
        upd = requests.put(
            f"{BASE_URL}/api/admin/demo-videos/{vid}",
            headers=admin_headers,
            json={"title": "TEST_DemoVideo_Updated", "status": "draft"},
            timeout=15,
        )
        assert upd.status_code == 200, f"update failed: {upd.status_code} {upd.text}"
        upd_body = upd.json()
        assert upd_body["title"] == "TEST_DemoVideo_Updated"
        assert upd_body["status"] == "draft"

        # 6. After moving to draft, public list should no longer contain it
        pub2 = requests.get(f"{BASE_URL}/api/demo-videos", timeout=10).json()["items"]
        assert vid not in {i["id"] for i in pub2}, "draft video leaking into public list"

    finally:
        # 7. Delete row + verify file cleaned up
        dl = requests.delete(
            f"{BASE_URL}/api/admin/demo-videos/{vid}",
            headers=admin_headers,
            timeout=15,
        )
        assert dl.status_code == 200
        assert dl.json().get("deleted_id") == vid

        # 8. Confirm file gone from local uploads
        fname = video_url.split("/")[-1]
        local_path = f"/app/backend/uploads/demo_videos/{fname}"
        assert not os.path.exists(local_path), f"file still present after delete: {local_path}"

        # 9. Public list returns to previous state
        after = requests.get(f"{BASE_URL}/api/demo-videos", timeout=10).json()["items"]
        assert {i["id"] for i in after} == before_ids
