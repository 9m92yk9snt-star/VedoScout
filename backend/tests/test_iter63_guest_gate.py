"""Iter63 — Guest upload + new auth flows (backend smoke)."""
import os
import uuid
import time
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://scout-ai-pro-1.preview.emergentagent.com"


def _post(path, **kw):
    return requests.post(f"{BASE}{path}", timeout=30, **kw)


# ---- Signup password rules ----
def test_signup_password_valid_8chars_upper_digit():
    email = f"test_iter63_{uuid.uuid4().hex[:8]}@elitescout.com"
    r = _post("/api/auth/signup", json={"email": email, "password": "Test1234", "full_name": "T User"})
    assert r.status_code in (200, 201), r.text
    d = r.json()
    assert "access_token" in d


def test_signup_password_no_uppercase_400():
    email = f"test_iter63_{uuid.uuid4().hex[:8]}@elitescout.com"
    r = _post("/api/auth/signup", json={"email": email, "password": "test1234", "name": "T"})
    assert r.status_code in (400, 422), r.text


def test_signup_password_too_short():
    email = f"test_iter63_{uuid.uuid4().hex[:8]}@elitescout.com"
    r = _post("/api/auth/signup", json={"email": email, "password": "Test12", "name": "T"})
    assert r.status_code in (400, 422), r.text


# ---- Google session exchange ----
def test_google_session_bogus_401():
    r = _post("/api/auth/google/session", json={"session_id": "definitely_bogus_xxx"})
    assert r.status_code == 401, r.text


def test_google_session_empty_400():
    r = _post("/api/auth/google/session", json={"session_id": ""})
    assert r.status_code in (400, 422), r.text


# ---- Google-only account login guard ----
def test_login_google_account_no_password():
    r = _post("/api/auth/login", json={"email": "google.test@elitescout.com", "password": "anything"})
    assert r.status_code == 401
    body = r.text.lower()
    assert "google" in body, body


# ---- Admin regression ----
def test_admin_login_regression():
    r = _post("/api/auth/login", json={"email": "admin@elitescout.com", "password": "Admin@2026!Elite"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert "access_token" in d and "user" in d


# ---- Guest chunked upload cycle ----
def test_guest_chunked_upload_cycle():
    # tiny payload
    payload = b"0" * 1024
    fname = f"tiny_{uuid.uuid4().hex[:6]}.mp4"
    init = requests.post(
        f"{BASE}/api/me/chunked-upload/init",
        data={"filename": fname, "total_size": len(payload)},
        timeout=30,
    )
    assert init.status_code == 200, init.text
    upload_id = init.json().get("upload_id")
    assert upload_id, init.json()

    files = {"chunk": ("chunk0", payload, "application/octet-stream")}
    ch = requests.post(
        f"{BASE}/api/me/chunked-upload/chunk",
        data={"upload_id": upload_id, "index": 0},
        files=files,
        timeout=30,
    )
    assert ch.status_code == 200, ch.text

    comp = requests.post(
        f"{BASE}/api/me/chunked-upload/complete",
        data={"upload_id": upload_id, "total_chunks": 1},
        timeout=60,
    )
    assert comp.status_code == 200, comp.text
    d = comp.json()
    assert "temp_token" in d or "token" in d or "video_id" in d, d
