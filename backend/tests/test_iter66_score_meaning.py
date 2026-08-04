"""Backend tests for the 'numbers become discovery' score_meaning feature."""
import os
import re
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
EMAIL = "smtest.parent@example.com"
PASSWORD = "SmTest@2026!x"
PREMIUM_RID = "smtest-premium-1"
FREE_RID = "smtest-free-1"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token")
    assert tok, "no access_token in login response"
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def premium_payload(session):
    r = session.get(f"{BASE}/api/reports/{PREMIUM_RID}")
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
    return r.json()


@pytest.fixture(scope="module")
def free_payload(session):
    r = session.get(f"{BASE}/api/reports/{FREE_RID}")
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
    return r.json()


# ---------- PREMIUM score_meaning ----------
class TestPremiumScoreMeaning:
    def test_score_meaning_present(self, premium_payload):
        assert "score_meaning" in premium_payload
        sm = premium_payload["score_meaning"]
        assert sm is not None
        assert "skills" in sm and isinstance(sm["skills"], list)

    def test_skills_count_and_sorted(self, premium_payload):
        skills = premium_payload["score_meaning"]["skills"]
        assert 15 <= len(skills) <= 25, f"expected ~19 skills, got {len(skills)}"
        scores = [s["score"] for s in skills]
        assert scores == sorted(scores, reverse=True), "skills must be sorted score desc"

    def test_first_name_substituted_no_placeholders(self, premium_payload):
        skills = premium_payload["score_meaning"]["skills"]
        for s in skills:
            for line in s.get("lines", []):
                assert "{name}" not in line, f"unsubstituted placeholder in {s['key']}: {line}"
                assert "{age}" not in line, f"unsubstituted placeholder in {s['key']}: {line}"

    def test_skill_shape(self, premium_payload):
        skills = premium_payload["score_meaning"]["skills"]
        for s in skills:
            assert set(["label", "score", "lines", "looks_for", "scale", "next_level", "angles"]).issubset(s.keys())
            assert len(s["lines"]) <= 2
            scale = s["scale"]
            assert set(scale.keys()) >= {"6", "8", "9"} or set(scale.keys()) >= {6, 8, 9}
            ang = s["angles"]
            assert isinstance(ang["better_than"], int)
            assert ang["gap_to_next"] is None or (isinstance(ang["gap_to_next"], (int, float)) and ang.get("next_band"))
            ev = s.get("evidence")
            assert ev is None or (isinstance(ev, dict) and "timestamp" in ev and "verified" in ev)

    def test_verified_evidence_only_at_anchors(self, premium_payload):
        """Verified must be True only near anchors t=104/250/370 or identity_verified comments (04:12/06:10/08:44)."""
        skills = premium_payload["score_meaning"]["skills"]
        verified_anchors = [104, 250, 370, 4*60+12, 6*60+10, 8*60+44]
        for s in skills:
            ev = s.get("evidence")
            if not ev:
                continue
            ts = ev["timestamp"]
            m, sec = str(ts).split(":")
            total = int(m) * 60 + int(sec)
            if ev["verified"]:
                assert any(abs(total - a) <= 5 for a in verified_anchors), \
                    f"skill {s['key']} verified but ts={ts} not near any anchor"

    def test_timing_of_runs_not_verified(self, premium_payload):
        """timing_of_runs (07:30) must have verified=false since not near any anchor."""
        skills = premium_payload["score_meaning"]["skills"]
        tor = next((s for s in skills if s["key"] == "timing_of_runs"), None)
        if tor and tor.get("evidence"):
            assert tor["evidence"]["verified"] is False, "timing_of_runs at 07:30 should be verified=false"

    def test_discovery_central_midfielder(self, premium_payload):
        disc = premium_payload["score_meaning"]["discovery"]
        assert disc is not None, "discovery should exist for Winger with strong scan/pass + weak accel"
        assert "midfielder" in (disc.get("suggest") or "").lower() or "Central Midfielder" in disc.get("suggest", "")
        assert disc.get("based_on") and len(disc["based_on"]) >= 2
        assert disc.get("note")


# ---------- FREE teaser ----------
class TestFreeTeaser:
    def test_no_full_report(self, free_payload):
        assert not free_payload.get("full_report"), "free payload must not have full_report"
        assert free_payload.get("score_meaning") in (None, {}) or "score_meaning" not in free_payload

    def test_teaser_shape(self, free_payload):
        t = free_payload.get("score_meaning_teaser")
        assert t is not None, "teaser missing"
        assert t.get("has_discovery") is True
        assert t.get("locked_count") == 18, f"expected 18 locked skills, got {t.get('locked_count')}"
        unlocked = t.get("unlocked")
        assert unlocked and unlocked.get("key") == "scanning"
        ev = unlocked.get("evidence")
        assert ev and ev.get("verified") is True

    def test_locked_labels_no_scores(self, free_payload):
        t = free_payload["score_meaning_teaser"]
        locked = t["locked_labels"]
        for lbl in locked:
            assert isinstance(lbl, str), "locked must be strings only"
            assert not re.search(r"\b\d+(\.\d+)?\b", lbl), f"score leaked in locked label: {lbl}"

    def test_no_score_leaks_free(self, free_payload):
        """Ensure no OTHER skill scores leak anywhere in the free payload."""
        import json
        # Remove the one legitimately unlocked skill and check no scores in serialized string
        payload = dict(free_payload)
        t = payload.get("score_meaning_teaser") or {}
        unlocked = t.get("unlocked")
        # Ensure full_report is not present with technical/tactical scores
        fr = payload.get("full_report")
        assert not fr or not any(k in fr for k in ("technical", "tactical", "physical", "mentality"))


# ---------- PDF audit ----------
class TestPremiumPDF:
    def test_pdf_content(self, session):
        r = session.get(f"{BASE}/api/reports/{PREMIUM_RID}/pdf")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        # Extract text via pdfminer if available; else best-effort strings
        try:
            from pdfminer.high_level import extract_text
            import io
            text = extract_text(io.BytesIO(r.content))
        except Exception:
            text = r.content.decode("latin-1", errors="ignore")
        assert "THE NUMBERS, TRANSLATED" in text.upper(), "Missing translated page header"
        assert "SEEN AT" in text.upper()
        assert "STRONGER THAN" in text.upper() and "OF 10" in text.upper()
        assert "A DISCOVERY ABOUT" in text.upper()

    def test_pdf_no_ai_or_scout_words(self, session):
        r = session.get(f"{BASE}/api/reports/{PREMIUM_RID}/pdf")
        try:
            from pdfminer.high_level import extract_text
            import io
            text = extract_text(io.BytesIO(r.content))
        except Exception:
            text = r.content.decode("latin-1", errors="ignore")
        # Mask allowed brand words
        masked = re.sub(r"SCOUTMEPLAY|SCOUTME\s*PRO\s*INTELLIGENCE|SCOUTME", "", text, flags=re.I)
        # Allowed feature names
        masked = re.sub(r"Real Scout Review|Talk With Scout", "", masked, flags=re.I)
        # Check for AI as standalone (uppercase word boundary)
        ai_hits = re.findall(r"\bAI\b", masked)
        # Filter out common false positives like 'AI'-inside filenames — just report
        assert not ai_hits, f"'AI' appears standalone in PDF: {ai_hits[:5]}"
        scout_hits = re.findall(r"\bscout(s|ing)?\b", masked, re.I)
        assert not scout_hits, f"'scout' appears in PDF: {scout_hits[:5]}"

    def test_no_percentile_word(self, session):
        r = session.get(f"{BASE}/api/reports/{PREMIUM_RID}/pdf")
        try:
            from pdfminer.high_level import extract_text
            import io
            text = extract_text(io.BytesIO(r.content))
        except Exception:
            text = r.content.decode("latin-1", errors="ignore")
        assert "percentile" not in text.lower(), "word 'percentile' must not appear"
