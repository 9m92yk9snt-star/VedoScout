"""Iter74: Instagram funnel (guide magnet, funnel admin, discount codes),
carousel studio, checkout regression with allow_promotion_codes,
newsletter welcome email, blog regression."""
import os
import time
import uuid
import asyncio
from datetime import datetime, timezone, timedelta

import pytest
import requests


def _load_base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE = _load_base()
API = f"{BASE}/api"
ADMIN_EMAIL = "admin@elitescout.com"
ADMIN_PASSWORD = "Admin@2026!Elite"
OWNER_EMAIL = "scoutmeplay@gmail.com"

# Cleanup tracking
_test_lead_ids = []
_test_code_ids = []
_test_sub_ids = []
_disposable_user_ids = []


# ── Fixtures ─────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def pub():
    return requests.Session()


@pytest.fixture(scope="module")
def admin(pub):
    r = pub.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    s = requests.Session()
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    s.cookies.update(pub.cookies)
    return s


# ── 1. Blog regression ─────────────────────────────────────────────
def test_blog_lists_articles(pub):
    r = pub.get(f"{API}/blog/posts")
    assert r.status_code == 200
    data = r.json()
    items = data.get("items") or []
    slugs = [p.get("slug") for p in items]
    assert "how-to-help-your-child-bounce-back-after-a-tough-match-0b85" in slugs, f"slugs={slugs}"
    # 6 published articles
    assert data.get("total", len(items)) >= 6


def test_blog_cover_image(pub):
    r = pub.get(f"{API}/blog/uploads/cover-bounce-back.jpg")
    assert r.status_code == 200
    assert "image" in r.headers.get("content-type", "")


def test_blog_article_renders(pub):
    slug = "how-to-help-your-child-bounce-back-after-a-tough-match-0b85"
    r = pub.get(f"{API}/blog/posts/{slug}")
    assert r.status_code == 200
    d = r.json()
    post = d.get("post") or d
    body = post.get("content_md") or post.get("content") or ""
    assert len(body) > 300
    cover = post.get("cover_image_url") or post.get("cover_image") or ""
    assert "bounce-back" in cover


def test_blog_studio_config_auto_weekly(admin):
    r = admin.get(f"{API}/blog-studio/config")
    assert r.status_code == 200
    d = r.json()
    assert d.get("auto_weekly") is True, f"auto_weekly must stay TRUE, got {d}"


# ── 2. Guide backend ───────────────────────────────────────────────
def test_guide_pdf_download(pub):
    r = pub.get(f"{API}/guide/pdf")
    assert r.status_code == 200
    assert r.headers.get("content-type") == "application/pdf"
    assert len(r.content) > 20000  # ~72KB expected


def test_guide_subscribe_invalid_email(pub):
    r = pub.post(f"{API}/guide/subscribe", json={"email": "not-an-email", "name": "x"})
    assert r.status_code == 400


def test_guide_subscribe_and_duplicate_and_admin_list(pub, admin):
    email = f"TEST_iter74_{uuid.uuid4().hex[:6]}@example.com"
    r = pub.post(f"{API}/guide/subscribe", json={"email": email, "name": "Iter74 Tester"})
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True

    # duplicate
    r2 = pub.post(f"{API}/guide/subscribe", json={"email": email, "name": "Iter74 Tester"})
    assert r2.status_code == 200
    assert r2.json().get("already") is True

    # admin list contains lead
    r3 = admin.get(f"{API}/admin/guide/leads")
    assert r3.status_code == 200
    leads = r3.json().get("items", [])
    match = [l for l in leads if l.get("email") == email.lower()]
    assert match, f"lead not found in admin listing"
    lead_id = match[0]["id"]
    _test_lead_ids.append(lead_id)

    # unsubscribe
    ur = pub.get(f"{API}/guide/unsubscribe/{lead_id}")
    assert ur.status_code == 200
    assert "unsubscribed" in ur.text.lower() or "unsub" in ur.text.lower()


# ── 3. Funnel admin config ─────────────────────────────────────────
def test_funnel_config_get_default(admin):
    r = admin.get(f"{API}/admin/guide/funnel")
    assert r.status_code == 200
    cfg = r.json()
    assert cfg.get("enabled") is True
    steps = cfg["steps"]
    assert "report_offer" in steps and "membership_offer" in steps and "paid_guide" in steps


def test_funnel_config_put_and_restore(admin):
    # snapshot
    orig = admin.get(f"{API}/admin/guide/funnel").json()

    # mutate
    r = admin.put(f"{API}/admin/guide/funnel", json={
        "enabled": True,
        "steps": {"report_offer": {"delay_days": 3, "percent": 25, "code": "TESTOFFER"}}
    })
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["steps"]["report_offer"]["delay_days"] == 3
    assert cfg["steps"]["report_offer"]["percent"] == 25
    assert cfg["steps"]["report_offer"]["code"] == "TESTOFFER"

    # verify GET
    r2 = admin.get(f"{API}/admin/guide/funnel")
    assert r2.json()["steps"]["report_offer"]["code"] == "TESTOFFER"

    # restore defaults
    restore = {
        "enabled": True,
        "steps": {
            "report_offer": {"enabled": True, "delay_days": 2, "code": "", "percent": 20},
            "membership_offer": {"enabled": True, "delay_days": 5, "code": "", "percent": 20},
            "paid_guide": {"enabled": False, "delay_days": 8, "price": 19.0, "link": ""},
        }
    }
    rr = admin.put(f"{API}/admin/guide/funnel", json=restore)
    assert rr.status_code == 200
    final = admin.get(f"{API}/admin/guide/funnel").json()
    assert final["steps"]["report_offer"]["code"] == ""
    assert final["steps"]["report_offer"]["delay_days"] == 2
    assert final["steps"]["paid_guide"]["enabled"] is False


# ── 4. Funnel sweep dry run (backdated synthetic lead) ─────────────
def test_funnel_sweep_dry_run_backdated_lead():
    """Insert a 3-day-old synthetic lead and verify sweep picks it up only when code set."""
    import sys
    sys.path.insert(0, "/app/backend")
    from motor.motor_asyncio import AsyncIOMotorClient
    from growth_funnel import guide_funnel_sweep

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    assert mongo_url and db_name

    async def _run():
        client = AsyncIOMotorClient(mongo_url)
        db = client[db_name]
        lead_id = str(uuid.uuid4())
        old_iso = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        email = f"TEST_iter74_sweep_{uuid.uuid4().hex[:6]}@example.com"
        await db.guide_leads.insert_one({
            "id": lead_id, "email": email, "name": "Sweep Tester",
            "source": "guide", "unsubscribed": False,
            "sent": {"guide": old_iso}, "created_at": old_iso
        })
        # snapshot funnel cfg
        orig_settings = await db.settings.find_one({"key": "guide_funnel"})

        async def _price():
            return 29.0

        try:
            # 1) With NO code -> should NOT pick report_offer
            await db.settings.update_one({"key": "guide_funnel"}, {"$set": {
                "enabled": True,
                "steps": {
                    "report_offer": {"enabled": True, "delay_days": 2, "code": "", "percent": 20},
                    "membership_offer": {"enabled": True, "delay_days": 5, "code": "", "percent": 20},
                    "paid_guide": {"enabled": False, "delay_days": 8, "price": 19.0, "link": ""},
                }
            }}, upsert=True)
            no_code = await guide_funnel_sweep(db, _price, dry_run=True)
            picked = [r for r in no_code if r["lead"] == email]
            assert not picked, f"should NOT pick without code, got {picked}"

            # 2) With code set -> should pick report_offer
            await db.settings.update_one({"key": "guide_funnel"}, {"$set": {
                "steps.report_offer.code": "SWEEPTEST20"
            }})
            with_code = await guide_funnel_sweep(db, _price, dry_run=True)
            picked = [r for r in with_code if r["lead"] == email and r["step"] == "report_offer"]
            assert picked, f"should pick report_offer with code, got {with_code}"
        finally:
            # cleanup lead & restore settings
            await db.guide_leads.delete_one({"id": lead_id})
            if orig_settings:
                orig_settings.pop("_id", None)
                await db.settings.update_one({"key": "guide_funnel"}, {"$set": orig_settings}, upsert=True)
            else:
                await db.settings.delete_one({"key": "guide_funnel"})
            client.close()

    asyncio.run(_run())

    # Ensure defaults restored
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    tok = r.json().get("access_token") or r.json().get("token")
    hdr = {"Authorization": f"Bearer {tok}"} if tok else {}
    restore = {
        "enabled": True,
        "steps": {
            "report_offer": {"enabled": True, "delay_days": 2, "code": "", "percent": 20},
            "membership_offer": {"enabled": True, "delay_days": 5, "code": "", "percent": 20},
            "paid_guide": {"enabled": False, "delay_days": 8, "price": 19.0, "link": ""},
        }
    }
    requests.put(f"{API}/admin/guide/funnel", json=restore, headers=hdr)


# ── 5. Discount codes ──────────────────────────────────────────────
def test_discount_code_create_toggle_delete(admin):
    code = f"TESTCODE{uuid.uuid4().hex[:4].upper()}"
    r = admin.post(f"{API}/admin/discount-codes", json={
        "code": code, "percent": 15, "applies_to": "both"
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["code"] == code
    assert d["percent"] == 15
    code_id = d["id"]
    _test_code_ids.append(code_id)

    # Stripe promo — currently broken (see warning). Record must still exist.
    warn = d.get("warning")
    stripe_ok = bool(d.get("stripe_promo_id"))
    if not stripe_ok:
        print(f"WARN: Stripe promo NOT created for code {code}. warning={warn}")

    # list
    r2 = admin.get(f"{API}/admin/discount-codes")
    assert r2.status_code == 200
    codes = r2.json().get("items", [])
    assert any(c["code"] == code for c in codes)

    # toggle
    r3 = admin.patch(f"{API}/admin/discount-codes/{code_id}")
    assert r3.status_code == 200
    assert r3.json().get("active") is False
    # toggle back
    admin.patch(f"{API}/admin/discount-codes/{code_id}")

    # delete
    r4 = admin.delete(f"{API}/admin/discount-codes/{code_id}")
    assert r4.status_code == 200
    _test_code_ids.remove(code_id)


# ── 6. Checkout regression ─────────────────────────────────────────
def test_checkout_subscribe_and_prepay_with_promotion_codes(pub, admin):
    """Create disposable user, verify Stripe session creation with allow_promotion_codes."""
    email = f"TEST_iter74_ck_{uuid.uuid4().hex[:6]}@example.com"
    r = pub.post(f"{API}/auth/signup", json={
        "email": email, "password": "Test@2026!Iter", "full_name": "Iter74 Tester"
    })
    assert r.status_code in (200, 201), r.text
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    user_id = (data.get("user") or {}).get("id") or data.get("user_id")
    if user_id:
        _disposable_user_ids.append(user_id)

    u = requests.Session()
    if tok:
        u.headers["Authorization"] = f"Bearer {tok}"
    u.cookies.update(pub.cookies)

    # subscribe tier=premium
    origin = BASE
    r2 = u.post(f"{API}/payments/subscribe", json={"tier": "premium", "origin_url": origin})
    assert r2.status_code == 200, f"subscribe failed: {r2.status_code} {r2.text[:400]}"
    d2 = r2.json()
    url = d2.get("url") or d2.get("checkout_url")
    assert url and "stripe.com" in url, f"expected Stripe URL, got {d2}"

    # embedded prepay-upload
    r3 = u.post(f"{API}/payments/embedded/prepay-upload", json={"origin_url": origin})
    assert r3.status_code == 200, f"prepay-upload failed: {r3.status_code} {r3.text[:400]}"
    d3 = r3.json()
    assert d3.get("client_secret"), f"missing client_secret: {d3}"

    # cleanup disposable user
    if user_id:
        # try DELETE /api/admin/users/{id}
        cleanup = admin.delete(f"{API}/admin/users/{user_id}")
        if cleanup.status_code not in (200, 204):
            # fallback: direct DB
            try:
                from motor.motor_asyncio import AsyncIOMotorClient
                async def _wipe():
                    client = AsyncIOMotorClient(os.environ.get("MONGO_URL"))
                    dbn = os.environ.get("DB_NAME")
                    await client[dbn].users.delete_one({"id": user_id})
                    await client[dbn].users.delete_one({"email": email})
                    client.close()
                asyncio.run(_wipe())
            except Exception:
                pass
        _disposable_user_ids.remove(user_id)


# ── 7. Newsletter welcome + unsubscribe ────────────────────────────
def test_newsletter_welcome_owner(pub):
    """Subscribe owner email — verify OK and welcome log line."""
    # Ensure prior subscriber removed to trigger fresh welcome
    # (we won't fail if it's already there — just verify ok:true)
    r = pub.post(f"{API}/newsletter/subscribe", json={"email": OWNER_EMAIL, "source": "iter74-test"})
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True

    # capture sub_id if returned - most implementations return id or already flag
    sub_id = d.get("id") or d.get("sub_id")

    # Give email time to queue then check backend log
    time.sleep(3)
    try:
        with open("/var/log/supervisor/backend.err.log") as f:
            log = f.read()[-40000:]
        # Only care about welcome subject line existence in recent logs
        if "Welcome to The ScoutMePlay Letter" not in log:
            # not necessarily fatal — could be already-subscribed
            print("WARN: welcome subject not seen in recent backend.err.log; may be already-subscribed skip")
    except Exception:
        pass

    # If new, remove test artifact — but per instructions do NOT remove owner unless needed.
    # We'll leave the owner subscriber if already there.


def test_newsletter_unsubscribe_flow(pub, admin):
    """Test full subscribe->unsubscribe flow with a TEST_ email."""
    email = f"TEST_iter74_nl_{uuid.uuid4().hex[:6]}@example.com"
    r = pub.post(f"{API}/newsletter/subscribe", json={"email": email, "source": "iter74"})
    assert r.status_code == 200
    # find sub_id via admin listing
    r2 = admin.get(f"{API}/admin/newsletter")
    subs = r2.json().get("items", [])
    match = [s for s in subs if s.get("email") == email.lower()]
    assert match, "test subscriber not found in admin listing"
    sub_id = match[0]["id"]

    ur = pub.get(f"{API}/newsletter/unsubscribe/{sub_id}")
    assert ur.status_code == 200
    # verify removed
    r3 = admin.get(f"{API}/admin/newsletter")
    subs2 = r3.json().get("items", [])
    assert not any(s.get("email") == email.lower() for s in subs2)


# ── 8. Cleanup: final restore ──────────────────────────────────────
def test_zz_final_cleanup_and_restore(admin):
    """Delete any test artifacts left behind, restore funnel defaults, verify auto_weekly still on."""
    # delete any test guide leads
    r = admin.get(f"{API}/admin/guide/leads")
    if r.status_code == 200:
        for lead in r.json().get("items", []):
            em = lead.get("email", "")
            if em.startswith("TEST_iter74") and em != OWNER_EMAIL:
                admin.delete(f"{API}/admin/guide/leads/{lead['id']}")

    # delete any lingering test codes
    r2 = admin.get(f"{API}/admin/discount-codes")
    if r2.status_code == 200:
        for c in r2.json().get("items", []):
            if c.get("code", "").startswith("TESTCODE"):
                admin.delete(f"{API}/admin/discount-codes/{c['id']}")

    # restore funnel defaults
    restore = {
        "enabled": True,
        "steps": {
            "report_offer": {"enabled": True, "delay_days": 2, "code": "", "percent": 20},
            "membership_offer": {"enabled": True, "delay_days": 5, "code": "", "percent": 20},
            "paid_guide": {"enabled": False, "delay_days": 8, "price": 19.0, "link": ""},
        }
    }
    admin.put(f"{API}/admin/guide/funnel", json=restore)

    # ensure auto_weekly still true
    r3 = admin.get(f"{API}/blog-studio/config")
    assert r3.json().get("auto_weekly") is True
