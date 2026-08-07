"""Blog Studio — warm-tone article generator (draft or instant publish) + weekly auto-draft loop.
Every generated article also gets a photorealistic cover image (Gemini image model)
in the same style as the launch covers."""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from blog_routes import UPLOAD_DIR, now_iso, slugify, make_excerpt, reading_time_min

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

COVER_STYLE = (
    "Photorealistic editorial photograph for a youth football journal. "
    "Grassroots football setting, warm golden-hour natural light, shallow depth of field, "
    "authentic candid documentary feel — real kids, parents or coaches on real local pitches, "
    "muddy boots, worn goals, sideline moments. Landscape composition. "
    "Absolutely no text, no lettering, no logos, no watermarks in the image."
)


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


async def _generate_cover(slug: str, title: str, category: str) -> str | None:
    """Generates a style-matched cover photo. Returns the public URL or None.
    Never raises — a missing cover must not block the article."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from PIL import Image

        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=f"blog-cover-{uuid.uuid4().hex[:8]}",
            system_message="You generate photorealistic images.",
        )
        chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
        msg = UserMessage(
            text=f"{COVER_STYLE}\n\nArticle title: \"{title}\" (category: {category}). "
                 "Create ONE cover photograph that captures the article's emotional core."
        )
        _text, images = await chat.send_message_multimodal_response(msg)
        if not images:
            logger.warning("cover generation returned no image for %s", slug)
            return None

        raw = base64.b64decode(images[0]["data"])
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        if img.width > 1600:
            img = img.resize((1600, int(img.height * 1600 / img.width)), Image.LANCZOS)
        fname = f"gen-cover-{slug[:60]}.jpg"
        out_path = UPLOAD_DIR / fname
        img.save(out_path, "JPEG", quality=86)
        url = f"/api/blog/uploads/{fname}"

        # Flush to R2 so the cover survives redeploys (uploads/ dir is ephemeral).
        try:
            import r2_storage
            if r2_storage.is_configured():
                await asyncio.to_thread(r2_storage.upload_file, f"blog/{fname}", out_path, "image/jpeg")
                url = f"/api/media/blog/{fname}"
        except Exception:
            logger.warning("blog cover R2 flush failed for %s (using local URL)", fname, exc_info=True)
        return url
    except Exception:
        logger.exception("cover generation failed for %s", slug)
        return None


async def _generate_article(db: Any, topic: str = "", keyword: str = "", publish: bool = False) -> dict:
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

    cover_url = await _generate_cover(slug, title, category)

    doc = {
        "id": str(uuid.uuid4()),
        "slug": slug,
        "title": title,
        "subtitle": grab("SUBTITLE") or None,
        "content_md": body_md,
        "excerpt": excerpt,
        "cover_image_url": cover_url,
        "cover_image_alt": title,
        "category": category,
        "tags": keywords[:4],
        "author_name": "ScoutMePlay Editorial",
        "status": "published" if publish else "draft",
        "published_at": now if publish else None,
        "meta_title": (grab("META_TITLE") or title)[:70],
        "meta_description": (grab("META_DESCRIPTION") or excerpt)[:160],
        "meta_keywords": keywords,
        "reading_time_minutes": reading_time_min(body_md),
        "view_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    await db.blog_posts.insert_one(doc)
    return {"post_id": doc["id"], "slug": slug, "title": title, "category": category,
            "status": doc["status"], "cover_image_url": cover_url}


class GenerateRequest(BaseModel):
    topic: str = Field(default="", max_length=200)
    keyword: str = Field(default="", max_length=100)
    publish_now: bool = False


class StudioConfig(BaseModel):
    auto_weekly: bool = False


def build_blog_studio_router(*, db: Any, admin_dep: Any):
    router = APIRouter(prefix="/blog-studio", tags=["blog-studio"])

    async def _run_job(job_id: str, topic: str, keyword: str, publish: bool):
        try:
            result = await _generate_article(db, topic, keyword, publish=publish)
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
        job = {"id": str(uuid.uuid4()), "status": "running", "topic": payload.topic,
               "keyword": payload.keyword, "publish_now": payload.publish_now, "created_at": now_iso()}
        await db.blog_studio_jobs.insert_one(job)
        asyncio.create_task(_run_job(job["id"], payload.topic, payload.keyword, payload.publish_now))
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
