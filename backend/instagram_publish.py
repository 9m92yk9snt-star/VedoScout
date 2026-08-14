"""instagram_publish.py — publish Carousel Studio jobs to the brand's own Instagram Business account.

Flow (Meta Graph API content publishing): child IMAGE containers (is_carousel_item)
→ parent CAROUSEL container → media_publish. Admin pastes a long-lived access token
+ IG business account id in the admin UI (verified against Graph API before saving).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from PIL import Image

logger = logging.getLogger("instagram_publish")

META_VERSION = "v25.0"
GRAPH = f"https://graph.facebook.com/{META_VERSION}"

CAROUSEL_DIR = Path(__file__).parent / "uploads" / "carousels"


async def _graph_post(path: str, data: dict, token: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{GRAPH}{path}", data={**data, "access_token": token})
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.is_error:
        msg = ((body.get("error") or {}).get("message")) or f"HTTP {r.status_code}"
        raise RuntimeError(msg)
    return body


async def _graph_get(path: str, params: dict, token: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{GRAPH}{path}", params={**params, "access_token": token})
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.is_error:
        msg = ((body.get("error") or {}).get("message")) or f"HTTP {r.status_code}"
        raise RuntimeError(msg)
    return body


def _jpeg_slides(job_dir: Path) -> list[str]:
    """Meta only fetches JPEG — convert the PNG slides once, return filenames in order."""
    names = []
    for png in sorted(job_dir.glob("slide-*.png"), key=lambda p: int(p.stem.split("-")[1])):
        jpg = png.with_suffix(".jpg")
        if not jpg.exists():
            Image.open(png).convert("RGB").save(jpg, "JPEG", quality=92)
        names.append(jpg.name)
    return names


async def _wait_ready(container_id: str, token: str):
    for attempt, delay in enumerate([0, 5, 20, 40, 60, 60]):
        if delay:
            await asyncio.sleep(delay)
        status = await _graph_get(f"/{container_id}", {"fields": "status_code"}, token)
        code = status.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Image container failed ({code}) — check the image is publicly reachable")
    raise RuntimeError("Image container did not become ready in time")


async def publish_carousel(token: str, ig_user_id: str, image_urls: list[str], caption: str) -> dict:
    if not 2 <= len(image_urls) <= 10:
        raise RuntimeError("A carousel needs 2-10 images")
    children = []
    for url in image_urls:
        item = await _graph_post(f"/{ig_user_id}/media", {"image_url": url, "is_carousel_item": "true"}, token)
        children.append(item["id"])
    for child in children:
        await _wait_ready(child, token)
    parent = await _graph_post(f"/{ig_user_id}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "caption": (caption or "")[:2200],
    }, token)
    published = await _graph_post(f"/{ig_user_id}/media_publish", {"creation_id": parent["id"]}, token)
    media_id = published["id"]
    permalink = None
    try:
        info = await _graph_get(f"/{media_id}", {"fields": "permalink"}, token)
        permalink = info.get("permalink")
    except Exception:
        pass
    return {"media_id": media_id, "permalink": permalink}


# ── Router ────────────────────────────────────────────────────────────────

class InstagramConfigPut(BaseModel):
    access_token: str = Field(min_length=20, max_length=600)
    ig_user_id: str = Field(min_length=5, max_length=40)


class PublishRequest(BaseModel):
    origin_url: str = Field(min_length=8, max_length=300)


def build_instagram_router(*, db: Any, admin_dep: Any):
    router = APIRouter(prefix="/instagram", tags=["instagram-publish"])

    async def _cfg() -> Optional[dict]:
        return await db.settings.find_one({"key": "instagram_publish"})

    @router.get("/config")
    async def get_config(_=Depends(admin_dep)):
        doc = await _cfg()
        if not doc or not doc.get("access_token"):
            return {"connected": False}
        return {
            "connected": True,
            "username": doc.get("username"),
            "ig_user_id": doc.get("ig_user_id"),
            "token_hint": f"…{doc['access_token'][-4:]}",
        }

    @router.put("/config")
    async def put_config(payload: InstagramConfigPut, _=Depends(admin_dep)):
        token = payload.access_token.strip()
        ig_id = payload.ig_user_id.strip()
        try:
            info = await _graph_get(f"/{ig_id}", {"fields": "id,username,name"}, token)
        except RuntimeError as e:
            raise HTTPException(400, f"Meta rejected the connection: {e}")
        if not info.get("username"):
            raise HTTPException(400, "Meta did not return a username for this account ID — check the Instagram Business Account ID")
        await db.settings.update_one(
            {"key": "instagram_publish"},
            {"$set": {
                "access_token": token,
                "ig_user_id": ig_id,
                "username": info.get("username"),
                "account_name": info.get("name"),
            }},
            upsert=True,
        )
        return {"connected": True, "username": info.get("username"), "ig_user_id": ig_id}

    @router.delete("/config")
    async def delete_config(_=Depends(admin_dep)):
        await db.settings.delete_one({"key": "instagram_publish"})
        return {"ok": True}

    async def _run_publish(job: dict, origin: str, cfg: dict):
        try:
            job_dir = CAROUSEL_DIR / job["job_dir_id"]
            names = await asyncio.to_thread(_jpeg_slides, job_dir)
            if len(names) < 2:
                raise RuntimeError("Carousel has fewer than 2 slides")
            urls = [f"{origin}/api/uploads/carousels/{job['job_dir_id']}/{n}" for n in names]
            result = await publish_carousel(cfg["access_token"], cfg["ig_user_id"], urls, job.get("caption") or "")
            await db.carousel_jobs.update_one({"id": job["id"]}, {"$set": {
                "instagram_status": "published",
                "instagram_media_id": result["media_id"],
                "instagram_permalink": result.get("permalink"),
                "instagram_error": None,
            }})
            logger.info("Instagram carousel published: %s", result["media_id"])
        except Exception as e:
            logger.exception("Instagram publish failed")
            await db.carousel_jobs.update_one({"id": job["id"]}, {"$set": {
                "instagram_status": "failed",
                "instagram_error": str(e)[:400],
            }})

    @router.post("/publish/{job_id}")
    async def publish(job_id: str, payload: PublishRequest, _=Depends(admin_dep)):
        cfg = await _cfg()
        if not cfg or not cfg.get("access_token"):
            raise HTTPException(400, "Connect your Instagram account first (Marketing → Instagram connection)")
        job = await db.carousel_jobs.find_one({"id": job_id})
        if not job or job.get("status") != "done":
            raise HTTPException(404, "Carousel not found or not ready")
        if job.get("instagram_status") == "publishing":
            raise HTTPException(409, "Already publishing")
        origin = payload.origin_url.rstrip("/")
        if not origin.startswith("http"):
            raise HTTPException(400, "Invalid origin")
        await db.carousel_jobs.update_one({"id": job_id}, {"$set": {"instagram_status": "publishing", "instagram_error": None}})
        asyncio.create_task(_run_publish(job, origin, cfg))
        return {"status": "publishing"}

    return router
