"""iter67 — growth package (nurture emails/discounts/share/reviews) tests."""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

OWNER = ("smtest.parent@example.com", "SmTest@2026!x")
ADMIN = ("admin@elitescout.com", "Admin@2026!Elite")
PUBLIC_TEASER_TOKEN = "e282ef4bcee743fc87258f35d037775e"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def owner_headers():
    return {"Authorization": f"Bearer {_login(*OWNER)}"}


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {_login(*ADMIN)}"}


# ── sweep ────────────────────────────────────────────────────────────
class TestSweep:
    def test_dry_run_returns_4_planned_items(self, admin_headers):
        r = requests.post(f"{API}/admin/conversion-sweep?dry_run=true", headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["dry_run"] is True
        mails = {x.get("mail") for x in data["results"]}
        assert "waiting_24h" in mails
        assert "discount_48h" in mails
        assert "discovery_72h" in mails
        assert "abandoned_checkout" in mails
        assert len(data["results"]) >= 4

    def test_dry_run_idempotent(self, admin_headers):
        r1 = requests.post(f"{API}/admin/conversion-sweep?dry_run=true", headers=admin_headers, timeout=60).json()
        r2 = requests.post(f"{API}/admin/conversion-sweep?dry_run=true", headers=admin_headers, timeout=60).json()
        # same count => flags not mutated
        assert len(r1["results"]) == len(r2["results"])


# ── discount pricing on reports ──────────────────────────────────────
class TestReportPricing:
    def test_report_with_discount(self, owner_headers):
        r = requests.get(f"{API}/reports/smtest-30h", headers=owner_headers, timeout=30)
        assert r.status_code == 200
        pricing = r.json().get("pricing") or {}
        d = pricing.get("discount")
        assert d is not None
        assert d["percent"] == 25
        assert abs(pricing["single"] - 129) < 0.01
        assert abs(d["discounted"] - 96.75) < 0.05

    def test_report_without_discount(self, owner_headers):
        r = requests.get(f"{API}/reports/smtest-50h", headers=owner_headers, timeout=30)
        assert r.status_code == 200
        pricing = r.json().get("pricing") or {}
        assert pricing.get("discount") in (None, {})


# ── campaign global fallback ─────────────────────────────────────────
class TestCampaign:
    def test_campaign_flow(self, admin_headers, owner_headers):
        # create
        r = requests.post(f"{API}/admin/discounts", headers=admin_headers,
                          json={"name": "QA test", "percent": 10, "hours_valid": 1, "send_email": False},
                          timeout=30)
        assert r.status_code == 200, r.text
        cid = r.json()["id"]

        # global fallback applies to smtest-50h
        p = requests.get(f"{API}/reports/smtest-50h", headers=owner_headers, timeout=30).json()["pricing"]
        assert p.get("discount") and p["discount"]["percent"] == 10

        # report-level 25 still wins
        p30 = requests.get(f"{API}/reports/smtest-30h", headers=owner_headers, timeout=30).json()["pricing"]
        assert p30["discount"]["percent"] == 25

        # deactivate
        d = requests.delete(f"{API}/admin/discounts/{cid}", headers=admin_headers, timeout=30)
        assert d.status_code == 200

        # smtest-50h back to null
        p = requests.get(f"{API}/reports/smtest-50h", headers=owner_headers, timeout=30).json()["pricing"]
        assert p.get("discount") in (None, {})

    def test_auto_percent_update(self, admin_headers):
        r = requests.put(f"{API}/admin/discounts/auto", headers=admin_headers, json={"percent": 30}, timeout=30)
        assert r.status_code == 200
        g = requests.get(f"{API}/admin/discounts", headers=admin_headers, timeout=30).json()
        assert abs(g["auto_percent"] - 30) < 0.01
        # restore
        requests.put(f"{API}/admin/discounts/auto", headers=admin_headers, json={"percent": 25}, timeout=30)


# ── share teaser + share-unlock ──────────────────────────────────────
class TestShare:
    def test_owner_creates_teaser_share_and_pngs_download(self, owner_headers):
        r = requests.post(f"{API}/reports/smtest-50h/teaser-share", headers=owner_headers, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("token")
        assert j.get("card_feed_url", "").startswith("/api/uploads/")
        assert j.get("card_story_url", "").startswith("/api/uploads/")
        # PNG downloads
        for u in [j["card_feed_url"], j["card_story_url"]]:
            resp = requests.get(f"{BASE}{u}", timeout=30)
            assert resp.status_code == 200
            assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_public_teaser_no_auth(self):
        r = requests.get(f"{API}/teaser/{PUBLIC_TEASER_TOKEN}", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("player_first") == "Noah"
        assert j.get("story") is not None

    def test_share_unlock_adds_bonus(self, owner_headers):
        r = requests.post(f"{API}/reports/smtest-50h/share-unlock", headers=owner_headers,
                          json={"shared": True}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert j.get("bonus") is not None
        # bonus reflected in report score_meaning_teaser
        rep = requests.get(f"{API}/reports/smtest-50h", headers=owner_headers, timeout=30).json()
        smt = rep.get("score_meaning_teaser") or {}
        assert smt.get("bonus") is not None
        bonus_label = smt["bonus"].get("label")
        locked_labels = smt.get("locked_labels") or []
        if bonus_label:
            assert bonus_label not in locked_labels


# ── reviews ──────────────────────────────────────────────────────────
class TestReviews:
    def test_public_get_no_auth(self):
        r = requests.get(f"{API}/reviews", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json().get("items"), list)

    def test_owner_upsert_only_one(self, owner_headers):
        r1 = requests.post(f"{API}/reviews", headers=owner_headers,
                           json={"stars": 4, "text": "Really helpful iter67 test A"}, timeout=30)
        assert r1.status_code == 200, r1.text
        r2 = requests.post(f"{API}/reviews", headers=owner_headers,
                           json={"stars": 5, "text": "Really helpful iter67 test B"}, timeout=30)
        assert r2.status_code == 200
        mine = requests.get(f"{API}/reviews/mine", headers=owner_headers, timeout=30).json()
        assert mine["review"]["stars"] == 5
        # only one for this user in public list
        pub = requests.get(f"{API}/reviews", timeout=30).json()["items"]
        mine_id = mine["review"]["id"]
        count = sum(1 for x in pub if x["id"] == mine_id)
        assert count <= 1

    def test_validation(self, owner_headers):
        bad = requests.post(f"{API}/reviews", headers=owner_headers, json={"stars": 0, "text": "abcd"}, timeout=30)
        assert bad.status_code == 422
        bad2 = requests.post(f"{API}/reviews", headers=owner_headers, json={"stars": 6, "text": "abcd"}, timeout=30)
        assert bad2.status_code == 422
        bad3 = requests.post(f"{API}/reviews", headers=owner_headers, json={"stars": 4, "text": "ab"}, timeout=30)
        assert bad3.status_code == 422

    def test_admin_add_and_delete(self, admin_headers):
        r = requests.post(f"{API}/admin/reviews", headers=admin_headers,
                          json={"name": "TEST QA parent", "stars": 5, "text": "iter67 admin-added review"}, timeout=30)
        assert r.status_code == 200, r.text
        rid = r.json()["review"]["id"]
        listing = requests.get(f"{API}/admin/reviews", headers=admin_headers, timeout=30).json()
        assert any(x["id"] == rid for x in listing["items"])
        d = requests.delete(f"{API}/admin/reviews/{rid}", headers=admin_headers, timeout=30)
        assert d.status_code == 200
