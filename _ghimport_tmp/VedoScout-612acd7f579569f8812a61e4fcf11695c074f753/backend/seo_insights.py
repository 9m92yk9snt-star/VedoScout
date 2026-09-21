"""seo_insights.py — admin SEO dashboard.
Organic traffic from first-party analytics (search-engine referrers),
per-article keyword performance, and LLM keyword suggestions."""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends

logger = logging.getLogger("seo_insights")

SEARCH_ENGINES = ("google.", "bing.", "duckduckgo.", "yahoo.", "ecosia.", "qwant.", "startpage.")


def _is_organic(ref: str) -> bool:
    r = (ref or "").lower()
    return any(se in r for se in SEARCH_ENGINES)


def build_seo_insights_router(db, admin_dep):
    router = APIRouter()

    @router.get("/admin/seo/insights")
    async def seo_insights(days: int = 30, _admin=Depends(admin_dep)):
        days = min(max(days, 7), 90)
        since = datetime.now(timezone.utc) - timedelta(days=days)

        total_sessions = len(await db.analytics_events.distinct(
            "sid", {"type": "pageview", "ts": {"$gte": since}}))

        organic_sids: set = set()
        daily: dict = {}
        landing: dict = {}
        cur = db.analytics_events.find(
            {"type": "pageview", "ts": {"$gte": since}, "referrer": {"$exists": True}},
            {"_id": 0, "sid": 1, "path": 1, "referrer": 1, "ts": 1},
        ).sort("ts", 1)
        async for d in cur:
            if not _is_organic(d.get("referrer")):
                continue
            sid = d.get("sid")
            if sid in organic_sids:
                continue
            organic_sids.add(sid)
            day = d["ts"].strftime("%Y-%m-%d") if hasattr(d.get("ts"), "strftime") else str(d.get("ts"))[:10]
            daily[day] = daily.get(day, 0) + 1
            path = d.get("path") or "/"
            landing[path] = landing.get(path, 0) + 1

        articles = []
        async for p in db.blog_posts.find(
            {"status": "published"},
            {"_id": 0, "title": 1, "slug": 1, "view_count": 1, "meta_keywords": 1,
             "category": 1, "published_at": 1},
        ).sort("view_count", -1).limit(50):
            articles.append({
                "title": p.get("title"),
                "slug": p.get("slug"),
                "views": int(p.get("view_count") or 0),
                "keywords": p.get("meta_keywords") or [],
                "category": p.get("category"),
                "published_at": p.get("published_at"),
            })

        sugg_doc = await db.settings.find_one({"key": "seo_keyword_suggestions"}, {"_id": 0})
        return {
            "days": days,
            "organic_sessions": len(organic_sids),
            "total_sessions": total_sessions,
            "organic_share_pct": round(len(organic_sids) / total_sessions * 100, 1) if total_sessions else 0.0,
            "daily": [{"day": k, "sessions": v} for k, v in sorted(daily.items())],
            "top_landing": sorted(
                [{"path": k, "sessions": v} for k, v in landing.items()],
                key=lambda x: -x["sessions"])[:10],
            "articles": articles,
            "suggestions": (sugg_doc or {}).get("value") or [],
            "suggestions_generated_at": (sugg_doc or {}).get("generated_at"),
        }

    @router.post("/admin/seo/keyword-suggestions")
    async def keyword_suggestions(_admin=Depends(admin_dep)):
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        existing = []
        async for p in db.blog_posts.find({}, {"_id": 0, "title": 1, "meta_keywords": 1}).limit(60):
            existing.append(f"- {p.get('title')} (keywords: {', '.join(p.get('meta_keywords') or [])})")

        prompt = f"""You are an SEO strategist for ScoutMePlay — video-based football reports for ambitious U7–U21 players and their families.

Existing journal articles:
{chr(10).join(existing) or '- (none)'}

Suggest 8 NEW primary keywords/topics that families and young players actually search on Google, that we do NOT already cover.
Mix parent-searches and player-searches. Realistic long-tail beats vanity volume.
Never use the standalone word "AI" and never "percentile".

Return ONLY a JSON array, no markdown fences, of objects:
[{{"keyword": "...", "audience": "parents|players|both", "intent": "one short line on why people search it", "interest": "high|medium|low (your honest estimate — not measured data)", "article_idea": "one-line article angle"}}]"""

        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=f"seo-kw-{uuid.uuid4().hex[:8]}",
            system_message="You are a precise SEO strategist. You return raw JSON only.",
        ).with_model("openai", "gpt-5.4")
        resp = await chat.send_message(UserMessage(text=prompt))
        text = resp if isinstance(resp, str) else getattr(resp, "text", None) or str(resp)
        m = re.search(r"\[.*\]", text, re.S)
        if not m:
            return {"suggestions": [], "error": "Could not parse suggestions — try again"}
        try:
            items = json.loads(m.group(0))[:10]
        except Exception:
            return {"suggestions": [], "error": "Could not parse suggestions — try again"}
        now = datetime.now(timezone.utc).isoformat()
        await db.settings.update_one(
            {"key": "seo_keyword_suggestions"},
            {"$set": {"key": "seo_keyword_suggestions", "value": items, "generated_at": now}},
            upsert=True,
        )
        return {"suggestions": items, "generated_at": now}

    return router
