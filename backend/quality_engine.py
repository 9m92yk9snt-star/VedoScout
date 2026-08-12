"""ScoutMePlay Quality Engine — Ad Studio-style anti-generic QC for existing admin content.

Covers: blog articles (text + keywords/SEO + cover image), Instagram carousels
(slides + caption), site SEO metadata, and a cross-content duplicate scanner.
Detect → propose → admin approves → apply (DB content only). Never edits code.
"""
from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ad_studio import PRODUCTS, FORBIDDEN

logger = logging.getLogger("elite-scout")

ROOT = Path(__file__).parent
BLOG_UPLOADS = ROOT / "uploads" / "blog"
CAROUSEL_DIR = ROOT / "uploads" / "carousels"
ADS_DIR = ROOT / "uploads" / "ads"
LANDING_DIR = ROOT / "static" / "landing"

now_iso = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731

FACTS = "\n".join(f"- {v['label']}: {v['facts']}" for v in PRODUCTS.values())

BRAND_STANDARD = (
    "ScoutMePlay visual/voice standard: premium football editorial + academy documentary. "
    "Authentic match/training photography, natural light, grain, imperfect framing, real emotion, "
    "football micro-moments (boots, first touch, scanning, touchline). Palette cream/dark green/black, "
    "lime only as accent. FORBIDDEN visuals: green glowing players, fake stadium lighting, plastic skin, "
    "holograms, HUD graphics, futuristic overlays, excessive neon, generic smiling football models. "
    "Copy must be specific football language, never generic SaaS marketing. " + FORBIDDEN
)

QC_SYSTEM = (
    "You are a ruthless creative director and editor QC'ing content for ScoutMePlay, a premium football "
    "scouting platform for youth players and parents. You reject anything generic, AI-sounding, hypey, "
    "factually wrong or unreadable on mobile. You answer ONLY in JSON. "
    f"The ONLY claims allowed about ScoutMePlay products:\n{FACTS}\n{BRAND_STANDARD}"
)

BLOG_CHECKS = [
    ("generic_wording", "Generic wording", "text"),
    ("sounds_generated", "Sounds AI-generated", "text"),
    ("repeated_wording", "Repeated wording", "text"),
    ("clear_to_reader", "Clear to player/parent", "text"),
    ("football_terminology", "Football terminology correct", "text"),
    ("grammar", "Grammar correct", "text"),
    ("headline_strength", "Headline strength", "text"),
    ("cta_strength", "CTA strength", "text"),
    ("claim_accurate", "Product claims accurate", "text"),
    ("seo_title", "SEO title quality", "seo"),
    ("meta_description", "Meta description quality", "seo"),
    ("keyword_natural", "Keywords used naturally", "seo"),
    ("alt_text", "Cover alt text", "seo"),
    ("image_generic", "Cover not generic", "image"),
    ("image_looks_ai", "Cover looks real (not AI art)", "image"),
    ("image_context", "Cover matches article meaning", "image"),
    ("image_brand", "Cover fits brand standard", "image"),
]

CAROUSEL_CHECKS = [
    ("hook_strength", "Slide 1 stops the scroll", "text"),
    ("slide_readability", "Slides readable on mobile", "text"),
    ("repeated_wording", "No repeated wording across slides", "text"),
    ("generic_content", "Not generic advice", "text"),
    ("claim_accurate", "Product claims accurate", "text"),
    ("cta_clear", "Final CTA slide clear", "text"),
    ("caption_quality", "Caption warm, human, specific", "text"),
    ("brand_fit", "Fits ScoutMePlay voice/visuals", "image"),
]

SEO_CHECKS = [
    ("title_ok", "Title specific & <=60 chars"),
    ("description_ok", "Description compelling & <=160 chars"),
    ("keywords_ok", "Keywords relevant, no stuffing"),
    ("no_generic_filler", "No generic SaaS filler"),
    ("claim_accurate", "Claims accurate"),
]


def _md5(*parts: str) -> str:
    return hashlib.md5("||".join(p or "" for p in parts).encode()).hexdigest()


def _parse_json(text: str) -> Any:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    i = t.find("{")
    return json.loads(t[i:] if i > 0 else t)


def _chat(session: str):
    from emergentintegrations.llm.chat import LlmChat
    c = LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=f"quality-{session}-{uuid.uuid4().hex[:6]}",
        system_message=QC_SYSTEM,
    ).with_model("gemini", "gemini-2.5-pro")
    c.extra_params = {"temperature": 0.0, "timeout": 100.0}
    return c


def _files(paths: list[Path]):
    from emergentintegrations.llm.chat import FileContentWithMimeType
    out = []
    for p in paths:
        if p and p.exists():
            mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
            out.append(FileContentWithMimeType(file_path=str(p), mime_type=mime))
    return out


def _norm_checks(raw: list, spec: list) -> list[dict]:
    by_key = {c.get("key"): c for c in (raw or []) if isinstance(c, dict)}
    out = []
    for item in spec:
        key, label = item[0], item[1]
        group = item[2] if len(item) > 2 else "text"
        c = by_key.get(key) or {}
        out.append({
            "key": key, "label": label, "group": group,
            "pass": bool(c.get("pass", False)),
            "issue": str(c.get("issue") or "")[:400],
        })
    return out


def _local_image(url: str) -> Optional[Path]:
    if not url:
        return None
    if url.startswith("/api/blog/uploads/") or url.startswith("/api/media/blog/"):
        return BLOG_UPLOADS / url.rsplit("/", 1)[-1]
    if url.startswith("/api/uploads/"):
        return ROOT / "uploads" / url.replace("/api/uploads/", "")
    return None


# ── Blog check ─────────────────────────────────────────────────────────────
def _blog_hash(post: dict) -> str:
    return _md5(post.get("title"), post.get("excerpt"), post.get("content_md"),
                post.get("meta_title"), post.get("meta_description"),
                post.get("cover_image_url"), post.get("cover_image_alt"))


async def _check_blog(post: dict) -> dict:
    from emergentintegrations.llm.chat import UserMessage
    cover = _local_image(post.get("cover_image_url") or "")
    body = (post.get("content_md") or "")[:5000]
    prompt = f"""QC this ScoutMePlay blog article. Blog tone: human, informative, knowledgeable — not an advertisement.
TITLE: {post.get('title')}
SUBTITLE: {post.get('subtitle') or '—'}
CATEGORY: {post.get('category') or '—'}
EXCERPT: {post.get('excerpt') or '—'}
META TITLE: {post.get('meta_title') or '(missing)'}
META DESCRIPTION: {post.get('meta_description') or '(missing)'}
META KEYWORDS: {', '.join(post.get('meta_keywords') or []) or '(missing)'}
COVER ALT TEXT: {post.get('cover_image_alt') or '(missing)'}
BODY (first 5000 chars):
{body}

The attached photo (if any) is the cover image. If no photo attached, mark the 4 image checks pass=true with issue "no local cover to analyse".
Evaluate every check strictly. Banned SaaS filler ("unlock your potential" etc.) fails generic_wording.
Return ONLY JSON:
{{"checks": [{{"key":"generic_wording","pass":true,"issue":""}}, ... all of: {[k for k, _, _ in BLOG_CHECKS]}],
 "scores": {{"text":0-100,"seo":0-100,"image":0-100,"overall":0-100}},
 "image_classification": "AUTHENTIC|REVIEW|TOO_GENERIC|NONE",
 "image_recommendation": "KEEP|IMPROVE|REPLACE|GENERATE|NONE",
 "proposed": {{"title":null_or_better,"excerpt":null_or_better,"meta_title":null_or_better,"meta_description":null_or_better,"meta_keywords":null_or_comma_separated,"cover_image_alt":null_or_better}}}}
Only fill a "proposed" field when the current one fails a check — keep proposals specific, football-real, same language as the article, factually true."""
    chat = _chat("blog")
    resp = await asyncio.wait_for(
        chat.send_message(UserMessage(text=prompt, file_contents=_files([cover]) or None)), timeout=150)
    data = _parse_json(resp if isinstance(resp, str) else getattr(resp, "text", str(resp)))
    checks = _norm_checks(data.get("checks"), BLOG_CHECKS)
    scores = {k: max(0, min(100, int(data.get("scores", {}).get(k, 0) or 0))) for k in ("text", "seo", "image", "overall")}
    if not (cover and cover.exists()):
        scores["image"] = None
        scores["overall"] = round((scores["text"] + scores["seo"]) / 2)
    proposed = {k: (str(v).strip() if v else None) for k, v in (data.get("proposed") or {}).items()
                if k in ("title", "excerpt", "meta_title", "meta_description", "meta_keywords", "cover_image_alt")}
    return {
        "checks": checks, "scores": scores,
        "passed": all(c["pass"] for c in checks),
        "image_classification": data.get("image_classification") or ("NONE" if not cover else "REVIEW"),
        "image_recommendation": data.get("image_recommendation") or "NONE",
        "proposed": {k: v for k, v in proposed.items() if v},
        "current": {
            "title": post.get("title"), "excerpt": post.get("excerpt"),
            "meta_title": post.get("meta_title"), "meta_description": post.get("meta_description"),
            "meta_keywords": ", ".join(post.get("meta_keywords") or []),
            "cover_image_alt": post.get("cover_image_alt"),
        },
    }


# ── Carousel check ─────────────────────────────────────────────────────────
def _carousel_hash(job: dict) -> str:
    return _md5(job.get("caption"), json.dumps(job.get("slide_urls") or []))


async def _check_carousel(job: dict) -> dict:
    from emergentintegrations.llm.chat import UserMessage
    job_dir = CAROUSEL_DIR / (job.get("job_dir_id") or "")
    slides = sorted(job_dir.glob("slide-*.png")) if job_dir.exists() else []
    attach = [slides[0], slides[len(slides) // 2], slides[-1]] if len(slides) >= 3 else slides
    prompt = f"""QC this ScoutMePlay Instagram carousel (comment-to-DM funnel promotion).
TOPIC: {job.get('topic')}
CAPTION: {job.get('caption') or '(missing)'}
Attached: slide 1 (hook), a middle slide, and the final CTA slide out of {len(slides)} slides.
Evaluate every check strictly (mobile-first readability, warm human voice, no guarantees).
Return ONLY JSON:
{{"checks": [{{"key":"hook_strength","pass":true,"issue":""}}, ... all of: {[k for k, _, _ in CAROUSEL_CHECKS]}],
 "scores": {{"text":0-100,"image":0-100,"overall":0-100}},
 "proposed": {{"caption": null_or_better_caption_with_hashtags}}}}
Only propose a caption if the current one fails caption_quality/claim_accurate/generic_content."""
    chat = _chat("carousel")
    resp = await asyncio.wait_for(
        chat.send_message(UserMessage(text=prompt, file_contents=_files(attach) or None)), timeout=150)
    data = _parse_json(resp if isinstance(resp, str) else getattr(resp, "text", str(resp)))
    checks = _norm_checks(data.get("checks"), CAROUSEL_CHECKS)
    scores = {k: max(0, min(100, int(data.get("scores", {}).get(k, 0) or 0))) for k in ("text", "image", "overall")}
    cap = (data.get("proposed") or {}).get("caption")
    return {
        "checks": checks, "scores": scores,
        "passed": all(c["pass"] for c in checks),
        "proposed": {"caption": str(cap).strip()} if cap else {},
        "current": {"caption": job.get("caption")},
    }


# ── SEO pages check ────────────────────────────────────────────────────────
async def _effective_seo_pages(db) -> list[dict]:
    from seo_social import PAGE_DEFS
    doc = await db.settings.find_one({"key": "seo_pages"}) or {}
    overrides = doc.get("pages") or {}
    pages = []
    for p in PAGE_DEFS:
        o = overrides.get(p["key"]) or {}
        pages.append({
            "key": p["key"], "path": p["path"], "label": p["label"],
            "title": (o.get("title") or "").strip() or p["title"],
            "description": (o.get("description") or "").strip() or p["description"],
            "keywords": (o.get("keywords") or "").strip() or p["keywords"],
        })
    return pages


def _seo_hash(pages: list[dict]) -> str:
    return _md5(json.dumps(pages, sort_keys=True))


async def _check_seo(pages: list[dict]) -> dict:
    from emergentintegrations.llm.chat import UserMessage
    listing = "\n".join(
        f"[{p['key']}] {p['path']} — TITLE: {p['title']} | DESCRIPTION: {p['description']} | KEYWORDS: {p['keywords']}"
        for p in pages)
    prompt = f"""QC the SEO metadata of every public ScoutMePlay page below. These appear in Google — they must be specific, credible and non-generic. Also flag titles/descriptions that are too similar to another page's.
{listing}

For EACH page evaluate: {[k for k, _ in SEO_CHECKS]}.
Return ONLY JSON:
{{"pages": {{"<key>": {{"checks":[{{"key":"title_ok","pass":true,"issue":""}}...],"score":0-100,
 "proposed": {{"title":null_or_better,"description":null_or_better,"keywords":null_or_better}}}}, ...}},
 "overall": 0-100}}
Only fill proposed fields for failing pages. Titles <=60 chars, descriptions <=160 chars, keep the page's actual purpose, never invent claims."""
    chat = _chat("seo")
    resp = await asyncio.wait_for(chat.send_message(UserMessage(text=prompt)), timeout=150)
    data = _parse_json(resp if isinstance(resp, str) else getattr(resp, "text", str(resp)))
    out_pages = {}
    for p in pages:
        raw = (data.get("pages") or {}).get(p["key"]) or {}
        checks = _norm_checks(raw.get("checks"), SEO_CHECKS)
        prop = {k: (str(v).strip() if v else None) for k, v in (raw.get("proposed") or {}).items()
                if k in ("title", "description", "keywords")}
        out_pages[p["key"]] = {
            "label": p["label"], "path": p["path"],
            "current": {"title": p["title"], "description": p["description"], "keywords": p["keywords"]},
            "checks": checks,
            "score": max(0, min(100, int(raw.get("score", 0) or 0))),
            "passed": all(c["pass"] for c in checks),
            "proposed": {k: v for k, v in prop.items() if v},
        }
    overall = max(0, min(100, int(data.get("overall", 0) or 0)))
    return {
        "pages": out_pages,
        "scores": {"overall": overall},
        "passed": all(v["passed"] for v in out_pages.values()),
        "proposed": {},
    }


# ── Duplicate scanner (no LLM) ─────────────────────────────────────────────
def _sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def _dhash(path: Path) -> Optional[int]:
    try:
        from PIL import Image
        img = Image.open(path).convert("L").resize((9, 8))
        px = list(img.getdata())
        bits = 0
        for row in range(8):
            for col in range(8):
                bits = (bits << 1) | (1 if px[row * 9 + col] > px[row * 9 + col + 1] else 0)
        return bits
    except Exception:
        return None


def _pairs_warn(items: list[tuple[str, str]], threshold: float, kind: str) -> list[dict]:
    warns = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (loc_a, text_a), (loc_b, text_b) = items[i], items[j]
            if not text_a or not text_b:
                continue
            r = _sim(text_a, text_b)
            if r >= threshold:
                warns.append({
                    "type": "text", "kind": kind, "similarity": round(r, 2),
                    "where": [loc_a, loc_b],
                    "detail": f'"{text_a[:120]}" ≈ "{text_b[:120]}"',
                })
    return warns


_SENT_RE = re.compile(r"[.!?]\s+")


async def _scan_duplicates(db) -> dict:
    warnings: list[dict] = []
    posts = [p async for p in db.blog_posts.find({}, {"_id": 0, "id": 1, "title": 1, "excerpt": 1, "meta_description": 1, "content_md": 1, "cover_image_url": 1})]

    warnings += _pairs_warn([(f"Blog → {p['title']}", p.get("title", "")) for p in posts], 0.72, "Blog titles")
    warnings += _pairs_warn([(f"Blog → {p['title']} (excerpt)", p.get("excerpt", "")) for p in posts], 0.72, "Blog excerpts")
    warnings += _pairs_warn([(f"Blog → {p['title']} (meta)", p.get("meta_description", "")) for p in posts], 0.72, "Blog meta descriptions")

    sent_map: dict[str, list[str]] = {}
    for p in posts:
        seen = set()
        for s in _SENT_RE.split(p.get("content_md") or ""):
            s = re.sub(r"[#*_>\[\]()`]", "", s).strip()
            key = s.lower()
            if len(s) >= 60 and key not in seen:
                seen.add(key)
                sent_map.setdefault(key, []).append(p["title"])
    for sent, titles in sent_map.items():
        if len(titles) >= 2:
            warnings.append({
                "type": "text", "kind": "Repeated sentence across articles",
                "similarity": 1.0, "where": [f"Blog → {t}" for t in titles[:4]],
                "detail": f'"{sent[:160]}"',
            })

    pages = await _effective_seo_pages(db)
    warnings += _pairs_warn([(f"SEO → {p['label']}", p["description"]) for p in pages], 0.65, "SEO descriptions")
    warnings += _pairs_warn([(f"SEO → {p['label']} (title)", p["title"]) for p in pages], 0.75, "SEO titles")

    jobs = [j async for j in db.carousel_jobs.find({"status": "done"}, {"_id": 0, "topic": 1, "caption": 1})]
    warnings += _pairs_warn([(f"Carousel → {j['topic']}", j.get("caption", "")) for j in jobs], 0.7, "Carousel captions")

    img_files: list[tuple[str, Path]] = []
    for p in posts:
        lp = _local_image(p.get("cover_image_url") or "")
        if lp and lp.exists():
            img_files.append((f"Blog cover → {p['title']}", lp))
    for d, label in ((ADS_DIR, "Ad Studio"), (LANDING_DIR, "Landing")):
        if d.exists():
            for f in sorted(d.glob("*.jpg")):
                img_files.append((f"{label} → {f.name}", f))
    hashes = await asyncio.to_thread(lambda: [(loc, _dhash(fp)) for loc, fp in img_files])
    for i in range(len(hashes)):
        for j in range(i + 1, len(hashes)):
            (la, ha), (lb, hb) = hashes[i], hashes[j]
            if ha is None or hb is None:
                continue
            dist = bin(ha ^ hb).count("1")
            if dist <= 6:
                warnings.append({
                    "type": "image", "kind": "Near-identical images",
                    "similarity": round(1 - dist / 64, 2), "where": [la, lb],
                    "detail": "These two images look nearly identical — vary the moment or replace one.",
                })

    sev = lambda w: 0 if w["similarity"] >= 0.9 else (1 if w["similarity"] >= 0.78 else 2)  # noqa: E731
    for w in warnings:
        w["severity"] = ["CRITICAL", "IMPORTANT", "IMPROVEMENT"][sev(w)]
    warnings.sort(key=sev)
    return {
        "warnings": warnings,
        "counts": {"text": sum(1 for w in warnings if w["type"] == "text"),
                   "image": sum(1 for w in warnings if w["type"] == "image"),
                   "items_scanned": len(posts) + len(pages) + len(jobs) + len(img_files)},
        "scores": {"overall": max(0, 100 - 8 * sum(1 for w in warnings if w["severity"] != "IMPROVEMENT") - 3 * sum(1 for w in warnings if w["severity"] == "IMPROVEMENT"))},
        "passed": not warnings,
        "proposed": {},
    }


# ── Runner / storage ───────────────────────────────────────────────────────
async def _run_check(db, kind: str, target_id: str, fn, content_hash: str):
    try:
        result = await fn()
        await db.quality_checks.update_one(
            {"kind": kind, "target_id": target_id},
            {"$set": {**result, "status": "ready", "error": None,
                      "content_hash": content_hash, "checked_at": now_iso()}},
            upsert=True)
    except Exception as e:
        logger.exception("quality check failed (%s/%s)", kind, target_id)
        await db.quality_checks.update_one(
            {"kind": kind, "target_id": target_id},
            {"$set": {"status": "error", "error": str(e)[:300], "checked_at": now_iso()}},
            upsert=True)


class BlogApply(BaseModel):
    fields: dict


class CarouselApply(BaseModel):
    caption: str


class SeoApply(BaseModel):
    pages: dict


BLOG_APPLY_WHITELIST = {"title", "subtitle", "excerpt", "meta_title", "meta_description", "meta_keywords", "cover_image_alt"}


def build_quality_router(*, db: Any, admin_dep: Any):
    router = APIRouter(prefix="/admin/quality", tags=["quality"])

    async def _start(kind: str, target_id: str, fn, content_hash: str):
        await db.quality_checks.update_one(
            {"kind": kind, "target_id": target_id},
            {"$set": {"status": "checking", "error": None, "started_at": now_iso()}},
            upsert=True)
        asyncio.create_task(_run_check(db, kind, target_id, fn, content_hash))
        return {"status": "checking"}

    @router.get("/latest")
    async def latest(kind: str, target_id: str, _=Depends(admin_dep)):
        doc = await db.quality_checks.find_one({"kind": kind, "target_id": target_id}, {"_id": 0})
        if not doc:
            return {"found": False}
        stale = False
        try:
            if doc.get("status") == "ready" and doc.get("content_hash"):
                if kind == "blog":
                    post = await db.blog_posts.find_one({"id": target_id})
                    stale = bool(post) and _blog_hash(post) != doc["content_hash"]
                elif kind == "carousel":
                    job = await db.carousel_jobs.find_one({"id": target_id})
                    stale = bool(job) and _carousel_hash(job) != doc["content_hash"]
                elif kind == "seo":
                    stale = _seo_hash(await _effective_seo_pages(db)) != doc["content_hash"]
        except Exception:
            pass
        return {"found": True, "stale": stale, **doc}

    @router.post("/blog/{post_id}/check")
    async def blog_check(post_id: str, _=Depends(admin_dep)):
        post = await db.blog_posts.find_one({"id": post_id}, {"_id": 0})
        if not post:
            raise HTTPException(404, "Post not found")
        return await _start("blog", post_id, lambda: _check_blog(post), _blog_hash(post))

    @router.post("/blog/{post_id}/apply")
    async def blog_apply(post_id: str, payload: BlogApply, _=Depends(admin_dep)):
        post = await db.blog_posts.find_one({"id": post_id})
        if not post:
            raise HTTPException(404, "Post not found")
        update = {}
        for k, v in payload.fields.items():
            if k not in BLOG_APPLY_WHITELIST or not isinstance(v, str) or not v.strip():
                continue
            update[k] = [s.strip() for s in v.split(",") if s.strip()] if k == "meta_keywords" else v.strip()
        if not update:
            raise HTTPException(400, "No valid fields")
        update["updated_at"] = now_iso()
        await db.blog_posts.update_one({"id": post_id}, {"$set": update})
        await db.quality_checks.update_one(
            {"kind": "blog", "target_id": post_id},
            {"$addToSet": {"applied": {"$each": list(update.keys())}}})
        return {"ok": True, "applied": [k for k in update if k != "updated_at"]}

    @router.post("/carousel/{job_id}/check")
    async def carousel_check(job_id: str, _=Depends(admin_dep)):
        job = await db.carousel_jobs.find_one({"id": job_id}, {"_id": 0})
        if not job:
            raise HTTPException(404, "Carousel not found")
        return await _start("carousel", job_id, lambda: _check_carousel(job), _carousel_hash(job))

    @router.post("/carousel/{job_id}/apply")
    async def carousel_apply(job_id: str, payload: CarouselApply, _=Depends(admin_dep)):
        if not payload.caption.strip():
            raise HTTPException(400, "Empty caption")
        r = await db.carousel_jobs.update_one({"id": job_id}, {"$set": {"caption": payload.caption.strip()}})
        if not r.matched_count:
            raise HTTPException(404, "Carousel not found")
        await db.quality_checks.update_one(
            {"kind": "carousel", "target_id": job_id}, {"$addToSet": {"applied": "caption"}})
        return {"ok": True, "applied": ["caption"]}

    @router.post("/seo/check")
    async def seo_check(_=Depends(admin_dep)):
        pages = await _effective_seo_pages(db)
        return await _start("seo", "site", lambda: _check_seo(pages), _seo_hash(pages))

    @router.post("/seo/apply")
    async def seo_apply(payload: SeoApply, _=Depends(admin_dep)):
        from seo_social import PAGE_DEFS
        valid = {p["key"] for p in PAGE_DEFS}
        doc = await db.settings.find_one({"key": "seo_pages"}) or {}
        overrides = doc.get("pages") or {}
        applied = []
        for key, vals in payload.pages.items():
            if key not in valid or not isinstance(vals, dict):
                continue
            cur = dict(overrides.get(key) or {})
            for f in ("title", "description", "keywords"):
                v = vals.get(f)
                if isinstance(v, str) and v.strip():
                    cur[f] = v.strip()
            overrides[key] = cur
            applied.append(key)
        if not applied:
            raise HTTPException(400, "No valid pages")
        await db.settings.update_one(
            {"key": "seo_pages"},
            {"$set": {"pages": overrides, "updated_at": now_iso()}}, upsert=True)
        await db.quality_checks.update_one(
            {"kind": "seo", "target_id": "site"}, {"$addToSet": {"applied": {"$each": applied}}})
        return {"ok": True, "applied": applied}

    @router.post("/duplicates/scan")
    async def duplicates_scan(_=Depends(admin_dep)):
        result = await _scan_duplicates(db)
        await db.quality_checks.update_one(
            {"kind": "duplicates", "target_id": "site"},
            {"$set": {**result, "status": "ready", "error": None, "checked_at": now_iso()}},
            upsert=True)
        return result

    @router.get("/overview")
    async def overview(_=Depends(admin_dep)):
        docs = [d async for d in db.quality_checks.find({}, {"_id": 0, "kind": 1, "target_id": 1, "status": 1, "scores": 1, "passed": 1, "checked_at": 1, "counts": 1})]
        blog = [d for d in docs if d["kind"] == "blog" and d.get("status") == "ready"]
        seo = next((d for d in docs if d["kind"] == "seo" and d.get("status") == "ready"), None)
        dup = next((d for d in docs if d["kind"] == "duplicates" and d.get("status") == "ready"), None)
        car = [d for d in docs if d["kind"] == "carousel" and d.get("status") == "ready"]
        avg = lambda xs: round(sum(xs) / len(xs)) if xs else None  # noqa: E731
        return {
            "blog": {"checked": len(blog), "avg": avg([d["scores"]["overall"] for d in blog if d.get("scores")]),
                     "failing": sum(1 for d in blog if not d.get("passed"))},
            "carousel": {"checked": len(car), "avg": avg([d["scores"]["overall"] for d in car if d.get("scores")]),
                         "failing": sum(1 for d in car if not d.get("passed"))},
            "seo": {"checked": bool(seo), "score": seo["scores"]["overall"] if seo and seo.get("scores") else None,
                    "checked_at": seo.get("checked_at") if seo else None},
            "duplicates": {"scanned": bool(dup), "warnings": (dup.get("counts", {}).get("text", 0) + dup.get("counts", {}).get("image", 0)) if dup else None,
                           "score": dup["scores"]["overall"] if dup and dup.get("scores") else None,
                           "checked_at": dup.get("checked_at") if dup else None},
        }

    return router

