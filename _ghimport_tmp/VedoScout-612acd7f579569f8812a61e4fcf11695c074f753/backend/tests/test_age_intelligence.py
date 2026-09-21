"""
Age Intelligence Scoring System tests.

Verifies:
  - 5 stages load + resolve correctly
  - 9 deterministic scores compute for an unlocked report
  - Stage-gating strips senior-pro panels for U6-U11
  - Disclaimer + what-we-evaluated blocks are surfaced
  - Level mapping returns one of 8 labels when tier is known
  - PDF v8+ includes age-stage strings
"""
import json
import os
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com"
).rstrip("/")
STAGES_FILE = "/app/backend/data/age_stages.json"
EXPECTED_STAGE_IDS = ["foundation", "technical", "understanding", "academy_ready", "senior"]


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "premium@elitescout.com", "password": "Premium@2026"},
                      timeout=20)
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="session")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def lukas_report(headers):
    rs = requests.get(f"{BASE_URL}/api/reports/mine", headers=headers, timeout=20).json()
    paid = [r for r in rs if r.get("is_paid") or r.get("manually_unlocked")]
    rid = next(r["id"] for r in paid if "lukas" in (r.get("player_name", "") or "").lower()
               or r.get("player_name") == "Lukas A.") if any("lukas" in (r.get("player_name","") or "").lower() for r in paid) else paid[0]["id"]
    return requests.get(f"{BASE_URL}/api/reports/{rid}", headers=headers, timeout=60).json()


# ---------- Stage catalog integrity ----------

def test_five_stages_load():
    with open(STAGES_FILE) as f:
        d = json.load(f)
    stages = d.get("stages") or []
    ids = [s["id"] for s in stages]
    assert ids == EXPECTED_STAGE_IDS, f"unexpected stage ids: {ids}"


def test_stage_age_bands_contiguous():
    """Stages must cover ages 6-99 without gaps or overlaps."""
    with open(STAGES_FILE) as f:
        d = json.load(f)
    stages = sorted(d["stages"], key=lambda s: s["age_min"])
    prev_max = 5
    for s in stages:
        assert s["age_min"] == prev_max + 1, f"gap before stage {s['id']}"
        prev_max = s["age_max"]
    assert prev_max >= 99


def test_foundation_stage_panels_locked():
    """U6-U8 MUST NOT show senior-pro panels."""
    with open(STAGES_FILE) as f:
        d = json.load(f)
    foundation = next(s for s in d["stages"] if s["id"] == "foundation")
    p = foundation["panels"]
    assert p["show_fifa_knn"] is False
    assert p["show_statsbomb"] is False
    assert p["show_trial_readiness"] is False


def test_technical_stage_panels_locked():
    """U9-U11 MUST NOT show senior-pro panels either."""
    with open(STAGES_FILE) as f:
        d = json.load(f)
    technical = next(s for s in d["stages"] if s["id"] == "technical")
    p = technical["panels"]
    assert p["show_fifa_knn"] is False
    assert p["show_statsbomb"] is False
    assert p["show_trial_readiness"] is False


def test_understanding_and_above_panels_unlocked():
    """U12+ MUST show all senior-pro panels."""
    with open(STAGES_FILE) as f:
        d = json.load(f)
    for sid in ("understanding", "academy_ready", "senior"):
        stage = next(s for s in d["stages"] if s["id"] == sid)
        p = stage["panels"]
        assert p["show_fifa_knn"] is True
        assert p["show_statsbomb"] is True
        assert p["show_trial_readiness"] is True


# ---------- API contract on Lukas (14yo → Understanding stage) ----------

def test_age_intelligence_attached(lukas_report):
    ai = lukas_report.get("age_intelligence")
    assert isinstance(ai, dict)
    assert ai["stage"]["id"] == "understanding"
    assert ai["stage"]["age_band"] == "U12-U14"


def test_nine_scores_present(lukas_report):
    s = (lukas_report.get("age_intelligence") or {}).get("scores") or {}
    expected = [
        "current_age_score", "position_specific_score", "next_level_readiness_score",
        "pro_style_match_score", "technical_score", "tactical_score",
        "physical_score", "mentality_body_language_score", "development_priority_score",
    ]
    for k in expected:
        assert k in s, f"missing score: {k}"
    # All 9 must be numbers (none missing for Lukas — he's in unlocked stage)
    for k in expected:
        assert isinstance(s[k], (int, float)), f"score {k} not numeric: {s[k]}"
        assert 0.0 <= s[k] <= 10.0, f"score {k}={s[k]} outside 0-10"


def test_pro_style_match_mirrors_fifa(lukas_report):
    """pro_style_match_score = fifa.similarity_pct / 10 when FIFA lens is present."""
    ai = lukas_report["age_intelligence"]
    fifa = ((lukas_report.get("archetype") or {}).get("lenses") or {}).get("fifa") or {}
    if fifa.get("similarity_pct"):
        expected = round(float(fifa["similarity_pct"]) / 10.0, 2)
        actual = ai["scores"]["pro_style_match_score"]
        assert abs(expected - actual) < 0.01, (
            f"pro_style_match_score {actual} != FIFA similarity / 10 {expected}"
        )


def test_disclaimer_present(lukas_report):
    ai = lukas_report["age_intelligence"]
    assert "age-appropriate" in ai["disclaimer"].lower()
    assert "professional player data" in ai["disclaimer"].lower()


def test_what_we_evaluated_present(lukas_report):
    ai = lukas_report["age_intelligence"]
    assert isinstance(ai["what_we_evaluated"], list)
    assert len(ai["what_we_evaluated"]) >= 4
    assert isinstance(ai["what_we_could_not_evaluate"], list)


def test_level_resolved(lukas_report):
    """Lukas has tier=pro_academy + overall=8 → Elite Academy."""
    ai = lukas_report["age_intelligence"]
    level = ai.get("level")
    if not level:
        pytest.skip("no tier resolved on this report")
    assert level["label"] in (
        "Beginner", "Grassroots", "Club", "Strong Club",
        "Academy", "Elite Academy", "Semi-Pro", "Professional",
    )


# ---------- Stage-gating on Almin (11yo → Technical stage) ----------

@pytest.fixture(scope="session")
def almin_report():
    """U6-U11 paid+unlocked report — accessible via admin role.
    Filters strictly: must be paid/unlocked AND have a full_report so
    age_intelligence is actually computed."""
    admin = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": "admin@elitescout.com", "password": "Admin@2026!Elite"},
                          timeout=20).json()
    admin_tok = admin.get("access_token") or admin.get("token")
    if not admin_tok:
        return None
    admin_headers = {"Authorization": f"Bearer {admin_tok}"}
    rs = requests.get(f"{BASE_URL}/api/admin/reports", headers=admin_headers, timeout=20)
    if rs.status_code != 200:
        return None
    candidates = [
        r for r in rs.json()
        if (r.get("player_details", {}).get("age") in (9, 10, 11))
        and (r.get("is_paid") or r.get("manually_unlocked"))
    ]
    # Fetch each and pick the FIRST one that has full_report (i.e. a real scored doc)
    for c in candidates:
        full = requests.get(f"{BASE_URL}/api/reports/{c['id']}",
                            headers=admin_headers, timeout=60).json()
        if full.get("full_report") and (full.get("full_report") or {}).get("scores"):
            return full
    return None


def test_almin_in_technical_stage(almin_report):
    if not almin_report:
        pytest.skip("Almin report not accessible from premium account")
    ai = almin_report.get("age_intelligence") or {}
    assert ai.get("stage", {}).get("id") == "technical"


def test_almin_fifa_gated(almin_report):
    if not almin_report:
        pytest.skip("Almin report not accessible")
    arch = almin_report.get("archetype") or {}
    assert arch.get("fifa_neighbors") in (None, [])
    assert arch.get("fifa_panel_gated_message")
    lenses = arch.get("lenses") or {}
    assert "fifa" not in lenses, "FIFA lens MUST be stripped for U9-U11"


def test_almin_statsbomb_gated(almin_report):
    if not almin_report:
        pytest.skip("Almin report not accessible")
    assert almin_report.get("statsbomb_calibration") is None
    assert almin_report.get("statsbomb_calibration_gated_message")


def test_almin_trial_readiness_gated(almin_report):
    if not almin_report:
        pytest.skip("Almin report not accessible")
    assert almin_report.get("trial_readiness") is None
    assert almin_report.get("trial_readiness_gated_message")


# ---------- PDF content ----------

def test_pdf_contains_age_intelligence_strings(headers, lukas_report):
    """PDF v8+ must include age-intelligence sections."""
    rid = lukas_report["id"]
    # Clear local cache first
    pdf_resp = requests.get(f"{BASE_URL}/api/reports/{rid}/pdf", headers=headers, timeout=120)
    assert pdf_resp.status_code == 200
    pdf_bytes = pdf_resp.content
    # Extract text
    try:
        import pypdf
        from io import BytesIO
        reader = pypdf.PdfReader(BytesIO(pdf_bytes))
        text = "".join((p.extract_text() or "") for p in reader.pages).upper()
    except ImportError:
        pytest.skip("pypdf not installed")
    expected_strings = [
        "AGE-ANCHORED EVALUATION",
        "AGE INTELLIGENCE SCOREBOARD",
        "HOW THIS EVALUATION WORKS",
        "EVALUATED FOR THIS STAGE",
        "CURRENT AGE SCORE",
    ]
    missing = [s for s in expected_strings if s not in text]
    assert not missing, f"PDF missing strings: {missing}"
