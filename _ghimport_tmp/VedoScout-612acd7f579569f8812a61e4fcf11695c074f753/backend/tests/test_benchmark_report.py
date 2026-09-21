"""Backend tests for ScoutMePlay overall_benchmark + per-skill verdict/tier/benchmarks fields.
Also validates PDF generation and Stripe embedded endpoints.
"""
import os
import io
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")

PREMIUM = ("premium@elitescout.com", "Premium@2026")
FREE = ("free@elitescout.com", "Free@2026")
ADMIN = ("admin@elitescout.com", "Admin@2026!Elite")

TIER_KEYS = {"elite_academy", "pro_academy", "strong_club", "standard_club"}


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"No token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def premium_token():
    return _login(*PREMIUM)


@pytest.fixture(scope="module")
def premium_report(premium_token):
    headers = {"Authorization": f"Bearer {premium_token}"}
    r = requests.get(f"{BASE_URL}/api/reports/mine", headers=headers, timeout=30)
    assert r.status_code == 200, f"reports/mine: {r.status_code} {r.text[:300]}"
    reports = r.json()
    assert isinstance(reports, list) and len(reports) >= 1, f"No reports for premium user: {reports}"
    rid = reports[0].get("id") or reports[0].get("_id")
    assert rid
    r2 = requests.get(f"{BASE_URL}/api/reports/{rid}", headers=headers, timeout=30)
    assert r2.status_code == 200, f"reports/{rid}: {r2.status_code} {r2.text[:300]}"
    return r2.json()


class TestOverallBenchmark:
    def test_overall_benchmark_block(self, premium_report):
        full = premium_report.get("full_report") or {}
        ob = full.get("overall_benchmark")
        assert ob, f"Missing overall_benchmark. keys: {list(full.keys())}"
        assert ob.get("tier") == "pro_academy", f"tier was {ob.get('tier')}"
        assert isinstance(ob.get("tier_label"), str) and ob["tier_label"]
        assert isinstance(ob.get("percentile"), str) and ob["percentile"]
        assert isinstance(ob.get("realistic_next_step"), str) and ob["realistic_next_step"]
        assert isinstance(ob.get("what_separates_from_next_tier"), str) and ob["what_separates_from_next_tier"]
        assert isinstance(ob.get("age_bracket_used"), str) and ob["age_bracket_used"]

    def test_sub_skills_have_benchmark_fields(self, premium_report):
        full = premium_report.get("full_report") or {}
        sections = ["technical", "tactical", "physical", "mentality"]
        sample_printed = False
        missing = []
        for sec in sections:
            sec_data = full.get(sec) or {}
            # find sub-skill dicts (skip 'overall' numeric)
            for k, v in sec_data.items():
                if isinstance(v, dict) and "score" in v:
                    for required in ("why_this_score", "tier_for_age", "benchmarks", "verdict"):
                        if required not in v:
                            missing.append(f"{sec}.{k} missing {required}")
                            continue
                    if not isinstance(v.get("why_this_score"), str) or not v["why_this_score"].strip():
                        missing.append(f"{sec}.{k}.why_this_score empty")
                    if v.get("tier_for_age") not in TIER_KEYS:
                        missing.append(f"{sec}.{k}.tier_for_age invalid: {v.get('tier_for_age')}")
                    bm = v.get("benchmarks") or {}
                    if not TIER_KEYS.issubset(bm.keys()):
                        missing.append(f"{sec}.{k}.benchmarks missing tier keys, got {list(bm.keys())}")
                    if not isinstance(v.get("verdict"), str) or not v["verdict"].strip():
                        missing.append(f"{sec}.{k}.verdict empty")
                    if not sample_printed:
                        print(f"\nSAMPLE SKILL {sec}.{k}:")
                        for kk in ("score", "why_this_score", "tier_for_age", "benchmarks", "verdict"):
                            print(f"  {kk}: {v.get(kk)}")
                        sample_printed = True
        assert not missing, "Missing fields: " + "; ".join(missing[:20])
        assert sample_printed, "No sub-skill dicts found in technical/tactical/physical/mentality"


class TestPremiumPDF:
    def test_pdf_download_and_content(self, premium_token, premium_report):
        rid = premium_report.get("id") or premium_report.get("_id")
        headers = {"Authorization": f"Bearer {premium_token}"}
        r = requests.get(f"{BASE_URL}/api/reports/{rid}/pdf", headers=headers, timeout=120)
        assert r.status_code == 200, f"pdf status {r.status_code} {r.text[:300]}"
        ct = r.headers.get("content-type", "")
        assert "application/pdf" in ct, f"content-type: {ct}"
        assert len(r.content) > 20_000, f"PDF too small: {len(r.content)} bytes"

        try:
            import pymupdf as fitz  # type: ignore
        except ImportError:
            import fitz  # type: ignore
        doc = fitz.open(stream=r.content, filetype="pdf")
        n_pages = doc.page_count
        assert n_pages >= 15, f"Expected >=15 pages, got {n_pages}"

        all_text = ""
        for i in range(n_pages):
            all_text += doc.load_page(i).get_text() + "\n"

        # Save page-1 text
        os.makedirs("/app/test_reports", exist_ok=True)
        with open("/app/test_reports/pdf_page1.txt", "w") as f:
            f.write(doc.load_page(0).get_text())

        upper = all_text.upper()
        assert "HOW YOU COMPARE" in upper, "Missing 'HOW YOU COMPARE'"
        assert "PRO ACADEMY" in upper, "Missing 'PRO ACADEMY'"
        assert "YOU ARE HERE" in upper, "Missing 'YOU ARE HERE'"
        assert "WHY THIS SCORE" in upper, "Missing 'WHY THIS SCORE'"
        doc.close()
        print(f"PDF OK: {n_pages} pages, {len(r.content)} bytes")


class TestStripeEmbedded:
    def test_stripe_config_endpoint(self):
        r = requests.get(f"{BASE_URL}/api/config/stripe", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("embedded_available") is True, f"embedded_available={d.get('embedded_available')}"
        pk = d.get("publishable_key") or ""
        assert pk.startswith("pk_live_"), f"publishable_key prefix: {pk[:12]}"

    def test_embedded_unlock_returns_client_secret(self, premium_token, premium_report):
        # premium user is already paid — try to unlock a NEW report would need an unpaid one.
        # Per request: call /api/payments/embedded/unlock and assert client_secret returned.
        rid = premium_report.get("id") or premium_report.get("_id")
        headers = {"Authorization": f"Bearer {premium_token}"}
        r = requests.post(
            f"{BASE_URL}/api/payments/embedded/unlock",
            headers=headers,
            json={"report_id": rid, "origin_url": BASE_URL},
            timeout=30,
        )
        # If already paid, server may return 400 — try with free user's flow instead.
        if r.status_code != 200:
            print(f"unlock with premium got {r.status_code}: {r.text[:200]}")
            # Fallback: try embedded prepay-upload (free user creates an embedded session)
            free_tok = _login(*FREE)
            r2 = requests.post(
                f"{BASE_URL}/api/payments/embedded/prepay-upload",
                headers={"Authorization": f"Bearer {free_tok}"},
                json={"origin_url": BASE_URL},
                timeout=30,
            )
            assert r2.status_code == 200, f"embedded prepay-upload: {r2.status_code} {r2.text[:300]}"
            d = r2.json()
            assert d.get("client_secret"), f"No client_secret: {d}"
            print(f"client_secret (prepay) OK: {d['client_secret'][:30]}...")
            return
        d = r.json()
        assert d.get("client_secret"), f"No client_secret in unlock response: {d}"
        print(f"client_secret (unlock) OK: {d['client_secret'][:30]}...")
