import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")
REPORT_ID = "f5748eb6-14cd-4ffc-bf20-afb88ef1c65a"
ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASS = "Admin@2026!Elite"


def _login():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in login resp: {r.json()}"
    return tok


def test_login():
    tok = _login()
    assert isinstance(tok, str) and len(tok) > 10


def test_report_tele_clip_urls():
    tok = _login()
    r = requests.get(f"{BASE_URL}/api/reports/{REPORT_ID}", headers={"Authorization": f"Bearer {tok}"}, timeout=60)
    assert r.status_code == 200, f"report fetch failed {r.status_code} {r.text[:300]}"
    data = r.json()
    fr = data.get("full_report") or {}
    comments = fr.get("video_comments") or []
    by_ts = {c.get("timestamp"): c for c in comments}
    assert "00:19" in by_ts, f"timestamps found: {list(by_ts.keys())}"

    c19 = by_ts["00:19"]
    url19 = c19.get("tele_clip_url")
    assert url19, f"00:19 missing tele_clip_url: {c19}"
    assert url19.startswith(f"/api/media/reports/{REPORT_ID}/frames/proofclip_1.mp4?tk="), f"bad url19: {url19}"
    assert "&exp=" in url19
    assert c19.get("tele_clip_coverage") == 1.0, f"coverage got {c19.get('tele_clip_coverage')}"

    c54 = by_ts.get("00:54")
    assert c54, "00:54 comment missing"
    url54 = c54.get("tele_clip_url")
    assert url54 and "proofclip_4.mp4?tk=" in url54, f"bad url54: {url54}"

    for ts in ("00:03", "00:33", "00:48"):
        c = by_ts.get(ts)
        assert c, f"missing {ts}"
        assert not c.get("tele_clip_url"), f"{ts} unexpectedly has clip: {c.get('tele_clip_url')}"

    # store for next tests via env-file (before regression asserts so it's always written)
    with open("/tmp/_iter94_url19.txt", "w") as f:
        f.write(url19)

    # regression: video_url (top-level) signed, frame_url on comments
    assert data.get("video_url"), "top-level video_url missing"
    assert any(cm.get("frame_url") for cm in comments), "no frame_url found on any comment"


def test_signed_media_range_and_403():
    with open("/tmp/_iter94_url19.txt") as f:
        url = f.read().strip()
    full = f"{BASE_URL}{url}"
    r = requests.get(full, headers={"Range": "bytes=0-1000"}, timeout=60)
    assert r.status_code == 206, f"expected 206 got {r.status_code} body={r.text[:200]}"
    assert "video/mp4" in r.headers.get("content-type", ""), f"ct={r.headers.get('content-type')}"

    # strip query
    stripped = full.split("?")[0]
    r2 = requests.get(stripped, timeout=30, allow_redirects=False)
    assert r2.status_code == 403, f"expected 403 without signed params got {r2.status_code}"


def test_demo_report():
    r = requests.get(f"{BASE_URL}/api/demo-report", timeout=60)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    assert (r.json().get("full_report") is not None), "no full_report in demo"
