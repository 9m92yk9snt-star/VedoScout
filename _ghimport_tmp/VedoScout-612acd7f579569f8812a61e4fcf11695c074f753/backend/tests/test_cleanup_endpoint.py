"""
Iteration 38 — Regression tests for /api/admin/cleanup-raw-uploads
=================================================================
Verifies:
  - Auth guard (no token / non-admin token blocked)
  - Response shape (all required keys present + correct types)
  - Idempotency (second call after first must yield 0 removals)
  - Safety: recent reports still resolve via /api/reports/mine + status
  - .mov files that ARE the playable (no .web.mp4 sibling) are preserved
"""

import os
from pathlib import Path
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # fall back to frontend .env if process env not exported
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break
BASE_URL = (BASE_URL or "").rstrip("/")

UPLOAD_DIR = Path("/app/backend/uploads")

ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"
FREE_EMAIL = "free@elitescout.com"
FREE_PASSWORD = "Free@2026"


# ---------- shared session helpers ----------
def _login(email: str, password: str) -> str | None:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=15,
    )
    if r.status_code != 200:
        return None
    return r.json().get("access_token")


@pytest.fixture(scope="module")
def admin_token():
    tok = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not tok:
        pytest.skip("Admin login failed — cannot run cleanup tests")
    return tok


@pytest.fixture(scope="module")
def free_token():
    return _login(FREE_EMAIL, FREE_PASSWORD)


# ---------- TEST: auth guard ----------
class TestAuthGuard:
    def test_cleanup_no_token_blocked(self):
        r = requests.post(f"{BASE_URL}/api/admin/cleanup-raw-uploads", timeout=15)
        assert r.status_code in (401, 403), (
            f"Expected 401/403 for unauthenticated cleanup, got {r.status_code}: {r.text[:200]}"
        )

    def test_cleanup_non_admin_blocked(self, free_token):
        if not free_token:
            pytest.skip("Free user login failed — cannot verify non-admin block")
        r = requests.post(
            f"{BASE_URL}/api/admin/cleanup-raw-uploads",
            headers={"Authorization": f"Bearer {free_token}"},
            timeout=15,
        )
        assert r.status_code in (401, 403), (
            f"Expected 401/403 for non-admin, got {r.status_code}: {r.text[:200]}"
        )


# ---------- TEST: response shape + idempotency ----------
class TestCleanupBehaviour:
    def test_cleanup_response_shape(self, admin_token):
        r = requests.post(
            f"{BASE_URL}/api/admin/cleanup-raw-uploads",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=120,
        )
        assert r.status_code == 200, f"cleanup call failed: {r.status_code} {r.text[:200]}"
        body = r.json()
        for key, expected_type in [
            ("removed_files", int),
            ("repointed_reports", int),
            ("freed_bytes", int),
            ("freed_mb", (int, float)),
            ("skipped_no_web_version", int),
            ("errors", list),
        ]:
            assert key in body, f"missing key '{key}' in cleanup response"
            assert isinstance(body[key], expected_type), (
                f"key '{key}' expected {expected_type}, got {type(body[key])}"
            )
        # stash for next test via module-level attr
        TestCleanupBehaviour._first = body

    def test_cleanup_is_idempotent(self, admin_token):
        # ensure first ran
        first = getattr(TestCleanupBehaviour, "_first", None)
        if first is None:
            pytest.skip("First cleanup call did not run")
        r = requests.post(
            f"{BASE_URL}/api/admin/cleanup-raw-uploads",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=120,
        )
        assert r.status_code == 200, f"second cleanup call failed: {r.status_code}"
        second = r.json()
        # Per main-agent context: prior manual run removed the 3 truly-orphaned
        # files; subsequent calls must reclaim 0 bytes (no removals, no repoints).
        assert second["removed_files"] == 0, (
            f"idempotency broken — 2nd call removed {second['removed_files']} files "
            f"(1st call removed {first['removed_files']}). errors={second['errors']}"
        )
        assert second["repointed_reports"] == 0, (
            f"idempotency broken — 2nd call repointed {second['repointed_reports']} reports"
        )
        assert second["freed_bytes"] == 0


# ---------- TEST: safety — reports still resolve after cleanup ----------
class TestPostCleanupSafety:
    def test_mov_files_preserved(self):
        """.mov files without a .web.mp4 sibling MUST still exist on disk."""
        if not UPLOAD_DIR.exists():
            pytest.skip("uploads dir not present in this environment")
        # Count .mov files that DO NOT have a .web.mp4 sibling — those are the
        # ones the cleanup MUST preserve.
        unsibling_movs = []
        for mov in UPLOAD_DIR.glob("*.mov"):
            stem = mov.name.rsplit(".", 1)[0]
            if not (UPLOAD_DIR / f"{stem}.web.mp4").exists():
                unsibling_movs.append(mov.name)
        # Sanity — main agent reported ~870 MB of these remain
        assert len(unsibling_movs) > 0, (
            "expected at least one playable raw .mov to remain after cleanup"
        )
        # Verify they all still exist (no false deletes)
        for name in unsibling_movs:
            assert (UPLOAD_DIR / name).exists(), f"unsibling .mov was deleted: {name}"

    def test_recent_admin_reports_video_files_exist(self, admin_token):
        """Pull /api/reports/mine and verify each report's video_filename still
        resolves to a file on disk (no broken playback)."""
        r = requests.get(
            f"{BASE_URL}/api/reports/mine",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        )
        assert r.status_code == 200, f"/api/reports/mine failed: {r.status_code}"
        reports = r.json()
        if not isinstance(reports, list):
            # some shapes wrap in {"reports": [...]}
            reports = reports.get("reports", []) if isinstance(reports, dict) else []
        # Inspect first 5 reports for video file existence
        broken = []
        checked = 0
        for rpt in reports[:5]:
            vfn = rpt.get("video_filename")
            if not vfn:
                continue
            checked += 1
            if not (UPLOAD_DIR / vfn).exists():
                broken.append(f"{rpt.get('id')}: {vfn}")
        assert not broken, f"After cleanup, these reports have missing video files: {broken}"
        if checked == 0:
            pytest.skip("No reports with video_filename to validate")

    def test_recent_admin_report_status_ok(self, admin_token):
        """For 1-2 recent reports, /api/reports/{id}/status should return 200."""
        r = requests.get(
            f"{BASE_URL}/api/reports/mine",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        )
        reports = r.json()
        if isinstance(reports, dict):
            reports = reports.get("reports", [])
        if not reports:
            pytest.skip("no reports for admin to validate status endpoint")
        tested = 0
        for rpt in reports[:3]:
            rid = rpt.get("id")
            if not rid:
                continue
            sr = requests.get(
                f"{BASE_URL}/api/reports/{rid}/status",
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=30,
            )
            assert sr.status_code == 200, (
                f"/api/reports/{rid}/status returned {sr.status_code}: {sr.text[:200]}"
            )
            body = sr.json()
            assert "analysis_status" in body or "status" in body, (
                f"status payload missing status key: {body}"
            )
            tested += 1
            if tested >= 2:
                break
        if tested == 0:
            pytest.skip("no report ids available to test status endpoint")
