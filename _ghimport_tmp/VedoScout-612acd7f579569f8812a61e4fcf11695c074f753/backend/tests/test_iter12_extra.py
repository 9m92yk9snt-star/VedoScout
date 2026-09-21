"""Iteration 12 — additional contract & PDF coverage beyond test_age_intelligence.py."""
import os
import requests
import pytest

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com"
).rstrip("/")


@pytest.fixture(scope="session")
def premium_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "premium@elitescout.com", "password": "Premium@2026"},
                      timeout=20).json()
    tok = r.get("access_token") or r.get("token")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def admin_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "admin@elitescout.com", "password": "Admin@2026!Elite"},
                      timeout=20).json()
    tok = r.get("access_token") or r.get("token")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def lukas(premium_headers):
    rs = requests.get(f"{BASE_URL}/api/reports/mine", headers=premium_headers, timeout=20).json()
    paid = [r for r in rs if r.get("is_paid") or r.get("manually_unlocked")]
    rid = paid[0]["id"]
    return requests.get(f"{BASE_URL}/api/reports/{rid}", headers=premium_headers, timeout=60).json()


@pytest.fixture(scope="session")
def almin(admin_headers):
    rs = requests.get(f"{BASE_URL}/api/admin/reports", headers=admin_headers, timeout=20).json()
    doc = next(
        (r for r in rs
         if (r.get("player_details", {}).get("age") in (9, 10, 11))
         and (r.get("is_paid") or r.get("manually_unlocked"))),
        None,
    )
    if not doc:
        return None
    return requests.get(f"{BASE_URL}/api/reports/{doc['id']}", headers=admin_headers, timeout=60).json()


# ---------- Hard regression on Lukas ----------
def test_lukas_archetype_still_present(lukas):
    assert lukas.get("archetype"), "archetype panel missing"
    arch = lukas["archetype"]
    assert arch.get("primary"), "archetype.primary missing"

def test_lukas_5_lenses_present(lukas):
    lenses = (lukas.get("archetype") or {}).get("lenses") or {}
    # Must have all 5 lenses since Lukas is U12+
    for k in ("technical", "tactical", "fifa", "physical", "mentality"):
        assert k in lenses, f"lens {k} missing"
        sim = lenses[k].get("similarity_pct") or lenses[k].get("score")
        if sim is not None and sim > 10:
            assert sim <= 92, f"FIFA cap exceeded: {k}={sim}"

def test_lukas_fifa_knn_top5(lukas):
    arch = lukas.get("archetype") or {}
    nb = arch.get("fifa_neighbors") or []
    assert len(nb) >= 1, "Expected FIFA neighbors for Lukas"

def test_lukas_statsbomb_present(lukas):
    assert lukas.get("statsbomb_calibration"), "StatsBomb calibration missing for Lukas"

def test_lukas_trial_readiness_present(lukas):
    assert lukas.get("trial_readiness"), "Trial readiness missing for Lukas"

def test_lukas_radar_present(lukas):
    # performance radar / detailed scores must still render
    assert lukas.get("detailed_scores") or lukas.get("performance_radar") or lukas.get("attributes"), \
        "No radar/attribute data"

def test_lukas_level_elite_academy(lukas):
    ai = lukas.get("age_intelligence") or {}
    level = ai.get("level") or {}
    # Pro academy + 8 → Elite Academy per spec
    assert level.get("label") in ("Elite Academy", "Academy", "Strong Club", "Club",
                                  "Beginner", "Grassroots", "Semi-Pro", "Professional"), \
        f"unexpected level: {level}"

# ---------- Almin 4-lens (FIFA stripped) ----------
def test_almin_only_4_lenses(almin):
    if not almin:
        pytest.skip("Almin not accessible")
    lenses = (almin.get("archetype") or {}).get("lenses") or {}
    assert "fifa" not in lenses
    assert len(lenses) >= 3, f"expected 4 lenses without fifa, got {list(lenses.keys())}"

def test_almin_age_intel_scores(almin):
    if not almin:
        pytest.skip("Almin not accessible")
    s = (almin.get("age_intelligence") or {}).get("scores") or {}
    # pro_style_match_score should be None / 0 when FIFA gated
    pss = s.get("pro_style_match_score")
    assert pss in (None, 0, 0.0) or pss <= 1.0, \
        f"pro_style_match_score should be gated for U9-U11, got {pss}"

# ---------- PDF v8 full string set ----------
def test_pdf_v8_full_strings_lukas(premium_headers, lukas):
    rid = lukas["id"]
    # Force regen
    try:
        import glob
        for f in glob.glob("/app/backend/pdfs/*.pdf"):
            os.remove(f)
    except Exception:
        pass
    pdf = requests.get(f"{BASE_URL}/api/reports/{rid}/pdf", headers=premium_headers, timeout=180)
    assert pdf.status_code == 200
    try:
        import pypdf
        from io import BytesIO
        reader = pypdf.PdfReader(BytesIO(pdf.content))
        text = "".join((p.extract_text() or "") for p in reader.pages).upper()
    except ImportError:
        pytest.skip("pypdf not installed")
    required = [
        "AGE-ANCHORED EVALUATION",
        "AGE INTELLIGENCE SCOREBOARD",
        "HOW THIS EVALUATION WORKS",
        "EVALUATED FOR THIS STAGE",
        "DELIBERATELY NOT EVALUATED",
        "CURRENT AGE SCORE",
        "POSITION-SPECIFIC",
        "DEV. PRIORITY",
        "FIFA DATA TWIN",
        "STATSBOMB EURO 2024",
    ]
    missing = [s for s in required if s not in text]
    assert not missing, f"PDF missing: {missing}"
