"""
SEO endpoints — sitemap.xml + robots.txt.
Self-contained module. Call `build_seo_router(...)` and include in app.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response


STATIC_ROUTES = [
    {"loc": "/", "priority": "1.0", "changefreq": "weekly"},
    {"loc": "/about", "priority": "0.7", "changefreq": "monthly"},
    {"loc": "/methodology", "priority": "0.8", "changefreq": "monthly"},
    {"loc": "/privacy", "priority": "0.3", "changefreq": "yearly"},
    {"loc": "/blog", "priority": "0.9", "changefreq": "daily"},
    {"loc": "/signup", "priority": "0.6", "changefreq": "monthly"},
    {"loc": "/login", "priority": "0.4", "changefreq": "yearly"},
]


def _site_base_url(request: Request) -> str:
    """Resolve the public site URL — env override > forwarded headers > request URL."""
    env_url = os.environ.get("PUBLIC_SITE_URL") or os.environ.get("FRONTEND_URL")
    if env_url:
        return env_url.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


def build_seo_router(*, db: Any):
    router = APIRouter(tags=["seo"])

    @router.get("/sitemap.xml", include_in_schema=False)
    async def sitemap_xml(request: Request):
        base = _site_base_url(request)
        today = datetime.now(timezone.utc).date().isoformat()

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]
        for r in STATIC_ROUTES:
            lines.append(
                f"<url><loc>{base}{r['loc']}</loc>"
                f"<lastmod>{today}</lastmod>"
                f"<changefreq>{r['changefreq']}</changefreq>"
                f"<priority>{r['priority']}</priority></url>"
            )

        # Blog posts (published)
        try:
            cursor = (
                db["blog_posts"]
                .find({"status": "published"}, {"slug": 1, "updated_at": 1, "published_at": 1})
                .sort("published_at", -1)
                .limit(5000)
            )
            async for doc in cursor:
                slug = doc.get("slug")
                if not slug:
                    continue
                lastmod = doc.get("updated_at") or doc.get("published_at") or today
                lastmod_date = lastmod.split("T")[0] if isinstance(lastmod, str) else today
                lines.append(
                    f"<url><loc>{base}/blog/{slug}</loc>"
                    f"<lastmod>{lastmod_date}</lastmod>"
                    f"<changefreq>monthly</changefreq>"
                    f"<priority>0.8</priority></url>"
                )
        except Exception:
            # If DB hiccups, still return the static sitemap rather than failing
            pass

        lines.append("</urlset>")
        return Response("\n".join(lines), media_type="application/xml")

    @router.get("/robots.txt", include_in_schema=False)
    async def robots_txt(request: Request):
        base = _site_base_url(request)
        body = (
            "User-agent: *\n"
            "Allow: /\n"
            "Disallow: /admin\n"
            "Disallow: /api/\n"
            "Disallow: /upload\n"
            "Disallow: /dashboard\n"
            "Disallow: /report/\n"
            f"\nSitemap: {base}/api/sitemap.xml\n"
        )
        return PlainTextResponse(body)

    return router
