"""
Blog routes for ScoutMePlay.

Self-contained module — no imports from server.py to avoid circular deps.
Call `build_blog_router(...)` from server.py and include the returned router.

Features
--------
- Public: list/get posts (only published), list categories, sitemap helper data
- Admin: create/update/delete/publish posts, image upload, manage categories
- AI: draft an article from a topic, suggest SEO meta (title/description/keywords)
"""

from __future__ import annotations

import os
import re
import uuid
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────────────
# Constants & helpers
# ──────────────────────────────────────────────────────────────────────────────

BLOG_POSTS = "blog_posts"
BLOG_CATEGORIES = "blog_categories"

UPLOAD_DIR = Path(os.environ.get("BLOG_UPLOAD_DIR", "/app/backend/uploads/blog"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB

SLUG_RE = re.compile(r"[^a-z0-9]+")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(text: str) -> str:
    text = (text or "").lower().strip()
    text = SLUG_RE.sub("-", text).strip("-")
    return text[:80] or f"post-{uuid.uuid4().hex[:8]}"


def word_count_markdown(md: str) -> int:
    if not md:
        return 0
    # crude: strip markdown headers/syntax then count words
    cleaned = re.sub(r"[#*_>`\[\]\(\)!]", " ", md)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return len([w for w in cleaned.split() if w.strip()])


def reading_time_min(md: str) -> int:
    return max(1, math.ceil(word_count_markdown(md) / 200))


def make_excerpt(md: str, max_chars: int = 220) -> str:
    if not md:
        return ""
    # Strip markdown headers, links, images, formatting
    text = re.sub(r"!\[.*?\]\(.*?\)", "", md)            # images
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)      # links → text
    text = re.sub(r"[#>*_`~]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rsplit(" ", 1)[0] + "…"


def public_post(doc: dict) -> dict:
    """Sanitize a Mongo doc for the public API response."""
    if not doc:
        return {}
    out = dict(doc)
    out.pop("_id", None)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic models (request schemas)
# ──────────────────────────────────────────────────────────────────────────────


class PostCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    subtitle: Optional[str] = None
    slug: Optional[str] = None
    content_md: str = ""
    excerpt: Optional[str] = None
    cover_image_url: Optional[str] = None
    cover_image_alt: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    author_name: Optional[str] = None
    status: str = "draft"  # draft | published
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: List[str] = Field(default_factory=list)


class PostUpdate(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    slug: Optional[str] = None
    content_md: Optional[str] = None
    excerpt: Optional[str] = None
    cover_image_url: Optional[str] = None
    cover_image_alt: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    author_name: Optional[str] = None
    status: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[List[str]] = None


class CategoryCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = "#1F4F2F"


class AIDraftRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    tone: Optional[str] = "informative, parent-friendly, no AI hype"
    length: Optional[str] = "700-1000 words"
    target_keyword: Optional[str] = None


class AISEORequest(BaseModel):
    title: str
    content_md: str


class AISeriesRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    count: int = Field(default=5, ge=3, le=10)
    audience: Optional[str] = "parents and ambitious young footballers U7–U21"


class SeriesItem(BaseModel):
    title: str
    brief: Optional[str] = ""
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    primary_keyword: Optional[str] = ""
    meta_title: Optional[str] = ""
    meta_description: Optional[str] = ""


class SeriesBulkSaveRequest(BaseModel):
    topic: str
    items: List[SeriesItem]


# ──────────────────────────────────────────────────────────────────────────────
# Router builder
# ──────────────────────────────────────────────────────────────────────────────


DEFAULT_CATEGORIES = [
    {"name": "Training", "slug": "training", "color": "#1F4F2F",
     "description": "Drills, periodisation and on-field skill development."},
    {"name": "Scouting Tips", "slug": "scouting-tips", "color": "#2D6B3D",
     "description": "How scouts and academies actually evaluate young players."},
    {"name": "Parent's Guide", "slug": "parents-guide", "color": "#4F6B30",
     "description": "Practical advice for parents supporting a football dream."},
    {"name": "Pro Player Path", "slug": "pro-player-path", "color": "#374B22",
     "description": "Inside the academy → professional journey."},
    {"name": "Reports & Analysis", "slug": "reports-analysis", "color": "#16331F",
     "description": "Sample reports, methodology, and case studies."},
]


def build_blog_router(
    *,
    db: Any,
    get_current_admin,
    get_current_user,
    call_gemini_text,
):
    """Build & return the blog APIRouter wired to the host app's dependencies."""

    router = APIRouter(prefix="/blog", tags=["blog"])

    # ── Seed default categories on first use ─────────────────────────────────
    async def ensure_categories():
        existing = await db[BLOG_CATEGORIES].count_documents({})
        if existing == 0:
            now = now_iso()
            await db[BLOG_CATEGORIES].insert_many([
                {**c, "id": str(uuid.uuid4()), "created_at": now}
                for c in DEFAULT_CATEGORIES
            ])

    # ── Slug uniqueness ──────────────────────────────────────────────────────
    async def unique_slug(base: str, exclude_id: Optional[str] = None) -> str:
        slug = slugify(base)
        attempt = slug
        i = 2
        while True:
            q: dict = {"slug": attempt}
            if exclude_id:
                q["id"] = {"$ne": exclude_id}
            taken = await db[BLOG_POSTS].count_documents(q)
            if not taken:
                return attempt
            attempt = f"{slug}-{i}"
            i += 1

    # =========================================================================
    # PUBLIC ENDPOINTS
    # =========================================================================

    @router.get("/posts")
    async def list_published_posts(
        category: Optional[str] = Query(None, description="Category slug filter"),
        tag: Optional[str] = Query(None, description="Tag filter"),
        q: Optional[str] = Query(None, description="Full-text query in title/excerpt"),
        limit: int = Query(12, ge=1, le=50),
        offset: int = Query(0, ge=0),
    ):
        await ensure_categories()
        query: dict = {"status": "published"}
        if category:
            # Posts store the category NAME while the UI filters by slug — accept both.
            names = {category}
            cat_doc = await db[BLOG_CATEGORIES].find_one(
                {"$or": [{"slug": category}, {"name": category}]}
            )
            if cat_doc:
                names.update({cat_doc.get("name"), cat_doc.get("slug")})
            query["category"] = {"$in": [n for n in names if n]}
        if tag:
            query["tags"] = tag
        if q:
            rx = re.compile(re.escape(q), re.IGNORECASE)
            query["$or"] = [{"title": rx}, {"excerpt": rx}, {"subtitle": rx}]
        total = await db[BLOG_POSTS].count_documents(query)
        cursor = (
            db[BLOG_POSTS]
            .find(query)
            .sort("published_at", -1)
            .skip(offset)
            .limit(limit)
        )
        items = [public_post(d) async for d in cursor]
        return {"total": total, "items": items, "limit": limit, "offset": offset}

    @router.get("/posts/{slug}")
    async def get_post_by_slug(slug: str):
        doc = await db[BLOG_POSTS].find_one({"slug": slug, "status": "published"})
        if not doc:
            raise HTTPException(404, "Post not found")
        # increment view count (fire-and-forget style)
        await db[BLOG_POSTS].update_one({"id": doc["id"]}, {"$inc": {"view_count": 1}})
        doc["view_count"] = (doc.get("view_count") or 0) + 1
        # related posts: same category, exclude self, top 3 latest
        related_cursor = (
            db[BLOG_POSTS]
            .find({
                "status": "published",
                "id": {"$ne": doc["id"]},
                "$or": [{"category": doc.get("category")}, {"tags": {"$in": doc.get("tags", [])}}],
            })
            .sort("published_at", -1)
            .limit(3)
        )
        related = [public_post(d) async for d in related_cursor]
        return {"post": public_post(doc), "related": related}

    @router.get("/categories")
    async def list_categories():
        await ensure_categories()
        cursor = db[BLOG_CATEGORIES].find({}).sort("name", 1)
        return [public_post(d) async for d in cursor]

    @router.get("/_sitemap")
    async def sitemap_data():
        """Internal — returns minimal data for sitemap.xml builder in main app."""
        cursor = (
            db[BLOG_POSTS]
            .find({"status": "published"}, {"slug": 1, "updated_at": 1, "published_at": 1})
            .sort("published_at", -1)
        )
        out = []
        async for d in cursor:
            out.append({
                "slug": d.get("slug"),
                "lastmod": d.get("updated_at") or d.get("published_at"),
            })
        return out

    # =========================================================================
    # ADMIN ENDPOINTS
    # =========================================================================

    @router.get("/admin/posts", dependencies=[Depends(get_current_admin)])
    async def admin_list_all(
        status: Optional[str] = Query(None, description="draft|published; omit for all"),
    ):
        query: dict = {}
        if status:
            query["status"] = status
        cursor = db[BLOG_POSTS].find(query).sort("updated_at", -1)
        items = [public_post(d) async for d in cursor]
        return {"items": items, "total": len(items)}

    @router.get("/admin/posts/{post_id}", dependencies=[Depends(get_current_admin)])
    async def admin_get_post(post_id: str):
        doc = await db[BLOG_POSTS].find_one({"id": post_id})
        if not doc:
            raise HTTPException(404, "Post not found")
        return public_post(doc)

    @router.post("/admin/posts", dependencies=[Depends(get_current_admin)])
    async def admin_create_post(payload: PostCreate):
        if payload.status not in ("draft", "published"):
            raise HTTPException(400, "Invalid status; must be 'draft' or 'published'")
        slug = await unique_slug(payload.slug or payload.title)
        now = now_iso()
        excerpt = (payload.excerpt or make_excerpt(payload.content_md)).strip()
        meta_desc = (payload.meta_description or excerpt)[:160]
        meta_title = (payload.meta_title or payload.title)[:70]
        doc = {
            "id": str(uuid.uuid4()),
            "slug": slug,
            "title": payload.title.strip(),
            "subtitle": (payload.subtitle or "").strip() or None,
            "content_md": payload.content_md,
            "excerpt": excerpt,
            "cover_image_url": payload.cover_image_url,
            "cover_image_alt": payload.cover_image_alt or payload.title,
            "category": payload.category,
            "tags": [t.strip() for t in (payload.tags or []) if t.strip()],
            "author_name": payload.author_name or "ScoutMePlay Editorial",
            "status": payload.status,
            "published_at": now if payload.status == "published" else None,
            "meta_title": meta_title,
            "meta_description": meta_desc,
            "meta_keywords": payload.meta_keywords or [],
            "reading_time_minutes": reading_time_min(payload.content_md),
            "view_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        await db[BLOG_POSTS].insert_one(doc)
        from quality_engine import schedule_auto_qc
        schedule_auto_qc(db, "blog", doc["id"])
        return public_post(doc)

    @router.put("/admin/posts/{post_id}", dependencies=[Depends(get_current_admin)])
    async def admin_update_post(post_id: str, payload: PostUpdate):
        existing = await db[BLOG_POSTS].find_one({"id": post_id})
        if not existing:
            raise HTTPException(404, "Post not found")
        update: dict = {}
        data = payload.model_dump(exclude_unset=True)

        if "title" in data:
            update["title"] = data["title"].strip()
        if "subtitle" in data:
            update["subtitle"] = (data["subtitle"] or "").strip() or None
        if "slug" in data and data["slug"]:
            update["slug"] = await unique_slug(data["slug"], exclude_id=post_id)
        if "content_md" in data:
            update["content_md"] = data["content_md"]
            update["reading_time_minutes"] = reading_time_min(data["content_md"])
            if not data.get("excerpt"):
                update["excerpt"] = make_excerpt(data["content_md"])
        if "excerpt" in data and data["excerpt"]:
            update["excerpt"] = data["excerpt"].strip()
        if "cover_image_url" in data:
            update["cover_image_url"] = data["cover_image_url"]
        if "cover_image_alt" in data:
            update["cover_image_alt"] = data["cover_image_alt"]
        if "category" in data:
            update["category"] = data["category"]
        if "tags" in data:
            update["tags"] = [t.strip() for t in (data["tags"] or []) if t.strip()]
        if "author_name" in data:
            update["author_name"] = data["author_name"]
        if "meta_title" in data:
            update["meta_title"] = (data["meta_title"] or update.get("title") or existing["title"])[:70]
        if "meta_description" in data:
            update["meta_description"] = (data["meta_description"] or "")[:160]
        if "meta_keywords" in data:
            update["meta_keywords"] = data["meta_keywords"] or []

        if "status" in data and data["status"]:
            if data["status"] not in ("draft", "published"):
                raise HTTPException(400, "Invalid status")
            update["status"] = data["status"]
            if data["status"] == "published" and not existing.get("published_at"):
                update["published_at"] = now_iso()

        update["updated_at"] = now_iso()
        await db[BLOG_POSTS].update_one({"id": post_id}, {"$set": update})
        return public_post(await db[BLOG_POSTS].find_one({"id": post_id}))

    @router.delete("/admin/posts/{post_id}", dependencies=[Depends(get_current_admin)])
    async def admin_delete_post(post_id: str):
        res = await db[BLOG_POSTS].delete_one({"id": post_id})
        if res.deleted_count == 0:
            raise HTTPException(404, "Post not found")
        return {"ok": True}

    @router.post("/admin/categories", dependencies=[Depends(get_current_admin)])
    async def admin_create_category(payload: CategoryCreate):
        await ensure_categories()
        slug = slugify(payload.slug or payload.name)
        if await db[BLOG_CATEGORIES].find_one({"slug": slug}):
            raise HTTPException(400, "Category slug already exists")
        doc = {
            "id": str(uuid.uuid4()),
            "name": payload.name.strip(),
            "slug": slug,
            "description": payload.description or "",
            "color": payload.color or "#1F4F2F",
            "created_at": now_iso(),
        }
        await db[BLOG_CATEGORIES].insert_one(doc)
        return public_post(doc)

    # ── Image upload ─────────────────────────────────────────────────────────
    @router.post("/admin/upload-image", dependencies=[Depends(get_current_admin)])
    async def admin_upload_image(file: UploadFile = File(...)):
        if file.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(400, f"Unsupported image type: {file.content_type}")
        data = await file.read()
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(400, "Image exceeds 5 MB")
        ext = (file.filename.rsplit(".", 1)[-1] if "." in (file.filename or "") else "jpg").lower()
        ext = ext if ext in {"jpg", "jpeg", "png", "webp", "gif"} else "jpg"
        fname = f"{uuid.uuid4().hex}.{ext}"
        out_path = UPLOAD_DIR / fname
        with open(out_path, "wb") as f:
            f.write(data)
        return {"url": f"/api/blog/uploads/{fname}", "filename": fname, "size": len(data)}

    # =========================================================================
    # AI ENDPOINTS (Gemini via host app helper)
    # =========================================================================

    @router.post("/admin/ai/draft", dependencies=[Depends(get_current_admin)])
    async def ai_draft_article(payload: AIDraftRequest):
        sys_msg = (
            "You are a senior football journalist who writes for parents, young players, "
            "and academy scouts. You write practical, evidence-based articles that NEVER "
            "exaggerate, never use AI-hype language, and never invent statistics. "
            "When you need a number, prefer to write it as an estimate or refer to publicly "
            "known sources. Use Markdown with clear H2/H3 sections, bullet lists, short "
            "paragraphs, and at least one practical takeaway box quoted in '>' style."
        )
        kw_hint = f"Primary target keyword: {payload.target_keyword}\n" if payload.target_keyword else ""
        prompt = (
            f"Write a Markdown blog article on the following topic.\n\n"
            f"TOPIC: {payload.topic}\n"
            f"TONE: {payload.tone}\n"
            f"LENGTH: {payload.length}\n"
            f"{kw_hint}"
            f"\nRules:\n"
            f"- First line is the H1 title (`# Title`).\n"
            f"- Then a 1-sentence hook subtitle in italics.\n"
            f"- 4–6 H2 sections with H3 sub-points.\n"
            f"- Use markdown bullet lists and a final 'Bottom line' takeaway.\n"
            f"- No fluff intros, no 'In conclusion', no AI disclaimers.\n"
            f"- Cite NO specific statistics unless they are widely known.\n"
        )
        try:
            text = await call_gemini_text(
                session_id=f"blog-draft-{uuid.uuid4().hex[:8]}",
                prompt=prompt,
                system_message=sys_msg,
            )
        except Exception as e:
            raise HTTPException(502, f"Gemini drafting failed: {e}")

        # Best-effort extract title from first line `# ...`
        title = ""
        body = (text or "").strip()
        first_line = body.splitlines()[0] if body else ""
        m = re.match(r"^\s*#\s+(.+)$", first_line)
        if m:
            title = m.group(1).strip()
            body = "\n".join(body.splitlines()[1:]).lstrip()

        return {
            "title": title,
            "content_md": body,
            "reading_time_minutes": reading_time_min(body),
            "excerpt": make_excerpt(body),
        }

    @router.post("/admin/ai/seo", dependencies=[Depends(get_current_admin)])
    async def ai_seo_suggest(payload: AISEORequest):
        sys_msg = (
            "You are an SEO specialist. Given a blog article, return ONLY a single JSON object "
            "with these exact keys: meta_title (string, ≤60 chars, compelling and clickable), "
            "meta_description (string, ≤160 chars, with primary keyword early, action-oriented), "
            "meta_keywords (array of 5–8 lowercase short phrases). Do not include any markdown "
            "fences, comments, or prose. JSON only."
        )
        # Limit content size to keep token cost down
        snippet = (payload.content_md or "")[:4000]
        prompt = (
            f"TITLE: {payload.title}\n\nARTICLE (markdown):\n{snippet}\n\n"
            f"Return the JSON object now."
        )
        try:
            raw = await call_gemini_text(
                session_id=f"blog-seo-{uuid.uuid4().hex[:8]}",
                prompt=prompt,
                system_message=sys_msg,
            )
        except Exception as e:
            raise HTTPException(502, f"Gemini SEO call failed: {e}")

        # robust JSON extract — strip possible code fences
        import json
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.MULTILINE)
        try:
            parsed = json.loads(cleaned)
        except Exception:
            # try to find the first {...} block
            m = re.search(r"\{[\s\S]*\}", cleaned)
            if not m:
                raise HTTPException(502, "Could not parse Gemini SEO response")
            parsed = json.loads(m.group(0))

        return {
            "meta_title": (parsed.get("meta_title") or "")[:70],
            "meta_description": (parsed.get("meta_description") or "")[:160],
            "meta_keywords": [str(k).strip().lower() for k in (parsed.get("meta_keywords") or []) if str(k).strip()][:8],
        }

    # ── AI: Generate Article Series ──────────────────────────────────────────
    @router.post("/admin/ai/series", dependencies=[Depends(get_current_admin)])
    async def ai_generate_series(payload: AISeriesRequest):
        sys_msg = (
            "You are an SEO content strategist for a football scouting platform. "
            "You design evergreen article series that are sequential, interconnected, "
            "build topical authority, and target intent-rich long-tail keywords. "
            "Return ONLY a valid JSON ARRAY. No markdown fences. No prose."
        )
        valid_cats = ", ".join(c["name"] for c in DEFAULT_CATEGORIES)
        prompt = (
            f"Plan a {payload.count}-article evergreen series on the topic:\n"
            f"  \"{payload.topic}\"\n\n"
            f"Audience: {payload.audience}\n\n"
            f"Return a JSON ARRAY of exactly {payload.count} objects. Each object must have these EXACT keys:\n"
            f"  - title (string, ≤80 chars, hook-driven and clickable)\n"
            f"  - brief (string, 1–2 sentences, what this article will cover)\n"
            f"  - category (string, one of: {valid_cats})\n"
            f"  - tags (array of 3–5 short lowercase phrases)\n"
            f"  - primary_keyword (string, the main SEO keyword for this article)\n"
            f"  - meta_title (string, ≤60 chars)\n"
            f"  - meta_description (string, ≤160 chars)\n\n"
            f"Rules:\n"
            f"- Articles must be sequential (Part 1, Part 2, …) and logically build on each other.\n"
            f"- Mix instructional, parent-perspective, drill-focused, and case-study angles.\n"
            f"- Use concrete age brackets (U7–U21) and specific examples, not vague advice.\n"
            f"- No two primary_keywords or meta_titles should overlap.\n"
            f"- Output JSON ARRAY only — no explanation, no fences.\n"
        )
        try:
            raw = await call_gemini_text(
                session_id=f"blog-series-{uuid.uuid4().hex[:8]}",
                prompt=prompt,
                system_message=sys_msg,
            )
        except Exception as e:
            raise HTTPException(502, f"Gemini series generation failed: {e}")

        import json
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.MULTILINE)
        try:
            parsed = json.loads(cleaned)
        except Exception:
            m = re.search(r"\[[\s\S]*\]", cleaned)
            if not m:
                raise HTTPException(502, "Could not parse Gemini series response")
            parsed = json.loads(m.group(0))

        if not isinstance(parsed, list):
            raise HTTPException(502, "Series response is not a JSON array")

        series = []
        for idx, item in enumerate(parsed[: payload.count], 1):
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or f"Part {idx}").strip()[:200]
            series.append({
                "index": idx,
                "title": title,
                "slug": slugify(title),
                "brief": (item.get("brief") or "").strip(),
                "category": item.get("category") or None,
                "tags": [str(t).strip().lower() for t in (item.get("tags") or []) if str(t).strip()][:5],
                "primary_keyword": (item.get("primary_keyword") or "").strip(),
                "meta_title": (item.get("meta_title") or title)[:70],
                "meta_description": (item.get("meta_description") or "")[:160],
            })

        return {"topic": payload.topic, "count": len(series), "series": series}

    @router.post("/admin/ai/series/save", dependencies=[Depends(get_current_admin)])
    async def ai_save_series(payload: SeriesBulkSaveRequest):
        """Save a generated series as draft posts (one per item) with an outline stub."""
        if not payload.items:
            raise HTTPException(400, "No items to save")
        saved = []
        for idx, item in enumerate(payload.items, 1):
            title = (item.title or f"{payload.topic} — Part {idx}").strip()
            brief = (item.brief or "").strip()
            primary_kw = (item.primary_keyword or "").strip()
            outline = (
                f"# {title}\n\n"
                f"*{brief}*\n\n"
                f"---\n\n"
                f"> **Outline placeholder** — open this article and use **AI Draft Assist** at the top "
                f"to expand it into a full ~800-word article. Suggested primary keyword: `{primary_kw}`.\n\n"
                f"## What this article will cover\n\n"
                f"- Hook & opening question\n"
                f"- 3–4 main sections with H2 headings\n"
                f"- One concrete example or mini case-study\n"
                f"- Practical takeaway box (quoted)\n"
                f"- Closing CTA back to ScoutMePlay\n\n"
                f"## Cross-links\n\n"
                f"_Add links to the other articles in this series once they're written._\n"
            )
            slug = await unique_slug(title)
            now = now_iso()
            doc = {
                "id": str(uuid.uuid4()),
                "slug": slug,
                "title": title,
                "subtitle": brief or None,
                "content_md": outline,
                "excerpt": brief or make_excerpt(outline),
                "cover_image_url": None,
                "cover_image_alt": title,
                "category": item.category,
                "tags": item.tags or [],
                "author_name": "ScoutMePlay Editorial",
                "status": "draft",
                "published_at": None,
                "meta_title": (item.meta_title or title)[:70],
                "meta_description": (item.meta_description or brief or "")[:160],
                "meta_keywords": [primary_kw] if primary_kw else [],
                "reading_time_minutes": reading_time_min(outline),
                "view_count": 0,
                "created_at": now,
                "updated_at": now,
            }
            await db[BLOG_POSTS].insert_one(doc)
            from quality_engine import schedule_auto_qc
            schedule_auto_qc(db, "blog", doc["id"])
            saved.append({"id": doc["id"], "slug": slug, "title": title})
        return {"saved": saved, "count": len(saved)}

    return router


# Mount handler — to be called from server.py
def mount_blog_uploads(app):
    """Mount static files for blog uploads. Call once from server.py main app."""
    from fastapi.staticfiles import StaticFiles
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/api/blog/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="blog-uploads")
