"""
SEO manager + social-follow settings.
Call `build_seo_social_router(db=..., admin_dep=...)` and include in the api router.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

PAGE_DEFS = [
    {
        "key": "home", "path": "/", "label": "Home / Landing",
        "title": "Discover Your True Football Level",
        "description": "Upload your football video and get an instant ScoutMe Pro report — plus a real professional scout review within 48h. Built for ambitious U7–U21 players.",
        "keywords": "football scouting report, youth football analysis, football talent, upload football video, player development plan, U7-U21 football, football trial preparation",
    },
    {
        "key": "upload", "path": "/upload", "label": "Upload page",
        "title": "Upload Your Football Video — Get Your Player Report",
        "description": "Free to start: upload one match clip, mark your player and receive a personal football report with scores, key moments and a training plan.",
        "keywords": "upload football video, football video analysis, youth player report, football skills assessment, match video review",
    },
    {
        "key": "about", "path": "/about", "label": "About us",
        "title": "About Us — Built by People Who Love Football",
        "description": "ScoutMePlay was built by scouts, parents and engineers who care about young footballers. Learn our story and what makes our reports different.",
        "keywords": "about scoutmeplay, football scouting company, youth football platform",
    },
    {
        "key": "methodology", "path": "/methodology", "label": "Methodology",
        "title": "Our Methodology — How Players Are Graded",
        "description": "A transparent look at how ScoutMePlay grades players: age-bracketed benchmarks, four development pillars and evidence-based scoring.",
        "keywords": "football player grading, youth football benchmarks, football methodology, player assessment criteria",
    },
    {
        "key": "blog", "path": "/blog", "label": "Blog index",
        "title": "Football Blog — Training, Scouting & Pro Path Insights",
        "description": "Expert articles on football scouting, training drills, parent guides and the academy-to-pro path. For ambitious U7–U21 players, parents and coaches.",
        "keywords": "football blog, youth football training, football scouting tips, parents guide football, academy football advice",
    },
    {
        "key": "scouts", "path": "/scouts", "label": "For scouts & clubs",
        "title": "For Scouts & Clubs — Discover Verified Youth Talent",
        "description": "Browse a growing database of analyzed youth players with verified reports, scores and video evidence. Built for scouts, academies and clubs.",
        "keywords": "football scout database, youth talent identification, player database, football recruitment",
    },
    {
        "key": "privacy", "path": "/privacy", "label": "Privacy policy",
        "title": "Privacy Policy",
        "description": "How ScoutMePlay collects, protects and uses your data. GDPR-compliant handling of videos, reports and personal information.",
        "keywords": "privacy policy, gdpr, data protection",
    },
    {
        "key": "terms", "path": "/terms", "label": "Terms of service",
        "title": "Terms of Service",
        "description": "The terms that apply when you use ScoutMePlay — uploads, reports, subscriptions, refunds and fair use.",
        "keywords": "terms of service, refund policy, subscription terms",
    },
    {
        "key": "signup", "path": "/signup", "label": "Sign up",
        "title": "Create Your Free Account",
        "description": "Create a free ScoutMePlay account, upload your first football video and see your free preview report — no card needed to start.",
        "keywords": "create account, free football report, sign up football analysis",
    },
    {
        "key": "login", "path": "/login", "label": "Log in",
        "title": "Log In",
        "description": "Log in to ScoutMePlay to see your reports, track progress and manage your player profile.",
        "keywords": "login, player dashboard",
    },
]


class SeoPageUpdate(BaseModel):
    title: str = Field(default="", max_length=70)
    description: str = Field(default="", max_length=175)
    keywords: str = Field(default="", max_length=300)


class SeoUpdate(BaseModel):
    pages: Dict[str, SeoPageUpdate] = {}


class SocialNetwork(BaseModel):
    url: str = Field(default="", max_length=300)
    followers: int = Field(default=0, ge=0)


class SocialFollowUpdate(BaseModel):
    enabled: bool = True
    instagram: SocialNetwork = SocialNetwork()
    facebook: SocialNetwork = SocialNetwork()


def build_seo_social_router(*, db: Any, admin_dep: Any):
    router = APIRouter(tags=["seo-social"])

    async def _seo_overrides() -> dict:
        doc = await db.settings.find_one({"key": "seo_pages"}) or {}
        return doc.get("pages") or {}

    @router.get("/seo/pages")
    async def public_seo_pages():
        overrides = await _seo_overrides()
        pages = {}
        for p in PAGE_DEFS:
            o = overrides.get(p["key"]) or {}
            pages[p["key"]] = {
                "path": p["path"],
                "title": (o.get("title") or "").strip() or p["title"],
                "description": (o.get("description") or "").strip() or p["description"],
                "keywords": (o.get("keywords") or "").strip() or p["keywords"],
            }
        return {"pages": pages}

    @router.get("/admin/seo")
    async def admin_get_seo(_=Depends(admin_dep)):
        overrides = await _seo_overrides()
        return {"pages": [{**p, "override": overrides.get(p["key"]) or {}} for p in PAGE_DEFS]}

    @router.put("/admin/seo")
    async def admin_put_seo(payload: SeoUpdate, _=Depends(admin_dep)):
        valid = {p["key"] for p in PAGE_DEFS}
        pages = {k: v.dict() for k, v in payload.pages.items() if k in valid}
        await db.settings.update_one(
            {"key": "seo_pages"},
            {"$set": {"pages": pages, "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        return {"ok": True, "saved": len(pages)}

    @router.post("/admin/seo/autofill")
    async def admin_autofill_seo(_=Depends(admin_dep)):
        pages = {p["key"]: {"title": p["title"], "description": p["description"], "keywords": p["keywords"]} for p in PAGE_DEFS}
        await db.settings.update_one(
            {"key": "seo_pages"},
            {"$set": {"pages": pages, "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        return {"ok": True, "pages": pages}

    # ── Social follow boxes ────────────────────────────────────────────
    async def _social_follow_payload() -> dict:
        doc = await db.settings.find_one({"key": "social_follow"}) or {}
        links_doc = await db.settings.find_one({"key": "social_links"}) or {}
        links = links_doc.get("value") or links_doc
        insta = doc.get("instagram") or {}
        face = doc.get("facebook") or {}
        return {
            "enabled": doc.get("enabled", True),
            "instagram": {
                "url": insta.get("url") or links.get("instagram_url") or "",
                "followers": int(insta.get("followers") or 0),
            },
            "facebook": {
                "url": face.get("url") or links.get("facebook_url") or "",
                "followers": int(face.get("followers") or 0),
            },
        }

    @router.get("/social-follow")
    async def public_social_follow():
        return await _social_follow_payload()

    @router.get("/admin/social-follow")
    async def admin_get_social_follow(_=Depends(admin_dep)):
        return await _social_follow_payload()

    @router.put("/admin/social-follow")
    async def admin_put_social_follow(payload: SocialFollowUpdate, _=Depends(admin_dep)):
        await db.settings.update_one(
            {"key": "social_follow"},
            {"$set": payload.dict()},
            upsert=True,
        )
        return {"ok": True}

    return router
