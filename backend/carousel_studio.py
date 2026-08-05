"""Carousel Studio — LLM slide texts + PIL-rendered 1080x1080 Instagram slides."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import random
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFilter, ImageFont

load_dotenv()
logger = logging.getLogger("carousel_studio")

ROOT = Path(__file__).parent
FONT_DIR = ROOT / "fonts"
BG_DIR = ROOT / "static" / "landing"
OUT_DIR = ROOT / "uploads" / "carousels"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SIZE = 1080
LIME = (204, 255, 0)
WHITE = (255, 255, 255)

SYSTEM_PROMPT = """You are the social voice of ScoutMePlay — a football platform for ambitious U7–U21 players and their families.
You write Instagram carousel slides in a warm, human, honest voice. Hope and realism together — never promise contracts, trials or guaranteed exposure.
NEVER use the standalone word "AI". Never use the word "percentile". Short punchy lines. British-neutral English."""


def _user_prompt(topic: str, slides: int, comment_word: str) -> str:
    return f"""Write an Instagram carousel about: "{topic}"

Structure (return EXACTLY {slides} content slides + 1 CTA slide as JSON):
- Slide 1 = HOOK: a bold scroll-stopping headline (max 9 words) + one short sub-line.
- Middle slides = one clear point each: short heading (max 8 words) + 2-4 short lines (each max 12 words). Practical, warm, honest.
- Optionally one slide can be "the fix" with concrete steps.
- Last slide = CTA: invite readers to comment "{comment_word}" to get our free parent guide in their DMs.

Return ONLY valid JSON, no markdown fences:
{{"caption": "<instagram caption, 3-5 warm sentences + 5 hashtags>", "slides": [
  {{"kind": "hook", "title": "<headline>", "lines": ["<sub-line>"]}},
  {{"kind": "point", "title": "<heading>", "lines": ["<line>", "<line>"]}},
  ...,
  {{"kind": "cta", "title": "COMMENT {comment_word.upper()}", "lines": ["<one warm line about the free guide>", "<one short reassurance line>"]}}
]}}"""


# ── PIL rendering ─────────────────────────────────────────────────────────

def _font(name: str, size: int):
    try:
        return ImageFont.truetype(str(FONT_DIR / name), size)
    except Exception:
        return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _background(idx: int, kind: str) -> Image.Image:
    if kind == "cta":
        img = Image.new("RGB", (SIZE, SIZE), (7, 10, 8))
        glow = Image.new("RGB", (SIZE, SIZE), (7, 10, 8))
        gd = ImageDraw.Draw(glow)
        gd.ellipse([SIZE * 0.25, SIZE * 0.55, SIZE * 0.75, SIZE * 1.05], fill=(24, 46, 28))
        glow = glow.filter(ImageFilter.GaussianBlur(160))
        return Image.blend(img, glow, 0.9)
    bgs = sorted(BG_DIR.glob("carousel-bg-[0-9].jpg"))
    if not bgs:
        return Image.new("RGB", (SIZE, SIZE), (10, 14, 11))
    bg = Image.open(bgs[idx % len(bgs)]).convert("RGB")
    w, h = bg.size
    s = max(SIZE / w, SIZE / h)
    bg = bg.resize((int(w * s) + 1, int(h * s) + 1), Image.LANCZOS)
    left = (bg.width - SIZE) // 2
    top = (bg.height - SIZE) // 2
    bg = bg.crop((left, top, left + SIZE, top + SIZE))
    overlay = Image.new("L", (SIZE, SIZE), 0)
    od = ImageDraw.Draw(overlay)
    for y in range(SIZE):
        od.line([(0, y), (SIZE, y)], fill=int(120 + 60 * abs(y - SIZE / 2) / (SIZE / 2)))
    dark = Image.new("RGB", (SIZE, SIZE), (4, 7, 5))
    return Image.composite(dark, bg, overlay.point(lambda v: min(255, v)))


def _watermark(draw):
    f = _font("Barlow-Bold.ttf", 30)
    text = "SCOUTMEPLAY"
    tw = draw.textlength(text, font=f)
    x = (SIZE - tw) / 2
    y = SIZE - 74
    draw.text((x, y), "SCOUT", font=f, fill=(255, 255, 255, 220))
    ox = draw.textlength("SCOUT", font=f)
    draw.text((x + ox, y), "ME", font=f, fill=LIME)
    ox += draw.textlength("ME", font=f)
    draw.text((x + ox, y), "PLAY", font=f, fill=(255, 255, 255, 220))


def render_slide(slide: dict, idx: int, total: int) -> Image.Image:
    kind = slide.get("kind") or "point"
    img = _background(idx, kind)
    draw = ImageDraw.Draw(img)

    title = (slide.get("title") or "").strip()
    lines = [l.strip() for l in (slide.get("lines") or []) if l and l.strip()]

    if kind == "hook":
        tf = _font("Barlow-Black.ttf", 108)
        tl = _wrap(draw, title.upper(), tf, 900)
        lf = _font("DMSans-Regular.ttf", 40)
        block_h = len(tl) * 112 + (len(lines) * 56 + 30 if lines else 0)
        y = (SIZE - block_h) / 2 - 20
        for ln in tl:
            w = draw.textlength(ln, font=tf)
            draw.text(((SIZE - w) / 2, y), ln, font=tf, fill=WHITE)
            y += 112
        y += 26
        for ln in lines:
            for sub in _wrap(draw, ln, lf, 820):
                w = draw.textlength(sub, font=lf)
                draw.text(((SIZE - w) / 2, y), sub, font=lf, fill=(230, 230, 225))
                y += 54
    elif kind == "cta":
        tf = _font("Barlow-Black.ttf", 120)
        tl = _wrap(draw, title.upper(), tf, 900)
        lf = _font("DMSans-Regular.ttf", 42)
        block_h = len(tl) * 126 + len(lines) * 58 + 40
        y = (SIZE - block_h) / 2 - 30
        for ln in tl:
            w = draw.textlength(ln, font=tf)
            draw.text(((SIZE - w) / 2, y), ln, font=tf, fill=LIME)
            y += 126
        y += 30
        for ln in lines:
            for sub in _wrap(draw, ln, lf, 840):
                w = draw.textlength(sub, font=lf)
                draw.text(((SIZE - w) / 2, y), sub, font=lf, fill=(235, 235, 230))
                y += 58
    else:
        tf = _font("Barlow-Black.ttf", 62)
        lf = _font("DMSans-Regular.ttf", 42)
        tl = _wrap(draw, title, tf, 860)
        wrapped = []
        for ln in lines:
            wrapped.extend(_wrap(draw, ln, lf, 820))
        block_h = len(tl) * 70 + 34 + len(wrapped) * 60
        y = (SIZE - block_h) / 2
        for ln in tl:
            w = draw.textlength(ln, font=tf)
            draw.text(((SIZE - w) / 2, y), ln, font=tf, fill=WHITE)
            y += 70
        y += 30
        for ln in wrapped:
            w = draw.textlength(ln, font=lf)
            draw.text(((SIZE - w) / 2, y), ln, font=lf, fill=(228, 228, 222))
            y += 60

    counter = _font("DMSans-Regular.ttf", 28)
    ct = f"{idx + 1}/{total}"
    draw.text((SIZE - draw.textlength(ct, font=counter) - 44, 44), ct, font=counter, fill=(255, 255, 255, 170))
    _watermark(draw)
    return img


# ── Generation job ────────────────────────────────────────────────────────

async def _generate(db: Any, topic: str, slides_count: int, comment_word: str) -> dict:
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    chat = LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=f"carousel-{uuid.uuid4().hex[:10]}",
        system_message=SYSTEM_PROMPT,
    ).with_model("openai", "gpt-5.4")
    resp = await chat.send_message(UserMessage(text=_user_prompt(topic, slides_count, comment_word)))
    text = resp if isinstance(resp, str) else getattr(resp, "text", None) or str(resp)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Model did not return JSON")
    data = json.loads(m.group(0))
    slides = data.get("slides") or []
    if len(slides) < 3:
        raise ValueError("Too few slides generated")

    job_id = uuid.uuid4().hex[:10]
    job_dir = OUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    urls = []
    start = random.randint(0, 6)
    for i, s in enumerate(slides):
        img = await asyncio.to_thread(render_slide, s, i, len(slides))
        fname = f"slide-{i + 1}.png"
        await asyncio.to_thread(img.save, job_dir / fname, "PNG")
        urls.append(f"/api/uploads/carousels/{job_id}/{fname}")
    _ = start
    return {"job_dir_id": job_id, "slide_urls": urls, "caption": data.get("caption") or "", "slides_data": slides}


class CarouselRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=250)
    slides: int = Field(default=7, ge=4, le=9)
    comment_word: str = Field(default="GUIDE", max_length=20)


def build_carousel_router(*, db: Any, admin_dep: Any):
    router = APIRouter(prefix="/carousel", tags=["carousel-studio"])

    async def _run(job_id: str, payload: CarouselRequest):
        try:
            result = await _generate(db, payload.topic, payload.slides, payload.comment_word)
            await db.carousel_jobs.update_one(
                {"id": job_id},
                {"$set": {"status": "done", **result, "finished_at": _now()}},
            )
        except Exception as e:
            logger.exception("carousel job failed")
            await db.carousel_jobs.update_one(
                {"id": job_id},
                {"$set": {"status": "failed", "error": str(e)[:400], "finished_at": _now()}},
            )

    @router.post("/generate")
    async def generate(payload: CarouselRequest, _=Depends(admin_dep)):
        job = {"id": str(uuid.uuid4()), "status": "running", "topic": payload.topic, "created_at": _now()}
        await db.carousel_jobs.insert_one(job)
        asyncio.create_task(_run(job["id"], payload))
        return {"job_id": job["id"], "status": "running"}

    @router.get("/jobs")
    async def jobs(_=Depends(admin_dep)):
        items = []
        async for d in db.carousel_jobs.find({}, {"_id": 0, "slides_data": 0}).sort("created_at", -1).limit(10):
            items.append(d)
        return {"items": items}

    @router.get("/jobs/{job_id}/zip")
    async def job_zip(job_id: str, _=Depends(admin_dep)):
        job = await db.carousel_jobs.find_one({"id": job_id})
        if not job or job.get("status") != "done":
            raise HTTPException(404, "Carousel not ready")
        job_dir = OUT_DIR / job["job_dir_id"]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(job_dir.glob("slide-*.png")):
                z.write(p, p.name)
            z.writestr("caption.txt", job.get("caption") or "")
        buf.seek(0)
        return Response(buf.read(), media_type="application/zip", headers={
            "Content-Disposition": f'attachment; filename="scoutmeplay-carousel-{job_id[:8]}.zip"'})

    @router.delete("/jobs/{job_id}")
    async def job_delete(job_id: str, _=Depends(admin_dep)):
        job = await db.carousel_jobs.find_one({"id": job_id})
        if job and job.get("job_dir_id"):
            import shutil
            shutil.rmtree(OUT_DIR / job["job_dir_id"], ignore_errors=True)
        await db.carousel_jobs.delete_one({"id": job_id})
        return {"ok": True}

    return router


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
