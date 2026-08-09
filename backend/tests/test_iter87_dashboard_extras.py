"""iter87 — Dashboard Hub extras: badges, replies, profile-views,
discoverable premium gate, report-ready notification idempotency.
Cleans up all disposable data; preserves seed scout message and seed opportunity."""
import os
import time
import uuid
import asyncio
import pytest
import requests

def _read_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.strip().split("=", 1)[1].rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

BASE_URL = _read_backend_url()
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASS = "Admin@2026!Elite"
SEED_MSG_ID = "78a7dbfb-611d-40a7-b668-0d592c48f094"  # 'Impressive footage' - MUST NOT DELETE

FREE_EMAIL = f"iter87.free.{uuid.uuid4().hex[:8]}@example.com"
FREE_PASS = "TestPass!2026"
PREM_EMAIL = f"iter87.prem.{uuid.uuid4().hex[:8]}@example.com"
PREM_PASS = "TestPass!2026"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


def _get_db():
    """Create a dedicated motor client per event loop to avoid loop binding issues."""
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        # read backend .env
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


def _signup(email, password, full_name="Test User"):
    """Direct DB insertion to bypass signup rate limits (test env)."""
    import sys
    sys.path.insert(0, "/app/backend")
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
                "password_hash": pw_hash,
                "full_name": full_name, "role": "user",
                "created_at": ts,
            })
            return uid
        finally:
            client.close()
    return _run(_do())


# ── shared state ─────────────────────────────────────────────────────────
STATE = {
    "admin_token": None,
    "free_token": None,
    "prem_token": None,
    "free_user_id": None,
    "prem_user_id": None,
    "disposable_msg_id": None,
    "created_report_ids": [],
    "created_fake_report_id": None,
    "cleanup_reply_ids": [],
}


@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown():
    # Setup: login admin
    STATE["admin_token"] = _login(ADMIN_EMAIL, ADMIN_PASS)

    # Create free user
    _signup(FREE_EMAIL, FREE_PASS, "Iter87 Free")
    STATE["free_token"] = _login(FREE_EMAIL, FREE_PASS)
    me = requests.get(f"{API}/auth/me", headers=_hdr(STATE["free_token"]), timeout=30).json()
    STATE["free_user_id"] = me["id"]

    # Create premium-simulated user (via db insert of paid report)
    _signup(PREM_EMAIL, PREM_PASS, "Iter87 Premium")
    STATE["prem_token"] = _login(PREM_EMAIL, PREM_PASS)
    me2 = requests.get(f"{API}/auth/me", headers=_hdr(STATE["prem_token"]), timeout=30).json()
    STATE["prem_user_id"] = me2["id"]

    # Inject a paid report for prem user so they have premium access
    async def _seed_prem():
        client, db = _get_db()
        try:
            rid = str(uuid.uuid4())
            await db.reports.insert_one({
                "id": rid, "user_id": STATE["prem_user_id"], "is_paid": True,
                "player_details": {"player_name": "Iter87 Prem Player"},
                "created_at": "2026-01-01T00:00:00+00:00",
            })
            STATE["created_report_ids"].append(rid)
        finally:
            client.close()
    _run(_seed_prem())

    yield

    # Teardown: cleanup all disposable users, messages, replies, reports, profile_view_events
    async def _clean():
        client, db = _get_db()
        try:
            if STATE["disposable_msg_id"]:
                await db.dashboard_messages.delete_many({"id": STATE["disposable_msg_id"]})
                await db.dashboard_message_replies.delete_many({"message_id": STATE["disposable_msg_id"]})
                await db.dashboard_message_reads.delete_many({"message_id": STATE["disposable_msg_id"]})
            if STATE.get("created_fake_report_id"):
                await db.dashboard_messages.delete_many({"link": f"/report/{STATE['created_fake_report_id']}"})
                await db.reports.delete_many({"id": STATE["created_fake_report_id"]})
            for rid in STATE["created_report_ids"]:
                await db.reports.delete_many({"id": rid})
            await db.profile_view_events.delete_many({"player_user_id": STATE["prem_user_id"]})
            await db.profile_view_events.delete_many({"player_user_id": STATE["free_user_id"]})
            await db.dashboard_message_replies.delete_many({"user_id": STATE["free_user_id"]})
            await db.dashboard_message_replies.delete_many({"user_id": STATE["prem_user_id"]})
            await db.users.delete_many({"id": STATE["free_user_id"]})
            await db.users.delete_many({"id": STATE["prem_user_id"]})
            await db.dashboard_messages.delete_many({"target_email": FREE_EMAIL.lower()})
            await db.dashboard_messages.delete_many({"target_email": PREM_EMAIL.lower()})
        finally:
            client.close()
    _run(_clean())


# ── Tests ────────────────────────────────────────────────────────────────

# Badges endpoint
def test_badges_free_user_locked_scout_message():
    r = requests.get(f"{API}/dashboard/inbox/badges", headers=_hdr(STATE["free_token"]), timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["premium_access"] is False
    assert d["locked_messages"] >= 1, f"expected locked>=1 (seed scout msg), got {d}"
    assert d["unread_messages"] == 0
    assert d["total"] == d["unread_notifications"] + d["unread_messages"] + d["locked_messages"]


def test_badges_admin_premium_access():
    r = requests.get(f"{API}/dashboard/inbox/badges", headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r.status_code == 200
    assert r.json()["premium_access"] is True


# Reply endpoint - create disposable admin message for reply tests
def test_create_disposable_admin_message():
    payload = {
        "kind": "message", "sender_type": "scout", "sender_name": "ITER87 Test Scout",
        "subject": "ITER87 disposable", "body": "reply test target", "target": "all",
    }
    r = requests.post(f"{API}/admin/dashboard/messages", headers=_hdr(STATE["admin_token"]),
                      json=payload, timeout=30)
    assert r.status_code == 200, r.text
    STATE["disposable_msg_id"] = r.json()["id"]


def test_reply_admin_success():
    mid = STATE["disposable_msg_id"]
    assert mid
    r = requests.post(f"{API}/dashboard/inbox/{mid}/reply", headers=_hdr(STATE["admin_token"]),
                      json={"body": "ITER87 admin reply body"}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "id" in d and d["body"] == "ITER87 admin reply body"


def test_reply_empty_body_400():
    mid = STATE["disposable_msg_id"]
    r = requests.post(f"{API}/dashboard/inbox/{mid}/reply", headers=_hdr(STATE["admin_token"]),
                      json={"body": "   "}, timeout=30)
    assert r.status_code == 400


def test_reply_unknown_id_404():
    r = requests.post(f"{API}/dashboard/inbox/{uuid.uuid4()}/reply",
                      headers=_hdr(STATE["admin_token"]), json={"body": "x"}, timeout=30)
    assert r.status_code == 404


def test_reply_free_user_forbidden():
    # Try to reply to seed scout message as free user
    r = requests.post(f"{API}/dashboard/inbox/{SEED_MSG_ID}/reply",
                      headers=_hdr(STATE["free_token"]), json={"body": "should fail"}, timeout=30)
    assert r.status_code == 403, f"free user must not reply to scout message; got {r.status_code} {r.text}"


# Admin messages list includes reply_count + admin replies endpoint
def test_admin_messages_include_reply_count():
    r = requests.get(f"{API}/admin/dashboard/messages", headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r.status_code == 200
    msgs = r.json()["messages"]
    disposable = next((m for m in msgs if m["id"] == STATE["disposable_msg_id"]), None)
    assert disposable is not None
    assert disposable["reply_count"] >= 1


def test_admin_message_replies_endpoint():
    r = requests.get(f"{API}/admin/dashboard/messages/{STATE['disposable_msg_id']}/replies",
                     headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r.status_code == 200
    replies = r.json()["replies"]
    assert len(replies) >= 1
    assert any(rep["body"] == "ITER87 admin reply body" for rep in replies)


def test_admin_messages_no_token_401():
    r = requests.get(f"{API}/admin/dashboard/messages", timeout=30)
    assert r.status_code in (401, 403)


def test_admin_messages_free_token_403():
    r = requests.get(f"{API}/admin/dashboard/messages", headers=_hdr(STATE["free_token"]), timeout=30)
    assert r.status_code == 403


def test_admin_replies_free_token_403():
    r = requests.get(f"{API}/admin/dashboard/messages/{STATE['disposable_msg_id']}/replies",
                     headers=_hdr(STATE["free_token"]), timeout=30)
    assert r.status_code == 403


# Profile-views endpoint
def test_profile_views_free_locked():
    r = requests.get(f"{API}/dashboard/profile-views", headers=_hdr(STATE["free_token"]), timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["locked"] is True


def test_profile_views_admin_unlocked():
    r = requests.get(f"{API}/dashboard/profile-views", headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["locked"] is False
    assert "total" in d and "this_week" in d


# Discoverable premium gate
def test_discoverable_free_forbidden():
    r = requests.put(f"{API}/profile/me", headers=_hdr(STATE["free_token"]),
                     json={"discoverable": True}, timeout=30)
    assert r.status_code == 403
    body = r.text.lower()
    assert "premium" in body or "scout library" in body


def test_discoverable_false_free_allowed():
    r = requests.put(f"{API}/profile/me", headers=_hdr(STATE["free_token"]),
                     json={"discoverable": False}, timeout=30)
    assert r.status_code == 200


def test_discoverable_premium_allowed():
    # premium user has paid report seeded
    r = requests.put(f"{API}/profile/me", headers=_hdr(STATE["prem_token"]),
                     json={"discoverable": True, "birth_year": 2000}, timeout=30)
    assert r.status_code == 200, r.text


# Profile view increments + self-view doesn't count
def test_profile_view_increments():
    # As admin, open prem user's detail
    pid = STATE["prem_user_id"]
    # Get initial (view as prem himself first to confirm no self-view record)
    r = requests.get(f"{API}/players-database/player/{pid}", headers=_hdr(STATE["prem_token"]), timeout=30)
    # premium user may or may not have scout access, don't assert here
    # As admin, view detail
    r = requests.get(f"{API}/players-database/player/{pid}", headers=_hdr(STATE["admin_token"]), timeout=30)
    assert r.status_code == 200, r.text
    time.sleep(0.5)
    # Now check prem user's profile-views total >= 1
    pv = requests.get(f"{API}/dashboard/profile-views", headers=_hdr(STATE["prem_token"]), timeout=30).json()
    assert pv["locked"] is False
    assert pv["total"] >= 1, f"expected total>=1 after admin viewed, got {pv}"


# Report-ready notification idempotency (direct import)
def test_notify_dashboard_report_idempotent():
    import sys
    sys.path.insert(0, "/app/backend")
    from server import _notify_dashboard_report  # noqa

    fake_report_id = str(uuid.uuid4())
    STATE["created_fake_report_id"] = fake_report_id

    async def _run_inner():
        client, db = _get_db()
        try:
            await db.reports.insert_one({
                "id": fake_report_id, "user_id": STATE["prem_user_id"],
                "player_details": {"player_name": "ITER87 Fake"},
                "created_at": "2026-01-01T00:00:00+00:00",
            })
            await _notify_dashboard_report(fake_report_id, "preview")
            await _notify_dashboard_report(fake_report_id, "preview")  # duplicate
            docs = await db.dashboard_messages.find(
                {"link": f"/report/{fake_report_id}"}, {"_id": 0}
            ).to_list(10)
            return docs
        finally:
            client.close()

    docs = _run(_run_inner())
    assert len(docs) == 1, f"expected exactly 1 notification doc, got {len(docs)}"
    assert docs[0]["target_email"] == PREM_EMAIL.lower()
    assert docs[0]["link"] == f"/report/{fake_report_id}"
