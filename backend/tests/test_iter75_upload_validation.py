"""Iter75: Regression - upload endpoint validation for country + photo_source.

Tests only 400-level rejections (safe, does not trigger paid Gemini analysis).
"""
import os
import io
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend/.env if not set in shell
    try:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = ln.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass

ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    token = r.json().get("access_token")
    assert token, "No access_token in login response"
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def _tiny_webm_bytes():
    # small non-empty bytes; server rejects on validation before decoding
    with open("/tmp/testvid.webm", "rb") as f:
        return f.read()


def test_landing_page_renders(admin_session):
    r = requests.get(f"{BASE_URL}/")
    assert r.status_code == 200
    assert "html" in r.headers.get("content-type", "").lower()


def test_admin_login_ok(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 200
    data = r.json()
    assert data.get("email") == ADMIN_EMAIL


def test_upload_missing_country_returns_400(admin_session):
    files = {
        "file": ("t.webm", io.BytesIO(_tiny_webm_bytes()), "video/webm"),
        "marker_image": ("m.jpg", io.BytesIO(b"\xff\xd8\xff\xe0fakejpg"), "image/jpeg"),
    }
    data = {
        "player_name": "TEST_Player",
        "age": "15",
        "position": "midfielder",
        "preferred_foot": "right",
        "video_type": "highlight",
        "description": "test",
        "photo_source": "video_crop",
        "marker_timestamp": "0.5",
    }
    r = admin_session.post(f"{BASE_URL}/api/reports/upload", data=data, files=files)
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:400]}"
    body = r.text.lower()
    assert "country" in body


def test_upload_missing_photo_source_returns_400(admin_session):
    files = {
        "file": ("t.webm", io.BytesIO(_tiny_webm_bytes()), "video/webm"),
        "marker_image": ("m.jpg", io.BytesIO(b"\xff\xd8\xff\xe0fakejpg"), "image/jpeg"),
    }
    data = {
        "player_name": "TEST_Player",
        "age": "15",
        "position": "midfielder",
        "preferred_foot": "right",
        "video_type": "highlight",
        "description": "test",
        "country": "Denmark",
        "marker_timestamp": "0.5",
    }
    r = admin_session.post(f"{BASE_URL}/api/reports/upload", data=data, files=files)
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:400]}"
    body = r.text.lower()
    assert "photo" in body


def test_admin_reports_list(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/reports")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    print(f"Reports found: {len(data)}")
    if data:
        # Save one id for frontend regression
        with open("/tmp/existing_report_id.txt", "w") as f:
            f.write(str(data[0].get("id") or data[0].get("_id") or ""))
