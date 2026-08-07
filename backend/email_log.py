"""email_log.py — admin email log + open-tracking pixel endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response

# 1×1 transparent PNG
_PIXEL = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f0300050201f4d34d380000000049454e44ae426082"
)


def build_email_log_router(db, admin_dep):
    router = APIRouter()

    @router.get("/email/open/{log_id}.png")
    async def email_open(log_id: str):
        """Open-tracking pixel — marks the email as opened (first open wins)."""
        try:
            await db.email_log.update_one(
                {"id": log_id[:64], "opened_at": None},
                {"$set": {"opened_at": datetime.now(timezone.utc).isoformat()}},
            )
        except Exception:
            pass
        return Response(content=_PIXEL, media_type="image/png",
                        headers={"Cache-Control": "no-store, max-age=0"})

    @router.get("/admin/email-log")
    async def email_log_list(q: Optional[str] = None, category: Optional[str] = None,
                             limit: int = 100, _admin=Depends(admin_dep)):
        limit = max(1, min(limit, 300))
        match: dict = {}
        if q:
            match["to"] = {"$regex": q.strip().lower()[:80], "$options": "i"}
        if category:
            match["category"] = category.strip()[:40]
        cur = db.email_log.find(match, {"_id": 0}).sort("ts", -1).limit(limit)
        items = []
        async for d in cur:
            ts = d.get("ts")
            items.append({
                "id": d.get("id"),
                "to": d.get("to"),
                "subject": d.get("subject"),
                "category": d.get("category"),
                "status": d.get("status"),
                "ts": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "opened_at": d.get("opened_at"),
            })
        total = await db.email_log.count_documents(match)
        opened = await db.email_log.count_documents({**match, "opened_at": {"$ne": None}})
        return {"items": items, "total": total, "opened": opened}

    return router
