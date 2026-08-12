"""ScoutMePlay Ad Studio — admin-only campaign generator.

One click: pick a product → 4 genuinely different creative concepts
(emotional / direct-response / problem-solution / product-value), each with
its own photographic image pair (portrait + square), copy grounded in REAL
product facts, and a mandatory anti-generic QC pass with automatic element
repair. Creatives are rendered/exported client-side per format.
"""
from __future__ import annotations

import asyncio
import base64
import io
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

logger = logging.getLogger("elite-scout")

UPLOAD_DIR = Path(__file__).parent / "uploads"
ADS_DIR = UPLOAD_DIR / "ads"
ADS_DIR.mkdir(parents=True, exist_ok=True)

now_iso = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731

# ── Ground truth: what each product ACTUALLY does ─────────────────────────
PRODUCTS: dict[str, dict] = {
    "instant_analysis": {
        "label": "Instant Pro Analysis",
        "facts": "Parents/players upload one match or training video. ScoutMePlay analyses technique, tactics, physical play and mentality and shows the exact video moments (with timestamps and photo frames) behind every observation. A free preview comes first — no card needed.",
    },
    "scout_review": {
        "label": "Real Scout Review",
        "facts": "Premium reports include a written review from a real football scout plus a chat where families can ask the scout questions about the report.",
    },
    "player_library": {
        "label": "Player Library",
        "facts": "Every report, video moment and score lives in one player profile. Upload more matches over time and the library tracks how scores develop between analyses.",
    },
    "exposure": {
        "label": "Player Exposure",
        "facts": "Premium player profiles are discoverable inside ScoutMePlay. Players see real profile-view counts and receive messages from scouts, agents or clubs in their inbox. No exposure outcome is ever guaranteed.",
    },
    "trials": {
        "label": "Trial Opportunities",
        "facts": "Premium and VIP members can browse and apply to trial and opportunity listings inside their dashboard. Applying is included; selection is always up to the organiser — never guaranteed.",
    },
    "benchmarks": {
        "label": "Player Benchmarks",
        "facts": "25 professional skill ratings, each benchmarked against players in the same age group, so families see where the player stands today — strengths and growth areas alike.",
    },
    "development": {
        "label": "Development Plan",
        "facts": "Every full report ends in an action plan: development priorities, a weekly training plan, a 12-month roadmap and practice missions. It updates with every new analysis.",
    },
    "single_report": {
        "label": "Single Scout Report",
        "facts": "One full scout report for one match video. One-time payment, no subscription: complete analysis, video-proofed moments, benchmarks, development plan and a downloadable PDF.",
    },
    "premium": {
        "label": "Premium",
        "facts": "The full package: complete video analysis with proof moments, 25 benchmarked ratings, real scout review + chat, player dashboard with exposure and trial listings, development plan and PDF reports.",
    },
    "vip": {
        "label": "VIP",
        "facts": "Everything in Premium with the highest priority: fastest turnaround and the deepest scout attention on every report.",
    },
}

ANGLES = ["emotional", "direct_response", "problem_solution", "product_value"]

FORBIDDEN = (
    "NEVER promise or imply: guaranteed trials, contracts, club interest, getting scouted/signed, "
    "pro careers, specific score improvements, or that scouts are currently watching. "
    "No invented stats, users, quotes or awards. Banned phrases: 'unlock your potential', "
    "'take your game to the next level', 'next level', 'game-changer', 'revolutionary', 'dream big', "
    "'AI-powered', 'cutting-edge', 'don't miss out'."
)

PHOTO_STYLE = (
    "Documentary football photography, shot on a real pitch. Natural available light, honest colours, "
    "visible photographic grain, slightly imperfect framing, shallow depth of field, a touch of motion blur "
    "where movement happens. Grass-roots/academy setting: worn boots, scuffed ball, training bibs, dew on grass. "
    "Face does not need to be visible. Palette leaning cream/off-white light, deep greens and near-black shadows. "
    "STRICTLY FORBIDDEN: text, logos, watermarks, branded shirts, holograms, HUD graphics, glowing lines, "
    "futuristic overlays, stadium crowds cheering, trophy lifting, studio lighting, plastic-perfect skin."
)

QC_KEYS = [
    ("generic_image", "Generic football image"),
    ("too_much_text", "Too much text"),
    ("weak_cta", "Weak CTA"),
    ("repeated_wording", "Repeated wording"),
    ("looks_ai", "Looks AI-generated"),
    ("claim_accurate", "Product claim accurate"),
    ("mobile_readable", "Mobile readable"),
]


def _chat(session: str, system: str, model=("openai", "gpt-5.4")):
    from emergentintegrations.llm.chat import LlmChat
    c = LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=f"adstudio-{session}-{uuid.uuid4().hex[:6]}",
        system_message=system,
    ).with_model(*model)
    return c


def _parse_json(text: str) -> Any:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    start = t.find("[") if t.lstrip().startswith("[") or t.find("[") < t.find("{") and t.find("[") != -1 else t.find("{")
    if start == -1:
        start = 0
    return json.loads(t[start:] if start else t)


# ── Copy generation ────────────────────────────────────────────────────────
COPY_SYSTEM = (
    "You are a senior performance-marketing copywriter for ScoutMePlay, a premium football scouting "
    "platform for youth players and their parents. Your copy is specific, warm, credible and short. "
    "You write like a human who knows grass-roots football — never like an ad template. " + FORBIDDEN
)


async def _generate_concepts(product_key: str, language: str) -> list[dict]:
    p = PRODUCTS[product_key]
    lang_line = "Write ALL copy in Danish (natural, everyday Danish — not translated-sounding)." if language == "da" else "Write ALL copy in English."
    prompt = f"""Product to advertise: {p['label']}
What it ACTUALLY does (the only claims you may make): {p['facts']}

Create EXACTLY 4 ad concepts, one per angle: emotional, direct_response, problem_solution, product_value.
{lang_line}

Rules:
- hook: max 7 words, no punctuation spam, no ALL CAPS words, each concept's hook must open with a DIFFERENT first word and use genuinely different framing (not the same sentence re-worded).
- sub: max 18 words, one concrete supporting line that makes the hook believable using only the facts above.
- cta: 2-4 words, action verb first, varied across concepts (never twice the same).
- Speak to the parent or the player (pick per angle) — direct 'you/your'.
- No hype words, no emojis, no exclamation-mark chains.
- image_portrait / image_square: one-sentence photography brief each for THIS concept — a specific football micro-moment (e.g. laces striking a wet ball, head up scanning over the shoulder, boots at the byline, first touch under pressure, tying boots alone before training). Portrait = wider scene with room above; square = tight close-up detail. Do NOT mention brands, text or graphics.

Return ONLY a JSON array of 4 objects with keys: angle, hook, sub, cta, image_portrait, image_square."""
    chat = _chat("copy", COPY_SYSTEM)
    from emergentintegrations.llm.chat import UserMessage
    resp = await asyncio.wait_for(chat.send_message(UserMessage(text=prompt)), timeout=120)
    text = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
    concepts = _parse_json(text)
    out = []
    for i, c in enumerate(concepts[:4]):
        out.append({
            "id": uuid.uuid4().hex[:8],
            "angle": c.get("angle") or ANGLES[i % 4],
            "hook": str(c.get("hook", "")).strip(),
            "sub": str(c.get("sub", "")).strip(),
            "cta": str(c.get("cta", "")).strip(),
            "image_brief": {
                "portrait": str(c.get("image_portrait", "")).strip(),
                "square": str(c.get("image_square", "")).strip(),
            },
            "images": {"portrait": None, "square": None},
            "qc": None,
            "selected": False,
            "edited": [],
        })
    return out


async def _fix_element(product_key: str, language: str, concept: dict, elements: list[str], issues: str) -> dict:
    """Regenerates only the failing text elements, keeping the rest."""
    p = PRODUCTS[product_key]
    lang_line = "Danish" if language == "da" else "English"
    prompt = f"""Fix ONLY these elements of the ad concept below: {', '.join(elements)}.
QC problems found: {issues}
Product: {p['label']} — facts (only allowed claims): {p['facts']}
Current concept (angle {concept['angle']}): hook="{concept['hook']}" sub="{concept['sub']}" cta="{concept['cta']}"
Language: {lang_line}. Same rules as before (hook<=7 words, sub<=18, cta 2-4 words, no hype, no banned phrases, factually true).
Return ONLY JSON: {{"hook": "...", "sub": "...", "cta": "..."}} with the untouched elements copied unchanged."""
    chat = _chat("fix", COPY_SYSTEM)
    from emergentintegrations.llm.chat import UserMessage
    resp = await asyncio.wait_for(chat.send_message(UserMessage(text=prompt)), timeout=90)
    text = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
    fixed = _parse_json(text)
    return {k: str(fixed.get(k, concept[k])).strip() or concept[k] for k in ("hook", "sub", "cta")}


# ── Image generation ───────────────────────────────────────────────────────
async def _gen_image(brief: str, shape: str, fname: str, corrective: str = "") -> Optional[str]:
    """Generates one ad photo. Returns public /api/uploads/ads/... URL or None."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from PIL import Image

        framing = (
            "Vertical 4:5 composition with generous negative space in the upper third for typography."
            if shape == "portrait" else
            "Square 1:1 composition, tight and intimate, subject filling the frame."
        )
        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=f"adstudio-img-{uuid.uuid4().hex[:8]}",
            system_message="You generate photorealistic photographs.",
        )
        chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
        msg = UserMessage(text=f"{PHOTO_STYLE}\n\nMoment: {brief}\n{framing}\n{corrective}")
        _t, images = await asyncio.wait_for(chat.send_message_multimodal_response(msg), timeout=120)
        if not images:
            return None
        raw = base64.b64decode(images[0]["data"])
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        if img.width > 1400:
            img = img.resize((1400, int(img.height * 1400 / img.width)), Image.LANCZOS)
        out = ADS_DIR / fname
        img.save(out, "JPEG", quality=88)
        return f"/api/uploads/ads/{fname}"
    except Exception:
        logger.exception("ad image generation failed (%s)", fname)
        return None


# ── QC — mandatory anti-generic check ─────────────────────────────────────
QC_SYSTEM = (
    "You are a ruthless creative director QC'ing performance ads for a premium football scouting platform. "
    "You reject anything generic, hypey, factually wrong or unreadable on mobile. Answer only in JSON."
)


async def _qc_concept(product_key: str, concept: dict, all_hooks: list[str]) -> dict:
    p = PRODUCTS[product_key]
    files = []
    try:
        from emergentintegrations.llm.chat import UserMessage, FileContentWithMimeType
        for shape in ("portrait", "square"):
            url = (concept.get("images") or {}).get(shape)
            if url:
                fp = ADS_DIR / url.rsplit("/", 1)[-1]
                if fp.exists():
                    files.append(FileContentWithMimeType(file_path=str(fp), mime_type="image/jpeg"))
        prompt = f"""QC this ad concept for "{p['label']}". Allowed claims ONLY: {p['facts']}
Copy — hook: "{concept['hook']}" | sub: "{concept['sub']}" | cta: "{concept['cta']}"
Other hooks in this campaign (must not overlap in wording/framing): {all_hooks}
The attached photo(s) are the ad images.

Evaluate each check. "pass" true/false + short issue when false:
- generic_image: photos are a specific, authentic football micro-moment (not a generic stock-looking football scene)
- too_much_text: hook<=7 words AND sub<=18 words AND cta<=4 words
- weak_cta: cta starts with an action verb and tells the user exactly what happens next
- repeated_wording: copy does not repeat wording/framing of the other hooks, and hook/sub/cta don't repeat each other
- looks_ai: photos look like real photography (grain, natural light, believable hands/limbs/ball) — not glossy AI art
- claim_accurate: every statement is covered by the allowed claims; nothing guaranteed that can't be
- mobile_readable: copy is short/punchy enough to read in 2 seconds on a phone

Return ONLY JSON: {{"checks": [{{"key": "...", "pass": true, "issue": ""}}], "worst_element": "hook|sub|cta|image|none"}}"""
        chat = _chat("qc", QC_SYSTEM, model=("gemini", "gemini-2.5-pro"))
        chat.extra_params = {"temperature": 0.0, "timeout": 90.0}
        resp = await asyncio.wait_for(
            chat.send_message(UserMessage(text=prompt, file_contents=files or None)), timeout=120
        )
        text = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
        data = _parse_json(text)
        checks = []
        by_key = {c.get("key"): c for c in data.get("checks", []) if isinstance(c, dict)}
        for key, label in QC_KEYS:
            c = by_key.get(key) or {}
            checks.append({
                "key": key, "label": label,
                "pass": bool(c.get("pass", False)),
                "issue": str(c.get("issue") or "")[:300],
            })
        return {
            "checks": checks,
            "passed": all(c["pass"] for c in checks),
            "worst_element": data.get("worst_element") or "none",
            "checked_at": now_iso(),
        }
    except Exception:
        logger.exception("ad QC failed")
        return {
            "checks": [{"key": k, "label": l, "pass": False, "issue": "QC engine error — re-run the check"} for k, l in QC_KEYS],
            "passed": False, "worst_element": "none", "checked_at": now_iso(),
        }


TEXT_CHECKS = {"too_much_text", "weak_cta", "repeated_wording", "claim_accurate", "mobile_readable"}
IMAGE_CHECKS = {"generic_image", "looks_ai"}


async def _auto_repair(product_key: str, language: str, concept: dict, all_hooks: list[str]) -> dict:
    """QC → repair failing elements once → re-QC. Returns final qc dict."""
    qc = await _qc_concept(product_key, concept, all_hooks)
    if qc["passed"]:
        return qc
    failed = [c for c in qc["checks"] if not c["pass"]]
    text_fail = [c for c in failed if c["key"] in TEXT_CHECKS]
    image_fail = [c for c in failed if c["key"] in IMAGE_CHECKS]
    if text_fail:
        try:
            issues = "; ".join(f"{c['label']}: {c['issue']}" for c in text_fail)
            fixed = await _fix_element(product_key, language, concept, ["hook", "sub", "cta"], issues)
            concept.update(fixed)
        except Exception:
            logger.exception("ad copy auto-repair failed")
    if image_fail:
        corrective = "PREVIOUS ATTEMPT FAILED QC: " + "; ".join(c["issue"] for c in image_fail) + \
            " Make it more raw, documentary and imperfect — a real captured moment."
        for shape in ("portrait", "square"):
            fname = f"{concept['id']}-{shape}-r.jpg"
            url = await _gen_image(concept["image_brief"][shape], shape, fname, corrective)
            if url:
                concept["images"][shape] = url
    if text_fail or image_fail:
        qc = await _qc_concept(product_key, concept, all_hooks)
        qc["auto_repaired"] = True
    return qc


# ── Campaign job ───────────────────────────────────────────────────────────
async def _run_campaign(db: Any, campaign_id: str, product_key: str, language: str):
    try:
        concepts = await _generate_concepts(product_key, language)
        await db.ad_campaigns.update_one({"id": campaign_id}, {"$set": {"concepts": concepts, "stage": "images"}})

        async def gen_pair(c):
            p_url, s_url = await asyncio.gather(
                _gen_image(c["image_brief"]["portrait"], "portrait", f"{c['id']}-portrait.jpg"),
                _gen_image(c["image_brief"]["square"], "square", f"{c['id']}-square.jpg"),
            )
            c["images"] = {"portrait": p_url, "square": s_url}

        await asyncio.gather(*(gen_pair(c) for c in concepts))
        await db.ad_campaigns.update_one({"id": campaign_id}, {"$set": {"concepts": concepts, "stage": "qc"}})

        all_hooks = [c["hook"] for c in concepts]
        qcs = await asyncio.gather(*(
            _auto_repair(product_key, language, c, [h for h in all_hooks if h != c["hook"]])
            for c in concepts
        ))
        for c, qc in zip(concepts, qcs):
            c["qc"] = qc
        await db.ad_campaigns.update_one(
            {"id": campaign_id},
            {"$set": {"concepts": concepts, "status": "ready", "stage": "done", "finished_at": now_iso()}},
        )
    except Exception as e:
        logger.exception("ad campaign %s failed", campaign_id)
        await db.ad_campaigns.update_one(
            {"id": campaign_id},
            {"$set": {"status": "error", "error": str(e)[:300]}},
        )


# ── Router ─────────────────────────────────────────────────────────────────
class GeneratePayload(BaseModel):
    product: str
    language: str = "en"


class EditPayload(BaseModel):
    hook: Optional[str] = None
    sub: Optional[str] = None
    cta: Optional[str] = None


class RegenPayload(BaseModel):
    element: str  # image | hook | copy | cta


def build_ad_studio_router(*, db: Any, admin_dep: Any):
    router = APIRouter(prefix="/admin/ad-studio", tags=["ad-studio"])

    @router.get("/products")
    async def products(_=Depends(admin_dep)):
        return [{"key": k, "label": v["label"], "facts": v["facts"]} for k, v in PRODUCTS.items()]

    @router.post("/generate")
    async def generate(payload: GeneratePayload, _=Depends(admin_dep)):
        if payload.product not in PRODUCTS:
            raise HTTPException(400, "Unknown product")
        cid = uuid.uuid4().hex[:10]
        doc = {
            "id": cid,
            "product": payload.product,
            "product_label": PRODUCTS[payload.product]["label"],
            "language": payload.language if payload.language in ("en", "da") else "en",
            "status": "generating",
            "stage": "copy",
            "error": None,
            "concepts": [],
            "created_at": now_iso(),
        }
        await db.ad_campaigns.insert_one({**doc})
        asyncio.create_task(_run_campaign(db, cid, payload.product, doc["language"]))
        return {"campaign_id": cid, "status": "generating"}

    @router.get("/campaigns")
    async def campaigns(_=Depends(admin_dep)):
        items = await db.ad_campaigns.find({}, {"_id": 0, "concepts": 0}).sort("created_at", -1).limit(20).to_list(20)
        return items

    @router.get("/campaigns/{cid}")
    async def campaign(cid: str, _=Depends(admin_dep)):
        doc = await db.ad_campaigns.find_one({"id": cid}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Not found")
        return doc

    async def _get(cid: str, concept_id: str):
        doc = await db.ad_campaigns.find_one({"id": cid}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Campaign not found")
        for c in doc.get("concepts", []):
            if c["id"] == concept_id:
                return doc, c
        raise HTTPException(404, "Concept not found")

    async def _save(doc):
        await db.ad_campaigns.update_one({"id": doc["id"]}, {"$set": {"concepts": doc["concepts"]}})

    @router.put("/campaigns/{cid}/concepts/{concept_id}")
    async def edit(cid: str, concept_id: str, payload: EditPayload, _=Depends(admin_dep)):
        doc, c = await _get(cid, concept_id)
        for field in ("hook", "sub", "cta"):
            v = getattr(payload, field)
            if v is not None and v.strip():
                c[field] = v.strip()
                if field not in c["edited"]:
                    c["edited"].append(field)
        await _save(doc)
        return c

    @router.post("/campaigns/{cid}/concepts/{concept_id}/select")
    async def select(cid: str, concept_id: str, _=Depends(admin_dep)):
        doc, c = await _get(cid, concept_id)
        c["selected"] = not c.get("selected")
        await _save(doc)
        return {"selected": c["selected"]}

    @router.post("/campaigns/{cid}/concepts/{concept_id}/qc")
    async def rerun_qc(cid: str, concept_id: str, _=Depends(admin_dep)):
        doc, c = await _get(cid, concept_id)
        hooks = [x["hook"] for x in doc["concepts"] if x["id"] != concept_id]
        c["qc"] = await _qc_concept(doc["product"], c, hooks)
        await _save(doc)
        return c

    @router.post("/campaigns/{cid}/concepts/{concept_id}/regen")
    async def regen(cid: str, concept_id: str, payload: RegenPayload, _=Depends(admin_dep)):
        doc, c = await _get(cid, concept_id)
        el = payload.element
        if el == "image":
            suffix = uuid.uuid4().hex[:4]
            for shape in ("portrait", "square"):
                url = await _gen_image(
                    c["image_brief"][shape], shape, f"{c['id']}-{shape}-{suffix}.jpg",
                    "Fresh take on the same moment — different angle and light, equally raw and documentary.",
                )
                if url:
                    c["images"][shape] = url
        elif el in ("hook", "copy", "cta"):
            elements = ["hook"] if el == "hook" else (["cta"] if el == "cta" else ["sub"])
            fixed = await _fix_element(
                doc["product"], doc.get("language", "en"), c, elements,
                f"Admin asked for a fresh {elements[0]} — genuinely different wording, same angle ({c['angle']}).",
            )
            for f in elements:
                c[f] = fixed[f]
                c["edited"] = [x for x in c["edited"] if x != f]
        else:
            raise HTTPException(400, "element must be image | hook | copy | cta")
        hooks = [x["hook"] for x in doc["concepts"] if x["id"] != concept_id]
        c["qc"] = await _qc_concept(doc["product"], c, hooks)
        await _save(doc)
        return c

    return router
