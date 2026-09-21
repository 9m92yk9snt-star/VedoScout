"""Session 3 testing — DNA fingerprint, frame thumbnails, share card."""
import os
import io
import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")
PREMIUM_EMAIL = "premium@elitescout.com"
PREMIUM_PASSWORD = "Premium@2026"


@pytest.fixture(scope="module")
def auth_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": PREMIUM_EMAIL, "password": PREMIUM_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="module")
def lukas_report(headers):
    r = requests.get(f"{BASE_URL}/api/reports/mine", headers=headers, timeout=30)
    assert r.status_code == 200, f"reports list failed: {r.text}"
    data = r.json()
    reports = data if isinstance(data, list) else data.get("reports", [])
    lukas = next((rep for rep in reports if "lukas" in (rep.get("player_name", "") + rep.get("title", "") + (rep.get("player_details") or {}).get("player_name", "")).lower()), None)
    assert lukas, f"No Lukas report found in {len(reports)} reports"
    rid = lukas.get("id") or lukas.get("_id") or lukas.get("report_id")
    r2 = requests.get(f"{BASE_URL}/api/reports/{rid}", headers=headers, timeout=60)
    assert r2.status_code == 200, f"report fetch failed: {r2.text}"
    return r2.json(), rid


# ---------- Session 3 ----------

class TestShareCard:
    def test_share_card_url_in_response(self, lukas_report):
        rep, _ = lukas_report
        share_url = rep.get("share_card_url")
        assert share_url, f"share_card_url missing in response. Keys: {list(rep.keys())}"
        assert isinstance(share_url, str)
        assert share_url.startswith("/api/uploads/cards/"), f"Unexpected share_card_url: {share_url}"
        print(f"share_card_url = {share_url}")

    def test_share_card_downloadable(self, lukas_report, headers):
        rep, _ = lukas_report
        share_url = rep["share_card_url"]
        full = f"{BASE_URL}{share_url}"
        r = requests.get(full, headers=headers, timeout=60)
        assert r.status_code == 200, f"share card GET failed: {r.status_code}"
        assert "image/png" in r.headers.get("content-type", ""), f"ct={r.headers.get('content-type')}"
        assert len(r.content) > 5000, f"size={len(r.content)}"
        with open("/tmp/api_share_card.png", "wb") as f:
            f.write(r.content)
        img = Image.open(io.BytesIO(r.content))
        img.verify()
        img2 = Image.open(io.BytesIO(r.content))
        print(f"share card png size={img2.size}, bytes={len(r.content)}")
        assert img2.size[0] == 1080 and img2.size[1] == 1350, f"got {img2.size}"


class TestFrameThumbnails:
    def test_video_comments_have_frame_url(self, lukas_report):
        rep, rid = lukas_report
        full = rep.get("full_report") or rep
        vc = full.get("video_comments") or rep.get("video_comments")
        assert isinstance(vc, list) and len(vc) == 6, f"expected 6 comments, got {len(vc) if vc else 'None'}"
        for i, c in enumerate(vc):
            assert "frame_url" in c, f"comment {i} missing frame_url. keys={list(c.keys())}"
            assert c["frame_url"].startswith(f"/api/uploads/frames/{rid}/"), f"bad url {c['frame_url']}"
        print(f"One frame_url: {vc[0]['frame_url']}")

    def test_frame_image_downloadable(self, lukas_report, headers):
        rep, _ = lukas_report
        full = rep.get("full_report") or rep
        vc = full.get("video_comments") or rep.get("video_comments")
        url = vc[0]["frame_url"]
        r = requests.get(f"{BASE_URL}{url}", headers=headers, timeout=30)
        assert r.status_code == 200, f"frame GET {r.status_code}"
        assert "image/jpeg" in r.headers.get("content-type", ""), f"ct={r.headers.get('content-type')}"
        assert len(r.content) > 2000, f"size={len(r.content)}"
        img = Image.open(io.BytesIO(r.content))
        img.verify()


class TestPremiumPDF:
    def test_pdf_pages_and_embedded_images(self, lukas_report, headers):
        rep, rid = lukas_report
        r = requests.get(f"{BASE_URL}/api/reports/{rid}/pdf", headers=headers, timeout=180)
        assert r.status_code == 200, f"pdf {r.status_code}: {r.text[:200]}"
        assert "pdf" in r.headers.get("content-type", "").lower()
        with open("/tmp/lukas_premium.pdf", "wb") as f:
            f.write(r.content)
        import fitz
        doc = fitz.open("/tmp/lukas_premium.pdf")
        n_pages = doc.page_count
        print(f"PDF pages = {n_pages}")
        assert n_pages >= 22, f"only {n_pages} pages"
        all_text = ""
        n_images = 0
        for p in doc:
            all_text += p.get_text()
            n_images += len(p.get_images(full=True))
        print(f"embedded images across pdf = {n_images}")
        assert n_images >= 5, f"only {n_images} embedded images"
        # regression text
        for kw in ("METHODOLOGY", "UEFA", "STYLISTIC ARCHETYPE", "EUROPEAN ACADEMY REFERENCE PROFILE", "TRIAL READINESS"):
            assert kw in all_text.upper(), f"PDF missing '{kw}'"
        doc.close()


class TestRegression:
    def test_archetype_age_trial(self, lukas_report):
        rep, _ = lukas_report
        full = rep.get("full_report") or rep
        tr = full.get("trial_readiness") or rep.get("trial_readiness")
        assert tr, "trial_readiness missing"
        assert tr.get("position_key") == "attacking midfielder", f"position_key={tr.get('position_key')}"
        arch = full.get("archetype") or rep.get("archetype")
        assert arch and arch.get("id") == "modric_type", f"archetype.id={arch.get('id') if arch else None}"
        agep = full.get("age_profile_reference") or rep.get("age_profile_reference")
        assert agep and agep.get("above_count") == 7, f"above_count={agep.get('above_count') if agep else None}"


class TestFfmpeg:
    def test_ffmpeg_installed(self):
        import shutil
        assert shutil.which("ffmpeg") == "/usr/bin/ffmpeg"
