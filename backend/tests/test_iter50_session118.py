"""Iteration 50 — Session 118 P0 fixes verification.

Fixes covered:
- E1: R2 flush BEFORE analysis_status='ready' (race condition fix)
- E2: 15-min wall-clock timeout wrapper around analyze_preview_task
- E3: "Cooking" → "Analyzing" in BackgroundAnalysisTracker.jsx
- Regression: landing/admin/FAQ still 200; testvip eligibility=true
- E2E sanity: upload tiny testsrc mp4 as testvip; poll status; expect progress_step>2
  OR failure with clear analysis_error within 60s (never stuck at step<=2).

Backend-only per review request. Frontend text change (E3) verified via grep.
"""

import os
import re
import subprocess
import time
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback from frontend .env for pytest runs
    env_path = Path("/app/frontend/.env")
    for line in env_path.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
            break

VIP_EMAIL = "testvip@scoutmeplay.com"
VIP_PASSWORD = "TestVip@2026!"
ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"

SERVER_PY = Path("/app/backend/server.py")
TRACKER_JSX = Path("/app/frontend/src/components/BackgroundAnalysisTracker.jsx")


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def server_src() -> str:
    return SERVER_PY.read_text()


@pytest.fixture(scope="session")
def tracker_src() -> str:
    return TRACKER_JSX.read_text()


@pytest.fixture(scope="session")
def vip_token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": VIP_EMAIL, "password": VIP_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"VIP login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"No token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="session")
def admin_token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json().get("token") or r.json().get("access_token")


# ---------- E1: R2 flush BEFORE status=ready ----------
class TestE1RaceConditionFix:
    def test_flush_before_status_ready(self, server_src):
        """Verify R2 flush happens BEFORE status is set to 'ready'."""
        flush_idx = server_src.find("await _flush_preview_artifacts_to_r2(report_id)")
        assert flush_idx > 0, "_flush_preview_artifacts_to_r2 call not found inside analyze_preview_task"
        # Find the analysis_status: 'ready' update AFTER the flush
        after_flush = server_src[flush_idx:]
        ready_idx = after_flush.find('"analysis_status": "ready"')
        assert ready_idx > 0, "analysis_status='ready' update not found AFTER R2 flush"
        # And confirm no earlier ready update in the same function (analyze_preview_task)
        # by ensuring the first occurrence of "analysis_status": "ready" in the func is AFTER flush
        func_start = server_src.find("async def analyze_preview_task(")
        func_end = server_src.find("async def ", func_start + 10)
        func_body = server_src[func_start:func_end]
        # In-function positions
        in_func_ready = func_body.find('"analysis_status": "ready"')
        in_func_flush = func_body.find("await _flush_preview_artifacts_to_r2(report_id)")
        assert in_func_flush > 0, "flush call not in analyze_preview_task body"
        assert in_func_ready > 0, "ready update not in analyze_preview_task body"
        assert in_func_flush < in_func_ready, (
            f"R2 flush at {in_func_flush} must come BEFORE ready update at {in_func_ready} "
            "— race condition still present!"
        )


# ---------- E2: Wall-clock timeout wrapper ----------
class TestE2TimeoutWrapper:
    def test_wrapper_function_defined(self, server_src):
        assert "async def _analyze_preview_task_with_timeout(report_id: str):" in server_src

    def test_wrapper_uses_asyncio_wait_for_with_900s(self, server_src):
        pat = re.compile(
            r"asyncio\.wait_for\(\s*analyze_preview_task\(report_id\)\s*,\s*timeout\s*=\s*900\s*\)"
        )
        assert pat.search(server_src), "asyncio.wait_for(analyze_preview_task(...), timeout=900) not found"

    def test_timeout_marks_failed_and_refunds(self, server_src):
        # Find wrapper body
        start = server_src.find("async def _analyze_preview_task_with_timeout")
        end = server_src.find("async def ", start + 10)
        body = server_src[start:end]
        assert "asyncio.TimeoutError" in body
        assert '"analysis_status": "failed"' in body
        assert "_refund_upload_eligibility" in body

    def test_background_task_uses_wrapper(self, server_src):
        assert "background.add_task(_analyze_preview_task_with_timeout, report_id)" in server_src

    def test_no_direct_background_call_to_analyze_preview_task(self, server_src):
        # There should be 0 direct background.add_task(analyze_preview_task, ...) calls
        pat = re.compile(r"background\.add_task\(\s*analyze_preview_task\b")
        matches = pat.findall(server_src)
        assert len(matches) == 0, f"Found {len(matches)} direct background.add_task(analyze_preview_task) — must all go through wrapper"

    def test_asyncio_imported(self, server_src):
        assert re.search(r"^import asyncio$", server_src, re.M), "asyncio not imported at top of server.py"


# ---------- E3: Cooking → Analyzing rename ----------
class TestE3StatusPillRename:
    def test_no_cooking_in_frontend(self):
        result = subprocess.run(
            ["grep", "-rniI", "cooking", "/app/frontend/src/"],
            capture_output=True, text=True,
        )
        # Filter out any legitimate matches (there should be none)
        hits = [line for line in result.stdout.splitlines() if line.strip()]
        assert len(hits) == 0, f"Found 'cooking' still present in frontend: {hits}"

    def test_analyzing_present_in_tracker(self, tracker_src):
        assert "Step {step} of 5 · Analyzing" in tracker_src or "Step {step} of 5" in tracker_src and "Analyzing" in tracker_src

    def test_stage_labels_updated(self, tracker_src):
        # New STAGE_LABELS content
        assert '1: "Receiving' in tracker_src
        assert '2: "Preparing your video"' in tracker_src
        assert '3: "Checking the content"' in tracker_src
        assert '4: "Writing the scout report"' in tracker_src
        assert '5: "Finalising"' in tracker_src


# ---------- Regression ----------
class TestRegression:
    def test_landing_faq_200(self):
        r = requests.get(f"{BASE_URL}/api/faq", timeout=15)
        assert r.status_code == 200

    def test_admin_login_200(self, admin_token):
        assert admin_token

    def test_vip_login_and_eligibility(self, vip_token):
        r = requests.get(
            f"{BASE_URL}/api/me/upload-eligibility",
            headers={"Authorization": f"Bearer {vip_token}"},
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("eligible") is True
        # reason should be subscription (VIP) or prepaid (fallback)
        assert data.get("reason") in ("subscription", "prepaid"), f"Unexpected reason: {data}"


# ---------- E2E sanity ----------
class TestE2ESanity:
    """Upload a 5-second testsrc mp4 as testvip and poll status.
    Success: progress_step advances past 2 within 60s OR analysis_status becomes
    'failed' with a clear error (Gemini rejecting synthetic testsrc video as
    'not football' is acceptable). Failure: stuck at step<=2 for full 60s.
    """

    @pytest.fixture(scope="class")
    def ffmpeg_bin(self):
        from importlib import import_module
        import sys
        sys.path.insert(0, "/app/backend")
        mb = import_module("media_binaries")
        return mb.FFMPEG_BIN

    @pytest.fixture(scope="class")
    def tiny_mp4(self, ffmpeg_bin):
        out = Path("/tmp/tinytest.mp4")
        if out.exists():
            out.unlink()
        subprocess.run(
            [ffmpeg_bin, "-f", "lavfi", "-i", "testsrc=duration=5:size=320x240:rate=30",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(out)],
            check=True, capture_output=True,
        )
        assert out.exists() and out.stat().st_size > 1000
        return out

    @pytest.fixture(scope="class")
    def marker_jpg(self):
        # 1x1 JPEG (minimal valid JFIF)
        p = Path("/tmp/tinymarker.jpg")
        # Use ffmpeg to make it — reliable
        from importlib import import_module
        import sys
        sys.path.insert(0, "/app/backend")
        mb = import_module("media_binaries")
        subprocess.run(
            [mb.FFMPEG_BIN, "-f", "lavfi", "-i", "color=c=red:s=32x32:d=0.1",
             "-frames:v", "1", "-y", str(p)],
            check=True, capture_output=True,
        )
        assert p.exists() and p.stat().st_size > 100
        return p

    def test_upload_and_poll(self, vip_token, admin_token, tiny_mp4, marker_jpg):
        # Upload
        files = {
            "file": ("tinytest.mp4", tiny_mp4.open("rb"), "video/mp4"),
            "marker_image": ("marker.jpg", marker_jpg.open("rb"), "image/jpeg"),
        }
        data = {
            "marker_timestamp": "0.0",
            "marker_box": '{"x":0.4,"y":0.3,"w":0.2,"h":0.4}',
            "player_name": "TEST_iter50",
            "age": "16",
            "position": "AMF",
            "preferred_foot": "right",
            "current_club": "TEST_FC",
            "video_type": "match",
            "description": "iter50 sanity synthetic testsrc",
        }
        r = requests.post(
            f"{BASE_URL}/api/reports/upload",
            headers={"Authorization": f"Bearer {vip_token}"},
            files=files, data=data, timeout=60,
        )
        assert r.status_code in (200, 201), f"upload failed: {r.status_code} {r.text[:500]}"
        rd = r.json()
        report_id = rd.get("report_id") or rd.get("id")
        assert report_id, f"No report_id in upload response: {rd}"
        print(f"[iter50] created report_id={report_id}")

        try:
            # Poll every 3s up to 60s
            deadline = time.time() + 60
            max_step_seen = 0
            last_status = None
            last_err = None
            while time.time() < deadline:
                sr = requests.get(
                    f"{BASE_URL}/api/reports/{report_id}/status",
                    headers={"Authorization": f"Bearer {vip_token}"},
                    timeout=15,
                )
                assert sr.status_code == 200, f"status endpoint failed: {sr.status_code} {sr.text}"
                sdata = sr.json()
                step = int(sdata.get("progress_step") or 0)
                status = sdata.get("analysis_status")
                last_status = status
                last_err = sdata.get("analysis_error")
                max_step_seen = max(max_step_seen, step)
                print(f"[iter50] t={int(time.time())} status={status} step={step} err={last_err}")
                if status in ("ready", "failed"):
                    break
                if step > 2:
                    break
                time.sleep(3)

            # Assertion: EITHER step advanced past 2 OR task failed with clear error
            passed = (max_step_seen > 2) or (last_status == "failed" and last_err) or (last_status == "ready")
            assert passed, (
                f"Task stuck: max_step_seen={max_step_seen} last_status={last_status} "
                f"last_err={last_err} — indicates pipeline hang (ffmpeg or Gemini)"
            )
            print(f"[iter50] E2E sanity OK: max_step={max_step_seen} status={last_status} err={last_err}")

        finally:
            # TEARDOWN: delete report via admin
            try:
                dr = requests.delete(
                    f"{BASE_URL}/api/admin/reports/{report_id}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    timeout=15,
                )
                print(f"[iter50] teardown delete status={dr.status_code}")
            except Exception as e:
                print(f"[iter50] teardown failed: {e}")
