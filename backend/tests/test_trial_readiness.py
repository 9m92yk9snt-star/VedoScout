"""Trial Readiness + Methodology Appendix tests (iteration 6)."""
import io
import os
import json
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")
PREMIUM_EMAIL = "premium@elitescout.com"
PREMIUM_PASS = "Premium@2026"


@pytest.fixture(scope="module")
def premium_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": PREMIUM_EMAIL, "password": PREMIUM_PASS})
    assert r.status_code == 200, f"premium login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token: {r.json()}"
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def lukas_report(premium_client):
    r = premium_client.get(f"{BASE_URL}/api/reports/mine")
    assert r.status_code == 200, r.text
    reports = r.json()
    assert isinstance(reports, list) and len(reports) > 0, "no reports for premium"
    # Find Lukas
    rid = None
    for rep in reports:
        name = (rep.get("player_name") or "").lower()
        if "lukas" in name:
            rid = rep.get("id") or rep.get("_id")
            break
    if not rid:
        rid = reports[0].get("id") or reports[0].get("_id")
    full = premium_client.get(f"{BASE_URL}/api/reports/{rid}")
    assert full.status_code == 200, full.text
    return rid, full.json()


# ---------- Trial Readiness object structure ----------
def test_trial_readiness_present_and_well_formed(lukas_report):
    rid, rep = lukas_report
    tr = rep.get("trial_readiness")
    assert tr is not None, f"trial_readiness MISSING in report keys: {list(rep.keys())}"
    for k in ("position_key", "headline", "readiness_tier", "strong_club_score", "pro_academy_score", "items"):
        assert k in tr, f"trial_readiness missing key '{k}'"
    assert isinstance(tr["items"], list) and len(tr["items"]) >= 6, f"items count={len(tr['items'])}"
    headline = tr["headline"]
    assert any(headline.lower().startswith(p) for p in ("ready for", "building towards", "foundation phase")), \
        f"bad headline: {headline!r}"
    assert tr["readiness_tier"] in ("pro_academy", "strong_club", "building_strong_club", "foundation"), \
        f"bad tier: {tr['readiness_tier']}"
    for it in tr["items"]:
        for k in ("id", "label", "strong_club_met", "pro_academy_met", "value", "strong_club_min", "pro_academy_min", "no_data"):
            assert k in it, f"item missing {k}: {it}"
    print(f"HEADLINE: {tr['headline']}")
    print(f"TIER: {tr['readiness_tier']}  STRONG: {tr['strong_club_score']}  PRO: {tr['pro_academy_score']}")
    for it in tr["items"][:3]:
        print(f" - {it['id']}: {it['label']} | val={it['value']} strong_met={it['strong_club_met']} pro_met={it['pro_academy_met']}")


def test_lukas_attacking_midfielder_mapping(lukas_report):
    rid, rep = lukas_report
    tr = rep["trial_readiness"]
    assert tr["position_key"] == "attacking midfielder", \
        f"Expected 'attacking midfielder', got {tr['position_key']!r} (alias collision regression?)"
    assert tr["headline"].lower() == "ready for pro academy trial", f"unexpected headline: {tr['headline']}"
    assert len(tr["items"]) == 8, f"expected 8 items for AM, got {len(tr['items'])}"


# ---------- PDF content ----------
def test_premium_pdf_contains_methodology_and_trial_readiness(premium_client, lukas_report):
    rid, _ = lukas_report
    r = premium_client.get(f"{BASE_URL}/api/reports/{rid}/pdf")
    assert r.status_code == 200, f"PDF download failed: {r.status_code} {r.text[:200]}"
    data = r.content
    assert len(data) > 30_000, f"PDF too small: {len(data)} bytes"

    import fitz  # PyMuPDF
    doc = fitz.open(stream=io.BytesIO(data), filetype="pdf")
    assert doc.page_count >= 22, f"page_count={doc.page_count}"
    text = ""
    for p in doc:
        text += p.get_text().upper() + "\n"
    doc.close()

    must_haves = ["READY FOR", "METHODOLOGY", "UEFA", "FOUR PILLARS", "FOUR-TIER LADDER"]
    missing = [m for m in must_haves if m not in text]
    assert not missing, f"PDF missing strings: {missing}"
    # trial readiness page distinct from "READY FOR" inside trial item: also check
    assert "TRIAL READINESS" in text or "READY FOR" in text


# ---------- Alias ordering ----------
def test_alias_order_specific_before_generic_midfielder():
    p = "/app/backend/data/trial_readiness.json"
    with open(p) as f:
        catalog = json.load(f)
    aliases = catalog.get("_aliases", {})
    keys_in_order = list(aliases.keys())
    assert "attacking midfielder" in keys_in_order
    assert "central midfielder" in keys_in_order
    am_idx = keys_in_order.index("attacking midfielder")
    cm_idx = keys_in_order.index("central midfielder")
    assert am_idx < cm_idx, "attacking midfielder must be iterated before central midfielder (which holds the generic 'midfielder' alias)"
    cm_aliases = aliases["central midfielder"]
    # Specific position keys must precede 'midfielder' string inside central_midfielder aliases
    if "midfielder" in cm_aliases:
        m_pos = cm_aliases.index("midfielder")
        # ensure 'central midfielder' or specific tokens are before it
        specifics = [a for a in cm_aliases[:m_pos] if "midfielder" in a or a in ("cm", "box to box", "central mid")]
        assert specifics, f"generic 'midfielder' must not be the first item in central_midfielder aliases: {cm_aliases}"
