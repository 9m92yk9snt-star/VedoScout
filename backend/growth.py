"""growth.py — conversion engine: discounts + scheduled nurture emails.
All emails are personal (player's name + REAL numbers) and only fire for
reports that are complete but never purchased. Flags on the docs guarantee
each mail is sent at most once."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from email_service import email_enabled, send_email_async
from email_templates import (
    render_conv_waiting_email,
    render_conv_discount_email,
    render_conv_discovery_email,
    render_abandoned_checkout_email,
    _site_url,
)
from score_meaning import build_score_meaning, build_score_meaning_teaser

logger = logging.getLogger("elite-scout")

MAX_AGE_HOURS = 14 * 24  # never nurture reports older than 14 days (launch safety)


def _parse_iso(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _now():
    return datetime.now(timezone.utc)


# ── Discounts ───────────────────────────────────────────────────────────────
async def growth_emails_enabled(db) -> bool:
    doc = await db.settings.find_one({"key": "growth_emails_enabled"})
    return bool(doc and doc.get("value") is True)


async def get_auto_discount_percent(db) -> float:
    doc = await db.settings.find_one({"key": "auto_discount_percent"})
    try:
        v = float(doc["value"]) if doc and "value" in doc else 25.0
    except Exception:
        v = 25.0
    return max(1.0, min(90.0, v))


async def get_active_discount(db, report: dict | None = None) -> dict | None:
    """Best active discount: report-level 48h offer wins over global campaign."""
    now = _now().isoformat()
    if report:
        d = report.get("discount")
        if isinstance(d, dict) and d.get("percent") and str(d.get("expires_at", "")) > now:
            return {"percent": float(d["percent"]), "expires_at": d["expires_at"],
                    "source": d.get("source", "auto_48h")}
    c = await db.discount_campaigns.find_one(
        {"active": True, "expires_at": {"$gt": now}}, sort=[("created_at", -1)])
    if c:
        return {"percent": float(c["percent"]), "expires_at": c["expires_at"],
                "source": "campaign", "name": c.get("name")}
    return None


def discounted_price(base: float, disc: dict) -> float:
    return round(float(base) * (1.0 - float(disc["percent"]) / 100.0), 2)


# ── Conversion sweep ────────────────────────────────────────────────────────
async def conversion_sweep(db, get_single_price, dry_run: bool = False) -> list:
    """One pass over unpaid completed reports + abandoned checkouts.
    Timeline per report: 24h numbers-waiting → 48h discount → 72h discovery."""
    if not email_enabled() and not dry_run:
        return []
    now = _now()
    results = []

    cur = db.reports.find({
        "status": "complete",
        "is_paid": {"$ne": True},
        "manually_unlocked": {"$ne": True},
        "full_report": {"$type": "object"},
        "conv_mail3_sent_at": {"$exists": False},
    }).sort("created_at", -1).limit(100)

    async for doc in cur:
        created = _parse_iso(doc.get("created_at"))
        email = doc.get("user_email")
        if not created or not email:
            continue
        age_h = (now - created).total_seconds() / 3600.0
        if age_h < 24 or age_h > MAX_AGE_HOURS:
            continue
        pd = doc.get("player_details") or {}
        first = str(pd.get("player_name") or "your player").split(" ")[0]
        report_url = f"{_site_url()}/report/{doc['id']}"

        try:
            if age_h >= 72 and not doc.get("conv_mail3_sent_at"):
                sm = build_score_meaning(doc)
                if sm and sm.get("discovery"):
                    if not dry_run:
                        html, text, subject = render_conv_discovery_email(first, report_url)
                        if await send_email_async(email, subject, html, text, category="conversion"):
                            await db.reports.update_one(
                                {"id": doc["id"]}, {"$set": {"conv_mail3_sent_at": now.isoformat()}})
                    results.append({"report_id": doc["id"], "mail": "discovery_72h", "to": email})
                else:
                    if not dry_run:
                        await db.reports.update_one(
                            {"id": doc["id"]}, {"$set": {"conv_mail3_sent_at": "skipped_no_discovery"}})
                    results.append({"report_id": doc["id"], "mail": "discovery_72h_skipped", "to": email})
            elif age_h >= 48 and not doc.get("conv_mail2_sent_at"):
                pct = await get_auto_discount_percent(db)
                base = float(await get_single_price())
                disc = {"percent": pct, "expires_at": (now + timedelta(hours=48)).isoformat(),
                        "source": "auto_48h"}
                if not dry_run:
                    html, text, subject = render_conv_discount_email(
                        first, report_url, pct, base, discounted_price(base, disc), hours=48)
                    if await send_email_async(email, subject, html, text, category="conversion"):
                        await db.reports.update_one(
                            {"id": doc["id"]},
                            {"$set": {"discount": disc, "conv_mail2_sent_at": now.isoformat()}})
                results.append({"report_id": doc["id"], "mail": "discount_48h", "to": email, "percent": pct})
            elif age_h >= 24 and not doc.get("conv_mail1_sent_at"):
                t = build_score_meaning_teaser(doc)
                unlocked = t.get("unlocked") or {}
                total = (t.get("locked_count") or 0) + (1 if unlocked else 0)
                if total < 2:
                    continue
                if not dry_run:
                    html, text, subject = render_conv_waiting_email(
                        first, total, unlocked.get("label"), unlocked.get("score"), report_url)
                    if await send_email_async(email, subject, html, text, category="conversion"):
                        await db.reports.update_one(
                            {"id": doc["id"]}, {"$set": {"conv_mail1_sent_at": now.isoformat()}})
                results.append({"report_id": doc["id"], "mail": "waiting_24h", "to": email, "numbers": total})
        except Exception:
            logger.exception("[conversion] mail failed for report %s", doc.get("id"))

    # ── Abandoned checkouts (1h after initiated, max 48h old) ──
    cur2 = db.payment_transactions.find({
        "payment_status": "initiated",
        "kind": {"$in": ["report_unlock", "prepay_upload"]},
        "abandon_mail_sent_at": {"$exists": False},
    }).sort("created_at", -1).limit(100)

    async for txn in cur2:
        created = _parse_iso(txn.get("created_at"))
        email = txn.get("user_email")
        if not created or not email:
            continue
        age_h = (now - created).total_seconds() / 3600.0
        if age_h > 48:
            if not dry_run:
                await db.payment_transactions.update_one(
                    {"id": txn["id"]}, {"$set": {"abandon_mail_sent_at": "expired"}})
            continue
        if age_h < 1:
            continue
        first, resume_url = "your player", f"{_site_url()}/dashboard"
        rid = txn.get("report_id")
        if rid:
            rdoc = await db.reports.find_one({"id": rid}, {"is_paid": 1, "player_details": 1})
            if not rdoc or rdoc.get("is_paid"):
                if not dry_run:
                    await db.payment_transactions.update_one(
                        {"id": txn["id"]}, {"$set": {"abandon_mail_sent_at": "skipped_paid"}})
                continue
            first = str((rdoc.get("player_details") or {}).get("player_name") or "your player").split(" ")[0]
            resume_url = f"{_site_url()}/report/{rid}"
        try:
            if not dry_run:
                html, text, subject = render_abandoned_checkout_email(first, resume_url)
                if await send_email_async(email, subject, html, text, category="abandoned_checkout"):
                    await db.payment_transactions.update_one(
                        {"id": txn["id"]}, {"$set": {"abandon_mail_sent_at": now.isoformat()}})
            results.append({"txn_id": txn["id"], "mail": "abandoned_checkout", "to": email})
        except Exception:
            logger.exception("[conversion] abandoned-checkout mail failed for txn %s", txn.get("id"))

    return results


# ── Activation sweep — signed up but never uploaded (24h + 72h nudges) ──────
async def activation_sweep(db, dry_run: bool = False) -> list:
    """Users who created an account but never uploaded a video.
    24h: warm 'your free analysis is waiting + how to film' nudge.
    72h: last friendly reminder. Flags on the user doc = sent at most once."""
    if not email_enabled() and not dry_run:
        return []
    from email_templates import render_activation_nudge_email
    now = _now()
    results = []
    cur = db.users.find({
        "role": {"$nin": ["admin", "scout"]},
        "activation_mail2_sent_at": {"$exists": False},
    }).sort("created_at", -1).limit(200)
    async for u in cur:
        email = (u.get("email") or "").lower()
        created = _parse_iso(u.get("created_at"))
        if not email or "@" not in email or email.endswith("@example.com") or not created:
            continue
        age_h = (now - created).total_seconds() / 3600.0
        if age_h < 24 or age_h > MAX_AGE_HOURS:
            continue
        if await db.reports.count_documents({"user_id": u.get("id")}, limit=1):
            continue
        first = str(u.get("full_name") or u.get("name") or "").split(" ")[0] or None
        try:
            mail1_at = _parse_iso(u.get("activation_mail1_sent_at"))
            if age_h >= 72 and mail1_at:
                if (now - mail1_at).total_seconds() < 24 * 3600:
                    continue
                if not dry_run:
                    html, text, subject = render_activation_nudge_email(first, stage=2)
                    if await send_email_async(email, subject, html, text, category="activation"):
                        await db.users.update_one(
                            {"id": u["id"]}, {"$set": {"activation_mail2_sent_at": now.isoformat()}})
                results.append({"user_id": u.get("id"), "mail": "activation_72h", "to": email})
            elif not u.get("activation_mail1_sent_at"):
                if not dry_run:
                    html, text, subject = render_activation_nudge_email(first, stage=1)
                    if await send_email_async(email, subject, html, text, category="activation"):
                        await db.users.update_one(
                            {"id": u["id"]}, {"$set": {"activation_mail1_sent_at": now.isoformat()}})
                results.append({"user_id": u.get("id"), "mail": "activation_24h", "to": email})
        except Exception:
            logger.exception("[activation] mail failed for user %s", u.get("id"))
    return results


async def conversion_loop(db, get_single_price):
    await asyncio.sleep(120)
    while True:
        try:
            if email_enabled() and await growth_emails_enabled(db):
                sent = await conversion_sweep(db, get_single_price)
                if sent:
                    logger.info("[conversion] processed %d item(s)", len(sent))
                acts = await activation_sweep(db)
                if acts:
                    logger.info("[activation] processed %d item(s)", len(acts))
        except Exception:
            logger.exception("[conversion] sweep crashed")
        await asyncio.sleep(15 * 60)
