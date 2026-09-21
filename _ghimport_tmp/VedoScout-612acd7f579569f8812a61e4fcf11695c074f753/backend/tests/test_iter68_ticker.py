"""Backend tests for iter68: stats ticker feature."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback: read from frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"

TICKER_KEYS = ["players_analyzed", "pro_reports", "scout_reviews",
               "players_available", "trial_invites", "club_opportunities"]


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module", autouse=True)
def _cleanup_after(admin_session):
    yield
    # reset to enabled=true, boosts all 0
    admin_session.put(f"{BASE_URL}/api/admin/ticker",
                      json={"enabled": True, "boosts": {k: 0 for k in TICKER_KEYS}})


def test_public_ticker_shape():
    r = requests.get(f"{BASE_URL}/api/stats/ticker")
    assert r.status_code == 200
    body = r.json()
    assert "enabled" in body
    if body["enabled"]:
        assert set(body["stats"].keys()) == set(TICKER_KEYS)
        for k, v in body["stats"].items():
            assert isinstance(v, int), f"{k} not int: {v}"


def test_admin_ticker_get(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/ticker")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "real" in body and "boosts" in body and "totals" in body
    for k in TICKER_KEYS:
        assert k in body["real"]
        assert k in body["boosts"]
        assert body["totals"][k] == body["real"][k] + body["boosts"][k]


def test_admin_ticker_put_persists(admin_session):
    payload = {"enabled": True,
               "boosts": {"trial_invites": 12, "club_opportunities": 3}}
    r = admin_session.put(f"{BASE_URL}/api/admin/ticker", json=payload)
    assert r.status_code == 200, r.text
    # verify via public endpoint
    pub = requests.get(f"{BASE_URL}/api/stats/ticker").json()
    assert pub["enabled"] is True
    real = admin_session.get(f"{BASE_URL}/api/admin/ticker").json()["real"]
    assert pub["stats"]["trial_invites"] == real["trial_invites"] + 12
    assert pub["stats"]["club_opportunities"] == real["club_opportunities"] + 3


def test_disable_ticker_returns_null(admin_session):
    r = admin_session.put(f"{BASE_URL}/api/admin/ticker",
                          json={"enabled": False, "boosts": {}})
    assert r.status_code == 200
    pub = requests.get(f"{BASE_URL}/api/stats/ticker").json()
    assert pub["enabled"] is False
    assert pub["stats"] is None
    # re-enable
    r = admin_session.put(f"{BASE_URL}/api/admin/ticker",
                          json={"enabled": True, "boosts": {}})
    assert r.status_code == 200
    pub = requests.get(f"{BASE_URL}/api/stats/ticker").json()
    assert pub["enabled"] is True
    assert pub["stats"] is not None


def test_negative_boosts_clamped(admin_session):
    r = admin_session.put(f"{BASE_URL}/api/admin/ticker",
                          json={"enabled": True,
                                "boosts": {"trial_invites": -5, "pro_reports": -100}})
    assert r.status_code == 200
    body = r.json()
    assert body["boosts"]["trial_invites"] == 0
    assert body["boosts"]["pro_reports"] == 0


def test_public_no_auth_required():
    # No auth header at all
    r = requests.get(f"{BASE_URL}/api/stats/ticker")
    assert r.status_code == 200
