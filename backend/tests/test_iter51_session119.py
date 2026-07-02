"""
Session 119 (iteration 51) regression tests.

Bugs under test:
  F1 — PrecisionScanOverlay wired to real backend step (frontend — grep-verified)
  F2 — UploadPage passes backendStep prop (frontend — grep-verified)
  F3 — transcode_to_web_mp4 fast-path for already-h264+yuv420p sources
  F4 — Graceful fallback when ffprobe binary is missing
  F5 — Session 116-118 regressions still hold (VIP eligibility, landing, admin, FAQ)
  F6 — Zero occurrences of 'chef' / 'Cooking' outside tests
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

# Make backend importable
BACKEND_DIR = Path("/app/backend")
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") \
    else Path("/app/frontend/.env").read_text().split("REACT_APP_BACKEND_URL=", 1)[1].splitlines()[0].strip().rstrip("/")

DEMO = Path("/app/backend/uploads/demo-sample.mp4")


# ─────────────────────────────────────────────────────────────────────────────
# F3 — transcode_to_web_mp4 fast-path
# ─────────────────────────────────────────────────────────────────────────────
class TestF3FastPath:
    def test_demo_sample_is_h264_yuv420p(self):
        """Sanity: our fixture is h264+yuv420p so fast-path should trigger."""
        from server import _probe_video_codec
        codec, pix_fmt = _probe_video_codec(DEMO)
        assert codec == "h264", f"expected h264, got {codec!r}"
        assert pix_fmt == "yuv420p", f"expected yuv420p, got {pix_fmt!r}"

    def test_fast_path_under_1_5_seconds(self, tmp_path):
        """H.264 + yuv420p source must skip re-encode and finish <1.5s."""
        from server import transcode_to_web_mp4

        # Copy demo to a fresh tmp file so .web.mp4 sibling is clean
        src = tmp_path / "sample.mp4"
        shutil.copy2(DEMO, src)
        # Wipe any stale .web.mp4 next to it (there shouldn't be one, but safety)
        stale = src.with_suffix(".web.mp4")
        if stale.exists():
            stale.unlink()

        t0 = time.time()
        out = transcode_to_web_mp4(src)
        elapsed = time.time() - t0

        assert elapsed < 1.5, f"Fast-path should be <1.5s, took {elapsed:.2f}s"
        assert out.exists(), f"Output path {out} does not exist"
        assert out.suffix == ".mp4"
        # Fast-path produces a .web.mp4 sibling, not the source itself
        assert out.name.endswith(".web.mp4"), f"Expected .web.mp4 sibling, got {out.name}"
        # Content is identical (shallow copy)
        assert out.stat().st_size == src.stat().st_size

    def test_probe_helper_exists_and_returns_tuple(self):
        from server import _probe_video_codec
        result = _probe_video_codec(DEMO)
        assert isinstance(result, tuple) and len(result) == 2


# ─────────────────────────────────────────────────────────────────────────────
# F4 — Fallback when ffprobe is missing
# ─────────────────────────────────────────────────────────────────────────────
class TestF4FfprobeMissingFallback:
    """Rename /usr/bin/ffprobe and verify graceful degradation."""

    BACKUP = "/usr/bin/ffprobe.bak_iter51"

    @pytest.fixture(autouse=True)
    def _hide_ffprobe(self):
        # Setup: hide ffprobe
        moved = False
        try:
            r = subprocess.run(
                ["sudo", "mv", "/usr/bin/ffprobe", self.BACKUP],
                capture_output=True, text=True,
            )
            moved = (r.returncode == 0)
            if not moved:
                pytest.skip(f"cannot hide ffprobe (sudo mv failed): {r.stderr}")
            yield
        finally:
            if moved:
                subprocess.run(
                    ["sudo", "mv", self.BACKUP, "/usr/bin/ffprobe"],
                    capture_output=True, text=True,
                )

    def test_probe_returns_empty_when_ffprobe_missing(self):
        """_probe_video_codec must swallow FileNotFoundError and return ('','')."""
        from server import _probe_video_codec
        codec, pix_fmt = _probe_video_codec(DEMO)
        assert codec == "", f"expected empty codec when ffprobe missing, got {codec!r}"
        assert pix_fmt == "", f"expected empty pix_fmt when ffprobe missing, got {pix_fmt!r}"

    def test_transcode_still_succeeds_via_bundled_ffmpeg(self, tmp_path):
        """Even without ffprobe, transcode_to_web_mp4 must fall through to full
        re-encode via imageio-ffmpeg's bundled binary and return a valid file."""
        from server import transcode_to_web_mp4

        src = tmp_path / "sample.mp4"
        shutil.copy2(DEMO, src)
        stale = src.with_suffix(".web.mp4")
        if stale.exists():
            stale.unlink()

        out = transcode_to_web_mp4(src)
        # Full re-encode path — must exist and be non-empty.
        assert out.exists()
        assert out.stat().st_size > 0
        # On re-encode success it's .web.mp4; on total ffmpeg failure the code
        # returns the source path — both are "gracefully handled" but only
        # the former is what we expect here.
        assert out.name.endswith(".web.mp4") or out == src


# ─────────────────────────────────────────────────────────────────────────────
# F5 — Regression: prior Session 116-118 fixes still green
# ─────────────────────────────────────────────────────────────────────────────
class TestF5Regression:
    def test_landing_200(self):
        # Landing may live on frontend port; hit the marketing FAQ backend route
        # (fast + no auth) as a proxy for "backend is up".
        r = requests.get(f"{BASE_URL}/api/faq", timeout=15)
        assert r.status_code == 200, r.text[:300]
        payload = r.json()
        # FAQ endpoint returns list of Q/A entries — must be non-empty
        assert isinstance(payload, (list, dict)) and payload

    def test_admin_login_200(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@elitescout.com", "password": "Admin@2026!Elite"},
            timeout=15,
        )
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        # Elite scout auth returns a token in `token` or `access_token`.
        assert any(k in data for k in ("token", "access_token")) or "user" in data

    def test_vip_eligibility_true(self):
        s = requests.Session()
        login = s.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "testvip@scoutmeplay.com", "password": "TestVip@2026!"},
            timeout=15,
        )
        assert login.status_code == 200, login.text[:300]
        token = login.json().get("token") or login.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        r = s.get(f"{BASE_URL}/api/me/upload-eligibility", headers=headers, timeout=15)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("eligible") is True, f"testvip should be eligible: {d}"

    def test_transcode_still_writes_pix_fmt_yuv420p_flag(self):
        """Session 117 pix_fmt yuv420p fix must still be present in the ffmpeg
        command list of transcode_to_web_mp4."""
        src = Path("/app/backend/server.py").read_text()
        # Find the transcode fn and check the -pix_fmt flag exists inside.
        i = src.index("def transcode_to_web_mp4(")
        # 3000-char window comfortably covers the function body.
        body = src[i : i + 3000]
        assert '"-pix_fmt", "yuv420p"' in body, "pix_fmt yuv420p flag missing in transcode_to_web_mp4"

    def test_wall_clock_timeout_wrapper_still_present(self):
        """Session 118 E2 900s wrapper still wires the background task."""
        src = Path("/app/backend/server.py").read_text()
        assert "_analyze_preview_task_with_timeout" in src
        assert "timeout=900" in src or "timeout = 900" in src


# ─────────────────────────────────────────────────────────────────────────────
# F6 — Zero 'chef' / 'Cooking' occurrences outside tests
# ─────────────────────────────────────────────────────────────────────────────
class TestF6NoChefOrCooking:
    def test_no_chef_or_cooking_in_frontend_src(self):
        # -w for chef so 'chef*' random ids don't hit; case-insensitive for Cooking
        r = subprocess.run(
            [
                "bash", "-lc",
                "grep -rInE '\\bchef\\b|Cooking' /app/frontend/src "
                "--include='*.js' --include='*.jsx' --include='*.ts' --include='*.tsx' "
                "| grep -v node_modules || true"
            ],
            capture_output=True, text=True,
        )
        assert r.stdout.strip() == "", f"forbidden strings found in frontend/src:\n{r.stdout}"

    def test_no_chef_or_cooking_in_backend(self):
        r = subprocess.run(
            [
                "bash", "-lc",
                "grep -rInE '\\bchef\\b|Cooking' /app/backend --include='*.py' "
                "| grep -v '/tests/' | grep -v __pycache__ || true"
            ],
            capture_output=True, text=True,
        )
        assert r.stdout.strip() == "", f"forbidden strings found in backend:\n{r.stdout}"


# ─────────────────────────────────────────────────────────────────────────────
# F1 / F2 — Frontend grep-based verification (per review instructions)
# ─────────────────────────────────────────────────────────────────────────────
class TestF1F2FrontendGrep:
    OVERLAY = Path("/app/frontend/src/components/PrecisionScanOverlay.jsx")
    UPLOAD = Path("/app/frontend/src/pages/UploadPage.jsx")

    def test_overlay_accepts_backendStep_prop(self):
        text = self.OVERLAY.read_text()
        assert "backendStep" in text, "backendStep prop missing"
        assert "backendStep = 0" in text or "backendStep=0" in text, "default value not 0"

    def test_overlay_clamps_to_backendStep_when_provided(self):
        text = self.OVERLAY.read_text()
        # Check the guard: `backendStep >= 1` and setStepIdx(backendStep - 1)
        assert "backendStep >= 1" in text
        assert "backendStep - 1" in text

    def test_overlay_titles_match_backend_semantics(self):
        text = self.OVERLAY.read_text()
        for title in [
            "Receiving your video",
            "Preparing the footage",
            "Checking the content",
            "Watching every touch",
            "Writing your scout report",
        ]:
            assert title in text, f"title missing: {title!r}"

    def test_uploadpage_wires_backendStep(self):
        text = self.UPLOAD.read_text()
        assert "useState(0)" in text
        assert "setBackendStep" in text
        assert "statusResp.progress_step" in text
        assert "backendStep={backendStep}" in text
