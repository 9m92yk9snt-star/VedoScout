"""
progress_tracking.py — Player Profiles + Trajectory Engine + Gemini Delta Narrative
+ Progress Pass credits + Tier 3 features (Archetype overlay, Video diff, Mission,
Growth card PNG).

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
import os
import re
import uuid
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, List, Optional, Dict, Tuple

from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import FileResponse
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
# Tier 3 — Archetype trajectory overlay
# ──────────────────────────────────────────────────────────────────────────


# Crude pro-archetype progression curve by age band. Each band represents the
# typical pillar score a top-archetype-matched youth player would be at, derived
# from the same calibrated 0–10 ladder the report uses. These are conservative
# senior-pro projection curves so the overlay shows the path, not hype.
ARCHETYPE_CURVE = {
    "elite":   {"U11": 7.0, "U14": 7.8, "U17": 8.6, "U21": 9.1},
    "high":    {"U11": 6.5, "U14": 7.3, "U17": 8.0, "U21": 8.6},
    "mid":     {"U11": 6.0, "U14": 6.8, "U17": 7.5, "U21": 8.0},
    "low":     {"U11": 5.5, "U14": 6.2, "U17": 6.8, "U21": 7.4},
}


def _archetype_tier_from_report(report_doc: dict) -> str:
    """Resolve which archetype curve a report should be overlaid against."""
    arch = report_doc.get("archetype") or {}
    full = report_doc.get("full_report") or {}
    ob = full.get("overall_benchmark") or {}
    tier = (ob.get("tier") or "").lower()
    if "elite" in tier:
        return "elite"
    if "pro" in tier or "academy" in tier:
        return "high"
    if "standard" in tier or "grassroots" in tier:
        return "low"
    # Fallback: use match strength
    ms = arch.get("match_strength")
    if isinstance(ms, (int, float)):
        if ms >= 8.5:
            return "elite"
        if ms >= 7.5:
            return "high"
        if ms >= 6.5:
            return "mid"
    return "mid"


def _band_for_age(age: Optional[int]) -> Optional[str]:
    if age is None:
        return None
    if age <= 11:
        return "U11"
    if age <= 14:
        return "U14"
    if age <= 17:
        return "U17"
    return "U21"


def _build_archetype_overlay(timeline: List[dict], reports: List[dict]) -> Optional[dict]:
    """Build the dataset for the side-by-side curve: player overall trajectory
    vs the typical archetype path at that age band."""
    if not timeline:
        return None
    # Use the latest report's archetype tier as the reference curve.
    tier_key = _archetype_tier_from_report(reports[-1])
    curve = ARCHETYPE_CURVE.get(tier_key) or ARCHETYPE_CURVE["mid"]
    arch_name = (reports[-1].get("archetype") or {}).get("name") or "Pro archetype"
    points = []
    for snap in timeline:
        band = _band_for_age(snap.get("age"))
        ref = curve.get(band) if band else None
        points.append({
            "date": snap["date"],
            "age": snap.get("age"),
            "band": band,
            "player_overall": snap.get("overall"),
            "archetype_overall": ref,
        })
    return {
        "archetype_name": arch_name,
        "tier_key": tier_key,
        "curve": curve,
        "points": points,
    }


# ──────────────────────────────────────────────────────────────────────────
# Tier 3 — Video-evidence diff
# ──────────────────────────────────────────────────────────────────────────


def _build_video_diff(reports: List[dict]) -> Optional[dict]:
    """Pair the FIRST and LATEST report's video_comments (with frame_url) so the
    UI can show before/after moments side-by-side."""
    if len(reports) < 2:
        return None
    first, last = reports[0], reports[-1]
    first_full = first.get("full_report") or {}
    last_full = last.get("full_report") or {}
    first_comments = [c for c in (first_full.get("video_comments") or []) if c.get("frame_url")]
    last_comments = [c for c in (last_full.get("video_comments") or []) if c.get("frame_url")]
    if not first_comments and not last_comments:
        return None
    # Up to 3 paired moments
    pairs = []
    for i in range(min(3, max(len(first_comments), len(last_comments)))):
        pair = {
            "before": first_comments[i] if i < len(first_comments) else None,
            "after": last_comments[i] if i < len(last_comments) else None,
        }
        if pair["before"] or pair["after"]:
            pairs.append(pair)
    if not pairs:
        return None
    return {
        "first_report_id": first["id"],
        "last_report_id": last["id"],
        "first_age": (first.get("player_details") or {}).get("age"),
        "last_age": (last.get("player_details") or {}).get("age"),
        "pairs": pairs,
    }


# ──────────────────────────────────────────────────────────────────────────
# Tier 3 — Mission status (closing the coaching loop)
# ──────────────────────────────────────────────────────────────────────────


def _build_mission_status(reports: List[dict]) -> Optional[dict]:
    """If the previous report declared `mission_focus`, evaluate whether those
    pillars improved in the latest report. Also auto-recommend the NEXT mission."""
    if len(reports) < 2:
        # Single-report case: still suggest the next mission so the UI has something.
        if not reports:
            return None
        last = reports[-1]
        last_pillars = _pillar_scores(last)
        if not any(v is not None for v in last_pillars.values()):
            return None
        weakest = sorted(
            [(k, v) for k, v in last_pillars.items() if v is not None],
            key=lambda kv: kv[1],
        )[:2]
        return {
            "previous_mission": None,
            "previous_results": [],
            "next_mission": [{"pillar": k, "current": v} for k, v in weakest],
        }
    prev, latest = reports[-2], reports[-1]
    prev_mission = prev.get("mission_focus") or []
    prev_pillars = _pillar_scores(prev)
    last_pillars = _pillar_scores(latest)
    results = []
    for pillar in prev_mission:
        before = prev_pillars.get(pillar)
        after = last_pillars.get(pillar)
        if before is not None and after is not None:
            results.append({
                "pillar": pillar,
                "before": before,
                "after": after,
                "delta": round(after - before, 2),
                "improved": after - before >= 0.3,
            })
    # next mission: 2 weakest pillars in latest
    weakest = sorted(
        [(k, v) for k, v in last_pillars.items() if v is not None],
        key=lambda kv: kv[1],
    )[:2]
    return {
        "previous_mission": prev_mission,
        "previous_results": results,
        "next_mission": [{"pillar": k, "current": v} for k, v in weakest],
    }


# ──────────────────────────────────────────────────────────────────────────
# Tier 3 — Growth card PNG (1080×1350 IG-ready)
# ──────────────────────────────────────────────────────────────────────────


def generate_growth_card(profile_doc: dict, trajectory: dict, out_path: Path) -> bool:
    """Render a shareable PNG summarising the player's progress."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:
        log.warning("growth card: PIL import failed: %s", e)
        return False

    timeline = trajectory.get("timeline") or []
    if not timeline:
        return False
    deltas = trajectory.get("deltas") or {}
    verdict = trajectory.get("verdict") or "first_report"
    badges = trajectory.get("badges") or []

    name = profile_doc.get("name") or "Player"
    first, last = timeline[0], timeline[-1]
    months_span = round((
        datetime.fromisoformat(last["date"].replace("Z", "+00:00")).timestamp()
        - datetime.fromisoformat(first["date"].replace("Z", "+00:00")).timestamp()
    ) / (60 * 60 * 24 * 30.5), 1) if len(timeline) >= 2 else 0

    W, H = 1080, 1350
    CREAM = (244, 239, 230)
    FOREST = (31, 79, 47)
    FOREST_POP = (45, 107, 61)
    INK = (10, 15, 13)
    MUTED = (107, 114, 128)
    AMBER = (185, 110, 17)
    VERDICT_COLOR = {
        "ahead": FOREST_POP,
        "on_track": FOREST,
        "plateau": AMBER,
        "first_report": MUTED,
    }.get(verdict, FOREST)
    VERDICT_LABEL = {
        "ahead": "AHEAD OF CURVE",
        "on_track": "ON TRACK",
        "plateau": "PLATEAU WATCH",
        "first_report": "BASELINE SET",
    }.get(verdict, "PROGRESS")

    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)

    try:
        font_xl = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 110)
        font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 56)
        font_md = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        font_xs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except Exception:
        font_xl = font_lg = font_md = font_sm = font_xs = ImageFont.load_default()

    # Forest header band
    d.rectangle([(0, 0), (W, 280)], fill=FOREST)
    d.polygon([(W - 220, 0), (W, 0), (W, 220)], fill=FOREST_POP)
    d.text((48, 36), "SCOUTMEPLAY  ·  PROGRESS", fill=CREAM, font=font_xs)
    d.text((48, 72), name.upper()[:24], fill=(255, 255, 255), font=font_lg)
    d.text((48, 148), f"{months_span} MONTH GROWTH STORY".upper() if months_span else "BASELINE REPORT",
           fill=CREAM, font=font_sm)

    # Verdict chip
    chip_y = 340
    chip_text = VERDICT_LABEL
    bbox = d.textbbox((0, 0), chip_text, font=font_md)
    cw = bbox[2] - bbox[0]
    chip_x = (W - cw - 96) // 2
    d.rectangle([(chip_x, chip_y), (chip_x + cw + 96, chip_y + 72)], fill=VERDICT_COLOR)
    d.text((chip_x + 48, chip_y + 18), chip_text, fill=(255, 255, 255), font=font_md)

    # Headline delta numbers
    raw_delta = deltas.get("overall_raw")
    pct_delta = deltas.get("overall_age_adjusted_pct")
    y = 480
    d.text((60, y), "RAW SCORE", fill=MUTED, font=font_xs)
    raw_text = f"{first.get('overall') or '-'} → {last.get('overall') or '-'}"
    d.text((60, y + 30), raw_text, fill=INK, font=font_md)
    if raw_delta is not None:
        prefix = "+" if raw_delta >= 0 else ""
        d.text((60, y + 90), f"{prefix}{raw_delta}", fill=FOREST if raw_delta >= 0 else AMBER, font=font_xl)
        d.text((60, y + 220), "POINTS GAINED" if raw_delta >= 0 else "POINTS LOST", fill=MUTED, font=font_xs)

    if pct_delta is not None:
        d.text((W // 2 + 30, y), "AGE-ADJUSTED PERCENTILE", fill=MUTED, font=font_xs)
        prefix = "+" if pct_delta >= 0 else ""
        d.text((W // 2 + 30, y + 90), f"{prefix}{pct_delta}", fill=FOREST_POP if pct_delta >= 0 else AMBER, font=font_xl)
        d.text((W // 2 + 30, y + 220), "PERCENTILE SHIFT", fill=MUTED, font=font_xs)

    # Pillar delta bars
    pillar_deltas = (deltas.get("pillars") or {})
    bars_y = 880
    d.text((60, bars_y - 36), "PILLAR DELTAS", fill=FOREST, font=font_xs)
    sorted_pillars = sorted(pillar_deltas.items(), key=lambda kv: -kv[1].get("delta", 0))
    for i, (pillar, dat) in enumerate(sorted_pillars[:5]):
        row_y = bars_y + i * 50
        d.text((60, row_y), pillar.replace("_", " ").upper(), fill=INK, font=font_xs)
        delta = dat.get("delta", 0)
        bar_x0 = 360
        bar_w = 600
        bar_h = 28
        # Background bar
        d.rectangle([(bar_x0, row_y - 4), (bar_x0 + bar_w, row_y + bar_h)], fill=(229, 231, 235))
        # Filled portion (delta scaled, max ±2.0 maps to full bar)
        max_delta = 2.0
        center = bar_x0 + bar_w // 2
        if delta >= 0:
            fill_w = min(bar_w // 2, int((delta / max_delta) * (bar_w // 2)))
            d.rectangle([(center, row_y - 4), (center + fill_w, row_y + bar_h)], fill=FOREST)
        else:
            fill_w = min(bar_w // 2, int((-delta / max_delta) * (bar_w // 2)))
            d.rectangle([(center - fill_w, row_y - 4), (center, row_y + bar_h)], fill=AMBER)
        d.line([(center, row_y - 6), (center, row_y + bar_h + 2)], fill=INK, width=2)
        delta_text = f"{'+' if delta >= 0 else ''}{delta}"
        d.text((bar_x0 + bar_w + 16, row_y), delta_text, fill=INK, font=font_xs)

    # Badge strip
    if badges:
        bg_y = H - 220
        d.text((60, bg_y), "BADGES", fill=FOREST, font=font_xs)
        x = 60
        for b in badges[:3]:
            label = (b.get("label") or "")[:18]
            bbox = d.textbbox((0, 0), label, font=font_xs)
            bw = bbox[2] - bbox[0]
            d.rectangle([(x, bg_y + 30), (x + bw + 32, bg_y + 70)], fill=FOREST)
            d.text((x + 16, bg_y + 40), label, fill=(255, 255, 255), font=font_xs)
            x += bw + 48

    d.text((60, H - 60), "SCOUTMEPLAY.COM  ·  GROUNDED IN DATA · BUILT FOR PARENTS",
           fill=MUTED, font=font_xs)

    img.save(out_path, "PNG", optimize=True)
    return True


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
    upload_dir: Path,
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

        # Pull the actual report docs once so we can build Tier 3 enrichments.
        report_ids = profile.get("report_ids") or []
        reports = []
        if report_ids:
            cursor = db[REPORTS].find({"id": {"$in": report_ids}}).sort("created_at", 1)
            reports = [r async for r in cursor]
        # Tier 3 enrichments
        traj["archetype_overlay"] = _build_archetype_overlay(traj.get("timeline") or [], reports)
        traj["video_diff"] = _build_video_diff(reports)
        traj["mission"] = _build_mission_status(reports)

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

    # ─── Growth card PNG (shareable) ─────────────────────────────────────
    @router.get("/players/{profile_id}/growth-card.png")
    async def get_growth_card(profile_id: str, user=Depends(get_current_user)):
        profile = await db[PLAYER_PROFILES].find_one({"id": profile_id, "user_id": user["id"]})
        if not profile:
            raise HTTPException(404, "Player profile not found")
        traj = await compute_trajectory(db, profile)
        if not traj.get("timeline"):
            raise HTTPException(404, "No reports linked yet")
        cards_dir = upload_dir / "growth_cards"
        cards_dir.mkdir(parents=True, exist_ok=True)
        out_path = cards_dir / f"{profile_id}_{traj['report_count']}.png"
        if not out_path.exists():
            ok = generate_growth_card(profile, traj, out_path)
            if not ok:
                raise HTTPException(500, "Failed to render growth card")
        return FileResponse(str(out_path), media_type="image/png", filename=f"{profile.get('name','player').replace(' ','_')}_growth.png")

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
        # Read live price from settings (admin-editable). Fallback to constructor default.
        live_price = pass_price_usd
        try:
            doc = await db["settings"].find_one({"key": "pass_price"})
            if doc and "value" in doc:
                live_price = float(doc["value"])
        except Exception:
            log.warning("pass_price lookup failed — falling back to constructor default")
        try:
            arm_stripe_fn()
            origin = payload.origin_url.rstrip("/")
            return_url = f"{origin}/dashboard?pass_session={{CHECKOUT_SESSION_ID}}"
            amount_cents = int(round(float(live_price) * 100))
            session = stripe_sdk.checkout.Session.create(
                ui_mode="embedded",
                mode="payment",
                redirect_on_completion="if_required",
                line_items=[{
                    "price_data": {
                        "currency": price_currency,
                        "product_data": {
                            "name": "ScoutMePlay – 12-month Plan",
                            "description": "3 premium reports for the same player across 12 months. Track real growth over time. Includes scout review on every report.",
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
            "amount": float(live_price),
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
