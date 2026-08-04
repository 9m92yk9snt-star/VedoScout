"""Blog Studio — warm-tone article generator (creates DRAFTS) + weekly auto-draft loop."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from blog_routes import now_iso, slugify, make_excerpt, reading_time_min

load_dotenv()
logger = logging.getLogger("blog_studio")

CATEGORIES = ("Training", "Scouting Tips", "Parent's Guide", "Pro Player Path")

SYSTEM_PROMPT = """You are the editorial voice of ScoutMePlay — a football platform for ambitious U7–U21 players and their families.

Voice rules (non-negotiable):
- Warm, human, honest. You write like a person who loves football and cares about kids, not like a marketer.
- Sell dreams responsibly: hope and realism together. NEVER promise professional contracts, academy places or guaranteed exposure.
- NEVER use the standalone word "AI". Never use the word "percentile". If you reference the product's analysis, call it "ScoutMe Pro Intelligence" or simply "the report".
- Practical over abstract: give parents and players things they can actually do this week.
- Short paragraphs. Concrete examples. British-neutral English."""


def _user_prompt(topic: str, keyword: str, existing: list) -> str:
    titles = "\n".join(f"- {t} (/blog/{s})" for t, s in existing) or "- (none yet)"
    topic_line = (
        f'Topic: "{topic}"' if topic.strip()
        else "Choose ONE fresh, search-relevant topic families actually google, NOT covered by the existing articles below."
    )
    kw_line = f'Primary SEO keyword: "{keyword}"' if keyword.strip() else "Choose a realistic primary SEO keyword for the topic."
    return f"""Write one complete blog article for the ScoutMePlay journal.

{topic_line}
{kw_line}

Existing articles (do not duplicate; link to 1-2 of them naturally where relevant):
{titles}

Requirements:
- 900–1200 words of markdown body with ## and ### headings, lists where helpful.
- Weave the primary keyword naturally into the first 100 words, one heading, and the conclusion.
- Include 1-2 natural internal links to [upload a match video](/upload) and/or [our methodology](/methodology), plus links to relevant existing articles.
- End with a gentle, warm call to action (never pushy).

Return EXACTLY this format (labels included, then --- on its own line, then the markdown body):
TITLE: <article title, max 65 chars, no brand name>
SUBTITLE: <one warm sentence>
META_TITLE: <max 65 chars>
META_DESCRIPTION: <max 155 chars>
KEYWORDS: <5 comma-separated keywords>
CATEGORY: <one of: Training | Scouting Tips | Parent's Guide | Pro Player Path>
---
<markdown body>"""


async def _generate_article(db: Any, topic: str = "", keyword: str = "") -> dict:
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    existing = []
    async for d in db.blog_posts.find({}, {"title": 1, "slug": 1}).sort("created_at", -1).limit(40):
        existing.append((d.get("title") or "", d.get("slug") or ""))

    chat = LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=f"blog-studio-{uuid.uuid4().hex[:10]}",
        system_message=SYSTEM_PROMPT,
    ).with_model("openai", "gpt-5.4")

    resp = await chat.send_message(UserMessage(text=_user_prompt(topic, keyword, existing)))
    text = resp if isinstance(resp, str) else getattr(resp, "text", None) or str(resp)

    head, sep, body = text.partition("\n---")
    if not sep:
        head, sep, body = text.partition("---")

    def grab(label: str) -> str:
        m = re.search(rf"^{label}:\s*(.+)$", head, re.M)
        return m.group(1).strip() if m else ""

    title = grab("TITLE") or (topic.strip() or "A new story from the journal")
    category = grab("CATEGORY")
    if category not in CATEGORIES:
        category = "Parent's Guide"
    keywords = [k.strip() for k in grab("KEYWORDS").split(",") if k.strip()][:6]
    body_md = body.strip().lstrip("-").strip()
    if len(body_md) < 400:
        raise ValueError("Generated article was too short — please try again")

    slug = f"{slugify(title)[:70]}-{uuid.uuid4().hex[:4]}"
    now = now_iso()
    excerpt = make_excerpt(body_md)
    doc = {
        "id": str(uuid.uuid4()),
        "slug": slug,
        "title": title,
        "subtitle": grab("SUBTITLE") or None,
        "content_md": body_md,
        "excerpt": excerpt,
        "cover_image_url": None,
        "cover_image_alt": title,
        "category": category,
        "tags": keywords[:4],
        "author_name": "ScoutMePlay Editorial",
        "status": "draft",
        "published_at": None,
        "meta_title": (grab("META_TITLE") or title)[:70],
        "meta_description": (grab("META_DESCRIPTION") or excerpt)[:160],
        "meta_keywords": keywords,
        "reading_time_minutes": reading_time_min(body_md),
        "view_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    await db.blog_posts.insert_one(doc)
    return {"post_id": doc["id"], "slug": slug, "title": title, "category": category}


class GenerateRequest(BaseModel):
    topic: str = Field(default="", max_length=200)
    keyword: str = Field(default="", max_length=100)


class StudioConfig(BaseModel):
    auto_weekly: bool = False


def build_blog_studio_router(*, db: Any, admin_dep: Any):
    router = APIRouter(prefix="/blog-studio", tags=["blog-studio"])

    async def _run_job(job_id: str, topic: str, keyword: str):
        try:
            result = await _generate_article(db, topic, keyword)
            await db.blog_studio_jobs.update_one(
                {"id": job_id},
                {"$set": {"status": "done", **result, "finished_at": now_iso()}},
            )
        except Exception as e:
            logger.exception("blog studio job failed")
            await db.blog_studio_jobs.update_one(
                {"id": job_id},
                {"$set": {"status": "failed", "error": str(e)[:400], "finished_at": now_iso()}},
            )

    @router.post("/generate")
    async def generate(payload: GenerateRequest, _=Depends(admin_dep)):
        job = {"id": str(uuid.uuid4()), "status": "running", "topic": payload.topic, "keyword": payload.keyword, "created_at": now_iso()}
        await db.blog_studio_jobs.insert_one(job)
        asyncio.create_task(_run_job(job["id"], payload.topic, payload.keyword))
        return {"job_id": job["id"], "status": "running"}

    @router.get("/jobs")
    async def jobs(_=Depends(admin_dep)):
        items = []
        async for d in db.blog_studio_jobs.find({}, {"_id": 0}).sort("created_at", -1).limit(6):
            items.append(d)
        return {"items": items}

    @router.get("/config")
    async def get_config(_=Depends(admin_dep)):
        doc = await db.settings.find_one({"key": "blog_studio"}) or {}
        return {"auto_weekly": bool(doc.get("auto_weekly")), "last_auto_at": doc.get("last_auto_at")}

    @router.put("/config")
    async def put_config(payload: StudioConfig, _=Depends(admin_dep)):
        await db.settings.update_one({"key": "blog_studio"}, {"$set": {"auto_weekly": payload.auto_weekly}}, upsert=True)
        return {"ok": True}

    return router


async def blog_studio_weekly_loop(db: Any):
    """Once a week (when enabled) auto-generate a fresh DRAFT article for admin review."""
    await asyncio.sleep(120)
    while True:
        try:
            cfg = await db.settings.find_one({"key": "blog_studio"}) or {}
            if cfg.get("auto_weekly"):
                last = cfg.get("last_auto_at")
                due = True
                if last:
                    try:
                        due = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).days >= 7
                    except Exception:
                        due = True
                if due:
                    result = await _generate_article(db)
                    await db.settings.update_one(
                        {"key": "blog_studio"},
                        {"$set": {"last_auto_at": datetime.now(timezone.utc).isoformat()}},
                        upsert=True,
                    )
                    logger.info("blog studio weekly draft created: %s", result.get("slug"))
        except Exception:
            logger.exception("blog studio weekly loop error")
        await asyncio.sleep(3600)
