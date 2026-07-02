"""
Session 122 (iter52) — Gemini video timeout fix verifications.

G1: make_preview_clip aggressive shrink (480p / 15 fps / CRF 32 / mono 32k)
    → output <250 KB AND base64 body <340 KB for 1280x720 30 s source.
G2: Content-gate is skipped for PAID uploads (subscription/prepaid/progress_pass).
    Grep for `gate_skipped_paid` returns exactly 1 hit in server.py.
G3: chat.extra_params timeout=240.0 set BEFORE asyncio.wait_for(..., timeout=300).
G4: R2 flush BEFORE analysis_status='ready' — comment + call ordering intact.
G5: transcode_to_web_mp4 fast-path (h264+yuv420p) still <1.5 s.
G6: PrecisionScanOverlay.jsx has `backendStep` prop; UploadPage.jsx passes it.
G7: Session 121 e2e suite (test_e2e_full_audit.py) still 10/10 green — verified
    separately by running that suite; this file asserts the file still exists.
G8: Regressions — VIP eligible=true, admin login 200, /api/faq 200,
    /api/media/{key} 404 JSON, no chef/Cooking strings.
"""
from __future__ import annotations

import base64
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

# Resolve BASE_URL from frontend/.env (production external URL)
_FRONTEND_ENV = Path("/app/frontend/.env")
BASE_URL = None
if _FRONTEND_ENV.exists():
    for ln in _FRONTEND_ENV.read_text().splitlines():
        if ln.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = ln.split("=", 1)[1].strip().rstrip("/")
            break
assert BASE_URL, "REACT_APP_BACKEND_URL missing from /app/frontend/.env"

SERVER_PY = Path("/app/backend/server.py")
OVERLAY_JSX = Path("/app/frontend/src/components/PrecisionScanOverlay.jsx")
UPLOAD_JSX = Path("/app/frontend/src/pages/UploadPage.jsx")
E2E_FILE = Path("/app/backend/tests/test_e2e_full_audit.py")

VIP_EMAIL = "testvip@scoutmeplay.com"
VIP_PASS = "TestVip@2026!"
ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASS = "Admin@2026!Elite"


# ═════════════════════════════════════════════════════════════════
# G1 — make_preview_clip aggressive shrink
# ═════════════════════════════════════════════════════════════════
class TestG1_PreviewClipShrink:
    """Preview clip must produce a small (<250 KB) mp4 for 30 s / 1280x720 source."""

    @pytest.fixture(scope="class")
    def source_video(self, tmp_path_factory) -> Path:
        """Generate a synthetic 1280x720 30 s test clip via ffmpeg (deterministic)."""
        d = tmp_path_factory.mktemp("g1")
        src = d / "src.mp4"
        # ffmpeg synthetic: testsrc pattern + sine audio, 30 s at 30 fps, 1280x720
        cmd = [
            "/usr/bin/ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=30",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=30",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-loglevel", "error",
            str(src),
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=60)
        assert r.returncode == 0, f"ffmpeg source gen failed: {r.stderr.decode()[:400]}"
        assert src.exists() and src.stat().st_size > 0
        return src

    def test_make_preview_clip_output_size(self, source_video: Path):
        """
        Call server.make_preview_clip on the synthetic source and assert:
          - output exists
          - output size < 250 KB
          - base64 body (size * 4/3) < 340 KB
        This is the payload that goes to Gemini inline.
        """
        # Import server module (may be slow due to startup imports)
        if "/app/backend" not in sys.path:
            sys.path.insert(0, "/app/backend")
        from server import make_preview_clip  # noqa: WPS433 (runtime import)

        out = make_preview_clip(source_video, marker_seconds=10.0, window_seconds=15)
        assert out.exists(), "preview clip not produced"
        assert out != source_video, "make_preview_clip fell back to original — encode failed"

        sz = out.stat().st_size
        assert sz < 250 * 1024, f"preview clip too big: {sz:,} B (target <250 KB)"

        b64_body_size = int(sz * 4 / 3)
        assert b64_body_size < 340 * 1024, (
            f"base64 body too big: {b64_body_size:,} B (target <340 KB)"
        )
        print(f"[G1] preview clip = {sz:,} B  |  base64 body ≈ {b64_body_size:,} B")

    def test_make_preview_clip_ffmpeg_flags_present(self):
        """Grep-verify the ffmpeg command uses 480p / 15 fps / CRF 32 / mono 32k audio."""
        src = SERVER_PY.read_text()
        # Extract just the make_preview_clip function body (first ~80 lines after def)
        m = re.search(r"def make_preview_clip\(.*?\n(.*?)\ndef ", src, re.DOTALL)
        assert m, "make_preview_clip not found in server.py"
        body = m.group(1)
        # All 5 flags MUST be present
        assert "scale='min(854,iw)':-2,fps=15" in body, "480p+15fps -vf missing"
        assert '"-crf", "32"' in body, "CRF 32 missing"
        assert '"-b:a", "32k"' in body, "audio 32 kbps missing"
        assert '"-ac", "1"' in body, "mono (-ac 1) missing"
        assert '"-c:a", "aac"' in body, "AAC codec missing"


# ═════════════════════════════════════════════════════════════════
# G2 — content-gate skipped for paid uploads
# ═════════════════════════════════════════════════════════════════
class TestG2_ContentGateSkipPaid:
    def test_is_paid_upload_branch_present(self):
        src = SERVER_PY.read_text()
        # is_paid_upload variable assigned from doc fields
        assert "is_paid_upload" in src, "is_paid_upload variable missing"
        # Both conditions: doc.is_paid OR eligibility_consumed in {subscription,prepaid,progress_pass}
        assert 'doc.get("is_paid")' in src, "doc.get('is_paid') check missing"
        assert '"subscription"' in src and '"prepaid"' in src and '"progress_pass"' in src, (
            "eligibility_consumed tuple missing subscription/prepaid/progress_pass"
        )

    def test_gate_skipped_paid_marker_exactly_once(self):
        """Session 122 says grep should return exactly 1 hit in server.py."""
        src = SERVER_PY.read_text()
        hits = src.count("gate_skipped_paid")
        assert hits == 1, f"expected exactly 1 gate_skipped_paid hit, found {hits}"

    def test_stub_gate_dict_fields(self):
        """When is_paid_upload=True, the stub gate dict MUST have all 7 keys."""
        src = SERVER_PY.read_text()
        # Locate the if is_paid_upload: block
        idx = src.find("if is_paid_upload:")
        assert idx > 0, "if is_paid_upload: branch missing"
        # Look at the next ~800 chars for the stub dict
        block = src[idx : idx + 800]
        for expected in [
            '"is_football": True',
            '"content_type": "match"',
            '"quality": "good"',
            '"player_visible": "clear"',
            '"games_detected": 1',
            '"camera_distance": "medium"',
            '"gate_skipped_paid": True',
        ]:
            assert expected in block, f"stub gate dict missing: {expected}"

    def test_free_tier_still_calls_run_content_gate(self):
        """The `else:` branch of is_paid_upload MUST call run_content_gate."""
        src = SERVER_PY.read_text()
        # Grab the region from "if is_paid_upload:" through the next 1500 chars
        idx = src.find("if is_paid_upload:")
        region = src[idx : idx + 1500]
        assert "else:" in region, "else branch missing"
        assert "run_content_gate(report_id" in region, "run_content_gate not called in else branch"


# ═════════════════════════════════════════════════════════════════
# G3 — explicit LiteLLM timeout=240 + asyncio.wait_for=300
# ═════════════════════════════════════════════════════════════════
class TestG3_LiteLLMTimeout:
    def test_extra_params_timeout_240(self):
        src = SERVER_PY.read_text()
        # Loose match — both "chat.extra_params =" and "timeout": 240.0 within 200 chars
        pat = re.compile(r'chat\.extra_params\s*=.{0,200}"timeout":\s*240\.0', re.DOTALL)
        assert pat.search(src), "chat.extra_params timeout=240.0 assignment missing"

    def test_asyncio_wait_for_timeout_300(self):
        src = SERVER_PY.read_text()
        # Match asyncio.wait_for(chat.send_message(...), timeout=300)
        pat = re.compile(r"asyncio\.wait_for\(\s*chat\.send_message\([^\)]*\)\s*,\s*timeout=300\)")
        assert pat.search(src), "asyncio.wait_for(chat.send_message(...), timeout=300) missing"

    def test_extra_params_before_wait_for(self):
        """Ordering: extra_params timeout=240 MUST come BEFORE asyncio.wait_for(..., 300)."""
        src = SERVER_PY.read_text()
        i_ep = src.find('"timeout": 240.0')
        i_wf = src.find("asyncio.wait_for(chat.send_message")
        assert 0 < i_ep < i_wf, (
            f"ordering wrong: extra_params idx={i_ep}, wait_for idx={i_wf} — must be extra_params first"
        )


# ═════════════════════════════════════════════════════════════════
# G4 — R2 flush BEFORE analysis_status='ready'
# ═════════════════════════════════════════════════════════════════
class TestG4_R2FlushBeforeReady:
    def test_flush_before_ready_ordering(self):
        src = SERVER_PY.read_text()
        # Locate analyze_preview_task then check ordering of _flush and analysis_status=ready
        i_task = src.find("async def analyze_preview_task")
        assert i_task > 0, "analyze_preview_task not found"
        region = src[i_task : i_task + 25000]
        i_flush = region.find("_flush_preview_artifacts_to_r2(report_id)")
        i_ready = region.find('"analysis_status": "ready"')
        assert 0 < i_flush < i_ready, (
            f"R2 flush must precede analysis_status=ready — flush idx={i_flush}, ready idx={i_ready}"
        )

    def test_flush_before_ready_comment_present(self):
        src = SERVER_PY.read_text()
        # Comment wording may span two lines: "BEFORE marking the report\n        # ready"
        assert re.search(r"BEFORE\s+marking\s+the\s+report[\s#]+ready", src, re.IGNORECASE), (
            "'BEFORE marking the report ready' comment/wording missing"
        )


# ═════════════════════════════════════════════════════════════════
# G5 — transcode_to_web_mp4 fast-path still <1.5 s
# ═════════════════════════════════════════════════════════════════
class TestG5_FastPathIntact:
    def test_probe_helper_and_fast_path_speed(self, tmp_path):
        """Copy demo-sample.mp4 (h264+yuv420p) → transcode_to_web_mp4 <1.5 s (fast-path)."""
        demo = Path("/app/backend/uploads/demo-sample.mp4")
        if not demo.exists():
            pytest.skip("demo-sample.mp4 not present in /app/backend/uploads")
        # Use isolated copy so previous test artifacts don't skew timing
        import shutil
        src = tmp_path / "demo.mp4"
        shutil.copy2(demo, src)

        if "/app/backend" not in sys.path:
            sys.path.insert(0, "/app/backend")
        from server import _probe_video_codec, transcode_to_web_mp4  # noqa: WPS433

        codec, pix_fmt = _probe_video_codec(src)
        assert codec == "h264", f"expected h264, got {codec}"
        assert pix_fmt in ("yuv420p", "yuvj420p"), f"expected yuv420p, got {pix_fmt}"

        t0 = time.perf_counter()
        out = transcode_to_web_mp4(src)
        elapsed = time.perf_counter() - t0
        assert out.exists(), "fast-path did not produce output"
        assert elapsed < 1.5, f"fast-path too slow: {elapsed:.2f} s (target <1.5 s)"
        print(f"[G5] transcode_to_web_mp4 fast-path elapsed = {elapsed*1000:.1f} ms")


# ═════════════════════════════════════════════════════════════════
# G6 — Frontend PrecisionScanOverlay backendStep prop wiring
# ═════════════════════════════════════════════════════════════════
class TestG6_FrontendBackendStepWiring:
    def test_overlay_accepts_backend_step_prop(self):
        assert OVERLAY_JSX.exists(), "PrecisionScanOverlay.jsx missing"
        src = OVERLAY_JSX.read_text()
        assert "backendStep" in src, "backendStep prop missing from PrecisionScanOverlay"
        # Prop must appear in the function signature
        assert re.search(r"function\s+PrecisionScanOverlay\([^)]*backendStep", src), (
            "backendStep not in PrecisionScanOverlay function signature"
        )

    def test_uploadpage_passes_backend_step_prop(self):
        assert UPLOAD_JSX.exists(), "UploadPage.jsx missing"
        src = UPLOAD_JSX.read_text()
        assert "backendStep={backendStep}" in src, "UploadPage.jsx doesn't pass backendStep prop"


# ═════════════════════════════════════════════════════════════════
# G7 — Session 121 e2e suite still exists (results verified separately)
# ═════════════════════════════════════════════════════════════════
class TestG7_E2ESuiteIntact:
    def test_e2e_file_present(self):
        assert E2E_FILE.exists(), "test_e2e_full_audit.py missing"

    def test_e2e_has_10_test_functions(self):
        src = E2E_FILE.read_text()
        cnt = len(re.findall(r"^\s+def test_", src, re.MULTILINE))
        assert cnt >= 10, f"expected ≥10 e2e test functions, found {cnt}"


# ═════════════════════════════════════════════════════════════════
# G8 — Regressions
# ═════════════════════════════════════════════════════════════════
class TestG8_Regressions:
    def test_faq_returns_200_with_items(self):
        r = requests.get(f"{BASE_URL}/api/faq", timeout=15)
        assert r.status_code == 200, f"/api/faq → {r.status_code}"
        data = r.json()
        # Support either list or {items: [...]}
        items = data if isinstance(data, list) else data.get("items", [])
        assert len(items) > 0, "/api/faq returned empty payload"

    def test_admin_login_works(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
            timeout=15,
        )
        assert r.status_code == 200, f"admin login → {r.status_code}: {r.text[:200]}"
        j = r.json()
        assert "token" in j or "access_token" in j, f"no token in admin login response: {list(j.keys())}"

    def test_vip_upload_eligibility_subscription(self):
        # Login as VIP
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": VIP_EMAIL, "password": VIP_PASS},
            timeout=15,
        )
        assert r.status_code == 200, f"VIP login → {r.status_code}: {r.text[:200]}"
        tok = r.json().get("token") or r.json().get("access_token")
        assert tok, "no token in VIP login response"

        r2 = requests.get(
            f"{BASE_URL}/api/me/upload-eligibility",
            headers={"Authorization": f"Bearer {tok}"},
            timeout=15,
        )
        assert r2.status_code == 200, f"/api/me/upload-eligibility → {r2.status_code}"
        j = r2.json()
        assert j.get("eligible") is True, f"VIP not eligible: {j}"
        assert j.get("reason") == "subscription", f"VIP reason expected 'subscription', got {j.get('reason')}"

    def test_media_proxy_missing_key_404_json(self):
        r = requests.get(f"{BASE_URL}/api/media/does-not-exist-key.mp4", timeout=15)
        assert r.status_code == 404, f"/api/media/{{missing}} → {r.status_code}"
        # Should be JSON body
        try:
            j = r.json()
        except Exception:
            pytest.fail(f"media proxy 404 body is not JSON: {r.text[:200]}")
        assert isinstance(j, dict), f"media proxy 404 body not a dict: {j}"

    def test_no_chef_or_cooking_strings(self):
        """Zero matches for \bchef\b or Cooking in production code."""
        import subprocess
        # backend (excluding tests/__pycache__)
        r_be = subprocess.run(
            ["grep", "-rEn", "--include=*.py", r"\bchef\b|Cooking", "/app/backend"],
            capture_output=True, text=True,
        )
        be_hits = [
            ln for ln in r_be.stdout.splitlines()
            if "/tests/" not in ln and "__pycache__" not in ln
        ]
        assert be_hits == [], f"chef/Cooking in backend: {be_hits}"
        # frontend/src
        r_fe = subprocess.run(
            ["grep", "-rEn", "--include=*.js", "--include=*.jsx", r"\bchef\b|Cooking", "/app/frontend/src"],
            capture_output=True, text=True,
        )
        fe_hits = [ln for ln in r_fe.stdout.splitlines() if "node_modules" not in ln]
        assert fe_hits == [], f"chef/Cooking in frontend: {fe_hits}"
