"""Session 124 (iter54) — Verification tests for J1..J6.

J1: Tightened Gemini timeouts (240→150s httpx, 300→180s asyncio) — both primary and retry.
J2: Retry-transparency backend flag (retry_in_progress set True before retry, False on completion/timeout).
J3: Status endpoint surfaces retry_in_progress in JSON payload.
J4: Frontend retry hint conditional on status?.retry_in_progress (data-testid=bg-analysis-retry-hint).
J5/J6: Regression grep (Session 116-123 fixes intact — VIP eligibility endpoint, admin login,
       /api/faq, /api/media 404, extract_json robustness, no 'chef'/'Cooking').

Testing strategy:
 - Source-code grep for structural properties (timeouts, retry_in_progress writes, hint JSX).
 - Live API hits (login, /api/reports/{id}/status, /api/faq, /api/media/missing-key, /api/me/upload-eligibility)
   against the public REACT_APP_BACKEND_URL to confirm the wired behavior end-to-end.
 - extract_json import + smoke-run the 12 tricky formats (Session 123 regression).
"""

import os
import re
import sys
import json
import time
from pathlib import Path

import pytest
import requests

BACKEND_DIR = "/app/backend"
SERVER_PY = Path(BACKEND_DIR) / "server.py"
JSX_PATH = Path("/app/frontend/src/components/BackgroundAnalysisTracker.jsx")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # fall back to reading frontend/.env
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip()
            break
BASE_URL = (BASE_URL or "").rstrip("/")

ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"
TESTVIP_EMAIL = "testvip@scoutmeplay.com"
TESTVIP_PASSWORD = "TestVip@2026!"

sys.path.insert(0, BACKEND_DIR)


# --------------------------- source snapshot ---------------------------


@pytest.fixture(scope="module")
def server_src() -> str:
    return SERVER_PY.read_text()


@pytest.fixture(scope="module")
def jsx_src() -> str:
    return JSX_PATH.read_text()


# --------------------------- J1: tightened timeouts ---------------------------


class TestJ1_TightenedTimeouts:
    """Session 124 tightened worst-case retry from ~10 min to ~6 min."""

    def test_primary_extra_params_timeout_150(self, server_src):
        # primary call: chat.extra_params timeout set to 150.0
        assert 'chat.extra_params = {**(chat.extra_params or {}), "timeout": 150.0, "temperature": 0.2}' in server_src, \
            "primary chat.extra_params timeout should be 150.0"

    def test_primary_wait_for_180(self, server_src):
        # primary call: asyncio.wait_for(..., timeout=180)
        pattern = r"await asyncio\.wait_for\(chat\.send_message\(user_message\), timeout=180\)"
        assert re.search(pattern, server_src), "primary wait_for should be timeout=180"

    def test_retry_extra_params_timeout_150(self, server_src):
        assert 'retry_chat.extra_params = {"timeout": 150.0, "temperature": 0.2}' in server_src, \
            "retry chat.extra_params timeout should be 150.0"

    def test_retry_wait_for_180(self, server_src):
        pattern = r"await asyncio\.wait_for\(retry_chat\.send_message\(retry_message\), timeout=180\)"
        assert re.search(pattern, server_src), "retry wait_for should be timeout=180"

    def test_no_old_timeout_240(self, server_src):
        # 240 must not appear as a timeout value anywhere in Gemini call paths
        hits = re.findall(r'"timeout":\s*240', server_src)
        hits += re.findall(r"timeout\s*=\s*240", server_src)
        assert hits == [], f"stale 240s timeouts still present: {hits}"

    def test_no_old_timeout_300_wait_for_send_message(self, server_src):
        # Old 300s wait_for around send_message must be gone
        assert not re.search(r"asyncio\.wait_for\([^)]*send_message[^)]*timeout=300\b", server_src), \
            "stale 300s wait_for(send_message) still present"


# --------------------------- J2: retry-transparency flag ---------------------------


class TestJ2_RetryInProgressFlag:
    """Backend writes retry_in_progress True → False around the retry send_message."""

    def test_grep_at_least_three_hits(self, server_src):
        hits = [ln for ln in server_src.splitlines() if "retry_in_progress" in ln]
        # Set True (once) + Set False on timeout + Set False after retry + surfaced in status
        # → at least 4 lines expected, but the spec says "≥ 3".
        assert len(hits) >= 3, f"expected ≥3 retry_in_progress lines, got {len(hits)}: {hits}"

    def test_set_true_before_retry(self, server_src):
        assert re.search(
            r'\$set.*"retry_in_progress":\s*True.*"retry_started_at"',
            server_src,
        ), "must set retry_in_progress True with retry_started_at before retry"

    def test_report_id_derived_from_session_prefix(self, server_src):
        # for prefix in ("gate-", "preview-", "full-"): ...
        assert re.search(r'for prefix in \("gate-", "preview-", "full-"\)', server_src), \
            "must derive report_id from gate-/preview-/full- session prefix"

    def test_clear_flag_on_timeout(self, server_src):
        # Look inside the TimeoutError branch — retry_in_progress: False is set before raising 504
        # We just check that the two "False" set-clauses exist in the file.
        false_clears = re.findall(r'"retry_in_progress":\s*False', server_src)
        assert len(false_clears) >= 2, \
            f"expected ≥2 retry_in_progress False clears (timeout + completion), got {len(false_clears)}"

    def test_uses_db_reports_update_one(self, server_src):
        assert 'db.reports.update_one' in server_src, "must persist flag via db.reports.update_one"


# --------------------------- J3: status endpoint surfaces flag ---------------------------


class TestJ3_StatusEndpointExposesFlag:
    def test_source_returns_retry_in_progress(self, server_src):
        assert '"retry_in_progress": bool(doc.get("retry_in_progress"))' in server_src, \
            "GET /api/reports/{id}/status must return retry_in_progress"

    def test_endpoint_route_present(self, server_src):
        assert '@api_router.get("/reports/{report_id}/status")' in server_src

    def test_live_status_endpoint_returns_401_without_auth(self):
        # Sanity: endpoint reachable; unauth → 401
        r = requests.get(f"{BASE_URL}/api/reports/deadbeef/status", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403 unauth, got {r.status_code}: {r.text[:200]}"

    def test_live_status_endpoint_payload_has_key(self):
        """Login as admin, find any report id, GET status, assert retry_in_progress key present."""
        login = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        if login.status_code != 200:
            pytest.skip(f"admin login failed ({login.status_code}) — cannot exercise status endpoint")
        token = login.json().get("token") or login.json().get("access_token")
        assert token, f"no token in login response: {login.json()}"
        h = {"Authorization": f"Bearer {token}"}

        # Find any report — admin scope. Try /api/admin/reports or fall back to a known id.
        report_id = None
        for path in ("/api/admin/reports", "/api/reports"):
            r = requests.get(f"{BASE_URL}{path}", headers=h, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data:
                    report_id = data[0].get("id") or data[0].get("_id")
                    if report_id:
                        break
                elif isinstance(data, dict):
                    items = data.get("reports") or data.get("items") or []
                    if items:
                        report_id = items[0].get("id") or items[0].get("_id")
                        if report_id:
                            break
        if not report_id:
            # last-known seeded id
            report_id = "64f59196-a520-4ba4-a0f9-de96df8802ef"

        r = requests.get(f"{BASE_URL}/api/reports/{report_id}/status", headers=h, timeout=15)
        assert r.status_code == 200, f"status endpoint {r.status_code}: {r.text[:200]}"
        body = r.json()
        assert "retry_in_progress" in body, f"status payload missing retry_in_progress: {body}"
        assert isinstance(body["retry_in_progress"], bool), \
            f"retry_in_progress must be bool, got {type(body['retry_in_progress'])}"
        # For a not-in-retry report the flag should be False
        assert body["retry_in_progress"] is False, \
            f"seeded report should not be mid-retry, got {body['retry_in_progress']}"


# --------------------------- J4: frontend hint ---------------------------


class TestJ4_FrontendRetryHint:
    def test_jsx_has_conditional_render(self, jsx_src):
        assert "status?.retry_in_progress" in jsx_src, \
            "JSX must gate hint on status?.retry_in_progress"

    def test_jsx_testid_and_copy(self, jsx_src):
        assert 'data-testid="bg-analysis-retry-hint"' in jsx_src, \
            "hint div must carry data-testid='bg-analysis-retry-hint'"
        assert "Prøver igen for bedste kvalitet" in jsx_src, \
            "hint text must match Danish copy 'Prøver igen for bedste kvalitet…'"

    def test_amber_italic_styling(self, jsx_src):
        # amber tone + italic per user description
        block = jsx_src[jsx_src.index("status?.retry_in_progress"):]
        block = block[: block.index("</div>") + 6] if "</div>" in block else block[:400]
        assert "italic" in block, f"hint must be italic — block: {block[:400]!r}"
        assert "amber" in block, f"hint must use amber tone — block: {block[:400]!r}"


# --------------------------- J5/J6: regression checks ---------------------------


class TestJ6_RegressionSession116_123:
    def test_admin_login_works(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        assert r.status_code == 200, f"admin login {r.status_code}: {r.text[:200]}"
        b = r.json()
        assert (b.get("token") or b.get("access_token")), f"no token: {b}"

    def test_faq_endpoint_returns_200(self):
        r = requests.get(f"{BASE_URL}/api/faq", timeout=15)
        assert r.status_code == 200, f"/api/faq {r.status_code}: {r.text[:200]}"
        # payload should be a list or dict
        data = r.json()
        assert isinstance(data, (list, dict)), f"unexpected /api/faq shape: {type(data)}"

    def test_media_missing_key_returns_404_json(self):
        r = requests.get(f"{BASE_URL}/api/media/nonexistent-{int(time.time())}", timeout=15)
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"
        body = r.json()
        assert body.get("detail") == "Media not found", f"wrong detail: {body}"

    def test_vip_eligibility_returns_subscription_reason(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TESTVIP_EMAIL, "password": TESTVIP_PASSWORD},
            timeout=15,
        )
        if r.status_code != 200:
            pytest.skip(f"testvip login failed ({r.status_code}): {r.text[:150]}")
        token = r.json().get("token") or r.json().get("access_token")
        h = {"Authorization": f"Bearer {token}"}
        e = requests.get(f"{BASE_URL}/api/me/upload-eligibility", headers=h, timeout=15)
        assert e.status_code == 200, f"eligibility {e.status_code}: {e.text[:200]}"
        body = e.json()
        assert body.get("eligible") is True, f"testvip should be eligible: {body}"
        assert body.get("reason") == "subscription", \
            f"testvip reason should be 'subscription', got {body.get('reason')}: {body}"

    def test_no_chef_or_cooking_in_backend(self):
        import subprocess
        p = subprocess.run(
            ["grep", "-rE", r"\bchef\b|Cooking", "/app/backend", "--include=*.py",
             "--exclude-dir=tests", "--exclude-dir=__pycache__"],
            capture_output=True, text=True,
        )
        assert p.stdout.strip() == "", f"unexpected chef/Cooking hits: {p.stdout}"

    def test_no_chef_or_cooking_in_frontend_src(self):
        import subprocess
        p = subprocess.run(
            ["grep", "-rE", r"\bchef\b|Cooking",
             "/app/frontend/src", "--include=*.jsx", "--include=*.js"],
            capture_output=True, text=True,
        )
        assert p.stdout.strip() == "", f"unexpected chef/Cooking hits: {p.stdout}"


class TestJ6_ExtractJsonStillRobust:
    """Session 122/123 extract_json tolerance is intact under Session 124 edits."""

    @pytest.fixture(scope="class")
    def extract_json(self):
        from server import extract_json as _fn
        return _fn

    @pytest.mark.parametrize("payload,expected", [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"k": 42}\n```', {"k": 42}),
        ('```\n{"k": 42}\n```', {"k": 42}),
        ('Sure! Here is the JSON:\n{"score": 99}\nHope that helps.', {"score": 99}),
        ('{"score": 99,}', {"score": 99}),  # trailing comma
        ('{\u201cscore\u201d: 99}', {"score": 99}),  # smart double quotes
        ('{"outer": {"inner": {"deep": 1}}}', {"outer": {"inner": {"deep": 1}}}),
        ('\ufeff{"a": "b"}', {"a": "b"}),  # BOM
        ('```json\n{"example":1}\n```\n```json\n{"real": true, "score": 99}\n```',
         {"real": True, "score": 99}),  # largest fence wins
        ('{"quote": "he said \\"hi {world}\\" today"}',
         {"quote": 'he said "hi {world}" today'}),  # braces inside string
        ('  {"x": [1,2,3,]}  ', {"x": [1, 2, 3]}),  # trailing comma in array
        ('{"txt": \u201cok\u201d}', {"txt": "ok"}),  # smart quote value
    ])
    def test_tricky_formats(self, extract_json, payload, expected):
        d = extract_json(payload)
        assert d == expected, f"payload {payload!r} produced {d!r}, expected {expected!r}"

    @pytest.mark.parametrize("bad", [
        "",                    # empty
        "no json here at all", # no braces
        "[1,2,3]",             # top-level list (must reject as not-dict)
    ])
    def test_invalid_inputs_raise(self, extract_json, bad):
        with pytest.raises(ValueError):
            extract_json(bad)
