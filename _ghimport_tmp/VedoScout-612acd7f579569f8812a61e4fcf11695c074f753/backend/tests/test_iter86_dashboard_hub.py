"""Backend tests for Dashboard Hub feature (iter86).

Covers: community numbers, admin message compose/list/delete, inbox premium
gating for free users, read state, opportunities (premium-only), performance
endpoint (no-report case), and admin auth guards.

The test uses the ADMIN account from /app/memory/test_credentials.md and
creates a disposable FREE user via /api/auth/signup which is deleted after
the run. The existing seed message 'Impressive footage' and opportunity
'Elite Football Academy Trials' are preserved.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"

# Disposable free user
FREE_EMAIL = f"iter86.free.{uuid.uuid4().hex[:8]}@example.com"
FREE_PASSWORD = "TestPass@2026!"
FREE_NAME = "Iter86 Free"


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def free_user():
    r = requests.post(f"{API}/auth/signup", json={"email": FREE_EMAIL, "password": FREE_PASSWORD, "full_name": FREE_NAME}, timeout=30)
    assert r.status_code == 200, f"free signup failed: {r.status_code} {r.text}"
    tok = r.json()["access_token"]
    uid = r.json()["user"]["id"]
    yield {"token": tok, "id": uid, "email": FREE_EMAIL}
    # cleanup via admin
    a = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30).json()["access_token"]
    # Try common admin delete endpoints
    for path in (f"/admin/users/{uid}", f"/admin/user/{uid}"):
        try:
            requests.delete(f"{API}{path}", headers=_auth_headers(a), timeout=15)
        except Exception:
            pass


@pytest.fixture(scope="module")
def state():
    return {"created_messages": [], "created_opps": []}


# ── Community ────────────────────────────────────────────────────────────
class TestCommunity:
    def test_get_community_defaults(self, free_user):
        r = requests.get(f"{API}/dashboard/community", headers=_auth_headers(free_user["token"]), timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("players_in_library", "clubs_looking", "scouts_searching", "active_agents", "trial_invites"):
            assert k in d and isinstance(d[k], int)

    def test_admin_put_community_persists_and_reset(self, admin_token):
        # Set to test value
        r = requests.put(
            f"{API}/admin/dashboard/community",
            json={"players_in_library": 9999},
            headers=_auth_headers(admin_token), timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["players_in_library"] == 9999
        # Verify via GET
        r2 = requests.get(f"{API}/dashboard/community", headers=_auth_headers(admin_token), timeout=15)
        assert r2.json()["players_in_library"] == 9999
        # Reset back to 2847
        r3 = requests.put(
            f"{API}/admin/dashboard/community",
            json={"players_in_library": 2847},
            headers=_auth_headers(admin_token), timeout=15,
        )
        assert r3.status_code == 200
        assert r3.json()["players_in_library"] == 2847


# ── Admin message compose validation ─────────────────────────────────────
class TestMessageCompose:
    def test_missing_subject_400(self, admin_token):
        r = requests.post(f"{API}/admin/dashboard/messages", json={"subject": "", "body": "hi"}, headers=_auth_headers(admin_token), timeout=15)
        assert r.status_code == 400

    def test_missing_body_400(self, admin_token):
        r = requests.post(f"{API}/admin/dashboard/messages", json={"subject": "hi", "body": ""}, headers=_auth_headers(admin_token), timeout=15)
        assert r.status_code == 400

    def test_invalid_kind_400(self, admin_token):
        r = requests.post(f"{API}/admin/dashboard/messages", json={"subject": "x", "body": "y", "kind": "bogus"}, headers=_auth_headers(admin_token), timeout=15)
        assert r.status_code == 400

    def test_invalid_sender_400(self, admin_token):
        r = requests.post(f"{API}/admin/dashboard/messages", json={"subject": "x", "body": "y", "sender_type": "bogus"}, headers=_auth_headers(admin_token), timeout=15)
        assert r.status_code == 400

    def test_invalid_target_400(self, admin_token):
        r = requests.post(f"{API}/admin/dashboard/messages", json={"subject": "x", "body": "y", "target": "bogus"}, headers=_auth_headers(admin_token), timeout=15)
        assert r.status_code == 400

    def test_target_email_unknown_404(self, admin_token):
        r = requests.post(f"{API}/admin/dashboard/messages", json={"subject": "x", "body": "y", "target_email": "nobody-xyz-999@nowhere.test"}, headers=_auth_headers(admin_token), timeout=15)
        assert r.status_code == 404

    def test_valid_compose_returns_id(self, admin_token, state):
        r = requests.post(
            f"{API}/admin/dashboard/messages",
            json={"subject": "ITER86 TEST notif", "body": "hello", "kind": "notification", "sender_type": "admin", "target": "all"},
            headers=_auth_headers(admin_token), timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id"] and d["subject"] == "ITER86 TEST notif"
        state["created_messages"].append(d["id"])


# ── Admin list & delete ──────────────────────────────────────────────────
class TestMessageListDelete:
    def test_list_messages_has_read_count(self, admin_token, state):
        r = requests.get(f"{API}/admin/dashboard/messages", headers=_auth_headers(admin_token), timeout=15)
        assert r.status_code == 200
        msgs = r.json()["messages"]
        assert isinstance(msgs, list) and len(msgs) >= 1
        for m in msgs:
            assert "read_count" in m

    def test_delete_unknown_message_404(self, admin_token):
        r = requests.delete(f"{API}/admin/dashboard/messages/nonexistent-id-xyz", headers=_auth_headers(admin_token), timeout=15)
        assert r.status_code == 404


# ── Message gating for free user ─────────────────────────────────────────
class TestGating:
    def test_inbox_shape_and_notification_visible(self, admin_token, free_user, state):
        # Create an admin notification targeted all
        r = requests.post(f"{API}/admin/dashboard/messages", json={"subject": "ITER86 all-notif", "body": "b", "kind": "notification", "sender_type": "admin", "target": "all"}, headers=_auth_headers(admin_token), timeout=15)
        assert r.status_code == 200
        notif_id = r.json()["id"]
        state["created_messages"].append(notif_id)

        # Create a scout message targeted all (should be locked for free)
        r2 = requests.post(f"{API}/admin/dashboard/messages", json={"subject": "ITER86 scout-msg", "body": "b", "kind": "message", "sender_type": "scout", "sender_name": "Scout X", "target": "all"}, headers=_auth_headers(admin_token), timeout=15)
        assert r2.status_code == 200
        scout_id = r2.json()["id"]
        state["created_messages"].append(scout_id)

        # premium-only message
        r3 = requests.post(f"{API}/admin/dashboard/messages", json={"subject": "ITER86 prem-only", "body": "b", "kind": "message", "sender_type": "admin", "target": "premium"}, headers=_auth_headers(admin_token), timeout=15)
        assert r3.status_code == 200
        prem_id = r3.json()["id"]
        state["created_messages"].append(prem_id)

        # message targeted specifically at free user's email
        r4 = requests.post(f"{API}/admin/dashboard/messages", json={"subject": "ITER86 direct-to-free", "body": "b", "kind": "message", "sender_type": "admin", "target": "all", "target_email": free_user["email"]}, headers=_auth_headers(admin_token), timeout=15)
        assert r4.status_code == 200, r4.text
        direct_id = r4.json()["id"]
        state["created_messages"].append(direct_id)

        # Fetch inbox as free user
        r5 = requests.get(f"{API}/dashboard/inbox", headers=_auth_headers(free_user["token"]), timeout=15)
        assert r5.status_code == 200, r5.text
        inbox = r5.json()
        assert inbox["premium_access"] is False
        notif_ids = {m["id"] for m in inbox["notifications"]}
        msg_ids = {m["id"] for m in inbox["messages"]}
        # Notification visible
        assert notif_id in notif_ids, "admin notification targeted all must be visible"
        # scout message must NOT be in messages array
        assert scout_id not in msg_ids, "scout message must be locked for free user"
        # locked count must include the scout msg
        assert inbox["locked_message_count"] >= 1
        # premium-only must not be visible
        assert prem_id not in msg_ids and prem_id not in notif_ids
        # direct-to-free must appear
        assert direct_id in msg_ids, "direct message to free user's email must appear"
        # Verify no scout/agent/club message body is present in visible messages
        for m in inbox["messages"]:
            assert m.get("sender_type") not in ("scout", "agent", "club"), f"leaked external sender: {m}"


# ── Read state ───────────────────────────────────────────────────────────
class TestReadState:
    def test_mark_read_and_read_all(self, admin_token, free_user, state):
        # Ensure at least one notification exists visible to free user
        r = requests.get(f"{API}/dashboard/inbox", headers=_auth_headers(free_user["token"]), timeout=15).json()
        assert r["notifications"], "need at least one notification"
        first_id = r["notifications"][0]["id"]

        # Mark unknown -> 404
        r2 = requests.post(f"{API}/dashboard/inbox/nonexistent-msg-xyz/read", headers=_auth_headers(free_user["token"]), timeout=15)
        assert r2.status_code == 404

        # Mark one read
        r3 = requests.post(f"{API}/dashboard/inbox/{first_id}/read", headers=_auth_headers(free_user["token"]), timeout=15)
        assert r3.status_code == 200

        # Verify count dropped
        after = requests.get(f"{API}/dashboard/inbox", headers=_auth_headers(free_user["token"]), timeout=15).json()
        # The specific message should be read=True
        found = next((m for m in after["notifications"] if m["id"] == first_id), None)
        assert found and found["read"] is True

        # Read all
        r4 = requests.post(f"{API}/dashboard/inbox/read-all", json={}, headers=_auth_headers(free_user["token"]), timeout=15)
        assert r4.status_code == 200
        assert r4.json()["ok"] is True

        final = requests.get(f"{API}/dashboard/inbox", headers=_auth_headers(free_user["token"]), timeout=15).json()
        assert final["unread_notifications"] == 0
        assert final["unread_messages"] == 0


# ── Opportunities ────────────────────────────────────────────────────────
class TestOpportunities:
    def test_create_missing_title_400(self, admin_token):
        r = requests.post(f"{API}/admin/dashboard/opportunities", json={"title": ""}, headers=_auth_headers(admin_token), timeout=15)
        assert r.status_code == 400

    def test_admin_crud_and_free_locked(self, admin_token, free_user, state):
        # Create
        r = requests.post(f"{API}/admin/dashboard/opportunities", json={"title": "ITER86 TEST OPP", "club_name": "TEST FC", "active": True}, headers=_auth_headers(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        opp = r.json()
        opp_id = opp["id"]
        state["created_opps"].append(opp_id)

        # Toggle active
        r2 = requests.put(f"{API}/admin/dashboard/opportunities/{opp_id}", json={"active": False}, headers=_auth_headers(admin_token), timeout=15)
        assert r2.status_code == 200
        assert r2.json()["active"] is False
        # Toggle back
        r2b = requests.put(f"{API}/admin/dashboard/opportunities/{opp_id}", json={"active": True}, headers=_auth_headers(admin_token), timeout=15)
        assert r2b.status_code == 200

        # Admin list
        r3 = requests.get(f"{API}/admin/dashboard/opportunities", headers=_auth_headers(admin_token), timeout=15)
        assert r3.status_code == 200
        assert any(o["id"] == opp_id for o in r3.json()["items"])

        # Free user: locked=true, empty items
        r4 = requests.get(f"{API}/dashboard/opportunities", headers=_auth_headers(free_user["token"]), timeout=15)
        assert r4.status_code == 200
        d = r4.json()
        assert d["locked"] is True
        assert d["items"] == []

        # Admin (premium via role): locked=false, items present
        r5 = requests.get(f"{API}/dashboard/opportunities", headers=_auth_headers(admin_token), timeout=15)
        assert r5.status_code == 200
        d5 = r5.json()
        assert d5["locked"] is False
        assert any(o["id"] == opp_id for o in d5["items"])


# ── Performance no-report ────────────────────────────────────────────────
class TestPerformance:
    def test_no_report_returns_has_report_false(self, free_user):
        r = requests.get(f"{API}/dashboard/performance", headers=_auth_headers(free_user["token"]), timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["has_report"] is False


# ── Admin auth guards ────────────────────────────────────────────────────
class TestAdminGuards:
    def test_no_token_401(self):
        r = requests.get(f"{API}/admin/dashboard/community", timeout=15)
        assert r.status_code in (401, 403), r.status_code

    def test_free_user_token_forbidden(self, free_user):
        for path in (
            "/admin/dashboard/community",
            "/admin/dashboard/messages",
            "/admin/dashboard/opportunities",
        ):
            r = requests.get(f"{API}{path}", headers=_auth_headers(free_user["token"]), timeout=15)
            assert r.status_code in (401, 403), f"{path} → {r.status_code}"

        r2 = requests.put(f"{API}/admin/dashboard/community", json={"players_in_library": 1}, headers=_auth_headers(free_user["token"]), timeout=15)
        assert r2.status_code in (401, 403)


# ── Cleanup (executes last) ─────────────────────────────────────────────
def test_zzz_cleanup(admin_token, state):
    for mid in state["created_messages"]:
        r = requests.delete(f"{API}/admin/dashboard/messages/{mid}", headers=_auth_headers(admin_token), timeout=15)
        assert r.status_code in (200, 404), f"cleanup message {mid} → {r.status_code}"
    for oid in state["created_opps"]:
        r = requests.delete(f"{API}/admin/dashboard/opportunities/{oid}", headers=_auth_headers(admin_token), timeout=15)
        assert r.status_code in (200, 404), f"cleanup opp {oid} → {r.status_code}"
    # Final community reset guarantee
    r = requests.put(f"{API}/admin/dashboard/community", json={"players_in_library": 2847}, headers=_auth_headers(admin_token), timeout=15)
    assert r.status_code == 200
