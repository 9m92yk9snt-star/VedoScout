"""
Iteration 7: Stylistic Archetype (C1) + European Academy Age Profile (C2)
Backend tests for ScoutMePlay credibility upgrade session 2.
"""
import os
import json
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")
PREMIUM_EMAIL = "premium@elitescout.com"
PREMIUM_PASSWORD = "Premium@2026"

ARCHETYPES_PATH = "/app/backend/data/archetypes.json"
AGE_PROFILES_PATH = "/app/backend/data/age_profiles.json"

EIGHT_POSITIONS = [
    "goalkeeper", "centre back", "full back", "defensive midfielder",
    "central midfielder", "attacking midfielder", "winger", "striker",
]


# -------- fixtures --------
@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": PREMIUM_EMAIL, "password": PREMIUM_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def lukas_report(headers):
    r = requests.get(f"{BASE_URL}/api/reports/mine", headers=headers, timeout=20)
    assert r.status_code == 200, r.text
    reports = r.json()
    assert isinstance(reports, list) and len(reports) > 0
    # find Lukas (attacking midfielder)
    target = None
    for rep in reports:
        nm = (rep.get("player_name") or rep.get("name") or "").lower()
        if "lukas" in nm:
            target = rep
            break
    if target is None:
        target = reports[0]
    rid = target.get("id") or target.get("_id")
    assert rid
    full = requests.get(f"{BASE_URL}/api/reports/{rid}", headers=headers, timeout=30)
    assert full.status_code == 200, full.text
    return full.json()


# -------- Catalog file integrity --------
class TestCatalogFiles:
    def test_archetypes_file_structure(self):
        with open(ARCHETYPES_PATH) as f:
            data = json.load(f)
        for pos in EIGHT_POSITIONS:
            assert pos in data, f"missing position '{pos}' in archetypes.json"
            arr = data[pos]
            assert isinstance(arr, list) and len(arr) >= 4, f"{pos} needs >=4 archetypes, got {len(arr)}"
            for a in arr:
                for k in ("id", "name", "anchor", "traits", "summary"):
                    assert k in a, f"{pos} archetype missing '{k}'"
                assert isinstance(a["anchor"], list) and len(a["anchor"]) >= 2
                assert isinstance(a["traits"], list) and len(a["traits"]) >= 1
                assert isinstance(a["summary"], str) and len(a["summary"]) > 0

    def test_age_profiles_file_structure(self):
        with open(AGE_PROFILES_PATH) as f:
            data = json.load(f)
        for pos in EIGHT_POSITIONS:
            assert pos in data, f"missing position '{pos}' in age_profiles.json"
            pa = data[pos].get("priority_attributes")
            assert isinstance(pa, list) and len(pa) >= 5, f"{pos} needs >=5 priority_attributes"
            for entry in pa:
                for k in ("key", "weight", "why_matters"):
                    assert k in entry, f"{pos} entry missing '{k}'"
                assert isinstance(entry["weight"], (int, float))


# -------- Report-level enrichment --------
class TestArchetypeBlock:
    def test_archetype_present_and_correct(self, lukas_report):
        a = lukas_report.get("archetype")
        assert a is not None, "archetype block missing from report"
        for k in ("id", "name", "traits", "summary", "match_strength", "developing"):
            assert k in a, f"archetype missing key '{k}'"
        assert a["id"] == "modric_type", f"expected modric_type, got {a['id']}"
        assert "Modric-type composer" in a["name"]
        assert isinstance(a["traits"], list) and len(a["traits"]) >= 1
        assert isinstance(a["match_strength"], (int, float))
        assert a["match_strength"] >= 8.0, f"match_strength {a['match_strength']} < 8.0"
        assert a["developing"] is False


class TestAgeProfileBlock:
    def test_age_profile_present_and_correct(self, lukas_report):
        ap = lukas_report.get("age_profile_reference")
        assert ap is not None, "age_profile_reference missing"
        for k in ("position_key", "age_bracket", "items", "summary",
                  "above_count", "below_count", "total_priority_attrs"):
            assert k in ap, f"age_profile missing '{k}'"
        assert ap["position_key"] == "attacking midfielder"
        assert ap["age_bracket"] == "U13-U14"
        assert isinstance(ap["items"], list)
        assert len(ap["items"]) == 7, f"expected 7 items, got {len(ap['items'])}"
        assert ap["above_count"] == 7
        assert ap["below_count"] == 0

    def test_age_profile_items_schema(self, lukas_report):
        items = lukas_report["age_profile_reference"]["items"]
        for it in items:
            for k in ("key", "label", "weight", "why_matters", "pro_academy_range",
                      "player_score", "player_tier", "delta"):
                assert k in it, f"item missing '{k}': {it}"
            assert isinstance(it["weight"], (int, float)) and 1 <= it["weight"] <= 5
            assert isinstance(it["why_matters"], str) and len(it["why_matters"]) > 0
            assert isinstance(it["pro_academy_range"], str) and len(it["pro_academy_range"]) > 0
            assert isinstance(it["player_score"], (int, float))
            assert isinstance(it["player_tier"], str)
            assert it["delta"] in ("at_or_above", "below", "no_data")


# -------- Trial readiness regression --------
class TestTrialReadinessRegression:
    def test_trial_readiness_still_present(self, lukas_report):
        tr = lukas_report.get("trial_readiness")
        assert tr is not None
        assert tr["position_key"] == "attacking midfielder"
        assert len(tr["items"]) == 8


# -------- PDF tests --------
class TestPremiumPDF:
    @pytest.fixture(scope="class")
    def pdf_bytes(self, headers, lukas_report):
        rid = lukas_report.get("id") or lukas_report.get("_id")
        r = requests.get(f"{BASE_URL}/api/reports/{rid}/pdf", headers=headers, timeout=120)
        assert r.status_code == 200, f"PDF download failed: {r.status_code}"
        return r.content

    def test_pdf_size(self, pdf_bytes):
        assert len(pdf_bytes) > 35 * 1024, f"PDF too small: {len(pdf_bytes)} bytes"

    def test_pdf_pages_and_text(self, pdf_bytes):
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        assert doc.page_count >= 22, f"pages={doc.page_count} < 22"
        full_text = ""
        for p in doc:
            full_text += p.get_text()
        # Normalize whitespace (PDF table headers can wrap mid-phrase, e.g. "PRO\nRANGE")
        import re as _re
        upper = _re.sub(r"\s+", " ", full_text.upper())

        # Session 2 — archetype + age profile
        required_session2 = [
            "STYLISTIC ARCHETYPE",
            "MODRIC-TYPE COMPOSER",
            "MATCH STRENGTH",
            "EUROPEAN ACADEMY REFERENCE PROFILE",
            "ATTACKING MIDFIELDER",
            "AT OR ABOVE",
            "PRO RANGE",
        ]
        missing = [s for s in required_session2 if s.upper() not in upper]
        assert not missing, f"PDF missing strings: {missing}"

        # at least one priority attribute label
        any_attr = any(label.upper() in upper for label in ["SCANNING", "PASSING", "DECISION MAKING"])
        assert any_attr, "PDF missing all of Scanning/Passing/Decision Making labels"

        # Regression: methodology appendix
        for s in ["FOUR PILLARS", "UEFA"]:
            assert s.upper() in upper, f"PDF missing regression string '{s}'"

        # Regression: trial readiness page
        assert "TRIAL READINESS" in upper or "READY FOR" in upper, "Trial-readiness page missing from PDF"
        doc.close()
