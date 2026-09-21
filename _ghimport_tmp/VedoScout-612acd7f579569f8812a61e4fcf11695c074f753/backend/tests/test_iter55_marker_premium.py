"""
Session 125 (iter55) — verify 3 regressions fixed:

1. Marker + subject_crop URLs on report/status endpoints must be /api/media/reports/... paths (R2 proxy),
   NOT /api/uploads/... raw paths. Both URLs must fetch HTTP 200.
2. Premium/admin/vip users must see the FULL unlocked report — no LockedOverlay, no upsell.
   (Verified server-side by is_paid / manually_unlocked / role checks — client-side gating via role.)
3. Timer 'Elapsed · MM:SS' visibility during upload/analyze must be hidden for premium
   users (hideTimers prop) — verified via source code grep since we cannot upload a real video.

Regression:
- Free-tier / unpaid user still sees LockedOverlay (client-side check verified via source).
- Marker + subject_crop URLs are HTTP 200 via /api/media/reports/{id}/... proxy path for admin.
"""

import os
import re
import requests
import pytest
from pathlib import Path

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # Fall back to frontend/.env if backend didn't set it
    _fe_env = Path("/app/frontend/.env")
    if _fe_env.exists():
        for line in _fe_env.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break
BASE_URL = (BASE_URL or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing from env"

ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"
FREE_EMAIL = "free@elitescout.com"
FREE_PASSWORD = "Free@2026"
EXISTING_REPORT_ID = "0153da80-8192-4208-87ac-5e7f6d38eeb5"


# ---------- helpers ----------
def _login(email: str, password: str) -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=15,
    )
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token")
    assert tok, "no access_token in login response"
    return tok


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def free_token():
    try:
        return _login(FREE_EMAIL, FREE_PASSWORD)
    except AssertionError as e:
        pytest.skip(f"free user login failed: {e}")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def free_headers(free_token):
    return {"Authorization": f"Bearer {free_token}"}


# =====================================================================
# Backend API tests
# =====================================================================
class TestReportMarkerFullEndpoint:
    """GET /api/reports/{id} — admin gets marker_url + subject_crop_url as /api/media/... path."""

    def test_admin_can_fetch_report(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/reports/{EXISTING_REPORT_ID}", headers=admin_headers, timeout=15)
        assert r.status_code == 200, f"admin GET report failed: {r.status_code} {r.text[:200]}"

    def test_marker_url_is_r2_proxy(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/reports/{EXISTING_REPORT_ID}", headers=admin_headers, timeout=15)
        d = r.json()
        mu = d.get("marker_url")
        assert mu, "marker_url missing from report response"
        # MUST NOT be raw uploads path
        assert not mu.startswith("/api/uploads/"), f"marker_url still points to legacy uploads: {mu}"
        # MUST be R2 proxy path or full URL
        assert mu.startswith("/api/media/reports/") or mu.startswith("http"), (
            f"marker_url not an R2 proxy path: {mu}"
        )

    def test_subject_crop_url_is_r2_proxy(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/reports/{EXISTING_REPORT_ID}", headers=admin_headers, timeout=15)
        d = r.json()
        sc = d.get("subject_crop_url")
        assert sc, "subject_crop_url missing from report response"
        assert not sc.startswith("/api/uploads/"), f"subject_crop_url still legacy: {sc}"
        assert sc.startswith("/api/media/reports/") or sc.startswith("http"), (
            f"subject_crop_url not an R2 proxy path: {sc}"
        )

    def test_admin_report_is_fully_populated(self, admin_headers):
        """Admin should see the full report — preview + full_report both present."""
        r = requests.get(f"{BASE_URL}/api/reports/{EXISTING_REPORT_ID}", headers=admin_headers, timeout=15)
        d = r.json()
        # The server serialization includes full_report when the caller is admin or the report is unlocked.
        assert d.get("preview"), "preview missing"
        assert d.get("full_report"), "full_report missing for admin (expected because admin bypasses paywall)"


class TestStatusEndpoint:
    """GET /api/reports/{id}/status — must also return R2 proxy paths for marker + subject_crop."""

    def test_status_returns_marker_url_r2(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/reports/{EXISTING_REPORT_ID}/status",
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") == "ready"
        mu = d.get("marker_url")
        assert mu, "marker_url missing from /status response"
        assert not mu.startswith("/api/uploads/"), f"status marker_url still legacy: {mu}"
        assert mu.startswith("/api/media/reports/") or mu.startswith("http")

    def test_status_returns_subject_crop_url(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/reports/{EXISTING_REPORT_ID}/status",
            headers=admin_headers,
            timeout=15,
        )
        d = r.json()
        sc = d.get("subject_crop_url")
        assert sc, "subject_crop_url missing from /status response"
        assert not sc.startswith("/api/uploads/"), f"status subject_crop_url still legacy: {sc}"
        assert sc.startswith("/api/media/reports/") or sc.startswith("http")


class TestMediaProxyReturnsImages:
    """/api/media/reports/... paths must resolve to actual image bytes (HTTP 200 + image/jpeg)."""

    def _fetch_and_assert(self, headers, url_path, min_bytes=500):
        # Absolute path (starts with /) → prefix BASE_URL. Full URL passes through.
        target = url_path if url_path.startswith("http") else f"{BASE_URL}{url_path}"
        r = requests.get(target, headers=headers, timeout=20, allow_redirects=True)
        assert r.status_code == 200, f"{url_path} → {r.status_code} {r.text[:150]}"
        ct = r.headers.get("content-type", "")
        assert ct.startswith("image/"), f"{url_path} content-type not image/*: {ct}"
        assert len(r.content) >= min_bytes, f"{url_path} suspiciously small ({len(r.content)}B)"

    def test_marker_image_fetches(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/reports/{EXISTING_REPORT_ID}",
            headers=admin_headers,
            timeout=15,
        )
        mu = r.json().get("marker_url")
        assert mu
        self._fetch_and_assert(admin_headers, mu, min_bytes=1000)

    def test_subject_crop_image_fetches(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/reports/{EXISTING_REPORT_ID}",
            headers=admin_headers,
            timeout=15,
        )
        sc = r.json().get("subject_crop_url")
        assert sc
        # subject crops can be tiny (a few KB) — lower floor
        self._fetch_and_assert(admin_headers, sc, min_bytes=500)


class TestFreeUserRegression:
    """Regression: free-tier user still sees preview only (no full_report in the response
    unless they've paid). This mirrors the server-side check that ultimately drives the
    LockedOverlay on the frontend."""

    def test_free_user_can_login(self, free_headers):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=free_headers, timeout=15)
        assert r.status_code == 200, f"auth/me failed: {r.status_code} {r.text[:200]}"
        me = r.json()
        assert me.get("role") == "user", f"expected role=user, got {me.get('role')}"

    def test_free_user_report_gating(self, free_headers):
        """Fetching admin's report as a free user is expected to 403 (not owner)."""
        r = requests.get(
            f"{BASE_URL}/api/reports/{EXISTING_REPORT_ID}",
            headers=free_headers,
            timeout=15,
        )
        # Server MUST NOT let a random free user see someone else's report
        assert r.status_code in (403, 404), f"free user got someone else's report: {r.status_code}"


# =====================================================================
# Frontend source-code grep verification (timer fix + role gating)
# =====================================================================
class TestFrontendSourceInvariants:
    """The 3 code-level assertions the spec asked us to verify by grepping source."""

    def test_upload_page_passes_hidetimers(self):
        src = Path("/app/frontend/src/pages/UploadPage.jsx").read_text()
        # `isPaidTier` computed via the shared isPremiumUser helper (role OR subscription_tier)
        assert re.search(r"isPaidTier\s*=\s*isPremiumUser\(\s*user\s*\)", src), (
            "isPaidTier not derived from isPremiumUser helper"
        )
        helper = Path("/app/frontend/src/lib/premium.js").read_text()
        assert '"admin"' in helper and '"premium"' in helper and '"vip"' in helper and '"scout"' in helper, (
            "premium.js role whitelist incomplete"
        )
        assert "subscription_tier" in helper, "premium.js must also honor subscription_tier"
        # `hideTimers={isPaidTier}` passed to PrecisionScanOverlay
        assert "hideTimers={isPaidTier}" in src, "UploadPage does not forward hideTimers to PrecisionScanOverlay"

    def test_precision_overlay_reads_hidetimers(self):
        src = Path("/app/frontend/src/components/PrecisionScanOverlay.jsx").read_text()
        # Accepts prop
        assert "hideTimers" in src, "PrecisionScanOverlay does not accept hideTimers prop"
        # Renders 'Working in the background' when true, else 'Elapsed · ...'
        assert '"Working in the background"' in src, "background-string not present in overlay"
        assert "Elapsed ·" in src, "Elapsed timer string missing"
        # The 'hideTimers ? "Working in the background" : `Elapsed · …`' ternary must be present
        assert re.search(r"hideTimers\s*\?\s*\"Working in the background\"\s*:", src), (
            "hideTimers ternary not gating the Elapsed timer"
        )

    def test_report_page_role_gates_unlocked(self):
        src = Path("/app/frontend/src/pages/ReportPage.jsx").read_text()
        # premiumRole computed via the shared isPremiumUser helper (role OR subscription_tier)
        assert re.search(r"premiumRole\s*=\s*isPremiumUser\(\s*user\s*\)", src), (
            "premiumRole not derived from isPremiumUser helper"
        )
        # unlocked = is_paid || manually_unlocked || premiumRole
        assert re.search(
            r"unlocked\s*=\s*is_paid\s*\|\|\s*manually_unlocked\s*\|\|\s*premiumRole",
            src,
        ), "unlocked flag not combining is_paid/manually_unlocked/premiumRole"
        # LockedOverlay is gated on !unlocked
        assert re.search(r"!unlocked\s*&&\s*\(\s*\n\s*<LockedOverlay", src) or re.search(
            r"!unlocked\s*&&\s*<LockedOverlay", src
        ), "LockedOverlay is NOT gated on !unlocked"


# =====================================================================
# Backend source-code grep verification (marker resolver + R2 flush)
# =====================================================================
class TestBackendSourceInvariants:
    def test_resolvers_exist(self):
        src = Path("/app/backend/server.py").read_text()
        assert "def _resolve_marker_url(" in src, "_resolve_marker_url helper missing"
        assert "def _resolve_subject_crop_url(" in src, "_resolve_subject_crop_url helper missing"
        # Overrides trump legacy /api/uploads/ path
        assert 'doc.get("marker_url_override")' in src
        assert 'doc.get("subject_crop_url_override")' in src

    def test_status_endpoint_uses_resolvers(self):
        src = Path("/app/backend/server.py").read_text()
        # /reports/{id}/status includes both resolver outputs
        # Find the status endpoint block and check both keys are set inside
        m = re.search(
            r"@api_router\.get\(\"/reports/\{report_id\}/status\"\).*?return out",
            src,
            re.DOTALL,
        )
        assert m, "status endpoint block not found"
        block = m.group(0)
        assert '"marker_url": _resolve_marker_url(doc)' in block, "status endpoint missing marker_url resolver"
        assert '"subject_crop_url": _resolve_subject_crop_url(doc)' in block, (
            "status endpoint missing subject_crop_url resolver"
        )

    def test_serialize_report_uses_resolvers(self):
        src = Path("/app/backend/server.py").read_text()
        m = re.search(r"async def _serialize_report\(doc:.*?return out", src, re.DOTALL)
        assert m, "_serialize_report not found"
        block = m.group(0)
        assert '"marker_url": _resolve_marker_url(doc)' in block
        assert '"subject_crop_url": _resolve_subject_crop_url(doc)' in block

    def test_r2_flush_covers_marker_and_subject_crop(self):
        src = Path("/app/backend/server.py").read_text()
        # Both marker + subject_crop must be uploaded to R2 inside _flush_preview_artifacts_to_r2
        m = re.search(r"async def _flush_preview_artifacts_to_r2.*?(?=\nasync def |\ndef )", src, re.DOTALL)
        assert m, "_flush_preview_artifacts_to_r2 not found"
        block = m.group(0)
        assert '"marker_url_override"' in block, "R2 flush does not set marker_url_override"
        assert '"subject_crop_url_override"' in block, "R2 flush does not set subject_crop_url_override"
