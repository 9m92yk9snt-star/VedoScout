"""
Iteration 30 — URL-fetch Veo pre-check tests.

Verifies that POST /api/me/url-fetch:
1) Returns 400 with the friendly Veo message for Veo CLIP URLs
   (https://app.veo.co/clubs/<club>/clips/<uuid>/)
2) Returns 400 with the same friendly message for Veo MATCH URLs
   (https://app.veo.co/matches/<slug>/)
3) Still succeeds (200 + token + preview_url) for a legitimate direct MP4
   (regression: confirms the pre-check did not break the rest of the pipeline)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback from frontend env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass

assert BASE_URL, "REACT_APP_BACKEND_URL not configured"

TEST_EMAIL = "testfree-mar@elitescout.com"
TEST_PASSWORD = "Free@2026!"

# Direct MP4 — small public sample for regression test
DIRECT_MP4_URL = "https://www.w3schools.com/html/mov_bbb.mp4"

VEO_CLIP_URL = "https://app.veo.co/clubs/broendby-if-pige-talent/clips/8af91277-9b23-46e6-9296-7f2c10690851/"
VEO_MATCH_URL = "https://app.veo.co/matches/20260606-match-pigetalent-u14-25-26-bsf-vf29a140/"


@pytest.fixture(scope="module")
def auth_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


def _assert_veo_friendly(resp):
    assert resp.status_code == 400, f"expected 400, got {resp.status_code}: {resp.text}"
    body = resp.json()
    detail = body.get("detail", "")
    assert isinstance(detail, str) and detail, f"missing detail string: {body}"
    # Must start with 'Veo links' (the friendly Veo message)
    assert detail.startswith("Veo links"), f"detail does not start with 'Veo links': {detail!r}"
    # Must reference the manual workflow — either 'Upload File' or 'download the clip' (case-insensitive)
    low = detail.lower()
    assert ("upload file" in low) or ("download" in low), (
        f"detail missing actionable hint: {detail!r}"
    )
    # Must NOT expose raw yt-dlp message
    assert "unsupported url" not in low, f"raw yt-dlp message leaked: {detail!r}"
    assert "file not found on disk" not in low, f"raw stack leaked: {detail!r}"


def test_veo_clip_url_returns_friendly_400(auth_headers):
    """Veo /clubs/<club>/clips/<uuid>/ URL must be rejected with a friendly message."""
    r = requests.post(
        f"{BASE_URL}/api/me/url-fetch",
        json={"url": VEO_CLIP_URL},
        headers=auth_headers,
        timeout=30,
    )
    _assert_veo_friendly(r)


def test_veo_match_url_returns_friendly_400(auth_headers):
    """Veo /matches/<slug>/ URL must ALSO be rejected with the same friendly message,
    and must NOT hang for 2 minutes attempting a 4GB download."""
    import time
    t0 = time.time()
    r = requests.post(
        f"{BASE_URL}/api/me/url-fetch",
        json={"url": VEO_MATCH_URL},
        headers=auth_headers,
        timeout=30,
    )
    elapsed = time.time() - t0
    # Pre-check must be near-instant (<5s); definitely not 2-minute timeout
    assert elapsed < 10, f"Veo match URL took too long ({elapsed:.1f}s) — pre-check not firing"
    _assert_veo_friendly(r)


def test_direct_mp4_still_works(auth_headers):
    """Regression: a legitimate direct MP4 URL must still succeed (200 + token)."""
    r = requests.post(
        f"{BASE_URL}/api/me/url-fetch",
        json={"url": DIRECT_MP4_URL},
        headers=auth_headers,
        timeout=120,
    )
    # Accept 200 (success). If the upstream host blocks (e.g. w3schools intermittently)
    # we record but don't pass — assert and let pytest report.
    assert r.status_code == 200, f"direct MP4 fetch failed: {r.status_code} {r.text[:400]}"
    data = r.json()
    assert "token" in data, f"missing token: {data}"
    assert "preview_url" in data, f"missing preview_url: {data}"
    assert isinstance(data.get("size_mb"), (int, float)), f"missing size_mb: {data}"
    assert data["size_mb"] > 0, f"size_mb is zero: {data}"
