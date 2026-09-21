"""analytics_tracking.py — first-party, cookie-less site analytics.

GDPR-light by design:
- anonymous per-session id (sessionStorage, dies with the browser session)
- NO cookies, NO IP addresses, NO fingerprinting, NO third parties
- events auto-expire after 180 days (TTL index)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

logger = logging.getLogger("analytics")

MAX_EVENTS_PER_BATCH = 25
VALID_TYPES = {"pageview", "leave", "click", "funnel"}
FUNNEL_EVENT_STEPS = [
    ("upload_started", "Upload started"),
    ("player_tapped", "Player tapped"),
    ("analysis_submitted", "Analysis submitted"),
    ("preview_viewed", "Preview viewed"),
    ("checkout_started", "Checkout started"),
]
UTM_KEYS = ("source", "medium", "campaign", "content")


class TrackEvent(BaseModel):
    type: str
    path: Optional[str] = None
    name: Optional[str] = None
    seconds: Optional[float] = None
    scroll: Optional[float] = None
    referrer: Optional[str] = None
    utm: Optional[dict] = None


class TrackBatch(BaseModel):
    sid: str = Field(min_length=8, max_length=64)
    device: Optional[str] = None
    events: List[TrackEvent] = Field(default_factory=list)


def build_analytics_router(db, admin_dep):
    router = APIRouter()
    indexes_done = {"ok": False}

    async def _ensure_indexes():
        if indexes_done["ok"]:
            return
        try:
            await db.analytics_events.create_index("ts", expireAfterSeconds=180 * 24 * 3600)
            await db.analytics_events.create_index([("type", 1), ("ts", -1)])
            await db.analytics_events.create_index([("sid", 1), ("ts", 1)])
            indexes_done["ok"] = True
        except Exception as e:
            logger.warning(f"analytics index creation failed: {e}")

    # ── PUBLIC collector ──
    @router.post("/track")
    async def track(batch: TrackBatch):
        await _ensure_indexes()
        now = datetime.now(timezone.utc)
        device = (batch.device or "").strip()[:20] or None
        docs = []
        for e in batch.events[:MAX_EVENTS_PER_BATCH]:
            if e.type not in VALID_TYPES:
                continue
            path = (e.path or "").strip()[:200]
            if path.startswith("/admin"):
                continue  # never track admin usage
            d = {"sid": batch.sid[:64], "type": e.type, "path": path, "ts": now, "device": device}
            if e.name:
                d["name"] = str(e.name)[:80]
            if e.type == "leave":
                if isinstance(e.seconds, (int, float)):
                    d["seconds"] = max(0.0, min(float(e.seconds), 3600.0))
                if isinstance(e.scroll, (int, float)):
                    d["scroll"] = max(0.0, min(float(e.scroll), 100.0))
            if e.type == "pageview":
                ref = (e.referrer or "").strip()[:200]
                if ref:
                    d["referrer"] = ref
                if isinstance(e.utm, dict):
                    utm = {k: str(v)[:80] for k, v in e.utm.items() if k in UTM_KEYS and v}
                    if utm:
                        d["utm"] = utm
            docs.append(d)
        if docs:
            try:
                await db.analytics_events.insert_many(docs)
            except Exception as e:
                logger.warning(f"analytics insert failed: {e}")
        return {"ok": True, "stored": len(docs)}

    # ── ADMIN overview ──
    @router.get("/admin/analytics/overview")
    async def analytics_overview(days: int = 30, _admin=Depends(admin_dep)):
        days = max(1, min(days, 180))
        since = datetime.now(timezone.utc) - timedelta(days=days)
        since_iso = since.isoformat()
        ev = db.analytics_events

        async def _unique_sids(match: dict) -> int:
            pipe = [{"$match": match}, {"$group": {"_id": "$sid"}}, {"$count": "n"}]
            r = await ev.aggregate(pipe).to_list(1)
            return r[0]["n"] if r else 0

        # daily series -------------------------------------------------------
        daily: dict = {}

        def _day_bucket(iso_day: str) -> dict:
            return daily.setdefault(iso_day, {"date": iso_day, "visitors": 0, "pageviews": 0, "signups": 0, "paid": 0})

        rows = await ev.aggregate([
            {"$match": {"type": "pageview", "ts": {"$gte": since}}},
            {"$group": {"_id": {"d": {"$dateToString": {"format": "%Y-%m-%d", "date": "$ts"}}, "sid": "$sid"}, "views": {"$sum": 1}}},
            {"$group": {"_id": "$_id.d", "visitors": {"$sum": 1}, "pageviews": {"$sum": "$views"}}},
        ]).to_list(200)
        for r in rows:
            b = _day_bucket(r["_id"])
            b["visitors"] = r["visitors"]
            b["pageviews"] = r["pageviews"]

        async for u in db.users.find({"created_at": {"$gte": since_iso}}, {"created_at": 1}):
            _day_bucket(str(u["created_at"])[:10])["signups"] += 1
        async for t in db.payment_transactions.find(
                {"payment_status": "paid", "created_at": {"$gte": since_iso}}, {"created_at": 1}):
            _day_bucket(str(t["created_at"])[:10])["paid"] += 1

        # fill missing days so the chart has a continuous axis
        for i in range(days):
            d = (since + timedelta(days=i + 1)).strftime("%Y-%m-%d")
            _day_bucket(d)
        series = sorted(daily.values(), key=lambda x: x["date"])[-days:]

        # funnel ---------------------------------------------------------------
        visitors = await _unique_sids({"type": "pageview", "ts": {"$gte": since}})
        signups = await db.users.count_documents({"created_at": {"$gte": since_iso}})
        funnel = [{"step": "Visitors", "count": visitors, "source": "sessions"},
                  {"step": "Signups", "count": signups, "source": "accounts"}]
        for key, label in FUNNEL_EVENT_STEPS:
            n = await _unique_sids({"type": "funnel", "name": key, "ts": {"$gte": since}})
            funnel.append({"step": label, "count": n, "source": "sessions"})
        paid = await db.payment_transactions.count_documents(
            {"payment_status": "paid", "created_at": {"$gte": since_iso}})
        funnel.append({"step": "Paid", "count": paid, "source": "transactions"})
        prev = None
        for f in funnel:
            f["pct_of_prev"] = round(f["count"] / prev * 100, 1) if prev else None
            prev = f["count"] or None

        # top pages + dwell/scroll --------------------------------------------
        pages = await ev.aggregate([
            {"$match": {"type": "pageview", "ts": {"$gte": since}}},
            {"$group": {"_id": "$path", "views": {"$sum": 1}}},
            {"$sort": {"views": -1}}, {"$limit": 12},
        ]).to_list(12)
        dwell = await ev.aggregate([
            {"$match": {"type": "leave", "ts": {"$gte": since}}},
            {"$group": {"_id": "$path", "avg_seconds": {"$avg": "$seconds"}, "avg_scroll": {"$avg": "$scroll"}}},
        ]).to_list(200)
        dwell_map = {d["_id"]: d for d in dwell}
        top_pages = [{
            "path": p["_id"] or "/",
            "views": p["views"],
            "avg_seconds": round((dwell_map.get(p["_id"], {}).get("avg_seconds") or 0), 1),
            "avg_scroll": round((dwell_map.get(p["_id"], {}).get("avg_scroll") or 0), 0),
        } for p in pages]

        # exit pages (last pageview per session) --------------------------------
        exits = await ev.aggregate([
            {"$match": {"type": "pageview", "ts": {"$gte": since}}},
            {"$sort": {"ts": 1}},
            {"$group": {"_id": "$sid", "last_path": {"$last": "$path"}}},
            {"$group": {"_id": "$last_path", "exits": {"$sum": 1}}},
            {"$sort": {"exits": -1}}, {"$limit": 10},
        ]).to_list(10)
        exit_pages = [{"path": e["_id"] or "/", "exits": e["exits"]} for e in exits]

        # CTA clicks -------------------------------------------------------------
        clicks = await ev.aggregate([
            {"$match": {"type": "click", "ts": {"$gte": since}, "name": {"$ne": None}}},
            {"$group": {"_id": "$name", "clicks": {"$sum": 1}}},
            {"$sort": {"clicks": -1}}, {"$limit": 15},
        ]).to_list(15)
        top_clicks = [{"name": c["_id"], "clicks": c["clicks"]} for c in clicks]

        # campaigns (UTM) ----------------------------------------------------------
        camps = await ev.aggregate([
            {"$match": {"type": "pageview", "ts": {"$gte": since}, "utm": {"$exists": True}}},
            {"$group": {"_id": {"s": "$utm.source", "c": "$utm.campaign", "sid": "$sid"}}},
            {"$group": {"_id": {"s": "$_id.s", "c": "$_id.c"}, "sessions": {"$sum": 1}}},
            {"$sort": {"sessions": -1}}, {"$limit": 10},
        ]).to_list(10)
        campaigns = [{"source": c["_id"].get("s") or "—", "campaign": c["_id"].get("c") or "—",
                      "sessions": c["sessions"]} for c in camps]

        # devices --------------------------------------------------------------------
        devs = await ev.aggregate([
            {"$match": {"type": "pageview", "ts": {"$gte": since}}},
            {"$group": {"_id": {"d": "$device", "sid": "$sid"}}},
            {"$group": {"_id": "$_id.d", "sessions": {"$sum": 1}}},
        ]).to_list(10)
        devices = [{"device": d["_id"] or "unknown", "sessions": d["sessions"]} for d in devs]

        # blog -------------------------------------------------------------------------
        blog = [p for p in top_pages if str(p["path"]).startswith("/blog")][:8]
        landing = dwell_map.get("/", {})

        return {
            "days": days,
            "series": series,
            "funnel": funnel,
            "top_pages": top_pages,
            "exit_pages": exit_pages,
            "top_clicks": top_clicks,
            "campaigns": campaigns,
            "devices": devices,
            "blog_pages": blog,
            "landing_avg_scroll": round(landing.get("avg_scroll") or 0),
            "landing_avg_seconds": round(landing.get("avg_seconds") or 0, 1),
        }

    return router
