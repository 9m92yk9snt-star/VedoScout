"""growth_funnel.py — guide lead magnet, offer email sequence + admin discount codes."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from email_service import send_email_async
from guide_emails import (
    render_guide_delivery_email,
    render_guide_membership_offer_email,
    render_guide_paid_guide_email,
    render_guide_report_offer_email,
)
from email_templates import _site_url
from guide_pdf import build_guide_pdf

load_dotenv()
logger = logging.getLogger("growth_funnel")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

DEFAULT_FUNNEL = {
    "enabled": True,
    "steps": {
        "report_offer": {"enabled": True, "delay_days": 2, "code": "", "percent": 20},
        "membership_offer": {"enabled": True, "delay_days": 5, "code": "", "percent": 20},
        "paid_guide": {"enabled": False, "delay_days": 8, "price": 19.0, "link": ""},
    },
}


def _now():
    return datetime.now(timezone.utc)


def _now_iso():
    return _now().isoformat()


async def get_funnel_config(db) -> dict:
    doc = await db.settings.find_one({"key": "guide_funnel"}) or {}
    cfg = {**DEFAULT_FUNNEL, **{k: v for k, v in doc.items() if k in ("enabled",)}}
    steps = dict(DEFAULT_FUNNEL["steps"])
    for sid, sdef in steps.items():
        steps[sid] = {**sdef, **((doc.get("steps") or {}).get(sid) or {})}
    cfg["steps"] = steps
    return cfg


def _unsub_url(lead_id: str) -> str:
    backend = os.environ.get("SITE_PUBLIC_URL") or _site_url()
    return f"{backend.rstrip('/')}/api/guide/unsubscribe/{lead_id}"


def _pdf_url() -> str:
    return f"{_site_url()}/api/guide/pdf"


# ── Stripe promo helpers ──────────────────────────────────────────────────

def _stripe():
    import stripe
    key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY")
    if not key or not key.startswith("sk_"):
        return None
    stripe.api_key = key
    return stripe


async def _create_stripe_promo(code: str, percent: int, expires_at: Optional[str], max_uses: Optional[int]):
    s = _stripe()
    if not s:
        return None, "Stripe not configured — code saved but cannot be redeemed at checkout yet"

    def _do():
        coupon = s.Coupon.create(percent_off=percent, duration="once", name=f"ScoutMePlay {code}")
        kwargs = {"code": code}
        try:
            promo = s.PromotionCode.create(promotion={"type": "coupon", "coupon": coupon.id}, **kwargs_extra(kwargs))
        except Exception as e:
            if "unknown parameter" in str(e).lower():
                promo = s.PromotionCode.create(coupon=coupon.id, **kwargs_extra(kwargs))
            else:
                raise
        return promo

    def kwargs_extra(kwargs):
        if expires_at:
            try:
                kwargs["expires_at"] = int(datetime.fromisoformat(expires_at).replace(tzinfo=timezone.utc).timestamp())
            except Exception:
                pass
        if max_uses:
            kwargs["max_redemptions"] = int(max_uses)
        return kwargs

    try:
        promo = await asyncio.to_thread(_do)
        return promo.id, None
    except Exception as e:
        logger.exception("Stripe promo create failed")
        return None, f"Stripe error: {e}"


async def _set_stripe_promo_active(promo_id: str, active: bool):
    s = _stripe()
    if not s or not promo_id:
        return
    try:
        await asyncio.to_thread(lambda: s.PromotionCode.modify(promo_id, active=active))
    except Exception:
        logger.exception("Stripe promo toggle failed")


async def _stripe_redemptions(promo_id: str) -> Optional[int]:
    s = _stripe()
    if not s or not promo_id:
        return None
    try:
        p = await asyncio.to_thread(lambda: s.PromotionCode.retrieve(promo_id))
        return int(p.times_redeemed or 0)
    except Exception:
        return None


# ── Models ────────────────────────────────────────────────────────────────

class GuideSubscribe(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    name: str = Field(default="", max_length=100)


class FunnelStepPatch(BaseModel):
    enabled: Optional[bool] = None
    delay_days: Optional[int] = Field(default=None, ge=0, le=60)
    code: Optional[str] = Field(default=None, max_length=40)
    percent: Optional[int] = Field(default=None, ge=1, le=90)
    price: Optional[float] = Field(default=None, ge=1, le=500)
    link: Optional[str] = Field(default=None, max_length=400)


class FunnelConfigPut(BaseModel):
    enabled: Optional[bool] = None
    steps: Optional[dict[str, FunnelStepPatch]] = None


class DiscountCodeCreate(BaseModel):
    code: str = Field(min_length=3, max_length=40)
    percent: int = Field(ge=1, le=90)
    applies_to: str = Field(default="both", pattern="^(report|subscription|both)$")
    expires_at: Optional[str] = None
    max_uses: Optional[int] = Field(default=None, ge=1, le=100000)


# ── Router ────────────────────────────────────────────────────────────────

def build_growth_funnel_router(*, db: Any, admin_dep: Any, get_single_price):
    router = APIRouter(tags=["growth-funnel"])

    # ---- public: guide lead magnet ----
    @router.post("/guide/subscribe")
    async def guide_subscribe(payload: GuideSubscribe):
        email = payload.email.strip().lower()
        if not EMAIL_RE.match(email):
            raise HTTPException(400, "Please enter a valid email address")
        first = payload.name.strip().split(" ")[0] if payload.name.strip() else None
        lead = await db.guide_leads.find_one({"email": email})
        if lead:
            if not lead.get("unsubscribed"):
                html, text, subject = render_guide_delivery_email(first or lead.get("name"), _pdf_url(), _unsub_url(lead["id"]))
                asyncio.create_task(send_email_async(email, subject, html, text))
            return {"ok": True, "already": True}
        lead = {
            "id": str(uuid.uuid4()),
            "email": email,
            "name": payload.name.strip() or None,
            "source": "guide",
            "unsubscribed": False,
            "sent": {"guide": _now_iso()},
            "created_at": _now_iso(),
        }
        await db.guide_leads.insert_one(lead)
        html, text, subject = render_guide_delivery_email(first, _pdf_url(), _unsub_url(lead["id"]))
        asyncio.create_task(send_email_async(email, subject, html, text))
        return {"ok": True}

    @router.get("/guide/pdf")
    async def guide_pdf():
        path = await asyncio.to_thread(build_guide_pdf)
        return FileResponse(str(path), media_type="application/pdf",
                            filename="ScoutMePlay-The-5-Things-Every-Football-Parent-Gets-Wrong.pdf")

    @router.get("/guide/unsubscribe/{lead_id}")
    async def guide_unsubscribe(lead_id: str):
        await db.guide_leads.update_one({"id": lead_id}, {"$set": {"unsubscribed": True}})
        return HTMLResponse("""<html><body style="font-family:Arial;background:#F5F1E8;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
        <div style="text-align:center;"><h2 style="color:#1F4F2F;">You're unsubscribed 👋</h2>
        <p style="color:#555;">No more guide emails from us. The guide is still yours to keep.</p></div></body></html>""")

    # ---- admin: leads ----
    @router.get("/admin/guide/leads")
    async def admin_leads(_=Depends(admin_dep)):
        items = []
        async for d in db.guide_leads.find({}, {"_id": 0}).sort("created_at", -1).limit(500):
            items.append(d)
        return {"total": await db.guide_leads.count_documents({}), "items": items}

    @router.delete("/admin/guide/leads/{lead_id}")
    async def admin_lead_delete(lead_id: str, _=Depends(admin_dep)):
        res = await db.guide_leads.delete_one({"id": lead_id})
        return {"ok": True, "deleted": res.deleted_count}

    # ---- admin: funnel config ----
    @router.get("/admin/guide/funnel")
    async def funnel_get(_=Depends(admin_dep)):
        return await get_funnel_config(db)

    @router.put("/admin/guide/funnel")
    async def funnel_put(payload: FunnelConfigPut, _=Depends(admin_dep)):
        cfg = await get_funnel_config(db)
        if payload.enabled is not None:
            cfg["enabled"] = payload.enabled
        for sid, patch in (payload.steps or {}).items():
            if sid not in cfg["steps"]:
                continue
            for k, v in patch.model_dump(exclude_none=True).items():
                cfg["steps"][sid][k] = v.strip().upper() if k == "code" and isinstance(v, str) else v
        await db.settings.update_one({"key": "guide_funnel"}, {"$set": {"enabled": cfg["enabled"], "steps": cfg["steps"]}}, upsert=True)
        return cfg

    # ---- admin: discount codes ----
    @router.post("/admin/discount-codes")
    async def code_create(payload: DiscountCodeCreate, _=Depends(admin_dep)):
        code = re.sub(r"[^A-Z0-9]", "", payload.code.upper())
        if len(code) < 3:
            raise HTTPException(400, "Code must be at least 3 letters/numbers")
        if await db.discount_codes.find_one({"code": code}):
            raise HTTPException(409, "That code already exists")
        promo_id, warn = await _create_stripe_promo(code, payload.percent, payload.expires_at, payload.max_uses)
        doc = {
            "id": str(uuid.uuid4()),
            "code": code,
            "percent": payload.percent,
            "applies_to": payload.applies_to,
            "expires_at": payload.expires_at,
            "max_uses": payload.max_uses,
            "active": True,
            "stripe_promo_id": promo_id,
            "created_at": _now_iso(),
        }
        await db.discount_codes.insert_one(doc)
        doc.pop("_id", None)
        return {**doc, "warning": warn}

    @router.get("/admin/discount-codes")
    async def code_list(_=Depends(admin_dep)):
        items = []
        async for d in db.discount_codes.find({}, {"_id": 0}).sort("created_at", -1).limit(100):
            items.append(d)
        for d in items[:20]:
            r = await _stripe_redemptions(d.get("stripe_promo_id"))
            if r is not None:
                d["times_redeemed"] = r
        return {"items": items}

    @router.patch("/admin/discount-codes/{code_id}")
    async def code_toggle(code_id: str, _=Depends(admin_dep)):
        doc = await db.discount_codes.find_one({"id": code_id})
        if not doc:
            raise HTTPException(404, "Code not found")
        new_active = not doc.get("active", True)
        await db.discount_codes.update_one({"id": code_id}, {"$set": {"active": new_active}})
        await _set_stripe_promo_active(doc.get("stripe_promo_id"), new_active)
        return {"ok": True, "active": new_active}

    @router.delete("/admin/discount-codes/{code_id}")
    async def code_delete(code_id: str, _=Depends(admin_dep)):
        doc = await db.discount_codes.find_one({"id": code_id})
        if doc:
            await _set_stripe_promo_active(doc.get("stripe_promo_id"), False)
        await db.discount_codes.delete_one({"id": code_id})
        return {"ok": True}

    # keep a reference for the loop
    router._get_single_price = get_single_price
    return router


# ── Funnel sweep loop ─────────────────────────────────────────────────────

async def guide_funnel_sweep(db, get_single_price, dry_run: bool = False) -> list:
    cfg = await get_funnel_config(db)
    if not cfg.get("enabled"):
        return []
    results = []
    now = _now()
    async for lead in db.guide_leads.find({"unsubscribed": {"$ne": True}}):
        created = lead.get("created_at")
        try:
            age_days = (now - datetime.fromisoformat(created)).total_seconds() / 86400
        except Exception:
            continue
        sent = lead.get("sent") or {}
        unsub = _unsub_url(lead["id"])
        first = (lead.get("name") or "").split(" ")[0] or None

        for sid, step in cfg["steps"].items():
            if not step.get("enabled") or sent.get(sid):
                continue
            if age_days < float(step.get("delay_days", 2)):
                continue
            if sid == "report_offer":
                if not step.get("code"):
                    continue
                base = float(await get_single_price())
                pct = int(step.get("percent", 20))
                new_price = round(base * (1 - pct / 100))
                html, text, subject = render_guide_report_offer_email(first, step["code"], pct, base, new_price, unsub)
            elif sid == "membership_offer":
                if not step.get("code"):
                    continue
                html, text, subject = render_guide_membership_offer_email(first, step["code"], int(step.get("percent", 20)), unsub)
            elif sid == "paid_guide":
                if not step.get("link"):
                    continue
                html, text, subject = render_guide_paid_guide_email(first, float(step.get("price", 19)), step["link"], unsub)
            else:
                continue
            results.append({"lead": lead["email"], "step": sid})
            if not dry_run:
                ok = await send_email_async(lead["email"], subject, html, text)
                if ok:
                    await db.guide_leads.update_one({"id": lead["id"]}, {"$set": {f"sent.{sid}": _now_iso()}})
    return results


async def guide_funnel_loop(db, get_single_price):
    await asyncio.sleep(180)
    while True:
        try:
            sent = await guide_funnel_sweep(db, get_single_price)
            if sent:
                logger.info("guide funnel sent %d email(s)", len(sent))
        except Exception:
            logger.exception("guide funnel loop error")
        await asyncio.sleep(3600)
