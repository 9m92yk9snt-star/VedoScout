"""iter88 — Dashboard Hub new features:
- Trial opportunity interest apply/idempotent/withdraw/free-403/unknown-404
- Admin: interest_count, applicants list, cascade delete
- Live library counts + use_live_players toggle
- Scout message email alarm (kind=message + sender_type scout/agent/club)
- Cleanup all disposable data, preserve seed opportunity zero interest
"""
import os
import sys
import time
import uuid
import asyncio
import pytest
import requests

sys.path.insert(0, "/app/backend")


def _read_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.strip().split("=", 1)[1].rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _read_backend_url()
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASS = "Admin@2026!Elite"

FREE_EMAIL = f"iter88.free.{uuid.uuid4().hex[:8]}@example.com"
PREM_EMAIL = f"iter88.prem.{uuid.uuid4().hex[:8]}@example.com"
PASS = "TestPass!2026"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


def _get_db():
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        with open("/app/backend/.env") as f:
            for line in f:
                line = line.strip()
                if line.startswith("MONGO_URL=") and not mongo_url:
                    mongo_url = line.split("=", 1)[1]
                elif line.startswith("DB_NAME=") and not db_name:
                    db_name = line.split("=", 1)[1]
    client = AsyncIOMotorClient(mongo_url)
    return client, client[db_name]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _signup(email, password, full_name="Test"):
    from server import hash_password, now_iso  # noqa
    pw_hash = hash_password(password)
    ts = now_iso()

    async def _do():
        client, db = _get_db()
        try:
            uid = str(uuid.uuid4())
            await db.users.delete_many({"email": email.lower()})
            await db.users.insert_one({
                "id": uid, "email": email.lower(),
                "password_hash": pw_hash, "full_name": full_name,
                "role": "user", "created_at": ts,
            })
            return uid
        finally:
            client.close()
    return _run(_do())


STATE = {
    "admin_token": None,
    "free_token": None,
    "prem_token": None,
    "free_uid": None,
    "prem_uid": None,
    "seed_opp_id": None,
    "temp_opp_id": None,
    "prem_report_id": None,
    "test_msg_ids": [],
    "prev_community": None,
}


@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown():
    STATE["admin_token"] = _login(ADMIN_EMAIL, ADMIN_PASS)

    _signup(FREE_EMAIL, PASS, "Iter88 Free")
    STATE["free_token"] = _login(FREE_EMAIL, PASS)
    STATE["free_uid"] = requests.get(f"{API}/auth/me", headers=_hdr(STATE["free_token"])).json()["id"]

    _signup(PREM_EMAIL, PASS, "Iter88 Premium")
    STATE["prem_token"] = _login(PREM_EMAIL, PASS)
    STATE["prem_uid"] = requests.get(f"{API}/auth/me", headers=_hdr(STATE["prem_token"])).json()["id"]

    # inject paid report for premium user
    async def _seed():
        client, db = _get_db()
        try:
            rid = str(uuid.uuid4())
            await db.reports.insert_one({
                "id": rid, "user_id": STATE["prem_uid"], "is_paid": True,
                "player_details": {"player_name": "Iter88 Prem"},
                "created_at": "2026-01-01T00:00:00+00:00",
            })
            STATE["prem_report_id"] = rid
            # snapshot community settings
            doc = await db.settings.find_one({"key": "dashboard_community"}, {"_id": 0}) or {}
            STATE["prev_community"] = doc.get("value") or {}
        finally:
            client.close()
    _run(_seed())

    # find seed opportunity 'Elite Football Academy Trials'
    r = requests.get(f"{API}/admin/dashboard/opportunities", headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r.status_code == 200
    items = r.json()["items"]
    seed = next((o for o in items if "Elite Football Academy" in o.get("title", "")), None)
    assert seed is not None, "seed opportunity not found — required for tests"
    STATE["seed_opp_id"] = seed["id"]

    yield

    # ── cleanup ────────────────────────────────────────────────────────
    async def _clean():
        client, db = _get_db()
        try:
            # remove interest docs from disposable users + admin on seed opp
            await db.dashboard_opportunity_interest.delete_many(
                {"user_id": {"$in": [STATE["free_uid"], STATE["prem_uid"]]}}
            )
            # also clear admin's leftover interest on seed opp if any
            admin_u = await db.users.find_one({"email": ADMIN_EMAIL.lower()}, {"_id": 0, "id": 1})
            if admin_u:
                await db.dashboard_opportunity_interest.delete_many({"user_id": admin_u["id"]})
            # delete disposable messages
            if STATE["test_msg_ids"]:
                await db.dashboard_messages.delete_many({"id": {"$in": STATE["test_msg_ids"]}})
            # delete temp opp
            if STATE["temp_opp_id"]:
                await db.dashboard_opportunities.delete_many({"id": STATE["temp_opp_id"]})
                await db.dashboard_opportunity_interest.delete_many({"opportunity_id": STATE["temp_opp_id"]})
            # delete disposable users + their reports
            if STATE["prem_report_id"]:
                await db.reports.delete_many({"id": STATE["prem_report_id"]})
            await db.users.delete_many({"id": {"$in": [STATE["free_uid"], STATE["prem_uid"]]}})
            # reset community to prior known state (manual 2847, use_live=false)
            reset_val = {**(STATE["prev_community"] or {}),
                         "use_live_players": False,
                         "players_in_library": 2847}
            await db.settings.update_one(
                {"key": "dashboard_community"},
                {"$set": {"value": reset_val}},
                upsert=True,
            )
        finally:
            client.close()
    _run(_clean())


# ── Interest endpoints ─────────────────────────────────────────────────

def test_interest_free_user_forbidden():
    r = requests.post(f"{API}/dashboard/opportunities/{STATE['seed_opp_id']}/interest",
                      headers=_hdr(STATE["free_token"]), timeout=30)
    assert r.status_code == 403


def test_interest_unknown_opp_404():
    r = requests.post(f"{API}/dashboard/opportunities/{uuid.uuid4()}/interest",
                      headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r.status_code == 404


def test_interest_admin_apply_ok():
    r = requests.post(f"{API}/dashboard/opportunities/{STATE['seed_opp_id']}/interest",
                      headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True and d.get("interested") is True


def test_interest_idempotent_reapply():
    # Re-apply → still exactly 1 applicant on this opp
    r = requests.post(f"{API}/dashboard/opportunities/{STATE['seed_opp_id']}/interest",
                      headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r.status_code == 200
    r2 = requests.get(f"{API}/admin/dashboard/opportunities/{STATE['seed_opp_id']}/interest",
                      headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r2.status_code == 200
    apps = r2.json()["applicants"]
    admin_apps = [a for a in apps if a.get("user_email") == ADMIN_EMAIL.lower()]
    assert len(admin_apps) == 1, f"expected exactly 1 admin applicant, got {len(admin_apps)}: {apps}"
    a = admin_apps[0]
    assert "user_name" in a and "user_email" in a and "created_at" in a


def test_dashboard_opportunities_includes_interested_true():
    r = requests.get(f"{API}/dashboard/opportunities", headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d.get("locked") is False
    item = next((o for o in d["items"] if o["id"] == STATE["seed_opp_id"]), None)
    assert item is not None
    assert item.get("interested") is True


def test_admin_opportunities_list_has_interest_count():
    r = requests.get(f"{API}/admin/dashboard/opportunities", headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r.status_code == 200
    items = r.json()["items"]
    seed = next((o for o in items if o["id"] == STATE["seed_opp_id"]), None)
    assert seed is not None
    assert seed.get("interest_count", 0) >= 1


def test_admin_applicants_no_auth_401_403():
    r = requests.get(f"{API}/admin/dashboard/opportunities/{STATE['seed_opp_id']}/interest", timeout=30)
    assert r.status_code in (401, 403)


def test_admin_applicants_free_token_403():
    r = requests.get(f"{API}/admin/dashboard/opportunities/{STATE['seed_opp_id']}/interest",
                     headers=_hdr(STATE["free_token"]), timeout=30)
    assert r.status_code == 403


def test_interest_withdraw():
    r = requests.delete(f"{API}/dashboard/opportunities/{STATE['seed_opp_id']}/interest",
                        headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d.get("interested") is False
    # verify count decreased
    r2 = requests.get(f"{API}/admin/dashboard/opportunities/{STATE['seed_opp_id']}/interest",
                      headers=_hdr(STATE["admin_token"]), timeout=30)
    apps = r2.json()["applicants"]
    admin_apps = [a for a in apps if a.get("user_email") == ADMIN_EMAIL.lower()]
    assert len(admin_apps) == 0


def test_delete_opportunity_cascades_interest():
    # create temp opp, apply, delete → verify interest gone
    payload = {"title": "ITER88 Temp Opp", "club_name": "Test", "age_band": "U18",
               "location": "Test", "active": True}
    r = requests.post(f"{API}/admin/dashboard/opportunities",
                      headers=_hdr(STATE["admin_token"]), json=payload, timeout=30)
    assert r.status_code == 200, r.text
    opp = r.json()
    STATE["temp_opp_id"] = opp["id"]
    # apply
    r2 = requests.post(f"{API}/dashboard/opportunities/{opp['id']}/interest",
                       headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r2.status_code == 200
    # verify exists in mongo
    async def _check_before():
        client, db = _get_db()
        try:
            n = await db.dashboard_opportunity_interest.count_documents({"opportunity_id": opp["id"]})
            return n
        finally:
            client.close()
    assert _run(_check_before()) == 1
    # delete opp
    r3 = requests.delete(f"{API}/admin/dashboard/opportunities/{opp['id']}",
                         headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r3.status_code == 200

    async def _check_after():
        client, db = _get_db()
        try:
            return await db.dashboard_opportunity_interest.count_documents({"opportunity_id": opp["id"]})
        finally:
            client.close()
    assert _run(_check_after()) == 0
    STATE["temp_opp_id"] = None  # cleanup done


# ── Community live counts ──────────────────────────────────────────────

def test_admin_community_has_live_fields():
    r = requests.get(f"{API}/admin/dashboard/community", headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert "live_players_in_library" in d
    assert "live_players_wk" in d
    assert isinstance(d["live_players_in_library"], int)


def test_toggle_use_live_players_reflected_in_user_endpoint():
    # Get baseline
    r0 = requests.get(f"{API}/dashboard/community", headers=_hdr(STATE["admin_token"]), timeout=30)
    baseline = r0.json().get("players_in_library")

    # PUT use_live_players=true
    r1 = requests.put(f"{API}/admin/dashboard/community",
                      headers=_hdr(STATE["admin_token"]),
                      json={"use_live_players": True}, timeout=30)
    assert r1.status_code == 200, r1.text
    live_count = r1.json()["live_players_in_library"]

    # GET as any user
    r2 = requests.get(f"{API}/dashboard/community", headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r2.status_code == 200
    assert r2.json()["players_in_library"] == live_count

    # Toggle off and set manual back
    r3 = requests.put(f"{API}/admin/dashboard/community",
                      headers=_hdr(STATE["admin_token"]),
                      json={"use_live_players": False, "players_in_library": 2847}, timeout=30)
    assert r3.status_code == 200

    r4 = requests.get(f"{API}/dashboard/community", headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r4.json()["players_in_library"] == 2847


# ── Email alarm ────────────────────────────────────────────────────────

def _tail_log(path="/var/log/supervisor/backend.err.log", n=400):
    try:
        with open(path, "r") as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except Exception:
        return ""


def test_email_alarm_scout_message_triggers():
    # premium target user's email
    payload = {
        "kind": "message", "sender_type": "scout", "sender_name": "ITER88 Test Scout",
        "subject": "ITER88 email alarm scout", "body": "hi",
        "target": "all", "target_email": PREM_EMAIL,
    }
    r = requests.post(f"{API}/admin/dashboard/messages",
                      headers=_hdr(STATE["admin_token"]), json=payload, timeout=30)
    assert r.status_code == 200, r.text
    STATE["test_msg_ids"].append(r.json()["id"])
    # async task; wait
    time.sleep(4)
    log = _tail_log()
    assert "message alert emails sent" in log, "expected 'message alert emails sent' log line"


def test_email_alarm_notification_kind_does_not_trigger():
    payload = {
        "kind": "notification", "sender_type": "scout", "sender_name": "ITER88 Test",
        "subject": "ITER88 no alarm notification", "body": "hi",
        "target": "all", "target_email": PREM_EMAIL,
    }
    r = requests.post(f"{API}/admin/dashboard/messages",
                      headers=_hdr(STATE["admin_token"]), json=payload, timeout=30)
    assert r.status_code == 200
    STATE["test_msg_ids"].append(r.json()["id"])
    # snapshot log lines count for "message alert emails sent"
    before = _tail_log().count("message alert emails sent")
    time.sleep(3)
    after = _tail_log().count("message alert emails sent")
    assert after == before, "notification kind must NOT trigger email alarm"


def test_email_alarm_admin_sender_does_not_trigger():
    before = _tail_log().count("message alert emails sent")
    payload = {
        "kind": "message", "sender_type": "admin", "sender_name": "ScoutMePlay",
        "subject": "ITER88 admin sender no alarm", "body": "hi",
        "target": "all", "target_email": PREM_EMAIL,
    }
    r = requests.post(f"{API}/admin/dashboard/messages",
                      headers=_hdr(STATE["admin_token"]), json=payload, timeout=30)
    assert r.status_code == 200
    STATE["test_msg_ids"].append(r.json()["id"])
    time.sleep(3)
    after = _tail_log().count("message alert emails sent")
    assert after == before, "sender_type=admin must NOT trigger email alarm"


def test_email_alarm_target_free_no_recipients():
    # target=free returns 0 recipients per _alert_recipient_emails
    before = _tail_log().count("message alert emails sent")
    payload = {
        "kind": "message", "sender_type": "scout", "sender_name": "ITER88 Test Scout",
        "subject": "ITER88 target free zero", "body": "hi",
        "target": "free",
    }
    r = requests.post(f"{API}/admin/dashboard/messages",
                      headers=_hdr(STATE["admin_token"]), json=payload, timeout=30)
    assert r.status_code == 200
    STATE["test_msg_ids"].append(r.json()["id"])
    time.sleep(3)
    log = _tail_log()
    # either no new "sent" line, or a "sent: 0/0" would be acceptable
    # implementation returns early if no recipients, so no new line
    after = log.count("message alert emails sent")
    assert after == before, "target=free must not email anyone"
