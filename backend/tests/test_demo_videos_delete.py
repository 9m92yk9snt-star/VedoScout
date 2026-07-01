"""
Regression tests for demo-video admin delete flow + public GET endpoint.
Covers:
- Admin login
- POST /api/admin/demo-videos (create dummy row)
- GET /api/admin/demo-videos
- DELETE /api/admin/demo-videos/{id}
- Confirms row is gone from public GET /api/demo-videos
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback: read from frontend .env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    token = data.get("token") or data.get("access_token")
    assert token, f"No token in login response: {data}"
    return token


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


def test_public_get_demo_videos_works(admin_headers):
    """Public endpoint returns 200 and items list (regression)."""
    r = requests.get(f"{BASE_URL}/api/demo-videos", timeout=15)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_admin_can_list_demo_videos(admin_headers):
    r = requests.get(f"{BASE_URL}/api/admin/demo-videos", headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    assert "items" in data


def test_admin_create_delete_flow(admin_headers):
    # CREATE
    payload = {
        "title": "TEST_DELETE_ME",
        "video_url": "/api/uploads/demo_videos/test.mp4",
        "order": 9999,
        "status": "active",
    }
    r = requests.post(
        f"{BASE_URL}/api/admin/demo-videos",
        headers=admin_headers,
        json=payload,
        timeout=15,
    )
    assert r.status_code in (200, 201), f"Create failed: {r.status_code} {r.text[:200]}"
    created = r.json()
    video_id = created.get("id") or created.get("_id") or created.get("item", {}).get("id")
    assert video_id, f"No id in create response: {created}"

    # Verify shows in admin list
    r = requests.get(f"{BASE_URL}/api/admin/demo-videos", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    ids = [v.get("id") for v in r.json().get("items", [])]
    assert video_id in ids, f"Created video {video_id} not in list {ids}"

    # Verify shows in public GET (status=active)
    r = requests.get(f"{BASE_URL}/api/demo-videos", timeout=15)
    assert r.status_code == 200
    public_ids = [v.get("id") for v in r.json().get("items", [])]
    assert video_id in public_ids, f"Created active video not in public list"

    # UPDATE regression
    r = requests.put(
        f"{BASE_URL}/api/admin/demo-videos/{video_id}",
        headers=admin_headers,
        json={"subtitle": "test subtitle regression"},
        timeout=15,
    )
    assert r.status_code == 200, f"Update failed: {r.status_code} {r.text[:200]}"

    # DELETE
    r = requests.delete(
        f"{BASE_URL}/api/admin/demo-videos/{video_id}",
        headers=admin_headers,
        timeout=15,
    )
    assert r.status_code == 200, f"Delete failed: {r.status_code} {r.text[:200]}"
    del_data = r.json()
    assert del_data.get("ok") is True
    assert del_data.get("deleted_id") == video_id or str(del_data.get("deleted_id")) == str(video_id)

    # Verify gone from admin list
    r = requests.get(f"{BASE_URL}/api/admin/demo-videos", headers=admin_headers, timeout=15)
    ids = [v.get("id") for v in r.json().get("items", [])]
    assert video_id not in ids, f"Deleted video {video_id} still in admin list"

    # Verify gone from public GET
    r = requests.get(f"{BASE_URL}/api/demo-videos", timeout=15)
    public_ids = [v.get("id") for v in r.json().get("items", [])]
    assert video_id not in public_ids, f"Deleted video {video_id} still in public list"


def test_admin_delete_requires_auth():
    """DELETE without auth must NOT succeed."""
    r = requests.delete(
        f"{BASE_URL}/api/admin/demo-videos/some-fake-id",
        timeout=15,
    )
    assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
