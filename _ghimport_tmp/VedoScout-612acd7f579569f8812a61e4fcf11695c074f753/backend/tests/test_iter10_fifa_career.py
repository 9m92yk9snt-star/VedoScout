"""
Iteration 10 — independent validation of Layer 5 (FIFA k-NN) + Step 3 (career_brief)
+ PDF regeneration + Gemini narrative cache version 3.

Runs against the live preview backend at REACT_APP_BACKEND_URL.
"""
import os
import re
import time
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com"
).rstrip("/")
PREMIUM_EMAIL = "premium@elitescout.com"
PREMIUM_PASSWORD = "Premium@2026"


@pytest.fixture(scope="module")
def headers():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": PREMIUM_EMAIL, "password": PREMIUM_PASSWORD},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def lukas(headers):
    rs = requests.get(f"{BASE_URL}/api/reports/mine", headers=headers, timeout=30)
    assert rs.status_code == 200
    paid = [r for r in rs.json() if r.get("is_paid") or r.get("manually_unlocked")]
    assert paid, "no unlocked Lukas report"
    rid = paid[0]["id"]
    r = requests.get(f"{BASE_URL}/api/reports/{rid}", headers=headers, timeout=120)
    assert r.status_code == 200, r.text
    rep = r.json()
    rep["_rid"] = rid
    return rep


# ---------- FIFA lens hard credibility cap ----------

def test_fifa_similarity_hard_cap_92(lukas):
    arch = lukas["archetype"]
    fifa = arch["lenses"]["fifa"]
    assert fifa["similarity_pct"] <= 92.0, (
        f"P0: FIFA top similarity {fifa['similarity_pct']}% exceeds 92% cap"
    )
    for n in arch.get("fifa_neighbors", []):
        assert n["similarity_pct"] <= 92.0, (
            f"P0: neighbor {n['name']} sim {n['similarity_pct']}% exceeds 92% cap"
        )


def test_fifa_top_match_in_expected_range(lukas):
    """For Lukas (Modric-type AM), top FIFA match should be 80-92%."""
    fifa = lukas["archetype"]["lenses"]["fifa"]
    assert 80.0 <= fifa["similarity_pct"] <= 92.0, (
        f"top similarity {fifa['similarity_pct']}% outside expected 80-92 for Lukas"
    )


def test_fifa_neighbors_count_and_sort(lukas):
    neighbors = lukas["archetype"]["fifa_neighbors"]
    assert len(neighbors) == 5, f"expected 5 neighbors, got {len(neighbors)}"
    sims = [n["similarity_pct"] for n in neighbors]
    assert sims == sorted(sims, reverse=True)
    for n in neighbors:
        assert n.get("name") and n.get("club")
        assert isinstance(n.get("nearest_attrs"), list) and len(n["nearest_attrs"]) >= 1


def test_fifa_lens_why_mentions_db_size(lukas):
    why = lukas["archetype"]["lenses"]["fifa"].get("why", "")
    assert "7,473" in why or "7473" in why or "FIFA-rated pros" in why, (
        f"FIFA lens 'why' should reference 7,473 FIFA-rated pros — got: {why!r}"
    )


def test_fifa_meta_size(lukas):
    meta = lukas["archetype"].get("fifa_db_meta") or {}
    assert meta.get("size", 0) >= 7000, f"FIFA DB meta size too small: {meta}"


# ---------- Step 3: career_brief on Modric primary ----------

def test_career_brief_modric_specifics(lukas):
    cb = lukas["archetype"].get("career_brief") or ""
    assert len(cb) > 60, f"career_brief too short: {cb!r}"
    # Must mention at least one verifiable Modric career stat
    keywords = ["Modric", "Modrić", "Croatia", "Ballon d'Or", "Real Madrid", "Champions League"]
    assert any(k in cb for k in keywords), f"career_brief missing Modric-verifiable keyword: {cb}"


# ---------- Lens regression: 4 original lenses still capped to 10 ----------

def test_legacy_4_lenses_score_within_10(lukas):
    lenses = lukas["archetype"]["lenses"]
    for k in ("style", "build", "role", "path"):
        s = lenses[k]["score"]
        assert 0.0 <= s <= 10.0, f"P0 regression: lens '{k}' score {s} outside 0-10"


# ---------- Layer 4 legacy regression ----------

def test_legacy_archetype_fields_intact(lukas):
    arch = lukas["archetype"]
    for f in ("id", "name", "club", "league", "tier", "match_strength", "alternatives", "traits"):
        assert f in arch, f"legacy field '{f}' missing — regression"


# ---------- Narrative cache v3 weaving ----------

def test_narrative_weaves_fifa_or_career(lukas):
    nar = lukas["archetype"].get("narrative") or ""
    assert nar, "narrative missing"
    # cache version 3 prompt should weave FIFA top match name OR a career_brief stat
    fifa_top = lukas["archetype"]["lenses"]["fifa"]["name"]
    cb = lukas["archetype"].get("career_brief", "")
    career_signals = ["Croatia", "Ballon", "Real Madrid", "Champions League", "Modric"]
    has_fifa_ref = fifa_top.split()[-1].lower() in nar.lower() or "closest" in nar.lower() \
                   or "data" in nar.lower() or "FIFA" in nar
    has_career_ref = any(k in nar for k in career_signals)
    assert has_fifa_ref or has_career_ref, (
        f"narrative weaves neither FIFA nor career stats. nar={nar!r} fifa_top={fifa_top}"
    )


# ---------- PDF: contains FIFA and CAREER SNAPSHOT sections ----------

def test_pdf_contains_fifa_and_career_sections(lukas, headers):
    rid = lukas["_rid"]
    r = requests.get(f"{BASE_URL}/api/reports/{rid}/pdf", headers=headers, timeout=120)
    assert r.status_code == 200, f"PDF download failed: {r.status_code} {r.text[:200]}"
    assert r.headers.get("content-type", "").startswith("application/pdf"), \
        f"not a PDF: {r.headers.get('content-type')}"
    body = r.content
    assert len(body) > 10_000, f"PDF too small ({len(body)} bytes)"
    # Save for manual inspection
    pdf_path = "/tmp/lukas_iter10.pdf"
    with open(pdf_path, "wb") as f:
        f.write(body)
    # Extract text
    try:
        from pypdf import PdfReader
    except ImportError:
        import subprocess
        subprocess.run(["pip", "install", "pypdf"], check=True, capture_output=True)
        from pypdf import PdfReader
    reader = PdfReader(pdf_path)
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    text_upper = text.upper()
    # Required new strings
    for needle in ["FIFA DATA TWIN", "CAREER SNAPSHOT"]:
        assert needle in text_upper, f"PDF missing '{needle}'. Sample: {text_upper[:500]}"
    # Either "REAL SIMILARITY SEARCH" or "k-NN" indicator
    assert "K-NN" in text_upper or "SIMILARITY" in text_upper, \
        "PDF missing k-NN / similarity wording"
    # Should contain at least 3 percentage signs in close range (5-row table)
    pct_count = len(re.findall(r"\d{2}\.\d%", text))
    assert pct_count >= 3, f"expected FIFA table similarity %, got {pct_count} matches"
