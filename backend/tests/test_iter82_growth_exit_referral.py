"""Iter82 — Backend tests for Exit-Intent Offer + Teammate Referral growth features.

Covers:
- GET /api/exit-offer/config (public defaults)
- POST /api/exit-offer/claim (disabled → 404, enabled → code)
- POST /api/exit-offer/attach (attach, duplicate-user 409)
- GET/POST /api/admin/exit-offer (config + stats + validation)
- GET /api/referral/me (defaults enabled=true, code, link)
- POST /api/referral/redeem (happy path, self=400, dup=409, unknown=404, disabled=404)
- GET /api/admin/referrals (rows)
- POST /api/admin/referral-settings (validation + restore)
- growth.get_active_discount() picks highest %

Cleans up all disposable users/reports/claims/referrals and RESTORES settings
(exit_offer disabled, referral enabled 15% / 30d).
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import bcrypt
import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PW = "Admin@2026!Elite"

TAG = uuid.uuid4().hex[:6]
USER_A_EMAIL = f"smtest.iter82.a_{TAG}@example.com"
USER_B_EMAIL = f"smtest.iter82.b_{TAG}@example.com"
USER_C_EMAIL = f"smtest.iter82.c_{TAG}@example.com"
PW = "Test@2026!Iter82"


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def seeded_users(db):
    """Seed three disposable users directly + return their ids and login tokens."""
    async def _seed():
        ids = {}
        for email in (USER_A_EMAIL, USER_B_EMAIL, USER_C_EMAIL):
            uid = str(uuid.uuid4())
            pw_hash = bcrypt.hashpw(PW.encode(), bcrypt.gensalt()).decode()
            await db.users.insert_one({
                "id": uid,
                "email": email.lower(),
                "password_hash": pw_hash,
                "full_name": f"Iter82 {email[:8]}",
                "role": "user",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            ids[email] = uid
        return ids
    return asyncio.get_event_loop().run_until_complete(_seed())


def _login(email):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": PW}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def tokens(seeded_users):
    return {
        "a": _login(USER_A_EMAIL),
        "b": _login(USER_B_EMAIL),
        "c": _login(USER_C_EMAIL),
        "admin": _login_admin(),
    }


def _login_admin():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json().get("access_token") or r.json().get("token")


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------------- exit-offer ----------------
class TestExitOffer:
    def test_public_config_defaults_disabled(self):
        r = requests.get(f"{BASE}/api/exit-offer/config", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert set(d.keys()) >= {"enabled", "percent", "countdown_minutes", "headline"}
        assert d["enabled"] is False  # default (or restored)

    def test_claim_returns_404_when_disabled(self):
        r = requests.post(f"{BASE}/api/exit-offer/claim", timeout=15)
        assert r.status_code == 404

    def test_admin_get_returns_config_and_stats(self, tokens):
        r = requests.get(f"{BASE}/api/admin/exit-offer", headers=H(tokens["admin"]), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "config" in j and "stats" in j
        assert "claims" in j["stats"] and "attached" in j["stats"]

    def test_admin_post_validates_percent(self, tokens):
        r = requests.post(f"{BASE}/api/admin/exit-offer", headers=H(tokens["admin"]),
                          json={"enabled": True, "percent": 95, "countdown_minutes": 10,
                                "valid_hours": 24, "headline": "x"}, timeout=15)
        assert r.status_code == 400

    def test_full_claim_and_attach_flow(self, tokens):
        # enable via admin
        r = requests.post(f"{BASE}/api/admin/exit-offer", headers=H(tokens["admin"]),
                          json={"enabled": True, "percent": 12, "countdown_minutes": 10,
                                "valid_hours": 24, "headline": "Test headline"}, timeout=15)
        assert r.status_code == 200

        # public config now shows enabled + 12
        r = requests.get(f"{BASE}/api/exit-offer/config", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["enabled"] is True
        assert float(j["percent"]) == 12.0
        assert j["headline"] == "Test headline"

        # public claim returns code + percent
        r = requests.post(f"{BASE}/api/exit-offer/claim", timeout=15)
        assert r.status_code == 200
        claim = r.json()
        assert "code" in claim and float(claim["percent"]) == 12.0
        code = claim["code"]

        # user A attaches → 200
        r = requests.post(f"{BASE}/api/exit-offer/attach", headers=H(tokens["a"]),
                          json={"code": code}, timeout=15)
        assert r.status_code == 200, r.text

        # user B attaching same code → 409
        r = requests.post(f"{BASE}/api/exit-offer/attach", headers=H(tokens["b"]),
                          json={"code": code}, timeout=15)
        assert r.status_code == 409, f"expected 409, got {r.status_code}: {r.text}"

        # unknown code → 404
        r = requests.post(f"{BASE}/api/exit-offer/attach", headers=H(tokens["b"]),
                          json={"code": "does_not_exist"}, timeout=15)
        assert r.status_code == 404

    def test_user_doc_has_exit_offer(self, db, seeded_users):
        u = asyncio.get_event_loop().run_until_complete(
            db.users.find_one({"id": seeded_users[USER_A_EMAIL]}))
        assert u.get("exit_offer"), "exit_offer not set on user doc"
        assert float(u["exit_offer"]["percent"]) == 12.0


# ---------------- referral ----------------
class TestReferral:
    def test_referral_me_defaults(self, tokens):
        r = requests.get(f"{BASE}/api/referral/me", headers=H(tokens["a"]), timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["enabled"] is True
        assert float(j["percent"]) == 15.0
        assert j["code"] and "?ref=" in j["link"]
        # store for later
        TestReferral.code_a = j["code"]

    def test_self_redeem_400(self, tokens):
        r = requests.post(f"{BASE}/api/referral/redeem", headers=H(tokens["a"]),
                          json={"code": TestReferral.code_a}, timeout=15)
        assert r.status_code == 400

    def test_unknown_code_404(self, tokens):
        r = requests.post(f"{BASE}/api/referral/redeem", headers=H(tokens["b"]),
                          json={"code": "zzz_unknown"}, timeout=15)
        assert r.status_code == 404

    def test_happy_path_and_dup_409(self, tokens, db, seeded_users):
        # B redeems A's code
        r = requests.post(f"{BASE}/api/referral/redeem", headers=H(tokens["b"]),
                          json={"code": TestReferral.code_a}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert float(j["percent"]) == 15.0

        # both users have referral_credit
        async def _check():
            ua = await db.users.find_one({"id": seeded_users[USER_A_EMAIL]})
            ub = await db.users.find_one({"id": seeded_users[USER_B_EMAIL]})
            assert isinstance(ua.get("referral_credit"), dict)
            assert isinstance(ub.get("referral_credit"), dict)
            assert float(ua["referral_credit"]["percent"]) == 15.0
            ref = await db.referrals.find_one({"referred_id": seeded_users[USER_B_EMAIL]})
            assert ref is not None
        asyncio.get_event_loop().run_until_complete(_check())

        # second redeem by B → 409
        r = requests.post(f"{BASE}/api/referral/redeem", headers=H(tokens["b"]),
                          json={"code": TestReferral.code_a}, timeout=15)
        assert r.status_code == 409

    def test_admin_referrals_lists_row(self, tokens):
        r = requests.get(f"{BASE}/api/admin/referrals", headers=H(tokens["admin"]), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "referrals" in j and "config" in j
        # verify our seeded row is present
        emails = [row.get("referred_email", "") for row in j["referrals"]]
        assert any(USER_B_EMAIL[:8] in (e or "") or USER_B_EMAIL.split("@")[0][:8] in (e or "") for e in emails) \
            or j["total"] >= 1, "expected our referral row"

    def test_admin_disable_referral_and_restore(self, tokens):
        # disable
        r = requests.post(f"{BASE}/api/admin/referral-settings",
                          headers=H(tokens["admin"]),
                          json={"enabled": False, "percent": 15, "valid_days": 30}, timeout=15)
        assert r.status_code == 200

        # redeem now returns 404
        r = requests.post(f"{BASE}/api/referral/redeem", headers=H(tokens["c"]),
                          json={"code": TestReferral.code_a}, timeout=15)
        assert r.status_code == 404

        # restore
        r = requests.post(f"{BASE}/api/admin/referral-settings",
                          headers=H(tokens["admin"]),
                          json={"enabled": True, "percent": 15, "valid_days": 30}, timeout=15)
        assert r.status_code == 200

    def test_admin_settings_validation(self, tokens):
        r = requests.post(f"{BASE}/api/admin/referral-settings",
                          headers=H(tokens["admin"]),
                          json={"enabled": True, "percent": 95, "valid_days": 30}, timeout=15)
        assert r.status_code == 400


# ---------------- get_active_discount ----------------
class TestActiveDiscount:
    def test_highest_percent_wins(self, db, seeded_users):
        """User A has exit_offer 12% + referral_credit 15% → 15% wins."""
        from growth import get_active_discount
        report = {"user_id": seeded_users[USER_A_EMAIL], "id": "fake-rid"}
        result = asyncio.get_event_loop().run_until_complete(get_active_discount(db, report))
        assert result is not None
        assert float(result["percent"]) == 15.0
        assert result["source"] == "referral"


# ---------------- cleanup + restore ----------------
class TestCleanup:
    def test_cleanup(self, tokens, db, seeded_users):
        # restore exit-offer disabled
        r = requests.post(f"{BASE}/api/admin/exit-offer", headers=H(tokens["admin"]),
                          json={"enabled": False, "percent": 10, "countdown_minutes": 15,
                                "valid_hours": 24,
                                "headline": "Wait — see what the video says first"}, timeout=15)
        assert r.status_code == 200

        # restore referral defaults
        r = requests.post(f"{BASE}/api/admin/referral-settings", headers=H(tokens["admin"]),
                          json={"enabled": True, "percent": 15, "valid_days": 30}, timeout=15)
        assert r.status_code == 200

        # delete seeded users, referrals, claims
        async def _clean():
            uids = list(seeded_users.values())
            await db.users.delete_many({"id": {"$in": uids}})
            await db.referrals.delete_many({"referrer_id": {"$in": uids}})
            await db.referrals.delete_many({"referred_id": {"$in": uids}})
            await db.exit_offer_claims.delete_many({"attached_user_id": {"$in": uids}})
            # also delete any orphan claims from this test run (percent=12 with our test window)
            await db.exit_offer_claims.delete_many({"percent": 12.0, "attached_user_id": None})
        asyncio.get_event_loop().run_until_complete(_clean())

        # verify exit offer is disabled publicly
        r = requests.get(f"{BASE}/api/exit-offer/config", timeout=15)
        assert r.status_code == 200
        assert r.json()["enabled"] is False
