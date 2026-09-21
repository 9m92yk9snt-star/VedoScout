"""
Iteration 46 — Tests for R2 (Cloudflare) migration of admin demo-video uploads.

Covers:
 1. R2 UPLOAD FLOW — POST /api/admin/demo-videos/upload-video pushes to R2.
 2. R2 STREAMING PROXY — GET/HEAD /api/media/{key:path} + Range + 404 + 400.
 3. R2 DELETE FLOW — DELETE /api/admin/demo-videos/{id} removes R2 objects.
 4. LANDING CAROUSEL SANITY — GET /api/demo-videos still returns seeded items.
 5. REGRESSION — Existing /api/uploads/... URLs still serve files.

Cleanup: any object uploaded via r2_storage under `__probe__/` is deleted at
teardown. Any demo-video rows created here are deleted at teardown.
"""

import os
import sys
import subprocess
import time
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

# Load backend .env so r2_storage can auth against R2
load_dotenv("/app/backend/.env")

# Make backend importable for direct r2_storage calls
sys.path.insert(0, "/app/backend")
import r2_storage  # noqa: E402


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"

TEST_MP4 = "/tmp/test.mp4"


def _ensure_test_video():
    p = Path(TEST_MP4)
    if p.exists() and p.stat().st_size > 1000:
        return
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-movflags", "+faststart",
            TEST_MP4,
        ],
        check=True, capture_output=True,
    )


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    token = data.get("token") or data.get("access_token")
    assert token
    return token


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def json_admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ─────────────────────────── Sanity ────────────────────────────

def test_r2_is_configured():
    """r2_storage must be configured (env vars present)."""
    assert r2_storage.is_configured(), "r2_storage.is_configured() returned False"


# ─────────────────── Streaming proxy (probe object) ───────────────────

PROBE_KEY = "__probe__/hello.txt"
PROBE_BODY = b"hello from r2 probe " + str(time.time()).encode()


@pytest.fixture(scope="module", autouse=True)
def _probe_object():
    """Upload a small probe object and clean up all __probe__/* after tests."""
    assert r2_storage.is_configured()
    r2_storage.upload_bytes(PROBE_KEY, PROBE_BODY, "text/plain")
    yield
    # Cleanup all probe objects
    try:
        client = r2_storage._get_client()
        bucket = r2_storage._cfg()["bucket"]
        resp = client.list_objects_v2(Bucket=bucket, Prefix="__probe__/")
        for o in resp.get("Contents", []) or []:
            client.delete_object(Bucket=bucket, Key=o["Key"])
    except Exception as e:
        print(f"probe cleanup warning: {e}")


def test_media_get_probe_returns_bytes():
    r = requests.get(f"{BASE_URL}/api/media/{PROBE_KEY}", timeout=15)
    assert r.status_code == 200, f"got {r.status_code} {r.text[:200]}"
    assert r.content == PROBE_BODY
    assert r.headers.get("accept-ranges", "").lower() == "bytes"


def test_media_head_probe_has_headers():
    r = requests.head(f"{BASE_URL}/api/media/{PROBE_KEY}", timeout=15)
    assert r.status_code == 200
    assert r.headers.get("content-length") == str(len(PROBE_BODY))
    assert r.headers.get("accept-ranges", "").lower() == "bytes"
    ct = (r.headers.get("content-type") or "").lower()
    assert "text/plain" in ct or "octet-stream" in ct


def test_media_range_returns_206():
    r = requests.get(
        f"{BASE_URL}/api/media/{PROBE_KEY}",
        headers={"Range": "bytes=0-9"},
        timeout=15,
    )
    assert r.status_code == 206, f"expected 206, got {r.status_code}"
    cr = r.headers.get("content-range", "")
    assert cr.startswith("bytes 0-9/"), f"bad content-range: {cr}"
    assert cr.endswith(f"/{len(PROBE_BODY)}")
    assert r.content == PROBE_BODY[0:10]


def test_media_unknown_key_returns_404():
    r = requests.get(
        f"{BASE_URL}/api/media/__probe__/does-not-exist-{int(time.time())}.bin",
        timeout=15,
    )
    assert r.status_code == 404
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    assert (body.get("detail") == "Media not found") or "Media not found" in r.text


def test_media_path_traversal_returns_400():
    # /api/media/../foo -> requests may normalise ../ on client side. Use raw string via URL join.
    # httpbin trick: build URL manually with %2E%2E (encoded ..) — but the FastAPI
    # {key:path} converter decodes it, still the check `..` in key should trigger 400.
    # Use fully-encoded path (encoded slash) to bypass URL normalization done
    # by uvicorn/starlette (which would otherwise collapse `..` and 404).
    r = requests.get(f"{BASE_URL}/api/media/%2E%2E%2Ffoo", timeout=15)
    assert r.status_code == 400, f"expected 400, got {r.status_code} body={r.text[:150]}"


# ─────────────────── R2 UPLOAD FLOW (admin) ───────────────────

_uploaded_r2_keys = []
_created_demo_ids = []


@pytest.fixture(scope="module", autouse=True)
def _cleanup_upload_artifacts(admin_token):
    yield
    # Delete DB rows we created
    hdrs = {"Authorization": f"Bearer {admin_token}"}
    for vid in _created_demo_ids:
        try:
            requests.delete(f"{BASE_URL}/api/admin/demo-videos/{vid}", headers=hdrs, timeout=15)
        except Exception:
            pass
    # Delete any leftover R2 objects
    for key in _uploaded_r2_keys:
        try:
            r2_storage.delete_object(key)
        except Exception:
            pass


def test_admin_upload_video_pushes_to_r2(admin_headers):
    _ensure_test_video()
    with open(TEST_MP4, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/api/admin/demo-videos/upload-video",
            headers=admin_headers,
            files={"file": ("test.mp4", f, "video/mp4")},
            timeout=180,
        )
    assert r.status_code == 200, f"Upload failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    assert data.get("ok") is True
    url = data.get("url") or ""
    poster = data.get("poster_url") or ""
    # (b)(c) URLs must be R2-backed backend proxy paths
    assert url.startswith("/api/media/demo_videos/"), f"video url not R2-backed: {url}"
    assert poster.startswith("/api/media/demo_videos/"), f"poster url not R2-backed: {poster}"

    # Remember keys so we clean up
    video_key = url.replace("/api/media/", "", 1)
    poster_key = poster.replace("/api/media/", "", 1)
    _uploaded_r2_keys.extend([video_key, poster_key])

    # (d) both URLs HEAD-fetchable
    for u in (url, poster):
        h = requests.head(f"{BASE_URL}{u}", timeout=30)
        assert h.status_code == 200, f"HEAD {u} => {h.status_code}"
        assert int(h.headers.get("content-length", "0")) > 0

    # (e) local disk cleaned up
    stem = video_key.split("/")[-1].replace(".web.mp4", "")
    local_dir = Path("/app/backend/uploads/demo_videos")
    for suffix in (".mp4", ".web.mp4", ".poster.jpg"):
        assert not (local_dir / f"{stem}{suffix}").exists(), \
            f"local file was NOT cleaned up: {stem}{suffix}"

    # (f) R2 bucket confirms objects
    assert r2_storage.object_exists(video_key), f"R2 missing video key {video_key}"
    assert r2_storage.object_exists(poster_key), f"R2 missing poster key {poster_key}"


# ─────────────────── R2 DELETE FLOW ───────────────────

def test_admin_delete_demo_video_removes_r2_objects(json_admin_headers):
    # Upload a probe video directly via r2_storage
    key = f"demo_videos/__probe__delete_{int(time.time())}.web.mp4"
    _ensure_test_video()
    with open(TEST_MP4, "rb") as f:
        data = f.read()
    r2_storage.upload_bytes(key, data, "video/mp4")
    assert r2_storage.object_exists(key)

    # Create demo-video row pointing to that key
    payload = {
        "title": "TEST_R2_DELETE",
        "video_url": f"/api/media/{key}",
        "order": 9998,
        "status": "draft",
    }
    r = requests.post(
        f"{BASE_URL}/api/admin/demo-videos",
        headers=json_admin_headers,
        json=payload,
        timeout=15,
    )
    assert r.status_code in (200, 201), f"Create failed: {r.status_code} {r.text[:200]}"
    created = r.json()
    vid = created.get("id")
    assert vid

    # DELETE the row
    r = requests.delete(
        f"{BASE_URL}/api/admin/demo-videos/{vid}",
        headers=json_admin_headers,
        timeout=15,
    )
    assert r.status_code == 200
    dd = r.json()
    assert dd.get("ok") is True
    assert dd.get("deleted_id") == vid

    # R2 object must be gone
    # (delete_object is best-effort; give R2 a tick)
    time.sleep(0.5)
    assert not r2_storage.object_exists(key), "R2 object still exists after delete"

    # DB row gone
    r = requests.get(f"{BASE_URL}/api/admin/demo-videos", headers=json_admin_headers, timeout=15)
    ids = [v.get("id") for v in r.json().get("items", [])]
    assert vid not in ids


# ─────────────────── Landing carousel + regression ───────────────────

def test_public_demo_videos_active_seeded():
    r = requests.get(f"{BASE_URL}/api/demo-videos", timeout=15)
    assert r.status_code == 200
    items = r.json().get("items", [])
    assert len(items) >= 2, f"expected >=2 seeded items, got {len(items)}"


def test_legacy_local_upload_still_serves():
    """Existing local /api/uploads/ URLs must still serve (regression)."""
    url = f"{BASE_URL}/api/uploads/demo_videos/75e7a7f1a57e49ff975b8ba5c750dcff.web.mp4"
    r = requests.head(url, timeout=30, allow_redirects=True)
    # If file is missing on disk this returns 404 — flag but don't hard-fail this specific file
    if r.status_code != 200:
        # Try any seeded video from public list
        pub = requests.get(f"{BASE_URL}/api/demo-videos", timeout=15).json().get("items", [])
        legacy = [v for v in pub if (v.get("video_url") or "").startswith("/api/uploads/")]
        if legacy:
            url2 = legacy[0]["video_url"]
            r2 = requests.head(f"{BASE_URL}{url2}", timeout=30)
            assert r2.status_code == 200, f"legacy upload {url2} => {r2.status_code}"
        else:
            pytest.skip("no legacy /api/uploads/ demo-video to regression-check")
    else:
        assert int(r.headers.get("content-length", "0")) > 0
