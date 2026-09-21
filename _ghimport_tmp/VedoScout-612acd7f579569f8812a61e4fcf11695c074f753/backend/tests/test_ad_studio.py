"""Ad Studio backend tests — iteration 92."""
import os
import time
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PW = "Admin@2026!Elite"
CAMPAIGN_ID = "23bd028c89"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json()["access_token"]
    return tok


@pytest.fixture(scope="module")
def h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ── Products endpoint ───────────────────────────────────────────────
def test_products_returns_10(h):
    r = requests.get(f"{BASE}/api/admin/ad-studio/products", headers=h, timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) == 10
    keys = {p["key"] for p in data}
    expected = {"instant_analysis", "scout_review", "player_library", "exposure", "trials",
                "benchmarks", "development", "single_report", "premium", "vip"}
    assert keys == expected
    for p in data:
        assert p["label"] and p["facts"]


def test_products_unauthenticated_rejected():
    r = requests.get(f"{BASE}/api/admin/ad-studio/products", timeout=15)
    assert r.status_code in (401, 403)


def test_products_non_admin_rejected():
    # signup temp user
    email = f"TEST_adstudio_{int(time.time())}@example.com"
    r = requests.post(f"{BASE}/api/auth/signup",
                      json={"email": email, "password": "TestPass123!", "full_name": "AdStudio Tester"},
                      timeout=30)
    if r.status_code != 200:
        pytest.skip(f"signup failed: {r.status_code}")
    tok = r.json()["access_token"]
    r2 = requests.get(f"{BASE}/api/admin/ad-studio/products",
                      headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    assert r2.status_code in (401, 403)


# ── Campaigns list & fetch ──────────────────────────────────────────
def test_campaigns_list_no_concepts_no_id(h):
    r = requests.get(f"{BASE}/api/admin/ad-studio/campaigns", headers=h, timeout=30)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    row = next((x for x in items if x.get("id") == CAMPAIGN_ID), None)
    assert row, f"campaign {CAMPAIGN_ID} not in list"
    assert "concepts" not in row
    assert "_id" not in row


def test_campaign_detail_full(h):
    r = requests.get(f"{BASE}/api/admin/ad-studio/campaigns/{CAMPAIGN_ID}", headers=h, timeout=30)
    assert r.status_code == 200
    doc = r.json()
    assert "_id" not in doc
    assert doc["id"] == CAMPAIGN_ID
    concepts = doc.get("concepts") or []
    assert len(concepts) == 4
    angles = {c["angle"] for c in concepts}
    assert angles == {"emotional", "direct_response", "problem_solution", "product_value"}
    for c in concepts:
        assert c["id"] and c["hook"] and c["sub"] and c["cta"]
        assert c["images"]["portrait"] and c["images"]["square"]
        assert c["images"]["portrait"].startswith("/api/uploads/ads/")
        assert c["qc"] and isinstance(c["qc"].get("checks"), list)
        assert len(c["qc"]["checks"]) == 7
        keys = {ch["key"] for ch in c["qc"]["checks"]}
        assert keys == {"generic_image", "too_much_text", "weak_cta", "repeated_wording",
                        "looks_ai", "claim_accurate", "mobile_readable"}


def test_campaign_images_reachable(h):
    r = requests.get(f"{BASE}/api/admin/ad-studio/campaigns/{CAMPAIGN_ID}", headers=h, timeout=30)
    c0 = r.json()["concepts"][0]
    for shape in ("portrait", "square"):
        url = f"{BASE}{c0['images'][shape]}"
        img = requests.get(url, timeout=30)
        assert img.status_code == 200, f"{url} returned {img.status_code}"
        assert img.headers.get("content-type", "").startswith("image/")
        assert len(img.content) > 5000


# ── Edit ────────────────────────────────────────────────────────────
def test_edit_hook_and_restore(h):
    r = requests.get(f"{BASE}/api/admin/ad-studio/campaigns/{CAMPAIGN_ID}", headers=h, timeout=30)
    c0 = r.json()["concepts"][0]
    cid = c0["id"]
    original_hook = c0["hook"]
    original_edited = list(c0.get("edited") or [])

    # edit
    r2 = requests.put(f"{BASE}/api/admin/ad-studio/campaigns/{CAMPAIGN_ID}/concepts/{cid}",
                      headers=h, json={"hook": "Test hook edited"}, timeout=30)
    assert r2.status_code == 200
    updated = r2.json()
    assert updated["hook"] == "Test hook edited"
    assert "hook" in updated["edited"]

    # verify persistence
    r3 = requests.get(f"{BASE}/api/admin/ad-studio/campaigns/{CAMPAIGN_ID}", headers=h, timeout=30)
    got = next(c for c in r3.json()["concepts"] if c["id"] == cid)
    assert got["hook"] == "Test hook edited"

    # restore
    r4 = requests.put(f"{BASE}/api/admin/ad-studio/campaigns/{CAMPAIGN_ID}/concepts/{cid}",
                      headers=h, json={"hook": original_hook}, timeout=30)
    assert r4.status_code == 200
    assert r4.json()["hook"] == original_hook
    # 'edited' still contains 'hook' by design (once flagged, stays)
    _ = original_edited


# ── Select toggle ───────────────────────────────────────────────────
def test_select_toggle(h):
    r = requests.get(f"{BASE}/api/admin/ad-studio/campaigns/{CAMPAIGN_ID}", headers=h, timeout=30)
    c0 = r.json()["concepts"][0]
    cid = c0["id"]
    initial = bool(c0.get("selected"))

    r1 = requests.post(f"{BASE}/api/admin/ad-studio/campaigns/{CAMPAIGN_ID}/concepts/{cid}/select",
                       headers=h, timeout=30)
    assert r1.status_code == 200
    assert r1.json()["selected"] == (not initial)

    r2 = requests.post(f"{BASE}/api/admin/ad-studio/campaigns/{CAMPAIGN_ID}/concepts/{cid}/select",
                       headers=h, timeout=30)
    assert r2.status_code == 200
    assert r2.json()["selected"] == initial


# ── QC re-run (LLM call) ────────────────────────────────────────────
def test_qc_rerun(h):
    r = requests.get(f"{BASE}/api/admin/ad-studio/campaigns/{CAMPAIGN_ID}", headers=h, timeout=30)
    c0 = r.json()["concepts"][0]
    cid = c0["id"]
    old_ts = (c0.get("qc") or {}).get("checked_at")
    r2 = requests.post(f"{BASE}/api/admin/ad-studio/campaigns/{CAMPAIGN_ID}/concepts/{cid}/qc",
                       headers=h, timeout=180)
    assert r2.status_code == 200
    got = r2.json()
    assert got["qc"]["checked_at"] and got["qc"]["checked_at"] != old_ts
    assert len(got["qc"]["checks"]) == 7


# ── Regen CTA (LLM call) ────────────────────────────────────────────
def test_regen_cta(h):
    r = requests.get(f"{BASE}/api/admin/ad-studio/campaigns/{CAMPAIGN_ID}", headers=h, timeout=30)
    c0 = r.json()["concepts"][0]
    cid = c0["id"]
    old_cta = c0["cta"]
    r2 = requests.post(f"{BASE}/api/admin/ad-studio/campaigns/{CAMPAIGN_ID}/concepts/{cid}/regen",
                       headers=h, json={"element": "cta"}, timeout=240)
    assert r2.status_code == 200
    got = r2.json()
    assert got["cta"] and got["cta"] != old_cta
    assert got["qc"] and got["qc"].get("checked_at")


def test_regen_invalid_element(h):
    r = requests.get(f"{BASE}/api/admin/ad-studio/campaigns/{CAMPAIGN_ID}", headers=h, timeout=30)
    cid = r.json()["concepts"][0]["id"]
    r2 = requests.post(f"{BASE}/api/admin/ad-studio/campaigns/{CAMPAIGN_ID}/concepts/{cid}/regen",
                       headers=h, json={"element": "bogus"}, timeout=30)
    assert r2.status_code == 400


def test_generate_unknown_product(h):
    r = requests.post(f"{BASE}/api/admin/ad-studio/generate", headers=h,
                      json={"product": "not_a_product", "language": "en"}, timeout=30)
    assert r.status_code == 400
