"""
Iteration 95 — CV shadow / identity-safety architecture verification.
Read-only checks against existing seeded premium reports.
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"
REPORT_ID = "d8c04d5d-6618-4db2-a128-865447478ef6"
OTHER_REPORTS = ["fe7bc3e5-8181-465f-a41a-99c54d691710", "3467a622-c287-4b81-add4-f5411b3fef4b"]


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:400]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- Admin login ----------
def test_admin_login_ok(admin_token):
    assert isinstance(admin_token, str) and len(admin_token) > 10


# ---------- Buyer report leak check ----------
def test_report_no_cv_shadow_leak(admin_headers):
    r = requests.get(f"{BASE_URL}/api/reports/{REPORT_ID}", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text[:400]
    body_text = r.text
    # deep leak check
    assert "cv_shadow" not in body_text, "cv_shadow key leaked in buyer-facing report"
    data = r.json()
    assert "full_report" in data and data["full_report"], "full_report missing"
    # video_comments and frame_url
    vc = data.get("video_comments") or data.get("full_report", {}).get("video_comments") or []
    assert isinstance(vc, list) and len(vc) > 0, "no video_comments"
    frame_urls = [c.get("frame_url") for c in vc if c.get("frame_url")]
    assert len(frame_urls) > 0, "no frame_url in video_comments"
    # tele_clip_url >=2
    tele_clips = [c.get("tele_clip_url") for c in vc if c.get("tele_clip_url")]
    assert len(tele_clips) >= 2, f"expected >=2 tele_clip_url entries, got {len(tele_clips)}"
    # stash on module for reuse
    pytest.frame_url = frame_urls[0]
    pytest.tele_clip_url = tele_clips[0]


def test_frame_image_loads(admin_headers):
    url = getattr(pytest, "frame_url", None)
    assert url, "prereq failed"
    full = url if url.startswith("http") else f"{BASE_URL}{url}"
    r = requests.get(full, headers=admin_headers, timeout=30)
    assert r.status_code == 200, f"frame fetch failed: {r.status_code}"
    ct = r.headers.get("content-type", "")
    assert "image" in ct, f"unexpected content-type: {ct}"


def test_tele_clip_loads(admin_headers):
    url = getattr(pytest, "tele_clip_url", None)
    assert url, "prereq failed"
    full = url if url.startswith("http") else f"{BASE_URL}{url}"
    # signed url - do not send auth header (already signed) but try with header first
    r = requests.get(full, timeout=60, stream=True, allow_redirects=True)
    if r.status_code in (401, 403):
        r = requests.get(full, headers=admin_headers, timeout=60, stream=True, allow_redirects=True)
    assert r.status_code == 200, f"tele clip fetch failed: {r.status_code}"
    ct = r.headers.get("content-type", "")
    assert "video" in ct or "mp4" in ct, f"unexpected content-type: {ct}"


# ---------- Admin cv-shadow endpoints ----------
def test_cv_shadow_summary_requires_auth():
    r = requests.get(f"{BASE_URL}/api/admin/cv-shadow/summary", timeout=30)
    assert r.status_code in (401, 403), f"unauth got {r.status_code}"


def test_cv_shadow_summary(admin_headers):
    r = requests.get(f"{BASE_URL}/api/admin/cv-shadow/summary", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text[:400]
    data = r.json()
    agg = data.get("aggregate") or data
    assert agg.get("reports") == 3, f"expected 3 reports, got {agg.get('reports')}"
    assert (agg.get("checked") or 0) > 0, f"checked should be >0, got {agg.get('checked')}"
    sr = agg.get("suspect_rate")
    assert sr is not None and sr <= 0.05, f"suspect_rate {sr} > 0.05"
    # engine v6: switch-risk must stay within the documented safe threshold
    # (same 2% rule that gates gap-bridge activation), not necessarily zero
    switch_rate = (agg.get("switch_risk_frames") or 0) / max(1, agg.get("checked") or 1)
    assert switch_rate <= 0.02, f"switch rate {switch_rate} > 0.02"
    assert agg.get("gap_bridge_active") is True, f"gap_bridge_active={agg.get('gap_bridge_active')}"


def test_cv_shadow_per_report_requires_auth():
    r = requests.get(f"{BASE_URL}/api/admin/reports/{REPORT_ID}/cv-shadow", timeout=30)
    assert r.status_code in (401, 403)


def test_cv_shadow_per_report(admin_headers):
    r = requests.get(f"{BASE_URL}/api/admin/reports/{REPORT_ID}/cv-shadow",
                     headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text[:400]
    data = r.json()
    ev = (data.get("cv_shadow") or {}).get("engine_version") or data.get("engine_version")
    assert ev is not None and int(ev) >= 5, f"engine_version={ev}"


# ---------- Regression ----------
def test_homepage_loads():
    r = requests.get(f"{BASE_URL}/", timeout=30)
    assert r.status_code == 200


def test_all_three_reports_no_leak(admin_headers):
    for rid in [REPORT_ID] + OTHER_REPORTS:
        r = requests.get(f"{BASE_URL}/api/reports/{rid}", headers=admin_headers, timeout=30)
        assert r.status_code == 200, f"{rid}: {r.status_code}"
        assert "cv_shadow" not in r.text, f"{rid} leaked cv_shadow"
