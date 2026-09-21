"""
Iteration 47 — Cloudflare R2 migration for PLAYER VIDEO uploads (Fase A) +
verification of pre-existing .mov → R2 migration (Fase B).

Covers:
 - FASE B: 4 pre-migrated reports (Almin13/Totooo/Ddddddd/Almin) — GET
   /api/admin/reports must return video_url under /api/media/reports/, each
   HEAD returns 200 + video/mp4, and no local .mov files match those stems.
 - FASE A: NEW upload via testfree-mar user goes through analyze_preview_task,
   video + poster are flushed to R2, local .web.mp4 is removed.
 - FASE A REGRESSION: premium user's seeded Lukas A. report still returns
   /api/uploads/... video_url (legacy branch intact).
 - R2 PROXY REGRESSION: /api/media/reports/... HEAD 200 + Range → 206.

Cleanup: DELETE any /api/reports/{id} we create, and R2-delete any objects
we put under 'reports/{test_id}/'.
"""

import io
import os
import sys
import subprocess
import time
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
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
FREE_EMAIL = "testfree-mar@elitescout.com"
FREE_PASSWORD = "Free@2026!"
PREMIUM_EMAIL = "premium@elitescout.com"
PREMIUM_PASSWORD = "Premium@2026"

TEST_MP4 = "/tmp/test_r2_player.mp4"
TEST_MARKER_JPG = "/tmp/test_r2_marker.jpg"

# Real football video available locally (passes content gate)
REAL_FOOTBALL_SRC = "/app/backend/uploads/10d5db11-bbd0-414b-816f-acc5f385998e.mp4"
REAL_FOOTBALL_MARKER = "/app/backend/uploads/10d5db11-bbd0-414b-816f-acc5f385998e-marker.jpg"

# 4 pre-migrated report IDs (Fase B)
MIGRATED_IDS = [
    "9079b88c-1b1d-4808-9311-e39879bd1a85",
    "07eed136-e534-41d7-83ae-c69811af3f79",
    "2d3083fd-75af-4b2c-a3a8-d83e01d28b3c",
    "0153da80-8192-4208-87ac-5e7f6d38eeb5",
]


def _ensure_test_media():
    """Copy an existing real football clip and extract a frame as marker_image
    so Gemini's content-gate (which correctly rejects testsrc / crop-thumbs)
    will let the analysis proceed."""
    import shutil
    if not os.path.exists(REAL_FOOTBALL_SRC):
        pytest.skip(f"real football video missing at {REAL_FOOTBALL_SRC}")
    shutil.copyfile(REAL_FOOTBALL_SRC, TEST_MP4)
    # Extract a full frame at t=1s from the video to use as marker_image
    subprocess.run(
        ["ffmpeg", "-y", "-ss", "1", "-i", TEST_MP4, "-frames:v", "1",
         "-q:v", "3", TEST_MARKER_JPG],
        check=True, capture_output=True,
    )


def _login(email, password):
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=15,
    )
    assert r.status_code == 200, f"login {email} => {r.status_code} {r.text[:200]}"
    d = r.json()
    tok = d.get("access_token") or d.get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def free_token():
    return _login(FREE_EMAIL, FREE_PASSWORD)


@pytest.fixture(scope="module")
def premium_token():
    return _login(PREMIUM_EMAIL, PREMIUM_PASSWORD)


# ══════════════════════ FASE B — Existing .mov migration ══════════════════════

def test_faseB_admin_reports_shows_R2_urls_for_migrated_players(admin_token):
    r = requests.get(
        f"{BASE_URL}/api/admin/reports?limit=200",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    items = body if isinstance(body, list) else body.get("items", [])
    by_id = {it.get("id"): it for it in items}
    missing = [rid for rid in MIGRATED_IDS if rid not in by_id]
    assert not missing, f"Migrated reports missing from admin list: {missing}"

    for rid in MIGRATED_IDS:
        it = by_id[rid]
        vurl = it.get("video_url") or ""
        assert vurl.startswith("/api/media/reports/"), \
            f"{rid} video_url not R2-backed: {vurl!r}"
        assert not vurl.startswith("/api/uploads/"), \
            f"{rid} still points to legacy /api/uploads/: {vurl!r}"


def test_faseB_migrated_video_urls_serve_video_mp4(admin_token):
    for rid in MIGRATED_IDS:
        url = f"{BASE_URL}/api/media/reports/{rid}/{rid}.web.mp4"
        h = requests.head(url, timeout=30)
        assert h.status_code == 200, f"{rid}: HEAD => {h.status_code}"
        ct = (h.headers.get("content-type") or "").lower()
        assert "video/mp4" in ct, f"{rid}: content-type={ct!r}"
        assert int(h.headers.get("content-length", "0")) > 1000


def test_faseB_no_local_mov_files_for_migrated_stems():
    uploads = Path("/app/backend/uploads")
    for rid in MIGRATED_IDS:
        # Any legacy .mov matching the stem
        for p in uploads.glob(f"{rid}*.mov"):
            pytest.fail(f"Legacy .mov leftover: {p}")
    # And no .mov files at all in uploads root
    all_movs = list(uploads.glob("*.mov"))
    assert not all_movs, f"Root uploads still contains .mov files: {all_movs[:5]}"


def test_faseB_r2_objects_exist_for_migrated_players():
    """Direct boto3 check that R2 has the objects."""
    assert r2_storage.is_configured()
    for rid in MIGRATED_IDS:
        key = f"reports/{rid}/{rid}.web.mp4"
        assert r2_storage.object_exists(key), f"R2 missing {key}"


# ══════════════════════ R2 PROXY REGRESSION ══════════════════════

def test_r2_proxy_range_returns_206_for_migrated_report():
    key_path = "reports/0153da80-8192-4208-87ac-5e7f6d38eeb5/0153da80-8192-4208-87ac-5e7f6d38eeb5.web.mp4"
    r = requests.get(
        f"{BASE_URL}/api/media/{key_path}",
        headers={"Range": "bytes=0-99"},
        timeout=30,
    )
    assert r.status_code == 206, f"expected 206, got {r.status_code}"
    cr = r.headers.get("content-range", "")
    assert cr.startswith("bytes 0-99/"), f"bad content-range: {cr}"
    assert len(r.content) == 100


# ══════════════════════ FASE A REGRESSION — legacy uploads ══════════════════════

def test_faseA_regression_premium_lukas_uses_legacy_uploads(premium_token):
    """
    Premium user's seeded Lukas A. report is a demo — its video_url must still
    start with /api/uploads/ (the /api/uploads/ static mount is the legacy
    branch used when video_url_override is unset).
    """
    r = requests.get(
        f"{BASE_URL}/api/reports/mine",
        headers={"Authorization": f"Bearer {premium_token}"},
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    items = body if isinstance(body, list) else body.get("items", [])
    assert len(items) >= 1, "premium user should have >=1 seeded report"
    # find any report with legacy /api/uploads/ URL
    legacy = [it for it in items if (it.get("video_url") or "").startswith("/api/uploads/")]
    assert legacy, f"No legacy /api/uploads/ report found for premium. video_urls: {[it.get('video_url') for it in items]}"


def test_faseA_regression_legacy_upload_head_status(premium_token):
    """
    HEAD the legacy /api/uploads/ URL — a well-configured demo should serve
    the file. If the file is missing on disk (deployment gap) this becomes a
    NOTED regression rather than a silent pass.
    """
    r = requests.get(
        f"{BASE_URL}/api/reports/mine",
        headers={"Authorization": f"Bearer {premium_token}"},
        timeout=15,
    )
    body = r.json()
    items = body if isinstance(body, list) else body.get("items", [])
    legacy = [it for it in items if (it.get("video_url") or "").startswith("/api/uploads/")]
    if not legacy:
        pytest.skip("no legacy report for HEAD check")
    url = f"{BASE_URL}{legacy[0]['video_url']}"
    h = requests.head(url, timeout=30, allow_redirects=True)
    assert h.status_code == 200, (
        f"legacy /api/uploads/ URL not served: {url} => {h.status_code}. "
        f"Check that the file exists under /app/backend/uploads/"
    )


# ══════════════════════ FASE A — NEW upload → R2 flow ══════════════════════

_created_report_ids = []
_r2_test_keys = []


@pytest.fixture(scope="module", autouse=True)
def _cleanup_after_upload(admin_token):
    yield
    hdrs = {"Authorization": f"Bearer {admin_token}"}
    for rid in _created_report_ids:
        try:
            requests.delete(f"{BASE_URL}/api/admin/reports/{rid}", headers=hdrs, timeout=15)
        except Exception:
            pass
        # Also attempt direct R2 cleanup for that report prefix
        try:
            client = r2_storage._get_client()
            bucket = r2_storage._cfg()["bucket"]
            resp = client.list_objects_v2(Bucket=bucket, Prefix=f"reports/{rid}/")
            for o in resp.get("Contents", []) or []:
                client.delete_object(Bucket=bucket, Key=o["Key"])
        except Exception as e:
            print(f"R2 cleanup warning for {rid}: {e}")
    # Sweep DB directly (in case delete endpoint 404)
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        import asyncio

        async def _sweep():
            c = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = c[os.environ["DB_NAME"]]
            for rid in _created_report_ids:
                await db.reports.delete_one({"id": rid})
        asyncio.run(_sweep())
    except Exception as e:
        print(f"DB sweep warning: {e}")


def test_faseA_new_upload_flushes_to_R2(free_token):
    _ensure_test_media()

    with open(TEST_MP4, "rb") as fv, open(TEST_MARKER_JPG, "rb") as fm:
        files = {
            "file": ("test.mp4", fv, "video/mp4"),
            "marker_image": ("marker.jpg", fm, "image/jpeg"),
        }
        data = {
            "marker_timestamp": "1.0",
            "marker_box": '{"x":0.3,"y":0.2,"w":0.4,"h":0.6}',
            "player_name": "TEST_R2_MIGRATION",
            "age": "15",
            "position": "CM",
            "preferred_foot": "right",
            "current_club": "Test FC",
            "video_type": "match",
            "description": "r2 migration test",
        }
        r = requests.post(
            f"{BASE_URL}/api/reports/upload",
            headers={"Authorization": f"Bearer {free_token}"},
            files=files,
            data=data,
            timeout=180,
        )
    assert r.status_code in (200, 201), f"upload failed: {r.status_code} {r.text[:400]}"
    body = r.json()
    rid = body.get("id") or body.get("report_id") or (body.get("report") or {}).get("id")
    assert rid, f"no report id in response: {body}"
    _created_report_ids.append(rid)

    # Poll status until 'ready' or timeout ~180s (Gemini can be slow)
    deadline = time.time() + 180
    last_status = None
    last_body = None
    while time.time() < deadline:
        s = requests.get(
            f"{BASE_URL}/api/reports/{rid}/status",
            headers={"Authorization": f"Bearer {free_token}"},
            timeout=15,
        )
        if s.status_code == 200:
            sb = s.json()
            last_body = sb
            last_status = sb.get("analysis_status") or sb.get("status")
            if last_status in ("ready", "preview_ready", "failed", "error"):
                break
        time.sleep(3)

    assert last_status in ("ready", "preview_ready"), (
        f"analysis did not reach ready in time (last_status={last_status!r}, "
        f"body={str(last_body)[:400]})"
    )

    # (a)/(b) URLs must be R2-backed
    vurl = last_body.get("video_url") or ""
    purl = last_body.get("poster_url") or ""
    assert vurl.startswith(f"/api/media/reports/{rid}/"), \
        f"video_url not R2-backed: {vurl!r}"
    if purl:
        assert purl.startswith(f"/api/media/reports/{rid}/"), \
            f"poster_url not R2-backed: {purl!r}"

    _r2_test_keys.append(vurl.replace("/api/media/", "", 1))
    if purl:
        _r2_test_keys.append(purl.replace("/api/media/", "", 1))

    # (c) HEAD video_url returns 200 + video/mp4
    h = requests.head(f"{BASE_URL}{vurl}", timeout=30)
    assert h.status_code == 200, f"HEAD {vurl} => {h.status_code}"
    ct = (h.headers.get("content-type") or "").lower()
    assert "video/mp4" in ct, f"content-type={ct!r}"
    assert int(h.headers.get("content-length", "0")) > 1000

    # (d) local .web.mp4 must NOT exist
    local_video = Path(f"/app/backend/uploads/{rid}.web.mp4")
    assert not local_video.exists(), f"local video not flushed: {local_video}"

    # (e) direct R2 confirmation
    key = f"reports/{rid}/{rid}.web.mp4"
    assert r2_storage.object_exists(key), f"R2 missing {key}"
