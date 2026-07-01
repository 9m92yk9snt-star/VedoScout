"""
Iteration 49 — 3 new P0 fixes for the R2-migrated video analysis pipeline:
  D1: /api/reports/{id}/generate-full is R2-aware (uses _ensure_report_video_local)
  D2: media_binaries.py resolves ffmpeg via imageio-ffmpeg bundle
  D3: Gemini chat.send_message wrapped in asyncio.wait_for(..., 480)
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
           "https://scout-ai-pro-1.preview.emergentagent.com"
BACKEND_DIR = Path("/app/backend")


# ── D2 · media_binaries module ────────────────────────────────────────
class TestD2MediaBinaries:
    def test_module_exports(self):
        from media_binaries import FFMPEG_BIN, FFPROBE_BIN, get_duration_seconds  # noqa
        assert callable(get_duration_seconds)

    def test_ffmpeg_resolves_to_imageio_bundle(self):
        from media_binaries import FFMPEG_BIN
        # Bundled binary path — survives even if /usr/bin/ffmpeg is wiped
        assert "imageio_ffmpeg" in FFMPEG_BIN, f"expected imageio bundle, got {FFMPEG_BIN}"
        assert Path(FFMPEG_BIN).exists(), f"binary missing: {FFMPEG_BIN}"

    def test_ffprobe_resolved(self):
        from media_binaries import FFPROBE_BIN
        assert FFPROBE_BIN and (Path(FFPROBE_BIN).exists() or FFPROBE_BIN == "ffprobe")

    def test_get_duration_seconds_real_video(self):
        from media_binaries import get_duration_seconds
        candidates = list(BACKEND_DIR.glob("uploads/*.mp4"))
        assert candidates, "no sample mp4 in uploads/"
        # pick a non-preview clip if available
        target = next((c for c in candidates if ".preview." not in c.name), candidates[0])
        dur = get_duration_seconds(target)
        assert dur > 0, f"duration returned 0 for {target}"

    def test_requirements_has_imageio_ffmpeg(self):
        req = (BACKEND_DIR / "requirements.txt").read_text()
        assert re.search(r"^imageio-ffmpeg==", req, re.M), "imageio-ffmpeg not pinned"

    def test_no_bare_ffmpeg_string_in_subprocess(self):
        """Search server.py + precision_engine.py for subprocess.run(['ffmpeg', ...])
        or subprocess.run(['ffprobe', ...]) — should be 0 hits."""
        for f in ("server.py", "precision_engine.py"):
            src = (BACKEND_DIR / f).read_text()
            # Look for the pattern: [ "ffmpeg" or [ 'ffmpeg' as first list arg
            bad_ffmpeg = re.findall(r"subprocess\.(?:run|Popen)\s*\(\s*\[\s*[\"']ffmpeg[\"']", src)
            bad_ffprobe = re.findall(r"subprocess\.(?:run|Popen)\s*\(\s*\[\s*[\"']ffprobe[\"']", src)
            assert not bad_ffmpeg, f"{f} still uses bare 'ffmpeg' in subprocess: {bad_ffmpeg}"
            assert not bad_ffprobe, f"{f} still uses bare 'ffprobe' in subprocess: {bad_ffprobe}"


# ── D3 · Gemini asyncio.wait_for wrapper ──────────────────────────────
class TestD3GeminiTimeout:
    def test_wait_for_wraps_send_message(self):
        src = (BACKEND_DIR / "server.py").read_text()
        # exactly the shape described in review request
        assert re.search(
            r"asyncio\.wait_for\(\s*chat\.send_message\(",
            src,
        ), "chat.send_message not wrapped in asyncio.wait_for"
        # timeout should be 480s
        assert re.search(
            r"asyncio\.wait_for\(\s*chat\.send_message\([^)]*\)\s*,\s*timeout\s*=\s*480",
            src,
        ), "timeout=480 not set on wait_for wrapping chat.send_message"

    def test_timeout_error_raises_504(self):
        src = (BACKEND_DIR / "server.py").read_text()
        # Look for TimeoutError → 504 pattern in call_gemini_with_video vicinity
        assert re.search(r"asyncio\.TimeoutError", src), "no TimeoutError handling"
        # 504 must appear near a TimeoutError block
        assert re.search(
            r"asyncio\.TimeoutError[\s\S]{0,600}?(HTTPException|status_code)\s*[=(]\s*504",
            src,
        ) or re.search(
            r"504[\s\S]{0,400}?asyncio\.TimeoutError",
            src,
        ), "504 status not raised on Gemini TimeoutError"


# ── D1 · generate-full endpoint uses _ensure_report_video_local ───────
class TestD1GenerateFullR2Aware:
    def test_helper_exists(self):
        src = (BACKEND_DIR / "server.py").read_text()
        assert re.search(
            r"async\s+def\s+_ensure_report_video_local\s*\(", src
        ), "_ensure_report_video_local helper missing"

    def test_generate_full_uses_helper(self):
        src = (BACKEND_DIR / "server.py").read_text()
        # Locate the endpoint body — search from route decorator forward
        m = re.search(
            r'@api_router\.post\(\s*[\"\']\/reports\/\{report_id\}\/generate-full[\"\'].*?\)\s*\n'
            r"async\s+def\s+generate_full_report\([\s\S]{50,3000}?\ndef\s",  # up to next top-level def
            src,
        )
        # fallback loose match
        if not m:
            idx = src.find("/reports/{report_id}/generate-full")
            assert idx >= 0
            body = src[idx: idx + 3000]
        else:
            body = m.group(0)
        assert "_ensure_report_video_local" in body, (
            "generate_full_report body must call _ensure_report_video_local (R2-aware)"
        )

    def test_no_upload_dir_video_filename_check(self):
        """The old local-only pattern `UPLOAD_DIR / doc.video_filename` inside
        generate_full_report endpoint would recreate the 404 bug."""
        src = (BACKEND_DIR / "server.py").read_text()
        idx = src.find("/reports/{report_id}/generate-full")
        assert idx >= 0
        body = src[idx: idx + 2500]
        # No direct UPLOAD_DIR / video_filename existence check that raises 404
        assert not re.search(
            r"UPLOAD_DIR\s*/\s*[a-zA-Z_.]*video_filename[\s\S]{0,200}?404",
            body,
        ), "endpoint still has local-only 404 path"


# ── Smoke · backend is up + basic auth still works ────────────────────
class TestSmokeRegression:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/faq", timeout=15)
        assert r.status_code == 200

    def test_admin_login(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@elitescout.com", "password": "Admin@2026!Elite"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "token" in data or "access_token" in data

    def test_vip_login_and_eligibility(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "testvip@scoutmeplay.com", "password": "TestVip@2026!"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        token = r.json().get("token") or r.json().get("access_token")
        assert token
        h = {"Authorization": f"Bearer {token}"}
        e = requests.get(f"{BASE_URL}/api/me/upload-eligibility", headers=h, timeout=15)
        assert e.status_code == 200, e.text
        payload = e.json()
        assert payload.get("eligible") is True, payload
        # VIP subscription must be recognised (either "subscription" or "prepaid" per state)
        assert payload.get("reason") in ("subscription", "prepaid"), payload


# ── D1-live · Endpoint 404 fix on a real paid report ──────────────────
class TestD1LiveEndpoint:
    def test_generate_full_does_not_404_on_paid_report(self):
        # Login as admin
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@elitescout.com", "password": "Admin@2026!Elite"},
            timeout=15,
        )
        assert r.status_code == 200
        token = r.json().get("token") or r.json().get("access_token")
        h = {"Authorization": f"Bearer {token}"}

        # Grab any paid report
        lst = requests.get(f"{BASE_URL}/api/admin/reports", headers=h, timeout=20)
        if lst.status_code != 200:
            pytest.skip(f"admin/reports unavailable: {lst.status_code}")
        reports = lst.json() if isinstance(lst.json(), list) else lst.json().get("reports", [])
        # Pick a paid report that has either a local video file OR an R2 override —
        # a truly orphaned report (no local + no R2) legitimately 404s.
        uploads = Path("/app/backend/uploads")
        def _resolvable(x):
            if not x.get("is_paid"):
                return False
            vf = x.get("video_filename")
            if vf and (uploads / vf).exists():
                return True
            if x.get("video_url_override"):
                return True
            return False
        paid = [x for x in reports if _resolvable(x)]
        if not paid:
            pytest.skip("no paid reports with a resolvable video (local or R2)")
        rid = paid[0]["id"]

        resp = requests.post(
            f"{BASE_URL}/api/reports/{rid}/generate-full",
            headers=h, timeout=30,
        )
        # 404 is the exact bug we fixed — must NOT happen
        assert resp.status_code != 404, (
            f"generate-full returned 404 (the exact bug) for report {rid}: {resp.text}"
        )
        # Acceptable: 200 with generating/exists/already_generating, or 409/403 for
        # non-owner logic — anything BUT 404 means R2-aware path is functioning
        assert resp.status_code in (200, 202, 403, 409), (
            f"unexpected status {resp.status_code}: {resp.text}"
        )
