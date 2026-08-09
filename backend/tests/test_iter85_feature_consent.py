"""Iter85: feature-consent + admin featured-clips backend tests."""
import os, requests, pytest
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PW = "Admin@2026!Elite"
TEMP_EMAIL = "smtest.iter85@example.com"
TEMP_PW = "TestIter85!"


def _login(email, pw):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def temp_token():
    return _login(TEMP_EMAIL, TEMP_PW)


# --- account consent endpoints ---

def test_consent_unauth_401():
    r = requests.get(f"{BASE}/api/account/feature-consent")
    assert r.status_code in (401, 403)


def test_consent_put_grant_then_withdraw(admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = requests.put(f"{BASE}/api/account/feature-consent", json={"granted": True}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "granted"
    r = requests.get(f"{BASE}/api/account/feature-consent", headers=h)
    assert r.json()["status"] == "granted"
    r = requests.put(f"{BASE}/api/account/feature-consent", json={"granted": False}, headers=h)
    assert r.json()["status"] == "withdrawn"
    r = requests.get(f"{BASE}/api/account/feature-consent", headers=h)
    assert r.json()["status"] == "withdrawn"


# --- admin featured-clips endpoint ---

def test_featured_clips_unauth_401():
    r = requests.get(f"{BASE}/api/admin/featured-clips")
    assert r.status_code in (401, 403)


def test_featured_clips_non_admin_403(temp_token):
    r = requests.get(f"{BASE}/api/admin/featured-clips", headers={"Authorization": f"Bearer {temp_token}"})
    assert r.status_code == 403


def test_featured_clips_admin_lists_seeded(admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = requests.get(f"{BASE}/api/admin/featured-clips", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert "clips" in data and isinstance(data["clips"], list)
    ids = {c["report_id"]: c for c in data["clips"]}
    assert "iter85-fc-full-report" in ids, f"seeded full report not listed. clips={ids.keys()}"
    assert "iter85-fc-preview-report" in ids
    assert ids["iter85-fc-full-report"]["full_report_ready"] is True
    assert ids["iter85-fc-preview-report"]["full_report_ready"] is False
    assert ids["iter85-fc-full-report"]["user_email"] == TEMP_EMAIL


def test_withdrawal_hides_clips(admin_token):
    import subprocess
    h = {"Authorization": f"Bearer {admin_token}"}
    subprocess.check_call(["python", "/app/backend/tests/seed_iter85.py", "withdraw"])
    r = requests.get(f"{BASE}/api/admin/featured-clips", headers=h)
    ids = {c["report_id"] for c in r.json()["clips"]}
    assert "iter85-fc-full-report" not in ids
    assert "iter85-fc-preview-report" not in ids
    # restore for later UI tests
    subprocess.check_call(["python", "/app/backend/tests/seed_iter85.py", "grant"])
    r = requests.get(f"{BASE}/api/admin/featured-clips", headers=h)
    ids = {c["report_id"] for c in r.json()["clips"]}
    assert "iter85-fc-full-report" in ids
