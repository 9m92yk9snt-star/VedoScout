"""
progress_tracking.py — Player Profiles + Trajectory Engine + Gemini Delta Narrative
+ Progress Pass credits.

Self-contained module — no imports from server.py to avoid circular deps.
Call `build_progress_router(...)` and include the returned router.

DATA MODEL
─────────────
player_profiles (new)
  - id, user_id, name, normalized_name, dob, position, preferred_foot
  - report_ids[], created_at, updated_at
  - cached_trajectory: {generated_at, ...}      # cache to avoid recomputing

users (extended — additive, all optional)
  - progress_pass: {purchased_at, credits_remaining, credits_total, expires_at, txn_id}

reports (extended — additive, all optional)
  - player_profile_id: str | None
  - previous_report_id: str | None
  - mission_focus: list[str] | None            # what skills were declared the focus
"""

from __future__ import annotations

import json
import re
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional, Dict

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field

log = logging.getLogger("progress_tracking")

PLAYER_PROFILES = "player_profiles"
REPORTS = "reports"
USERS = "users"


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _public(doc: dict) -> dict:
    if not doc:
        return {}
    out = dict(doc)
    out.pop("_id", None)
    return out


def _age_at(report_doc: dict) -> Optional[int]:
    details = report_doc.get("player_details") or {}
    age = details.get("age")
    try:
        return int(age) if age is not None else None
    except (TypeError, ValueError):
        return None


def _overall(report_doc: dict) -> Optional[float]:
    full = report_doc.get("full_report") or {}
    sc = full.get("scores") or {}
    val = sc.get("overall_development")
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _pillar_scores(report_doc: dict) -> Dict[str, Optional[float]]:
    full = report_doc.get("full_report") or {}
    sc = full.get("scores") or {}
    out = {}
    for key in ("technical", "tactical", "physical", "mental", "decision_making"):
        v = sc.get(key)
        if v is None:
            # some reports use camelCase or section.score nesting
            section = full.get(key) or full.get(key.replace("_", " "))
            if isinstance(section, dict):
                v = section.get("score")
        try:
            out[key] = float(v) if v is not None else None
        except (TypeError, ValueError):
            out[key] = None
    return out


# ──────────────────────────────────────────────────────────────────────────
# Trajectory computation
# ──────────────────────────────────────────────────────────────────────────


def _verdict(timeline: List[dict]) -> str:
    """
    Return 'ahead' | 'on_track' | 'plateau' based on overall + per-pillar deltas.
    Needs 2+ reports.
    """
    if len(timeline) < 2:
        return "first_report"
    first, last = timeline[0], timeline[-1]
    overall_delta = (last.get("overall") or 0) - (first.get("overall") or 0)
    # Roughly: expect 0.3 - 0.6 score improvement per year of age at U10–U16
    months_span = max(1, (
        datetime.fromisoformat(last["date"].replace("Z", "+00:00")).timestamp()
        - datetime.fromisoformat(first["date"].replace("Z", "+00:00")).timestamp()
    ) / (60 * 60 * 24 * 30.5))
    yearly_pace = (overall_delta * 12) / months_span
    if yearly_pace >= 0.7:
        return "ahead"
    if yearly_pace <= 0.05:
        return "plateau"
    return "on_track"


def _age_adjusted_percentile(score: Optional[float], age: Optional[int]) -> Optional[float]:
    """
    Simple, transparent age-bucket percentile so deltas stay honest.
    Calibrated against the same StatsBomb-driven scoring philosophy: at every
    age bracket, a score of 7.0 is roughly the 50th percentile; +1.0 → +20 pts.
    Bracketed by age band so 13yo vs 15yo gets compared against their own peers.
    """
    if score is None or age is None:
        return None
    if age <= 10:
        base = 6.0
    elif age <= 12:
        base = 6.5
    elif age <= 14:
        base = 7.0
    elif age <= 17:
        base = 7.5
    else:
        base = 8.0
    pct = 50.0 + (float(score) - base) * 20.0
    return round(max(2.0, min(98.0, pct)), 1)


def _compute_badges(timeline: List[dict]) -> List[dict]:
    badges = []
    if not timeline:
        return badges
    # First Century — first score 80+ in any pillar
    for snap in timeline:
        for pillar, v in (snap.get("pillars") or {}).items():
            if v is not None and v >= 8.0:
                badges.append({"id": "first_century", "label": "First Century",
                               "earned_at": snap["date"],
                               "detail": f"{pillar.replace('_', ' ').title()} hit {v}/10"})
                break
        if any(b["id"] == "first_century" for b in badges):
            break
    # Plateau Breaker — any pillar improved by ≥1.0 from a prior stagnant pair
    if len(timeline) >= 3:
        keys = ["technical", "tactical", "physical", "mental", "decision_making"]
        for k in keys:
            scores = [s["pillars"].get(k) for s in timeline if s["pillars"].get(k) is not None]
            if len(scores) >= 3:
                if abs(scores[1] - scores[0]) < 0.2 and (scores[-1] - scores[1]) >= 1.0:
                    badges.append({
                        "id": f"plateau_breaker_{k}",
                        "label": "Plateau Breaker",
                        "detail": f"{k.replace('_', ' ').title()} broke through after a flat period (+{round(scores[-1] - scores[1], 1)})",
                        "earned_at": timeline[-1]["date"],
                    })
                    break
    # Stage Up — moved across an age development band
    bands_seen = set()
    for snap in timeline:
        age = snap.get("age")
        if age is None:
            continue
        if age <= 11:
            bands_seen.add("U11")
        elif age <= 14:
            bands_seen.add("U14")
        elif age <= 17:
            bands_seen.add("U17")
        else:
            bands_seen.add("U21")
    if len(bands_seen) >= 2:
        badges.append({
            "id": "stage_up",
            "label": "Stage Up",
            "detail": f"Crossed development band ({' → '.join(sorted(bands_seen))})",
            "earned_at": timeline[-1]["date"],
        })
    # Pro Comparison Unlocked — first time the player crosses U12 with stage-gated panels
    pro_unlocked_age = next((s["age"] for s in timeline if s.get("age") and s["age"] >= 12), None)
    if pro_unlocked_age:
        badges.append({
            "id": "pro_unlock",
            "label": "Pro Comparison Unlocked",
            "detail": f"At age {pro_unlocked_age}, full pro archetype + FIFA + StatsBomb panels unlocked",
            "earned_at": next((s["date"] for s in timeline if s.get("age") == pro_unlocked_age), timeline[-1]["date"]),
        })
    return badges


async def compute_trajectory(db, profile_doc: dict) -> dict:
    """Pull every linked report and compute a trajectory snapshot."""
    report_ids = profile_doc.get("report_ids") or []
    if not report_ids:
        return {"timeline": [], "verdict": "first_report", "badges": [], "deltas": {}, "narrative": None}

    cursor = db[REPORTS].find({"id": {"$in": report_ids}}).sort("created_at", 1)
    reports = [r async for r in cursor]
    if not reports:
        return {"timeline": [], "verdict": "first_report", "badges": [], "deltas": {}, "narrative": None}

    timeline = []
    for r in reports:
        snap = {
            "report_id": r["id"],
            "date": r.get("created_at") or now_iso(),
            "age": _age_at(r),
            "overall": _overall(r),
            "pillars": _pillar_scores(r),
        }
        snap["age_adjusted_pct"] = _age_adjusted_percentile(snap["overall"], snap["age"])
        timeline.append(snap)

    verdict = _verdict(timeline)
    badges = _compute_badges(timeline)

    # Deltas (latest vs first)
    deltas = {}
    if len(timeline) >= 2:
        first, last = timeline[0], timeline[-1]
        if first["overall"] is not None and last["overall"] is not None:
            deltas["overall_raw"] = round(last["overall"] - first["overall"], 2)
            if first.get("age_adjusted_pct") is not None and last.get("age_adjusted_pct") is not None:
                deltas["overall_age_adjusted_pct"] = round(last["age_adjusted_pct"] - first["age_adjusted_pct"], 1)
        deltas["pillars"] = {}
        for k in ("technical", "tactical", "physical", "mental", "decision_making"):
            a = first["pillars"].get(k)
            b = last["pillars"].get(k)
            if a is not None and b is not None:
                deltas["pillars"][k] = {"from": a, "to": b, "delta": round(b - a, 2)}

    return {
        "timeline": timeline,
        "verdict": verdict,
        "badges": badges,
        "deltas": deltas,
        "report_count": len(timeline),
    }


# ──────────────────────────────────────────────────────────────────────────
# Gemini Delta Narrative
# ──────────────────────────────────────────────────────────────────────────


async def generate_delta_narrative(call_gemini_text, profile_doc: dict, trajectory: dict) -> Optional[str]:
    """Ask Gemini to write a specific, evidence-based delta narrative.
    Strict guardrails: only paraphrase real data from the trajectory, no invented stats."""
    timeline = trajectory.get("timeline") or []
    if len(timeline) < 2:
        return None
    deltas = trajectory.get("deltas") or {}
    verdict = trajectory.get("verdict")

    first, last = timeline[0], timeline[-1]
    months_between = round((
        datetime.fromisoformat(last["date"].replace("Z", "+00:00")).timestamp()
        - datetime.fromisoformat(first["date"].replace("Z", "+00:00")).timestamp()
    ) / (60 * 60 * 24 * 30.5), 1)

    facts = {
        "player_name": profile_doc.get("name") or "the player",
        "months_between": months_between,
        "first_age": first.get("age"),
        "last_age": last.get("age"),
        "first_overall": first.get("overall"),
        "last_overall": last.get("overall"),
        "first_age_adjusted_pct": first.get("age_adjusted_pct"),
        "last_age_adjusted_pct": last.get("age_adjusted_pct"),
        "overall_raw_delta": deltas.get("overall_raw"),
        "age_adjusted_delta": deltas.get("overall_age_adjusted_pct"),
        "pillar_deltas": deltas.get("pillars") or {},
        "verdict": verdict,
    }

    sys_msg = (
        "You are a senior football scout writing a 'between-the-lines' progress narrative "
        "for a parent. Only reference the facts in the JSON given. Do NOT invent statistics, "
        "video moments, training drills, or pro player comparisons. Be specific, calm, and honest. "
        "If the age-adjusted percentile dropped while the raw score rose, you MUST point that out. "
        "Tone: warm, direct, no AI-hype phrases ('truly remarkable journey'…). 140–180 words. "
        "Return plain prose only — no markdown headers."
    )
    prompt = (
        f"FACTS (only use these — do not invent more):\n{json.dumps(facts, indent=2)}\n\n"
        f"Write the narrative paragraph now. Begin with the player's name. End with a single-sentence "
        f"'next focus' recommendation derived from the weakest pillar delta."
    )

    try:
        text = await call_gemini_text(
            session_id=f"trajectory-{uuid.uuid4().hex[:8]}",
            prompt=prompt,
            system_message=sys_msg,
        )
    except Exception as e:
        log.warning(f"Delta narrative failed: {e}")
        return None

    return (text or "").strip() or None


# ──────────────────────────────────────────────────────────────────────────
# Progress Pass — credits-based follow-up purchases
# ──────────────────────────────────────────────────────────────────────────


PASS_CREDITS = 3
PASS_VALID_DAYS = 365


def _pass_active(user_doc: dict) -> dict:
    """Return canonical pass state. Migrates absence/expiry transparently."""
    pp = user_doc.get("progress_pass") or {}
    if not pp:
        return {"active": False, "credits_remaining": 0, "expires_at": None}
    try:
        exp = datetime.fromisoformat((pp.get("expires_at") or "").replace("Z", "+00:00"))
        expired = exp < datetime.now(timezone.utc)
    except Exception:
        expired = True
    return {
        "active": (pp.get("credits_remaining") or 0) > 0 and not expired,
        "credits_remaining": pp.get("credits_remaining") or 0,
        "credits_total": pp.get("credits_total") or PASS_CREDITS,
        "expires_at": pp.get("expires_at"),
        "purchased_at": pp.get("purchased_at"),
    }


# ──────────────────────────────────────────────────────────────────────────
# Profile resolution helpers (used by upload endpoint elsewhere in server.py)
# ──────────────────────────────────────────────────────────────────────────


async def find_or_create_profile(db, user_id: str, player_details: dict, report_id: str) -> str:
    """Find an existing player_profile for this user by normalized name (+ position),
    else create a new one. Append report_id to its list. Returns profile id."""
    name = (player_details or {}).get("player_name") or ""
    position = (player_details or {}).get("position")
    foot = (player_details or {}).get("preferred_foot")
    age = (player_details or {}).get("age")
    normalized = _normalize_name(name)
    if not normalized:
        return ""

    existing = await db[PLAYER_PROFILES].find_one({
        "user_id": user_id,
        "normalized_name": normalized,
    })
    if existing:
        # Append report id idempotently
        if report_id and report_id not in (existing.get("report_ids") or []):
            await db[PLAYER_PROFILES].update_one(
                {"id": existing["id"]},
                {
                    "$addToSet": {"report_ids": report_id},
                    "$set": {
                        "updated_at": now_iso(),
                        "last_position": position or existing.get("last_position"),
                        "last_age": age or existing.get("last_age"),
                    },
                },
            )
        return existing["id"]

    profile = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "name": (name or "").strip(),
        "normalized_name": normalized,
        "last_position": position,
        "last_age": age,
        "preferred_foot": foot,
        "report_ids": [report_id] if report_id else [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db[PLAYER_PROFILES].insert_one(profile)
    return profile["id"]


# ──────────────────────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────────────────────


class StartProgressPassCheckoutRequest(BaseModel):
    origin_url: str = Field(min_length=8)


def build_progress_router(
    *,
    db: Any,
    get_current_user,
    call_gemini_text,
    stripe_sdk,
    pass_price_usd: float = 599.0,
    price_currency: str = "USD",
    arm_stripe_fn=None,
):
    router = APIRouter(prefix="/progress", tags=["progress"])

    # ─── Players list ────────────────────────────────────────────────────
    @router.get("/players")
    async def list_my_players(user=Depends(get_current_user)):
        cursor = db[PLAYER_PROFILES].find({"user_id": user["id"]}).sort("updated_at", -1)
        out = []
        async for p in cursor:
            out.append({
                **_public(p),
                "report_count": len(p.get("report_ids") or []),
            })
        return {"items": out, "total": len(out)}

    # ─── Player detail + trajectory ──────────────────────────────────────
    @router.get("/players/{profile_id}/trajectory")
    async def get_trajectory(profile_id: str, user=Depends(get_current_user)):
        profile = await db[PLAYER_PROFILES].find_one({"id": profile_id, "user_id": user["id"]})
        if not profile:
            raise HTTPException(404, "Player profile not found")

        traj = await compute_trajectory(db, profile)

        # Generate narrative if 2+ reports and not cached recently
        cached = profile.get("cached_trajectory") or {}
        cached_narr = cached.get("narrative")
        cached_at = cached.get("generated_at")
        regenerate = True
        if cached_at and cached_narr:
            # Re-use narrative if the cached report_count matches current
            if cached.get("report_count") == traj["report_count"]:
                regenerate = False
                traj["narrative"] = cached_narr
        if regenerate and traj["report_count"] >= 2:
            narrative = await generate_delta_narrative(call_gemini_text, profile, traj)
            traj["narrative"] = narrative
            await db[PLAYER_PROFILES].update_one(
                {"id": profile_id},
                {
                    "$set": {
                        "cached_trajectory": {
                            "narrative": narrative,
                            "report_count": traj["report_count"],
                            "verdict": traj["verdict"],
                            "generated_at": now_iso(),
                        },
                        "updated_at": now_iso(),
                    }
                },
            )

        return {"profile": _public(profile), "trajectory": traj}

    @router.delete("/players/{profile_id}")
    async def delete_my_profile(profile_id: str, user=Depends(get_current_user)):
        res = await db[PLAYER_PROFILES].delete_one({"id": profile_id, "user_id": user["id"]})
        if res.deleted_count == 0:
            raise HTTPException(404, "Player profile not found")
        return {"ok": True}

    # ─── Progress Pass status ────────────────────────────────────────────
    @router.get("/pass/status")
    async def progress_pass_status(user=Depends(get_current_user)):
        u = await db[USERS].find_one({"id": user["id"]})
        return _pass_active(u or {})

    # ─── Progress Pass embedded Stripe checkout ──────────────────────────
    @router.post("/pass/checkout")
    async def progress_pass_checkout(payload: StartProgressPassCheckoutRequest, user=Depends(get_current_user)):
        if not stripe_sdk or not arm_stripe_fn:
            raise HTTPException(503, "Stripe not configured")
        try:
            arm_stripe_fn()
            origin = payload.origin_url.rstrip("/")
            return_url = f"{origin}/dashboard?pass_session={{CHECKOUT_SESSION_ID}}"
            amount_cents = int(round(float(pass_price_usd) * 100))
            session = stripe_sdk.checkout.Session.create(
                ui_mode="embedded",
                mode="payment",
                redirect_on_completion="if_required",
                line_items=[{
                    "price_data": {
                        "currency": price_currency,
                        "product_data": {
                            "name": "ScoutMePlay – Progress Pass",
                            "description": "3 premium reports for the same player across 12 months. Track real growth over time.",
                        },
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }],
                return_url=return_url,
                metadata={
                    "kind": "progress_pass",
                    "user_id": user["id"],
                    "user_email": user["email"],
                },
                payment_intent_data={"metadata": {
                    "kind": "progress_pass",
                    "user_id": user["id"],
                    "user_email": user["email"],
                }},
            )
        except Exception as e:
            log.exception("Progress Pass checkout failed")
            raise HTTPException(500, f"Stripe error: {e}")

        # Record the pending transaction
        txn = {
            "id": str(uuid.uuid4()),
            "session_id": session.id,
            "user_id": user["id"],
            "user_email": user["email"],
            "kind": "progress_pass",
            "ui_mode": "embedded",
            "amount": float(pass_price_usd),
            "currency": price_currency,
            "credits": PASS_CREDITS,
            "payment_status": "initiated",
            "status": "open",
            "created_at": now_iso(),
        }
        await db["payment_transactions"].insert_one(txn)

        return {"client_secret": session.client_secret, "session_id": session.id}

    # ─── Activate pass after successful Stripe session (called by frontend) ─
    @router.post("/pass/activate/{session_id}")
    async def progress_pass_activate(session_id: str, user=Depends(get_current_user)):
        if not stripe_sdk or not arm_stripe_fn:
            raise HTTPException(503, "Stripe not configured")
        try:
            arm_stripe_fn()
            sess = stripe_sdk.checkout.Session.retrieve(session_id)
        except Exception as e:
            raise HTTPException(400, f"Could not verify session: {e}")

        if sess.get("payment_status") != "paid":
            raise HTTPException(402, "Payment not completed")

        # Confirm this session belongs to this user (defence in depth)
        meta = sess.get("metadata") or {}
        if meta.get("user_id") != user["id"]:
            raise HTTPException(403, "Session does not belong to this user")

        # Idempotent — if already activated by this session, return current state
        u = await db[USERS].find_one({"id": user["id"]})
        existing_pass = (u or {}).get("progress_pass") or {}
        if existing_pass.get("activation_session_id") == session_id:
            return _pass_active(u)

        now = datetime.now(timezone.utc)
        new_pass = {
            "purchased_at": now.isoformat(),
            "expires_at": (now + timedelta(days=PASS_VALID_DAYS)).isoformat(),
            "credits_total": PASS_CREDITS,
            "credits_remaining": PASS_CREDITS,
            "activation_session_id": session_id,
        }
        await db[USERS].update_one({"id": user["id"]}, {"$set": {"progress_pass": new_pass}})
        await db["payment_transactions"].update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": "paid", "status": "complete", "updated_at": now_iso()}},
        )
        return _pass_active({"progress_pass": new_pass})

    return router


# ──────────────────────────────────────────────────────────────────────────
# Helpers exported for server.py upload integration
# ──────────────────────────────────────────────────────────────────────────


async def consume_pass_credit(db, user_id: str) -> bool:
    """Try to consume a progress pass credit. Return True on success."""
    u = await db[USERS].find_one({"id": user_id})
    state = _pass_active(u or {})
    if not state["active"]:
        return False
    new_remaining = state["credits_remaining"] - 1
    await db[USERS].update_one(
        {"id": user_id},
        {"$set": {"progress_pass.credits_remaining": new_remaining}},
    )
    return True
