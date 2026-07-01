"""Iteration 48 — P0 production bug fixes verification.

Bug A: VIP paywall — /api/me/upload-eligibility must return eligible=true reason=subscription
       for VIP users regardless of subscription.status being 'active' OR 'trialing'.
       POST /api/reports/upload must NOT return 402 PREPAY_REQUIRED for VIP.

Bug B: Video playback — transcode_to_web_mp4 must include -pix_fmt yuv420p so iPhone
       HEVC 10-bit videos get re-encoded to browser-compatible 8-bit yuv420p.
       (Verified via source grep; end-to-end transcode is too slow for CI.)

Bug C: Avatar upload — POST /api/profile/avatar/upload must return R2 URL
       (/api/media/avatars/...), GET /api/profile/me echoes it, HTTP GET on that URL
       returns 200 image/jpeg, DELETE /api/profile/avatar clears it.

Regression: landing page, admin login, /api/faq.
"""
from __future__ import annotations

import io
import os
import re
import time
from pathlib import Path

import pytest
import requests


def _load_env_from(dotenv_path: str) -> None:
    """Populate os.environ from a .env file if the key isn't already set.
    We can't rely on load_dotenv() alone because REACT_APP_BACKEND_URL lives
    in /app/frontend/.env and MONGO_URL/DB_NAME live in /app/backend/.env."""
    try:
        with open(dotenv_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                os.environ.setdefault(k, v)
    except FileNotFoundError:
        pass


_load_env_from("/app/frontend/.env")
_load_env_from("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

VIP_EMAIL = "testvip@scoutmeplay.com"
VIP_PASSWORD = "TestVip@2026!"
ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"

SERVER_PY = Path("/app/backend/server.py")


# ---------------------- Fixtures ----------------------
@pytest.fixture(scope="session")
def vip_token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": VIP_EMAIL, "password": VIP_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"VIP login failed: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def vip_headers(vip_token) -> dict:
    return {"Authorization": f"Bearer {vip_token}"}


@pytest.fixture(scope="session")
def admin_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------------- Bug A — VIP paywall ----------------------
class TestBugAVipPaywall:
    """VIP subscribers must never hit the $159 paywall."""

    def test_upload_eligibility_active_vip(self, vip_headers):
        """Baseline: VIP with subscription.status='active' → eligible=true reason=subscription."""
        r = requests.get(f"{BASE_URL}/api/me/upload-eligibility", headers=vip_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["eligible"] is True, f"VIP not eligible: {data}"
        assert data["reason"] == "subscription", f"Expected reason=subscription, got: {data}"
        assert data.get("subscription", {}).get("tier") == "vip", data

    def test_upload_eligibility_trialing_vip(self, vip_headers):
        """Patch Mongo subscription.status='trialing' → must still be eligible=true reason=subscription.
        This is the regression fix — previously the strict status=='active' check missed trialing.
        """
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient

        mongo_url = os.environ["MONGO_URL"]
        db_name = os.environ["DB_NAME"]

        async def _flip(status: str):
            cli = AsyncIOMotorClient(mongo_url)
            try:
                await cli[db_name].users.update_one(
                    {"email": VIP_EMAIL},
                    {"$set": {"subscription.status": status}},
                )
            finally:
                cli.close()

        try:
            asyncio.get_event_loop().run_until_complete(_flip("trialing"))
        except RuntimeError:
            asyncio.run(_flip("trialing"))

        try:
            r = requests.get(f"{BASE_URL}/api/me/upload-eligibility", headers=vip_headers, timeout=15)
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["eligible"] is True, f"VIP (trialing) not eligible — REGRESSION: {data}"
            assert data["reason"] == "subscription", f"Expected reason=subscription for trialing, got: {data}"
            assert data.get("subscription", {}).get("tier") == "vip", data
        finally:
            # Restore to active
            try:
                asyncio.get_event_loop().run_until_complete(_flip("active"))
            except RuntimeError:
                asyncio.run(_flip("active"))

    def test_upload_vip_no_prepay_required(self, vip_headers):
        """POST /api/reports/upload with tiny MP4 as VIP must NOT return 402 PREPAY_REQUIRED.
        We use a minimal payload — Gemini analysis will likely fail (bad video), but the
        payment gate is what we're testing. The report row should be created with is_paid=true.
        """
        # Copy an existing real football clip as the source (a valid MP4 shape avoids
        # early 400s from python-multipart / ffprobe). Fallback to raw bytes if none.
        candidate = None
        for p in Path("/app/backend/uploads").glob("*.mp4"):
            if p.stat().st_size < 5 * 1024 * 1024:  # under 5 MB
                candidate = p
                break
        if candidate is None:
            pytest.skip("No small MP4 available in /app/backend/uploads to test upload gate")

        # Also grab a small JPG as the marker
        marker = None
        for p in Path("/app/backend/uploads").glob("*.jpg"):
            if p.stat().st_size < 2 * 1024 * 1024:
                marker = p
                break
        if marker is None:
            pytest.skip("No small JPG marker available")

        with candidate.open("rb") as fv, marker.open("rb") as fm:
            files = {
                "file": ("TEST_iter48.mp4", fv, "video/mp4"),
                "marker_image": ("TEST_iter48.jpg", fm, "image/jpeg"),
            }
            data = {
                "player_name": "TEST_iter48_vip",
                "age": "18",
                "position": "midfielder",
                "preferred_foot": "right",
                "video_type": "match",
                "description": "iter48 gate test",
                "marker_timestamp": "0.5",
                "marker_box": '{"x":0.3,"y":0.3,"w":0.2,"h":0.4}',
            }
            r = requests.post(
                f"{BASE_URL}/api/reports/upload",
                headers=vip_headers,
                files=files,
                data=data,
                timeout=120,
            )
        # KEY ASSERTION: not a 402 PREPAY_REQUIRED
        assert r.status_code != 402, (
            f"REGRESSION: VIP hit paywall! status={r.status_code} body={r.text[:400]}"
        )
        assert r.status_code in (200, 201, 202), f"Unexpected: {r.status_code} {r.text[:400]}"
        body = r.json()
        report_id = body.get("report_id") or body.get("id")
        assert report_id, f"No report_id in response: {body}"

        # Verify is_paid=true on the report doc — best-effort via /api/reports/{id}
        s = requests.get(
            f"{BASE_URL}/api/reports/{report_id}", headers=vip_headers, timeout=15
        )
        if s.status_code == 200:
            rep = s.json()
            assert rep.get("is_paid") is True, f"Report should be is_paid=true for VIP, got: {rep.get('is_paid')}"

        # CLEANUP: admin delete
        try:
            adm = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=15,
            )
            atok = adm.json()["access_token"]
            requests.delete(
                f"{BASE_URL}/api/admin/reports/{report_id}",
                headers={"Authorization": f"Bearer {atok}"},
                timeout=15,
            )
        except Exception:
            pass


# ---------------------- Bug B — pix_fmt yuv420p ----------------------
class TestBugBPixFmt:
    """The transcoder must force 8-bit yuv420p output for iPhone HEVC 10-bit videos."""

    def test_transcode_to_web_mp4_has_pix_fmt_yuv420p(self):
        src = SERVER_PY.read_text()
        # Locate the transcode_to_web_mp4 function body
        m = re.search(
            r"def\s+transcode_to_web_mp4\b.*?(?=\ndef\s|\nclass\s|\n@api_router|\Z)",
            src,
            flags=re.DOTALL,
        )
        assert m, "Could not locate transcode_to_web_mp4 function in server.py"
        body = m.group(0)
        assert "yuv420p" in body, "REGRESSION: -pix_fmt yuv420p missing from transcode_to_web_mp4"
        assert "-pix_fmt" in body, "REGRESSION: -pix_fmt flag missing from transcode_to_web_mp4"


# ---------------------- Bug C — Avatar upload → R2 ----------------------
class TestBugCAvatarR2:
    """Avatar upload must be pushed to R2 and served via /api/media/avatars/..."""

    def _make_jpeg(self) -> bytes:
        """Build a 400x400 red JPEG using PIL (Pillow is a project dep)."""
        from PIL import Image  # noqa: WPS433
        buf = io.BytesIO()
        Image.new("RGB", (400, 400), (255, 0, 0)).save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    def test_avatar_upload_returns_r2_media_url(self, vip_headers):
        payload = self._make_jpeg()
        assert len(payload) > 500, "JPEG payload suspiciously small"

        # Clean any prior avatar first (best effort)
        requests.delete(f"{BASE_URL}/api/profile/avatar", headers=vip_headers, timeout=15)

        files = {"file": ("TEST_avatar.jpg", payload, "image/jpeg")}
        r = requests.post(
            f"{BASE_URL}/api/profile/avatar/upload",
            headers=vip_headers,
            files=files,
            timeout=30,
        )
        assert r.status_code == 200, f"Avatar upload failed: {r.status_code} {r.text[:300]}"
        data = r.json()
        avatar_url = data.get("avatar_url")
        assert avatar_url, f"No avatar_url in response: {data}"
        # KEY ASSERTION: R2 proxy path, not legacy local disk path
        assert avatar_url.startswith("/api/media/avatars/"), (
            f"REGRESSION: avatar_url not R2-backed. Got: {avatar_url} "
            f"(should start with /api/media/avatars/, NOT /api/uploads/avatars/)"
        )

        # (b) /api/profile/me returns the same URL
        me = requests.get(f"{BASE_URL}/api/profile/me", headers=vip_headers, timeout=15)
        assert me.status_code == 200, me.text
        me_data = me.json()
        assert me_data.get("avatar_url") == avatar_url, (
            f"/api/profile/me avatar_url mismatch: got {me_data.get('avatar_url')} expected {avatar_url}"
        )

        # (c) HTTP GET on avatar_url returns 200 image/jpeg with correct size
        full = f"{BASE_URL}{avatar_url}" if avatar_url.startswith("/") else avatar_url
        g = requests.get(full, headers=vip_headers, timeout=30)
        assert g.status_code == 200, f"avatar GET failed: {g.status_code} url={full}"
        ct = g.headers.get("content-type", "").lower()
        assert "image/jpeg" in ct or "image/jpg" in ct, f"Wrong content-type: {ct}"
        assert len(g.content) == len(payload) or abs(len(g.content) - len(payload)) < 200, (
            f"Avatar size mismatch: uploaded {len(payload)} vs served {len(g.content)}"
        )

    def test_avatar_delete_clears_it(self, vip_headers):
        # Precondition: upload one first
        payload = self._make_jpeg()
        requests.post(
            f"{BASE_URL}/api/profile/avatar/upload",
            headers=vip_headers,
            files={"file": ("TEST_avatar.jpg", payload, "image/jpeg")},
            timeout=30,
        )
        # DELETE
        d = requests.delete(f"{BASE_URL}/api/profile/avatar", headers=vip_headers, timeout=15)
        assert d.status_code == 200, f"avatar DELETE failed: {d.status_code} {d.text[:200]}"

        # /api/profile/me → avatar_url should now be None
        me = requests.get(f"{BASE_URL}/api/profile/me", headers=vip_headers, timeout=15)
        assert me.status_code == 200
        assert me.json().get("avatar_url") in (None, ""), (
            f"After DELETE, avatar_url should be null, got: {me.json().get('avatar_url')}"
        )


# ---------------------- Regression suite ----------------------
class TestRegression:
    def test_landing_page_loads(self):
        r = requests.get(f"{BASE_URL}/", timeout=15)
        assert r.status_code == 200
        # SPA — the shell HTML has the title tag pre-rendered.
        assert "ScoutMePlay" in r.text or "Elite" in r.text or "scoutmeplay" in r.text.lower(), (
            f"Landing page missing brand marker; first 500 chars: {r.text[:500]}"
        )

    def test_admin_login_and_scouts(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/scouts", headers=admin_headers, timeout=15)
        assert r.status_code == 200, f"admin/scouts failed: {r.status_code} {r.text[:200]}"
        # Response shape may be list or dict — just assert 200 with JSON
        j = r.json()
        assert isinstance(j, (list, dict))

    def test_faq_returns_8_items(self):
        r = requests.get(f"{BASE_URL}/api/faq", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # Accept either list-of-items or {"items": [...]}
        items = data if isinstance(data, list) else data.get("items", data.get("faqs", []))
        assert len(items) >= 8, f"Expected 8+ FAQ items, got {len(items)}"
