"""Live API integration tests for Tier 3 Progress Tracking router.

Hits the deployed backend via REACT_APP_BACKEND_URL and verifies the
new /api/progress/* surface plus upload-eligibility / webhook safety.
"""

import io
import os
import struct
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com"
).rstrip("/")

PREMIUM_EMAIL = "premium@elitescout.com"
PREMIUM_PASSWORD = "Premium@2026"
FREE_EMAIL = "free@elitescout.com"
FREE_PASSWORD = "Free@2026"


# --- helpers ---------------------------------------------------------------


def _login(email: str, password: str) -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30
    )
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:200]}"
    body = r.json()
    return body.get("access_token") or body["token"]


@pytest.fixture(scope="module")
def premium_token():
    return _login(PREMIUM_EMAIL, PREMIUM_PASSWORD)


@pytest.fixture(scope="module")
def premium_headers(premium_token):
    return {"Authorization": f"Bearer {premium_token}"}


@pytest.fixture(scope="module")
def mongo():
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db = os.environ.get("DB_NAME", "test_database")
    return MongoClient(url)[db]


# --- player profiles list --------------------------------------------------


def test_progress_players_list(premium_headers):
    r = requests.get(f"{BASE_URL}/api/progress/players", headers=premium_headers, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "items" in data, data
    players = data["items"]
    assert len(players) >= 2, f"expected >=2 player profiles, got {len(players)}"
    names = [p.get("name") or p.get("display_name") for p in players]
    # premium user should have Lukas A. and Almin Orman
    assert any("Lukas" in (n or "") for n in names), names
    assert any("Almin" in (n or "") for n in names), names
    for p in players:
        assert "id" in p
        assert "report_count" in p


# --- trajectory ------------------------------------------------------------


@pytest.fixture(scope="module")
def lukas_profile_id(premium_headers):
    r = requests.get(f"{BASE_URL}/api/progress/players", headers=premium_headers, timeout=30)
    for p in r.json()["items"]:
        if "Lukas" in (p.get("name") or p.get("display_name") or ""):
            return p["id"]
    pytest.skip("Lukas profile not found")


@pytest.fixture(scope="module")
def almin_profile_id(premium_headers):
    r = requests.get(f"{BASE_URL}/api/progress/players", headers=premium_headers, timeout=30)
    for p in r.json()["items"]:
        if "Almin" in (p.get("name") or p.get("display_name") or ""):
            return p["id"]
    pytest.skip("Almin profile not found")


def test_trajectory_lukas_two_reports(premium_headers, lukas_profile_id):
    r = requests.get(
        f"{BASE_URL}/api/progress/players/{lukas_profile_id}/trajectory",
        headers=premium_headers,
        timeout=60,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    t = body.get("trajectory", body)
    # structure
    for key in (
        "timeline",
        "verdict",
        "badges",
        "deltas",
        "archetype_overlay",
        "mission",
    ):
        assert key in t, f"missing {key} in trajectory"
    assert isinstance(t["timeline"], list)
    assert len(t["timeline"]) >= 2
    for snap in t["timeline"]:
        for fld in ("date", "age", "overall", "pillars", "age_adjusted_pct"):
            assert fld in snap, snap
    # verdict
    assert t["verdict"] in ("ahead", "on_track", "plateau"), t["verdict"]
    # narrative present for 2+ reports
    assert t.get("narrative"), "narrative should be non-empty for 2+ reports"
    # badges include First Century + Pro Comparison Unlocked
    badge_names = [b.get("name") or b.get("title") or b for b in t["badges"]]
    flat = " ".join(str(x) for x in badge_names)
    assert "First Century" in flat or any("Century" in str(x) for x in badge_names)
    assert "Pro Comparison" in flat or any("Pro Comparison" in str(x) for x in badge_names)
    # deltas
    d = t["deltas"]
    assert "overall_raw" in d
    assert "overall_age_adjusted_pct" in d
    # archetype overlay
    ao = t["archetype_overlay"]
    for fld in ("archetype_name", "tier_key", "curve", "points"):
        assert fld in ao, ao
    # mission with 2 previous_results, both improved
    m = t["mission"]
    assert "previous_results" in m
    assert len(m["previous_results"]) >= 2


def test_trajectory_almin_first_report(premium_headers, almin_profile_id):
    r = requests.get(
        f"{BASE_URL}/api/progress/players/{almin_profile_id}/trajectory",
        headers=premium_headers,
        timeout=60,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    t = body.get("trajectory", body)
    assert t["verdict"] == "first_report", t["verdict"]
    # narrative may be None/empty for single report
    assert t.get("narrative") in (None, "", ) or isinstance(t.get("narrative"), str)


# --- growth card PNG -------------------------------------------------------


def test_growth_card_png(premium_headers, lukas_profile_id):
    r = requests.get(
        f"{BASE_URL}/api/progress/players/{lukas_profile_id}/growth-card.png",
        headers=premium_headers,
        timeout=60,
    )
    assert r.status_code == 200, r.text[:200]
    assert r.headers.get("content-type", "").startswith("image/png")
    # PNG signature
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    # Parse IHDR for width/height (bytes 16..24)
    width = struct.unpack(">I", r.content[16:20])[0]
    height = struct.unpack(">I", r.content[20:24])[0]
    assert (width, height) == (1080, 1350), f"got {width}x{height}"


# --- progress pass status & eligibility -----------------------------------


def test_pass_status_inactive(premium_headers):
    r = requests.get(f"{BASE_URL}/api/progress/pass/status", headers=premium_headers, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("active") is False
    assert data.get("credits_remaining") == 0


def test_upload_eligibility_has_progress_pass(premium_headers):
    r = requests.get(f"{BASE_URL}/api/me/upload-eligibility", headers=premium_headers, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "progress_pass" in data, data


# --- Stripe checkout (no real charge) -------------------------------------


def test_progress_pass_checkout_session_create(premium_headers, mongo):
    r = requests.post(
        f"{BASE_URL}/api/progress/pass/checkout",
        headers=premium_headers,
        json={"origin_url": "https://scout-ai-pro-1.preview.emergentagent.com"},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("client_secret")
    sid = data.get("session_id")
    assert sid
    # check payment_transactions row was inserted
    tx = mongo.payment_transactions.find_one({"session_id": sid})
    assert tx is not None, "payment_transactions row missing"
    assert tx.get("kind") == "progress_pass"
    assert tx.get("amount") in (599, 599.0, 59900) or float(tx.get("amount")) == 599.0
    assert tx.get("credits") == 3
    assert tx.get("payment_status") == "initiated"
    assert tx.get("status") == "open"


def test_progress_pass_activate_unpaid_rejects(premium_headers, mongo):
    # find an open progress_pass session for the premium user (created above)
    tx = mongo.payment_transactions.find_one(
        {"kind": "progress_pass", "payment_status": "initiated"}, sort=[("created_at", -1)]
    )
    if not tx:
        pytest.skip("no open progress_pass session to activate")
    sid = tx["session_id"]
    r = requests.post(
        f"{BASE_URL}/api/progress/pass/activate/{sid}",
        headers=premium_headers,
        timeout=30,
    )
    # spec: 402 Payment not completed
    assert r.status_code == 402, f"expected 402, got {r.status_code} {r.text[:200]}"


# --- Stripe webhook safety ------------------------------------------------


def test_webhook_invalid_signature_rejected():
    r = requests.post(
        f"{BASE_URL}/api/webhook/stripe-embedded",
        data=b'{"type":"checkout.session.completed","data":{}}',
        headers={"Stripe-Signature": "t=0,v1=invalid", "Content-Type": "application/json"},
        timeout=15,
    )
    # invalid signature -> 400 (route is reachable, rejects safely)
    assert r.status_code in (400, 401), f"expected 400/401, got {r.status_code}"
