"""blog_seed.py — production-safe blog bootstrap.
Covers: bundled static/blog_covers → uploads/blog on every boot (uploads/ is
git-ignored so fresh deploys ship without them). Posts: blog_seed_data.json
inserted ONCE per database (settings flag) when no published posts exist."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from blog_routes import UPLOAD_DIR

logger = logging.getLogger("blog_seed")
_BASE = Path(__file__).parent
COVERS_SRC = _BASE / "static" / "blog_covers"
SEED_DATA = _BASE / "blog_seed_data.json"


async def ensure_blog_seed(db) -> None:
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        if COVERS_SRC.is_dir():
            for src in COVERS_SRC.glob("*.jpg"):
                dst = UPLOAD_DIR / src.name
                if not dst.exists():
                    shutil.copyfile(src, dst)
    except Exception:
        logger.exception("blog cover restore failed (non-fatal)")

    try:
        if await db.settings.find_one({"key": "blog_seed_v1_done"}):
            return
        has_published = await db.blog_posts.count_documents({"status": "published"}, limit=1)
        if not has_published and SEED_DATA.exists():
            inserted = 0
            for p in json.loads(SEED_DATA.read_text()):
                if await db.blog_posts.find_one({"slug": p.get("slug")}, {"_id": 1}):
                    continue
                await db.blog_posts.insert_one(dict(p))
                inserted += 1
            if inserted:
                logger.info("blog seed: inserted %d launch article(s)", inserted)
        await db.settings.update_one(
            {"key": "blog_seed_v1_done"},
            {"$set": {"key": "blog_seed_v1_done", "value": True}},
            upsert=True,
        )
    except Exception:
        logger.exception("blog post seed failed (non-fatal)")
