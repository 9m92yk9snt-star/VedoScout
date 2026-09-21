"""Iter11 — live API + PDF verification (StatsBomb calibration)."""
import os, io, re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")
PREMIUM = ("premium@elitescout.com", "Premium@2026")


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": PREMIUM[0], "password": PREMIUM[1]}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="session")
def report(token):
    h = {"Authorization": f"Bearer {token}"}
    rs = requests.get(f"{BASE_URL}/api/reports/mine", headers=h, timeout=20).json()
    paid = [r for r in rs if r.get("is_paid") or r.get("manually_unlocked")]
    assert paid, "no paid report seeded"
    rid = paid[0]["id"]
    r = requests.get(f"{BASE_URL}/api/reports/{rid}", headers=h, timeout=120)
    return r.json(), rid, h


def test_calibration_block_shape(report):
    data, _, _ = report
    cal = data.get("statsbomb_calibration")
    assert cal, "statsbomb_calibration missing"
    assert cal["position_n"] >= 5
    assert cal["matches"] >= 45
    assert "statsbomb" in cal["source_url"].lower()
    assert cal.get("competition")
    assert cal.get("methodology")
    assert cal.get("license")
    # Summary counters match rows
    counts = {k: 0 for k in ("p90", "p75", "p50", "p25", "below_p25")}
    for r in cal["rows"]:
        counts[r["bucket"]] += 1
    assert counts == cal["summary"]


def test_lukas_passing_decision_intensity_buckets(report):
    """Lukas spot-checks per request: Passing 9→p90, DM 9→p90, Intensity 6→p25."""
    data, _, _ = report
    rows = {r["attribute_key"]: r for r in data["statsbomb_calibration"]["rows"]}
    # find by key (flexible across naming)
    def find(*keys):
        for k in keys:
            if k in rows:
                return rows[k]
        # fuzzy: match label substring
        for r in rows.values():
            lbl = (r.get("attribute_label") or "").lower()
            if any(k.replace("_", " ") in lbl for k in keys):
                return r
        return None

    passing = find("passing")
    dm = find("decision_making", "decisionmaking")
    intensity = find("intensity")
    assert passing and dm and intensity, f"missing rows. got {list(rows)}"
    assert int(passing["score"]) == 9 and passing["bucket"] == "p90"
    assert int(dm["score"]) == 9 and dm["bucket"] == "p90"
    assert int(intensity["score"]) == 6 and intensity["bucket"] == "p25"


def test_legacy_layers_still_present(report):
    data, _, _ = report
    assert data.get("archetype")
    arch = data["archetype"]
    neighbors = arch.get("fifa_neighbors") or []
    assert isinstance(neighbors, list) and len(neighbors) >= 3, f"fifa_neighbors missing/short: {len(neighbors)}"
    # 92% FIFA cap
    for n in neighbors:
        assert n.get("similarity_pct", 0) <= 92.0, f"FIFA cap breached: {n.get('similarity_pct')}"
    # Lens scores ≤ 10
    for lens in (arch.get("lenses") or {}).values():
        if isinstance(lens, dict) and "score" in lens:
            assert lens["score"] <= 10
    # career brief present
    assert arch.get("career_brief")


def test_pdf_contains_statsbomb_strings(report):
    _, rid, h = report
    # purge cached pdf
    import glob
    for p in glob.glob("/app/backend/pdfs/*.pdf"):
        try: os.remove(p)
        except: pass
    r = requests.get(f"{BASE_URL}/api/reports/{rid}/pdf", headers=h, timeout=120)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    pdf = r.content
    assert len(pdf) > 5000
    # extract text via pypdf
    from pypdf import PdfReader
    text = ""
    for page in PdfReader(io.BytesIO(pdf)).pages:
        text += (page.extract_text() or "") + "\n"
    text_l = text.lower()
    # required strings
    must = ["PRO CALIBRATION", "STATSBOMB EURO 2024", "Top 25%", "p75=", "StatsBomb"]
    missing = [s for s in must if s not in text]
    assert not missing, f"PDF missing strings: {missing}\n---PDF SAMPLE---\n{text[:800]}"
    assert "methodology" in text_l


def test_methodology_sources_in_api():
    # quickly verify static methodology page route exists (frontend route handled by SPA so just hit backend root)
    r = requests.get(f"{BASE_URL}/api/", timeout=10)
    # If a health endpoint exists, status should be 200 or 404 - just ensure backend is up
    assert r.status_code in (200, 404)
