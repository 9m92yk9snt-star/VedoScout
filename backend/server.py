"""
Elite Football AI Scout Platform - Backend Server
"""
import os
import uuid
import json
import math
import logging
import shutil
import re
import base64
import tempfile
import asyncio
from types import SimpleNamespace
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple

import bcrypt
import secrets
import jwt as pyjwt
from dotenv import load_dotenv
import httpx

# Local modules
import r2_storage
from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form, Request, status, BackgroundTasks

# ScoutMePlay email service — Gmail SMTP + templates. Modules silently no-op
# when SMTP env vars are unset, so nothing breaks in dev/preview.
from email_service import send_email, send_email_async, send_bulk_email, email_enabled
from email_templates import (
    render_welcome_email,
    render_purchase_confirmation,
    render_bulk_email,
    render_admin_sale_notification,
)
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field, ConfigDict

from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout,
    CheckoutSessionResponse,
    CheckoutStatusResponse,
    CheckoutSessionRequest,
)

# Precision Scout — multi-signal player tracking + confident-voice pipeline
from precision_engine import (
    extract_player_fingerprint,
    extract_audio_events,
    extract_frame_at,
    build_preview_prompt as precision_build_preview_prompt,
    build_full_prompt as precision_build_full_prompt,
    scrub_hedging,
    PlayerFingerprint,
)

# Raw Stripe SDK — required for `ui_mode="embedded"` checkout (not supported by emergentintegrations wrapper).
import stripe as stripe_sdk

# PDF generation
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image as RLImage
)
from reportlab.platypus.flowables import Flowable

# ---- Setup ----
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

UPLOAD_DIR = ROOT_DIR / "uploads"
PDF_DIR = ROOT_DIR / "pdfs"
UPLOAD_DIR.mkdir(exist_ok=True)
# Bump this whenever PDF rendering changes (new sections, layout shifts, etc.).
# Each PDF is cached on disk keyed by report_id + this version, so a bump
# invalidates every stale PDF without losing the current ones.
PDF_RENDER_VERSION = 13  # v13 = Nano Banana cover + section header hero bands (Feb 27 2026)


def _pdf_cache_path(report_id: str) -> Path:
    return PDF_DIR / f"{report_id}.v{PDF_RENDER_VERSION}.pdf"


def _purge_stale_pdfs(report_id: str) -> None:
    """Delete older-version cached PDFs for a given report id so disk doesn't
    leak. Safe no-op if none exist."""
    for old in PDF_DIR.glob(f"{report_id}*.pdf"):
        if old.name != _pdf_cache_path(report_id).name:
            try:
                old.unlink()
            except Exception:
                pass


PDF_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("elite-scout")

# ---- DB ----
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# ---- Constants ----
EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
STRIPE_API_KEY = os.environ["STRIPE_API_KEY"]
# Embedded checkout uses the raw Stripe SDK and requires a real Stripe secret key.
# If STRIPE_SECRET_KEY is unset we fall back to STRIPE_API_KEY (so non-embedded flows keep working).
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY") or STRIPE_API_KEY
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
CONTACT_NOTIFY_EMAIL = os.environ.get("CONTACT_NOTIFY_EMAIL", "scoutmeplay@gmail.com")
JWT_SECRET = os.environ["JWT_SECRET_KEY"]
JWT_ALG = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXP_MIN = int(os.environ.get("JWT_EXPIRES_MINUTES", "1440"))
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
DEFAULT_PRICE = float(os.environ.get("DEFAULT_REPORT_PRICE_USD", "159"))
DEFAULT_PASS_PRICE = float(os.environ.get("DEFAULT_PASS_PRICE_USD", "399"))
DEFAULT_SINGLE_PRICE = float(os.environ.get("DEFAULT_SINGLE_PRICE_USD", "129"))
DEFAULT_PREMIUM_PRICE = float(os.environ.get("DEFAULT_PREMIUM_PRICE_USD", "29.99"))
DEFAULT_VIP_PRICE = float(os.environ.get("DEFAULT_VIP_PRICE_USD", "49.99"))
# When a subscribed user (Premium / VIP) has exhausted their monthly quota,
# they can buy additional reports at a discounted per-report rate — cheaper
# than the $129 Single Report price because they're already paying for a
# subscription. These are the defaults; admin overrides are stored in
# `settings.premium_extra_report_price` / `settings.vip_extra_report_price`.
DEFAULT_PREMIUM_EXTRA_PRICE = float(os.environ.get("DEFAULT_PREMIUM_EXTRA_USD", "89"))
DEFAULT_VIP_EXTRA_PRICE = float(os.environ.get("DEFAULT_VIP_EXTRA_USD", "59"))
DEFAULT_SOCIAL_LINKS = {
    "twitter_url":   "https://twitter.com/scoutmeplay",
    "facebook_url":  "https://www.facebook.com/scoutmeplay",
    "linkedin_url":  "https://www.linkedin.com/company/scoutmeplay",
    "instagram_url": "https://www.instagram.com/scoutmeplay",
}
PRICE_CURRENCY = os.environ.get("DEFAULT_REPORT_CURRENCY", "usd").lower()

# ---- Subscription tier catalog ----
# Single source of truth for the monthly subscription tiers shown on
# the landing page. The actual Stripe Product + Price objects are
# created idempotently on backend startup (see `_ensure_subscription_products`).
# Upload limits gate the /api/me/upload-eligibility endpoint.
SUBSCRIPTION_TIERS = {
    "premium": {
        "name": "ScoutMePlay Premium",
        "description": "2 video reports per month · Extra reports at discounted rate · Advanced AI analysis · Progress tracking · PDF downloads · Scout database visibility",
        "amount": 29.99,
        "monthly_upload_limit": 2,
    },
    "vip": {
        "name": "ScoutMePlay VIP Premium",
        "description": "4 video reports per month · Extra reports at deepest discount · Elite AI analysis · Real scout review · Direct scout contact · Personalised scout feedback",
        "amount": 49.99,
        "monthly_upload_limit": 4,
    },
}
# A user record's `subscription.tier` will be one of {"free", "premium", "vip"}.
# Free is implicit (no Stripe price/product); paid tiers are the keys above.

# Single source of truth for the PAID SCOUT ACCESS tiers — ONE-TIME LIFETIME
# purchases (not subscriptions). One user pays once → permanent database access
# until admin manually revokes. Unlimited searches + reveals for both tiers.
SCOUT_ACCESS_TIERS = {
    "scout": {
        "name": "ScoutMePlay Scout — Lifetime",
        "description": "Individual scouts & agents · Lifetime database access · Unlimited searches + reveals",
        "amount": 399.00,
        "monthly_reveals": None,  # unlimited
        "seats": 1,
        "role_hint": "scout_client",
        "one_time": True,
    },
    "club": {
        "name": "ScoutMePlay Club — Lifetime",
        "description": "Football clubs · Lifetime access · 5 seats · Unlimited searches + reveals · Priority support",
        "amount": 899.00,
        "monthly_reveals": None,  # unlimited
        "seats": 5,
        "role_hint": "club_client",
        "one_time": True,
    },
}

# ---- App ----
app = FastAPI(title="Elite Football AI Scout API")
api_router = APIRouter(prefix="/api")

# Mount uploads as static (under /api so Kubernetes ingress routes it to backend)
app.mount("/api/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# Mount landing assets (Nano Banana generated images, etc.). Created on demand
# by /app/backend/scripts/generate_landing_images.py.
_LANDING_STATIC = ROOT_DIR / "static" / "landing"
_LANDING_STATIC.mkdir(parents=True, exist_ok=True)
app.mount("/api/static/landing", StaticFiles(directory=str(_LANDING_STATIC)), name="landing-static")

# ============== MODELS ==============

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- Trial readiness catalog (position-specific scout-style checklist) ----

DATA_DIR = ROOT_DIR / "data"

try:
    with open(DATA_DIR / "trial_readiness.json", "r", encoding="utf-8") as _f:
        TRIAL_READINESS_CATALOG = json.load(_f)
except Exception as _e:  # pragma: no cover - file is shipped with the repo
    logging.warning("Could not load trial_readiness.json: %s", _e)
    TRIAL_READINESS_CATALOG = {}


def _normalise_position(raw: Optional[str]) -> Optional[str]:
    """Map a free-text position to one of the catalog position keys."""
    if not raw:
        return None
    text = str(raw).strip().lower()
    aliases = TRIAL_READINESS_CATALOG.get("_aliases", {})
    for canonical, options in aliases.items():
        for opt in options:
            if opt in text:
                return canonical
    return None


def _flatten_scores(full_report: dict) -> dict:
    """Collapse the four section objects into a single {sub_attr: score} map."""
    flat: dict = {}
    if not isinstance(full_report, dict):
        return flat
    for section in ("technical", "tactical", "physical", "mentality"):
        sec = full_report.get(section) or {}
        if not isinstance(sec, dict):
            continue
        for key, value in sec.items():
            if isinstance(value, dict) and isinstance(value.get("score"), (int, float)):
                flat[key] = value["score"]
    return flat


def compute_trial_readiness(full_report: dict, player_details: dict) -> Optional[dict]:
    """Server-side, deterministic. Reads scores + position → returns the
    checklist envelope used by both web UI and PDF.

    Returns None if we cannot map the position to the catalog (graceful fallback)."""
    if not isinstance(full_report, dict):
        return None
    position = _normalise_position((player_details or {}).get("position"))
    if not position:
        return None
    catalog = TRIAL_READINESS_CATALOG.get(position)
    if not catalog:
        return None
    scores = _flatten_scores(full_report)
    if not scores:
        return None

    items_out = []
    for item in catalog.get("items", []):
        attr_keys = item.get("attrs") or []
        attr_scores = [scores[k] for k in attr_keys if k in scores]
        if not attr_scores:
            items_out.append({
                "id": item["id"],
                "label": item["label"],
                "strong_club_met": False,
                "pro_academy_met": False,
                "no_data": True,
                "value": None,
                "strong_club_min": item.get("strong_club_min"),
                "pro_academy_min": item.get("pro_academy_min"),
            })
            continue
        logic = item.get("logic", "min")
        value = min(attr_scores) if logic == "min" else (sum(attr_scores) / len(attr_scores))
        items_out.append({
            "id": item["id"],
            "label": item["label"],
            "value": round(value, 1),
            "strong_club_min": item.get("strong_club_min"),
            "pro_academy_min": item.get("pro_academy_min"),
            "strong_club_met": value >= item.get("strong_club_min", 6),
            "pro_academy_met": value >= item.get("pro_academy_min", 7),
            "no_data": False,
        })

    if not items_out:
        return None

    countable = [i for i in items_out if not i["no_data"]]
    strong_met = sum(1 for i in countable if i["strong_club_met"])
    pro_met = sum(1 for i in countable if i["pro_academy_met"])
    total = len(countable)

    # Headline label — what the player IS ready for, today
    if total > 0 and pro_met / total >= 0.75:
        headline = "Ready for Pro Academy trial"
        readiness_tier = "pro_academy"
    elif total > 0 and strong_met / total >= 0.75:
        headline = "Ready for Strong Club trial"
        readiness_tier = "strong_club"
    elif total > 0 and strong_met / total >= 0.5:
        headline = "Building towards a Strong Club trial"
        readiness_tier = "building_strong_club"
    else:
        headline = "Foundation phase — build the basics first"
        readiness_tier = "foundation"

    return {
        "position_key": position,
        "headline": headline,
        "readiness_tier": readiness_tier,
        "strong_club_score": f"{strong_met}/{total}",
        "pro_academy_score": f"{pro_met}/{total}",
        "items": items_out,
    }


# ---- Archetype catalog + age-profile reference (server-side enrichment) ----

try:
    with open(DATA_DIR / "archetypes.json", "r", encoding="utf-8") as _f:
        ARCHETYPES_CATALOG = json.load(_f)
except Exception as _e:  # pragma: no cover
    logging.warning("Could not load archetypes.json: %s", _e)
    ARCHETYPES_CATALOG = {}

try:
    with open(DATA_DIR / "age_profiles.json", "r", encoding="utf-8") as _f:
        AGE_PROFILES_CATALOG = json.load(_f)
except Exception as _e:  # pragma: no cover
    logging.warning("Could not load age_profiles.json: %s", _e)
    AGE_PROFILES_CATALOG = {}

# Real FIFA pro dataset — pre-processed from the Kaggle FIFA 22 mirror.
# Used by the 5th lens (FIFA Data Twin) to do real similarity matching
# against 7k+ senior pros across all major leagues. See
# scripts/build_fifa_dataset.py for how this file is generated.
try:
    with open(DATA_DIR / "fifa_players.json", "r", encoding="utf-8") as _f:
        _FIFA_DB = json.load(_f)
    FIFA_PLAYERS = _FIFA_DB.get("players", [])
    FIFA_META = _FIFA_DB.get("_meta", {})
    # Bucket by position for fast same-position lookups
    FIFA_BY_POSITION: Dict[str, list] = {}
    for _p in FIFA_PLAYERS:
        FIFA_BY_POSITION.setdefault(_p.get("position", ""), []).append(_p)
    logging.info(
        "Loaded FIFA pro DB: %d players across %d positions",
        len(FIFA_PLAYERS), len(FIFA_BY_POSITION),
    )
except Exception as _e:  # pragma: no cover
    logging.warning("Could not load fifa_players.json: %s", _e)
    FIFA_PLAYERS = []
    FIFA_BY_POSITION = {}
    FIFA_META = {}

# StatsBomb Euro 2024 per-position percentiles — pre-computed offline from
# the public open-data repo. See scripts/build_statsbomb_percentiles.py.
# Used by Step 2 to calibrate the "Pro Academy" tier against real senior-pro
# performance distributions and to cite a verifiable source on the report.
try:
    with open(DATA_DIR / "statsbomb_percentiles.json", "r", encoding="utf-8") as _f:
        _SB_DB = json.load(_f)
    STATSBOMB_PCTS = _SB_DB.get("percentiles_by_position", {})
    STATSBOMB_META = _SB_DB.get("_meta", {})
    logging.info(
        "Loaded StatsBomb percentile DB: %d positions, source=%s",
        len(STATSBOMB_PCTS), STATSBOMB_META.get("source", "unknown"),
    )
except Exception as _e:  # pragma: no cover
    logging.warning("Could not load statsbomb_percentiles.json: %s", _e)
    STATSBOMB_PCTS = {}
    STATSBOMB_META = {}

# Age Intelligence Scoring System — 5 development stages from U6 to senior.
# Drives age-appropriate scoring math + stage-gating of senior-pro panels.
# See age_stages.json for the full schema.
try:
    with open(DATA_DIR / "age_stages.json", "r", encoding="utf-8") as _f:
        _AGE_STAGES_DB = json.load(_f)
    AGE_STAGES = _AGE_STAGES_DB.get("stages", [])
    AGE_LEVEL_MAPPING = _AGE_STAGES_DB.get("level_mapping", {})
    AGE_INTELLIGENCE_DISCLAIMER = _AGE_STAGES_DB.get("disclaimer", "")
    logging.info("Loaded Age Intelligence stages: %d stages", len(AGE_STAGES))
except Exception as _e:  # pragma: no cover
    logging.warning("Could not load age_stages.json: %s", _e)
    AGE_STAGES = []
    AGE_LEVEL_MAPPING = {}
    AGE_INTELLIGENCE_DISCLAIMER = ""


# ---- 4-Layer Intelligence Stack helpers -----------------------------------
# Layer 1 = static curated JSON catalog (archetypes.json)
# Layer 2 = multi-dimensional ranker (this module — Style/Build/Role/Path lenses)
# Layer 3 = Gemini narrative generator (text-only, see generate_archetype_narrative)
# Layer 4 = UI personalization (frontend ArchetypeCard + 4 lens strip)

# Age-bracket keys MUST match the keys in archetypes.json:academy_bio.
_AGE_BRACKETS = [
    (0, 10,  "8-10"),
    (11, 12, "11-12"),
    (13, 14, "13-14"),
    (15, 17, "15-17"),
    (18, 99, "18-21"),
]


def _age_bracket_key(age) -> Optional[str]:
    """Map a player's age (int|str|None) to the bracket key used in academy_bio."""
    try:
        a = int(str(age).strip())
    except (TypeError, ValueError):
        return None
    for lo, hi, key in _AGE_BRACKETS:
        if lo <= a <= hi:
            return key
    return None


# Build categories used in archetypes.json:profile.build
_BUILD_KEYS = ["small_technical", "compact_balanced", "athletic_runner", "tall_powerful"]
_BUILD_LABELS = {
    "small_technical":  "Small · technical",
    "compact_balanced": "Compact · balanced",
    "athletic_runner":  "Athletic · runner",
    "tall_powerful":    "Tall · powerful",
}


def _infer_build(scores: dict) -> str:
    """Infer the player's physical build from observed physical/technical scores.
    Pure deterministic fallback when the player_details form doesn't capture it.

    Logic (each rule contributes one signal, highest signal wins):
      - High `body_control`/`balance`/`first_touch` & low `intensity`/`courage_in_duels`
          → small_technical (Pedri / Modric-type frame)
      - High `acceleration`/`speed`/`work_rate`            → athletic_runner
      - High `courage_in_duels`/`intensity`/`body_control` → tall_powerful
      - Otherwise (everything balanced)                    → compact_balanced
    """
    if not isinstance(scores, dict) or not scores:
        return "compact_balanced"

    def avg(*keys):
        vals = [scores[k] for k in keys if isinstance(scores.get(k), (int, float))]
        return sum(vals) / len(vals) if vals else 5.0

    technical = avg("first_touch", "ball_control", "balance", "body_control")
    athletic  = avg("acceleration", "speed", "work_rate")
    powerful  = avg("courage_in_duels", "intensity", "body_control")

    # Compute deltas vs overall average
    overall = (technical + athletic + powerful) / 3.0
    candidates = [
        ("small_technical",  technical - overall),
        ("athletic_runner",  athletic  - overall),
        ("tall_powerful",    powerful  - overall),
    ]
    candidates.sort(key=lambda x: x[1], reverse=True)
    top_key, top_delta = candidates[0]
    # If no signal is meaningfully above the others, call it compact/balanced
    if top_delta < 0.4:
        return "compact_balanced"
    return top_key


# Per-position role inference. The role keys MUST match the role values used
# in archetypes.json:profile.role. Each rule maps a dominant attribute pattern
# to a role key.
_ROLE_RULES = {
    "attacking midfielder": [
        ("press_resistant_8", ["first_touch", "ball_control", "scanning"]),
        ("deep_creator",      ["passing", "scanning", "decision_making"]),
        ("chaos_creator",     ["dribbling", "shooting", "one_v_one"]),
        ("shadow_striker",    ["timing_of_runs", "shooting", "off_ball_movement"]),
        ("wide_creator",      ["dribbling", "passing", "weak_foot"]),
    ],
    "central midfielder": [
        ("deep_creator_8",     ["passing", "scanning", "decision_making"]),
        ("press_resistant_8",  ["first_touch", "ball_control", "scanning"]),
        ("creator_8",          ["passing", "shooting", "weak_foot"]),
        ("box_arriving_8",     ["timing_of_runs", "intensity", "shooting"]),
        ("box_to_box_8",       ["work_rate", "intensity", "courage_in_duels"]),
    ],
    "defensive midfielder": [
        ("tempo_6",      ["passing", "scanning", "decision_making"]),
        ("destroyer_6",  ["courage_in_duels", "intensity", "positioning"]),
        ("carrier_8",    ["ball_control", "dribbling", "first_touch"]),
        ("box_to_box_8", ["work_rate", "intensity", "timing_of_runs"]),
    ],
    "centre back": [
        ("ball_playing_cb", ["passing", "first_touch", "ball_control"]),
        ("athletic_cb",     ["speed", "acceleration", "courage_in_duels"]),
        ("leader_cb",       ["positioning", "scanning", "confidence"]),
        ("aggressive_cb",   ["intensity", "courage_in_duels", "speed"]),
    ],
    "full back": [
        ("creative_fb",   ["passing", "scanning", "first_touch"]),
        ("attacking_fb",  ["acceleration", "speed", "work_rate"]),
        ("defensive_fb",  ["positioning", "one_v_one", "courage_in_duels"]),
    ],
    "winger": [
        ("dribble_winger",   ["dribbling", "one_v_one", "agility"]),
        ("direct_winger",    ["acceleration", "speed", "shooting"]),
        ("inverted_winger",  ["shooting", "dribbling", "weak_foot"]),
        ("creator_winger",   ["passing", "weak_foot", "first_touch"]),
    ],
    "striker": [
        ("penalty_box_9", ["shooting", "off_ball_movement", "timing_of_runs"]),
        ("runner_9",      ["acceleration", "speed", "timing_of_runs"]),
        ("pressing_9",    ["work_rate", "intensity", "courage_in_duels"]),
        ("complete_9",    ["first_touch", "passing", "shooting"]),
    ],
    "goalkeeper": [
        ("sweeper",       ["passing", "scanning", "decision_making"]),
        ("shot_stopper",  ["one_v_one", "agility", "confidence"]),
    ],
}


def _infer_role(scores: dict, position: Optional[str]) -> Optional[str]:
    """Pick the role from _ROLE_RULES whose 3 key attrs the player scores
    highest on. Returns None when no scores or no rules exist for the position.
    """
    if not position or not isinstance(scores, dict) or not scores:
        return None
    rules = _ROLE_RULES.get(position)
    if not rules:
        return None
    best, best_avg = None, -1.0
    for role_key, attrs in rules:
        vals = [scores[a] for a in attrs if isinstance(scores.get(a), (int, float))]
        if not vals:
            continue
        avg_v = sum(vals) / len(vals)
        if avg_v > best_avg:
            best, best_avg = role_key, avg_v
    return best


# Mapping from overall_benchmark tier to archetype tier — used for the
# "Career-path twin" lens (i.e. an Elite Academy kid maps best to an
# `elite` archetype's journey, while a Strong-Club kid maps best to a
# `breakthrough`/`established` story).
_TIER_PATH_PREFERENCE = {
    "elite_academy":  ["elite", "world_class", "established", "breakthrough"],
    "pro_academy":    ["world_class", "elite", "established", "breakthrough"],
    "strong_club":    ["established", "breakthrough", "world_class", "elite"],
    "standard_club":  ["breakthrough", "established", "world_class", "elite"],
}


# ---- Layer 5 — FIFA Data Twin (k-NN on real Kaggle dataset) ----------------
# This is the precision lens. Real numbers, real pros, no curation.

# Attribute basket used for similarity matching. We compare ONLY on attributes
# present in BOTH the player's scoring vector and the FIFA player's `attrs`
# dict — so a missing attribute on either side is simply skipped, not zeroed.
_FIFA_MATCH_ATTRS = [
    "first_touch", "ball_control", "dribbling", "passing", "long_passing",
    "shooting", "crossing", "scanning", "vision", "decision_making",
    "composure", "positioning", "off_ball_movement", "timing_of_runs",
    "acceleration", "speed", "agility", "balance", "intensity",
    "work_rate", "courage_in_duels", "body_control",
]


def _cosine_similarity(v1: list, v2: list) -> float:
    """Cosine similarity in [-1, 1]."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


def _euclidean_distance(v1: list, v2: list) -> float:
    """Euclidean distance — used to penalize raw magnitude mismatches."""
    if not v1 or not v2 or len(v1) != len(v2):
        return float("inf")
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(v1, v2)))


def find_fifa_neighbors(
    scores: dict,
    position: Optional[str],
    player_build: Optional[str] = None,
    player_foot: Optional[str] = None,
    k: int = 5,
) -> list:
    """k-NN against the real FIFA-22 senior-pro dataset (~7,500 players).

    Returns up to `k` neighbors, each with:
      name, long_name, club, league, age, height_cm, position, build,
      preferred_foot, overall, similarity_pct, nearest_attrs.

    Similarity model is RMSE-based (NOT cosine):
        per_attr_rmse = euclidean(player_vec, pro_vec) / sqrt(n_attrs)
        similarity_pct = max(0, 100 - per_attr_rmse * 18)
    This gives an honest spread — typical 14yo vs senior pro lands 65-85%,
    with truly elite matches reaching ~88%. A hard cap of 92% keeps the
    output credible (no false "98% match" claims).
    Small +1.0/+1.5% bonuses are added for foot/build exact matches.
    """
    if not isinstance(scores, dict) or not scores or not position:
        return []
    pool = FIFA_BY_POSITION.get(position) or []
    if not pool:
        return []

    available_attrs = [a for a in _FIFA_MATCH_ATTRS if isinstance(scores.get(a), (int, float))]
    if len(available_attrs) < 6:
        return []

    neighbors = []
    for pro in pool:
        pro_attrs = pro.get("attrs") or {}
        common = [a for a in available_attrs if isinstance(pro_attrs.get(a), (int, float))]
        if len(common) < 6:
            continue
        pv = [float(scores[a]) for a in common]
        ev = [float(pro_attrs[a]) for a in common]

        # RMSE-based similarity — much more honest than pure cosine
        dist = _euclidean_distance(pv, ev)
        per_attr_rmse = dist / math.sqrt(len(common))
        base_pct = max(0.0, 100.0 - per_attr_rmse * 18.0)

        bonus = 0.0
        if player_foot and pro.get("preferred_foot") and player_foot == pro["preferred_foot"]:
            bonus += 1.0
        if player_build and pro.get("build") and player_build == pro["build"]:
            bonus += 1.5
        # Hard cap at 92% — a 14yo vs senior pro should NEVER be reported
        # as 99% similar, however well the kid scores. Caps create credibility.
        similarity_pct = round(min(92.0, base_pct + bonus), 1)

        deltas = sorted([(a, abs(scores[a] - pro_attrs[a])) for a in common], key=lambda x: x[1])
        nearest_attrs = [a for a, _ in deltas[:3]]

        neighbors.append({
            "name":           pro.get("name"),
            "long_name":      pro.get("long_name"),
            "club":           pro.get("club"),
            "league":         pro.get("league"),
            "age":            pro.get("age"),
            "height_cm":      pro.get("height_cm"),
            "position":       pro.get("position"),
            "build":          pro.get("build"),
            "preferred_foot": pro.get("preferred_foot"),
            "overall":        pro.get("overall"),
            "similarity_pct": similarity_pct,
            "nearest_attrs":  nearest_attrs,
        })

    if not neighbors:
        return []
    # Best similarity first; tie-break by FIFA overall (famous pros surface first)
    neighbors.sort(key=lambda n: (-n["similarity_pct"], -n["overall"]))
    return neighbors[:k]




# ---- Step 2 — StatsBomb Euro 2024 calibration ------------------------------
# Map each ScoutMePlay attribute to the StatsBomb per-90 metric that best
# proxies it. The kid's 0-10 score on the LHS is then anchored to where it
# would sit in the senior-pro distribution on the RHS (e.g. "your 8/10 in
# passing matches the top 25% of Euro 2024 starters at this position").

_SCORE_TO_STATSBOMB = {
    "passing":              "pass_completion_pct",
    "long_passing":         "progressive_passes_per_90",
    "scanning":             "passes_into_final_third_per_90",
    "decision_making":      "progressive_passes_per_90",
    "vision":               "key_passes_per_90",
    "positioning":          "interceptions_per_90",
    "off_ball_movement":    "shots_per_90",
    "timing_of_runs":       "goals_per_90",
    "shooting":             "xg_per_90",
    "finishing":            "goals_per_90",
    "dribbling":            "dribbles_completed_per_90",
    "one_v_one":            "dribble_completion_pct",
    "intensity":            "pressures_per_90",
    "work_rate":            "ball_recoveries_per_90",
    "courage_in_duels":     "duels_won_per_90",
    "ball_recoveries":      "ball_recoveries_per_90",
}

# Human-friendly labels for the calibration UI / PDF
_STATSBOMB_METRIC_LABELS = {
    "pass_completion_pct":            "Pass completion %",
    "passes_per_90":                  "Passes per 90",
    "progressive_passes_per_90":      "Progressive passes per 90",
    "passes_into_final_third_per_90": "Passes into final third per 90",
    "key_passes_per_90":              "Key passes per 90",
    "shots_per_90":                   "Shots per 90",
    "goals_per_90":                   "Goals per 90",
    "xg_per_90":                      "Expected goals (xG) per 90",
    "dribbles_attempted_per_90":      "Dribbles attempted per 90",
    "dribbles_completed_per_90":      "Dribbles completed per 90",
    "duels_won_per_90":               "Duels won per 90",
    "ball_recoveries_per_90":         "Ball recoveries per 90",
    "interceptions_per_90":           "Interceptions per 90",
    "pressures_per_90":               "Pressures per 90",
    "dribble_completion_pct":         "Dribble completion %",
    "duel_win_pct":                   "Duel-win %",
}


def _score_to_percentile_bucket(score: float) -> Tuple[str, str]:
    """Map a 0-10 ScoutMePlay score to a Euro 2024 percentile bucket.

    The calibration is intentionally generous on the upper end so we don't
    accidentally tell every 8/10 they're "elite" — we anchor 7=median pro,
    8=top-quartile pro, 9=top-decile pro.
    """
    if score >= 9.0:
        return "p90", "Top 10% of Euro 2024 starters"
    if score >= 8.0:
        return "p75", "Top 25% of Euro 2024 starters"
    if score >= 7.0:
        return "p50", "Median Euro 2024 starter"
    if score >= 6.0:
        return "p25", "Bottom 25% of Euro 2024 starters"
    return "below_p25", "Below Euro 2024 starter level"


def compute_statsbomb_calibration(full_report: dict, player_details: dict) -> Optional[dict]:
    """Build a per-attribute calibration showing where the player's scores
    land against Euro 2024 senior-pro distributions for their position.

    Output:
      {
        position: "...",
        position_n: 14,
        source: "...",
        rows: [
          {
            attribute_key, attribute_label, score (0-10),
            statsbomb_metric, statsbomb_metric_label,
            bucket ("p25"|"p50"|"p75"|"p90"|"below_p25"),
            bucket_label ("Top 25% of Euro 2024 starters"),
            pro_p25, pro_p50, pro_p75, pro_p90  (raw per-90 values)
          },
          ...
        ],
        summary: { p90: 3, p75: 5, p50: 4, p25: 1, below_p25: 0 }
      }

    Returns None when the dataset has no rows for that position.
    """
    if not STATSBOMB_PCTS or not isinstance(full_report, dict):
        return None
    position = _normalise_position((player_details or {}).get("position"))
    if not position:
        return None
    pcts = STATSBOMB_PCTS.get(position)
    if not pcts:
        return None
    scores = _flatten_scores(full_report)
    if not scores:
        return None

    rows = []
    bucket_counts = {"p90": 0, "p75": 0, "p50": 0, "p25": 0, "below_p25": 0}
    for attr_key, sb_metric in _SCORE_TO_STATSBOMB.items():
        score = scores.get(attr_key)
        if not isinstance(score, (int, float)):
            continue
        metric_pcts = pcts.get(sb_metric)
        if not isinstance(metric_pcts, dict):
            continue
        bucket, label = _score_to_percentile_bucket(score)
        bucket_counts[bucket] += 1
        rows.append({
            "attribute_key":          attr_key,
            "attribute_label":        attr_key.replace("_", " ").title(),
            "score":                  score,
            "statsbomb_metric":       sb_metric,
            "statsbomb_metric_label": _STATSBOMB_METRIC_LABELS.get(sb_metric, sb_metric),
            "bucket":                 bucket,
            "bucket_label":           label,
            "pro_p25":                metric_pcts.get("p25"),
            "pro_p50":                metric_pcts.get("p50"),
            "pro_p75":                metric_pcts.get("p75"),
            "pro_p90":                metric_pcts.get("p90"),
        })

    if not rows:
        return None

    return {
        "position":     position,
        "position_n":   pcts.get("_n_players"),
        "min_minutes":  pcts.get("_min_minutes_filter"),
        "source":       STATSBOMB_META.get("source", "StatsBomb Open Data"),
        "source_url":   STATSBOMB_META.get("source_url", "https://github.com/statsbomb/open-data"),
        "competition":  STATSBOMB_META.get("competition", "UEFA Euro 2024"),
        "matches":      STATSBOMB_META.get("matches"),
        "license":      STATSBOMB_META.get("license"),
        "methodology":  STATSBOMB_META.get("methodology"),
        "rows":         rows,
        "summary":      bucket_counts,
    }




# =============================================================================
# AGE INTELLIGENCE SCORING SYSTEM
# =============================================================================
# Five development stages × deterministic 9-score system × stage-gating.
# Everything below is PURE PYTHON math over the AI scores — no LLM involved.
#
# Why this exists:
#   The Gemini prompt has a SOFT age instruction (the model is *told* to grade
#   age-appropriately). But soft instructions are unreliable. This module
#   enforces age-appropriateness in the post-processing math: a U7's
#   "decision_making" is weighted differently than a U17's, period.

# Default scoring weights for the 4 high-level scoring sections used to
# produce the technical/tactical/physical/mentality summary scores.
_SECTION_ATTRS = {
    "technical":  ["first_touch", "ball_control", "dribbling", "passing", "shooting",
                   "weak_foot", "one_v_one", "long_passing"],
    "tactical":   ["positioning", "off_ball_movement", "scanning", "decision_making",
                   "timing_of_runs", "game_understanding"],
    "physical":   ["acceleration", "speed", "balance", "agility", "intensity",
                   "body_control"],
    "mentality":  ["confidence", "work_rate", "courage_in_duels", "response_to_mistakes",
                   "competitive_mindset", "focus", "composure"],
}


def resolve_age_stage(age) -> Optional[dict]:
    """Return the development-stage dict for the given age, or None if no
    stages are loaded or the age is unparseable."""
    if not AGE_STAGES:
        return None
    try:
        a = int(str(age).strip())
    except (TypeError, ValueError):
        return None
    for stage in AGE_STAGES:
        if int(stage.get("age_min", 0)) <= a <= int(stage.get("age_max", 99)):
            return stage
    return None


def next_age_stage(current_stage: Optional[dict]) -> Optional[dict]:
    """Return the stage that comes AFTER the current one, or None if the
    player is already at the final stage."""
    if not current_stage or not AGE_STAGES:
        return None
    cur_idx = next((i for i, s in enumerate(AGE_STAGES) if s["id"] == current_stage["id"]), -1)
    if cur_idx < 0 or cur_idx + 1 >= len(AGE_STAGES):
        return None
    return AGE_STAGES[cur_idx + 1]


def _weighted_mean(scores: dict, attrs: list, downweight: Optional[list] = None) -> Optional[float]:
    """Mean of `attrs` from `scores`, where attrs in `downweight` get half-weight."""
    if not attrs:
        return None
    downweight_set = set(downweight or [])
    weighted_sum = 0.0
    total_weight = 0.0
    for a in attrs:
        v = scores.get(a)
        if not isinstance(v, (int, float)):
            continue
        w = 0.5 if a in downweight_set else 1.0
        weighted_sum += v * w
        total_weight += w
    if total_weight == 0:
        return None
    return round(weighted_sum / total_weight, 2)


def _resolve_level(tier: Optional[str], stage_id: Optional[str], overall: Optional[float]) -> Optional[dict]:
    """Map (tier, stage, overall_score) → one of 8 human-friendly levels:
    Beginner / Grassroots / Club / Strong Club / Academy / Elite Academy /
    Semi-Pro / Professional. Returns {label, definition} or None."""
    if not tier or not stage_id or not AGE_LEVEL_MAPPING:
        return None
    rules = AGE_LEVEL_MAPPING.get("rules", [])
    overall_f = float(overall) if isinstance(overall, (int, float)) else 0.0
    for rule in rules:
        if rule.get("when_tier") != tier:
            continue
        if stage_id not in (rule.get("in_stages") or []):
            continue
        if not (float(rule.get("min_overall", 0.0)) <= overall_f <= float(rule.get("max_overall", 10.0))):
            continue
        label = rule["level"]
        return {
            "label":      label,
            "definition": (AGE_LEVEL_MAPPING.get("level_definitions") or {}).get(label, ""),
            "tier":       tier,
            "stage_id":   stage_id,
        }
    return None


def compute_age_intelligence(full_report: dict, player_details: dict) -> Optional[dict]:
    """The 9-score Age Intelligence block + stage gates + disclaimers.

    Returns:
      {
        stage: {id, label, age_band, headline, what_we_evaluate[], what_we_dont_evaluate[]},
        next_stage: {...} | None,
        scores: {
          current_age_score, position_specific_score, next_level_readiness_score,
          pro_style_match_score, technical_score, tactical_score, physical_score,
          mentality_body_language_score, development_priority_score
        },
        level: {label, definition, tier, stage_id} | None,
        panels: {show_fifa_knn, show_statsbomb, show_trial_readiness, ...},
        panel_replacement_messages: {fifa_knn, statsbomb, trial_readiness},
        evaluation_basis: "U12-U14 / Game Understanding Stage",
        what_we_evaluated:    [...],
        what_we_could_not_evaluate: [...],
        disclaimer: "<full disclaimer text>"
      }

    Returns None when we cannot resolve the stage or have no scores.
    """
    if not isinstance(full_report, dict) or not isinstance(player_details, dict):
        return None
    stage = resolve_age_stage(player_details.get("age"))
    if not stage:
        return None
    scores = _flatten_scores(full_report)
    if not scores:
        return None

    focus_attrs   = stage.get("focus_attributes") or []
    downweight    = stage.get("downweight_attributes") or []

    # 1. current_age_score — weighted mean over stage focus attrs (downweighted
    #    ones contribute half). This is the canonical "score for the kid AT
    #    THIS STAGE" — different from the AI's overall_development score.
    current_age_score = _weighted_mean(scores, focus_attrs, downweight=downweight)

    # 2. position_specific_score — re-weight using the position's priority
    #    attribute weights from age_profiles.json, but ONLY count attrs that
    #    appear in the stage's focus list (stage-aware).
    position_specific_score = None
    position = _normalise_position(player_details.get("position"))
    if position and AGE_PROFILES_CATALOG.get(position):
        priority_attrs = (AGE_PROFILES_CATALOG[position].get("priority_attributes") or [])
        weighted_sum, total_weight = 0.0, 0.0
        for spec in priority_attrs:
            k, w = spec.get("key"), float(spec.get("weight", 1))
            if k not in scores or not isinstance(scores[k], (int, float)):
                continue
            # If a position-priority attr is in the stage's downweight list,
            # halve its weight so we don't over-score U7 tactics.
            if k in (downweight or []):
                w = w * 0.5
            weighted_sum += scores[k] * w
            total_weight += w
        if total_weight > 0:
            position_specific_score = round(weighted_sum / total_weight, 2)

    # 3. next_level_readiness_score — average of the NEXT stage's focus
    #    attributes mapped to the kid's current scores. Returns "how close
    #    is this kid to the next stage's expectations" as a 0-10.
    next_stage = next_age_stage(stage)
    next_level_readiness_score = None
    if next_stage:
        next_level_readiness_score = _weighted_mean(scores, next_stage.get("focus_attributes") or [])

    # 4. pro_style_match_score — re-emit FIFA k-NN top-match similarity as
    #    a 0-10 (similarity_pct / 10). ONLY when the stage allows it; for
    #    U6-U11 we surface None and the UI shows a friendly stage message.
    pro_style_match_score = None
    panels = stage.get("panels") or {}
    if panels.get("show_fifa_knn"):
        # We're not running k-NN here (match_archetype owns that). We surface
        # whatever was computed there during _serialize_report by reading
        # from the archetype block — left to the caller to thread in.
        pro_style_match_score = None  # threaded from archetype.lenses.fifa.score by caller

    # 5-8. Section means (technical/tactical/physical/mentality_body_language).
    technical_score              = _weighted_mean(scores, _SECTION_ATTRS["technical"],  downweight=downweight)
    tactical_score               = _weighted_mean(scores, _SECTION_ATTRS["tactical"],   downweight=downweight)
    physical_score               = _weighted_mean(scores, _SECTION_ATTRS["physical"],   downweight=downweight)
    mentality_body_language_score = _weighted_mean(scores, _SECTION_ATTRS["mentality"], downweight=downweight)

    # 9. development_priority_score — how trainable the kid's WEAK areas are.
    #    Take the 3 weakest stage-focus attrs and return 10 - their average
    #    (so weaker = more headroom = higher priority to train).
    development_priority_score = None
    focus_scores_present = sorted(
        [scores[a] for a in focus_attrs if isinstance(scores.get(a), (int, float))]
    )
    if len(focus_scores_present) >= 3:
        weakest = focus_scores_present[:3]
        development_priority_score = round(10.0 - (sum(weakest) / len(weakest)), 2)
    elif focus_scores_present:
        development_priority_score = round(10.0 - (sum(focus_scores_present) / len(focus_scores_present)), 2)

    # Level mapping (the 8-level human-friendly scale)
    overall_benchmark = (full_report.get("overall_benchmark") or {})
    tier = (overall_benchmark.get("tier") or "").strip().lower() or None
    overall_dev = (full_report.get("scores") or {}).get("overall_development")
    level = _resolve_level(tier, stage["id"], overall_dev)

    # What the AI ACTUALLY could vs could not evaluate (read from the AI's
    # own per-skill `cannot_evaluate` flags + the stage's
    # `what_we_dont_evaluate` framing). This is the truthful version of the
    # AI's report — surfaced prominently on every page.
    could_not_evaluate_from_ai = []
    for section in ("technical", "tactical", "physical", "mentality"):
        sec = full_report.get(section) or {}
        if not isinstance(sec, dict):
            continue
        for k, v in sec.items():
            if isinstance(v, dict) and v.get("cannot_evaluate"):
                reason = v.get("evaluable_reason") or "Not observable from this footage."
                could_not_evaluate_from_ai.append({
                    "key":    k,
                    "label":  k.replace("_", " ").title(),
                    "reason": reason,
                })

    return {
        "stage": {
            "id":                    stage["id"],
            "label":                 stage["label"],
            "age_band":              stage["age_band"],
            "headline":              stage.get("headline", ""),
            "what_we_evaluate":      stage.get("what_we_evaluate", []),
            "what_we_dont_evaluate": stage.get("what_we_dont_evaluate", []),
        },
        "next_stage": ({
            "id":       next_stage["id"],
            "label":    next_stage["label"],
            "age_band": next_stage["age_band"],
        } if next_stage else None),
        "scores": {
            "current_age_score":             current_age_score,
            "position_specific_score":       position_specific_score,
            "next_level_readiness_score":    next_level_readiness_score,
            "pro_style_match_score":         pro_style_match_score,
            "technical_score":               technical_score,
            "tactical_score":                tactical_score,
            "physical_score":                physical_score,
            "mentality_body_language_score": mentality_body_language_score,
            "development_priority_score":    development_priority_score,
        },
        "level":                       level,
        "panels":                      panels,
        "panel_replacement_messages":  stage.get("panel_replacement_messages") or {},
        "evaluation_basis":            f"{stage['age_band']} / {stage['label']}",
        "what_we_evaluated":           stage.get("what_we_evaluate", []),
        "what_we_could_not_evaluate":  stage.get("what_we_dont_evaluate", []),
        "what_ai_could_not_evaluate":  could_not_evaluate_from_ai,
        "disclaimer":                  AGE_INTELLIGENCE_DISCLAIMER,
    }


def apply_stage_gating(serialized: dict, age_intel: Optional[dict]) -> None:
    """Mutate `serialized` to hide senior-pro panels for younger stages.
    Strict rule: U6-U11 must NOT show direct senior-pro comparisons; they
    only see archetype style references framed as long-term development.

    This implements scope (b) requirement #3.
    """
    if not isinstance(serialized, dict) or not age_intel:
        return
    panels = age_intel.get("panels") or {}

    # 1. FIFA k-NN — strip the fifa lens + the top-5 neighbours panel
    if not panels.get("show_fifa_knn") and isinstance(serialized.get("archetype"), dict):
        arch = serialized["archetype"]
        if isinstance(arch.get("lenses"), dict) and "fifa" in arch["lenses"]:
            del arch["lenses"]["fifa"]
        arch["fifa_neighbors"] = []
        arch["fifa_db_meta"] = None
        # Tag so the UI can show a friendly "reserved for U12+" message
        arch["fifa_panel_gated_message"] = (age_intel.get("panel_replacement_messages") or {}).get("fifa_knn")

    # 2. StatsBomb Pro Calibration — hide entirely for U6-U11
    if not panels.get("show_statsbomb"):
        serialized["statsbomb_calibration_gated_message"] = (
            (age_intel.get("panel_replacement_messages") or {}).get("statsbomb")
        )
        serialized["statsbomb_calibration"] = None

    # 3. Trial readiness — hide for U6-U11 (replaced with friendly message)
    if not panels.get("show_trial_readiness"):
        serialized["trial_readiness_gated_message"] = (
            (age_intel.get("panel_replacement_messages") or {}).get("trial_readiness")
        )
        serialized["trial_readiness"] = None

    # 4. Career brief — clear it from archetype for U6-U8 (we still keep the
    # bio chunk so the kid sees how the pro started). For U9+ we keep it.
    if (not panels.get("show_career_brief")) and isinstance(serialized.get("archetype"), dict):
        serialized["archetype"]["career_brief"] = ""

    # 5. Surface the "pro_style_match_score" from the (un-gated) archetype
    # block so the AgeIntelligence scoreboard can render a real number when
    # FIFA panels are allowed.
    if panels.get("show_fifa_knn") and isinstance(serialized.get("archetype"), dict):
        fifa_lens = (serialized["archetype"].get("lenses") or {}).get("fifa") or {}
        sim_pct = fifa_lens.get("similarity_pct")
        if isinstance(sim_pct, (int, float)):
            age_intel["scores"]["pro_style_match_score"] = round(float(sim_pct) / 10.0, 2)




def match_archetype(full_report: dict, player_details: dict) -> Optional[dict]:
    """4-Lens deterministic matcher.

    For every candidate archetype in the player's position, compute four
    independent scores:
      - style_score  — weighted average across the archetype's `anchor` attrs
      - build_score  — 10 if archetype.profile.build == inferred player build
      - role_score   — 10 if archetype.profile.role  == inferred player role
      - path_score   — based on alignment between archetype.tier and the
                       player's overall_benchmark.tier
      - foot_bonus   — +1 when archetype.profile.foot matches the player's
                       preferred_foot (or "both")

    Then pick ONE best archetype per lens. Returns:
      {
        id, name, club, league, tier, traits, summary,    # primary (style winner)
        match_strength, evidence, developing,
        lenses: {
          style: { ...archetype meta..., score, why },
          build: { ...archetype meta..., score, why },
          role:  { ...archetype meta..., score, why },
          path:  { ...archetype meta..., score, why }
        },
        academy_bio_chunk: "<bio for the age bracket from the STYLE winner>",
        age_bracket_used: "13-14",
        alternatives: [ next 2 style candidates ]
      }
    """
    if not isinstance(full_report, dict):
        return None
    position = _normalise_position((player_details or {}).get("position"))
    if not position:
        return None
    candidates = ARCHETYPES_CATALOG.get(position) or []
    if not candidates:
        return None
    scores = _flatten_scores(full_report)
    if not scores:
        return None

    # ---- Inferred player profile (build/role/foot/tier) -----------------
    player_foot = str((player_details or {}).get("preferred_foot") or "").strip().lower()
    player_build = _infer_build(scores)
    player_role = _infer_role(scores, position)
    player_tier = ((full_report.get("overall_benchmark") or {}).get("tier") or "").strip().lower()
    path_order = _TIER_PATH_PREFERENCE.get(player_tier, ["world_class", "elite", "established", "breakthrough"])

    ranked = []
    for arch in candidates:
        anchor = arch.get("anchor") or []
        weighted = []
        for entry in anchor:
            if isinstance(entry, dict):
                weighted.append((entry.get("key"), float(entry.get("weight", 1))))
            else:
                weighted.append((entry, 1.0))
        weighted = [(k, w) for k, w in weighted if k in scores]
        if not weighted:
            continue

        # --- Lens 1: Style (weighted average across signature attrs) ----
        total_w = sum(w for _, w in weighted)
        style_score = sum(scores[k] * w for k, w in weighted) / total_w

        # --- Signature gate (existing behaviour preserved) ---------------
        sigs = arch.get("signature_attrs") or []
        passes_signature = True
        for sig in sigs:
            if isinstance(sig, dict):
                sig_key, sig_min = sig.get("key"), sig.get("min", 7)
            else:
                sig_key, sig_min = sig, 7
            if scores.get(sig_key, 0) < sig_min:
                passes_signature = False
                break

        # --- Profile-based lenses ---------------------------------------
        profile = arch.get("profile") or {}
        arch_foot  = str(profile.get("foot")  or "").lower()
        arch_build = str(profile.get("build") or "").lower()
        arch_role  = str(profile.get("role")  or "").lower()

        # Foot bonus: +1.0 if exact match, +0.5 if either side is "both"
        if player_foot and arch_foot:
            if player_foot == arch_foot:
                foot_bonus = 1.0
            elif player_foot == "both" or arch_foot == "both":
                foot_bonus = 0.5
            else:
                foot_bonus = 0.0
        else:
            foot_bonus = 0.0

        # Build lens: 10 if exact match, 6 if "compact_balanced" (neutral)
        if arch_build and player_build:
            if arch_build == player_build:
                build_score = 10.0
            elif "compact_balanced" in (arch_build, player_build):
                build_score = 7.0  # neutral build always partially fits
            else:
                build_score = 4.0
        else:
            build_score = 5.0

        # Role lens
        if arch_role and player_role:
            role_score = 10.0 if arch_role == player_role else 4.0
        else:
            role_score = 5.0

        # Path lens — preference list maps tier → ordered archetype tiers
        arch_tier = str(arch.get("tier") or "").lower()
        if arch_tier in path_order:
            # Position 0 = best fit (10), last = lowest fit (~6)
            idx = path_order.index(arch_tier)
            path_score = max(6.0, 10.0 - 1.2 * idx)
        else:
            path_score = 6.0

        # Evidence — top-3 attrs by (score * weight) contribution
        contribs = sorted(
            [{"key": k, "label": k.replace("_", " ").title(), "score": scores[k], "weight": w}
             for k, w in weighted],
            key=lambda x: x["score"] * x["weight"],
            reverse=True,
        )[:3]

        ranked.append({
            "id":             arch["id"],
            "name":           arch["name"],
            "club":           arch.get("club"),
            "league":         arch.get("league"),
            "tier":           arch.get("tier"),
            "traits":         arch.get("traits") or [],
            "summary":        arch.get("summary") or "",
            "profile":        profile,
            "academy_bio":    arch.get("academy_bio") or {},
            "career_brief":   arch.get("career_brief") or "",
            "match_strength": round(style_score, 2),
            "evidence":       contribs,
            "passes_signature": passes_signature,
            "_style":  round(style_score + foot_bonus * 0.3, 3),
            "_build":  round(build_score + foot_bonus, 3),
            "_role":   round(role_score + foot_bonus, 3),
            "_path":   round(path_score + foot_bonus * 0.3, 3),
        })

    if not ranked:
        return None

    # ---- Style winner (primary archetype) -------------------------------
    # Prefer signature-passing matches first, then by style score
    by_style = sorted(ranked, key=lambda x: (x["passes_signature"], x["_style"]), reverse=True)
    primary = by_style[0]

    age_bracket = _age_bracket_key((player_details or {}).get("age"))
    academy_bio_chunk = None
    if primary.get("academy_bio") and age_bracket:
        academy_bio_chunk = primary["academy_bio"].get(age_bracket)

    # ---- Lens twins (independent picks across the 4 lenses) -------------
    def _pick(metric_key, exclude_id=None):
        pool = [c for c in ranked if c["id"] != exclude_id] if exclude_id else ranked
        if not pool:
            return None
        winner = max(pool, key=lambda x: x[metric_key])
        # Clip the displayed lens score to the [0, 10] contract advertised
        # on the UI (the raw metric can exceed 10 due to the foot bonus).
        raw = float(winner[metric_key])
        display = round(min(10.0, max(0.0, raw)), 2)
        return {
            "id":    winner["id"],
            "name":  winner["name"],
            "club":  winner["club"],
            "league": winner["league"],
            "tier":  winner["tier"],
            "summary": winner["summary"],
            "score": display,
            "profile": winner.get("profile") or {},
        }

    style_pick = _pick("_style")
    build_pick = _pick("_build")
    role_pick  = _pick("_role")
    path_pick  = _pick("_path")

    # ---- Layer 5: FIFA Data Twin (real k-NN against ~7,500 senior pros) ----
    fifa_neighbors = find_fifa_neighbors(
        scores=scores,
        position=position,
        player_build=player_build,
        player_foot=player_foot,
        k=5,
    )
    fifa_top = fifa_neighbors[0] if fifa_neighbors else None
    fifa_lens = None
    if fifa_top:
        # Build the human-readable "why" — list the 3 attrs where kid & pro are closest
        nearest_labels = ", ".join(a.replace("_", " ") for a in fifa_top.get("nearest_attrs", []))
        fifa_lens = {
            "lens": "fifa",
            "lens_label": "FIFA data twin",
            "name":   fifa_top["name"],
            "long_name": fifa_top.get("long_name"),
            "club":   fifa_top["club"],
            "league": fifa_top["league"],
            "tier":   None,
            "age":    fifa_top.get("age"),
            "height_cm": fifa_top.get("height_cm"),
            "build":  fifa_top.get("build"),
            "preferred_foot": fifa_top.get("preferred_foot"),
            "overall": fifa_top.get("overall"),
            # Score advertised on a 0-10 scale to match other lenses
            "score":  round(fifa_top["similarity_pct"] / 10.0, 2),
            "similarity_pct": fifa_top["similarity_pct"],
            "nearest_attrs": fifa_top.get("nearest_attrs", []),
            "why": (
                f"Nearest senior pro by 22-attribute similarity search across "
                f"{len(FIFA_PLAYERS):,} FIFA-rated pros — closest on "
                f"{nearest_labels or 'multiple attributes'}."
            ),
        }

    lenses = {
        "style": {
            "lens": "style",
            "lens_label": "Style twin",
            "why": "Plays in the same mould — same signature attributes drive both players.",
            **(style_pick or {}),
        },
        "build": {
            "lens": "build",
            "lens_label": "Build twin",
            "why": f"Same physical build — {_BUILD_LABELS.get(player_build, player_build)}"
                   + (f", {player_foot}-footed" if player_foot else "")
                   + ".",
            **(build_pick or {}),
        },
        "role": {
            "lens": "role",
            "lens_label": "Role twin",
            "why": f"Same on-pitch role — {(player_role or 'inferred from scores').replace('_', ' ')}.",
            **(role_pick or {}),
        },
        "path": {
            "lens": "path",
            "lens_label": "Career-path twin",
            "why": f"Likely development arc — currently sitting at {player_tier.replace('_', ' ') or 'this tier'}.",
            **(path_pick or {}),
        },
    }
    if fifa_lens:
        lenses["fifa"] = fifa_lens

    # ---- Developing fallback (unchanged behaviour) ----------------------
    if (not primary["passes_signature"]) or (primary["match_strength"] < 6.0):
        return {
            "id": None,
            "name": "Developing — no clear archetype yet",
            "traits": [],
            "summary": (
                "Scores are still developing across this position's signature attributes. "
                "A clearer stylistic identity will emerge as the player's strengths sharpen."
            ),
            "match_strength": primary["match_strength"],
            "developing": True,
            "evidence": primary.get("evidence", []),
            "age_bracket_used": age_bracket,
            "academy_bio_chunk": None,
            "lenses": lenses,
            "alternatives": [
                {k: r[k] for k in ("id", "name", "club", "league", "tier", "match_strength")}
                for r in by_style[1:4]
            ],
            "inferred_build": player_build,
            "inferred_role":  player_role,
            "preferred_foot": player_foot or None,
            "fifa_neighbors": fifa_neighbors,
            "fifa_db_meta": {
                "source":  FIFA_META.get("source_dataset", "FIFA 22 dataset"),
                "size":    len(FIFA_PLAYERS),
                "scale":   "0-10 (FIFA 0-99 normalised)",
            },
        }

    # ---- Strip private metric keys before returning ---------------------
    def _clean(d):
        return {k: v for k, v in d.items() if not k.startswith("_") and k != "passes_signature"}

    out = _clean(primary)
    out["developing"]        = False
    out["academy_bio_chunk"] = academy_bio_chunk
    out["age_bracket_used"]  = age_bracket
    out["lenses"]            = lenses
    out["alternatives"]      = [
        {k: r[k] for k in ("id", "name", "club", "league", "tier", "match_strength")}
        for r in by_style[1:4]
    ]
    out["inferred_build"] = player_build
    out["inferred_role"]  = player_role
    out["preferred_foot"] = player_foot or None
    # Ship the top-5 FIFA neighbours separately so the UI can render an
    # "Other close FIFA matches" strip beneath the headline lens.
    out["fifa_neighbors"] = fifa_neighbors
    out["fifa_db_meta"]   = {
        "source":  FIFA_META.get("source_dataset", "FIFA 22 dataset"),
        "size":    len(FIFA_PLAYERS),
        "scale":   "0-10 (FIFA 0-99 normalised)",
    }
    return out


# ---- Layer 3 — Gemini-powered narrative ------------------------------------

def _pro_name_from_archetype(archetype: dict) -> str:
    """Extract just the pro's name from an archetype name like
    'Modric-type composer' → 'Modric', 'Lamine Yamal-type wonderkid' → 'Lamine Yamal'.
    Splits on the first '-type' suffix marker.
    """
    raw = (archetype or {}).get("name") or ""
    # Common pattern: '<Name>-type <descriptor>' — keep everything BEFORE '-type'
    if "-type" in raw:
        return raw.split("-type", 1)[0].strip()
    # Fallback: legacy entries that may already be just 'Name'
    return raw.strip()


async def call_gemini_text(session_id: str, prompt: str, system_message: str = "") -> str:
    """Fast text-only Gemini call. No file_contents. Returns raw text."""
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=system_message or (
            "You are a precise football writer. You ONLY use facts that are explicitly given to you. "
            "You NEVER invent biographical facts. You write plain English, no jargon."
        ),
    ).with_model("gemini", "gemini-2.5-flash")
    user_message = UserMessage(text=prompt, file_contents=[])
    response = await chat.send_message(user_message)
    return response if isinstance(response, str) else str(response)


async def generate_archetype_narrative(player_details: dict, full_report: dict, archetype: dict) -> Optional[str]:
    """Produce a 50-70 word narrative that weaves the player's top scores into
    the chosen archetype's age-bracketed bio chunk. Strict guardrails — Gemini
    cannot invent any historical facts: it only paraphrases the supplied bio.

    Returns None when:
      - archetype is None or developing
      - we don't have an age_bracket bio chunk to anchor on
      - the call fails (we never crash the report on a narrative failure)
    """
    if not isinstance(archetype, dict) or archetype.get("developing") or not archetype.get("id"):
        return None
    bio_chunk = archetype.get("academy_bio_chunk")
    age_bracket = archetype.get("age_bracket_used")
    if not bio_chunk or not age_bracket:
        return None

    player_name = (player_details or {}).get("player_name") or "the player"
    age = (player_details or {}).get("age") or "—"
    position = (player_details or {}).get("position") or ""

    # Top 3 evidence attrs (already computed by match_archetype)
    evidence = archetype.get("evidence") or []
    top_attrs_str = ", ".join(
        f"{e.get('label')} {e.get('score')}/10" for e in evidence[:3] if isinstance(e, dict)
    ) or "balanced scores across signature attributes"

    pro_name = _pro_name_from_archetype(archetype)
    career_brief = (archetype.get("career_brief") or "").strip()

    # Pull the top FIFA neighbor (if any) so the narrative can cite the real
    # similarity-search result alongside the curated archetype. This is what
    # turns a generic "you play like X" line into a precise, data-backed claim.
    fifa_neighbors = archetype.get("fifa_neighbors") or []
    fifa_top = fifa_neighbors[0] if fifa_neighbors else None
    fifa_line = ""
    if fifa_top and isinstance(fifa_top.get("similarity_pct"), (int, float)):
        nearest = ", ".join(a.replace("_", " ") for a in fifa_top.get("nearest_attrs", [])[:3])
        fifa_line = (
            f"\nFIFA-22 NEAREST-NEIGHBOUR (independent k-NN result across 7,473 senior pros): "
            f"{fifa_top['name']} ({fifa_top.get('club') or '—'}), {fifa_top['similarity_pct']:.1f}% similar — "
            f"closest on {nearest}. You MAY mention this match in one short sentence, "
            f"but only as a similarity finding (e.g. \"the closest senior pro by data is X\"). "
            f"Do NOT make any other claim about that pro."
        )

    career_line = ""
    if career_brief:
        career_line = (
            f"\nPRO CAREER CONTEXT (FBref / Transfermarkt verified — facts only):\n\"{career_brief}\"\n"
            "You MAY paraphrase ONE statistic from this line if it flows naturally, "
            "but do NOT invent any other career fact."
        )

    prompt = f"""Write a single short paragraph (60-90 words, plain English, no jargon) that compares this young footballer to the named professional AT THE SAME AGE.

STRICT RULES — read carefully:
1. Use ONLY the BIO_CHUNK and (if provided) the PRO CAREER CONTEXT. You may paraphrase but DO NOT invent any other historical fact about the pro (no goals scored, no transfers, no clubs not mentioned).
2. NEVER compare the kid to the pro's peak career — only the pro at age {age_bracket}.
3. Weave in 2 of the kid's top scores naturally.
4. Open with the kid's name. Close with one sentence about what comes next.
5. If the FIFA-22 NEAREST-NEIGHBOUR line is present, weave it in once — but ONLY as "data similarity" framing (not a career claim).
6. No bullet points. No JSON. Plain prose.

KID:
- Name: {player_name}
- Age: {age}
- Position: {position}
- Top measured strengths: {top_attrs_str}

PRO REFERENCE (style match): {pro_name}
PRO AT AGE {age_bracket} (this is the ONLY biographical fact you may use, plus the career line below):
"{bio_chunk}"
{career_line}
{fifa_line}

OUTPUT (just the paragraph, nothing else):"""

    try:
        text = await call_gemini_text(
            session_id=f"archetype-narrative-{archetype.get('id')}-{age_bracket}",
            prompt=prompt,
        )
        return (text or "").strip().strip('"').strip()
    except Exception as e:
        logger.warning(f"Archetype narrative generation failed: {e}")
        return None


def compute_age_profile_reference(full_report: dict, player_details: dict) -> Optional[dict]:
    """Builds the 'European Academy reference profile' comparison block.

    For the player's position we pull the position's priority attributes,
    look up the player's actual score from the AI report, and compare
    against the pro-academy benchmark range from the AI's own benchmarks
    field. Returns deltas + a short summary so the user can SEE how the
    player overlays on a top-academy reference profile.
    """
    if not isinstance(full_report, dict):
        return None
    position = _normalise_position((player_details or {}).get("position"))
    if not position:
        return None
    profile = AGE_PROFILES_CATALOG.get(position)
    if not profile or not isinstance(profile, dict):
        return None
    priority_attrs = profile.get("priority_attributes") or []
    if not priority_attrs:
        return None

    scores = _flatten_scores(full_report)
    # Pull each attribute's benchmark + tier from the AI's own per-skill block
    skill_meta = _collect_skill_meta(full_report)

    age_bracket = (full_report.get("overall_benchmark") or {}).get("age_bracket_used") or ""

    items = []
    above = 0
    below = 0
    on_par = 0
    for spec in priority_attrs:
        k = spec["key"]
        score = scores.get(k)
        meta = skill_meta.get(k) or {}
        pro_range = ((meta.get("benchmarks") or {}).get("pro_academy")) or "7-8.5"
        tier = meta.get("tier_for_age")
        if score is None:
            delta_label = "no_data"
        elif tier in ("elite_academy", "pro_academy"):
            delta_label = "at_or_above"
            above += 1
        elif tier in ("standard_club",) or (isinstance(score, (int, float)) and score < 5.5):
            delta_label = "below"
            below += 1
        else:
            delta_label = "below"
            below += 1 if tier == "strong_club" else 0
            if tier == "strong_club":
                pass
            else:
                on_par += 1
        items.append({
            "key": k,
            "label": k.replace("_", " ").title(),
            "weight": spec.get("weight", 3),
            "why_matters": spec.get("why_matters", ""),
            "pro_academy_range": pro_range,
            "player_score": score,
            "player_tier": tier,
            "delta": delta_label,
        })

    summary_parts = []
    if above:
        summary_parts.append(f"<b>{above}</b> at or above Pro Academy level")
    if below:
        summary_parts.append(f"<b>{below}</b> still developing")
    summary = " · ".join(summary_parts) if summary_parts else "Profile is forming."

    return {
        "position_key": position,
        "age_bracket": age_bracket,
        "items": items,
        "summary": summary,
        "above_count": above,
        "below_count": below,
        "total_priority_attrs": len(items),
    }


def _collect_skill_meta(full_report: dict) -> dict:
    """Flat lookup: sub_attr_key -> {benchmarks, tier_for_age, why_this_score, verdict}."""
    meta: dict = {}
    if not isinstance(full_report, dict):
        return meta
    for section in ("technical", "tactical", "physical", "mentality"):
        sec = full_report.get(section) or {}
        if not isinstance(sec, dict):
            continue
        for key, value in sec.items():
            if isinstance(value, dict):
                meta[key] = {
                    "benchmarks": value.get("benchmarks"),
                    "tier_for_age": value.get("tier_for_age"),
                    "why_this_score": value.get("why_this_score"),
                    "verdict": value.get("verdict"),
                }
    return meta


# ---- Video frame thumbnails (Session 3: feature F) ----

def _ts_to_seconds(timestamp: str) -> Optional[int]:
    """Parse 'MM:SS' or 'HH:MM:SS' (or plain '125') into integer seconds."""
    if timestamp is None:
        return None
    s = str(timestamp).strip()
    if not s:
        return None
    try:
        parts = s.split(":")
        if len(parts) == 1:
            return int(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except (ValueError, TypeError):
        return None
    return None


def _make_placeholder_frame(timestamp: str, comment: str, out_path: Path) -> bool:
    """Generate a branded forest-on-cream placeholder frame when ffmpeg
    extraction is unavailable (e.g. seeded demo with no real video)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        W, H = 640, 360
        img = Image.new("RGB", (W, H), (244, 239, 230))
        d = ImageDraw.Draw(img)
        d.rectangle([(0, 0), (8, H)], fill=(31, 79, 47))
        d.polygon([(W - 110, 0), (W, 0), (W, 110)], fill=(45, 107, 61))
        cx, cy = W // 2, H // 2 - 30
        d.rectangle([(cx - 70, cy - 30), (cx + 70, cy + 30)], outline=(31, 79, 47), width=3)
        d.rectangle([(cx + 50, cy - 18), (cx + 80, cy + 18)], outline=(31, 79, 47), width=3)
        d.ellipse([(cx - 25, cy - 18), (cx + 25, cy + 32)], outline=(31, 79, 47), width=3)
        try:
            font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
            font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        except Exception:
            font_lg = ImageFont.load_default()
            font_sm = ImageFont.load_default()
        ts_text = str(timestamp or "—")
        bbox = d.textbbox((0, 0), ts_text, font=font_lg)
        tw = bbox[2] - bbox[0]
        d.text(((W - tw) // 2, H - 110), ts_text, fill=(31, 79, 47), font=font_lg)
        sub = "Moment placeholder · upload a real clip to see the live frame"
        bbox = d.textbbox((0, 0), sub, font=font_sm)
        sw = bbox[2] - bbox[0]
        d.text(((W - sw) // 2, H - 50), sub, fill=(107, 114, 128), font=font_sm)
        img.save(out_path, "JPEG", quality=82)
        return True
    except Exception as e:
        logging.warning("placeholder frame failed: %s", e)
        return False


def _extract_video_frame(video_path: Path, seconds: int, out_path: Path) -> bool:
    """Use ffmpeg to grab a single frame at the given second."""
    try:
        import subprocess
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-ss", str(max(0, int(seconds))),
                "-i", str(video_path),
                "-frames:v", "1", "-q:v", "3",
                "-vf", "scale=640:-1",
                str(out_path),
            ],
            capture_output=True, timeout=15,
        )
        return result.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0
    except Exception as e:
        logging.warning("ffmpeg frame extraction failed: %s", e)
        return False


def ensure_video_frames(report_doc: dict) -> list:
    """For every video_comments entry, ensure a frame JPEG exists on disk and
    attach a `frame_url` to the comment. Falls back to a branded placeholder
    when the video file is missing or ffmpeg fails.

    When a player fingerprint exists on the report, each thumbnail is verified
    against the locked player using `verify_and_pick_thumbnail` — we sample a
    small window around the AI's timestamp, pick the frame whose pixels best
    match the marked player's jersey/shorts, and stamp a volt-green reticle so
    readers can see exactly which player on screen the comment refers to.
    """
    full = report_doc.get("full_report") or {}
    comments = full.get("video_comments") or []
    if not comments:
        return []

    report_id = report_doc.get("id")
    if not report_id:
        return comments

    frames_dir = UPLOAD_DIR / "frames" / str(report_id)
    frames_dir.mkdir(parents=True, exist_ok=True)

    video_filename = report_doc.get("video_filename")
    video_path = UPLOAD_DIR / video_filename if video_filename else None
    have_video = bool(video_path and video_path.exists())

    # Try to reconstruct the player fingerprint for thumbnail re-verification.
    fingerprint_obj = None
    fp_dict = report_doc.get("fingerprint")
    if isinstance(fp_dict, dict):
        try:
            from precision_engine import PlayerFingerprint  # local import to avoid circulars
            fingerprint_obj = PlayerFingerprint(
                jersey_hex=fp_dict.get("jersey_hex", "#888888"),
                jersey_name=fp_dict.get("jersey_name", "unclear"),
                shorts_hex=fp_dict.get("shorts_hex", "#888888"),
                shorts_name=fp_dict.get("shorts_name", "unclear"),
                body_ratio=float(fp_dict.get("body_ratio", 2.0)),
                crop_path=fp_dict.get("crop_path"),
                box=fp_dict.get("box", {}),
                confidence=fp_dict.get("confidence", "ok"),
            )
        except Exception as e:
            logging.warning(f"thumbnail verify: could not reconstruct fingerprint: {e}")
            fingerprint_obj = None

    enriched = []
    for idx, c in enumerate(comments):
        if not isinstance(c, dict):
            enriched.append(c)
            continue
        ts = c.get("timestamp", "")
        out_path = frames_dir / f"frame_{idx:02d}.jpg"
        frame_meta = None
        if not out_path.exists():
            ok = False
            if have_video:
                seconds = _ts_to_seconds(ts)
                if seconds is not None:
                    # Prefer the verified-and-reticled thumbnail when we have a fingerprint
                    if fingerprint_obj is not None:
                        try:
                            from precision_engine import verify_and_pick_thumbnail
                            ok, frame_meta = verify_and_pick_thumbnail(
                                video_path, float(seconds), fingerprint_obj, out_path,
                            )
                        except Exception as e:
                            logging.warning(f"thumbnail verify failed for ts={ts}: {e}")
                            ok = False
                    if not ok:
                        ok = _extract_video_frame(video_path, seconds, out_path)
            if not ok:
                _make_placeholder_frame(ts, c.get("comment", ""), out_path)
        out = dict(c)
        out["frame_url"] = f"/api/uploads/frames/{report_id}/{out_path.name}"
        if frame_meta:
            out["frame_verified"] = bool(frame_meta.get("ok"))
            out["frame_picked_ts"] = frame_meta.get("picked_ts")
            out["frame_match_score"] = frame_meta.get("match_score")
            out["frame_reticle"] = frame_meta.get("reticle")
        enriched.append(out)
    return enriched


# ---- Shareable IG-ready PNG card (Session 3: feature J - shareable) ----

def generate_share_card(report_doc: dict, out_path: Path) -> bool:
    """Render a 1080x1350 IG-ready PNG summarising the player's report."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:
        logging.warning("share card: PIL import failed: %s", e)
        return False

    pd = report_doc.get("player_details") or {}
    fr = report_doc.get("full_report") or {}
    ob = fr.get("overall_benchmark") or {}
    arch = report_doc.get("archetype") or {}
    scores = fr.get("scores") or {}

    player_name = pd.get("player_name") or "Player"
    position = pd.get("position") or "—"
    age = pd.get("age") or ""
    overall = scores.get("overall_development")
    tier_label = ob.get("tier_label") or "—"

    flat = []
    for sec in ("technical", "tactical", "physical", "mentality"):
        s = fr.get(sec) or {}
        if isinstance(s, dict):
            for key, value in s.items():
                if isinstance(value, dict) and isinstance(value.get("score"), (int, float)):
                    flat.append((value["score"], key.replace("_", " ").title()))
    flat.sort(reverse=True)
    top_strengths = [name for _, name in flat[:3]]

    W, H = 1080, 1350
    CREAM = (244, 239, 230)
    FOREST = (31, 79, 47)
    FOREST_POP = (45, 107, 61)
    INK = (10, 15, 13)
    MUTED = (107, 114, 128)

    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)

    try:
        font_xl = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 180)
        font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
        font_md = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        font_xs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except Exception:
        font_xl = font_lg = font_md = font_sm = font_xs = ImageFont.load_default()

    d.rectangle([(0, 0), (W, 280)], fill=FOREST)
    d.polygon([(W - 220, 0), (W, 0), (W, 220)], fill=FOREST_POP)
    d.text((48, 36), "SCOUTMEPLAY", fill=CREAM, font=font_xs)
    d.text((48, 72), player_name.upper()[:24], fill=(255, 255, 255), font=font_lg)
    sub = f"{position.upper()}"
    if age:
        sub += f"  ·  AGE {age}"
    d.text((48, 156), sub[:46], fill=CREAM, font=font_sm)
    if arch.get("match_strength") is not None and not arch.get("developing"):
        ms_text = f"{arch['match_strength']:.1f}/10"
        d.text((W - 250, 110), "MATCH", fill=CREAM, font=font_xs)
        d.text((W - 250, 132), ms_text, fill=(255, 255, 255), font=font_md)

    score_y = 360
    score_text = f"{overall}" if overall is not None else "—"
    bbox = d.textbbox((0, 0), score_text, font=font_xl)
    sw = bbox[2] - bbox[0]
    d.text(((W - sw) // 2, score_y), score_text, fill=FOREST, font=font_xl)
    slash = "/10"
    d.text(((W + sw) // 2 + 14, score_y + 116), slash, fill=MUTED, font=font_md)
    d.text((W // 2 - 130, score_y + 200), "OVERALL DEVELOPMENT", fill=MUTED, font=font_xs)

    tier_y = 660
    tier_text = tier_label.upper()
    bbox = d.textbbox((0, 0), tier_text, font=font_md)
    tw = bbox[2] - bbox[0]
    pad_x = 48
    chip_x0 = (W - tw - pad_x * 2) // 2
    d.rectangle([(chip_x0, tier_y), (chip_x0 + tw + pad_x * 2, tier_y + 76)], fill=FOREST)
    d.text((chip_x0 + pad_x, tier_y + 18), tier_text, fill=(255, 255, 255), font=font_md)

    if arch.get("name") and not arch.get("developing"):
        arch_y = 800
        d.text((60, arch_y), "STYLISTIC ARCHETYPE", fill=FOREST, font=font_xs)
        d.text((60, arch_y + 28), arch["name"], fill=INK, font=font_md)

    if top_strengths:
        sy = 920
        d.text((60, sy), "TOP STRENGTHS", fill=FOREST, font=font_xs)
        for i, name in enumerate(top_strengths):
            yy = sy + 42 + i * 50
            d.ellipse([(64, yy + 10), (84, yy + 30)], fill=FOREST)
            d.text((104, yy), name, fill=INK, font=font_md)

    bars = []
    for pillar, color in [("technical", FOREST), ("tactical", FOREST_POP), ("physical", (185, 110, 17)), ("mentality", INK)]:
        s = fr.get(pillar) or {}
        if isinstance(s, dict):
            for key, value in s.items():
                if isinstance(value, dict) and isinstance(value.get("score"), (int, float)):
                    bars.append((value["score"], color))
    bars.sort(key=lambda x: -x[0])
    if bars:
        dna_y = 1130
        dna_h = 88
        seg_w = (W - 120) / max(len(bars), 1)
        d.text((60, dna_y - 30), "PLAYER DNA", fill=FOREST, font=font_xs)
        for i, (score, color) in enumerate(bars):
            x0 = 60 + i * seg_w
            h = max(10, (score / 10.0) * dna_h)
            d.rectangle([(x0, dna_y + (dna_h - h)), (x0 + seg_w - 2, dna_y + dna_h)], fill=color)

    d.text((60, H - 60), "SCOUTMEPLAY.COM  ·  ALIGNED WITH UEFA YOUTH-DEVELOPMENT PILLARS", fill=MUTED, font=font_xs)

    img.save(out_path, "PNG", optimize=True)
    return True


def ensure_share_card(report_doc: dict) -> Optional[str]:
    """Generate (lazily) the IG-ready share card and return its public URL."""
    report_id = report_doc.get("id")
    if not report_id:
        return None
    cards_dir = UPLOAD_DIR / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    card_path = cards_dir / f"{report_id}.png"
    if not card_path.exists():
        if not generate_share_card(report_doc, card_path):
            return None
    return f"/api/uploads/cards/{card_path.name}"










class UserSignup(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=80)
    # Honeypot — bots fill hidden form fields, humans leave it empty. Blocks signup
    # if any value is submitted. Frontend renders this as a visually-hidden input.
    website: Optional[str] = Field(default="", max_length=200)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class UserPublic(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    created_at: str
    is_paid_scout: bool = False  # True when user.scout_access.active is True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class PlayerDetails(BaseModel):
    player_name: str
    age: int
    position: str
    preferred_foot: str  # left / right / both
    current_club: Optional[str] = None
    video_type: str  # highlight / match / training
    description: str  # which player are you in the video


class PriceUpdate(BaseModel):
    price: Optional[float] = None
    # backward-compat — admin UI may send price_dkk; we treat both as the canonical price
    price_dkk: Optional[float] = None


class PricingUpdate(BaseModel):
    """Update one or more of the admin-controlled display prices.

    `single_price` directly drives the one-time Single-Report checkout (Stripe
    receives the new amount on every new session, so it always matches the UI).
    `premium_price` / `vip_price` are DISPLAY values only — they update the
    pricing tier cards across the site immediately. The actual recurring
    Stripe Price IDs are immutable and were created on backend startup. When
    one of these is changed, a `stripe_sync_required` flag is returned so the
    admin UI can surface a note.
    """
    single_price:  Optional[float] = None
    premium_price: Optional[float] = None
    vip_price:     Optional[float] = None
    # NEW — per-report extra-purchase price for subscribers who exhausted quota.
    # Cheaper than the single_price because the buyer is already paying for a subscription.
    premium_extra_price: Optional[float] = None
    vip_extra_price:     Optional[float] = None


class SocialLinksUpdate(BaseModel):
    twitter_url:   Optional[str] = None
    facebook_url:  Optional[str] = None
    linkedin_url:  Optional[str] = None
    instagram_url: Optional[str] = None


class FAQCreate(BaseModel):
    """Admin creates a new Common Question / FAQ entry.
    `q` is the visible question, `a` is the visible answer. Both required.
    Special sentinel `__PRICE_FAQ__` in `a` renders the dynamic pricing copy
    on the landing page (kept for the legacy behaviour of one existing entry).
    """
    q: str
    a: str
    published: Optional[bool] = True


class FAQUpdate(BaseModel):
    """PATCH-style — any subset of fields can be updated."""
    q: Optional[str] = None
    a: Optional[str] = None
    published: Optional[bool] = None
    order: Optional[int] = None


class FAQReorder(BaseModel):
    """POST /api/admin/faq/reorder — send the full ordered list of item IDs.
    Backend rewrites the `order` field on each so drag-to-reorder is stable.
    """
    ordered_ids: list[str]


class CheckoutInit(BaseModel):
    report_id: str
    origin_url: str


class PrepayUploadInit(BaseModel):
    origin_url: str


class SubscribeInit(BaseModel):
    """Frontend posts only the tier id + the originating window URL.
    The actual price is looked up on the backend from SUBSCRIPTION_TIERS to
    prevent any client-side price manipulation."""
    tier: str = Field(description="'premium' or 'vip'")
    origin_url: str


class AgentReviewSubmit(BaseModel):
    review_text: str = Field(min_length=10)
    agent_name: Optional[str] = "Elite Scout Team"


class AgentMessageSubmit(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


# ============== AUTH UTILITIES ==============

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ── SECURITY HELPERS (added Feb 2026) ──────────────────────────────────

_PASSWORD_MIN_LENGTH = 10
_LOGIN_MAX_ATTEMPTS = 5           # per (ip, email) combo
_LOGIN_LOCKOUT_MINUTES = 15
_SIGNUP_MAX_PER_IP_PER_HOUR = 5
_RESET_TOKEN_TTL_MINUTES = 60


def validate_password_strength(pw: str) -> None:
    """Enforce a strong-enough password. Raises HTTPException 400 with a clear
    message so the frontend can show it verbatim. Rules mirror what the client-
    side validator shows so the two never diverge (defence in depth)."""
    if not pw or len(pw) < _PASSWORD_MIN_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {_PASSWORD_MIN_LENGTH} characters.",
        )
    if len(pw) > 128:
        raise HTTPException(status_code=400, detail="Password is too long (max 128 characters).")
    checks = [
        (any(c.islower() for c in pw), "a lowercase letter"),
        (any(c.isupper() for c in pw), "an uppercase letter"),
        (any(c.isdigit() for c in pw), "a digit"),
        (any(not c.isalnum() for c in pw), "a symbol (e.g. ! ? # $ %)"),
    ]
    missing = [label for ok, label in checks if not ok]
    if missing:
        raise HTTPException(
            status_code=400,
            detail="Password must include " + ", ".join(missing) + ".",
        )
    # Optional: reject the most common junk passwords outright.
    if pw.lower() in {
        "password1!", "password123", "qwerty1234", "welcome123!", "abcd1234!",
        "footballer1!", "letmein123!", "scoutmeplay1!",
    }:
        raise HTTPException(status_code=400, detail="That password is too common. Try a unique passphrase.")


def _client_ip(request: Request) -> str:
    """Best-effort client IP behind Kubernetes ingress / Cloudflare."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip() or "unknown"
    return (request.client.host if request.client else "unknown") or "unknown"


async def _login_lockout_check(ip: str, email: str) -> None:
    """Reject login if too many failed attempts. Uses a Mongo counter keyed on
    (ip:email) with a 15-minute rolling window."""
    key = f"{ip}:{email.lower()}"
    doc = await db.login_attempts.find_one({"key": key}, {"_id": 0})
    if not doc:
        return
    if doc.get("locked_until"):
        try:
            locked_until = datetime.fromisoformat(str(doc["locked_until"]).replace("Z", "+00:00"))
            if locked_until > datetime.now(timezone.utc):
                mins = max(1, int((locked_until - datetime.now(timezone.utc)).total_seconds() / 60))
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many failed login attempts. Try again in {mins} minute{'s' if mins != 1 else ''}.",
                )
        except (TypeError, ValueError):
            pass


async def _login_attempt_record_failure(ip: str, email: str) -> None:
    key = f"{ip}:{email.lower()}"
    doc = await db.login_attempts.find_one({"key": key}, {"_id": 0}) or {}
    count = int(doc.get("count") or 0) + 1
    updates = {"count": count, "key": key, "last_at": now_iso()}
    if count >= _LOGIN_MAX_ATTEMPTS:
        updates["locked_until"] = (
            datetime.now(timezone.utc) + timedelta(minutes=_LOGIN_LOCKOUT_MINUTES)
        ).isoformat()
    await db.login_attempts.update_one({"key": key}, {"$set": updates}, upsert=True)


async def _login_attempt_clear(ip: str, email: str) -> None:
    key = f"{ip}:{email.lower()}"
    await db.login_attempts.delete_one({"key": key})


async def _signup_rate_limit_check(ip: str) -> None:
    """Reject if more than N signups from the same IP in the last hour."""
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    recent = await db.signup_attempts.count_documents({"ip": ip, "created_at": {"$gte": since}})
    if recent >= _SIGNUP_MAX_PER_IP_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail="Too many signups from this network. Please try again later.",
        )


async def _signup_rate_limit_record(ip: str) -> None:
    await db.signup_attempts.insert_one({"ip": ip, "created_at": now_iso()})


def _generate_reset_token() -> str:
    """32-byte URL-safe token (256 bits) — cryptographically random."""
    return secrets.token_urlsafe(32)


def create_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXP_MIN),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)):
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = pyjwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALG])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_current_admin(user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def get_current_admin_or_scout(user=Depends(get_current_user)):
    """Used by agent-review endpoints — both admins and scouts can review reports."""
    if user.get("role") not in ("admin", "scout"):
        raise HTTPException(status_code=403, detail="Admin or scout access required")
    return user


# ============== GEMINI ANALYSIS ==============

CONTENT_GATE_PROMPT = """You are a strict video content validator for a professional football scouting service. A short video clip and a reference frame (player marked with a bright green circle and "THIS PLAYER" label) are provided. Look at them and decide whether this submission can be analysed.

Return ONLY a JSON object in EXACTLY this shape — no extra fields, no commentary outside JSON:

{
  "is_football": true | false,
  "content_type": "full_match" | "small_sided" | "training" | "drill" | "fitness" | "freestyle" | "mixed" | "other",
  "quality": "good" | "poor" | "unwatchable",
  "player_visible": "clear" | "partial" | "unclear" | "not_visible",
  "games_detected": <integer count of distinct games or sessions visible>,
  "camera_distance": "close" | "medium" | "far" | "too_far",
  "issues": ["<short concrete issue>", "..."],
  "rejection_reason": "<one sentence explaining why this video cannot be analysed, or null if acceptable>"
}

STRICT rules:
- A football match, small-sided game, training session, drills, fitness work, or freestyle with a football ALL count as football → is_football: true.
- A basketball game, dance video, dog video, indoor non-football footage, a still photo or random clips → is_football: false.
- If the video is so dark, shaky, or low-resolution that no football action can be identified → quality: "unwatchable".
- If the marked player is genuinely never visible across the clip → player_visible: "not_visible".
- Set rejection_reason ONLY when one of these is true:
    • is_football is false, OR
    • quality is "unwatchable", OR
    • player_visible is "not_visible".
  Otherwise rejection_reason MUST be null.
- Be FAIR but firm. If you can see football activity and the player is shown at least briefly, accept it.

Return only the JSON."""


PREVIEW_PROMPT = """You are an experienced football coach giving a SHORT, evidence-based FREE PREVIEW based on a 15-second clip and a reference frame.

🚫 ABSOLUTE ANTI-HALLUCINATION RULE
You MUST describe ONLY what literally happens in the 15-second video — frame by frame.
NEVER invent match-style actions (e.g. "beating defenders", "powerful strike on goal",
"finishing a counter-attack", "shoots past the keeper", "winning a header") unless you
actually SEE opposition defenders, a goalkeeper, a goal, or a real match situation in
the footage. If the clip shows ONLY a kid working with cones, then describe ONLY cone
work (ball-touches on cones, body shape during the dribble pattern, weight transfer,
repetition consistency). If you cannot see something, say so explicitly — never guess.

Treat the user-provided "VIDEO_TYPE" as an INTENT label, not as ground truth. The
content_type field below is what we ACTUALLY detected in the clip — always defer to
the detected reality, never to the user's selected label.

🚫 OUTCOME-CLAIM GUARDRAILS (HARD CONSTRAINT)
You MUST NOT claim ANY of the following unless the action is **visibly completed**
in the actual video frames you analysed:
  - "scores", "finishes", "puts the ball in the net", "powerful strike on goal",
    "shoots past the keeper", "scores past the goalkeeper" — only if the ball
    visibly crosses the goal-line or enters the net on screen.
  - "wins the tackle", "wins the duel", "blocks the shot" — only if the visible
    outcome is the marked player ending up with the ball after a contested action.
  - "saves the shot" — only for goalkeepers, and only when a shot is visibly stopped.
  - "creates the chance", "assists the goal", "lays the ball off" — only if the
    marked player visibly passes/crosses to a teammate AND that teammate visibly
    shoots/scores in the SAME continuous sequence.

✅ SAFE LANGUAGE WHEN YOU AREN'T SURE WHAT HAPPENED NEXT
If the marked player passes the ball but the camera follows OR cuts before you see
the next action, describe the PASS itself ("plays a sharp diagonal ball into the
box", "lays it off first-time", "puts the ball back into space") — NOT the outcome
("assist", "goal-scoring chance"). Same for shots that go off-screen: describe the
strike ("rasps a low drive towards the bottom corner"), NOT the result ("scores",
"hits the post") unless you literally see the impact.

Confusing a goal with an assist (or vice versa) is the #1 trust-killer for parents
and academy scouts reading this report. When in doubt, describe the player's
ACTION, not the OUTCOME.

🎯 CONTENT-TYPE-LOCKED VOCABULARY (HARD CONSTRAINT)
- If CONTENT_TYPE is "drill", "training", "technical_drills", or "freestyle":
    ✅ Allowed phrases: "cone work", "ball mastery", "first touch on the cone", "body shape
       through the gate", "weight transfer", "repetition rhythm", "scanning before each
       touch", "two-footed control during the drill", "speed of the drill", "fluency between cones".
    ❌ FORBIDDEN phrases: "beats a defender", "finishes on goal", "powerful strike",
       "1v1 with the keeper", "match-winning run", "scores", "tackles", "passes a teammate
       in tight space" (unless you literally see a teammate receiving the ball).
- If CONTENT_TYPE is "full_match" / "small_sided" / "mixed":
    Match-action vocabulary IS allowed — but only describe moments you literally see,
    and the OUTCOME-CLAIM GUARDRAILS above ALWAYS apply (no inventing goals/assists).
- If CONTENT_TYPE is "fitness": describe physical work only (sprint, change of direction).

🎯 GROUND RULE — EVIDENCE OR SILENCE
Every observation must come from what you actually SAW in the clip. If you can't see it, say so — never invent.

🎯 LANGUAGE
Plain, natural football coach language. AVOID jargon like "press-resistant", "scanning frequency", "line-breaking", "half-turn", "high-intensity transitions", "vertical progression". Use phrases like "stays calm under pressure", "always looks around before the ball arrives", "his left foot is dangerous", "gets tired late in the game".

🎯 PLAYER IDENTIFICATION
A reference frame is attached. The player to analyse is the ONE CIRCLED IN BRIGHT GREEN with the label "THIS PLAYER". Track ONLY that player. Note their jersey colour, number, body type, hair, distinguishing features. Ignore everyone else.

🎯 CONTENT CONTEXT (from pre-analysis — THIS IS THE TRUTH OF WHAT'S IN THE VIDEO)
CONTENT_TYPE: {content_type}
PLAYER_VISIBILITY: {player_visible}
CAMERA_DISTANCE: {camera_distance}

🎯 PLAYER DETAILS
{player_details}

Produce a JSON object EXACTLY in this format:

{
  "player_type": "<short, friendly label e.g. 'Smart playmaker with a strong left foot' — based on observation>",
  "brief_summary": "<2-3 sentences about how THE CIRCLED PLAYER plays based ONLY on what you literally saw — if the clip is cone work, talk about cone work, NOT match action>",
  "top_strengths": ["<observed strength 1>", "<observed strength 2>", "<observed strength 3>"],
  "area_for_improvement": "<one specific area, only if visible in the clip — otherwise 'Need more footage to spot an improvement area'>",
  "evidence_note": "<one short sentence about what kind of moments you observed (e.g., 'Saw 5 clear touches and 2 passes in the clip')>",
  "confidence": "high" | "medium" | "low",
  "confidence_reason": "<one sentence — e.g. 'Player visible for most of the clip with multiple touches' or 'Only 2 brief on-ball moments visible'>",
  "sample_section": {
    "title": "Sample: Technical Snapshot",
    "content": "<3-4 sentence teaser of the deeper technical breakdown — still in natural football language, still evidence-based — DRILL-ONLY language if content_type is drill/training/freestyle>"
  }
}

CRITICAL:
- Independent developmental feedback — do NOT imply trials, contracts, selection
- Evidence-only — never invent or guess
- If content_type is drill/training/freestyle, NEVER use match-game vocabulary (defenders, goal, keeper, finishing) — this is a HARD CONSTRAINT, not a suggestion
- Return ONLY valid JSON, no markdown, no commentary
"""


FULL_REPORT_PROMPT = """You are an experienced football scout writing a PREMIUM, EVIDENCE-BASED development report for a young player.

🎯 GROUND RULE — EVIDENCE OR SILENCE
Every score and every claim must come from something you actually OBSERVED in the video. If you cannot see it, set "cannot_evaluate": true with a reason. NEVER guess.

🚫 OUTCOME-CLAIM GUARDRAILS (HARD CONSTRAINT — TRUST-CRITICAL)
You MUST NOT claim ANY of the following unless the action is **visibly completed**
in the actual video frames you analysed:
  - "scores a goal", "finishes", "puts the ball in the net", "powerful strike on goal",
    "shoots past the keeper" — only if the ball visibly crosses the goal-line or
    enters the net ON SCREEN.
  - "wins the tackle", "wins the duel", "blocks the shot" — only if the marked player
    visibly ends up with the ball after the contested action.
  - "saves the shot" — only for goalkeepers, and only when a shot is visibly stopped.
  - "creates the chance", "assists the goal", "lays the ball off for the finish" — only
    if the marked player visibly passes/crosses to a teammate AND that teammate visibly
    shoots/scores in the SAME continuous sequence (same frames, no cut).

✅ SAFE LANGUAGE WHEN YOU AREN'T SURE WHAT HAPPENED NEXT
If the marked player passes the ball but the camera follows OR cuts before you see
the next action, describe the PASS itself ("plays a sharp diagonal ball into the
box", "lays it off first-time", "puts the ball back into space") — NOT the outcome
("assist", "goal-scoring chance"). Same for shots that go off-screen: describe the
strike ("rasps a low drive towards the bottom corner"), NOT the result.

Confusing a goal with an assist (or vice versa) is the #1 trust-killer for parents
and academy scouts reading this report. When in doubt, describe the player's
ACTION, not the OUTCOME. This applies to EVERY section: executive_summary,
final_summary, video_comments, scout_view, and every evidence_string in every
scored sub-skill.

🎯 LANGUAGE
Plain, natural football coach language. AVOID jargon like "press-resistant", "scanning frequency", "line-breaking passes", "half-turn", "high-intensity transitions", "vertical progression", "false-9 in possession systems". Use plain phrases: "stays calm when defenders close him down", "always looks around before getting the ball", "his left foot can find any pass", "gets tired late in matches", "ready to step up to a stronger team".

🎯 PLAYER IDENTIFICATION
A reference frame is attached showing the player CIRCLED in bright green with the label "THIS PLAYER". Track ONLY that player across the video. Note their jersey colour, number, body type, hair, and distinguishing features. If you lose sight of them in some moments, only score what you actually saw.

🎯 CONTENT AWARENESS (from pre-analysis)
CONTENT_TYPE: {content_type}
QUALITY: {quality}
PLAYER_VISIBILITY: {player_visible}
CAMERA_DISTANCE: {camera_distance}
GAMES_DETECTED: {games_detected}

ADAPT YOUR ANALYSIS to the content_type:
- "full_match" / "small_sided" / "mixed": evaluate ALL categories (technical, tactical, physical, mentality).
- "training": evaluate technical thoroughly. Evaluate tactical only if opposition/spacing context exists. If a sub-skill has no observable evidence, mark it cannot_evaluate.
- "drill": evaluate technical thoroughly. Tactical, mentality (duel courage, response to mistakes) → almost always cannot_evaluate unless clearly shown.
- "fitness": evaluate physical thoroughly. Technical/tactical/mentality → cannot_evaluate unless they appear.
- "freestyle": evaluate technical (ball mastery) only. All other categories cannot_evaluate.

🎯 EVIDENCE STRUCTURE
For EVERY scored sub-skill (e.g. first_touch, passing, scanning), return this exact object shape:

{
  "score": <integer 1-10, OR null if cannot_evaluate>,
  "notes": "<2-4 sentences of plain-language observation, OR 'Not observable from this footage' if cannot_evaluate>",
  "confidence": "high" | "medium" | "low",
  "confidence_reason": "<ONE sentence — e.g. '7 clear touches observed across the clip' or 'only 2 brief moments visible at distance'>",
  "observations_used": <integer count of distinct moments used>,
  "evidence": [{"timestamp": "MM:SS or 'General'", "what": "<concrete moment description>"}],
  "cannot_evaluate": false | true,
  "evaluable_reason": "<ONLY when cannot_evaluate=true: ONE sentence explaining why this skill cannot be assessed from this video, e.g. 'No shooting situations were visible in the footage.'>",
  "why_this_score": "<2-3 sentences explaining WHY you chose this specific score. Refer to concrete observed moments and reasoning. NEVER 'I gave this score because.' — be specific: 'Scored X because he consistently does Y but struggles when Z.'>",
  "tier_for_age": "elite_academy" | "pro_academy" | "strong_club" | "standard_club",
  "benchmarks": {
    "elite_academy": "<typical score range for top 5% peers — e.g. Ajax/La Masia/Bayern academy at this age+position, e.g. '9-10'>",
    "pro_academy": "<typical score range for top 15% — most professional U-academies at this age+position, e.g. '7.5-8.5'>",
    "strong_club": "<top regional/elite-amateur club at this age+position, e.g. '6-7'>",
    "standard_club": "<average local club / school football at this age+position, e.g. '4-5.5'>"
  },
  "verdict": "<ONE sentence in this format: 'Currently sitting at <tier> for a <age>-year-old <position>. To reach <next tier>, focus on <one specific actionable thing>.'>"
}

When cannot_evaluate=true: score MUST be null, notes brief, evidence may be empty, confidence "low", tier_for_age can be omitted, benchmarks can be omitted, verdict can be omitted or short.

🎯 BENCHMARK CALIBRATION (this is what makes the report feel real)
Calibrate every "benchmarks" object to the PLAYER'S AGE AND POSITION. A 12-year-old does NOT face the same standards as a 17-year-old. A goalkeeper is not measured against a striker. Use the age-bracket rubric below:

AGE BRACKETS (use the bracket that contains the player's age):
- U11–U12 (5v5/9v9): elite=8-9, pro=6.5-8, strong=5-6.5, standard=3-5
- U13–U14 (11v11 introduction): elite=8.5-10, pro=7-8.5, strong=5.5-7, standard=4-5.5
- U15–U16 (academy selection age): elite=9-10, pro=7.5-9, strong=6-7.5, standard=4-6
- U17–U18 (pro contract age): elite=9-10, pro=8-9, strong=6.5-8, standard=5-6.5
- U19–U21 (reserve/loan age): elite=9-10, pro=8-9.5, strong=7-8, standard=5.5-7
- Senior 22+: elite=9-10, pro=8-9.5, strong=7-8.5, standard=6-7.5

POSITION ADJUSTMENTS — emphasize the right attributes for the position:
- Goalkeeper: emphasize positioning, decision_making, focus, body_control, courage_in_duels; de-emphasize dribbling, shooting, weak_foot
- Centre-back: positioning, courage_in_duels, decision_making, heading; de-emphasize dribbling, shooting
- Full-back/Wing-back: speed, acceleration, intensity, off_ball_movement, passing
- Defensive midfielder: scanning, decision_making, passing, positioning, work_rate
- Central/Attacking midfielder: passing, first_touch, scanning, decision_making, weak_foot
- Winger: dribbling, acceleration, one_v_one, weak_foot, timing_of_runs
- Striker/Forward: first_touch, shooting, one_v_one, off_ball_movement, courage_in_duels

When you write benchmarks, write them as RANGES (e.g. "7.5-8.5") not single numbers. Calibrate the range to the AGE+POSITION combination. Choose the tier_for_age by checking which range the player's actual score falls into.

🎯 PLAYER DETAILS
{player_details}

Produce a JSON object EXACTLY in this format:

{
  "player_type": "<short friendly label>",
  "executive_summary": "<4-6 sentences describing THE CIRCLED PLAYER's style and what makes him stand out — strictly based on what you observed>",
  "content_analysis": {
    "content_type_observed": "<the type you actually saw, plain words>",
    "minutes_observed": <approximate minutes of observable play of THIS PLAYER>,
    "key_situations": ["<short list of distinct situations seen, e.g. 'attacking transition', 'first-touch under pressure', 'recovery sprint'>"]
  },
  "technical": {
    "first_touch": { ... evidence object as above ... },
    "ball_control": { ... },
    "dribbling": { ... },
    "passing": { ... },
    "shooting": { ... },
    "weak_foot": { ... },
    "one_v_one": { ... }
  },
  "tactical": {
    "positioning": { ... },
    "off_ball_movement": { ... },
    "scanning": { ... },
    "decision_making": { ... },
    "timing_of_runs": { ... },
    "game_understanding": { ... }
  },
  "physical": {
    "acceleration": { ... },
    "speed": { ... },
    "balance": { ... },
    "agility": { ... },
    "intensity": { ... },
    "body_control": { ... }
  },
  "mentality": {
    "confidence": { ... },
    "work_rate": { ... },
    "courage_in_duels": { ... },
    "response_to_mistakes": { ... },
    "competitive_mindset": { ... },
    "focus": { ... }
  },
  "scout_view": {
    "key_strengths": ["<3-5 plain-language bullets, each grounded in observed evidence>"],
    "areas_of_concern": ["<2-4 bullets>"],
    "development_priorities": ["<3-4 bullets — what to focus on next>"],
    "appropriate_next_level": "<plain words>",
    "positional_suitability": "<plain words>",
    "what_we_could_not_assess": ["<list of categories or sub-skills that need different footage to evaluate, plain words>"]
  },
  "potential_assessment": {
    "current_level": "<plain words>",
    "development_potential": "<honest, encouraging>",
    "recommended_next_step": "<concrete>",
    "three_month_focus": "<main focus for next 90 days>"
  },
  "training_plan": {
    "exercises": [
      {"name": "<exercise>", "description": "<2 sentence drill description>", "duration": "<e.g. '15 min'>"},
      {"name": "...", "description": "...", "duration": "..."},
      {"name": "...", "description": "...", "duration": "..."},
      {"name": "...", "description": "...", "duration": "..."},
      {"name": "...", "description": "...", "duration": "..."}
    ],
    "weekly_focus": "<paragraph>",
    "thirty_day_plan": "<paragraph>",
    "ninety_day_plan": "<paragraph>"
  },
  "video_comments": [{"timestamp": "MM:SS", "comment": "<specific moment observation in plain words>"}],
  "scores": {
    "technical": <integer 1-10>,
    "tactical": <integer 1-10>,
    "physical": <integer 1-10>,
    "mentality": <integer 1-10>,
    "overall_development": <integer 1-10>
  },
  "scores_confidence": {
    "technical": "high" | "medium" | "low",
    "tactical": "high" | "medium" | "low",
    "physical": "high" | "medium" | "low",
    "mentality": "high" | "medium" | "low",
    "overall_development": "high" | "medium" | "low"
  },
  "overall_benchmark": {
    "tier": "elite_academy" | "pro_academy" | "strong_club" | "standard_club",
    "tier_label": "<human label, e.g. 'Pro Academy Standard'>",
    "percentile": "<short plain-language phrase comparing to peers of same age+position, e.g. 'Currently in the top 15-25% of U14 central midfielders'>",
    "realistic_next_step": "<concrete next step calibrated to the player's tier, e.g. 'Trial at a regional pro academy or strong talent center'>",
    "what_separates_from_next_tier": "<ONE specific thing that, if improved, would move the player into the next tier above. Plain football language.>",
    "age_bracket_used": "U11-U12" | "U13-U14" | "U15-U16" | "U17-U18" | "U19-U21" | "Senior_22+"
  },
  "final_summary": "<3-5 sentence encouraging closing summary about THIS PLAYER, plain football language>",
  "evidence_quality_note": "<one paragraph explaining the overall evidence quality of this video — what was strong, what was missing, what kind of follow-up footage would strengthen the report>"
}

RULES FOR TOP-LEVEL "scores":
- These are AGGREGATES. Average the observable sub-skills in each category.
- If MOST sub-skills in a category are cannot_evaluate, score the category honestly low (3-5) and set scores_confidence to "low".
- If the entire category is cannot_evaluate, still give a defensible integer (e.g. 5) but set scores_confidence to "low" and reflect this in evidence_quality_note.

RULES FOR "overall_benchmark":
- The tier_label MUST match the AGE BRACKET RUBRIC above. Compare the overall_development score against the rubric for the player's age bracket.
- "percentile" should reference the EXACT age bracket and position used in the rubric, e.g. "Top 15-20% of U15 wingers".
- "realistic_next_step" must be calibrated to the player's CURRENT tier, not aspirational. If they're standard_club, the next step is strong_club — NOT pro academy. If they're already pro_academy, next step is elite_academy.

CRITICAL:
- Independent developmental analysis — do NOT imply trials, contracts, selection
- Evidence-only — never invent, never guess
- Honest cannot_evaluate is better than fake confidence
- Return ONLY valid JSON, no markdown, no commentary
"""


def extract_json(text: str) -> dict:
    """Extract first JSON object from text."""
    # Try fenced code first
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    # Find first '{' and matching last '}'
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model response")
    candidate = text[start:end + 1]
    return json.loads(candidate)


async def call_gemini_with_video(
    session_id: str,
    prompt: str,
    video_path: str,
    marker_path: Optional[str] = None,
    crop_path: Optional[str] = None,
    anchor_crops: Optional[list[str]] = None,
) -> dict:
    """Send a video file (+ optional marker image, subject crop, and multi-anchor crops)
    + prompt to Gemini and return parsed JSON.

    `anchor_crops` is a list of additional same-player crops at different timestamps.
    They go FIRST in file_contents so Gemini sees the player from every angle before
    being given the wide marker frame and full video.
    """
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=(
            "You are an experienced football scout writing in a confident, definitive "
            "voice — never hedge. ALWAYS respond with valid JSON only. When you describe "
            "the locked player you observed something — state it as fact. If you cannot "
            "see them in a moment, write OFF-CAMERA instead. Never describe a different "
            "player."
        ),
    ).with_model("gemini", "gemini-2.5-pro")

    file_contents = []
    # Multi-anchor crops first — these are the same player at different moments
    if anchor_crops:
        for p in anchor_crops:
            try:
                if p and Path(p).exists():
                    file_contents.append(
                        FileContentWithMimeType(file_path=p, mime_type="image/jpeg")
                    )
            except Exception:
                pass
    # Subject crop (legacy single-anchor) — only if no multi-anchor ensemble provided
    if not anchor_crops and crop_path and Path(crop_path).exists():
        file_contents.append(
            FileContentWithMimeType(file_path=crop_path, mime_type="image/jpeg")
        )
    if marker_path and Path(marker_path).exists():
        file_contents.append(
            FileContentWithMimeType(file_path=marker_path, mime_type="image/jpeg")
        )
    video_file = FileContentWithMimeType(
        file_path=video_path,
        mime_type="video/mp4",
    )
    file_contents.append(video_file)

    user_message = UserMessage(text=prompt, file_contents=file_contents)
    response = await chat.send_message(user_message)
    response_text = response if isinstance(response, str) else str(response)
    try:
        return extract_json(response_text)
    except Exception as e:
        logger.error(f"Failed to parse Gemini response: {e}\n{response_text[:500]}")
        raise HTTPException(status_code=500, detail="AI analysis returned invalid format. Please try again.")


# ── Scout Mode helper — Gemini Vision frame detection ────────────────
#
#   Replaces the client-side MediaPipe "person" detector that cannot tell
#   parents/spectators apart from real child players. Gemini understands
#   the scene (a youth football match) and only returns kids ON the pitch.
class _ScoutDetectRequest(BaseModel):
    image: str  # data:image/jpeg;base64,... OR raw base64
    frame_w: Optional[int] = None  # source frame size (for diagnostics)
    frame_h: Optional[int] = None


SCOUT_DETECT_PROMPT = (
    "You are looking at a single still frame from a YOUTH football (soccer) "
    "match video. Your job is to identify EVERY player visible on the pitch.\n\n"
    "BE THOROUGH. A typical frame has 6–20 players on screen — do not stop "
    "after finding only a few. Scan EVERY region of the image: left wing, "
    "right wing, midfield, near both goals, background, foreground. Look "
    "for players that are small, distant, blurred, in motion, partly "
    "occluded, in shadow, or only partly on screen — INCLUDE THEM ALL.\n\n"
    "INCLUDE every player on the pitch:\n"
    "- Field players from both teams (any age, any pose: running, "
    "  standing, falling, jumping, passing, defending)\n"
    "- Goalkeepers — even when partly hidden by the goal frame/net\n"
    "- Players who are partly off-screen, blurred, distant, or in shadow\n"
    "- Players in clusters / close together — separate them into individual boxes\n\n"
    "ONLY EXCLUDE if you are CONFIDENT the person is not a player:\n"
    "- Adults in coats, hi-vis vests, or street clothes (parents, coaches, photographers)\n"
    "- People clearly behind a fence/railing/wall (NOT on the pitch surface)\n"
    "- People on a paved path, sidewalk, parking lot, bench, or terrace\n"
    "- Referees in striped or all-black uniforms\n"
    "- Buildings, windows, lamp posts, fence posts (NOT people)\n\n"
    "DECISION RULE: If a person appears to be wearing a football jersey "
    "AND their feet are on the green pitch surface → INCLUDE them. "
    "When uncertain, prefer to INCLUDE rather than exclude.\n\n"
    "For each player return a TIGHT bounding box with coordinates as "
    "fractions of the full image size (0.0 to 1.0):\n"
    "  - x  = left edge of the box\n"
    "  - y  = top edge of the box (top of the head)\n"
    "  - w  = box width\n"
    "  - h  = box height (head to feet)\n"
    "Box must hug each player TIGHTLY — head at the top, feet at the bottom, "
    "shoulders defining the width. DO NOT merge multiple players into one box; "
    "give each player their own box even if they are close together.\n\n"
    'Respond with VALID JSON ONLY in this exact shape (no markdown, no commentary):\n'
    '{"players": [{"x": 0.12, "y": 0.45, "w": 0.05, "h": 0.18, "label": "kid in white jersey #9"}, ...]}'
)


@api_router.post("/scout/detect-players")
async def scout_detect_players(req: _ScoutDetectRequest):
    """Single-frame detection: Gemini Vision returns precise boxes for every
    child football player visible on the pitch in the supplied frame.
    Excludes parents, spectators, refs, anyone off the field.

    Response: { "players": [{ "x": 0..1, "y": 0..1, "w": 0..1, "h": 0..1, "label": str, "score": 0..1 }, ...] }
    Returns an empty list (never raises) when Gemini misbehaves, so the
    frontend can gracefully fall back to its MediaPipe boxes."""
    raw = req.image or ""
    if raw.startswith("data:"):
        try:
            _, b64 = raw.split(",", 1)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid data URL image")
    else:
        b64 = raw
    try:
        img_bytes = base64.b64decode(b64)
        if len(img_bytes) < 1024:
            raise ValueError("decoded image too small")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image payload")

    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(img_bytes)
            tmp_path = tmp.name

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"scout-detect-{uuid.uuid4().hex}",
            system_message=(
                "You are a precise computer-vision assistant. You return "
                "tight bounding boxes only for children actively playing "
                "football on the pitch. You always respond with VALID JSON."
            ),
        ).with_model("gemini", "gemini-2.5-pro")

        user_message = UserMessage(
            text=SCOUT_DETECT_PROMPT,
            file_contents=[FileContentWithMimeType(file_path=tmp_path, mime_type="image/jpeg")],
        )
        try:
            response = await chat.send_message(user_message)
        except Exception as e:
            logger.warning(f"Scout detect: Gemini call failed: {e}")
            return {"players": [], "error": "gemini_unavailable"}
        text = response if isinstance(response, str) else str(response)

        try:
            parsed = extract_json(text)
        except Exception as e:
            logger.warning(f"Scout detect: failed to parse Gemini JSON: {e} | head={text[:240]}")
            return {"players": [], "error": "parse_failed"}

        items = parsed.get("players") or parsed.get("boxes") or []
        if not isinstance(items, list):
            return {"players": [], "error": "shape_unexpected"}

        cleaned: list[dict] = []
        for p in items:
            if not isinstance(p, dict):
                continue
            try:
                x = float(p.get("x", 0))
                y = float(p.get("y", 0))
                w = float(p.get("w", p.get("width", 0)))
                h = float(p.get("h", p.get("height", 0)))
                if w <= 0 or h <= 0 or w > 0.95 or h > 0.95:
                    continue
                # Tall-shaped sanity check — humans aren't wider than tall
                if h < 1.1 * w:
                    continue
                cleaned.append({
                    "x": max(0.0, min(1.0, x)),
                    "y": max(0.0, min(1.0, y)),
                    "w": max(0.005, min(1.0, w)),
                    "h": max(0.005, min(1.0, h)),
                    "label": str(p.get("label", ""))[:80],
                    "score": float(p.get("confidence", p.get("score", 0.95))),
                })
            except Exception:
                continue

        # Cap at 25 — covers a full 11v11 + GKs + substitutes warming up
        cleaned = cleaned[:25]
        return {"players": cleaned}
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# ── Scout Mode v4 — Track ONE Player Across Multiple Frames ─────────
#
# The user taps ONE player in the first keyframe. This endpoint then asks
# Gemini Vision to find that SAME player in each of the other 9 keyframes
# — using jersey, shorts, body shape, hair, sock colour, every visual cue.
# Calls run in parallel (`asyncio.gather`) so 9 frames complete in ~15-20 s
# instead of ~90 s sequential.

class _TrackRefBox(BaseModel):
    x: float
    y: float
    w: float
    h: float


class _TrackRef(BaseModel):
    image: str          # data URL or raw base64 of the FRAME the user tapped on
    box: _TrackRefBox   # fractional 0-1 location of the tapped player


class _TrackTarget(BaseModel):
    id: str             # caller-provided identifier (e.g. "hint-2")
    image: str          # data URL or raw base64 of the frame to search


class _TrackPlayerRequest(BaseModel):
    reference: _TrackRef
    targets: list[_TrackTarget]


def _decode_data_url(s: str) -> bytes:
    """Strip optional data-URL header and base64-decode the payload."""
    raw = s or ""
    if raw.startswith("data:"):
        try:
            _, b64 = raw.split(",", 1)
        except ValueError:
            raise ValueError("Invalid data URL")
    else:
        b64 = raw
    return base64.b64decode(b64)


def _build_track_prompt(ref_box: dict) -> str:
    """Crafts the Gemini prompt for one ref→target re-identification call.
    Kept INTENTIONALLY SHORT — Flash is sensitive to long prompts and the
    instruction is simple: find the same player.
    """
    return (
        "IMAGE 1: a youth football match frame. The player to track is in "
        f"the box (x={ref_box['x']:.3f}, y={ref_box['y']:.3f}, "
        f"w={ref_box['w']:.3f}, h={ref_box['h']:.3f}) — 0-1 fractional coords.\n"
        "IMAGE 2: another frame from the SAME match. Find the EXACT SAME "
        "player (same jersey, shorts, socks, body shape, hair).\n\n"
        "Return JSON only:\n"
        '  {"box":{"x":0.0,"y":0.0,"w":0.0,"h":0.0},"confidence":0.0,"reason":""}\n'
        "where box is the tight 0-1 fractional bounding box in IMAGE 2.\n"
        "If the player is NOT visible OR you cannot identify them with "
        'reasonable confidence, return {"box":null,"confidence":0,"reason":"not visible"}.\n'
        "No markdown, no commentary, JSON only."
    )


async def _track_one_frame(ref_path: str, ref_box: dict, target_path: str, target_id: str) -> dict:
    """Single ref→target Gemini call. Always returns a dict (never raises).
    Uses Gemini 2.5 Flash — 3-5x faster than Pro for ReID at no accuracy loss.
    """
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"scout-track-{uuid.uuid4().hex}",
            system_message=(
                "You are a precise computer-vision assistant for football "
                "scouting. You return tight bounding boxes for ONE specific "
                "player. You always respond with VALID JSON."
            ),
        ).with_model("gemini", "gemini-2.5-flash")
        msg = UserMessage(
            text=_build_track_prompt(ref_box),
            file_contents=[
                FileContentWithMimeType(file_path=ref_path, mime_type="image/jpeg"),
                FileContentWithMimeType(file_path=target_path, mime_type="image/jpeg"),
            ],
        )
        response = await chat.send_message(msg)
        text = response if isinstance(response, str) else str(response)
        try:
            parsed = extract_json(text)
        except Exception as e:
            logger.warning(f"Scout track[{target_id}]: parse_failed {e} | head={text[:240]}")
            return {"id": target_id, "box": None, "confidence": 0.0, "reason": "parse_failed"}

        box_raw = parsed.get("box")
        conf = float(parsed.get("confidence", 0) or 0)
        reason = str(parsed.get("reason", ""))[:120]

        if not box_raw or not isinstance(box_raw, dict):
            return {"id": target_id, "box": None, "confidence": conf, "reason": reason or "not_found"}

        try:
            x = float(box_raw.get("x", 0))
            y = float(box_raw.get("y", 0))
            w = float(box_raw.get("w", box_raw.get("width", 0)))
            h = float(box_raw.get("h", box_raw.get("height", 0)))
            if w <= 0 or h <= 0:
                return {"id": target_id, "box": None, "confidence": conf, "reason": reason or "zero_box"}
            return {
                "id": target_id,
                "box": {
                    "x": max(0.0, min(1.0, x)),
                    "y": max(0.0, min(1.0, y)),
                    "w": max(0.005, min(1.0, w)),
                    "h": max(0.005, min(1.0, h)),
                },
                "confidence": max(0.0, min(1.0, conf)),
                "reason": reason,
            }
        except Exception:
            return {"id": target_id, "box": None, "confidence": conf, "reason": "bad_coords"}
    except Exception as e:
        logger.warning(f"Scout track[{target_id}]: gemini_call_failed {e}")
        return {"id": target_id, "box": None, "confidence": 0.0, "reason": "gemini_error"}


@api_router.post("/scout/track-player")
async def scout_track_player(req: _TrackPlayerRequest):
    """Re-identify the tapped player across multiple keyframes in parallel.

    Input:
      {
        "reference": { "image": "data:image/jpeg;base64,...", "box": {x,y,w,h} },
        "targets":   [{ "id": "hint-2", "image": "data:..." }, ... up to ~12]
      }

    Output:
      {
        "matches": [
          { "id": "hint-2", "box": {x,y,w,h}, "confidence": 0.92, "reason": "white jersey + black shorts" },
          { "id": "hint-3", "box": null,      "confidence": 0.0,  "reason": "not visible" },
          ...
        ]
      }

    Box coordinates are 0–1 fractional. The endpoint NEVER raises — failed
    Gemini calls return `box: null` so the frontend can flag them in the
    review grid for the user to manually retap.
    """
    if not req.targets:
        raise HTTPException(status_code=400, detail="targets list is empty")
    if len(req.targets) > 14:
        raise HTTPException(status_code=400, detail="too many targets (max 14)")

    # Decode reference image
    try:
        ref_bytes = _decode_data_url(req.reference.image)
        if len(ref_bytes) < 1024:
            raise ValueError("reference too small")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid reference image")
    ref_box = req.reference.box.dict()

    # Write reference + every target image to temp files (Gemini SDK reads from disk)
    temp_paths: list[str] = []
    target_paths: list[tuple[str, str]] = []  # (id, path)
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(ref_bytes)
            ref_path = f.name
            temp_paths.append(ref_path)

        for t in req.targets:
            try:
                tb = _decode_data_url(t.image)
                if len(tb) < 512:
                    target_paths.append((t.id, ""))
                    continue
            except Exception:
                target_paths.append((t.id, ""))
                continue
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                f.write(tb)
                target_paths.append((t.id, f.name))
                temp_paths.append(f.name)

        # PARALLEL Gemini calls — the whole reason this endpoint exists.
        async def _stub_invalid(tid: str) -> dict:
            return {"id": tid, "box": None, "confidence": 0.0, "reason": "invalid_target"}

        tasks = []
        for (tid, tpath) in target_paths:
            if not tpath:
                tasks.append(_stub_invalid(tid))
            else:
                tasks.append(_track_one_frame(ref_path, ref_box, tpath, tid))

        matches = await asyncio.gather(*tasks)
        return {"matches": list(matches)}
    finally:
        for p in temp_paths:
            try:
                os.unlink(p)
            except Exception:
                pass


async def run_content_gate(report_id: str, clip_path: Path, marker_path: Optional[Path]) -> dict:
    """Quick AI gate that validates a clip before deep analysis.
    Returns a structured dict; never raises (falls back to permissive on error)."""
    try:
        gate = await call_gemini_with_video(
            session_id=f"gate-{report_id}",
            prompt=CONTENT_GATE_PROMPT,
            video_path=str(clip_path),
            marker_path=str(marker_path) if marker_path and marker_path.exists() else None,
        )
        # Basic sanity defaults
        gate.setdefault("is_football", True)
        gate.setdefault("quality", "good")
        gate.setdefault("player_visible", "clear")
        gate.setdefault("content_type", "other")
        gate.setdefault("games_detected", 1)
        gate.setdefault("camera_distance", "medium")
        gate.setdefault("issues", [])
        gate.setdefault("rejection_reason", None)
        return gate
    except Exception as e:
        logger.warning(f"Content gate failed, falling back to permissive: {e}")
        return {
            "is_football": True,
            "content_type": "other",
            "quality": "good",
            "player_visible": "clear",
            "games_detected": 1,
            "camera_distance": "medium",
            "issues": [],
            "rejection_reason": None,
            "gate_error": True,
        }


def gate_rejection_message(gate: dict) -> Optional[str]:
    """Return a user-facing rejection message if the gate result requires rejection. Otherwise None."""
    if not gate.get("is_football", True):
        return (
            gate.get("rejection_reason")
            or "This video doesn't look like football. Please upload a clip of a match, training, drill, or freestyle work with a football."
        )
    if gate.get("quality") == "unwatchable":
        return (
            gate.get("rejection_reason")
            or "The video quality is too low to analyse reliably. Please upload a clearer recording (better lighting, less shake, closer to the action)."
        )
    if gate.get("player_visible") == "not_visible":
        return (
            gate.get("rejection_reason")
            or "We couldn't spot the marked player in this footage. Mark a different moment where the player is clearly on screen, or upload a clip that includes them."
        )
    return None


def transcode_to_web_mp4(src_path: Path) -> Path:
    """
    Convert the uploaded video to a browser-friendly MP4 (H.264 + AAC, faststart).
    Returns the new file path. Falls back to original if ffmpeg fails.
    """
    import subprocess
    out_path = src_path.with_suffix(".web.mp4")
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(src_path),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                "-vf", "scale='min(1280,iw)':-2",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                "-loglevel", "error",
                str(out_path),
            ],
            capture_output=True, timeout=180,
        )
        if result.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
            return out_path
        logger.warning(f"ffmpeg returncode={result.returncode}, stderr={result.stderr[:300]}")
    except Exception as e:
        logger.warning(f"ffmpeg transcode failed: {e}")
    return src_path


def get_video_duration_seconds(path: Path) -> float:
    """Return video duration in seconds (0 on failure)."""
    import subprocess
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, timeout=15, text=True,
        )
        if result.returncode == 0:
            return float(result.stdout.strip() or 0)
    except Exception as e:
        logger.warning(f"ffprobe failed: {e}")
    return 0.0


def make_preview_clip(video_path: Path, marker_seconds: float, window_seconds: int = 15) -> Path:
    """
    Cut a short window (~window_seconds) centered around the marker timestamp.
    Returns the new clip path. Falls back to the original video on failure or if
    the video is already shorter than the window.
    """
    import subprocess
    duration = get_video_duration_seconds(video_path)
    if duration <= window_seconds + 0.5:
        return video_path  # already short enough — analyse the whole thing

    half_before = 8.0
    start = max(0.0, float(marker_seconds) - half_before)
    end = start + window_seconds
    if end > duration:
        end = duration
        start = max(0.0, end - window_seconds)
    actual_window = end - start

    out_path = video_path.with_name(video_path.stem + ".preview.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.2f}",
        "-i", str(video_path),
        "-t", f"{actual_window:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
        "-loglevel", "error",
        str(out_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=60)
        if r.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
            return out_path
        logger.warning(f"preview clip ffmpeg failed: {r.stderr[:300]}")
    except Exception as e:
        logger.warning(f"preview clip failed: {e}")
    return video_path


def generate_poster(video_path: Path) -> Optional[Path]:
    """Extract a single-frame poster JPG from the video. Returns None on failure."""
    import subprocess
    poster_path = video_path.with_suffix(".poster.jpg")
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(video_path),
                "-ss", "00:00:02", "-vframes", "1",
                "-vf", "scale='min(1280,iw)':-2",
                "-q:v", "4",
                "-loglevel", "error",
                str(poster_path),
            ],
            capture_output=True, timeout=30,
        )
        if result.returncode == 0 and poster_path.exists():
            return poster_path
    except Exception as e:
        logger.warning(f"Poster generation failed: {e}")
    return None


# ============== ROUTES: HEALTH ==============

@api_router.get("/")
async def root():
    return {"status": "ok", "service": "Elite Football AI Scout API"}


# ============== ROUTES: AUTH ==============

@api_router.post("/auth/signup", response_model=TokenResponse)
async def signup(payload: UserSignup, request: Request, background_tasks: BackgroundTasks):
    # Honeypot — the visible signup form leaves the hidden "website" field empty.
    # Bots that fill every field trigger this branch and get a soft-reject that
    # looks identical to a real success in the network tab.
    if (payload.website or "").strip():
        logger.info("Honeypot triggered on /auth/signup — silently rejecting bot signup")
        raise HTTPException(status_code=400, detail="Signup could not be completed. Please try again.")

    ip = _client_ip(request)
    await _signup_rate_limit_check(ip)
    validate_password_strength(payload.password)

    existing = await db.users.find_one({"email": payload.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = str(uuid.uuid4())
    user_doc = {
        "id": user_id,
        "email": payload.email.lower(),
        "password_hash": hash_password(payload.password),
        "full_name": payload.full_name.strip(),
        "role": "user",
        "created_at": now_iso(),
    }
    await db.users.insert_one(user_doc)
    await _signup_rate_limit_record(ip)
    # Fire-and-forget welcome email — never blocks the signup response.
    # Silently no-ops when SMTP env vars aren't configured (dev / preview).
    try:
        html, text, subject = render_welcome_email(user_doc["full_name"])
        background_tasks.add_task(send_email, user_doc["email"], subject, html, text)
    except Exception as exc:
        logger.warning("Could not queue welcome email for %s: %s", user_doc["email"], exc)
    token = create_token(user_id, user_doc["email"], "user")
    return TokenResponse(
        access_token=token,
        user=UserPublic(
            id=user_id,
            email=user_doc["email"],
            full_name=user_doc["full_name"],
            role="user",
            created_at=user_doc["created_at"],
        ),
    )


@api_router.post("/auth/login", response_model=TokenResponse)
async def login(payload: UserLogin, request: Request):
    ip = _client_ip(request)
    email = payload.email.lower()
    await _login_lockout_check(ip, email)
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        await _login_attempt_record_failure(ip, email)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await _login_attempt_clear(ip, email)
    token = create_token(user["id"], user["email"], user["role"])
    is_paid_scout = (user.get("scout_access") or {}).get("status") == "active"
    return TokenResponse(
        access_token=token,
        user=UserPublic(
            id=user["id"],
            email=user["email"],
            full_name=user["full_name"],
            role=user["role"],
            created_at=user["created_at"],
            is_paid_scout=is_paid_scout,
        ),
    )


# ── Password reset flow ────────────────────────────────────────────────
# Two-step: /auth/forgot-password creates a one-time-use token and emails
# the reset link. /auth/reset-password consumes the token and rotates the
# password hash. We ALWAYS return 200 on /forgot-password (even when the
# email is unknown) to avoid leaking which addresses are registered.

@api_router.post("/auth/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, request: Request, background_tasks: BackgroundTasks):
    email = payload.email.lower().strip()
    # Rate-limit password-reset requests by IP too — same window as signup.
    ip = _client_ip(request)
    try:
        await _signup_rate_limit_check(ip)
    except HTTPException:
        # Silently swallow to avoid confirming address enumeration.
        return {"ok": True, "message": "If an account exists for that email, you'll receive a reset link shortly."}

    user = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "email": 1, "full_name": 1})
    if user:
        token = _generate_reset_token()
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=_RESET_TOKEN_TTL_MINUTES))
        await db.password_reset_tokens.insert_one({
            "token": token,
            "user_id": user["id"],
            "email": user["email"],
            "expires_at": expires_at,  # datetime object for TTL index compatibility
            "used": False,
            "created_at": now_iso(),
            "ip": ip,
        })
        # Build reset URL against the frontend origin.
        frontend_origin = os.environ.get("PUBLIC_FRONTEND_URL") or str(request.url).split("/api/")[0]
        reset_url = f"{frontend_origin}/reset-password?token={token}"
        try:
            from email_templates import render_bulk_email  # reuse the branded chrome
            body_html = (
                f"<p>We received a request to reset the password for your ScoutMePlay account.</p>"
                f"<p>Click the button below within the next {_RESET_TOKEN_TTL_MINUTES} minutes to choose a new password:</p>"
                f"<p style='margin:24px 0;'><a href='{reset_url}' "
                f"style='background:#1F4F2F;color:#fff;padding:14px 24px;font-weight:800;"
                f"letter-spacing:2px;text-transform:uppercase;text-decoration:none;font-size:13px;'>Reset my password</a></p>"
                f"<p style='font-size:12px;color:#666;'>If the button doesn't work, copy this link:<br/>"
                f"<span style='word-break:break-all;color:#1F4F2F;'>{reset_url}</span></p>"
                f"<p>If you didn't request this, you can safely ignore this email — your password won't change.</p>"
            )
            html, text, subject = render_bulk_email(
                subject="Reset your ScoutMePlay password",
                body_html=body_html,
                preheader="Click within 60 minutes to reset your password",
            )
            background_tasks.add_task(send_email, user["email"], subject, html, text)
        except Exception as exc:
            logger.warning("Could not queue reset email for %s: %s", email, exc)
    else:
        # No user with that email — still log the attempt so brute-force scans
        # against valid emails don't slip past without being counted.
        logger.info("Password-reset requested for unknown email %s (ip=%s)", email, ip)

    return {"ok": True, "message": "If an account exists for that email, you'll receive a reset link shortly."}


@api_router.post("/auth/reset-password", response_model=TokenResponse)
async def reset_password(payload: ResetPasswordRequest, request: Request):
    validate_password_strength(payload.new_password)

    token_doc = await db.password_reset_tokens.find_one({"token": payload.token}, {"_id": 0})
    if not token_doc or token_doc.get("used"):
        raise HTTPException(status_code=400, detail="This reset link is no longer valid. Request a new one.")

    expires_at = token_doc.get("expires_at")
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            expires_at = None
    if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
        # Mongo hands datetimes back naive-UTC; make them explicit so the
        # comparison against `datetime.now(tz=UTC)` doesn't blow up.
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not expires_at or expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="This reset link has expired. Request a new one.")

    user = await db.users.find_one({"id": token_doc["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=400, detail="Account no longer exists.")

    # Rotate the password hash and consume the token.
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": hash_password(payload.new_password), "password_updated_at": now_iso()}},
    )
    await db.password_reset_tokens.update_one(
        {"token": payload.token},
        {"$set": {"used": True, "used_at": now_iso()}},
    )
    # Clear any brute-force lockout for this user.
    await db.login_attempts.delete_many({"key": {"$regex": f":{user['email']}$"}})

    # Log the user in immediately (matches "reset → dashboard" UX expectation).
    access_token = create_token(user["id"], user["email"], user["role"])
    is_paid_scout = (user.get("scout_access") or {}).get("status") == "active"
    return TokenResponse(
        access_token=access_token,
        user=UserPublic(
            id=user["id"],
            email=user["email"],
            full_name=user["full_name"],
            role=user["role"],
            created_at=user["created_at"],
            is_paid_scout=is_paid_scout,
        ),
    )


@api_router.get("/auth/me", response_model=UserPublic)
async def me(user=Depends(get_current_user)):
    is_paid_scout = (user.get("scout_access") or {}).get("status") == "active"
    return UserPublic(
        id=user["id"],
        email=user["email"],
        full_name=user["full_name"],
        role=user["role"],
        created_at=user["created_at"],
        is_paid_scout=is_paid_scout,
    )


# ============== ROUTES: PLAYER PROFILE & VISIBILITY ==============
# Phase 1 of the "Scout Database" feature — every player now has an editable
# public profile (avatar + position + physical stats + country + club) plus a
# `discoverable` toggle that opts them in/out of the paid scout search index.
# Minors (<16 by birth_year) must confirm parental_consent to be discoverable.

_AVATAR_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_AVATAR_ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp"}


def _public_profile_of(user_doc: dict) -> dict:
    pp = user_doc.get("public_profile") or {}
    avatar_filename = user_doc.get("avatar_filename")
    # avatar_filename is stored as "avatars/<user_id>.<ext>" — pass through as-is
    # under /api/uploads/ (which is mounted on UPLOAD_DIR).
    avatar_url = f"/api/uploads/{avatar_filename}" if avatar_filename else None
    return {
        "user_id": user_doc.get("id"),
        "full_name": user_doc.get("full_name"),
        "email": user_doc.get("email"),
        "role": user_doc.get("role"),
        "avatar_url": avatar_url,
        "avatar_source": user_doc.get("avatar_source"),
        "discoverable": bool(user_doc.get("discoverable", False)),
        "parent_consent": bool(user_doc.get("parent_consent", False)),
        "birth_year": user_doc.get("birth_year"),
        "public_profile": {
            "position": pp.get("position"),
            "preferred_foot": pp.get("preferred_foot"),
            "height_cm": pp.get("height_cm"),
            "weight_kg": pp.get("weight_kg"),
            "country": pp.get("country"),
            "club": pp.get("club"),
            "bio": pp.get("bio"),
        },
        "discoverable_updated_at": user_doc.get("discoverable_updated_at"),
    }


class PublicProfileUpdate(BaseModel):
    position: Optional[str] = None
    preferred_foot: Optional[str] = None  # left / right / both
    height_cm: Optional[int] = None
    weight_kg: Optional[int] = None
    country: Optional[str] = None
    club: Optional[str] = None
    bio: Optional[str] = None


class ProfileVisibilityUpdate(BaseModel):
    discoverable: Optional[bool] = None
    parent_consent: Optional[bool] = None
    birth_year: Optional[int] = None
    public_profile: Optional[PublicProfileUpdate] = None


def _is_minor(birth_year: Optional[int]) -> bool:
    if not birth_year:
        return False
    try:
        current_year = datetime.now(timezone.utc).year
        return (current_year - int(birth_year)) < 16
    except (TypeError, ValueError):
        return False


@api_router.get("/profile/me")
async def get_my_profile(user=Depends(get_current_user)):
    """Returns the caller's full profile (avatar, visibility toggles, public fields)."""
    full_doc = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
    if not full_doc:
        raise HTTPException(status_code=404, detail="User not found")
    return _public_profile_of(full_doc)


@api_router.put("/profile/me")
async def update_my_profile(payload: ProfileVisibilityUpdate, user=Depends(get_current_user)):
    """Update visibility toggles + public profile fields.
    Enforces parental-consent gate for minors — a discoverable=True from a user
    with birth_year making them <16 is rejected unless parent_consent is also True.
    """
    updates: dict = {}
    if payload.birth_year is not None:
        updates["birth_year"] = int(payload.birth_year)
    if payload.parent_consent is not None:
        updates["parent_consent"] = bool(payload.parent_consent)

    # discoverable gate: minors require parent_consent
    if payload.discoverable is not None:
        want_discoverable = bool(payload.discoverable)
        if want_discoverable:
            effective_by = updates.get("birth_year", user.get("birth_year"))
            effective_pc = updates.get("parent_consent", user.get("parent_consent"))
            if _is_minor(effective_by) and not effective_pc:
                raise HTTPException(
                    status_code=400,
                    detail="Parental consent is required for players under 16 to be discoverable.",
                )
        updates["discoverable"] = want_discoverable
        updates["discoverable_updated_at"] = now_iso()

    if payload.public_profile is not None:
        existing_pp = user.get("public_profile") or {}
        merged = dict(existing_pp)
        for k, v in payload.public_profile.dict(exclude_unset=True).items():
            merged[k] = v
        updates["public_profile"] = merged

    if not updates:
        return _public_profile_of(user)

    await db.users.update_one({"id": user["id"]}, {"$set": updates})
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
    return _public_profile_of(fresh)


@api_router.post("/profile/avatar/upload")
async def upload_avatar(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Upload a custom avatar. Replaces any previous avatar for this user."""
    if file.content_type not in _AVATAR_ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Only JPG, PNG or WEBP images are allowed.")
    avatars_dir = UPLOAD_DIR / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)
    ext = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp"}.get(
        file.content_type, "jpg"
    )
    fname = f"{user['id']}.{ext}"
    fpath = avatars_dir / fname
    total = 0
    with fpath.open("wb") as buf:
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _AVATAR_MAX_BYTES:
                fpath.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Avatar must be 5 MB or smaller.")
            buf.write(chunk)
    # Remove any old avatars in a different extension for this user
    for other in avatars_dir.glob(f"{user['id']}.*"):
        if other.name != fname:
            other.unlink(missing_ok=True)
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "avatar_filename": f"avatars/{fname}",
            "avatar_source": "upload",
            "avatar_updated_at": now_iso(),
        }},
    )
    return {
        "ok": True,
        "avatar_url": f"/api/uploads/avatars/{fname}",
        "avatar_source": "upload",
    }


@api_router.post("/profile/avatar/from-report/{report_id}")
async def avatar_from_report(report_id: str, user=Depends(get_current_user)):
    """Auto-generate an avatar from the cropped subject frame of one of the
    user's own reports. Uses the existing `subject_crop_filename` (already
    produced by the background pipeline from the 10-tap marked bounding box).
    """
    report = await db.reports.find_one({"id": report_id, "user_id": user["id"]}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found for this user")
    crop_name = report.get("subject_crop_filename")
    if not crop_name:
        raise HTTPException(
            status_code=400,
            detail="This report has no player crop yet — try again once analysis finishes.",
        )
    src = UPLOAD_DIR / crop_name
    if not src.exists():
        raise HTTPException(status_code=404, detail="Player crop file is missing on disk")

    avatars_dir = UPLOAD_DIR / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{user['id']}.jpg"
    dst = avatars_dir / fname
    shutil.copyfile(src, dst)
    # Clear any other-extension leftovers
    for other in avatars_dir.glob(f"{user['id']}.*"):
        if other.name != fname:
            other.unlink(missing_ok=True)
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "avatar_filename": f"avatars/{fname}",
            "avatar_source": "auto_video",
            "avatar_updated_at": now_iso(),
            "avatar_from_report_id": report_id,
        }},
    )
    return {
        "ok": True,
        "avatar_url": f"/api/uploads/avatars/{fname}",
        "avatar_source": "auto_video",
        "from_report_id": report_id,
    }


@api_router.delete("/profile/avatar")
async def delete_avatar(user=Depends(get_current_user)):
    avatars_dir = UPLOAD_DIR / "avatars"
    for f in avatars_dir.glob(f"{user['id']}.*"):
        f.unlink(missing_ok=True)
    await db.users.update_one(
        {"id": user["id"]},
        {"$unset": {"avatar_filename": "", "avatar_source": "", "avatar_from_report_id": ""}},
    )
    return {"ok": True}


# ============== ROUTES: DEMO VIDEOS (Landing "How it works" carousel) ==============
# Admin-uploaded short iPhone videos that demo the workflow (upload → mark →
# report). Displayed in a swipeable carousel on the landing page directly
# below the "How it works" section.

_DEMO_VIDEO_MAX_BYTES = 100 * 1024 * 1024  # 100 MB — plenty for a 30-60s iPhone clip
_DEMO_VIDEO_ALLOWED = {"video/mp4", "video/quicktime", "video/webm", "video/x-m4v"}
_DEMO_POSTER_ALLOWED = {"image/jpeg", "image/jpg", "image/png", "image/webp"}


class DemoVideoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    subtitle: Optional[str] = Field(default=None, max_length=180)
    video_url: str = Field(min_length=1, max_length=500)
    poster_url: Optional[str] = Field(default=None, max_length=500)
    order: Optional[int] = 0
    status: Optional[str] = "active"  # "active" | "draft"


class DemoVideoUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=80)
    subtitle: Optional[str] = Field(default=None, max_length=180)
    video_url: Optional[str] = Field(default=None, max_length=500)
    poster_url: Optional[str] = Field(default=None, max_length=500)
    order: Optional[int] = None
    status: Optional[str] = None


def _serialize_demo_video(doc: dict) -> dict:
    return {
        "id": doc.get("id"),
        "title": doc.get("title"),
        "subtitle": doc.get("subtitle"),
        "video_url": doc.get("video_url"),
        "poster_url": doc.get("poster_url"),
        "order": int(doc.get("order") or 0),
        "status": doc.get("status") or "active",
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


@api_router.get("/demo-videos")
async def public_list_demo_videos():
    """Public — landing page fetches this. Only active videos, ordered."""
    cursor = db.demo_videos.find({"status": "active"}, {"_id": 0}).sort("order", 1)
    items = [_serialize_demo_video(d) async for d in cursor]
    return {"items": items}


# ─── Cloudflare R2 streaming proxy ──────────────────────────────────────────
# Streams objects from R2 through the backend. Used when the R2 bucket isn't
# exposed via a public URL (no r2.dev subdomain + no custom domain). Supports
# HTTP Range requests so <video> elements can seek. Keys are always safe:
# they only reference objects the backend itself wrote via r2_storage.
@api_router.get("/media/{key:path}")
@api_router.head("/media/{key:path}")
async def stream_r2_media(key: str, request: Request):
    if not r2_storage.is_configured():
        raise HTTPException(404, "Media not found")
    # Basic safety: block obvious traversal / control chars. R2 keys are
    # forward-slash-separated but never absolute.
    if key.startswith("/") or ".." in key or "\x00" in key:
        raise HTTPException(400, "Bad media key")

    range_header = request.headers.get("range") or request.headers.get("Range")
    try:
        obj = r2_storage.get_stream(key, range_header=range_header)
    except Exception as e:
        # Distinguish "object doesn't exist" (return 404) from real errors (502).
        err_response = getattr(e, "response", None) or {}
        code = ""
        if isinstance(err_response, dict):
            code = err_response.get("Error", {}).get("Code", "") or str(err_response.get("ResponseMetadata", {}).get("HTTPStatusCode", ""))
        err_str = str(e)
        logger.info(f"[R2 stream] key={key} err_code={code!r} err={err_str[:200]}")
        if code in ("NoSuchKey", "NoSuchBucket", "404") or "NoSuchKey" in err_str or "Not Found" in err_str:
            raise HTTPException(404, "Media not found") from None
        raise HTTPException(502, f"Upstream media error: {code or err_str[:80]}") from None

    headers = {
        "Content-Type": obj.get("ContentType") or "application/octet-stream",
        "Accept-Ranges": "bytes",
        "Cache-Control": obj.get("CacheControl") or "public, max-age=31536000, immutable",
    }
    content_length = obj.get("ContentLength")
    if content_length is not None:
        headers["Content-Length"] = str(content_length)
    content_range = obj.get("ContentRange")
    status_code = 200
    if content_range:
        headers["Content-Range"] = content_range
        status_code = 206  # partial content
    etag = obj.get("ETag")
    if etag:
        headers["ETag"] = etag

    # HEAD requests: return headers only, no body.
    if request.method.upper() == "HEAD":
        try:
            obj["Body"].close()
        except Exception:
            pass
        return Response(status_code=status_code, headers=headers)

    body = obj["Body"]  # botocore StreamingBody
    def iter_chunks():
        try:
            for chunk in body.iter_chunks(chunk_size=64 * 1024):
                if chunk:
                    yield chunk
        finally:
            try:
                body.close()
            except Exception:
                pass

    return StreamingResponse(iter_chunks(), status_code=status_code, headers=headers)


@api_router.get("/admin/demo-videos")
async def admin_list_demo_videos(_=Depends(get_current_admin)):
    cursor = db.demo_videos.find({}, {"_id": 0}).sort("order", 1)
    items = [_serialize_demo_video(d) async for d in cursor]
    return {"items": items}


@api_router.post("/admin/demo-videos")
async def admin_create_demo_video(payload: DemoVideoCreate, _=Depends(get_current_admin)):
    doc = {
        "id": str(uuid.uuid4()),
        "title": payload.title.strip(),
        "subtitle": (payload.subtitle or "").strip() or None,
        "video_url": payload.video_url.strip(),
        "poster_url": (payload.poster_url or "").strip() or None,
        "order": int(payload.order or 0),
        "status": payload.status if payload.status in ("active", "draft") else "active",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.demo_videos.insert_one(doc)
    return _serialize_demo_video(doc)


@api_router.put("/admin/demo-videos/{video_id}")
async def admin_update_demo_video(video_id: str, payload: DemoVideoUpdate, _=Depends(get_current_admin)):
    updates = {}
    for field in ("title", "subtitle", "video_url", "poster_url"):
        v = getattr(payload, field)
        if v is not None:
            updates[field] = v.strip() if isinstance(v, str) else v
    if payload.order is not None:
        updates["order"] = int(payload.order)
    if payload.status in ("active", "draft"):
        updates["status"] = payload.status
    if not updates:
        raise HTTPException(400, "No fields to update")
    updates["updated_at"] = now_iso()
    result = await db.demo_videos.update_one({"id": video_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Demo video not found")
    fresh = await db.demo_videos.find_one({"id": video_id}, {"_id": 0})
    return _serialize_demo_video(fresh)


@api_router.delete("/admin/demo-videos/{video_id}")
async def admin_delete_demo_video(video_id: str, _=Depends(get_current_admin)):
    doc = await db.demo_videos.find_one({"id": video_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Demo video not found")
    # Best-effort cleanup — remove both local files (legacy) and R2 objects (new).
    for url_key in ("video_url", "poster_url"):
        url = doc.get(url_key) or ""
        if url.startswith("/api/uploads/demo_videos/"):
            local = UPLOAD_DIR / url.replace("/api/uploads/", "", 1)
            local.unlink(missing_ok=True)
        elif r2_storage.is_configured():
            key = r2_storage.key_from_url(url)
            if key:
                r2_storage.delete_object(key)
    await db.demo_videos.delete_one({"id": video_id})
    return {"ok": True, "deleted_id": video_id}


@api_router.post("/admin/demo-videos/upload-video")
async def admin_upload_demo_video_file(file: UploadFile = File(...), _=Depends(get_current_admin)):
    """Upload an iPhone MOV / MP4 video file. Re-encodes to browser-safe H.264 8-bit
    (Chrome/Firefox can't decode HEVC/10-bit iPhone footage), auto-generates a poster,
    and pushes both to Cloudflare R2 (fallback: local disk if R2 is not configured)."""
    if file.content_type not in _DEMO_VIDEO_ALLOWED:
        raise HTTPException(400, f"Only MP4 / MOV / WebM videos are allowed (got {file.content_type})")
    demo_dir = UPLOAD_DIR / "demo_videos"
    demo_dir.mkdir(parents=True, exist_ok=True)
    ext_by_mime = {
        "video/mp4": "mp4",
        "video/quicktime": "mov",
        "video/webm": "webm",
        "video/x-m4v": "m4v",
    }
    ext = ext_by_mime.get(file.content_type, "mp4")
    stem = uuid.uuid4().hex
    fname = f"{stem}.{ext}"
    fpath = demo_dir / fname
    total = 0
    with fpath.open("wb") as buf:
        while True:
            chunk = await file.read(1024 * 1024)  # 1 MB chunks
            if not chunk:
                break
            total += len(chunk)
            if total > _DEMO_VIDEO_MAX_BYTES:
                fpath.unlink(missing_ok=True)
                raise HTTPException(413, "Video is too large (max 100 MB).")
            buf.write(chunk)

    # Re-encode to browser-safe H.264 8-bit + AAC + faststart. Chrome/Firefox
    # can't decode HEVC or yuv420p10le which iPhones default to.
    web_path = demo_dir / f"{stem}.web.mp4"
    poster_path = demo_dir / f"{stem}.poster.jpg"
    final_url = f"/api/uploads/demo_videos/{fname}"  # fallback if ffmpeg fails
    poster_url = None
    web_created = False
    try:
        import subprocess
        r = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(fpath),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
                "-pix_fmt", "yuv420p",
                "-vf", "scale='min(1280,iw)':-2",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                "-loglevel", "error",
                str(web_path),
            ],
            capture_output=True, timeout=180,
        )
        if r.returncode == 0 and web_path.exists() and web_path.stat().st_size > 0:
            fpath.unlink(missing_ok=True)  # drop the original — .web.mp4 is what we serve
            final_url = f"/api/uploads/demo_videos/{stem}.web.mp4"
            web_created = True
            # Auto-extract a poster from ~1s in (avoids all-black first frame)
            try:
                pr = subprocess.run(
                    [
                        "ffmpeg", "-y", "-ss", "1", "-i", str(web_path),
                        "-vframes", "1", "-q:v", "3",
                        "-loglevel", "error",
                        str(poster_path),
                    ],
                    capture_output=True, timeout=30,
                )
                if pr.returncode == 0 and poster_path.exists() and poster_path.stat().st_size > 0:
                    poster_url = f"/api/uploads/demo_videos/{stem}.poster.jpg"
            except Exception as e:
                logger.warning(f"demo-video poster extraction failed: {e}")
        else:
            logger.warning(f"demo-video ffmpeg transcode rc={r.returncode} stderr={r.stderr[:200]}")
    except Exception as e:
        logger.warning(f"demo-video ffmpeg transcode failed: {e}")

    # ── Push to Cloudflare R2 (only new uploads; existing local files untouched) ──
    if r2_storage.is_configured() and web_created:
        try:
            video_key = f"demo_videos/{stem}.web.mp4"
            uploaded_url = r2_storage.upload_file(video_key, web_path, "video/mp4")
            final_url = uploaded_url
            web_path.unlink(missing_ok=True)  # free container disk

            if poster_path.exists() and poster_path.stat().st_size > 0:
                poster_key = f"demo_videos/{stem}.poster.jpg"
                uploaded_poster = r2_storage.upload_file(poster_key, poster_path, "image/jpeg")
                poster_url = uploaded_poster
                poster_path.unlink(missing_ok=True)

            logger.info(f"[R2] demo-video uploaded key={video_key} url={final_url}")
        except Exception as e:
            # Never fail the upload if R2 has a hiccup — keep the local file so
            # the admin can still create the video row.
            logger.warning(f"[R2] demo-video upload failed, keeping local: {e}")

    return {
        "ok": True,
        "url": final_url,
        "poster_url": poster_url,
        "size_bytes": total,
        "content_type": file.content_type,
    }


@api_router.post("/admin/demo-videos/upload-poster")
async def admin_upload_demo_poster(file: UploadFile = File(...), _=Depends(get_current_admin)):
    """Optional poster/thumbnail image for a demo video."""
    if file.content_type not in _DEMO_POSTER_ALLOWED:
        raise HTTPException(400, "Only JPG, PNG or WEBP posters are allowed")
    demo_dir = UPLOAD_DIR / "demo_videos"
    demo_dir.mkdir(parents=True, exist_ok=True)
    ext = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp"}.get(file.content_type, "jpg")
    fname = f"poster-{uuid.uuid4().hex}.{ext}"
    fpath = demo_dir / fname
    total = 0
    with fpath.open("wb") as buf:
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > 5 * 1024 * 1024:
                fpath.unlink(missing_ok=True)
                raise HTTPException(413, "Poster is too large (max 5 MB).")
            buf.write(chunk)
    return {
        "ok": True,
        "url": f"/api/uploads/demo_videos/{fname}",
    }


# ============== ROUTES: VIDEO UPLOAD & FREE PREVIEW ==============

@api_router.get("/settings/price")
async def public_price():
    doc = await db.settings.find_one({"key": "report_price"}, {"_id": 0})
    value = doc.get("value", DEFAULT_PRICE) if doc else DEFAULT_PRICE
    pass_doc = await db.settings.find_one({"key": "pass_price"}, {"_id": 0})
    pass_value = pass_doc.get("value", DEFAULT_PASS_PRICE) if pass_doc else DEFAULT_PASS_PRICE
    # NEW: 3 monthly + single-report admin-controlled display prices
    single_doc = await db.settings.find_one({"key": "single_price"}, {"_id": 0})
    single_value = float(single_doc["value"]) if single_doc and "value" in single_doc else DEFAULT_SINGLE_PRICE
    prem_doc = await db.settings.find_one({"key": "premium_price"}, {"_id": 0})
    premium_value = float(prem_doc["value"]) if prem_doc and "value" in prem_doc else DEFAULT_PREMIUM_PRICE
    vip_doc = await db.settings.find_one({"key": "vip_price"}, {"_id": 0})
    vip_value = float(vip_doc["value"]) if vip_doc and "value" in vip_doc else DEFAULT_VIP_PRICE
    # NEW: per-report extra prices for subscribers who exhausted their quota.
    pem_doc = await db.settings.find_one({"key": "premium_extra_report_price"}, {"_id": 0})
    premium_extra_value = float(pem_doc["value"]) if pem_doc and "value" in pem_doc else DEFAULT_PREMIUM_EXTRA_PRICE
    vex_doc = await db.settings.find_one({"key": "vip_extra_report_price"}, {"_id": 0})
    vip_extra_value = float(vex_doc["value"]) if vex_doc and "value" in vex_doc else DEFAULT_VIP_EXTRA_PRICE
    landing_doc = await db.settings.find_one({"key": "active_landing"}, {"_id": 0})
    landing_value = landing_doc.get("value", "minimal") if landing_doc else "minimal"
    if landing_value not in ("full", "minimal"):
        landing_value = "minimal"
    # `price_dkk` is kept only as a legacy alias for older frontend builds
    return {
        "price": float(value),
        "pass_price": float(pass_value),
        "single_price": float(single_value),
        "premium_price": float(premium_value),
        "vip_price": float(vip_value),
        "premium_extra_price": float(premium_extra_value),
        "vip_extra_price": float(vip_extra_value),
        "currency": PRICE_CURRENCY,
        "price_dkk": float(value),
        "social": await get_social_links(),
        "active_landing": landing_value,
    }


@api_router.get("/settings/landing")
async def public_active_landing():
    """Lightweight endpoint used by the Landing route to decide which
    variant to render. Avoids waiting for the full /settings/price payload."""
    doc = await db.settings.find_one({"key": "active_landing"}, {"_id": 0})
    value = doc.get("value", "minimal") if doc else "minimal"
    if value not in ("full", "minimal"):
        value = "minimal"
    return {"active_landing": value}


async def get_social_links() -> dict:
    """Resolve current social-link configuration: stored overrides merged onto defaults."""
    doc = await db.settings.find_one({"key": "social_links"})
    if doc and isinstance(doc.get("value"), dict):
        return {**DEFAULT_SOCIAL_LINKS, **doc["value"]}
    return DEFAULT_SOCIAL_LINKS


async def get_current_price() -> float:
    doc = await db.settings.find_one({"key": "report_price"})
    if doc and "value" in doc:
        return float(doc["value"])
    return DEFAULT_PRICE


async def get_pass_price() -> float:
    doc = await db.settings.find_one({"key": "pass_price"})
    if doc and "value" in doc:
        return float(doc["value"])
    return DEFAULT_PASS_PRICE


@api_router.post("/reports/upload")
async def upload_video_and_create_preview(
    background: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    temp_video_token: Optional[str] = Form(None),
    marker_image: UploadFile = File(...),
    marker_timestamp: float = Form(0.0),
    marker_box: Optional[str] = Form(None),  # legacy: JSON {"x":0..1,...}
    marker_anchors: Optional[str] = Form(None),  # NEW: JSON [{"t":sec,"box":{x,y,w,h}}, ...]
    player_name: str = Form(...),
    age: int = Form(...),
    position: str = Form(...),
    preferred_foot: str = Form(...),
    current_club: Optional[str] = Form(None),
    video_type: str = Form(...),
    description: str = Form(...),
    user=Depends(get_current_user),
):
    # ============== UPLOAD GATE ==============
    # Free users get ONE free preview lifetime. After that, every upload requires
    # a pre-payment OR a Progress Pass credit.
    is_admin = user.get("role") == "admin"
    free_used = bool(user.get("free_preview_used"))
    prepaid = int(user.get("prepaid_uploads", 0) or 0)
    pass_state = _progress_pass_active(user)
    used_pass_credit = False
    upload_will_be_paid = False
    if not is_admin:
        if free_used and prepaid <= 0 and not pass_state.get("active"):
            current_price = await get_current_price()
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "PREPAY_REQUIRED",
                    "message": f"Your free preview is used. Pay ${current_price:g} to upload your next video — or activate a Progress Pass to track growth.",
                },
            )
        # Prefer Progress Pass credit when prepaid credits are not present.
        if free_used and prepaid <= 0 and pass_state.get("active"):
            used_pass_credit = True
            upload_will_be_paid = True
        else:
            upload_will_be_paid = free_used and prepaid > 0
    else:
        # Admins get a FULL premium report for every upload they make — no
        # payment, no eligibility burn, no preview/teaser. Setting
        # `upload_will_be_paid = True` makes the document `is_paid: True` so the
        # background `generate_full_report_task` auto-fires after the preview
        # (see line ~3717). All other admin guards (line 3163 `if not is_admin`,
        # line 3302 `if not is_admin` credit-burn skip) already exist.
        upload_will_be_paid = True

    # ============== RESOLVE SOURCE: file upload OR temp URL-fetch token ==============
    using_temp_token = False
    temp_file_path: Optional[Path] = None
    if not file and temp_video_token:
        temp_file_path = resolve_temp_token_path(upload_dir=UPLOAD_DIR, token=temp_video_token)
        if not temp_file_path:
            raise HTTPException(status_code=400, detail="Video URL fetch expired or not found. Please re-paste the link.")
        using_temp_token = True
    if not file and not using_temp_token:
        raise HTTPException(status_code=400, detail="No video provided. Upload a file or paste a video URL.")

    # Validate file type
    allowed_mimes = {"video/mp4", "video/quicktime", "video/x-m4v", "video/webm"}
    if not using_temp_token and file.content_type not in allowed_mimes:
        raise HTTPException(status_code=400, detail=f"Unsupported video format: {file.content_type}. Use MP4, MOV, or WebM.")

    # Save video file
    report_id = str(uuid.uuid4())
    if using_temp_token:
        ext = temp_file_path.suffix.lstrip(".").lower() or "mp4"
    else:
        ext = (file.filename or "video.mp4").split(".")[-1].lower()
    if ext not in {"mp4", "mov", "m4v", "webm"}:
        ext = "mp4"
    stored_name = f"{report_id}.{ext}"
    file_path = UPLOAD_DIR / stored_name

    if using_temp_token:
        # Move the pre-downloaded temp file into the report-id naming convention
        shutil.move(str(temp_file_path), str(file_path))
    else:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

    file_size = file_path.stat().st_size

    # Save marker image (the frame the user circled the player on)
    marker_filename = f"{report_id}-marker.jpg"
    marker_path = UPLOAD_DIR / marker_filename
    with marker_path.open("wb") as buffer:
        shutil.copyfileobj(marker_image.file, buffer)

    # ============== CACHE RAW MARKER DATA FOR BACKGROUND TASK ==============
    # Heavy work (ffmpeg transcoding, fingerprinting, poster, preview clip, audio
    # peaks, duration validation) used to run inline here. On Cloudflare-fronted
    # production deployments this blew the 100-second edge timeout on larger
    # uploads. EVERYTHING after file save is now deferred to `analyze_preview_task`.
    #
    # The upload endpoint must return in ≲ 10 s — the time it takes the browser
    # to PUT the raw bytes plus a single Mongo insert.
    raw_marker_box = marker_box  # JSON string or None
    raw_marker_anchors = marker_anchors  # JSON string or None

    # Build player details summary
    details = {
        "player_name": player_name,
        "age": age,
        "position": position,
        "preferred_foot": preferred_foot,
        "current_club": current_club or "Independent",
        "video_type": video_type,
        "description": description,
    }

    # Persist the report doc with `analysis_status: "analyzing"` so the frontend
    # gets a valid report_id back IMMEDIATELY. The background task will fill in
    # `video_filename` (transcoded), `poster_filename`, `fingerprint`, `anchors`,
    # `audio_events_preview`, `content_gate`, and finally `preview`.
    report_doc = {
        "id": report_id,
        "user_id": user["id"],
        "user_email": user["email"],
        "player_details": details,
        # Until the background task transcodes the file, `video_filename` points
        # at the raw upload so the frontend status endpoint can fall back safely.
        "video_filename": stored_name,
        "original_video_filename": stored_name,
        "raw_upload_filename": stored_name,         # explicit handle for the bg task
        "poster_filename": None,                    # populated by background task
        "marker_filename": marker_filename,
        "marker_timestamp": float(marker_timestamp),
        # Raw JSON strings — parsed inside the bg task so we never crash the upload
        "raw_marker_box": raw_marker_box,
        "raw_marker_anchors": raw_marker_anchors,
        "video_duration_sec": None,                 # populated by background task
        "video_size_bytes": file_size,
        "content_gate": None,                       # populated by background task
        "preview": None,                            # populated by background task
        "full_report": None,
        "is_paid": bool(upload_will_be_paid),
        "manually_unlocked": False,
        "created_at": now_iso(),
        "paid_at": now_iso() if upload_will_be_paid else None,
        "fingerprint": None,                        # populated by background task
        "subject_crop_filename": None,
        "anchors": [],
        "audio_events_preview": [],
        # ----- async pipeline state -----
        "analysis_status": "analyzing",             # analyzing | ready | failed
        "progress_step": 1,                         # 1..5 — see analyze_preview_task
        "analysis_error": None,
        "eligibility_consumed": (                   # so the bg task can refund on failure
            "admin" if is_admin
            else ("pass_credit" if used_pass_credit
                  else ("prepaid" if upload_will_be_paid
                        else "free_preview"))
        ),
    }
    await db.reports.insert_one(report_doc)

    # ============== LINK TO PLAYER PROFILE ==============
    try:
        profile_id = await find_or_create_profile(db, user["id"], details, report_id)
        if profile_id:
            await db.reports.update_one({"id": report_id}, {"$set": {"player_profile_id": profile_id}})
    except Exception as e:
        logger.warning(f"Player profile link failed for report {report_id}: {e}")
        profile_id = None

    # ============== CONSUME ELIGIBILITY ==============
    # Burn the credit NOW (synchronously) so users can't game the system by spamming
    # uploads while the background task runs. The background task will refund this
    # credit if the analysis ultimately fails (content gate rejection or Gemini error).
    if not is_admin:
        if used_pass_credit:
            await consume_pass_credit(db, user["id"])
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"last_upload_at": now_iso()}},
            )
        elif upload_will_be_paid:
            await db.users.update_one(
                {"id": user["id"]},
                {"$inc": {"prepaid_uploads": -1}, "$set": {"last_upload_at": now_iso()}},
            )
        elif not free_used:
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"free_preview_used": True, "last_upload_at": now_iso()}},
            )

    # ============== KICK OFF THE BACKGROUND TASK ==============
    background.add_task(analyze_preview_task, report_id)

    # Return IMMEDIATELY so the HTTP request never holds RAM longer than ~10 s
    # (just enough to save the file). This is the structural fix for Cloudflare
    # 524/520 timeouts on production: ffmpeg transcoding + Gemini calls now run
    # entirely outside the request lifecycle.
    return {
        "id": report_id,
        "player_details": details,
        "preview": None,                       # frontend polls /status for this
        "is_paid": bool(upload_will_be_paid),
        "created_at": report_doc["created_at"],
        "analysis_status": "analyzing",        # signal to the frontend to start polling
        "progress_step": 1,
    }


def _resolve_video_url(doc: dict) -> Optional[str]:
    """Resolve the playable video URL for a report doc.

    Priority: explicit override (R2 or full HTTP URL) > legacy `/api/uploads/` path.
    Reports migrated to R2 have `video_url_override` set to a full URL / proxy path.
    """
    override = doc.get("video_url_override")
    if override:
        return override
    vf = doc.get("video_filename")
    return f"/api/uploads/{vf}" if vf else None


def _resolve_poster_url(doc: dict) -> Optional[str]:
    """Same priority as _resolve_video_url but for the poster thumbnail."""
    override = doc.get("poster_url_override")
    if override:
        return override
    pf = doc.get("poster_filename")
    return f"/api/uploads/{pf}" if pf else None


@api_router.get("/reports/{report_id}/status")
async def get_report_status(report_id: str, user=Depends(get_current_user)):
    """Lightweight polling endpoint used by the frontend during async preview generation.

    Returns the current `analysis_status` (analyzing | ready | failed), an integer
    `progress_step` (1..5) the UI overlay can render honestly, and — once ready —
    the preview payload itself plus the URLs needed to render the report. Polled
    every ~3 seconds by `UploadPage.jsx` while the heavy Gemini work runs in the
    background task `analyze_preview_task`.
    """
    doc = await db.reports.find_one({"id": report_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found.")
    # Allow the owner or admin to poll
    if doc.get("user_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your report.")

    analysis_status = doc.get("analysis_status", "ready")  # legacy reports default to ready
    step = int(doc.get("progress_step", 5 if analysis_status == "ready" else 1) or 1)
    error = doc.get("analysis_error")

    out = {
        "id": report_id,
        "status": analysis_status,
        "progress_step": step,
        "error": error,
        # Full-report generation runs as its own background task after the
        # preview is ready; the frontend polls this same endpoint and just
        # reads `full_report_status` so it can show the right loading state.
        "full_report_status": doc.get("full_report_status") or ("ready" if doc.get("full_report") else None),
        "full_report_error": doc.get("full_report_error"),
        "has_full_report": bool(doc.get("full_report")),
    }
    if analysis_status == "ready":
        marker_filename = doc.get("marker_filename")
        out.update({
            "preview": doc.get("preview"),
            "player_details": doc.get("player_details"),
            "video_url": _resolve_video_url(doc),
            "poster_url": _resolve_poster_url(doc),
            "marker_url": f"/api/uploads/{marker_filename}" if marker_filename else None,
            "is_paid": bool(doc.get("is_paid")),
            "created_at": doc.get("created_at"),
        })
    return out


async def analyze_preview_task(report_id: str):
    """Background task — runs ALL heavy work (ffmpeg transcoding, fingerprinting,
    poster, preview clip, audio peaks, content gate, preview generation) OUTSIDE
    the HTTP request lifecycle.

    This is the structural fix for the Cloudflare 524/520 timeouts on production:
    keeping `ffmpeg -i video.mp4 -c:v libx264 …` inside the HTTP request blew the
    100-second Cloudflare edge timeout on larger uploads. Everything below now
    runs after the upload endpoint has already returned `{status: 'analyzing'}`.

    Step map (must align with the frontend PrecisionScanOverlay):
      1 = received & queued
      2 = preparing video (transcode + fingerprint + anchors + audio)
      3 = content gate verifying clip
      4 = building preview report
      5 = ready
    """
    try:
        # ------------------------------------------------------------------
        # Step 1 → Step 2: preparing video
        # ------------------------------------------------------------------
        await db.reports.update_one(
            {"id": report_id},
            {"$set": {"analysis_status": "analyzing", "progress_step": 2}},
        )
        doc = await db.reports.find_one({"id": report_id})
        if not doc:
            logger.error(f"analyze_preview_task: report {report_id} vanished")
            return

        details = doc.get("player_details") or {}
        details_str = json.dumps(details, ensure_ascii=False)
        marker_filename = doc.get("marker_filename")
        raw_filename = doc.get("raw_upload_filename") or doc.get("video_filename")
        marker_timestamp = float(doc.get("marker_timestamp") or 0.0)
        raw_marker_box = doc.get("raw_marker_box")
        raw_marker_anchors = doc.get("raw_marker_anchors")

        marker_path = UPLOAD_DIR / marker_filename if marker_filename else None
        raw_path = UPLOAD_DIR / raw_filename if raw_filename else None
        if not (marker_path and marker_path.exists() and raw_path and raw_path.exists()):
            await db.reports.update_one(
                {"id": report_id},
                {"$set": {
                    "analysis_status": "failed",
                    "analysis_error": "Source files missing after upload.",
                    "progress_step": 5,
                }},
            )
            try:
                await _refund_upload_eligibility(report_id)
            except Exception:
                pass
            return

        # ============== TRANSCODE TO WEB-FRIENDLY MP4 ==============
        # Convert to H.264/AAC so the clip plays in every browser. Heavy ffmpeg —
        # was the #1 contributor to the Cloudflare 100 s timeout on production.
        web_path = transcode_to_web_mp4(raw_path)
        web_filename = web_path.name
        # If the transcode produced a NEW file (different name), update the doc so
        # the status endpoint can serve the playable file. If transcoding fell
        # back to the original, video_filename stays as-is.
        if web_filename != raw_filename:
            await db.reports.update_one(
                {"id": report_id},
                {"$set": {"video_filename": web_filename}},
            )
            # ── DISK CLEANUP: now that the web-friendly .web.mp4 is saved AND
            # ── the report doc points at it, the original raw upload (.mov /
            # ── source .mp4) is no longer needed. Removing it here saves
            # ── ~60 % disk per upload and prevents the container disk from
            # ── filling. Best-effort only — failure to unlink is logged, not
            # ── fatal (transcode already succeeded, user impact is zero).
            try:
                if raw_path.exists() and raw_path.resolve() != web_path.resolve():
                    raw_bytes = raw_path.stat().st_size
                    raw_path.unlink()
                    logger.info(
                        f"raw-upload cleanup: removed {raw_path.name} "
                        f"({raw_bytes // 1024} KB) after successful transcode of {web_filename}"
                    )
            except Exception as cleanup_err:
                logger.warning(f"raw-upload cleanup failed for {report_id}: {cleanup_err}")

        # ============== DURATION VALIDATION (5-min cap) ==============
        duration_sec = get_video_duration_seconds(web_path)
        if duration_sec > 305:  # buffer for rounding
            await db.reports.update_one(
                {"id": report_id},
                {"$set": {
                    "analysis_status": "failed",
                    "analysis_error": (
                        f"Video is {duration_sec / 60:.1f} minutes. Maximum is 5 "
                        "minutes — please trim and re-upload."
                    ),
                    "video_duration_sec": duration_sec,
                    "progress_step": 5,
                }},
            )
            try:
                await _refund_upload_eligibility(report_id)
            except Exception as re:
                logger.warning(f"Eligibility refund failed for {report_id}: {re}")
            # Best-effort cleanup of the giant clip
            for p in {raw_path, web_path, marker_path}:
                try:
                    p.unlink()
                except Exception:
                    pass
            return
        await db.reports.update_one(
            {"id": report_id},
            {"$set": {"video_duration_sec": duration_sec}},
        )

        # ============== POSTER THUMBNAIL ==============
        poster_path = generate_poster(web_path)
        poster_filename = poster_path.name if poster_path else None
        if poster_filename:
            await db.reports.update_one(
                {"id": report_id},
                {"$set": {"poster_filename": poster_filename}},
            )

        # ============== PRECISION SCOUT — VISUAL FINGERPRINT (anchor 1) ==============
        fingerprint_payload = None
        crop_filename = None
        crop_path = None
        primary_box_data = None
        fp = None
        try:
            if raw_marker_box:
                primary_box_data = json.loads(raw_marker_box)
            elif raw_marker_anchors:
                anchors_seed = json.loads(raw_marker_anchors)
                if isinstance(anchors_seed, list) and anchors_seed:
                    primary_box_data = anchors_seed[0].get("box")
            if primary_box_data is None:
                primary_box_data = {"x": 0.40, "y": 0.30, "w": 0.20, "h": 0.50}

            crop_filename = f"{report_id}-subject.jpg"
            crop_path = UPLOAD_DIR / crop_filename
            fp = extract_player_fingerprint(
                marker_image_path=str(marker_path),
                box=primary_box_data,
                crop_save_path=str(crop_path),
            )
            fingerprint_payload = {
                "jersey_hex": fp.jersey_hex,
                "jersey_name": fp.jersey_name,
                "shorts_hex": fp.shorts_hex,
                "shorts_name": fp.shorts_name,
                "body_ratio": fp.body_ratio,
                "box": fp.box,
            }
            if not fp.crop_path:
                crop_filename = None
                crop_path = None
        except Exception as e:
            logger.warning(f"Precision fingerprint failed for {report_id}: {e}")
            fp = None
            fingerprint_payload = None

        # ============== EXTRA ANCHOR CROPS (anchors 2..5) ==============
        extra_anchors_payload: list[dict] = []
        anchor_crop_paths: list[str] = []
        if fp is not None and crop_path and Path(crop_path).exists():
            anchor_crop_paths.append(str(crop_path))
            extra_anchors_payload.append({
                "i": 1,
                "t": float(marker_timestamp or 0.0),
                "box": fp.box,
                "jersey_name": fp.jersey_name,
                "shorts_name": fp.shorts_name,
                "body_ratio": fp.body_ratio,
                "crop_filename": crop_filename,
            })
        if raw_marker_anchors:
            try:
                all_anchors = json.loads(raw_marker_anchors)
                if not isinstance(all_anchors, list):
                    all_anchors = []
            except Exception:
                all_anchors = []
            for idx, a in enumerate(all_anchors[1:6], start=2):
                try:
                    t_anchor = float(a.get("t", 0.0))
                    box_anchor = a.get("box") or {}
                    if not box_anchor:
                        continue
                    frame_filename = f"{report_id}-anchor-frame-{idx}.jpg"
                    frame_path = UPLOAD_DIR / frame_filename
                    if not extract_frame_at(web_path, t_anchor, frame_path):
                        continue
                    crop_filename_a = f"{report_id}-anchor-{idx}.jpg"
                    crop_path_a = UPLOAD_DIR / crop_filename_a
                    fp_a = extract_player_fingerprint(
                        marker_image_path=str(frame_path),
                        box=box_anchor,
                        crop_save_path=str(crop_path_a),
                    )
                    try:
                        frame_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    if fp_a.crop_path and Path(fp_a.crop_path).exists():
                        anchor_crop_paths.append(str(crop_path_a))
                        extra_anchors_payload.append({
                            "i": idx,
                            "t": t_anchor,
                            "box": fp_a.box,
                            "jersey_name": fp_a.jersey_name,
                            "shorts_name": fp_a.shorts_name,
                            "body_ratio": fp_a.body_ratio,
                            "crop_filename": crop_filename_a,
                        })
                except Exception as e:
                    logger.warning(f"Anchor {idx} extraction failed for {report_id}: {e}")

        # Persist fingerprint + anchors
        await db.reports.update_one(
            {"id": report_id},
            {"$set": {
                "fingerprint": fingerprint_payload,
                "subject_crop_filename": crop_filename,
                "anchors": extra_anchors_payload,
            }},
        )

        # ============== PREVIEW CLIP + AUDIO PEAKS ==============
        preview_clip_path = make_preview_clip(web_path, marker_seconds=marker_timestamp, window_seconds=15)
        try:
            audio_events_preview = extract_audio_events(preview_clip_path, top_n=5)
        except Exception as e:
            logger.warning(f"Audio extraction failed (preview) for {report_id}: {e}")
            audio_events_preview = []
        await db.reports.update_one(
            {"id": report_id},
            {"$set": {
                "audio_events_preview": [
                    {"t": e.t, "peak_db": e.peak_db, "kind": e.kind} for e in audio_events_preview
                ],
            }},
        )

        # Re-load the doc so downstream code sees the freshly persisted state.
        doc = await db.reports.find_one({"id": report_id})
        anchors = doc.get("anchors") or []
        audio_events_preview_raw = doc.get("audio_events_preview") or []
        fingerprint_payload = doc.get("fingerprint")

        # Rebuild the lightweight FingerPrint-like object the precision prompt needs
        fp_obj = None
        if fingerprint_payload:
            try:
                fp_obj = PlayerFingerprint(
                    jersey_hex=fingerprint_payload.get("jersey_hex", "#888888"),
                    jersey_name=fingerprint_payload.get("jersey_name", "unclear"),
                    shorts_hex=fingerprint_payload.get("shorts_hex", "#888888"),
                    shorts_name=fingerprint_payload.get("shorts_name", "unclear"),
                    body_ratio=float(fingerprint_payload.get("body_ratio", 2.0)),
                    crop_path=str(crop_path) if crop_path and Path(crop_path).exists() else None,
                    box=fingerprint_payload.get("box", {}),
                    confidence="ok",
                )
            except Exception:
                fp_obj = None

        # Convert the persisted audio event dicts back into the lightweight namedtuple-ish
        # objects the precision prompt builder expects (only the attrs it reads).
        audio_events_preview = [
            SimpleNamespace(t=float(e.get("t", 0)), peak_db=float(e.get("peak_db", 0)), kind=str(e.get("kind", "")))
            for e in audio_events_preview_raw
        ]

        # ============== CONTENT GATE (Gemini call #1) ==============
        # Step 2 → 3: content gate verifying clip
        await db.reports.update_one({"id": report_id}, {"$set": {"progress_step": 3}})
        gate = await run_content_gate(report_id, preview_clip_path, marker_path)
        rejection = gate_rejection_message(gate)
        if rejection:
            # Soft-reject: persist the error so the user sees a friendly message
            # AND refund the eligibility that was consumed at upload time.
            await db.reports.update_one(
                {"id": report_id},
                {"$set": {
                    "analysis_status": "failed",
                    "analysis_error": rejection,
                    "content_gate": gate,
                    "progress_step": 5,
                }},
            )
            try:
                await _refund_upload_eligibility(report_id)
            except Exception as e:
                logger.warning(f"Eligibility refund failed for {report_id}: {e}")
            return
        await db.reports.update_one({"id": report_id}, {"$set": {"content_gate": gate}})

        # ============== PREVIEW PROMPT BUILD ==============
        if fp_obj is not None:
            preview_prompt = precision_build_preview_prompt(
                base_prompt=PREVIEW_PROMPT,
                fingerprint=fp_obj,
                audio_events=audio_events_preview,
                player_details=details,
                content_type=str(gate.get("content_type", "other")),
                player_visible=str(gate.get("player_visible", "clear")),
                camera_distance=str(gate.get("camera_distance", "medium")),
                anchors=anchors,
            )
        else:
            preview_prompt = (
                PREVIEW_PROMPT
                .replace("{player_details}", details_str)
                .replace("{content_type}", str(gate.get("content_type", "other")))
                .replace("{player_visible}", str(gate.get("player_visible", "clear")))
                .replace("{camera_distance}", str(gate.get("camera_distance", "medium")))
            )

        # ============== PREVIEW GEMINI CALL (#2) ==============
        # Step 3 → 4: building preview report
        await db.reports.update_one({"id": report_id}, {"$set": {"progress_step": 4}})
        preview = await call_gemini_with_video(
            session_id=f"preview-{report_id}",
            prompt=preview_prompt,
            video_path=str(preview_clip_path),
            marker_path=str(marker_path),
            crop_path=str(crop_path) if crop_path and Path(crop_path).exists() else None,
            anchor_crops=anchor_crop_paths if len(anchor_crop_paths) > 1 else None,
        )
        preview = scrub_hedging(preview)

        # ============== PERSIST ==============
        await db.reports.update_one(
            {"id": report_id},
            {"$set": {
                "preview": preview,
                "analysis_status": "ready",
                "progress_step": 5,
                "analysis_error": None,
            }},
        )

        # ============== FLUSH VIDEO + POSTER TO R2 ==============
        # Preview + Gemini calls are done. Push the playable video and poster
        # to R2 and drop the local copies to keep the container disk clean.
        # Marker/subject/anchor crops stay local — they're small and may be
        # re-used by generate_full_report_task or admin re-generation flows.
        try:
            await _flush_preview_artifacts_to_r2(report_id)
        except Exception as e:
            logger.warning(f"R2 flush post-preview failed for {report_id}: {e}")

        # If the upload was prepaid / pass-credit, kick off the full premium report too.
        doc = await db.reports.find_one({"id": report_id})
        if doc and doc.get("is_paid"):
            asyncio.create_task(generate_full_report_task(report_id))
    except Exception as e:
        logger.exception(f"analyze_preview_task failed for {report_id}")
        await db.reports.update_one(
            {"id": report_id},
            {"$set": {
                "analysis_status": "failed",
                "analysis_error": f"AI preview generation failed: {str(e)[:200]}",
                "progress_step": 5,
            }},
        )
        try:
            await _refund_upload_eligibility(report_id)
        except Exception as re:
            logger.warning(f"Eligibility refund failed for {report_id}: {re}")


async def _refund_upload_eligibility(report_id: str):
    """Give back the credit consumed at upload time when the background analysis fails.
    Looks at the report doc's `eligibility_consumed` field (set by the upload endpoint)
    to decide which bucket to credit back."""
    doc = await db.reports.find_one({"id": report_id})
    if not doc:
        return
    consumed = doc.get("eligibility_consumed") or "none"
    user_id = doc.get("user_id")
    if not user_id:
        return
    if consumed == "free_preview":
        await db.users.update_one({"id": user_id}, {"$set": {"free_preview_used": False}})
    elif consumed == "prepaid":
        await db.users.update_one({"id": user_id}, {"$inc": {"prepaid_uploads": 1}})
    elif consumed == "pass_credit":
        # restore one progress pass credit
        await db.users.update_one({"id": user_id}, {"$inc": {"progress_pass.credits": 1}})


# ─── Report R2 storage helpers ──────────────────────────────────────────────
async def _flush_preview_artifacts_to_r2(report_id: str):
    """Push a completed report's playable video + poster to R2 and drop the
    local copies. Marker + subject + anchor crops stay LOCAL (small, may be
    re-used by admin flows / re-generation). Best-effort — never raises.

    Idempotent: if the override URLs are already set, or R2 isn't configured,
    this is a no-op."""
    if not r2_storage.is_configured():
        return
    doc = await db.reports.find_one({"id": report_id})
    if not doc:
        return
    updates: dict = {}

    # Video (.web.mp4)
    if not doc.get("video_url_override"):
        vf = doc.get("video_filename")
        if vf:
            vp = UPLOAD_DIR / vf
            if vp.exists() and vp.stat().st_size > 0:
                try:
                    key = f"reports/{report_id}/{vf}"
                    url = r2_storage.upload_file(key, vp, "video/mp4")
                    updates["video_url_override"] = url
                    vp.unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"R2 flush video failed {report_id}: {e}")

    # Poster (.web.poster.jpg)
    if not doc.get("poster_url_override"):
        pf = doc.get("poster_filename")
        if pf:
            pp = UPLOAD_DIR / pf
            if pp.exists() and pp.stat().st_size > 0:
                try:
                    key = f"reports/{report_id}/{pf}"
                    url = r2_storage.upload_file(key, pp, "image/jpeg")
                    updates["poster_url_override"] = url
                    pp.unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"R2 flush poster failed {report_id}: {e}")

    if updates:
        await db.reports.update_one({"id": report_id}, {"$set": updates})


async def _ensure_report_video_local(report_id: str) -> Optional[Path]:
    """Return a local Path to the report's playable video for ffmpeg / Gemini.
    If it's been flushed to R2, download it into /tmp first. Caller MUST NOT
    delete the file — a stale /tmp file is cheap; the process is short-lived.

    Returns None if the video cannot be located.
    """
    doc = await db.reports.find_one({"id": report_id})
    if not doc:
        return None
    vf = doc.get("video_filename")
    if vf:
        local = UPLOAD_DIR / vf
        if local.exists() and local.stat().st_size > 0:
            return local
    # Try R2 override
    override = doc.get("video_url_override")
    key = r2_storage.key_from_url(override) if override else None
    if not key or not r2_storage.is_configured():
        return None
    tmp_dir = Path(tempfile.gettempdir()) / "scoutmeplay_reports" / report_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dest = tmp_dir / (vf or f"{report_id}.web.mp4")
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    ok = r2_storage.download_to_file(key, dest)
    if not ok:
        return None
    return dest


@api_router.get("/reports/mine")
async def my_reports(user=Depends(get_current_user)):
    docs = await db.reports.find(
        {"user_id": user["id"]},
        {"_id": 0, "full_report": 0},
    ).sort("created_at", -1).to_list(100)
    for d in docs:
        d["video_url"] = _resolve_video_url(d)
        d["poster_url"] = _resolve_poster_url(d)
    return docs


def _default_agent_review(unlock_iso: Optional[str] = None) -> dict:
    """Default 'pending' agent review when a report is just unlocked."""
    return {
        "status": "pending",
        "created_at": unlock_iso or now_iso(),
        "delivered_at": None,
        "agent_name": None,
        "review_text": None,
        "messages": [],
    }


async def _ensure_agent_review(doc: dict) -> dict:
    """If the report is unlocked but has no agent_review yet, lazily create one."""
    if doc.get("agent_review"):
        return doc["agent_review"]
    unlocked = doc.get("is_paid") or doc.get("manually_unlocked")
    if not unlocked:
        return None
    if doc.get("demo"):
        # demo reports get a default delivered review with a sample message
        review = {
            "status": "delivered",
            "created_at": doc.get("paid_at") or doc.get("created_at") or now_iso(),
            "delivered_at": doc.get("paid_at") or doc.get("created_at") or now_iso(),
            "agent_name": "Elite Scout Team",
            "review_text": (
                "Lukas has a wonderful blend of game intelligence and left-foot quality that's "
                "rare in his age group. I'd recommend pairing his fitness work with regular play "
                "against older boys at training — the gap will close fast. He's the type of "
                "player I'd want a second look at in 3 months. Keep going."
            ),
            "messages": [],
        }
    else:
        review = _default_agent_review(doc.get("paid_at"))
    await db.reports.update_one({"id": doc["id"]}, {"$set": {"agent_review": review}})
    doc["agent_review"] = review
    return review


async def _serialize_report(doc: dict, include_full: bool) -> dict:
    marker_filename = doc.get("marker_filename")
    subject_crop_filename = doc.get("subject_crop_filename")
    out = {
        "id": doc["id"],
        "user_id": doc["user_id"],
        "user_email": doc.get("user_email"),
        "player_details": doc["player_details"],
        "video_url": _resolve_video_url(doc),
        "poster_url": _resolve_poster_url(doc),
        "marker_url": f"/api/uploads/{marker_filename}" if marker_filename else None,
        "subject_crop_url": f"/api/uploads/{subject_crop_filename}" if subject_crop_filename else None,
        "fingerprint": doc.get("fingerprint"),
        "anchors": doc.get("anchors", []),
        "audio_events_preview": doc.get("audio_events_preview", []),
        "audio_events_full": doc.get("audio_events_full", []),
        "preview": doc.get("preview"),
        "content_gate": doc.get("content_gate"),
        "is_paid": doc.get("is_paid", False),
        "manually_unlocked": doc.get("manually_unlocked", False),
        "demo": doc.get("demo", False),
        "created_at": doc.get("created_at"),
        "paid_at": doc.get("paid_at"),
    }
    if include_full:
        out["full_report"] = doc.get("full_report")
        out["agent_review"] = doc.get("agent_review")
        out["trial_readiness"] = compute_trial_readiness(
            doc.get("full_report") or {},
            doc.get("player_details") or {},
        )
        archetype = match_archetype(
            doc.get("full_report") or {},
            doc.get("player_details") or {},
        )
        # ----- Layer 3: attach the Gemini narrative (cached on the doc) -----
        # Narrative cache version bumps invalidate stale narratives when we
        # change the underlying prompt (e.g. v2 added the FIFA k-NN match).
        _NARRATIVE_CACHE_VERSION = 3
        if archetype and not archetype.get("developing") and archetype.get("id"):
            cached = doc.get("archetype_narrative")
            cached_for = doc.get("archetype_narrative_archetype_id")
            cached_bracket = doc.get("archetype_narrative_age_bracket")
            cached_version = doc.get("archetype_narrative_version", 1)
            current_id = archetype.get("id")
            current_bracket = archetype.get("age_bracket_used")
            if (cached and cached_for == current_id and cached_bracket == current_bracket
                    and cached_version == _NARRATIVE_CACHE_VERSION):
                archetype["narrative"] = cached
            else:
                # Generate lazily — never block the response on a hard failure.
                try:
                    narrative = await generate_archetype_narrative(
                        doc.get("player_details") or {},
                        doc.get("full_report") or {},
                        archetype,
                    )
                except Exception as _e:
                    logger.warning(f"narrative generation crashed: {_e}")
                    narrative = None
                if narrative:
                    archetype["narrative"] = narrative
                    # Persist for instant reuse on next fetch
                    await db.reports.update_one(
                        {"id": doc["id"]},
                        {"$set": {
                            "archetype_narrative": narrative,
                            "archetype_narrative_archetype_id": current_id,
                            "archetype_narrative_age_bracket": current_bracket,
                            "archetype_narrative_version": _NARRATIVE_CACHE_VERSION,
                        }},
                    )
        out["archetype"] = archetype
        out["age_profile_reference"] = compute_age_profile_reference(
            doc.get("full_report") or {},
            doc.get("player_details") or {},
        )
        # Step 2: Pro calibration — anchor user scores against StatsBomb Euro 2024 percentiles
        out["statsbomb_calibration"] = compute_statsbomb_calibration(
            doc.get("full_report") or {},
            doc.get("player_details") or {},
        )
        # === Age Intelligence Scoring System ============================
        # Deterministic age-band scoring + stage-gating of senior-pro panels.
        # This MUST run AFTER archetype/statsbomb so apply_stage_gating can
        # strip them out for younger stages (U6-U11).
        age_intel = compute_age_intelligence(
            doc.get("full_report") or {},
            doc.get("player_details") or {},
        )
        if age_intel:
            apply_stage_gating(out, age_intel)
            out["age_intelligence"] = age_intel
        # Extract / placeholder frames for every video_comments timestamp and
        # rewrite the comments list with a `frame_url` per moment.
        enriched_comments = ensure_video_frames(doc)
        if enriched_comments and isinstance(out.get("full_report"), dict):
            out["full_report"] = {**out["full_report"], "video_comments": enriched_comments}
        # Generate share card lazily — use enriched archetype for the card.
        share_doc = {**doc, "archetype": out.get("archetype")}
        out["share_card_url"] = ensure_share_card(share_doc)
    return out


@api_router.get("/reports/{report_id}")
async def get_report(report_id: str, user=Depends(get_current_user)):
    doc = await db.reports.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")
    if doc["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    unlocked = doc.get("is_paid") or doc.get("manually_unlocked") or user["role"] == "admin"
    if unlocked:
        await _ensure_agent_review(doc)
    return await _serialize_report(doc, include_full=bool(unlocked))


@api_router.post("/reports/{report_id}/generate-full")
async def generate_full_report(report_id: str, background: BackgroundTasks, user=Depends(get_current_user)):
    """Kick off the full premium report generation in the background.

    The Gemini full-report call takes 3-5 minutes — way past Cloudflare's 100 s
    edge timeout. To avoid a 524 we return immediately with `{status: "generating"}`
    and the heavy work runs in `generate_full_report_task`. The frontend polls
    `GET /reports/{id}/status` to know when it's done.
    """
    doc = await db.reports.find_one({"id": report_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")
    if doc["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    unlocked = doc.get("is_paid") or doc.get("manually_unlocked") or user["role"] == "admin"
    if not unlocked:
        raise HTTPException(status_code=402, detail="Payment required")

    if doc.get("full_report"):
        return {"status": "exists", "report_id": report_id, "full_report_status": "ready"}

    # Idempotency — if a task is already running for this report, no-op.
    current = doc.get("full_report_status")
    if current == "generating":
        return {"status": "already_generating", "report_id": report_id, "full_report_status": "generating"}

    file_path = UPLOAD_DIR / doc["video_filename"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Video file missing")

    # Mark as queued + clear any previous error and kick off the bg task.
    await db.reports.update_one(
        {"id": report_id},
        {"$set": {"full_report_status": "generating", "full_report_error": None}},
    )
    background.add_task(generate_full_report_task, report_id)
    return {"status": "generating", "report_id": report_id, "full_report_status": "generating"}


async def generate_full_report_task(report_id: str) -> None:
    """Fire-and-forget full report generation (used after Stripe payment OR auto-paid uploads).

    Sets `full_report_status` on the report doc so the frontend can poll
    `/reports/{id}/status` to know when generation is done. Status values:
    `generating` | `ready` | `failed`.
    """
    try:
        doc = await db.reports.find_one({"id": report_id})
        if not doc or doc.get("full_report"):
            # Already done — make sure status reflects that for any concurrent poller.
            if doc and doc.get("full_report") and doc.get("full_report_status") != "ready":
                await db.reports.update_one(
                    {"id": report_id},
                    {"$set": {"full_report_status": "ready"}},
                )
            return
        await db.reports.update_one(
            {"id": report_id},
            {"$set": {"full_report_status": "generating", "full_report_error": None}},
        )
        file_path = await _ensure_report_video_local(report_id)
        if not file_path or not file_path.exists():
            logger.warning(f"generate_full_report_task: video missing for {report_id}")
            await db.reports.update_one(
                {"id": report_id},
                {"$set": {"full_report_status": "failed", "full_report_error": "Source video file missing on server."}},
            )
            return

        marker_path = None
        if doc.get("marker_filename"):
            mp = UPLOAD_DIR / doc["marker_filename"]
            if mp.exists():
                marker_path = str(mp)

        crop_path_str = None
        if doc.get("subject_crop_filename"):
            cp = UPLOAD_DIR / doc["subject_crop_filename"]
            if cp.exists():
                crop_path_str = str(cp)

        anchor_payload_list = doc.get("anchors") or []
        anchor_crops_full: list[str] = []
        for a in anchor_payload_list:
            cf = a.get("crop_filename") if isinstance(a, dict) else None
            if not cf:
                continue
            p = UPLOAD_DIR / cf
            if p.exists():
                anchor_crops_full.append(str(p))

        details_str = json.dumps(doc["player_details"], ensure_ascii=False)
        gate = doc.get("content_gate") or {}

        # ── Precision priors ──
        fp_obj = None
        fp_payload = doc.get("fingerprint")
        if fp_payload:
            try:
                fp_obj = PlayerFingerprint(
                    jersey_hex=fp_payload.get("jersey_hex", "#888888"),
                    jersey_name=fp_payload.get("jersey_name", "unclear"),
                    shorts_hex=fp_payload.get("shorts_hex", "#888888"),
                    shorts_name=fp_payload.get("shorts_name", "unclear"),
                    body_ratio=float(fp_payload.get("body_ratio", 2.0)),
                    crop_path=crop_path_str,
                    box=fp_payload.get("box", {}),
                    confidence="ok",
                )
            except Exception:
                fp_obj = None
        try:
            audio_events_full = extract_audio_events(file_path, top_n=10)
        except Exception:
            audio_events_full = []

        if fp_obj is not None:
            full_prompt = precision_build_full_prompt(
                base_prompt=FULL_REPORT_PROMPT,
                fingerprint=fp_obj,
                audio_events=audio_events_full,
                player_details=doc["player_details"],
                content_type=str(gate.get("content_type", "other")),
                quality=str(gate.get("quality", "good")),
                player_visible=str(gate.get("player_visible", "clear")),
                camera_distance=str(gate.get("camera_distance", "medium")),
                games_detected=int(gate.get("games_detected", 1) or 1),
                anchors=anchor_payload_list,
            )
        else:
            full_prompt = (
                FULL_REPORT_PROMPT
                .replace("{player_details}", details_str)
                .replace("{content_type}", str(gate.get("content_type", "other")))
                .replace("{quality}", str(gate.get("quality", "good")))
                .replace("{player_visible}", str(gate.get("player_visible", "clear")))
                .replace("{camera_distance}", str(gate.get("camera_distance", "medium")))
                .replace("{games_detected}", str(gate.get("games_detected", 1)))
            )
        full = await call_gemini_with_video(
            session_id=f"full-{report_id}",
            prompt=full_prompt,
            video_path=str(file_path),
            marker_path=marker_path,
            crop_path=crop_path_str,
            anchor_crops=anchor_crops_full if anchor_crops_full else None,
        )
        full = scrub_hedging(full)
        await db.reports.update_one(
            {"id": report_id},
            {"$set": {
                "full_report": full,
                "full_generated_at": now_iso(),
                "full_report_status": "ready",
                "full_report_error": None,
                "audio_events_full": [
                    {"t": e.t, "peak_db": e.peak_db, "kind": e.kind} for e in audio_events_full
                ],
            }},
        )
        # Ensure scout review is queued for every paid/unlocked report
        try:
            fresh = await db.reports.find_one({"id": report_id})
            if fresh and not fresh.get("agent_review") and (fresh.get("is_paid") or fresh.get("manually_unlocked")):
                review = _default_agent_review(fresh.get("paid_at"))
                await db.reports.update_one(
                    {"id": report_id},
                    {"$set": {"agent_review": review}},
                )
        except Exception:
            logger.exception(f"Failed to queue agent_review for {report_id}")
    except Exception as e:
        logger.exception(f"generate_full_report_task failed for {report_id}")
        # Persist a friendly failure marker so the frontend can surface "Try again".
        try:
            await db.reports.update_one(
                {"id": report_id},
                {"$set": {
                    "full_report_status": "failed",
                    "full_report_error": str(e)[:240] or "Pro Scout Intelligence couldn't finish this report. Tap Regenerate to retry.",
                }},
            )
        except Exception:
            pass


# ============== AGENT REVIEW (user side) ==============

@api_router.get("/reports/{report_id}/agent-review")
async def get_agent_review(report_id: str, user=Depends(get_current_user)):
    doc = await db.reports.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")
    if doc["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    unlocked = doc.get("is_paid") or doc.get("manually_unlocked") or user["role"] == "admin"
    if not unlocked:
        raise HTTPException(status_code=402, detail="Payment required")
    review = await _ensure_agent_review(doc)
    return review


@api_router.post("/reports/{report_id}/agent-messages")
async def user_send_agent_message(report_id: str, payload: AgentMessageSubmit, user=Depends(get_current_user)):
    doc = await db.reports.find_one({"id": report_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")
    if doc["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    if not (doc.get("is_paid") or doc.get("manually_unlocked")):
        raise HTTPException(status_code=402, detail="Payment required")
    review = doc.get("agent_review") or await _ensure_agent_review(doc)
    if review.get("status") != "delivered":
        raise HTTPException(status_code=400, detail="Your scout has not posted their review yet. Please wait.")
    msg = {"sender": "user", "text": payload.text.strip(), "created_at": now_iso()}
    await db.reports.update_one(
        {"id": report_id},
        {"$push": {"agent_review.messages": msg}, "$set": {"agent_review.last_user_message_at": now_iso()}},
    )
    return {"status": "sent", "message": msg}


# ============== AGENT REVIEW (admin / scout side) ==============

@api_router.get("/admin/agent-queue")
async def admin_agent_queue(_=Depends(get_current_admin_or_scout)):
    """All unlocked reports with their agent review state — oldest pending first."""
    cursor = db.reports.find(
        {"$or": [{"is_paid": True}, {"manually_unlocked": True}]},
        {"_id": 0, "full_report": 0, "preview": 0},
    ).sort("paid_at", 1)
    out = []
    async for d in cursor:
        review = d.get("agent_review")
        if not review:
            review = await _ensure_agent_review(d)
        out.append({
            "report_id": d["id"],
            "user_email": d.get("user_email"),
            "player_name": d.get("player_details", {}).get("player_name"),
            "player_position": d.get("player_details", {}).get("position"),
            "paid_at": d.get("paid_at"),
            "demo": d.get("demo", False),
            "agent_review": review,
            "video_url": _resolve_video_url(d),
            "poster_url": _resolve_poster_url(d),
            "marker_url": f"/api/uploads/{d['marker_filename']}" if d.get("marker_filename") else None,
        })
    # sort pending first, then by oldest
    out.sort(key=lambda x: (x["agent_review"].get("status") != "pending", x.get("paid_at") or ""))
    return out


@api_router.put("/admin/reports/{report_id}/agent-review")
async def admin_deliver_review(report_id: str, payload: AgentReviewSubmit, admin=Depends(get_current_admin_or_scout)):
    doc = await db.reports.find_one({"id": report_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")
    if not (doc.get("is_paid") or doc.get("manually_unlocked")):
        raise HTTPException(status_code=400, detail="Report is not unlocked yet")
    review = doc.get("agent_review") or _default_agent_review(doc.get("paid_at"))
    review["status"] = "delivered"
    review["review_text"] = payload.review_text.strip()
    review["agent_name"] = payload.agent_name or "Elite Scout Team"
    review["delivered_at"] = now_iso()
    review.setdefault("messages", [])
    await db.reports.update_one({"id": report_id}, {"$set": {"agent_review": review}})
    return review


@api_router.post("/admin/reports/{report_id}/agent-messages")
async def admin_send_agent_message(report_id: str, payload: AgentMessageSubmit, admin=Depends(get_current_admin_or_scout)):
    doc = await db.reports.find_one({"id": report_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")
    review = doc.get("agent_review")
    if not review or review.get("status") != "delivered":
        raise HTTPException(status_code=400, detail="Deliver the initial review before sending messages.")
    msg = {"sender": "agent", "text": payload.text.strip(), "created_at": now_iso(), "agent_name": review.get("agent_name") or "Elite Scout Team"}
    await db.reports.update_one(
        {"id": report_id},
        {"$push": {"agent_review.messages": msg}, "$set": {"agent_review.last_agent_message_at": now_iso()}},
    )
    return {"status": "sent", "message": msg}


# ============== PDF GENERATION ==============

"""
============== PREMIUM PDF GENERATOR ==============

Cream paper · forest accents · ink text · Helvetica-Bold for headlines.
Designed to feel like a high-end coaching-academy printed report — not a screenshot.
"""

# Brand palette (mirrors the website tokens)
_PDF_CREAM   = HexColor("#F4EFE6")  # page background
_PDF_CREAM_S = HexColor("#EAE3D2")  # alternating row
_PDF_CARD    = HexColor("#FFFFFF")
_PDF_FOREST  = HexColor("#1F4F2F")
_PDF_FOREST_POP = HexColor("#2D6B3D")
_PDF_INK     = HexColor("#0A0F0D")
_PDF_MUTED   = HexColor("#4B5563")
_PDF_BORDER  = HexColor("#E5E7EB")


def _pdf_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="Eyebrow", fontName="Helvetica-Bold", fontSize=8, leading=11,
        textColor=_PDF_FOREST, letterSpacing=2, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="HeroTitle", fontName="Helvetica-Bold", fontSize=40, leading=42,
        textColor=_PDF_INK, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="HeroSub", fontName="Helvetica", fontSize=10.5, leading=14,
        textColor=_PDF_MUTED, spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="SectionTitle", fontName="Helvetica-Bold", fontSize=18, leading=22,
        textColor=_PDF_INK, spaceBefore=18, spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name="SectionEyebrow", fontName="Helvetica-Bold", fontSize=8, leading=10,
        textColor=_PDF_FOREST, letterSpacing=2.4, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="SubTitle", fontName="Helvetica-Bold", fontSize=11.5, leading=15,
        textColor=_PDF_INK, spaceBefore=10, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="BodyW", fontName="Helvetica", fontSize=10, leading=14.5,
        textColor=_PDF_INK, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="BodyMuted", fontName="Helvetica", fontSize=9.5, leading=14,
        textColor=_PDF_MUTED, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="MutedW", fontName="Helvetica-Oblique", fontSize=8.5, leading=11.5,
        textColor=_PDF_MUTED, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="Label", fontName="Helvetica-Bold", fontSize=8, leading=10,
        textColor=_PDF_FOREST, spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="QuoteLead", fontName="Helvetica-Bold", fontSize=14, leading=20,
        textColor=_PDF_INK, spaceBefore=10, spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="CoverFootnote", fontName="Helvetica", fontSize=8, leading=11,
        textColor=_PDF_MUTED, alignment=TA_LEFT, spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="ForestBullet", fontName="Helvetica", fontSize=10, leading=14.5,
        textColor=_PDF_INK, leftIndent=16, bulletIndent=2, spaceAfter=4,
        bulletFontName="Helvetica-Bold", bulletColor=_PDF_FOREST, bulletFontSize=9,
    ))
    # NEW — clean styles used by the redesigned components below
    styles.add(ParagraphStyle(
        name="Caption", fontName="Helvetica-Bold", fontSize=7, leading=9,
        textColor=_PDF_MUTED, letterSpacing=1.8, spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="CaptionForest", fontName="Helvetica-Bold", fontSize=7, leading=9,
        textColor=_PDF_FOREST, letterSpacing=1.8, spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="Body", fontName="Helvetica", fontSize=10, leading=14.5,
        textColor=_PDF_INK, spaceAfter=4,
    ))
    return styles


def _big_score(value, big_size=40, unit_size=12, big_color="#1F4F2F", unit_color="#9CA3AF", unit="/ 10", align="LEFT"):
    """Returns a Table flowable with a perfectly baseline-aligned big number + small unit suffix.

    Solves the "5 /10" overlap/floating problem by putting each part in its own cell with VALIGN=BOTTOM."""
    val_str = "—" if value is None or value == "" else str(value)
    big_para = Paragraph(
        f'<font color="{big_color}" size="{big_size}"><b>{val_str}</b></font>',
        ParagraphStyle(
            "_bs", fontName="Helvetica-Bold", fontSize=big_size,
            leading=big_size * 1.0, textColor=HexColor(big_color),
            spaceAfter=0, spaceBefore=0,
        ),
    )
    unit_para = Paragraph(
        f'<font color="{unit_color}" size="{unit_size}"><b>{unit}</b></font>',
        ParagraphStyle(
            "_us", fontName="Helvetica-Bold", fontSize=unit_size,
            leading=unit_size * 1.1, textColor=HexColor(unit_color),
            spaceAfter=0, spaceBefore=0,
        ),
    )
    # Approximate width for the big number cell (Helvetica-Bold avg char width ~ 0.58 * size)
    big_w = max(0.7, len(val_str) * big_size * 0.62 / 28.35)  # cm
    t = Table(
        [[big_para, unit_para]],
        colWidths=[big_w * cm, 2.0 * cm],
        hAlign=align,
    )
    t.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (0, 0),    0),
        # Nudge the unit up so its baseline sits roughly on the big number's baseline
        ("BOTTOMPADDING", (1, 0), (1, 0),    max(2, big_size * 0.12)),
        ("LEFTPADDING",   (1, 0), (1, 0),    4),
    ]))
    return t


def _callout(text: str, color="#B45309", bg="#FEF3C7", icon="●"):
    """Premium inline callout pill — used for 'NEED MORE FOOTAGE' and similar status flags.
    Designed with: thick left accent rail, amber-cream gradient feel, generous padding,
    uppercase tracked text to read as a deliberate design element rather than a placeholder."""
    para = Paragraph(
        f'<font color="{color}" size="8"><b>{icon}&nbsp;&nbsp;{text}</b></font>',
        ParagraphStyle(
            "_cl", fontName="Helvetica-Bold", fontSize=8, leading=11,
            textColor=HexColor(color), spaceAfter=0, spaceBefore=0,
            letterSpacing=1.4, alignment=TA_LEFT,
        ),
    )
    t = Table([[para]], colWidths=[4.6 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), HexColor(bg)),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBEFORE",    (0, 0), (0, -1), 3.0, HexColor(color)),
        ("BOX",           (0, 0), (-1, -1), 0.5, HexColor("#FDE68A")),
    ]))
    return t


def _draw_background(canv, doc):
    """Cream page + forest accent rail on the left + page numbers + brand footer."""
    canv.saveState()
    w, h = doc.pagesize

    # Cream page background
    canv.setFillColor(_PDF_CREAM)
    canv.rect(0, 0, w, h, fill=1, stroke=0)

    # Subtle forest vertical rail on the left (the "spine")
    canv.setFillColor(_PDF_FOREST)
    canv.rect(0, 0, 0.18 * cm, h, fill=1, stroke=0)

    # Top-right brand mark
    canv.setFillColor(_PDF_INK)
    canv.setFont("Helvetica-Bold", 8)
    canv.drawRightString(w - 1.6 * cm, h - 1.0 * cm, "SCOUTMEPLAY")
    canv.setFillColor(_PDF_FOREST)
    canv.drawRightString(w - 0.65 * cm, h - 1.0 * cm, "·")

    # Footer line + brand + page number — improved contrast
    canv.setStrokeColor(_PDF_BORDER)
    canv.setLineWidth(0.4)
    canv.line(1.6 * cm, 1.55 * cm, w - 1.6 * cm, 1.55 * cm)

    canv.setFillColor(_PDF_FOREST)
    canv.setFont("Helvetica-Bold", 7.5)
    canv.drawString(1.6 * cm, 1.05 * cm, "SCOUTMEPLAY · MENTALKIDS")
    canv.setFillColor(HexColor("#374151"))  # darker than _PDF_MUTED for legibility
    canv.setFont("Helvetica", 7.5)
    canv.drawString(5.4 * cm, 1.05 * cm, "Professional player development report")
    canv.setFillColor(_PDF_INK)
    canv.setFont("Helvetica-Bold", 7.5)
    canv.drawRightString(w - 1.6 * cm, 1.05 * cm, f"Page {doc.page}")

    canv.restoreState()


_NANO_BANANA_DIR = Path(__file__).resolve().parent / "static" / "landing"


def _draw_cover_background(canv, doc):
    """Cover page background: cream + Nano Banana stadium-tunnel photo behind
    a heavy forest tint on the LEFT PANEL, big ScoutMePlay wordmark rotated
    vertically. Mirrors the cinematic feel of the web report's OverallBenchmarkBanner.
    """
    canv.saveState()
    w, h = doc.pagesize

    # Cream base
    canv.setFillColor(_PDF_CREAM)
    canv.rect(0, 0, w, h, fill=1, stroke=0)

    # Forest left panel (1/3 width)
    panel_w = w * 0.34

    # Nano Banana stadium tunnel photo — covers the left panel behind the forest tint
    tunnel_bg = _NANO_BANANA_DIR / "bg-benchmark-tunnel.png"
    if tunnel_bg.exists():
        try:
            # Crop-to-fit: draw slightly wider than the panel and let the panel clip
            canv.drawImage(
                str(tunnel_bg),
                x=0,
                y=0,
                width=panel_w,
                height=h,
                preserveAspectRatio=False,  # fill the entire panel
                anchor="c",
                mask="auto",
            )
        except Exception:
            # If the image is unreadable for any reason, fall back to solid forest
            canv.setFillColor(_PDF_FOREST)
            canv.rect(0, 0, panel_w, h, fill=1, stroke=0)
    else:
        canv.setFillColor(_PDF_FOREST)
        canv.rect(0, 0, panel_w, h, fill=1, stroke=0)

    # Heavy forest tint on top — keeps brand identity while letting the photo add depth
    canv.setFillColor(_PDF_FOREST)
    canv.setFillAlpha(0.72)
    canv.rect(0, 0, panel_w, h, fill=1, stroke=0)
    canv.setFillAlpha(1.0)

    # Subtle diagonal accent stripe on the forest panel
    canv.setFillColor(_PDF_FOREST_POP)
    canv.rect(panel_w - 0.45 * cm, 0, 0.45 * cm, h, fill=1, stroke=0)

    # Top-of-page brand wordmark on the forest panel (rotated 90deg, runs vertically)
    canv.setFillColor(HexColor("#FFFFFF"))
    canv.setFont("Helvetica-Bold", 11)
    canv.saveState()
    canv.translate(1.6 * cm, h - 2.2 * cm)
    canv.rotate(-90)
    canv.drawString(0, 0, "SCOUTMEPLAY")
    canv.restoreState()
    # tagline beneath wordmark (also rotated)
    canv.setFillColor(HexColor("#FFFFFFAA"))
    canv.setFont("Helvetica", 7)
    canv.saveState()
    canv.translate(2.3 * cm, h - 2.2 * cm)
    canv.rotate(-90)
    canv.drawString(0, 0, "PROFESSIONAL · INDEPENDENT · EVIDENCE-BASED")
    canv.restoreState()

    # Bottom-left footer on the green panel — increased contrast
    canv.setFillColor(HexColor("#FFFFFFCC"))
    canv.setFont("Helvetica", 7.5)
    canv.drawString(1.6 * cm, 1.0 * cm, "MENTALKIDS / Denmark")
    canv.setFillColor(HexColor("#FFFFFF"))
    canv.setFont("Helvetica-Bold", 7.5)
    canv.drawString(1.6 * cm, 0.55 * cm, "SCOUTMEPLAY.COM")

    canv.restoreState()


# ---- Reusable visual primitives ----

# Nano Banana background images shared with the web report. Each key maps to a
# concrete PNG under /app/backend/static/landing/ — same asset the web report uses.
_NANO_BG = {
    "technical": _NANO_BANANA_DIR / "bg-radar-tactics.png",      # chalk tactics board
    "tactical":  _NANO_BANANA_DIR / "bg-archetype-aerial.png",   # aerial pitch layout
    "physical":  _NANO_BANANA_DIR / "bg-standout-boots.png",     # boots on grass
    "mentality": _NANO_BANANA_DIR / "bg-standout-net.png",       # goal net close-up
    "scout":     _NANO_BANANA_DIR / "bg-scout-hero.png",         # chalk touchline
    "tunnel":    _NANO_BANANA_DIR / "bg-benchmark-tunnel.png",   # stadium tunnel
}


class _NanoHeroBand(Flowable):
    """A photo-band section header — Nano Banana image + heavy forest tint +
    white section title + volt eyebrow. Mirrors the cinematic hero-band feel
    of the web report's chapter openers so the printed PDF and the on-screen
    report share the same premium visual language.

    Fixed-height (2.6 cm) full-width strip. Draws its own background image,
    so callers just insert it into the story like any other flowable.
    """

    def __init__(self, image_path: Path, section_num: str, title: str, subtitle: str = "",
                 width: float = None, height: float = 2.6 * cm):
        Flowable.__init__(self)
        self.image_path = image_path
        self.section_num = (section_num or "").upper()
        self.title = (title or "").upper()
        self.subtitle = subtitle or ""
        self._w = width or (A4[0] - 3.2 * cm)  # matches the inner_frame width
        self._h = height

    def wrap(self, availWidth, availHeight):  # noqa: N802 (ReportLab API)
        return (self._w, self._h)

    def draw(self):
        c = self.canv
        w, h = self._w, self._h

        # 1) Background image, cropped to fit the strip
        try:
            if self.image_path and Path(self.image_path).exists():
                c.drawImage(
                    str(self.image_path), 0, 0, width=w, height=h,
                    preserveAspectRatio=False, anchor="c", mask="auto",
                )
            else:
                c.setFillColor(_PDF_FOREST)
                c.rect(0, 0, w, h, fill=1, stroke=0)
        except Exception:
            c.setFillColor(_PDF_FOREST)
            c.rect(0, 0, w, h, fill=1, stroke=0)

        # 2) Heavy forest tint — keeps the brand identity, lets photo add depth
        c.setFillColor(_PDF_FOREST)
        c.setFillAlpha(0.80)
        c.rect(0, 0, w, h, fill=1, stroke=0)
        c.setFillAlpha(1.0)

        # 3) Volt accent stripe on the left edge (matches the web hero divider)
        c.setFillColor(HexColor("#CCFF00"))
        c.rect(0, 0, 0.14 * cm, h, fill=1, stroke=0)

        # 4) Text — volt eyebrow + big white section title + optional subtitle
        c.setFillColor(HexColor("#CCFF00"))
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(0.65 * cm, h - 0.75 * cm, self.section_num)

        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 17)
        c.drawString(0.65 * cm, h - 1.55 * cm, self.title)

        if self.subtitle:
            c.setFillColor(HexColor("#FFFFFFCC"))
            c.setFont("Helvetica", 8.5)
            c.drawString(0.65 * cm, h - 2.15 * cm, self.subtitle)


def _nano_hero(section_num: str, title: str, subtitle: str, pillar_key: str) -> list:
    """Convenience factory — returns a `_NanoHeroBand` for a pillar section,
    plus the spacer that lets the score table below breathe."""
    band = _NanoHeroBand(
        image_path=_NANO_BG.get(pillar_key),
        section_num=section_num,
        title=title,
        subtitle=subtitle,
    )
    return [band, Spacer(1, 0.6 * cm)]


def _section_header(title: str, styles, idx: int = None):
    """Forest eyebrow + big ink title + thicker forest underline.
    Returned as a Table so the underline visually 'hangs' under the title."""
    eyebrow_text = f"SECTION {idx:02d}" if idx else "ANALYSIS"
    eyebrow = Paragraph(eyebrow_text, styles["SectionEyebrow"])
    head = Paragraph(title, styles["SectionTitle"])

    # Underline accent — wider + thicker for stronger hierarchy
    line = Table([[""]], colWidths=[3.2 * cm], rowHeights=[0.12 * cm])
    line.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _PDF_FOREST),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [eyebrow, head, line, Spacer(1, 0.45 * cm)]


def _score_pill(score) -> str:
    """Inline score formatting for table cells — clean, consistent baseline."""
    try:
        s = float(score)
        # Use single-size paragraph: bold forest number, lighter gray suffix at same size
        return f"<font color='#1F4F2F'><b>{s:g}</b></font><font color='#9CA3AF'>&nbsp;/&nbsp;10</font>"
    except Exception:
        return "<font color='#9CA3AF'>—</font>"


def _score_table(rows, styles):
    """Premium attribute table with alternating cream rows + forest accents.

    Uses generous padding and a wider SCORE column so numbers never crowd the NOTES text."""
    data = [["ATTRIBUTE", "SCORE", "NOTES"]]
    for label, score, notes in rows:
        data.append([
            Paragraph(f"<b>{label}</b>", styles["BodyW"]),
            Paragraph(_score_pill(score), styles["BodyW"]),
            Paragraph(notes or "—", styles["BodyMuted"]),
        ])
    # Wider SCORE column + slightly narrower NOTES so values get breathing room
    t = Table(data, colWidths=[4.4 * cm, 3.2 * cm, 8.4 * cm], repeatRows=1)
    style = [
        # Header row — forest band
        ("BACKGROUND",    (0, 0), (-1, 0), _PDF_FOREST),
        ("TEXTCOLOR",     (0, 0), (-1, 0), HexColor("#FFFFFF")),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 8),
        ("ALIGN",         (0, 0), (-1, 0), "LEFT"),
        ("ALIGN",         (1, 0), (1, 0),  "CENTER"),
        ("LEFTPADDING",   (0, 0), (-1, 0), 12),
        ("RIGHTPADDING",  (0, 0), (-1, 0), 12),
        ("TOPPADDING",    (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 9),
        # Body
        ("VALIGN",        (0, 1), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 1), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 1), (-1, -1), 12),
        ("TOPPADDING",    (0, 1), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 10),
        # subtle dividers
        ("LINEBELOW",     (0, 1), (-1, -1), 0.25, _PDF_BORDER),
        # Score column always centered
        ("ALIGN",         (1, 1), (1, -1),  "CENTER"),
    ]
    # Alternate row backgrounds
    for i in range(1, len(data)):
        bg = _PDF_CARD if i % 2 == 1 else _PDF_CREAM_S
        style.append(("BACKGROUND", (0, i), (-1, i), bg))
    t.setStyle(TableStyle(style))
    return t


def _list_bullets(items, styles):
    """Forest-bulleted list with proper baseline alignment."""
    flow = []
    for s in items or []:
        flow.append(Paragraph(s, styles["ForestBullet"], bulletText="▸"))
    if not flow:
        flow.append(Paragraph("<font color='#9CA3AF'>No items recorded.</font>", styles["BodyMuted"]))
    return flow


def _kv_card(items, styles):
    """A 'card' table with bold label + body paragraph rows.
    `items` is list of (label, value) tuples."""
    data = []
    for label, value in items:
        data.append([
            Paragraph(f"<b>{label}</b>", styles["Label"]),
            Paragraph(value or "—", styles["BodyW"]),
        ])
    if not data:
        return Spacer(1, 0)
    t = Table(data, colWidths=[4.2 * cm, 11.3 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _PDF_CARD),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.4, _PDF_BORDER),
        ("LINEBEFORE",    (0, 0), (0, -1),  2.0, _PDF_FOREST),
    ]))
    return t


def _cover_summary_box(overall: str, player_type: str, body: str, styles):
    """Big quoted highlight on the cover page — uses _big_score for proper baseline alignment."""
    rows = [
        [Paragraph("OVERALL DEVELOPMENT", styles["Label"]),
         Paragraph("PLAYER TYPE", styles["Label"])],
        [_big_score(overall, big_size=32, unit_size=12, unit="/ 10"),
         Paragraph(f'<font size="13" color="#0A0F0D"><b>{player_type or "Independent"}</b></font>', styles["BodyW"])],
    ]
    t = Table(rows, colWidths=[5.6 * cm, 5.6 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _PDF_CARD),
        ("LEFTPADDING",   (0, 0), (-1, -1), 16),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 16),
        ("TOPPADDING",    (0, 0), (-1, 0),   14),
        ("BOTTOMPADDING", (0, 0), (-1, 0),   4),
        ("TOPPADDING",    (0, 1), (-1, 1),   2),
        ("BOTTOMPADDING", (0, 1), (-1, 1),   16),
        ("VALIGN",        (0, 0), (-1, -1), "BOTTOM"),
        ("VALIGN",        (1, 1), (1, 1),   "BOTTOM"),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.4, _PDF_BORDER),
        ("LINEBEFORE",    (0, 0), (0, -1),  2.2, _PDF_FOREST),
    ]))
    return t


def _section_rows(section: dict) -> list:
    rows = []
    for key, value in section.items():
        if isinstance(value, dict):
            label = key.replace("_", " ").title()
            score = value.get("score", "-")
            notes = value.get("notes", "")
            rows.append((label, score, notes))
    return rows


# ---- Benchmark / tier visualisation primitives ----

_TIER_ORDER = ["standard_club", "strong_club", "pro_academy", "elite_academy"]
_TIER_LABEL = {
    "standard_club": "Standard Club",
    "strong_club":   "Strong Club",
    "pro_academy":   "Pro Academy",
    "elite_academy": "Elite Academy",
}
_TIER_DOT = {
    "standard_club": HexColor("#78716C"),  # stone
    "strong_club":   HexColor("#D97706"),  # amber
    "pro_academy":   _PDF_FOREST_POP,
    "elite_academy": HexColor("#10B981"),  # emerald
}


def _tier_chip(tier_key: str, styles) -> str:
    """Inline HTML <font> tag fragment for a tier label, coloured by tier."""
    label = _TIER_LABEL.get(tier_key, "—")
    col = _TIER_DOT.get(tier_key, _PDF_MUTED).hexval()[2:]  # strip 0x
    return f"<font color='#{col}'><b>{label.upper()}</b></font>"


def _benchmark_strip(tier_key: str, benchmarks: dict, styles):
    """Premium 4-column 'tier ladder' showing where the player sits.
    Returns a small Table flowable."""
    if not benchmarks or not isinstance(benchmarks, dict):
        return None
    cells = []
    for k in _TIER_ORDER:
        active = (k == tier_key)
        label = _TIER_LABEL.get(k, "—")
        rng = benchmarks.get(k) or "—"
        col_hex = "#" + _TIER_DOT.get(k, _PDF_MUTED).hexval()[2:]
        # Active cell: forest border + filled cream; inactive: muted
        if active:
            inner = (
                f"<font color='{col_hex}' size='6.5'><b>{label.upper()}</b></font><br/>"
                f"<font color='#0A0F0D' size='10'><b>{rng}</b></font><br/>"
                f"<font color='#1F4F2F' size='6.5'><b>YOU ARE HERE</b></font>"
            )
        else:
            inner = (
                f"<font color='#9CA3AF' size='6.5'><b>{label.upper()}</b></font><br/>"
                f"<font color='#6B7280' size='9'>{rng}</font>"
            )
        cells.append(Paragraph(inner, styles["BodyW"]))
    t = Table([cells], colWidths=[3.7 * cm] * 4)
    style = [
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND",    (0, 0), (-1, -1), _PDF_CARD),
        ("BOX",           (0, 0), (-1, -1), 0.4, _PDF_BORDER),
    ]
    # Highlight active cell with forest left border + cream background
    for i, k in enumerate(_TIER_ORDER):
        if k == tier_key:
            style.append(("BACKGROUND", (i, 0), (i, 0), _PDF_CREAM_S))
            style.append(("LINEBEFORE", (i, 0), (i, 0), 2.5, _PDF_FOREST))
    t.setStyle(TableStyle(style))
    return t


def _skill_card(key: str, value: dict, styles):
    """Premium card for ONE scored sub-skill — exact parity with the web report.

    Shows:
      - Skill name + score + tier (top row)
      - Notes
      - Why this score (forest eyebrow + body)
      - Benchmark strip (4-tier ladder, player's tier highlighted)
      - Verdict (italic forest-accent line)

    Returns a single Table flowable (one card)."""
    label = key.replace("_", " ").title()
    cannot_eval = bool(value.get("cannot_evaluate"))
    score = value.get("score")
    notes = value.get("notes", "")
    tier = value.get("tier_for_age")
    why = value.get("why_this_score")
    benchmarks = value.get("benchmarks")
    verdict = value.get("verdict")

    # ----- Top row: name + score pill + tier chip -----
    if cannot_eval:
        score_para = _callout("NEED MORE FOOTAGE", color="#B45309", bg="#FEF3C7", icon="▲")
    else:
        score_para = _big_score(score, big_size=22, unit_size=9, unit="/ 10", align="RIGHT")
    tier_html = f"<br/>{_tier_chip(tier, styles)}" if tier and not cannot_eval else ""
    name_para = Paragraph(
        f"<font color='#0A0F0D' size='13'><b>{label}</b></font>{tier_html}",
        styles["BodyW"],
    )

    inner_rows = [[name_para, score_para]]
    # Notes
    notes_text = value.get("evaluable_reason") if cannot_eval else notes
    if notes_text:
        inner_rows.append([Paragraph(notes_text, styles["BodyW"]), ""])

    # Why this score
    if why and not cannot_eval:
        inner_rows.append([
            Paragraph(
                f"<font color='#1F4F2F' size='7.5'><b>WHY THIS SCORE</b></font><br/>"
                f"<font color='#0A0F0D' size='9.5'>{why}</font>",
                styles["BodyW"],
            ),
            ""
        ])

    # Benchmark strip
    strip = _benchmark_strip(tier, benchmarks, styles) if benchmarks and tier and not cannot_eval else None
    if strip is not None:
        inner_rows.append([strip, ""])

    # Verdict
    if verdict and not cannot_eval:
        inner_rows.append([
            Paragraph(
                f"<font color='#1F4F2F' size='9'><b>›</b></font>&nbsp;&nbsp;"
                f"<i><font color='#4B5563' size='9'>{verdict}</font></i>",
                styles["BodyW"],
            ),
            ""
        ])

    card = Table(inner_rows, colWidths=[12.5 * cm, 3.0 * cm])
    # Each row spans full width except the first one (name + score split)
    span_style = []
    for i in range(1, len(inner_rows)):
        span_style.append(("SPAN", (0, i), (1, i)))

    card.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _PDF_CARD),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN",        (0, 0), (0, 0),   "MIDDLE"),
        ("VALIGN",        (1, 0), (1, 0),   "MIDDLE"),
        ("ALIGN",         (1, 0), (1, 0),   "RIGHT"),
        ("LINEBEFORE",    (0, 0), (0, -1),  2.0, _PDF_FOREST),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.4, _PDF_BORDER),
        *span_style,
    ]))
    return card


def _skill_section_block(section: dict, styles):
    """Returns a list of Flowables: one premium card per sub-skill in the section."""
    if not isinstance(section, dict):
        return []
    flow = []
    for key, value in section.items():
        if not isinstance(value, dict):
            continue
        flow.append(_skill_card(key, value, styles))
        flow.append(Spacer(1, 0.18 * cm))
    return flow


def _scout_summary_page(report_doc: dict, styles):
    """The signature '60-Second Scout Summary' page — placed right after the cover
    so a busy academy scout can absorb the report in 60 seconds.

    Distils: name + age + position, big score, archetype 1-liner, top strengths,
    top development priorities, and a 'If you only read one page' anchor.
    """
    full = report_doc.get("full_report") or {}
    details = report_doc.get("player_details") or {}
    sc = full.get("scores") or {}
    sv = full.get("scout_view") or {}
    archetype = full.get("archetype") or {}

    player_name = details.get("player_name") or "Player"
    age = details.get("age") or "—"
    position = details.get("position") or "Player"
    overall = sc.get("overall_development")
    overall_str = f"{overall:.1f}" if isinstance(overall, (int, float)) else (str(overall) if overall else "—")

    arch_name = (archetype.get("name") or archetype.get("anchor_name") or "").strip()
    arch_summary = (archetype.get("summary") or archetype.get("brief") or "").strip()
    arch_oneliner = arch_name or arch_summary

    strengths = (sv.get("key_strengths") or [])[:3]
    priorities = (sv.get("development_priorities") or [])[:2]

    flow = []

    # Eyebrow + title
    flow.append(Paragraph("60-Second Scout Summary", styles["Eyebrow"]))
    flow.append(Paragraph(player_name, styles["HeroTitle"]))
    flow.append(Paragraph(
        f"<font color='#1F4F2F'><b>{position}</b></font>  &middot;  Age {age}",
        styles["BodyMuted"],
    ))
    flow.append(Spacer(1, 0.5 * cm))

    # Score + Archetype card (2 cols) — score uses baseline-aligned _big_score helper
    score_inner = Table(
        [
            [Paragraph('<font color="#1F4F2F" size="8"><b>SCOUT SCORE</b></font>',
                       ParagraphStyle("_ss_l", fontName="Helvetica-Bold", fontSize=8, leading=11,
                                      textColor=_PDF_FOREST, spaceAfter=4, letterSpacing=1.2))],
            [_big_score(overall_str, big_size=36, unit_size=13,
                        big_color="#0A0F0D", unit_color="#9CA3AF", unit="/ 10", align="LEFT")],
        ],
        colWidths=[4.5 * cm],
    )
    score_inner.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    score_block = score_inner
    if arch_oneliner:
        arch_block = Paragraph(
            f"<font color='#1F4F2F' size='8'><b>ARCHETYPE MATCH</b></font><br/>"
            f"<font color='#0A0F0D' size='14'><b>{arch_name or 'Archetype'}</b></font><br/>"
            f"<font color='#374151' size='9'>{arch_summary or '&nbsp;'}</font>",
            styles["BodyW"],
        )
    else:
        arch_block = Paragraph(
            "<font color='#374151' size='9'><i>Archetype matching pending — see full report.</i></font>",
            styles["BodyW"],
        )

    summary_card = Table(
        [[score_block, arch_block]],
        colWidths=[5.0 * cm, 10.0 * cm],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (0, 0), HexColor("#F4EFE6")),
            ("BACKGROUND", (1, 0), (1, 0), HexColor("#FBFAF6")),
            ("BOX", (0, 0), (-1, -1), 0.6, _PDF_BORDER),
            ("LINEBEFORE", (1, 0), (1, 0), 0.6, _PDF_BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 16),
            ("RIGHTPADDING", (0, 0), (-1, -1), 16),
            ("TOPPADDING", (0, 0), (-1, -1), 16),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
        ]),
    )
    flow.append(summary_card)
    flow.append(Spacer(1, 0.7 * cm))

    # Strengths + Priorities side-by-side
    def _bullets_html(items, fg):
        if not items:
            return "<font color='#9CA3AF' size='9'><i>None recorded.</i></font>"
        return "".join(
            f"<font color='{fg}' size='9'><b>&#9670;</b></font> "
            f"<font color='#0A0F0D' size='9.5'>{str(it).strip()}</font><br/><br/>"
            for it in items
        )

    str_block = Paragraph(
        "<font color='#1F4F2F' size='8'><b>TOP STRENGTHS</b></font><br/><br/>" + _bullets_html(strengths, "#1F4F2F"),
        styles["BodyW"],
    )
    pri_block = Paragraph(
        "<font color='#7C2D12' size='8'><b>DEVELOPMENT PRIORITIES</b></font><br/><br/>" + _bullets_html(priorities, "#7C2D12"),
        styles["BodyW"],
    )
    sw_table = Table(
        [[str_block, pri_block]],
        colWidths=[7.5 * cm, 7.5 * cm],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (0, 0), HexColor("#F4EFE6")),
            ("BACKGROUND", (1, 0), (1, 0), HexColor("#FBFAF6")),
            ("BOX", (0, 0), (-1, -1), 0.6, _PDF_BORDER),
            ("LINEBEFORE", (1, 0), (1, 0), 0.6, _PDF_BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ]),
    )
    flow.append(sw_table)
    flow.append(Spacer(1, 0.9 * cm))

    # Closing anchor line
    flow.append(Paragraph(
        "<font color='#1F4F2F' size='9'><b>IF YOU ONLY READ ONE PAGE — THIS IS IT.</b></font><br/>"
        "<font color='#374151' size='8.5'><i>Continue for the full technical / tactical / physical / mental breakdown, "
        "video-time evidence, age-bracketed pro comparisons and personalised training plan.</i></font>",
        styles["BodyW"],
    ))

    return flow


def _overall_benchmark_page(ob: dict, overall_score, styles):
    """The signature 'How you compare' page — forest hero panel + tier landscape."""
    if not isinstance(ob, dict) or not ob.get("tier"):
        return []

    flow = []
    tier_key = ob.get("tier")
    tier_label = ob.get("tier_label") or _TIER_LABEL.get(tier_key, "—")
    pct = ob.get("percentile") or ""
    nxt = ob.get("realistic_next_step") or ""
    sep = ob.get("what_separates_from_next_tier") or ""
    bracket = (ob.get("age_bracket_used") or "").replace("_", " ")

    # Hero card: dark forest panel with the big score + tier
    # Use a 3-row vertical Table inside the left cell so eyebrow / big score / tier label
    # sit cleanly stacked with proper baselines — instead of one Paragraph that mixes sizes.
    big_score_table = _big_score(
        overall_score, big_size=44, unit_size=14,
        big_color="#FFFFFF", unit_color="#FFFFFF99", unit="/ 10", align="LEFT",
    )
    left_rows = [
        [Paragraph('<font color="#FFFFFF" size="7.5"><b>HOW YOU COMPARE</b></font>',
                   ParagraphStyle("_hyc", fontName="Helvetica-Bold", fontSize=7.5, leading=10,
                                  textColor=HexColor("#FFFFFF"), spaceAfter=2))],
        [big_score_table],
        [Paragraph(f'<font color="#FFFFFF" size="10"><b>{tier_label.upper()}</b></font>',
                   ParagraphStyle("_tl", fontName="Helvetica-Bold", fontSize=10, leading=13,
                                  textColor=HexColor("#FFFFFF"), spaceBefore=6, spaceAfter=0))],
    ]
    if bracket:
        left_rows.append([
            Paragraph(f'<font color="#FFFFFF80" size="7"><b>CALIBRATED FOR {bracket.upper()}</b></font>',
                      ParagraphStyle("_cb", fontName="Helvetica-Bold", fontSize=7, leading=9,
                                     textColor=HexColor("#FFFFFF80"), spaceBefore=3, spaceAfter=0))
        ])
    hero_left = Table(left_rows, colWidths=[5.0 * cm])
    hero_left.setStyle(TableStyle([
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))

    # Right side — stacked label/value pairs, each one in its own Paragraph (single font size each)
    right_rows = []
    if pct:
        right_rows.append([Paragraph(f'<font color="#FFFFFF" size="11">{pct}</font>',
                                     ParagraphStyle("_pct", fontName="Helvetica", fontSize=11, leading=15,
                                                    textColor=HexColor("#FFFFFF"), spaceAfter=8))])
    if nxt:
        right_rows.append([Paragraph('<font color="#FFFFFF99" size="7"><b>REALISTIC NEXT STEP</b></font>',
                                     ParagraphStyle("_rns_l", fontName="Helvetica-Bold", fontSize=7, leading=9,
                                                    textColor=HexColor("#FFFFFF99"), spaceAfter=2))])
        right_rows.append([Paragraph(f'<font color="#FFFFFF" size="9.5">{nxt}</font>',
                                     ParagraphStyle("_rns_v", fontName="Helvetica", fontSize=9.5, leading=13,
                                                    textColor=HexColor("#FFFFFF"), spaceAfter=8))])
    if sep:
        right_rows.append([Paragraph('<font color="#FFFFFF99" size="7"><b>TO REACH THE NEXT TIER</b></font>',
                                     ParagraphStyle("_sep_l", fontName="Helvetica-Bold", fontSize=7, leading=9,
                                                    textColor=HexColor("#FFFFFF99"), spaceAfter=2))])
        right_rows.append([Paragraph(f'<font color="#FFFFFF" size="9.5">{sep}</font>',
                                     ParagraphStyle("_sep_v", fontName="Helvetica", fontSize=9.5, leading=13,
                                                    textColor=HexColor("#FFFFFF"), spaceAfter=0))])
    if not right_rows:
        right_rows = [[Paragraph('<font color="#FFFFFF80" size="9">—</font>', styles["BodyW"])]]
    hero_right = Table(right_rows, colWidths=[9.5 * cm])
    hero_right.setStyle(TableStyle([
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))

    hero = Table([[hero_left, hero_right]], colWidths=[5.4 * cm, 10.1 * cm])
    hero.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _PDF_FOREST),
        ("LEFTPADDING",   (0, 0), (-1, -1), 18),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 18),
        ("TOPPADDING",    (0, 0), (-1, -1), 20),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 20),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LINEAFTER",     (0, 0), (0, 0),   0.4, HexColor("#FFFFFF22")),
    ]))
    flow.append(hero)
    flow.append(Spacer(1, 0.5 * cm))

    # Tier landscape (4 cells)
    cells = []
    for k in _TIER_ORDER:
        active = (k == tier_key)
        col_hex = "#" + _TIER_DOT.get(k, _PDF_MUTED).hexval()[2:]
        lbl = _TIER_LABEL.get(k, "—")
        if active:
            inner = (
                f"<font color='{col_hex}' size='7'><b>{lbl.upper()}</b></font><br/>"
                f"<font color='#1F4F2F' size='8'><b>← YOU ARE HERE</b></font>"
            )
        else:
            inner = f"<font color='#9CA3AF' size='7'><b>{lbl.upper()}</b></font>"
        cells.append(Paragraph(inner, styles["BodyW"]))
    landscape = Table([cells], colWidths=[3.7 * cm] * 4)
    landscape_style = [
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("BACKGROUND",    (0, 0), (-1, -1), _PDF_CARD),
        ("BOX",           (0, 0), (-1, -1), 0.4, _PDF_BORDER),
        ("LINEAFTER",     (0, 0), (-2, 0),  0.4, _PDF_BORDER),
    ]
    for i, k in enumerate(_TIER_ORDER):
        if k == tier_key:
            landscape_style.append(("BACKGROUND", (i, 0), (i, 0), _PDF_CREAM_S))
            landscape_style.append(("LINEBELOW", (i, 0), (i, 0), 3.0, _PDF_FOREST))
            landscape_style.append(("LINEABOVE", (i, 0), (i, 0), 3.0, _PDF_FOREST))
    landscape.setStyle(TableStyle(landscape_style))
    flow.append(Paragraph("TIER LANDSCAPE", styles["Label"]))
    flow.append(Spacer(1, 0.15 * cm))
    flow.append(landscape)

    return flow


def _trial_readiness_page(tr: dict, styles):
    """Premium scout-style checklist page. Renders the headline + a grid of items.

    Each item shows: status icon, label, value, and the required thresholds."""
    if not isinstance(tr, dict) or not tr.get("items"):
        return []

    flow = []

    # Headline strip — forest or cream depending on readiness tier
    tier_key = tr.get("readiness_tier")
    if tier_key in ("pro_academy",):
        bg = _PDF_FOREST
        fg_hex = "#FFFFFF"
        eyebrow_hex = "#FFFFFFAA"
    elif tier_key in ("strong_club",):
        bg = _PDF_FOREST_POP
        fg_hex = "#FFFFFF"
        eyebrow_hex = "#FFFFFFAA"
    else:
        bg = _PDF_CREAM_S
        fg_hex = "#0A0F0D"
        eyebrow_hex = "#1F4F2F"

    headline_left = Paragraph(
        f"<font color='{eyebrow_hex}' size='7'><b>TODAY, THIS PLAYER IS</b></font><br/>"
        f"<font color='{fg_hex}' size='17'><b>{tr.get('headline', 'Trial readiness')}</b></font><br/><br/>"
        f"<font color='{fg_hex}' size='9'><b>STRONG CLUB {tr.get('strong_club_score', '-')}</b>"
        f"&nbsp;&nbsp;&nbsp;<b>PRO ACADEMY {tr.get('pro_academy_score', '-')}</b></font>",
        styles["BodyW"],
    )
    headline_right = Paragraph(
        f"<font color='{eyebrow_hex}' size='7'><b>POSITION</b></font><br/>"
        f"<font color='{fg_hex}' size='11'><b>{(tr.get('position_key') or '').upper()}</b></font>",
        styles["BodyW"],
    )
    headline = Table([[headline_left, headline_right]], colWidths=[11.5 * cm, 4.0 * cm])
    headline.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), bg),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    flow.append(headline)
    flow.append(Spacer(1, 0.4 * cm))

    # Checklist grid — 2 columns
    items = tr.get("items", [])
    rows = []
    for i in range(0, len(items), 2):
        row_cells = []
        for j in range(2):
            if i + j >= len(items):
                row_cells.append("")
                continue
            it = items[i + j]
            row_cells.append(_trial_item_cell(it, styles))
        rows.append(row_cells)

    grid = Table(rows, colWidths=[7.75 * cm, 7.75 * cm])
    grid_style = [
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    grid.setStyle(TableStyle(grid_style))
    flow.append(grid)

    flow.append(Spacer(1, 0.4 * cm))
    flow.append(Paragraph(
        "<i><font color='#6B7280' size='8'>Trial readiness is computed from the scores in this report. "
        "It is a scout-style guide, not a guarantee of selection.</font></i>",
        styles["BodyW"],
    ))
    return flow


def _trial_item_cell(item: dict, styles):
    """A single checklist cell — icon + label + status line."""
    if item.get("no_data"):
        mark_hex = "#9CA3AF"
        bg = HexColor("#E5E7EB")
        status = "NO DATA"
        status_hex = "#9CA3AF"
        mark = "—"
    elif item.get("pro_academy_met"):
        mark_hex = "#FFFFFF"
        bg = _PDF_FOREST
        status = "PRO ACADEMY READY"
        status_hex = "#1F4F2F"
        mark = "✓"
    elif item.get("strong_club_met"):
        mark_hex = "#1F4F2F"
        bg = _PDF_CREAM_S
        status = "STRONG CLUB READY"
        status_hex = "#2D6B3D"
        mark = "✓"
    else:
        mark_hex = "#9CA3AF"
        bg = _PDF_CARD
        status = "NEEDS WORK"
        status_hex = "#9CA3AF"
        mark = "○"

    icon = Paragraph(f"<font color='{mark_hex}' size='14'><b>{mark}</b></font>", styles["BodyW"])
    val = item.get("value")
    sc_min = item.get("strong_club_min")
    pa_min = item.get("pro_academy_min")
    score_line = ""
    if not item.get("no_data") and val is not None:
        score_line = (
            f"<font color='#9CA3AF' size='7'>"
            f"&nbsp;&nbsp;score {val} · need {sc_min}/{pa_min}"
            f"</font>"
        )
    body = Paragraph(
        f"<font color='#0A0F0D' size='9.5'><b>{item.get('label', '')}</b></font><br/>"
        f"<font color='{status_hex}' size='7'><b>{status}</b></font>{score_line}",
        styles["BodyW"],
    )
    cell = Table([[icon, body]], colWidths=[1.0 * cm, 6.6 * cm])
    cell.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _PDF_CARD),
        ("BACKGROUND",    (0, 0), (0, 0),   bg),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("ALIGN",         (0, 0), (0, 0),   "CENTER"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return cell





def _archetype_card_pdf(archetype: dict, styles):
    """Forest hero card — stylistic archetype block for the PDF cover area.
    Renders the new Gemini narrative + age-bracketed bio chunk when present."""
    if not isinstance(archetype, dict) or not archetype.get("name"):
        return []

    developing = bool(archetype.get("developing"))
    bg = _PDF_CARD if developing else _PDF_FOREST
    fg_hex = "#0A0F0D" if developing else "#FFFFFF"
    eyebrow_hex = "#1F4F2F" if developing else "#FFFFFFAA"

    traits = archetype.get("traits") or []
    traits_html = ""
    if traits:
        traits_html = "<br/><br/>" + "&nbsp;&nbsp;".join(
            f"<font color='{eyebrow_hex}' size='7'><b>· {t.upper()}</b></font>" for t in traits[:5]
        )

    match_html = ""
    if not developing and isinstance(archetype.get("match_strength"), (int, float)):
        match_html = (
            f"<font color='{eyebrow_hex}' size='7'><b>MATCH STRENGTH</b></font><br/>"
            f"<font color='{fg_hex}' size='24'><b>{archetype['match_strength']:.1f}</b></font>"
            f"<font color='{eyebrow_hex}' size='10'> / 10</font>"
        )

    left = Paragraph(
        f"<font color='{eyebrow_hex}' size='7'><b>STYLISTIC ARCHETYPE</b></font><br/>"
        f"<font color='{fg_hex}' size='17'><b>{archetype['name']}</b></font><br/><br/>"
        f"<font color='{fg_hex}' size='9.5'>{archetype.get('summary', '')}</font>"
        f"{traits_html}",
        styles["BodyW"],
    )
    right = Paragraph(match_html or "&nbsp;", styles["BodyW"])

    card = Table([[left, right]], colWidths=[11.5 * cm, 4.0 * cm])
    card.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), bg),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("ALIGN",         (1, 0), (1, 0),   "RIGHT"),
    ]))

    flow = [card, Spacer(1, 0.2 * cm)]

    # ----- Narrative card (Gemini-generated, age-anchored) ------------------
    narrative = (archetype.get("narrative") or "").strip()
    if narrative and not developing:
        narrative_card = Table(
            [[Paragraph(
                f"<font color='#1F4F2F' size='7'><b>PERSONALIZED COMPARISON · AGE-ANCHORED</b></font><br/><br/>"
                f"<font color='#0A0F0D' size='10'>{narrative}</font>",
                styles["BodyW"],
            )]],
            colWidths=[15.5 * cm],
        )
        narrative_card.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), _PDF_CARD),
            ("LINEBEFORE",    (0, 0), (0, -1),  3, _PDF_FOREST),
            ("LEFTPADDING",   (0, 0), (-1, -1), 14),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
            ("TOPPADDING",    (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ]))
        flow += [narrative_card, Spacer(1, 0.2 * cm)]

    # ----- Age-bracketed bio chunk (the verifiable fact) --------------------
    bio_chunk = (archetype.get("academy_bio_chunk") or "").strip()
    bracket = archetype.get("age_bracket_used")
    if bio_chunk and bracket and not developing:
        pro_name = _pro_name_from_archetype(archetype)
        bio_card = Table(
            [[Paragraph(
                f"<font color='#1F4F2F' size='7'><b>WHAT {pro_name.upper()} WAS DOING AT AGE {bracket}</b></font><br/><br/>"
                f"<font color='#0A0F0D' size='9.5'><i>{bio_chunk}</i></font>",
                styles["BodyW"],
            )]],
            colWidths=[15.5 * cm],
        )
        bio_card.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), "#F4EFE6"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 14),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
            ("TOPPADDING",    (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ]))
        flow += [bio_card, Spacer(1, 0.2 * cm)]

    # ----- Career brief — FBref / Transfermarkt verified career stats -------
    career_brief = (archetype.get("career_brief") or "").strip()
    if career_brief and not developing:
        pro_name = _pro_name_from_archetype(archetype)
        career_card = Table(
            [[Paragraph(
                f"<font color='#1F4F2F' size='7'><b>{pro_name.upper()} &middot; CAREER SNAPSHOT (FBREF &middot; TRANSFERMARKT)</b></font><br/><br/>"
                f"<font color='#0A0F0D' size='9'>{career_brief}</font>",
                styles["BodyW"],
            )]],
            colWidths=[15.5 * cm],
        )
        career_card.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), _PDF_CARD),
            ("LINEBEFORE",    (0, 0), (0, -1),  3, _PDF_FOREST),
            ("LEFTPADDING",   (0, 0), (-1, -1), 14),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
            ("TOPPADDING",    (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ]))
        flow += [career_card, Spacer(1, 0.2 * cm)]

    flow.append(Paragraph(
        "<i><font color='#9CA3AF' size='7.5'>Stylistic comparisons describe how this player plays today — "
        "not their ceiling, and not the named professional's youth data.</font></i>",
        styles["BodyW"],
    ))
    return flow


def _lens_matches_pdf(archetype: dict, styles):
    """5-Lens strip — Style / Build / Role / Career-path / FIFA k-NN for the PDF."""
    if not isinstance(archetype, dict):
        return []
    lenses = archetype.get("lenses") or {}
    if not lenses:
        return []

    # Count active lenses for header text
    lens_keys = [k for k in ("style", "build", "role", "path", "fifa") if (lenses.get(k) or {}).get("name")]
    n = len(lens_keys)
    if n == 0:
        return []

    header = Paragraph(
        f"<font color='#1F4F2F' size='7'><b>THE {n}-LENS COMPARISON</b></font><br/>"
        f"<font color='#0A0F0D' size='13'><b>How this player resembles {n} different professionals</b></font><br/>"
        "<font color='#0A0F0D' size='8.5'>Each lens picks the closest pro on a different dimension: how he plays, "
        "his physical build, his on-pitch role, the career path he's on"
        + (", and a real k-NN similarity search against 7,500+ FIFA-rated senior pros." if "fifa" in lens_keys else ".")
        + "</font>",
        styles["BodyW"],
    )

    rows = [[
        Paragraph("<font color='#FFFFFF' size='7'><b>LENS</b></font>", styles["BodyW"]),
        Paragraph("<font color='#FFFFFF' size='7'><b>MATCHED PRO</b></font>", styles["BodyW"]),
        Paragraph("<font color='#FFFFFF' size='7'><b>WHY</b></font>", styles["BodyW"]),
        Paragraph("<font color='#FFFFFF' size='7'><b>SCORE</b></font>", styles["BodyW"]),
    ]]
    for key in lens_keys:
        lens = lenses.get(key) or {}
        is_fifa = (key == "fifa")
        score_html = (
            f"<font color='#1F4F2F' size='14'><b>{lens.get('similarity_pct', 0):.1f}</b></font>"
            f"<font color='#9CA3AF' size='7'>%</font>"
            if is_fifa else
            f"<font color='#1F4F2F' size='14'><b>{lens.get('score', 0):.1f}</b></font>"
            f"<font color='#9CA3AF' size='7'> /10</font>"
        )
        rows.append([
            Paragraph(f"<font color='#0A0F0D' size='9'><b>{(lens.get('lens_label') or key).upper()}</b></font>", styles["BodyW"]),
            Paragraph(
                f"<font color='#0A0F0D' size='9'><b>{lens.get('name', '')}</b></font><br/>"
                f"<font color='#9CA3AF' size='7'>{lens.get('club', '') or ''}"
                + (f" · {lens.get('league')}" if lens.get('league') else "")
                + "</font>",
                styles["BodyW"],
            ),
            Paragraph(f"<font color='#0A0F0D' size='8'>{lens.get('why', '')}</font>", styles["BodyW"]),
            Paragraph(score_html, styles["BodyW"]),
        ])

    if len(rows) <= 1:
        return []

    table = Table(rows, colWidths=[2.8 * cm, 4.6 * cm, 6.4 * cm, 1.7 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  _PDF_FOREST),
        ("BACKGROUND",    (0, 1), (-1, -1), _PDF_CARD),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [_PDF_CARD, "#F4EFE6"]),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))

    return [header, Spacer(1, 0.2 * cm), table, Spacer(1, 0.2 * cm)]


def _fifa_neighbors_pdf(archetype: dict, styles):
    """FIFA Data Twin — top-5 nearest-neighbour result as a PDF table."""
    if not isinstance(archetype, dict):
        return []
    neighbors = archetype.get("fifa_neighbors") or []
    if not neighbors:
        return []
    meta = archetype.get("fifa_db_meta") or {}
    db_size = meta.get("size") or 7500

    header = Paragraph(
        "<font color='#1F4F2F' size='7'><b>FIFA DATA TWIN &middot; REAL SIMILARITY SEARCH</b></font><br/>"
        "<font color='#0A0F0D' size='13'><b>The 5 closest senior pros by 22-attribute k-NN</b></font><br/>"
        f"<font color='#0A0F0D' size='8.5'>The player's full scoring vector was matched against "
        f"<b>{db_size:,} senior pros</b> in the EA Sports FIFA-22 dataset using per-attribute "
        "Euclidean similarity across 22 dimensions.</font>",
        styles["BodyW"],
    )

    rows = [[
        Paragraph("<font color='#FFFFFF' size='7'><b>#</b></font>", styles["BodyW"]),
        Paragraph("<font color='#FFFFFF' size='7'><b>PRO</b></font>", styles["BodyW"]),
        Paragraph("<font color='#FFFFFF' size='7'><b>BUILD &middot; FOOT</b></font>", styles["BodyW"]),
        Paragraph("<font color='#FFFFFF' size='7'><b>CLOSEST ON</b></font>", styles["BodyW"]),
        Paragraph("<font color='#FFFFFF' size='7'><b>SIMILARITY</b></font>", styles["BodyW"]),
    ]]
    for i, n in enumerate(neighbors[:5]):
        nearest_str = ", ".join(a.replace("_", " ") for a in (n.get("nearest_attrs") or [])[:3])
        club_line = (n.get('club') or '')
        if n.get('league'):
            club_line += f" &middot; {n.get('league')}"
        if n.get('overall'):
            club_line += f" &middot; FIFA {n.get('overall')}"
        rows.append([
            Paragraph(f"<font color='#1F4F2F' size='13'><b>{i+1}</b></font>", styles["BodyW"]),
            Paragraph(
                f"<font color='#0A0F0D' size='9'><b>{n.get('name', '')}</b></font><br/>"
                f"<font color='#9CA3AF' size='7'>{club_line}</font>",
                styles["BodyW"],
            ),
            Paragraph(
                f"<font color='#0A0F0D' size='8'>{(n.get('build') or '').replace('_', ' ')}</font><br/>"
                f"<font color='#9CA3AF' size='7'>{(n.get('preferred_foot') or '').upper()}-FOOTED</font>",
                styles["BodyW"],
            ),
            Paragraph(f"<font color='#0A0F0D' size='8'>{nearest_str}</font>", styles["BodyW"]),
            Paragraph(
                f"<font color='#1F4F2F' size='14'><b>{n.get('similarity_pct', 0):.1f}</b></font>"
                f"<font color='#9CA3AF' size='7'>%</font>",
                styles["BodyW"],
            ),
        ])

    table = Table(rows, colWidths=[0.7 * cm, 4.6 * cm, 3.1 * cm, 5.4 * cm, 1.7 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0),  _PDF_FOREST),
        ("BACKGROUND",     (0, 1), (-1, -1), _PDF_CARD),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_PDF_CARD, "#F4EFE6"]),
        ("LEFTPADDING",    (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 7),
        ("TOPPADDING",     (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 7),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]))

    footnote = Paragraph(
        "<i><font color='#9CA3AF' size='7.5'>Similarity = 100 &minus; RMSE &times; 18 across 22 measured attributes "
        "(FIFA attribute ratings normalised to 0-10, identical to the player's scale). "
        f"Source: {meta.get('source') or 'EA Sports FIFA 22'}. "
        "Capped at 92% &mdash; a youth-player score should never match a senior pro 99%.</font></i>",
        styles["BodyW"],
    )

    return [header, Spacer(1, 0.2 * cm), table, Spacer(1, 0.2 * cm), footnote, Spacer(1, 0.2 * cm)]




def _age_profile_page(profile: dict, styles):
    """European Academy reference profile — position priorities table."""
    if not isinstance(profile, dict) or not profile.get("items"):
        return []

    flow = []
    pos = (profile.get("position_key") or "").upper()
    age = (profile.get("age_bracket") or "").upper()
    summary = (profile.get("summary") or "").replace("<b>", "").replace("</b>", "")

    eyebrow = Paragraph(
        f"<font color='#1F4F2F' size='7'><b>EUROPEAN ACADEMY REFERENCE PROFILE</b></font><br/>"
        f"<font color='#0A0F0D' size='9.5'>The attributes that matter most for a {profile.get('position_key', '')}"
        f" — measured against the Pro Academy expectation for {profile.get('age_bracket', 'the age bracket')}.</font>",
        styles["BodyW"],
    )
    chip = Paragraph(
        f"<font color='#1F4F2F' size='6.5'><b>POSITION · AGE</b></font><br/>"
        f"<font color='#0A0F0D' size='10'><b>{pos}{' · ' + age if age else ''}</b></font><br/>"
        f"<font color='#4B5563' size='7.5'><b>{summary.upper()}</b></font>",
        styles["BodyW"],
    )
    intro = Table([[eyebrow, chip]], colWidths=[11.0 * cm, 4.5 * cm])
    intro.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND",    (1, 0), (1, 0),   _PDF_CARD),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (1, 0), (1, 0),   12),
        ("RIGHTPADDING",  (1, 0), (1, 0),   12),
        ("LINEBEFORE",    (1, 0), (1, 0),   2.0, _PDF_FOREST),
    ]))
    flow.append(intro)
    flow.append(Spacer(1, 0.35 * cm))

    head = [
        Paragraph("<font color='#9CA3AF' size='7'><b>ATTRIBUTE</b></font>", styles["BodyW"]),
        Paragraph("<font color='#9CA3AF' size='7'><b>IMPORTANCE</b></font>", styles["BodyW"]),
        Paragraph("<font color='#9CA3AF' size='7'><b>PRO RANGE</b></font>", styles["BodyW"]),
        Paragraph("<font color='#9CA3AF' size='7'><b>PLAYER</b></font>", styles["BodyW"]),
        Paragraph("<font color='#9CA3AF' size='7'><b>STATE</b></font>", styles["BodyW"]),
    ]
    rows = [head]
    for it in profile["items"]:
        delta = it.get("delta")
        if delta == "at_or_above":
            state_html = "<font color='#1F4F2F' size='8'><b>▲ AT OR ABOVE</b></font>"
        elif delta == "below":
            state_html = "<font color='#D97706' size='8'><b>▼ BELOW</b></font>"
        else:
            state_html = "<font color='#9CA3AF' size='8'><b>—</b></font>"

        weight = it.get("weight", 3)
        dots = ""
        for i in range(5):
            color = "#1F4F2F" if i < weight else "#D6D3D1"
            dots += f"<font color='{color}' size='12'>●</font> "

        attr_p = Paragraph(
            f"<font color='#0A0F0D' size='10'><b>{it.get('label', '')}</b></font><br/>"
            f"<font color='#6B7280' size='7.5'>{it.get('why_matters', '')}</font>",
            styles["BodyW"],
        )
        player_val = it.get('player_score')
        if player_val is None:
            player_cell = Paragraph("<font color='#9CA3AF' size='16'><b>—</b></font>", styles["BodyW"])
        else:
            player_cell = Paragraph(
                f"<font color='#1F4F2F' size='15'><b>{player_val}</b></font>"
                f"<font color='#9CA3AF' size='8'>&nbsp;/10</font>",
                ParagraphStyle("_apc", fontName="Helvetica-Bold", fontSize=15, leading=18,
                               textColor=_PDF_FOREST, spaceAfter=0, alignment=TA_CENTER),
            )
        rows.append([
            attr_p,
            Paragraph(f"<font size='10'>{dots}</font>", styles["BodyW"]),
            Paragraph(f"<font color='#0A0F0D' size='10'><b>{it.get('pro_academy_range', '—')}</b></font>", styles["BodyW"]),
            player_cell,
            Paragraph(state_html, styles["BodyW"]),
        ])

    # Widen PLAYER + STATE columns for breathing room; tighten ATTRIBUTE slightly
    table = Table(rows, colWidths=[6.0 * cm, 2.6 * cm, 2.2 * cm, 1.9 * cm, 2.8 * cm])
    style = [
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("ALIGN",         (3, 1), (3, -1),  "CENTER"),
        ("ALIGN",         (2, 1), (2, -1),  "CENTER"),
        ("ALIGN",         (1, 1), (1, -1),  "LEFT"),
        ("ALIGN",         (4, 1), (4, -1),  "RIGHT"),
        ("BACKGROUND",    (0, 0), (-1, 0),  HexColor("#F0EAE0")),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.4, _PDF_FOREST),
    ]
    for i in range(1, len(rows)):
        style.append(("BACKGROUND", (0, i), (-1, i), _PDF_CARD))
        style.append(("LINEBELOW",  (0, i), (-1, i), 0.3, _PDF_BORDER))
        style.append(("LINEBEFORE", (0, i), (0, i),  2.0, _PDF_FOREST))
    table.setStyle(TableStyle(style))
    flow.append(table)
    flow.append(Spacer(1, 0.3 * cm))
    flow.append(Paragraph(
        "<i><font color='#9CA3AF' size='8'>Reference profile is curated from European youth-academy development "
        "frameworks. It compares the player's actual scores against what scouts at Pro Academy level typically "
        "look for.</font></i>",
        styles["BodyW"],
    ))
    return flow


def _statsbomb_calibration_pdf(calibration: dict, styles):
    """Pro Calibration table for the PDF — anchors player scores against
    Euro 2024 senior-pro per-90 percentiles. Cites StatsBomb open data."""
    if not isinstance(calibration, dict):
        return []
    rows_in = calibration.get("rows") or []
    if not rows_in:
        return []

    BUCKET_LABEL = {
        "p90":      "Top 10%",
        "p75":      "Top 25%",
        "p50":      "Median pro",
        "p25":      "Bottom 25%",
        "below_p25": "Below pro",
    }
    BUCKET_COLOR = {
        "p90":       _PDF_FOREST,
        "p75":       "#1F4F2F",
        "p50":       "#9CA3AF",
        "p25":       "#9CA3AF",
        "below_p25": "#9CA3AF",
    }

    header = Paragraph(
        "<font color='#1F4F2F' size='7'><b>PRO CALIBRATION &middot; STATSBOMB EURO 2024</b></font><br/>"
        "<font color='#0A0F0D' size='13'><b>Where your scores sit vs Euro 2024 senior pros</b></font><br/>"
        f"<font color='#0A0F0D' size='8.5'>Each AI score is anchored against the actual per-90 distribution "
        f"of <b>{calibration.get('position_n')} {calibration.get('position')} starters</b> at the European "
        f"Championship 2024 &mdash; extracted from public StatsBomb event-level data across "
        f"<b>{calibration.get('matches')} matches</b>.</font>",
        styles["BodyW"],
    )

    rows = [[
        Paragraph("<font color='#FFFFFF' size='7'><b>ATTRIBUTE</b></font>", styles["BodyW"]),
        Paragraph("<font color='#FFFFFF' size='7'><b>STATSBOMB METRIC</b></font>", styles["BodyW"]),
        Paragraph("<font color='#FFFFFF' size='7'><b>SCORE</b></font>", styles["BodyW"]),
        Paragraph("<font color='#FFFFFF' size='7'><b>vs EURO 2024 PROS</b></font>", styles["BodyW"]),
        Paragraph("<font color='#FFFFFF' size='7'><b>PRO REFERENCE</b></font>", styles["BodyW"]),
    ]]
    for r in rows_in:
        bucket = r.get("bucket", "p25")
        pro_ref = (
            f"p90={r.get('pro_p90')}" if bucket == "p90" else
            f"p75={r.get('pro_p75')}" if bucket == "p75" else
            f"p50={r.get('pro_p50')}" if bucket == "p50" else
            f"p25={r.get('pro_p25')}"
        )
        rows.append([
            Paragraph(f"<font color='#0A0F0D' size='9'><b>{r.get('attribute_label', '')}</b></font>", styles["BodyW"]),
            Paragraph(f"<font color='#0A0F0D' size='8'>{r.get('statsbomb_metric_label', '')}</font>", styles["BodyW"]),
            Paragraph(
                f"<font color='#1F4F2F' size='14'><b>{r.get('score')}</b></font>"
                f"<font color='#9CA3AF' size='7'> /10</font>",
                styles["BodyW"],
            ),
            Paragraph(
                f"<font color='{BUCKET_COLOR.get(bucket, '#9CA3AF')}' size='9'>"
                f"<b>{BUCKET_LABEL.get(bucket, bucket)}</b></font>",
                styles["BodyW"],
            ),
            Paragraph(f"<font color='#9CA3AF' size='8'>{pro_ref}</font>", styles["BodyW"]),
        ])

    table = Table(rows, colWidths=[3.3 * cm, 4.5 * cm, 1.7 * cm, 3.4 * cm, 2.6 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0),  _PDF_FOREST),
        ("BACKGROUND",     (0, 1), (-1, -1), _PDF_CARD),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_PDF_CARD, "#F4EFE6"]),
        ("LEFTPADDING",    (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 7),
        ("TOPPADDING",     (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 7),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]))

    footnote = Paragraph(
        f"<i><font color='#9CA3AF' size='7.5'><b>Source:</b> {calibration.get('source')} "
        f"&middot; {calibration.get('source_url')} &middot; "
        f"License: {calibration.get('license', '')}. "
        f"<b>Methodology:</b> {calibration.get('methodology', '')}</font></i>",
        styles["BodyW"],
    )

    return [header, Spacer(1, 0.2 * cm), table, Spacer(1, 0.2 * cm), footnote, Spacer(1, 0.2 * cm)]





def _age_intelligence_pdf(age_intel: dict, styles):
    """Stage banner + 9-score scoreboard + disclaimer + what-we-evaluated."""
    if not isinstance(age_intel, dict):
        return []
    stage = age_intel.get("stage") or {}
    scores = age_intel.get("scores") or {}
    level = age_intel.get("level") or {}

    # 1) Stage banner (forest hero)
    level_html = ""
    if level and level.get("label"):
        level_html = (
            f"<font color='#FFFFFF' size='8'><b>LEVEL: {level['label'].upper()}</b></font><br/>"
            f"<font color='#FFFFFFAA' size='8'>{level.get('definition','')}</font>"
        )
    stage_card = Table(
        [[Paragraph(
            f"<font color='#FFFFFFAA' size='7'><b>AGE-ANCHORED EVALUATION</b></font><br/>"
            f"<font color='#FFFFFF' size='17'><b>{stage.get('age_band','')} &middot; {stage.get('label','')}</b></font><br/>"
            f"<font color='#FFFFFFAA' size='9'><i>{stage.get('headline','')}</i></font>",
            styles["BodyW"],
        ),
        Paragraph(level_html or "&nbsp;", styles["BodyW"])]],
        colWidths=[11.0 * cm, 4.5 * cm],
    )
    stage_card.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _PDF_FOREST),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("ALIGN",         (1, 0), (1, 0),   "RIGHT"),
    ]))

    # 2) Disclaimer
    disclaimer = age_intel.get("disclaimer") or ""
    disc_card = Table(
        [[Paragraph(
            f"<font color='#1F4F2F' size='7'><b>HOW THIS EVALUATION WORKS</b></font><br/><br/>"
            f"<font color='#0A0F0D' size='9'>{disclaimer}</font>",
            styles["BodyW"],
        )]],
        colWidths=[15.5 * cm],
    )
    disc_card.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), "#F4EFE6"),
        ("LINEBEFORE",    (0, 0), (0, -1),  3, _PDF_FOREST),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))

    # 3) 9-score grid (3 columns × 3 rows)
    SCORE_ORDER = [
        ("current_age_score",             "Current Age Score"),
        ("position_specific_score",       "Position-Specific"),
        ("next_level_readiness_score",    "Next-Level Readiness"),
        ("pro_style_match_score",         "Pro Style Match"),
        ("technical_score",               "Technical"),
        ("tactical_score",                "Tactical"),
        ("physical_score",                "Physical"),
        ("mentality_body_language_score", "Mentality / Body Lang."),
        ("development_priority_score",    "Dev. Priority"),
    ]

    def _score_cell(label, val, highlight=False):
        fg = "#FFFFFF" if highlight else "#0A0F0D"
        eyebrow = "#FFFFFFAA" if highlight else "#1F4F2F"
        if val is None:
            val_html = f"<font color='{fg}' size='14'><b>&mdash;</b></font><br/><font color='{eyebrow}' size='7'>unlocks at U12</font>"
        else:
            val_html = f"<font color='{fg}' size='18'><b>{float(val):.1f}</b></font><font color='{eyebrow}' size='7'> /10</font>"
        return Paragraph(
            f"<font color='{eyebrow}' size='6.5'><b>{label.upper()}</b></font><br/>{val_html}",
            styles["BodyW"],
        )

    rows = []
    row = []
    for i, (key, label) in enumerate(SCORE_ORDER):
        cell = _score_cell(label, scores.get(key), highlight=(key == "current_age_score"))
        row.append(cell)
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        while len(row) < 3:
            row.append(Paragraph("&nbsp;", styles["BodyW"]))
        rows.append(row)

    grid = Table(rows, colWidths=[5.17 * cm] * 3)
    grid_styles = [
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]
    # Background colours per cell (forest for current_age, cream for the rest)
    for r in range(len(rows)):
        for c in range(3):
            idx = r * 3 + c
            if idx < len(SCORE_ORDER) and SCORE_ORDER[idx][0] == "current_age_score":
                grid_styles.append(("BACKGROUND", (c, r), (c, r), _PDF_FOREST))
            elif idx < len(SCORE_ORDER):
                grid_styles.append(("BACKGROUND", (c, r), (c, r), _PDF_CARD))
    grid.setStyle(TableStyle(grid_styles))

    # 4) What we evaluated · what we did not
    evaluated   = age_intel.get("what_we_evaluated", []) or []
    not_for     = age_intel.get("what_we_could_not_evaluate", []) or []

    left_html = (
        "<font color='#1F4F2F' size='7'><b>EVALUATED FOR THIS STAGE</b></font><br/><br/>"
        + "".join(
            f"<font color='#0A0F0D' size='9'>&middot; {e}</font><br/>" for e in evaluated
        )
    )
    right_html = (
        "<font color='#9CA3AF' size='7'><b>DELIBERATELY NOT EVALUATED AT THIS STAGE</b></font><br/><br/>"
        + ("".join(f"<font color='#0A0F0D' size='9'>&middot; {e}</font><br/>" for e in not_for)
           if not_for
           else "<font color='#9CA3AF' size='9'><i>At this stage we evaluate everything visible.</i></font>")
    )
    eval_block = Table(
        [[Paragraph(left_html, styles["BodyW"]), Paragraph(right_html, styles["BodyW"])]],
        colWidths=[7.75 * cm, 7.75 * cm],
    )
    eval_block.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0),  _PDF_CARD),
        ("BACKGROUND",    (1, 0), (1, 0),  "#F4EFE6"),
        ("LINEBEFORE",    (0, 0), (0, 0),  3, _PDF_FOREST),
        ("LINEBEFORE",    (1, 0), (1, 0),  3, "#D6D3D1"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))

    return [
        stage_card,
        Spacer(1, 0.2 * cm),
        disc_card,
        Spacer(1, 0.3 * cm),
        Paragraph(
            "<font color='#1F4F2F' size='7'><b>AGE INTELLIGENCE SCOREBOARD</b></font><br/>"
            "<font color='#0A0F0D' size='12'><b>9 scores &middot; age-anchored, deterministic</b></font>",
            styles["BodyW"],
        ),
        Spacer(1, 0.15 * cm),
        grid,
        Spacer(1, 0.3 * cm),
        eval_block,
        Spacer(1, 0.3 * cm),
    ]



def build_pdf(report_doc: dict, output_path: str):
    """Builds a premium cream/forest PDF. Document is organised as:
        Page 1  — Cover (forest panel + player name + score box)
        Page 2  — Executive Summary + Score Overview
        Page 3+ — Technical / Tactical / Physical / Mentality (one full section per spread)
        Page    — Scout View
        Page    — Potential Assessment
        Page    — Personal Training Plan (5 drills + weekly + 30/90 day)
        Page    — Video Comments (if any)
        Page    — Final Summary + closing
    """
    full = report_doc["full_report"]
    details = report_doc["player_details"]
    styles = _pdf_styles()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.9 * cm,
        bottomMargin=2.2 * cm,
        title=f"ScoutMePlay Report — {details.get('player_name','Player')}",
        author="ScoutMePlay · Mentalkids",
        subject="Football Player Development Report",
    )

    # Page templates: the FIRST page uses the cover background (forest panel on left),
    # SUBSEQUENT pages use the regular cream background with the slim forest rail.
    from reportlab.platypus.doctemplate import PageTemplate
    from reportlab.platypus.frames import Frame

    cover_frame = Frame(
        x1=doc.pagesize[0] * 0.34 + 1.0 * cm,
        y1=2.0 * cm,
        width=doc.pagesize[0] * 0.66 - 2.6 * cm,
        height=doc.pagesize[1] - 4.0 * cm,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        id="cover",
    )
    inner_frame = Frame(
        x1=1.6 * cm + 0.3 * cm,
        y1=2.0 * cm,
        width=doc.pagesize[0] - 3.2 * cm - 0.3 * cm,
        height=doc.pagesize[1] - 4.0 * cm,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        id="inner",
    )
    doc.addPageTemplates([
        PageTemplate(id="Cover", frames=[cover_frame], onPage=_draw_cover_background),
        PageTemplate(id="Inner", frames=[inner_frame], onPage=_draw_background),
    ])

    story = []
    player_name = (details.get("player_name") or "Player").upper()
    position = (details.get("position") or "").title()
    age = details.get("age", "—")
    foot = (details.get("preferred_foot") or "").title() or "—"
    club = details.get("current_club") or "Independent"

    # ===== COVER =====
    story.append(Spacer(1, 4 * cm))
    story.append(Paragraph("SCOUTMEPLAY · PREMIUM PLAYER REPORT", styles["Eyebrow"]))
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph(player_name, styles["HeroTitle"]))
    story.append(Spacer(1, 0.1 * cm))
    story.append(Paragraph(
        f"<b>{position or '—'}</b> &nbsp;·&nbsp; Age {age} &nbsp;·&nbsp; {foot} foot",
        styles["BodyW"],
    ))
    story.append(Paragraph(club, styles["BodyMuted"]))
    story.append(Spacer(1, 1.2 * cm))

    overall = full.get("scores", {}).get("overall_development", "—")
    ptype = full.get("player_type", "Independent")
    story.append(_cover_summary_box(str(overall), ptype, "", styles))
    story.append(Spacer(1, 0.8 * cm))

    # Executive paragraph teaser on the cover — show only the FIRST clean sentence
    # so it never appears truncated. The full summary is on page 2.
    exec_summary = full.get("executive_summary", "")
    if exec_summary:
        snippet = exec_summary.strip()
        # Take just the first sentence (clean break, never mid-word)
        for sep in (". ", "! ", "? "):
            if sep in snippet:
                snippet = snippet.split(sep, 1)[0] + sep.strip()
                break
        if len(snippet) > 220:
            snippet = snippet[:217].rsplit(" ", 1)[0] + "…"
        story.append(Paragraph("EXECUTIVE SUMMARY", styles["Eyebrow"]))
        story.append(Paragraph(snippet, styles["QuoteLead"]))

    story.append(Spacer(1, 1.0 * cm))
    story.append(Paragraph(
        f"Issued by SCOUTMEPLAY · Mentalkids &nbsp;·&nbsp; {datetime.now(timezone.utc).strftime('%d %B %Y')}",
        styles["CoverFootnote"],
    ))
    story.append(Paragraph(
        "Independent player development analysis. Not a recruitment guarantee.",
        styles["MutedW"],
    ))

    # Switch to inner template starting from page 2
    from reportlab.platypus import NextPageTemplate
    story.append(NextPageTemplate("Inner"))
    story.append(PageBreak())

    # ===== PAGE 2 — 60-SECOND SCOUT SUMMARY (shareable single-page TL;DR) =====
    scout_summary_flow = _scout_summary_page(report_doc, styles)
    if scout_summary_flow:
        story += scout_summary_flow
        story.append(PageBreak())

    # ===== EXECUTIVE SUMMARY + SCORE OVERVIEW =====
    story += _section_header("Executive summary", styles, idx=1)
    story.append(Paragraph(exec_summary or "Not provided.", styles["BodyW"]))
    story.append(Spacer(1, 0.8 * cm))

    story += _section_header("Score overview", styles, idx=2)
    sc = full.get("scores", {}) or {}
    score_rows = [
        ("Technical",            sc.get("technical"),           "Composite technical ability"),
        ("Tactical",             sc.get("tactical"),            "Composite tactical intelligence"),
        ("Physical",             sc.get("physical"),            "Composite physical attributes"),
        ("Mentality",            sc.get("mentality"),           "Composite mental attributes"),
        ("Overall development",  sc.get("overall_development"), "Holistic developmental indicator"),
    ]
    story.append(_score_table(score_rows, styles))

    # ===== HOW YOU COMPARE — Overall benchmark (signature page) =====
    ob = full.get("overall_benchmark") or {}
    if ob.get("tier"):
        story.append(PageBreak())
        story += _section_header("How you compare", styles, idx=3)
        story += _overall_benchmark_page(ob, sc.get("overall_development"), styles)

    # ===== AGE INTELLIGENCE SCOREBOARD — stage banner, 9 scores, what we evaluated =====
    age_intel = report_doc.get("age_intelligence")
    if age_intel:
        story.append(Spacer(1, 0.5 * cm))
        story += _age_intelligence_pdf(age_intel, styles)

    # ===== STYLISTIC ARCHETYPE — placed right after the age intelligence block =====
    archetype = report_doc.get("archetype")
    if archetype and archetype.get("name"):
        story.append(Spacer(1, 0.5 * cm))
        story += _archetype_card_pdf(archetype, styles)
        # 5-Lens twins strip (Style / Build / Role / Career-path / FIFA)
        story.append(Spacer(1, 0.3 * cm))
        story += _lens_matches_pdf(archetype, styles)
        # FIFA Data Twin — top-5 closest senior pros by real k-NN
        # (Stripped by apply_stage_gating for U6-U11, so this is a no-op there.)
        if archetype.get("fifa_neighbors"):
            story.append(Spacer(1, 0.3 * cm))
            story += _fifa_neighbors_pdf(archetype, styles)
        # Pro Calibration — gated to U12+ via apply_stage_gating()
        statsbomb_cal = report_doc.get("statsbomb_calibration")
        if statsbomb_cal:
            story.append(Spacer(1, 0.3 * cm))
            story += _statsbomb_calibration_pdf(statsbomb_cal, styles)

    story.append(PageBreak())

    # ===== TECHNICAL & TACTICAL — premium per-skill cards with benchmarks =====
    section_idx = 4 if ob.get("tier") else 3
    if "technical" in full:
        story += _nano_hero(f"Section {section_idx:02d}", "Technical analysis",
                            "Ball, dribbling, passing, shooting", "technical")
        story += _skill_section_block(full["technical"], styles)
        story.append(Spacer(1, 0.4 * cm))
        section_idx += 1

    if "tactical" in full:
        story.append(PageBreak())
        story += _nano_hero(f"Section {section_idx:02d}", "Tactical analysis",
                            "Scanning, decisions, positioning", "tactical")
        story += _skill_section_block(full["tactical"], styles)
        section_idx += 1

    story.append(PageBreak())

    # ===== PHYSICAL & MENTALITY =====
    if "physical" in full:
        story += _nano_hero(f"Section {section_idx:02d}", "Physical analysis",
                            "Speed, balance, agility, stamina", "physical")
        story += _skill_section_block(full["physical"], styles)
        story.append(Spacer(1, 0.4 * cm))
        section_idx += 1

    if "mentality" in full:
        story.append(PageBreak())
        story += _nano_hero(f"Section {section_idx:02d}", "Mentality analysis",
                            "Confidence, courage, focus, body language", "mentality")
        story += _skill_section_block(full["mentality"], styles)
        section_idx += 1

    story.append(PageBreak())

    # ===== EUROPEAN ACADEMY REFERENCE PROFILE — position priorities vs Pro Academy expectations =====
    ap = report_doc.get("age_profile_reference") or {}
    if ap and ap.get("items"):
        story += _section_header("European Academy reference profile", styles, idx=section_idx)
        section_idx += 1
        story += _age_profile_page(ap, styles)
        story.append(PageBreak())

    # ===== TRIAL READINESS — position-specific scout-style checklist =====
    tr = report_doc.get("trial_readiness") or {}
    if tr and tr.get("items"):
        story += _section_header("Trial readiness — what this player is ready for, today", styles, idx=section_idx)
        section_idx += 1
        story += _trial_readiness_page(tr, styles)
        story.append(PageBreak())

    # ===== SCOUT VIEW =====
    if "scout_view" in full:
        sv = full["scout_view"] or {}
        story += _section_header("Scout view — how a scout might assess this player", styles, idx=section_idx)
        section_idx += 1

        story.append(Paragraph("KEY STRENGTHS", styles["Label"]))
        story += _list_bullets(sv.get("key_strengths"), styles)
        story.append(Spacer(1, 0.35 * cm))

        story.append(Paragraph("AREAS OF CONCERN", styles["Label"]))
        story += _list_bullets(sv.get("areas_of_concern"), styles)
        story.append(Spacer(1, 0.35 * cm))

        story.append(Paragraph("DEVELOPMENT PRIORITIES", styles["Label"]))
        story += _list_bullets(sv.get("development_priorities"), styles)
        story.append(Spacer(1, 0.4 * cm))

        story.append(_kv_card([
            ("Next competitive level", sv.get("appropriate_next_level", "")),
            ("Positional suitability",   sv.get("positional_suitability", "")),
        ], styles))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(
            "<i>This is an independent development analysis and does not guarantee selection or advancement opportunities.</i>",
            styles["MutedW"],
        ))

    # ===== POTENTIAL =====
    if "potential_assessment" in full:
        pa = full["potential_assessment"] or {}
        story.append(PageBreak())
        story += _section_header("Potential assessment", styles, idx=section_idx)
        section_idx += 1
        story.append(_kv_card([
            ("Current level",            pa.get("current_level", "")),
            ("Development potential",    pa.get("development_potential", "")),
            ("Recommended next step",    pa.get("recommended_next_step", "")),
            ("3-month focus",            pa.get("three_month_focus", "")),
        ], styles))

    # ===== TRAINING PLAN =====
    if "training_plan" in full:
        tp = full["training_plan"] or {}
        story.append(PageBreak())
        story += _section_header("Personal training plan", styles, idx=section_idx)
        section_idx += 1

        story.append(Paragraph("FIVE FOCUSED EXERCISES", styles["Label"]))
        exercises = tp.get("exercises", []) or []
        if exercises:
            ex_rows = []
            for i, ex in enumerate(exercises, 1):
                # Numbered chip cell — a forest box with white digit (Table inside table)
                num_chip = Table(
                    [[Paragraph(
                        f'<font color="#FFFFFF" size="11"><b>{i:02d}</b></font>',
                        ParagraphStyle("_xn", fontName="Helvetica-Bold", fontSize=11, leading=13,
                                       textColor=HexColor("#FFFFFF"), alignment=TA_CENTER,
                                       spaceBefore=0, spaceAfter=0),
                    )]],
                    colWidths=[0.95 * cm], rowHeights=[0.95 * cm],
                )
                num_chip.setStyle(TableStyle([
                    ("BACKGROUND",    (0, 0), (-1, -1), _PDF_FOREST),
                    ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
                    ("TOPPADDING",    (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]))
                duration = ex.get('duration', '')
                duration_html = (
                    f'<font color="#1F4F2F" size="9"><b>&nbsp;·&nbsp;{duration}</b></font>'
                    if duration else ""
                )
                ex_rows.append([
                    num_chip,
                    Paragraph(
                        f'<font color="#0A0F0D" size="11"><b>{ex.get("name", "—")}</b></font>{duration_html}<br/>'
                        f'<font color="#4B5563" size="9.5">{ex.get("description", "")}</font>',
                        styles["BodyW"],
                    ),
                ])
            et = Table(ex_rows, colWidths=[1.4 * cm, 14.1 * cm])
            et.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), _PDF_CARD),
                ("LEFTPADDING",   (0, 0), (-1, -1), 12),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
                ("TOPPADDING",    (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ("VALIGN",        (0, 0), (0, -1),  "TOP"),
                ("VALIGN",        (1, 0), (1, -1),  "TOP"),
                ("LINEBELOW",     (0, 0), (-1, -1), 0.4, _PDF_BORDER),
            ]))
            story.append(et)
        else:
            story.append(Paragraph("<font color='#9CA3AF'>No exercises recorded.</font>", styles["BodyMuted"]))

        story.append(Spacer(1, 0.6 * cm))
        story.append(_kv_card([
            ("Weekly focus",       tp.get("weekly_focus", "")),
            ("30-day plan",        tp.get("thirty_day_plan", "")),
            ("90-day plan",        tp.get("ninety_day_plan", "")),
        ], styles))

    # ===== VIDEO MOMENTS — frame-stamped evidence with thumbnails =====
    if full.get("video_comments"):
        story.append(PageBreak())
        story += _section_header("Video moments — frame-stamped evidence", styles, idx=section_idx)
        section_idx += 1
        story.append(Paragraph(
            "<font color='#1F4F2F' size='7'><b>EVERY OBSERVATION IS ANCHORED TO THE EXACT FRAME IT WAS SEEN AT</b></font>",
            styles["BodyW"],
        ))
        story.append(Spacer(1, 0.3 * cm))
        vc_rows = []
        for c in full["video_comments"]:
            frame_cell = ""
            frame_url = c.get("frame_url") or ""
            if frame_url.startswith("/api/uploads/"):
                frame_path = UPLOAD_DIR / frame_url[len("/api/uploads/"):]
                if frame_path.exists():
                    try:
                        frame_cell = RLImage(str(frame_path), width=4.5 * cm, height=2.5 * cm, kind="proportional")
                    except Exception:
                        frame_cell = ""
            if not frame_cell:
                frame_cell = Paragraph(
                    "<font color='#9CA3AF' size='8'><i>frame unavailable</i></font>",
                    styles["BodyW"],
                )
            text_cell = Paragraph(
                f"<font color='#1F4F2F' size='13'><b>{c.get('timestamp', '')}</b></font><br/>"
                f"<font color='#0A0F0D' size='10'>{c.get('comment', '')}</font>",
                styles["BodyW"],
            )
            vc_rows.append([frame_cell, text_cell])
        vct = Table(vc_rows, colWidths=[5.0 * cm, 10.5 * cm])
        vct.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), _PDF_CARD),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("VALIGN",        (1, 0), (1, -1), "TOP"),
            ("LINEBELOW",     (0, 0), (-1, -1), 0.4, _PDF_BORDER),
            ("LINEBEFORE",    (0, 0), (0, -1),  2.0, _PDF_FOREST),
        ]))
        story.append(vct)

    # ===== FINAL SUMMARY =====
    story.append(PageBreak())
    story += _section_header("Final summary", styles, idx=section_idx)
    story.append(Paragraph(full.get("final_summary", "Not provided."), styles["BodyW"]))
    story.append(Spacer(1, 0.6 * cm))

    # Sign-off card
    signoff = Table([[
        Paragraph(
            "<b>Issued by</b><br/>"
            "SCOUTMEPLAY · MENTALKIDS<br/>"
            "Denmark · scoutmeplay@gmail.com",
            styles["BodyMuted"],
        ),
        Paragraph(
            f"<b>Report ID</b><br/>"
            f"{report_doc.get('id', '—')}<br/>"
            f"Generated {datetime.now(timezone.utc).strftime('%d %B %Y')}",
            styles["BodyMuted"],
        ),
    ]], colWidths=[7.7 * cm, 7.8 * cm])
    signoff.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _PDF_CARD),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LINEBEFORE",    (0, 0), (0, -1),  2.0, _PDF_FOREST),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.4, _PDF_BORDER),
    ]))
    story.append(signoff)
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(
        "<i>Scores are presented as developmental guidance based on the submitted video, not definitive scouting evaluations. "
        "ScoutMePlay provides independent feedback only. We do not represent players or contact clubs on your behalf.</i>",
        styles["MutedW"],
    ))

    # ===== METHODOLOGY APPENDIX (always last) =====
    story.append(PageBreak())
    story += _methodology_appendix(styles)

    doc.build(story)


def _methodology_appendix(styles):
    """Final page of every PDF — explains how the report is scored so any
    coach receiving it can verify the framework. Strictly defensible language
    (UEFA-aligned, never UEFA-certified)."""
    flow = []
    flow += _section_header("How ScoutMePlay scores — methodology", styles, idx=None)
    flow.append(Paragraph(
        "Every report is built around the same four player-development pillars used across European Category-1 "
        "youth academies. This appendix explains how we evaluate, benchmark, and tier players — so any coach or "
        "scout receiving this PDF can understand the numbers.",
        styles["BodyW"],
    ))
    flow.append(Spacer(1, 0.25 * cm))
    flow.append(Paragraph(
        "<font color='#9CA3AF' size='7'><b>ALIGNED WITH UEFA YOUTH-DEVELOPMENT PILLARS · "
        "NOT CERTIFIED OR ENDORSED BY UEFA</b></font>",
        styles["BodyW"],
    ))
    flow.append(Spacer(1, 0.5 * cm))

    # --- Pillars ---
    flow.append(Paragraph("THE FOUR PILLARS", styles["Label"]))
    pillars_rows = [
        ("Technical",  "Skills with the ball — first touch, ball control, passing, dribbling, shooting, weak-foot use, 1v1."),
        ("Tactical",   "Decisions without the ball — positioning, off-ball movement, scanning, decision-making, timing of runs, game understanding."),
        ("Physical",   "Athletic foundation — acceleration, speed, balance, agility, intensity (90-minute), body control."),
        ("Mental",     "Habits and character — confidence, work rate, courage in duels, response to mistakes, competitive mindset, focus."),
    ]
    flow.append(_two_col_card_table(pillars_rows, styles))
    flow.append(Spacer(1, 0.45 * cm))

    # --- Tier ladder ---
    flow.append(Paragraph("THE FOUR-TIER LADDER", styles["Label"]))
    flow.append(Paragraph(
        "Each sub-skill is scored 1-10 and placed into one of four tiers, calibrated to the player's age and position.",
        styles["BodyW"],
    ))
    flow.append(Spacer(1, 0.15 * cm))
    tiers = [
        ("Elite Academy",  "Top-end Category-1 academies (La Masia, Clairefontaine, Cobham-level). Top 1-3% of an age group."),
        ("Pro Academy",    "Strong regional or national pro-club academies. Trial-ready for serious competitive pathways. Top 10-15%."),
        ("Strong Club",    "Higher-level competitive club football, talent centres, district selections. Top 30%."),
        ("Standard Club",  "Mainstream club football where most players develop. Baseline for organised youth football."),
    ]
    flow.append(_two_col_card_table(tiers, styles))
    flow.append(Spacer(1, 0.45 * cm))

    # --- Age brackets ---
    flow.append(Paragraph("AGE BRACKETS", styles["Label"]))
    flow.append(Paragraph(
        "A 7/10 for first touch at U11 is not the same as a 7/10 at U17. Every score is calibrated against the typical "
        "milestone for the age bracket and position.",
        styles["BodyW"],
    ))
    flow.append(Spacer(1, 0.15 * cm))
    ages = [
        ("U11",  "Foundation — coordination, ball mastery, basic decision-making."),
        ("U13",  "Build phase — scanning habits, positional discipline, both-footed development."),
        ("U15",  "Performance phase — match impact, pressing intensity, tactical role clarity."),
        ("U17",  "Specialisation — position-specific excellence, physical maturity, mental resilience."),
        ("U19",  "Pre-professional — match management, leadership, consistency across 90 minutes."),
        ("U21",  "Professional threshold — high-performance habits, durability, decision quality at speed."),
    ]
    flow.append(_two_col_card_table(ages, styles))
    flow.append(Spacer(1, 0.45 * cm))

    # --- What we don't claim ---
    flow.append(Paragraph("WHAT WE DON'T CLAIM", styles["Label"]))
    for item in [
        "We are not UEFA-certified. We align with the same pillars used in UEFA elite-youth coaching education — that's it.",
        "We don't publish childhood scores of professional players. Stylistic archetype comparisons describe style, not factual youth data.",
        "We don't guarantee selection, signing, or progression to any club or academy.",
        "Set-pieces from open play, off-camera defensive work, and goalkeeping moments are not assessable from outfield clips.",
    ]:
        flow.append(Paragraph(
            f"<font color='#1F4F2F'><b>·</b></font>&nbsp;&nbsp;<font color='#0A0F0D' size='9.5'>{item}</font>",
            styles["BodyW"],
        ))
        flow.append(Spacer(1, 0.1 * cm))

    flow.append(Spacer(1, 0.4 * cm))
    flow.append(Paragraph(
        "<i><font color='#9CA3AF' size='8'>Methodology version 1.0 — last updated Feb 2026.</font></i>",
        styles["BodyW"],
    ))
    return flow


def _two_col_card_table(rows, styles):
    """Helper for the methodology appendix — left column is a bold label,
    right column is a body paragraph. Cards alternate background subtly."""
    data = []
    for label, body in rows:
        data.append([
            Paragraph(f"<font color='#1F4F2F' size='10'><b>{label.upper()}</b></font>", styles["BodyW"]),
            Paragraph(f"<font color='#0A0F0D' size='9.5'>{body}</font>", styles["BodyW"]),
        ])
    t = Table(data, colWidths=[4.5 * cm, 11.0 * cm])
    style = [
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("BACKGROUND",    (0, 0), (-1, -1), _PDF_CARD),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, _PDF_BORDER),
        ("LINEBEFORE",    (0, 0), (0, -1),  2.0, _PDF_FOREST),
    ]
    t.setStyle(TableStyle(style))
    return t


@api_router.get("/reports/{report_id}/pdf")
async def download_pdf(report_id: str, user=Depends(get_current_user)):
    doc = await db.reports.find_one({"id": report_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")
    if doc["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    unlocked = doc.get("is_paid") or doc.get("manually_unlocked") or user["role"] == "admin"
    if not unlocked:
        raise HTTPException(status_code=402, detail="Payment required")
    if not doc.get("full_report"):
        raise HTTPException(status_code=400, detail="Full report not generated yet")

    pdf_path = _pdf_cache_path(report_id)
    if not pdf_path.exists():
        _purge_stale_pdfs(report_id)
        # Compute deterministic enrichment so PDF == web report.
        doc["trial_readiness"] = compute_trial_readiness(
            doc.get("full_report") or {},
            doc.get("player_details") or {},
        )
        doc["archetype"] = match_archetype(
            doc.get("full_report") or {},
            doc.get("player_details") or {},
        )
        # Attach the cached narrative (if any) so the PDF mirrors the web report
        if isinstance(doc.get("archetype"), dict) and doc.get("archetype_narrative"):
            if doc.get("archetype_narrative_archetype_id") == doc["archetype"].get("id"):
                doc["archetype"]["narrative"] = doc["archetype_narrative"]
        doc["age_profile_reference"] = compute_age_profile_reference(
            doc.get("full_report") or {},
            doc.get("player_details") or {},
        )
        # Step 2 — StatsBomb calibration for the PDF mirror
        doc["statsbomb_calibration"] = compute_statsbomb_calibration(
            doc.get("full_report") or {},
            doc.get("player_details") or {},
        )
        # Age Intelligence — drives stage-gated rendering in the PDF too
        age_intel = compute_age_intelligence(
            doc.get("full_report") or {},
            doc.get("player_details") or {},
        )
        if age_intel:
            apply_stage_gating(doc, age_intel)
            doc["age_intelligence"] = age_intel
        # Extract / placeholder frames so the PDF can embed them too.
        enriched_comments = ensure_video_frames(doc)
        if enriched_comments and isinstance(doc.get("full_report"), dict):
            doc["full_report"] = {**doc["full_report"], "video_comments": enriched_comments}
        build_pdf(doc, str(pdf_path))

    player_name_safe = re.sub(r"[^A-Za-z0-9_-]", "_", doc["player_details"]["player_name"])
    filename = f"EliteScout_{player_name_safe}_Report.pdf"
    return FileResponse(str(pdf_path), media_type="application/pdf", filename=filename)


# Cached path of the public sample PDF (built once on first hit).
_SAMPLE_PDF_PATH = Path(__file__).resolve().parent / "uploads" / "scoutmeplay_sample_report.pdf"
_SAMPLE_REPORT_ID_HINT_KEY = "sample_demo_report_id"


async def _resolve_sample_report() -> dict | None:
    """Return a fully-unlocked demo report doc suitable for the public sample PDF.

    Strategy: prefer an admin-pinned doc id stored in settings; otherwise pick the
    most recent paid report belonging to the seeded premium demo user (Lukas A.).
    """
    pinned = await db.settings.find_one({"_id": _SAMPLE_REPORT_ID_HINT_KEY})
    if pinned and pinned.get("report_id"):
        doc = await db.reports.find_one({"id": pinned["report_id"]})
        if doc and doc.get("full_report"):
            return doc
    # Fallback — most recent paid report with a full_report payload (avoid empties)
    doc = await db.reports.find_one(
        {"is_paid": True, "full_report": {"$exists": True, "$ne": None}},
        sort=[("created_at", -1)],
    )
    return doc


@api_router.get("/sample/scoutmeplay-report.pdf")
async def download_public_sample_pdf():
    """Public, no-auth endpoint that streams a curated sample premium PDF.

    Used by the landing page's "Download sample PDF" button to give prospects an
    honest preview of what the full premium report looks like before paying.
    Cached on disk; rebuilds when the source report is updated.
    """
    doc = await _resolve_sample_report()
    if not doc:
        raise HTTPException(status_code=404, detail="Sample report not available yet")
    src_id = doc["id"]

    # Use the same per-report PDF cache that the authenticated download uses, so
    # admin tweaks propagate. Then expose it under a public filename.
    pdf_path = _pdf_cache_path(src_id)
    if not pdf_path.exists():
        _purge_stale_pdfs(src_id)
        doc["trial_readiness"] = compute_trial_readiness(
            doc.get("full_report") or {},
            doc.get("player_details") or {},
        )
        doc["archetype"] = match_archetype(
            doc.get("full_report") or {},
            doc.get("player_details") or {},
        )
        if isinstance(doc.get("archetype"), dict) and doc.get("archetype_narrative"):
            if doc.get("archetype_narrative_archetype_id") == doc["archetype"].get("id"):
                doc["archetype"]["narrative"] = doc["archetype_narrative"]
        doc["age_profile_reference"] = compute_age_profile_reference(
            doc.get("full_report") or {},
            doc.get("player_details") or {},
        )
        doc["statsbomb_calibration"] = compute_statsbomb_calibration(
            doc.get("full_report") or {},
            doc.get("player_details") or {},
        )
        age_intel = compute_age_intelligence(
            doc.get("full_report") or {},
            doc.get("player_details") or {},
        )
        if age_intel:
            apply_stage_gating(doc, age_intel)
            doc["age_intelligence"] = age_intel
        enriched_comments = ensure_video_frames(doc)
        if enriched_comments and isinstance(doc.get("full_report"), dict):
            doc["full_report"] = {**doc["full_report"], "video_comments": enriched_comments}
        build_pdf(doc, str(pdf_path))

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename="ScoutMePlay_Sample_Report.pdf",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ============== PAYMENTS (STRIPE) ==============

# ---- Subscription helpers (recurring billing) ---------------------------
#
# Subscriptions use the raw Stripe SDK (mode="subscription") because
# emergentintegrations.StripeCheckout only models one-time payments.
# Product + Price objects are created idempotently on backend startup;
# the resulting Stripe IDs are cached in `db.settings` keyed by
# `stripe_subscription_<tier>` so we never duplicate products on
# subsequent restarts.

async def _ensure_subscription_products():
    """At-startup: create (once) a Stripe Product + recurring monthly Price
    for each tier in SUBSCRIPTION_TIERS. Stores the resulting price_id in
    `db.settings` so subsequent boots are a no-op. Safe to call on every boot.
    No-ops if Stripe keys are missing — the subscribe endpoint will fail
    cleanly in that case with a 503."""
    if not _embedded_ready():
        logger.warning("Stripe live keys missing — subscription products NOT created. Add STRIPE_SECRET_KEY + STRIPE_PUBLISHABLE_KEY.")
        return

    _arm_real_stripe()
    for tier_id, conf in SUBSCRIPTION_TIERS.items():
        settings_key = f"stripe_subscription_{tier_id}"
        existing = await db.settings.find_one({"key": settings_key}, {"_id": 0})
        if existing and existing.get("value", {}).get("price_id"):
            continue  # already provisioned

        try:
            product = stripe_sdk.Product.create(
                name=conf["name"],
                description=conf["description"],
                metadata={
                    **_SCOUTMEPLAY_METADATA,
                    "tier": tier_id,
                    "tier_kind": "subscription",
                },
            )
            price = stripe_sdk.Price.create(
                unit_amount=int(round(conf["amount"] * 100)),
                currency=PRICE_CURRENCY,
                recurring={"interval": "month"},
                product=product.id,
                metadata={"tier": tier_id},
            )
        except Exception:
            logger.exception(f"Failed to provision Stripe product+price for tier '{tier_id}'")
            continue

        await db.settings.update_one(
            {"key": settings_key},
            {"$set": {
                "key": settings_key,
                "value": {
                    "product_id": product.id,
                    "price_id": price.id,
                    "amount": conf["amount"],
                    "currency": PRICE_CURRENCY,
                },
                "updated_at": now_iso(),
            }},
            upsert=True,
        )
        logger.info(f"Stripe provisioned tier '{tier_id}' → product {product.id} / price {price.id} (${conf['amount']}/mo)")


async def _get_subscription_price_id(tier: str) -> Optional[str]:
    doc = await db.settings.find_one({"key": f"stripe_subscription_{tier}"}, {"_id": 0})
    return ((doc or {}).get("value") or {}).get("price_id")


# ─── SCOUT ACCESS: idempotent Stripe product provisioning + helpers ───

async def _ensure_scout_access_products():
    """Mirrors `_ensure_subscription_products` but for the SCOUT ACCESS tiers.
    Fase 2 update — creates a Stripe Product + ONE-TIME Price for scout / club,
    cached under settings key `stripe_scout_access_<tier>`. Not recurring.
    """
    if not _embedded_ready():
        return
    _arm_real_stripe()
    # Clean out any legacy tier settings from the retired monthly model so the
    # new one-time tiers don't accidentally return an old subscription price_id.
    await db.settings.delete_many({"key": {"$in": [
        "stripe_scout_access_scout_basic",
        "stripe_scout_access_scout_pro",
        "stripe_scout_access_club_enterprise",
    ]}})

    for tier_id, conf in SCOUT_ACCESS_TIERS.items():
        settings_key = f"stripe_scout_access_{tier_id}"
        existing = await db.settings.find_one({"key": settings_key}, {"_id": 0})
        if existing and existing.get("value", {}).get("price_id"):
            continue
        try:
            product = stripe_sdk.Product.create(
                name=conf["name"],
                description=conf["description"],
                metadata={
                    **_SCOUTMEPLAY_METADATA,
                    "tier": tier_id,
                    "tier_kind": "scout_access",
                    "billing": "one_time",
                },
            )
            price = stripe_sdk.Price.create(
                unit_amount=int(round(conf["amount"] * 100)),
                currency=PRICE_CURRENCY,
                product=product.id,
                metadata={"tier": tier_id, "kind": "scout_access"},
            )
        except Exception:
            logger.exception(f"Failed to provision Stripe scout-access product+price for '{tier_id}'")
            continue

        await db.settings.update_one(
            {"key": settings_key},
            {"$set": {
                "key": settings_key,
                "value": {
                    "product_id": product.id,
                    "price_id": price.id,
                    "amount": conf["amount"],
                    "currency": PRICE_CURRENCY,
                    "one_time": True,
                },
                "updated_at": now_iso(),
            }},
            upsert=True,
        )
        logger.info(f"Stripe provisioned scout-access tier '{tier_id}' → {price.id} (${conf['amount']} lifetime)")


async def _get_scout_access_price_id(tier: str) -> Optional[str]:
    doc = await db.settings.find_one({"key": f"stripe_scout_access_{tier}"}, {"_id": 0})
    return ((doc or {}).get("value") or {}).get("price_id")


def _has_active_scout_access(user: dict) -> Optional[dict]:
    """Returns the active scout_access dict if the user has paid scout access,
    otherwise None. Fase 2 update — access is now LIFETIME (one-time payment),
    so we only reject if status is explicitly 'revoked' by admin."""
    sa = user.get("scout_access") or {}
    if sa.get("status") != "active":
        return None
    # Legacy monthly subs still respect period_end. New one-time purchases
    # (marked one_time=True) never expire.
    if sa.get("one_time"):
        return sa
    period_end = sa.get("current_period_end")
    if period_end:
        try:
            if isinstance(period_end, (int, float)):
                exp = datetime.fromtimestamp(period_end, tz=timezone.utc)
            else:
                exp = datetime.fromisoformat(str(period_end).replace("Z", "+00:00"))
            if exp < datetime.now(timezone.utc):
                return None
        except Exception:
            pass
    return sa


async def _require_scout_access(user=Depends(get_current_user)) -> dict:
    """Dependency — 402 Payment Required if the caller has no active scout access."""
    if user.get("role") == "admin":
        return user  # admins bypass the paywall for testing/moderation
    sa = _has_active_scout_access(user)
    if not sa:
        raise HTTPException(
            status_code=402,
            detail="Scout access subscription required. Subscribe at /scouts to browse the player database.",
        )
    return user


def _subscription_state_from_stripe(sub) -> Dict[str, Any]:
    """Translate a Stripe Subscription object into the shape we persist on `users.subscription`.
    Accepts either a SDK object or a webhook event dict."""
    def g(k, default=None):
        return sub.get(k, default) if isinstance(sub, dict) else getattr(sub, k, default)
    items = g("items") or {}
    items_data = (items.get("data") if isinstance(items, dict) else getattr(items, "data", None)) or []
    first_item = items_data[0] if items_data else None
    price_obj = (first_item.get("price") if isinstance(first_item, dict) else getattr(first_item, "price", None)) if first_item else None
    price_id = (price_obj.get("id") if isinstance(price_obj, dict) else getattr(price_obj, "id", None)) if price_obj else None
    md = g("metadata") or {}
    tier = (md.get("tier") if isinstance(md, dict) else getattr(md, "tier", None))

    def _ts_to_iso(ts):
        if not ts:
            return None
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
        except Exception:
            return None

    return {
        "tier": tier,
        "status": g("status"),
        "stripe_customer_id": g("customer"),
        "stripe_subscription_id": g("id"),
        "stripe_price_id": price_id,
        "current_period_end": _ts_to_iso(g("current_period_end")),
        "current_period_start": _ts_to_iso(g("current_period_start")),
        "cancel_at_period_end": bool(g("cancel_at_period_end")),
        "canceled_at": _ts_to_iso(g("canceled_at")),
        "ended_at": _ts_to_iso(g("ended_at")),
        "updated_at": now_iso(),
    }


def _has_active_subscription(user: dict) -> Optional[str]:
    """Return the active subscription tier ('premium'/'vip') if the user has one, else None."""
    sub = (user or {}).get("subscription") or {}
    sub_status = sub.get("status")
    if sub_status in ("active", "trialing", "past_due"):  # past_due still gives access — Stripe retries before downgrading
        return sub.get("tier")
    return None


@api_router.get("/me/upload-eligibility")
async def get_upload_eligibility(user=Depends(get_current_user)):
    """Tells the frontend whether the user can upload for free, must pre-pay, or is admin.

    Subscription tiers (Premium / VIP) take precedence over prepaid credits —
    if a user has both an active subscription AND prepaid uploads, the
    subscription is used first so they preserve their one-off credits."""
    if user.get("role") == "admin":
        return {"eligible": True, "reason": "admin", "free_preview_used": True, "prepaid_uploads": 999,
                "progress_pass": {"active": False, "credits_remaining": 0}, "subscription": None}

    # Subscription check (Premium / VIP)
    sub_tier = _has_active_subscription(user)
    if sub_tier:
        tier_conf = SUBSCRIPTION_TIERS.get(sub_tier, {})
        limit = tier_conf.get("monthly_upload_limit")  # None = unlimited
        # Count how many uploads in the current billing period
        period_start = (user.get("subscription") or {}).get("current_period_start") or now_iso()
        used = await db.reports.count_documents({
            "user_id": user["id"],
            "created_at": {"$gte": period_start},
        })
        remaining = None if limit is None else max(0, limit - used)
        if limit is None or remaining > 0:
            return {
                "eligible": True,
                "reason": "subscription",
                "free_preview_used": bool(user.get("free_preview_used")),
                "prepaid_uploads": int(user.get("prepaid_uploads", 0) or 0),
                "progress_pass": _progress_pass_active(user),
                "subscription": {"tier": sub_tier, "monthly_limit": limit, "used_this_period": used, "remaining": remaining},
            }
        # Subscription exhausted for this billing cycle — fall through to other reasons (prepaid/free still ok)

    free_used = bool(user.get("free_preview_used"))
    prepaid = int(user.get("prepaid_uploads", 0) or 0)
    pass_state = _progress_pass_active(user)
    subscription_block = None
    # Every branch below benefits from knowing the price of one extra report
    # for the current user — the dashboard uses it for the "buy 1 extra report"
    # button when the user's monthly quota is exhausted.
    extra_price, extra_tier = await get_extra_report_price_for_user(user)
    if sub_tier:
        # Communicate the cap so the frontend can show "2/2 used — resets at <date>"
        tier_conf = SUBSCRIPTION_TIERS.get(sub_tier, {})
        subscription_block = {
            "tier": sub_tier,
            "monthly_limit": tier_conf.get("monthly_upload_limit"),
            "remaining": 0,
            "exhausted": True,
            "extra_report_price": extra_price,
            "extra_report_price_tier": extra_tier,
        }
    if not free_used:
        return {"eligible": True, "reason": "free_preview", "free_preview_used": False,
                "prepaid_uploads": prepaid, "progress_pass": pass_state, "subscription": subscription_block,
                "extra_report_price": extra_price, "extra_report_price_tier": extra_tier}
    if prepaid > 0:
        return {"eligible": True, "reason": "prepaid", "free_preview_used": True,
                "prepaid_uploads": prepaid, "progress_pass": pass_state, "subscription": subscription_block,
                "extra_report_price": extra_price, "extra_report_price_tier": extra_tier}
    if pass_state.get("active"):
        return {"eligible": True, "reason": "progress_pass", "free_preview_used": True,
                "prepaid_uploads": 0, "progress_pass": pass_state, "subscription": subscription_block,
                "extra_report_price": extra_price, "extra_report_price_tier": extra_tier}
    return {"eligible": False, "reason": "prepay_required", "free_preview_used": True,
            "prepaid_uploads": 0, "progress_pass": pass_state, "subscription": subscription_block,
            "extra_report_price": extra_price, "extra_report_price_tier": extra_tier}


@api_router.post("/payments/prepay-upload")
async def create_prepay_upload_checkout(payload: PrepayUploadInit, request: Request, user=Depends(get_current_user)):
    """Stripe checkout for a single per-report purchase. On success, +1 prepaid_uploads
    (which the buyer redeems to unlock one full premium scout report).

    Price source depends on the buyer's subscription tier:
      - Free / no subscription  → `single_price`  (default $129)
      - Premium subscriber      → `premium_extra_report_price` (default $89)
      - VIP subscriber          → `vip_extra_report_price` (default $59)

    All three amounts are admin-editable via PUT /api/admin/pricing, so
    subscribers always see the discount that matches the amount shown on
    their dashboard's "buy extra report" button.
    """
    price, price_tier = await get_extra_report_price_for_user(user)

    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)

    origin = payload.origin_url.rstrip("/")
    success_url = f"{origin}/upload?prepay_session={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/upload?prepay_canceled=1"

    metadata = {
        "kind": "prepay_upload",
        "user_id": user["id"],
        "user_email": user["email"],
        "price_tier": price_tier,  # "single" | "premium" | "vip" — which discount was applied
        # Brand attribution — keeps ScoutMePlay separate from 1MillionBolde in the shared Stripe account
        "brand": "ScoutMePlay",
        "company": "Mentalkids",
        "website": "ScoutMePlay",
        "source": "scoutmeplay_website",
        "niche": "football_scouting_video_analysis",
        "product": "ScoutMePlay – Football Video Analysis",
    }

    session_req = CheckoutSessionRequest(
        amount=float(price),
        currency=PRICE_CURRENCY,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata=metadata,
    )
    session = await stripe_checkout.create_checkout_session(session_req)

    txn = {
        "id": str(uuid.uuid4()),
        "session_id": session.session_id,
        "user_id": user["id"],
        "user_email": user["email"],
        "report_id": None,
        "kind": "prepay_upload",
        "brand": "ScoutMePlay",
        "amount": float(price),
        "currency": PRICE_CURRENCY,
        "metadata": metadata,
        "payment_status": "initiated",
        "status": "open",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.payment_transactions.insert_one(txn)

    return {"url": session.url, "session_id": session.session_id}


# ============== SUBSCRIPTIONS (Premium / VIP) ==============

@api_router.post("/payments/subscribe")
async def create_subscription_checkout(payload: SubscribeInit, user=Depends(get_current_user)):
    """Create a Stripe Checkout Session in `mode=subscription` for the chosen tier.

    Only the tier id ('premium'|'vip') is accepted from the client — the price
    is looked up from Stripe via the cached price_id, preventing client-side
    price manipulation. Redirects through the hosted Stripe Checkout page.
    """
    tier = (payload.tier or "").lower().strip()
    if tier not in SUBSCRIPTION_TIERS:
        raise HTTPException(400, "Unknown subscription tier")
    if not _embedded_ready():
        raise HTTPException(503, "Subscription checkout not configured. Add Stripe live keys to enable.")
    if _has_active_subscription(user):
        raise HTTPException(409, "You already have an active subscription. Use the dashboard to change tier instead.")

    price_id = await _get_subscription_price_id(tier)
    if not price_id:
        # Lazy-provision in case the startup hook hadn't completed yet
        await _ensure_subscription_products()
        price_id = await _get_subscription_price_id(tier)
        if not price_id:
            raise HTTPException(503, f"Stripe price for tier '{tier}' is not provisioned yet — try again in a moment.")

    origin = payload.origin_url.rstrip("/")
    success_url = f"{origin}/dashboard?subscribe_session={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/?subscribe_canceled=1"

    metadata = _build_embedded_metadata({
        "kind": "subscription",
        "tier": tier,
        "user_id": user["id"],
        "user_email": user["email"],
    })

    try:
        _arm_real_stripe()
        # Reuse the user's existing Stripe customer if they have one (so all
        # their invoices live under one customer in the Stripe dashboard).
        existing_sub = (user.get("subscription") or {})
        customer_id = existing_sub.get("stripe_customer_id")
        session_kwargs = dict(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata,
            subscription_data={"metadata": metadata},
            allow_promotion_codes=True,
        )
        if customer_id:
            session_kwargs["customer"] = customer_id
        else:
            session_kwargs["customer_email"] = user["email"]
        session = stripe_sdk.checkout.Session.create(**session_kwargs)
    except Exception as e:
        logger.exception("Stripe subscription session create failed")
        raise HTTPException(500, f"Stripe error: {e}")

    await db.payment_transactions.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session.id,
        "user_id": user["id"],
        "user_email": user["email"],
        "report_id": None,
        "kind": "subscription",
        "tier": tier,
        "ui_mode": "hosted",
        "brand": "ScoutMePlay",
        "amount": SUBSCRIPTION_TIERS[tier]["amount"],
        "currency": PRICE_CURRENCY,
        "metadata": metadata,
        "payment_status": "initiated",
        "status": "open",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })

    return {"url": session.url, "session_id": session.id}


@api_router.get("/payments/subscribe/status/{session_id}")
async def get_subscription_status(session_id: str, user=Depends(get_current_user)):
    """Poll endpoint — frontend calls this after Stripe redirects back. Verifies
    the checkout session is paid and copies the subscription state to `users.subscription`.
    Idempotent: side-effects only fire once per session via `txn.credited`."""
    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not txn:
        raise HTTPException(404, "Subscription session not found")
    if txn["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(403, "Not authorized")

    if txn.get("payment_status") == "paid" and txn.get("credited"):
        # Re-fetch user to return current subscription state
        u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
        return {"payment_status": "paid", "status": "complete", "kind": "subscription",
                "tier": txn.get("tier"), "subscription": (u or {}).get("subscription")}

    if not _embedded_ready():
        raise HTTPException(503, "Stripe not configured.")

    try:
        _arm_real_stripe()
        session = stripe_sdk.checkout.Session.retrieve(session_id, expand=["subscription"])
    except Exception as e:
        logger.exception("Stripe subscription status retrieve failed")
        raise HTTPException(500, f"Stripe error: {e}")

    new_payment_status = session.payment_status or "unpaid"
    new_status = session.status or "open"

    update = {"payment_status": new_payment_status, "status": new_status, "updated_at": now_iso()}
    if new_payment_status == "paid" and not txn.get("credited") and session.subscription:
        # Persist the subscription state onto the user record (single source of truth)
        sub_state = _subscription_state_from_stripe(session.subscription)
        # Tier from session metadata is authoritative (Stripe Price metadata may not be expanded)
        sub_state["tier"] = txn.get("tier") or sub_state.get("tier")
        sub_state["started_at"] = now_iso()
        await db.users.update_one(
            {"id": txn["user_id"]},
            {"$set": {"subscription": sub_state}},
        )
        update["credited"] = True

    await db.payment_transactions.update_one({"session_id": session_id}, {"$set": update})

    u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
    return {
        "payment_status": new_payment_status,
        "status": new_status,
        "kind": "subscription",
        "tier": txn.get("tier"),
        "subscription": (u or {}).get("subscription"),
    }


@api_router.get("/me/subscription")
async def get_my_subscription(user=Depends(get_current_user)):
    """Return the user's current subscription block (or null if none), plus a
    `usage` object that tells the frontend how many uploads have been consumed
    in the current billing period. This drives the dashboard's Premium-at-
    limit upgrade UI (show only VIP once Premium's 5/5 is used).
    """
    sub = user.get("subscription") or None
    usage = None
    sub_tier = _has_active_subscription(user)
    if sub_tier:
        tier_conf = SUBSCRIPTION_TIERS.get(sub_tier, {})
        limit = tier_conf.get("monthly_upload_limit")  # None = unlimited
        period_start = (user.get("subscription") or {}).get("current_period_start") or now_iso()
        used = await db.reports.count_documents({
            "user_id": user["id"],
            "created_at": {"$gte": period_start},
        })
        remaining = None if limit is None else max(0, limit - used)
        usage = {
            "used_this_period": used,
            "monthly_limit": limit,
            "remaining": remaining,
            "exhausted": (limit is not None and used >= limit),
        }
    return {"subscription": sub, "tiers": SUBSCRIPTION_TIERS, "usage": usage}


@api_router.post("/me/subscription/cancel")
async def cancel_my_subscription(user=Depends(get_current_user)):
    """Self-serve cancel — sets `cancel_at_period_end=True` so the user keeps access
    until the end of their paid period. Stripe webhook will mark it `canceled` when
    the period ends."""
    sub = user.get("subscription") or {}
    sub_id = sub.get("stripe_subscription_id")
    if not sub_id or sub.get("status") not in ("active", "trialing", "past_due"):
        raise HTTPException(400, "No active subscription to cancel")
    if sub.get("cancel_at_period_end"):
        raise HTTPException(400, "Subscription already scheduled for cancellation")
    if not _embedded_ready():
        raise HTTPException(503, "Stripe not configured")

    try:
        _arm_real_stripe()
        updated = stripe_sdk.Subscription.modify(sub_id, cancel_at_period_end=True)
    except Exception as e:
        logger.exception("Stripe subscription cancel failed")
        raise HTTPException(500, f"Stripe error: {e}")

    state = {**sub, **_subscription_state_from_stripe(updated)}
    state["tier"] = sub.get("tier")  # preserve canonical tier (metadata may be empty after modify)
    await db.users.update_one({"id": user["id"]}, {"$set": {"subscription": state}})
    return {"subscription": state}


@api_router.post("/me/subscription/resume")
async def resume_my_subscription(user=Depends(get_current_user)):
    """Un-cancel — clears `cancel_at_period_end` so billing continues."""
    sub = user.get("subscription") or {}
    sub_id = sub.get("stripe_subscription_id")
    if not sub_id or not sub.get("cancel_at_period_end"):
        raise HTTPException(400, "Subscription is not scheduled for cancellation")
    if not _embedded_ready():
        raise HTTPException(503, "Stripe not configured")

    try:
        _arm_real_stripe()
        updated = stripe_sdk.Subscription.modify(sub_id, cancel_at_period_end=False)
    except Exception as e:
        logger.exception("Stripe subscription resume failed")
        raise HTTPException(500, f"Stripe error: {e}")

    state = {**sub, **_subscription_state_from_stripe(updated)}
    state["tier"] = sub.get("tier")
    await db.users.update_one({"id": user["id"]}, {"$set": {"subscription": state}})
    return {"subscription": state}


@api_router.post("/me/subscription/change-tier")
async def change_subscription_tier(payload: SubscribeInit, user=Depends(get_current_user)):
    """Self-serve upgrade/downgrade between Premium ↔ VIP with proration.
    Re-uses the SubscribeInit schema but only the `tier` field is read."""
    new_tier = (payload.tier or "").lower().strip()
    if new_tier not in SUBSCRIPTION_TIERS:
        raise HTTPException(400, "Unknown subscription tier")
    sub = user.get("subscription") or {}
    sub_id = sub.get("stripe_subscription_id")
    if not sub_id or sub.get("status") not in ("active", "trialing", "past_due"):
        raise HTTPException(400, "No active subscription to change. Subscribe first.")
    if sub.get("tier") == new_tier:
        raise HTTPException(400, f"You are already on the {new_tier} plan")
    if not _embedded_ready():
        raise HTTPException(503, "Stripe not configured")

    new_price = await _get_subscription_price_id(new_tier)
    if not new_price:
        raise HTTPException(503, f"Stripe price for '{new_tier}' not provisioned yet")

    try:
        _arm_real_stripe()
        live = stripe_sdk.Subscription.retrieve(sub_id)
        item_id = live["items"]["data"][0]["id"]
        updated = stripe_sdk.Subscription.modify(
            sub_id,
            items=[{"id": item_id, "price": new_price}],
            proration_behavior="create_prorations",
            metadata={**(sub.get("metadata") or {}), "tier": new_tier},
        )
    except Exception as e:
        logger.exception("Stripe subscription change-tier failed")
        raise HTTPException(500, f"Stripe error: {e}")

    state = {**sub, **_subscription_state_from_stripe(updated)}
    state["tier"] = new_tier
    state["changed_at"] = now_iso()
    await db.users.update_one({"id": user["id"]}, {"$set": {"subscription": state}})
    return {"subscription": state}


# ============== PAYMENTS (legacy one-time) ==============


@api_router.post("/payments/checkout")
async def create_checkout(payload: CheckoutInit, request: Request, user=Depends(get_current_user)):
    report = await db.reports.find_one({"id": payload.report_id})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    if report.get("is_paid"):
        raise HTTPException(status_code=400, detail="Report already paid")

    price = await get_current_price()

    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)

    origin = payload.origin_url.rstrip("/")
    success_url = f"{origin}/report/{payload.report_id}?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/report/{payload.report_id}?canceled=1"

    metadata = {
        "report_id": payload.report_id,
        "user_id": user["id"],
        "user_email": user["email"],
        "kind": "report_unlock",
        # Brand attribution — keeps ScoutMePlay separate from 1MillionBolde in the shared Stripe account
        "brand": "ScoutMePlay",
        "company": "Mentalkids",
        "website": "ScoutMePlay",
        "source": "scoutmeplay_website",
        "niche": "football_scouting_video_analysis",
        "product": "ScoutMePlay – Football Video Analysis",
    }

    session_req = CheckoutSessionRequest(
        amount=float(price),
        currency=PRICE_CURRENCY,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata=metadata,
    )
    session = await stripe_checkout.create_checkout_session(session_req)

    # Persist payment transaction
    txn = {
        "id": str(uuid.uuid4()),
        "session_id": session.session_id,
        "user_id": user["id"],
        "user_email": user["email"],
        "report_id": payload.report_id,
        "brand": "ScoutMePlay",
        "amount": float(price),
        "currency": PRICE_CURRENCY,
        "metadata": metadata,
        "payment_status": "initiated",
        "status": "open",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.payment_transactions.insert_one(txn)

    return {"url": session.url, "session_id": session.session_id}


@api_router.get("/payments/status/{session_id}")
async def payment_status(session_id: str, request: Request, user=Depends(get_current_user)):
    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    # If already finalized, just return
    if txn.get("payment_status") == "paid":
        return {"payment_status": "paid", "status": txn.get("status", "complete")}

    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    status_resp: CheckoutStatusResponse = await stripe_checkout.get_checkout_status(session_id)

    new_payment_status = status_resp.payment_status
    new_status = status_resp.status

    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {
            "payment_status": new_payment_status,
            "status": new_status,
            "updated_at": now_iso(),
        }},
    )

    # On success, mark report paid or credit prepay (idempotent)
    if new_payment_status == "paid":
        kind = (txn.get("kind") or txn.get("metadata", {}).get("kind") or "report")
        if kind == "prepay_upload":
            # Idempotent credit grant: only grant if not previously credited
            if not txn.get("credited"):
                await db.users.update_one(
                    {"id": txn["user_id"]},
                    {"$inc": {"prepaid_uploads": 1}},
                )
                await db.payment_transactions.update_one(
                    {"session_id": session_id},
                    {"$set": {"credited": True}},
                )
        else:
            report = await db.reports.find_one({"id": txn.get("report_id")})
            if report and not report.get("is_paid"):
                await db.reports.update_one(
                    {"id": txn["report_id"]},
                    {"$set": {"is_paid": True, "paid_at": now_iso()}},
                )

    return {
        "payment_status": new_payment_status,
        "status": new_status,
        "amount_total": status_resp.amount_total,
        "currency": status_resp.currency,
        "kind": (txn.get("kind") or txn.get("metadata", {}).get("kind") or "report"),
    }


@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("Stripe-Signature", "")

    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)

    try:
        event = await stripe_checkout.handle_webhook(body, signature)
    except Exception as e:
        logger.error(f"Stripe webhook verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid webhook")

    if event.event_type == "checkout.session.completed" and event.payment_status == "paid":
        session_id = event.session_id
        metadata = event.metadata or {}
        kind = metadata.get("kind") or "report"
        txn = await db.payment_transactions.find_one({"session_id": session_id})

        if kind == "prepay_upload":
            if txn and not txn.get("credited"):
                await db.payment_transactions.update_one(
                    {"session_id": session_id},
                    {"$set": {"payment_status": "paid", "status": "complete", "credited": True, "updated_at": now_iso()}},
                )
                user_id = metadata.get("user_id") or txn.get("user_id")
                if user_id:
                    await db.users.update_one(
                        {"id": user_id},
                        {"$inc": {"prepaid_uploads": 1}},
                    )
        else:
            report_id = metadata.get("report_id") or (txn and txn.get("report_id"))
            if report_id:
                if txn and txn.get("payment_status") != "paid":
                    await db.payment_transactions.update_one(
                        {"session_id": session_id},
                        {"$set": {"payment_status": "paid", "status": "complete", "updated_at": now_iso()}},
                    )
                    await db.reports.update_one(
                        {"id": report_id},
                        {"$set": {"is_paid": True, "paid_at": now_iso()}},
                    )

    return {"received": True}


# ============== EMBEDDED CHECKOUT (true in-page Stripe checkout) ==============
# These endpoints use the raw stripe SDK because emergentintegrations does not yet expose
# `ui_mode="embedded"`. They run side-by-side with the redirect-style endpoints above and
# only activate when valid `STRIPE_SECRET_KEY` and `STRIPE_PUBLISHABLE_KEY` are configured.

_SCOUTMEPLAY_METADATA = {
    "brand": "ScoutMePlay",
    "company": "Mentalkids",
    "website": "ScoutMePlay",
    "source": "scoutmeplay_website",
    "niche": "football_scouting_video_analysis",
    "product": "ScoutMePlay – Football Video Analysis",
}


def _embedded_ready() -> bool:
    """Return True only when both pk and sk are real Stripe keys (not the Emergent stub)."""
    pk_ok = STRIPE_PUBLISHABLE_KEY.startswith("pk_")
    sk_ok = STRIPE_SECRET_KEY.startswith("sk_") and STRIPE_SECRET_KEY != "sk_test_emergent"
    return pk_ok and sk_ok


def _arm_real_stripe():
    """Reset the global `stripe` SDK to point at real Stripe.

    emergentintegrations.StripeCheckout silently mutates `stripe.api_base` to its proxy
    whenever the legacy endpoints run. Since both modules share the same `stripe` module
    object, every embedded SDK call MUST re-arm api_base + api_key before use.
    """
    stripe_sdk.api_key = STRIPE_SECRET_KEY
    stripe_sdk.api_base = "https://api.stripe.com"


@api_router.get("/config/stripe")
async def stripe_config():
    """Public endpoint — gives the frontend the publishable key and embedded availability flag."""
    return {
        "publishable_key": STRIPE_PUBLISHABLE_KEY,
        "embedded_available": _embedded_ready(),
    }


def _build_embedded_metadata(extra: Dict[str, str]) -> Dict[str, str]:
    return {**_SCOUTMEPLAY_METADATA, **extra}


@api_router.post("/payments/embedded/prepay-upload")
async def embedded_prepay_upload(payload: PrepayUploadInit, user=Depends(get_current_user)):
    if not _embedded_ready():
        raise HTTPException(status_code=503, detail="Embedded checkout not configured. Add Stripe pk_/sk_ keys.")
    price = await get_current_single_price()
    amount_cents = int(round(float(price) * 100))

    origin = payload.origin_url.rstrip("/")
    return_url = f"{origin}/upload?embedded_session={{CHECKOUT_SESSION_ID}}"

    metadata = _build_embedded_metadata({
        "kind": "prepay_upload",
        "user_id": user["id"],
        "user_email": user["email"],
    })

    try:
        _arm_real_stripe()
        session = stripe_sdk.checkout.Session.create(
            ui_mode="embedded",
            mode="payment",
            redirect_on_completion="if_required",
            line_items=[{
                "price_data": {
                    "currency": PRICE_CURRENCY,
                    "product_data": {
                        "name": "ScoutMePlay – Football Video Analysis",
                        "description": "Upload credit · full premium report included",
                    },
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            return_url=return_url,
            metadata=metadata,
            payment_intent_data={"metadata": metadata},
        )
    except Exception as e:
        logger.exception("Stripe embedded session create failed")
        raise HTTPException(status_code=500, detail=f"Stripe error: {e}")

    txn = {
        "id": str(uuid.uuid4()),
        "session_id": session.id,
        "user_id": user["id"],
        "user_email": user["email"],
        "report_id": None,
        "kind": "prepay_upload",
        "ui_mode": "embedded",
        "brand": "ScoutMePlay",
        "amount": float(price),
        "currency": PRICE_CURRENCY,
        "metadata": metadata,
        "payment_status": "initiated",
        "status": "open",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.payment_transactions.insert_one(txn)

    return {"client_secret": session.client_secret, "session_id": session.id}


@api_router.post("/payments/embedded/unlock")
async def embedded_unlock(payload: CheckoutInit, user=Depends(get_current_user)):
    if not _embedded_ready():
        raise HTTPException(status_code=503, detail="Embedded checkout not configured. Add Stripe pk_/sk_ keys.")
    report = await db.reports.find_one({"id": payload.report_id})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    if report.get("is_paid"):
        raise HTTPException(status_code=400, detail="Report already paid")

    price = await get_current_price()
    amount_cents = int(round(float(price) * 100))

    origin = payload.origin_url.rstrip("/")
    return_url = f"{origin}/report/{payload.report_id}?embedded_session={{CHECKOUT_SESSION_ID}}"

    metadata = _build_embedded_metadata({
        "kind": "report_unlock",
        "report_id": payload.report_id,
        "user_id": user["id"],
        "user_email": user["email"],
    })

    try:
        _arm_real_stripe()
        session = stripe_sdk.checkout.Session.create(
            ui_mode="embedded",
            mode="payment",
            redirect_on_completion="if_required",
            line_items=[{
                "price_data": {
                    "currency": PRICE_CURRENCY,
                    "product_data": {
                        "name": "ScoutMePlay – Premium Report Unlock",
                        "description": "Unlock the full 11-section premium scouting report",
                    },
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            return_url=return_url,
            metadata=metadata,
            payment_intent_data={"metadata": metadata},
        )
    except Exception as e:
        logger.exception("Stripe embedded session create failed")
        raise HTTPException(status_code=500, detail=f"Stripe error: {e}")

    txn = {
        "id": str(uuid.uuid4()),
        "session_id": session.id,
        "user_id": user["id"],
        "user_email": user["email"],
        "report_id": payload.report_id,
        "kind": "report_unlock",
        "ui_mode": "embedded",
        "brand": "ScoutMePlay",
        "amount": float(price),
        "currency": PRICE_CURRENCY,
        "metadata": metadata,
        "payment_status": "initiated",
        "status": "open",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.payment_transactions.insert_one(txn)

    return {"client_secret": session.client_secret, "session_id": session.id}


@api_router.get("/payments/embedded/status/{session_id}")
async def embedded_status(session_id: str, user=Depends(get_current_user)):
    """Status check for embedded sessions — uses raw Stripe SDK + applies same side-effects
    as the redirect-style status endpoint (grant credit / mark report paid, idempotent)."""
    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    if txn.get("payment_status") == "paid":
        return {"payment_status": "paid", "status": txn.get("status", "complete"), "kind": txn.get("kind")}

    if not _embedded_ready():
        raise HTTPException(status_code=503, detail="Embedded checkout not configured.")

    try:
        _arm_real_stripe()
        session = stripe_sdk.checkout.Session.retrieve(session_id)
    except Exception as e:
        logger.exception("Stripe embedded status retrieve failed")
        raise HTTPException(status_code=500, detail=f"Stripe error: {e}")

    new_payment_status = session.payment_status or "unpaid"
    new_status = session.status or "open"

    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {
            "payment_status": new_payment_status,
            "status": new_status,
            "updated_at": now_iso(),
        }},
    )

    # Idempotent side-effects on success
    if new_payment_status == "paid":
        kind = txn.get("kind") or "report_unlock"
        if kind == "prepay_upload":
            if not txn.get("credited"):
                await db.users.update_one(
                    {"id": txn["user_id"]},
                    {"$inc": {"prepaid_uploads": 1}},
                )
                await db.payment_transactions.update_one(
                    {"session_id": session_id},
                    {"$set": {"credited": True}},
                )
        elif kind == "report_unlock":
            report = await db.reports.find_one({"id": txn.get("report_id")})
            if report and not report.get("is_paid"):
                await db.reports.update_one(
                    {"id": txn["report_id"]},
                    {"$set": {"is_paid": True, "paid_at": now_iso()}},
                )

    return {
        "payment_status": new_payment_status,
        "status": new_status,
        "amount_total": session.amount_total,
        "currency": session.currency,
        "kind": txn.get("kind") or "report_unlock",
    }


@api_router.post("/webhook/stripe-embedded")
async def stripe_webhook_embedded(request: Request):
    """Real-Stripe webhook for embedded checkout. Configure this URL in your Stripe Dashboard:
    https://<your-domain>/api/webhook/stripe-embedded
    Listens for `checkout.session.completed` and credits prepaid_uploads or marks report as paid.
    """
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook secret not configured.")

    body = await request.body()
    signature = request.headers.get("Stripe-Signature", "")

    _arm_real_stripe()
    try:
        event = stripe_sdk.Webhook.construct_event(
            payload=body, sig_header=signature, secret=STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe_sdk.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        session_id = session["id"]
        if session.get("payment_status") != "paid":
            return {"received": True}

        txn = await db.payment_transactions.find_one({"session_id": session_id})
        if not txn:
            # Webhook beat the frontend — insert a minimal txn so we can credit
            logger.warning(f"Webhook for unknown session {session_id} — crediting from metadata")

        metadata = session.get("metadata") or {}
        kind = metadata.get("kind") or (txn or {}).get("kind") or "report_unlock"

        if kind == "prepay_upload":
            user_id = metadata.get("user_id") or (txn or {}).get("user_id")
            already_credited = txn and txn.get("credited")
            if user_id and not already_credited:
                await db.users.update_one(
                    {"id": user_id},
                    {"$inc": {"prepaid_uploads": 1}},
                )
            if txn:
                await db.payment_transactions.update_one(
                    {"session_id": session_id},
                    {"$set": {
                        "payment_status": "paid",
                        "status": "complete",
                        "credited": True,
                        "updated_at": now_iso(),
                    }},
                )
        elif kind == "report_unlock":
            report_id = metadata.get("report_id") or (txn or {}).get("report_id")
            if report_id:
                report = await db.reports.find_one({"id": report_id})
                if report and not report.get("is_paid"):
                    await db.reports.update_one(
                        {"id": report_id},
                        {"$set": {"is_paid": True, "paid_at": now_iso()}},
                    )
                if txn:
                    await db.payment_transactions.update_one(
                        {"session_id": session_id},
                        {"$set": {
                            "payment_status": "paid",
                            "status": "complete",
                            "updated_at": now_iso(),
                        }},
                    )
        elif kind == "progress_pass":
            user_id = metadata.get("user_id") or (txn or {}).get("user_id")
            if user_id:
                u = await db.users.find_one({"id": user_id})
                existing = (u or {}).get("progress_pass") or {}
                # Idempotent: only activate if not already activated by THIS session
                if existing.get("activation_session_id") != session_id:
                    from datetime import timedelta as _td
                    now_dt = datetime.now(timezone.utc)
                    await db.users.update_one(
                        {"id": user_id},
                        {"$set": {"progress_pass": {
                            "purchased_at": now_dt.isoformat(),
                            "expires_at": (now_dt + _td(days=365)).isoformat(),
                            "credits_total": 3,
                            "credits_remaining": 3,
                            "activation_session_id": session_id,
                        }}},
                    )
                if txn:
                    await db.payment_transactions.update_one(
                        {"session_id": session_id},
                        {"$set": {
                            "payment_status": "paid",
                            "status": "complete",
                            "updated_at": now_iso(),
                        }},
                    )
        elif kind == "subscription":
            # First-time subscription activation. The Stripe Subscription
            # object is referenced via `session.subscription` (str id). We
            # already persist most state in /payments/subscribe/status, but
            # the webhook is the source-of-truth in case the user closes the
            # tab before the success poll runs.
            user_id = metadata.get("user_id") or (txn or {}).get("user_id")
            sub_id = session.get("subscription")
            if user_id and sub_id and not (txn or {}).get("credited"):
                try:
                    _arm_real_stripe()
                    live = stripe_sdk.Subscription.retrieve(sub_id)
                    sub_state = _subscription_state_from_stripe(live)
                    sub_state["tier"] = metadata.get("tier") or sub_state.get("tier")
                    sub_state["started_at"] = now_iso()
                    await db.users.update_one(
                        {"id": user_id},
                        {"$set": {"subscription": sub_state}},
                    )
                except Exception:
                    logger.exception("Webhook subscription activation failed")
            if txn:
                await db.payment_transactions.update_one(
                    {"session_id": session_id},
                    {"$set": {
                        "payment_status": "paid",
                        "status": "complete",
                        "credited": True,
                        "updated_at": now_iso(),
                    }},
                )

        elif kind == "scout_access":
            # Fase 2 (updated) — ONE-TIME payment for lifetime scout database access.
            # Writes to `users.scout_access` and (for regular users only) elevates
            # their role to scout_client / club_client for future authorization.
            user_id = metadata.get("user_id") or (txn or {}).get("user_id")
            tier_id = metadata.get("tier") or (txn or {}).get("tier")
            if user_id and tier_id and not (txn or {}).get("credited"):
                try:
                    tier_conf = SCOUT_ACCESS_TIERS.get(tier_id, {})
                    scout_access_state = {
                        "tier": tier_id,
                        "status": "active",
                        "one_time": True,
                        "stripe_customer_id": session.get("customer"),
                        "stripe_payment_intent": session.get("payment_intent"),
                        "current_period_end": None,  # lifetime
                        "monthly_reveals": tier_conf.get("monthly_reveals"),
                        "seats": tier_conf.get("seats", 1),
                        "reveals_used_this_period": 0,
                        "started_at": now_iso(),
                        "verified": False,
                    }
                    set_ops = {"scout_access": scout_access_state}
                    role_hint = tier_conf.get("role_hint", "scout_client")
                    u = await db.users.find_one({"id": user_id}, {"_id": 0, "role": 1})
                    if (u or {}).get("role") in (None, "user"):
                        set_ops["role"] = role_hint
                    await db.users.update_one({"id": user_id}, {"$set": set_ops})
                except Exception:
                    logger.exception("Webhook scout-access activation failed")
            if txn:
                await db.payment_transactions.update_one(
                    {"session_id": session_id},
                    {"$set": {
                        "payment_status": "paid",
                        "status": "complete",
                        "credited": True,
                        "updated_at": now_iso(),
                    }},
                )

        # ── Purchase confirmation email — fire-and-forget for every paid kind ──
        # Runs AFTER we've credited the user in Mongo so if SMTP is slow, the
        # user's dashboard is already updated. Never blocks the webhook response.
        try:
            user_email = None
            user_name = None
            user_id_for_email = metadata.get("user_id") or (txn or {}).get("user_id")
            if user_id_for_email:
                u = await db.users.find_one({"id": user_id_for_email}, {"email": 1, "full_name": 1, "_id": 0})
                if u:
                    user_email = u.get("email")
                    user_name = u.get("full_name")
            if not user_email:
                # Fallback — Stripe attaches the buyer's email to the customer
                user_email = (session.get("customer_details") or {}).get("email") or session.get("customer_email")
            if user_email:
                amount_cents = int(session.get("amount_total") or 0)
                currency = (session.get("currency") or "USD").upper()
                product_name = {
                    "prepay_upload": "Extra Scout Report",
                    "report_unlock": "Full Scout Report Unlock",
                    "subscription":  f"{metadata.get('tier', '').title() or 'Premium'} Subscription",
                    "progress_pass": "Season Progress Pass",
                    "scout_access":  f"{SCOUT_ACCESS_TIERS.get(metadata.get('tier') or '', {}).get('name') or 'Scout Access'}",
                }.get(kind, "ScoutMePlay purchase")
                extra_details = None
                if kind == "prepay_upload":
                    price_tier = metadata.get("price_tier") or "single"
                    extra_details = {
                        "single":  "One-off single-report purchase",
                        "premium": "Premium subscriber rate — cheaper than single-report price",
                        "vip":     "VIP subscriber rate — deepest per-report discount",
                    }.get(price_tier)
                elif kind == "scout_access":
                    extra_details = "Monthly scout database access — search + reveal player contacts"
                html, text, subject = render_purchase_confirmation(
                    user_name=user_name,
                    product_name=product_name,
                    amount_cents=amount_cents,
                    currency=currency,
                    extra_details=extra_details,
                )
                # Use asyncio.create_task since we're already inside an async webhook
                asyncio.create_task(send_email_async(user_email, subject, html, text))

                # ── Realtime admin sales-notification ──
                # Fires to the ScoutMePlay operator inbox on EVERY paid checkout
                # (subscription / single-report / extra-report / progress-pass).
                # Uses SMTP_FROM_EMAIL as the recipient (defaults to scoutmeplay@gmail.com).
                try:
                    admin_recipient = (
                        os.environ.get("ADMIN_SALES_EMAIL")
                        or os.environ.get("SMTP_FROM_EMAIL")
                        or os.environ.get("SMTP_USERNAME")
                    )
                    if admin_recipient:
                        adm_html, adm_text, adm_subject = render_admin_sale_notification(
                            product_name=product_name,
                            amount_cents=amount_cents,
                            currency=currency,
                            buyer_email=user_email,
                            buyer_name=user_name,
                            extra_details=extra_details,
                            session_id=session_id,
                        )
                        asyncio.create_task(
                            send_email_async(admin_recipient, adm_subject, adm_html, adm_text)
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Admin sale-notification email dispatch failed: %s", exc)
        except Exception as exc:  # noqa: BLE001 — never block webhook on email failure
            logger.warning("Purchase-confirmation email dispatch failed: %s", exc)
    elif event["type"] in (
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.created",
    ):
        sub_obj = event["data"]["object"]
        sub_id = sub_obj.get("id")
        md = sub_obj.get("metadata") or {}
        # Find the user — first via metadata.user_id (set when we created the
        # checkout session), fall back to looking up by stripe_customer_id.
        user_id = md.get("user_id")
        target = None
        if user_id:
            target = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        if not target:
            target = await db.users.find_one(
                {"subscription.stripe_subscription_id": sub_id},
                {"_id": 0, "password_hash": 0},
            )
        if target:
            existing = target.get("subscription") or {}
            new_state = _subscription_state_from_stripe(sub_obj)
            # Preserve our canonical tier — Stripe metadata might be stripped on some events.
            new_state["tier"] = md.get("tier") or existing.get("tier") or new_state.get("tier")
            # Preserve started_at across updates
            if existing.get("started_at"):
                new_state["started_at"] = existing.get("started_at")
            await db.users.update_one({"id": target["id"]}, {"$set": {"subscription": new_state}})
            logger.info(f"Subscription event {event['type']} → user {target['id']} status={new_state.get('status')} tier={new_state.get('tier')}")

    # Invoice events — useful for analytics + handling payment failures.
    elif event["type"] in ("invoice.payment_succeeded", "invoice.payment_failed"):
        inv = event["data"]["object"]
        sub_id = inv.get("subscription")
        if sub_id:
            # Mirror the resulting subscription state so the user record stays current.
            try:
                _arm_real_stripe()
                live = stripe_sdk.Subscription.retrieve(sub_id)
                tier_pre = await db.users.find_one(
                    {"subscription.stripe_subscription_id": sub_id},
                    {"_id": 0, "subscription.tier": 1, "id": 1},
                )
                if tier_pre:
                    new_state = _subscription_state_from_stripe(live)
                    new_state["tier"] = (tier_pre.get("subscription") or {}).get("tier") or new_state.get("tier")
                    await db.users.update_one(
                        {"id": tier_pre["id"]},
                        {"$set": {"subscription": new_state}},
                    )
            except Exception:
                logger.exception("Webhook invoice handling failed")

    return {"received": True}





# ============== ADMIN ROUTES ==============

@api_router.get("/admin/stats")
async def admin_stats(_=Depends(get_current_admin)):
    total_users = await db.users.count_documents({"role": "user"})
    total_uploads = await db.reports.count_documents({})
    total_paid = await db.reports.count_documents({"$or": [{"is_paid": True}, {"manually_unlocked": True}]})

    # Bounded scan (5,000 most recent paid transactions) so the admin dashboard
    # stays snappy as the production payment_transactions collection grows.
    # Production deployment health check flagged the unbounded `async for` here
    # as a P0 perf risk; once a Mongo aggregation pipeline is wired in this can
    # become unbounded again with a $group/$sum.
    cursor = (
        db.payment_transactions
        .find({"payment_status": "paid"}, {"_id": 0, "amount": 1, "currency": 1})
        .sort("created_at", -1)
        .limit(5000)
    )
    revenue_usd = 0.0
    revenue_dkk = 0.0
    async for tx in cursor:
        cur = tx.get("currency", "").lower()
        if cur == "usd":
            revenue_usd += float(tx.get("amount", 0))
        elif cur == "dkk":
            revenue_dkk += float(tx.get("amount", 0))
    return {
        "total_users": total_users,
        "total_uploads": total_uploads,
        "total_paid_reports": total_paid,
        "revenue_usd": revenue_usd,
        # backward-compat fields (admin UI may still read `revenue_dkk`)
        "revenue_dkk": revenue_dkk,
        "currency": PRICE_CURRENCY.upper(),
    }


@api_router.get("/admin/users")
async def admin_users(_=Depends(get_current_admin)):
    """Returns all users enriched with computed `segment` field:
    - admin     : role == admin
    - scout     : role == scout
    - premium   : role == user AND (prepaid_uploads > 0 OR has at least 1 paid report)
    - free      : role == user AND none of the above
    """
    docs = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    # Bounded scans (1,000 most recent reports) so /admin/users stays responsive
    # as the production reports collection grows past ~50k docs. The data shown
    # in admin UI is dominated by recent activity anyway; older bulk-paid users
    # are still surfaced via their `prepaid_uploads` counter on the user doc.
    paid_emails = set()
    async for r in db.reports.find(
        {"$or": [{"is_paid": True}, {"manually_unlocked": True}]},
        {"_id": 0, "user_email": 1},
    ).sort("created_at", -1).limit(1000):
        if r.get("user_email"):
            paid_emails.add(r["user_email"].lower())
    # paid-report counts per user_id for richer display
    report_counts: Dict[str, int] = {}
    async for r in db.reports.find({}, {"_id": 0, "user_id": 1}).sort("created_at", -1).limit(1000):
        if r.get("user_id"):
            report_counts[r["user_id"]] = report_counts.get(r["user_id"], 0) + 1
    out = []
    for u in docs:
        role = u.get("role") or "user"
        if role == "admin":
            seg = "admin"
        elif role == "scout":
            seg = "scout"
        elif int(u.get("prepaid_uploads", 0) or 0) > 0 or (u.get("email", "").lower() in paid_emails):
            seg = "premium"
        else:
            seg = "free"
        u["segment"] = seg
        u["report_count"] = report_counts.get(u.get("id"), 0)
        out.append(u)
    return out


# ============== ADMIN — USER MANAGEMENT ==============

class ScoutCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str = Field(min_length=2, max_length=100)


@api_router.post("/admin/scouts", status_code=201)
async def admin_create_scout(payload: ScoutCreate, admin=Depends(get_current_admin)):
    """Create a new scout (agent) account that can respond to reports."""
    email = payload.email.lower().strip()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    scout = {
        "id": str(uuid.uuid4()),
        "email": email,
        "password_hash": hash_password(payload.password),
        "full_name": payload.full_name.strip(),
        "role": "scout",
        "created_at": now_iso(),
        "created_by_admin": admin["id"],
    }
    await db.users.insert_one(scout)
    return {
        "id": scout["id"],
        "email": scout["email"],
        "full_name": scout["full_name"],
        "role": "scout",
        "created_at": scout["created_at"],
    }


@api_router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, admin=Depends(get_current_admin)):
    """Delete any user (free, premium, scout). Admin accounts cannot be deleted.
    Cascades: removes the user's reports + uploaded video/marker files + PDFs.
    Payment transactions are kept (audit trail) but the user_id reference remains.
    """
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("role") == "admin":
        raise HTTPException(status_code=400, detail="Admin accounts cannot be deleted")
    if target["id"] == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    # Cascade-delete the user's reports + files
    reports_deleted = 0
    async for r in db.reports.find({"user_id": user_id}, {"_id": 0, "id": 1, "video_filename": 1, "raw_upload_filename": 1, "poster_filename": 1, "marker_filename": 1, "subject_crop_filename": 1}):
        for fname_key in ("video_filename", "raw_upload_filename", "poster_filename", "marker_filename", "subject_crop_filename"):
            fname = r.get(fname_key)
            if fname:
                try:
                    (UPLOAD_DIR / fname).unlink(missing_ok=True)
                except Exception:
                    pass
        try:
            # Purge ALL PDF versions for this report (current + any stale)
            for old in PDF_DIR.glob(f"{r['id']}*.pdf"):
                old.unlink(missing_ok=True)
        except Exception:
            pass
        reports_deleted += 1
    await db.reports.delete_many({"user_id": user_id})
    await db.users.delete_one({"id": user_id})
    return {
        "status": "deleted",
        "email": target.get("email"),
        "role": target.get("role"),
        "reports_deleted": reports_deleted,
    }


# ============== CONTACT MESSAGES ==============

class ContactSubmit(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    message: str = Field(min_length=10, max_length=4000)
    company: Optional[str] = None  # honeypot field — bots fill this; humans don't


@api_router.post("/contact", status_code=201)
async def contact_submit(payload: ContactSubmit, request: Request, background: BackgroundTasks):
    """Public contact form. Stored in `contact_messages` and visible in admin → Messages tab.
    Also forwards to CONTACT_NOTIFY_EMAIL via FormSubmit.co (free, no signup) in the background.
    """
    # Honeypot: silently accept then discard if a bot filled the hidden field
    if payload.company:
        return {"status": "received"}

    # Simple rate-limit: max 5 messages per IP per hour
    client_ip = request.client.host if request.client else "unknown"
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    recent = await db.contact_messages.count_documents({
        "client_ip": client_ip,
        "created_at": {"$gte": cutoff},
    })
    if recent >= 5:
        raise HTTPException(
            status_code=429,
            detail="Too many messages. Please try again in an hour.",
        )

    msg = {
        "id": str(uuid.uuid4()),
        "name": payload.name.strip(),
        "email": payload.email.lower().strip(),
        "message": payload.message.strip(),
        "client_ip": client_ip,
        "user_agent": request.headers.get("User-Agent", "")[:300],
        "status": "new",  # new | read | archived
        "created_at": now_iso(),
    }
    await db.contact_messages.insert_one(msg)

    # Fire-and-forget email forward (non-blocking, never fails the request)
    background.add_task(_forward_contact_to_email, msg)

    return {"status": "received", "id": msg["id"]}


async def _forward_contact_to_email(msg: Dict[str, Any]):
    """Forward contact form submission to CONTACT_NOTIFY_EMAIL via FormSubmit.co.
    FormSubmit is a free email-relay service that requires no signup or API key.
    The very first email sent to a new address will instead be an activation email — the
    admin must click the link once to whitelist the address. After that, all future
    emails arrive in their inbox within seconds.

    NOTE: FormSubmit's AJAX endpoint silently rejects requests without Origin/Referer headers
    (responds 200 with `{"success":"false"}`). We must always send those.
    """
    if not CONTACT_NOTIFY_EMAIL:
        return
    try:
        # The Origin/Referer must look like a real browser submission for FormSubmit to accept it.
        # Read from APP_PUBLIC_URL env so the same code works across preview, production
        # (scoutmeplay.com) and any future custom domain. Falls back to the public production
        # domain so contact-form posts on un-configured pods still succeed.
        origin = os.environ.get("APP_PUBLIC_URL", "https://scoutmeplay.com")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://formsubmit.co/ajax/{CONTACT_NOTIFY_EMAIL}",
                json={
                    "name": msg["name"],
                    "email": msg["email"],
                    "message": msg["message"],
                    "_subject": f"ScoutMePlay contact: {msg['name']}",
                    "_replyto": msg["email"],
                    "_template": "table",
                    "_captcha": "false",
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Origin": origin,
                    "Referer": f"{origin}/about",
                    "User-Agent": "ScoutMePlay/1.0 (+https://scoutmeplay.com)",
                },
            )
            body = {}
            try:
                body = resp.json()
            except Exception:
                pass
            if resp.status_code >= 400:
                logger.warning(
                    f"FormSubmit forward failed ({resp.status_code}) for msg {msg['id']}: {resp.text[:200]}"
                )
            elif str(body.get("success")).lower() == "false":
                # FormSubmit returns 200 even on logical failure — check the JSON
                logger.warning(
                    f"FormSubmit rejected msg {msg['id']}: {body.get('message')}"
                )
            else:
                logger.info(f"Contact message {msg['id']} forwarded to {CONTACT_NOTIFY_EMAIL}")
    except Exception as e:
        logger.warning(f"FormSubmit forward error for msg {msg['id']}: {e}")


@api_router.get("/admin/contact-messages")
async def admin_list_contact(_=Depends(get_current_admin)):
    cursor = db.contact_messages.find({}, {"_id": 0}).sort("created_at", -1).limit(500)
    return await cursor.to_list(500)


@api_router.put("/admin/contact-messages/{msg_id}/status")
async def admin_update_contact_status(msg_id: str, payload: Dict[str, str], _=Depends(get_current_admin)):
    new_status = (payload.get("status") or "").lower()
    if new_status not in ("new", "read", "archived"):
        raise HTTPException(status_code=400, detail="Invalid status")
    res = await db.contact_messages.update_one({"id": msg_id}, {"$set": {"status": new_status}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": new_status}


@api_router.delete("/admin/contact-messages/{msg_id}")
async def admin_delete_contact(msg_id: str, _=Depends(get_current_admin)):
    res = await db.contact_messages.delete_one({"id": msg_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "deleted"}




@api_router.get("/admin/reports")
async def admin_reports(_=Depends(get_current_admin)):
    docs = await db.reports.find({}, {"_id": 0, "full_report": 0}).sort("created_at", -1).to_list(500)
    for d in docs:
        d["video_url"] = _resolve_video_url(d)
        d["poster_url"] = _resolve_poster_url(d)
    return docs


@api_router.post("/admin/seed-test-accounts")
async def admin_seed_test_accounts(_=Depends(get_current_admin)):
    """Idempotent: creates (or updates) two demo accounts used for QA:
      • testscout@scoutmeplay.com — paid CLUB tier, verified, unlimited reveals
      • testvip@scoutmeplay.com   — VIP subscription, 10 prepaid uploads, discoverable
    Safe to call multiple times — always upserts. Only admin can trigger."""
    r1 = await _grant_access_impl(
        email="testscout@scoutmeplay.com",
        password="TestScout@2026!",
        full_name="Test Scout McTester",
        access_type="scout_club",
    )
    r2 = await _grant_access_impl(
        email="testvip@scoutmeplay.com",
        password="TestVip@2026!",
        full_name="Test VIP Player",
        access_type="vip",
    )
    return {"ok": True, "seeded": [r1, r2]}


class GrantAccessRequest(BaseModel):
    email: str
    password: str
    full_name: str
    access_type: str  # "scout_club" | "scout_agent" | "vip" | "premium" | "prepaid_5"


@api_router.post("/admin/grant-access")
async def admin_grant_access(req: GrantAccessRequest, _=Depends(get_current_admin)):
    """Admin-only: create (or upgrade) a user with full paid access — no Stripe.
    access_type:
      • scout_club   → CLUB tier: lifetime, unlimited reveals, 5 seats, verified
      • scout_agent  → AGENT tier: lifetime, 20 reveals/mo, 1 seat, verified
      • vip          → VIP monthly (30d) + 10 prepaid uploads + discoverable
      • premium      → Premium monthly (30d) + 5 prepaid uploads
      • prepaid_5    → free tier + 5 prepaid single-report credits
    """
    result = await _grant_access_impl(
        email=(req.email or "").strip().lower(),
        password=req.password,
        full_name=(req.full_name or "").strip(),
        access_type=(req.access_type or "").strip(),
    )
    return {"ok": True, **result}


async def _grant_access_impl(email: str, password: str, full_name: str, access_type: str):
    """Shared upsert helper — used by both `/admin/grant-access` and
    `/admin/seed-test-accounts`."""
    from datetime import timedelta
    if not email or "@" not in email:
        raise HTTPException(400, "Valid email is required")
    if not password or len(password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if not full_name:
        raise HTTPException(400, "Full name is required")

    now_iso = datetime.now(timezone.utc).isoformat()
    period_end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

    # Common base fields — always overwritten on upsert
    base = {
        "email": email,
        "password_hash": pw_hash,
        "full_name": full_name,
        "email_verified": True,
        "granted_by_admin_at": now_iso,
    }
    # Merge per-tier fields
    if access_type == "scout_club":
        base.update({
            "role": "club_client",
            "scout_access": {
                "tier": "club", "status": "active", "one_time": True,
                "stripe_customer_id": None, "stripe_payment_intent": None,
                "current_period_end": None, "monthly_reveals": None,
                "seats": 5, "reveals_used_this_period": 0, "started_at": now_iso,
                "verified": True, "organization": "Admin-granted",
                "verification": {
                    "status": "approved", "org_name": "Admin-granted",
                    "role_title": "Head of Recruitment",
                    "requested_at": now_iso, "approved_at": now_iso,
                    "approved_by": "admin-grant",
                },
            },
        })
    elif access_type == "scout_agent":
        base.update({
            "role": "scout_client",
            "scout_access": {
                "tier": "agent", "status": "active", "one_time": True,
                "stripe_customer_id": None, "stripe_payment_intent": None,
                "current_period_end": None, "monthly_reveals": 20,
                "seats": 1, "reveals_used_this_period": 0, "started_at": now_iso,
                "verified": True, "organization": "Admin-granted",
                "verification": {
                    "status": "approved", "org_name": "Admin-granted",
                    "role_title": "Agent",
                    "requested_at": now_iso, "approved_at": now_iso,
                    "approved_by": "admin-grant",
                },
            },
        })
    elif access_type == "vip":
        base.update({
            "role": "user",
            "prepaid_uploads": 10,
            "discoverable": True,
            "discoverable_updated_at": now_iso,
            "subscription": {
                "tier": "vip", "status": "active",
                "stripe_customer_id": None, "stripe_subscription_id": None,
                "current_period_end": period_end, "started_at": now_iso,
                "monthly_reports_included": 4, "reports_used_this_period": 0,
                "scout_review_included": True,
            },
            "progress_pass": {"credits": 5, "started_at": now_iso},
        })
    elif access_type == "premium":
        base.update({
            "role": "user",
            "prepaid_uploads": 5,
            "subscription": {
                "tier": "premium", "status": "active",
                "stripe_customer_id": None, "stripe_subscription_id": None,
                "current_period_end": period_end, "started_at": now_iso,
                "monthly_reports_included": 2, "reports_used_this_period": 0,
                "scout_review_included": False,
            },
        })
    elif access_type == "prepaid_5":
        base.update({"role": "user", "prepaid_uploads": 5})
    else:
        raise HTTPException(400, f"Unknown access_type: {access_type}")

    # Upsert — create with an ID on first insert, only overwrite existing user's fields on subsequent calls.
    set_on_insert = {"id": str(uuid.uuid4()), "created_at": now_iso, "free_preview_used": False}
    await db.users.update_one(
        {"email": email},
        {"$set": base, "$setOnInsert": set_on_insert},
        upsert=True,
    )
    return {
        "email": email,
        "password": password,
        "role": base["role"],
        "access_type": access_type,
    }


@api_router.get("/admin/payments")
async def admin_payments(_=Depends(get_current_admin)):
    docs = await db.payment_transactions.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return docs


@api_router.put("/admin/price")
async def admin_update_price(payload: PriceUpdate, _=Depends(get_current_admin)):
    new_price = payload.price if payload.price is not None else payload.price_dkk
    if new_price is None or new_price <= 0:
        raise HTTPException(status_code=400, detail="Price must be > 0")
    if new_price > 999:
        raise HTTPException(status_code=400, detail="Price must be <= 999")
    await db.settings.update_one(
        {"key": "report_price"},
        {"$set": {"key": "report_price", "value": float(new_price), "updated_at": now_iso()}},
        upsert=True,
    )
    return {"price": float(new_price), "currency": PRICE_CURRENCY, "price_dkk": float(new_price)}


@api_router.put("/admin/pass-price")
async def admin_update_pass_price(payload: PriceUpdate, _=Depends(get_current_admin)):
    """Update the 12-month plan / Progress Pass price."""
    new_price = payload.price if payload.price is not None else payload.price_dkk
    if new_price is None or new_price <= 0:
        raise HTTPException(status_code=400, detail="Price must be > 0")
    if new_price > 9999:
        raise HTTPException(status_code=400, detail="Price must be <= 9999")
    await db.settings.update_one(
        {"key": "pass_price"},
        {"$set": {"key": "pass_price", "value": float(new_price), "updated_at": now_iso()}},
        upsert=True,
    )
    return {"pass_price": float(new_price), "currency": PRICE_CURRENCY}


@api_router.put("/admin/pricing")
async def admin_update_pricing(payload: PricingUpdate, _=Depends(get_current_admin)):
    """Bulk update for the 3 admin-controlled display prices.

    Accepts any subset of {single_price, premium_price, vip_price}. Returns
    the new values plus a `stripe_sync_required` flag when premium or vip
    prices changed (subscription Stripe Prices are immutable — see
    PricingUpdate docstring).
    """
    updates: list[tuple[str, float]] = []
    if payload.single_price is not None:
        if payload.single_price <= 0 or payload.single_price > 9999:
            raise HTTPException(status_code=400, detail="single_price out of range")
        updates.append(("single_price", float(payload.single_price)))
    if payload.premium_price is not None:
        if payload.premium_price <= 0 or payload.premium_price > 999:
            raise HTTPException(status_code=400, detail="premium_price out of range")
        updates.append(("premium_price", float(payload.premium_price)))
    if payload.vip_price is not None:
        if payload.vip_price <= 0 or payload.vip_price > 999:
            raise HTTPException(status_code=400, detail="vip_price out of range")
        updates.append(("vip_price", float(payload.vip_price)))
    if payload.premium_extra_price is not None:
        if payload.premium_extra_price <= 0 or payload.premium_extra_price > 9999:
            raise HTTPException(status_code=400, detail="premium_extra_price out of range")
        updates.append(("premium_extra_report_price", float(payload.premium_extra_price)))
    if payload.vip_extra_price is not None:
        if payload.vip_extra_price <= 0 or payload.vip_extra_price > 9999:
            raise HTTPException(status_code=400, detail="vip_extra_price out of range")
        updates.append(("vip_extra_report_price", float(payload.vip_extra_price)))
    if not updates:
        raise HTTPException(status_code=400, detail="No prices provided")
    now = now_iso()
    for key, value in updates:
        await db.settings.update_one(
            {"key": key},
            {"$set": {"key": key, "value": value, "updated_at": now}},
            upsert=True,
        )
    stripe_sync_required = any(k in ("premium_price", "vip_price") for k, _ in updates)
    # Echo current state of all five for the UI
    snap = {}
    for key, default in (
        ("single_price", DEFAULT_SINGLE_PRICE),
        ("premium_price", DEFAULT_PREMIUM_PRICE),
        ("vip_price", DEFAULT_VIP_PRICE),
        ("premium_extra_report_price", DEFAULT_PREMIUM_EXTRA_PRICE),
        ("vip_extra_report_price", DEFAULT_VIP_EXTRA_PRICE),
    ):
        doc = await db.settings.find_one({"key": key})
        snap[key] = float(doc["value"]) if doc and "value" in doc else default
    # Alias the two extra-report keys to the shorter public names expected by the frontend
    snap["premium_extra_price"] = snap.pop("premium_extra_report_price")
    snap["vip_extra_price"] = snap.pop("vip_extra_report_price")
    return {
        **snap,
        "currency": PRICE_CURRENCY,
        "stripe_sync_required": stripe_sync_required,
        "note": (
            "Premium/VIP subscription changes update the displayed price on the website immediately. "
            "Stripe subscription Price IDs are immutable, so the actual checkout amount "
            "stays at the originally configured value until the Stripe Prices are re-created."
        ) if stripe_sync_required else None,
    }


# ════════════════════════════════════════════════════════════════════════════
# FAQ / Common Questions CMS
# ════════════════════════════════════════════════════════════════════════════
# Admin-editable landing-page FAQ. Stored in `db.faq_items` — one document per
# question. Public `GET /api/faq` returns only published items sorted by
# `order`. On first-ever access, the collection is seeded with the same set
# of default items previously hardcoded in the frontend so existing sites do
# not lose their FAQ.
# ────────────────────────────────────────────────────────────────────────────

_DEFAULT_FAQ_ITEMS = [
    {
        "q": "How long does it take to get my report?",
        "a": ("Your Pro Scout Intelligence analysis is delivered instantly — as soon as the AI pipeline "
              "finishes processing your video (typically 5–15 minutes, depending on clip length). "
              "If your plan includes a real scout review (VIP Premium), a professional scout responds "
              "with their personal feedback within 48 hours on top of the instant AI report. "
              "If we ever miss that 48-hour window on a scout review, your purchase is refunded in full — "
              "automatically, no support tickets needed."),
    },
    {
        "q": "Is my child too young for this?",
        "a": ("ScoutMePlay is built for ambitious players aged U7 to U21. The report adjusts to the player's "
              "age — a 9-year-old is benchmarked against age-appropriate development standards, not against "
              "a senior pro. You get an honest read of where the player is, and where they could realistically go next."),
    },
    {
        "q": "What if my video isn't great quality?",
        "a": ("A phone camera at training or a game is perfectly fine. We need to see your player on the "
              "pitch with the ball. Wider shots (showing more of the pitch) are better than tight close-ups, "
              "and a clear view of the player's movement helps the scout review. If our scout can't fairly "
              "assess the video, we contact you and either offer a re-upload or a refund."),
    },
    {
        "q": "How is this different from my child's coach feedback?",
        "a": ("A coach knows your player from the inside — that's irreplaceable. A scout looks from the outside, "
              "comparing your player against thousands of others in a structured 4-pillar framework "
              "(Technical, Tactical, Physical, Mentality). Coaches build your player day by day. "
              "ScoutMePlay tells you where they stand right now and what to focus on next."),
    },
    {
        "q": "Does this guarantee a trial or contract?",
        "a": ("No, and we'll never claim that. ScoutMePlay is built to help players grow, not to broker contracts. "
              "Anyone promising guaranteed trials is selling you something we won't sell. Our job is to give you "
              "honest, professional feedback so you can train smarter — the rest is up to the player."),
    },
    {
        "q": "Will my video be kept private?",
        "a": ("Yes. Your video is used only to produce your report and is never published, sold, or shared outside "
              "the scout reviewing it. You retain full ownership of your video and your report. You can request "
              "deletion of your account and data at any time from your dashboard."),
    },
    {
        "q": "What's the difference between the single report and the monthly plans?",
        "a": "__PRICE_FAQ__",
    },
    {
        "q": "Can I get reports for more than one player?",
        "a": ("Yes — but each player needs their own report (or plan), so the analysis stays fair and personal. "
              "If you have multiple kids in football, each upload is reviewed independently against age-appropriate benchmarks."),
    },
]


def _faq_doc_to_public(doc: dict) -> dict:
    return {
        "id": doc.get("id"),
        "q": doc.get("q") or "",
        "a": doc.get("a") or "",
        "order": int(doc.get("order", 0)),
        "published": bool(doc.get("published", True)),
        "updated_at": doc.get("updated_at"),
        "created_at": doc.get("created_at"),
    }


async def _seed_faq_if_empty() -> None:
    """Idempotent seed. Called from the public GET on first hit if the
    collection is completely empty. Safe to call multiple times — it's a
    no-op once the collection has any documents."""
    count = await db.faq_items.count_documents({})
    if count > 0:
        return
    now = now_iso()
    for idx, item in enumerate(_DEFAULT_FAQ_ITEMS):
        await db.faq_items.insert_one({
            "id": str(uuid.uuid4()),
            "q": item["q"],
            "a": item["a"],
            "order": idx,
            "published": True,
            "created_at": now,
            "updated_at": now,
        })


@api_router.get("/faq")
async def get_public_faq():
    """Public — returns only published FAQ items, sorted by `order` ascending.
    Auto-seeds the built-in defaults on first ever access."""
    await _seed_faq_if_empty()
    cursor = db.faq_items.find({"published": True}, {"_id": 0}).sort("order", 1)
    items = [_faq_doc_to_public(d) async for d in cursor]
    return {"items": items}


@api_router.get("/admin/faq")
async def get_admin_faq(user=Depends(get_current_admin)):
    """Admin — returns ALL items (including unpublished), sorted by `order`."""
    await _seed_faq_if_empty()
    cursor = db.faq_items.find({}, {"_id": 0}).sort("order", 1)
    items = [_faq_doc_to_public(d) async for d in cursor]
    return {"items": items}


@api_router.post("/admin/faq")
async def create_faq_item(payload: FAQCreate, user=Depends(get_current_admin)):
    q = (payload.q or "").strip()
    a = (payload.a or "").strip()
    if not q or not a:
        raise HTTPException(status_code=400, detail="Both 'q' and 'a' are required")
    if len(q) > 300:
        raise HTTPException(status_code=400, detail="Question too long (max 300 chars)")
    if len(a) > 5000:
        raise HTTPException(status_code=400, detail="Answer too long (max 5000 chars)")
    # Append at the end
    max_order_doc = await db.faq_items.find({}, {"order": 1, "_id": 0}).sort("order", -1).limit(1).to_list(length=1)
    next_order = (max_order_doc[0]["order"] + 1) if max_order_doc else 0
    now = now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "q": q,
        "a": a,
        "order": next_order,
        "published": bool(payload.published) if payload.published is not None else True,
        "created_at": now,
        "updated_at": now,
    }
    await db.faq_items.insert_one(doc)
    return _faq_doc_to_public(doc)


@api_router.put("/admin/faq/{item_id}")
async def update_faq_item(item_id: str, payload: FAQUpdate, user=Depends(get_current_admin)):
    existing = await db.faq_items.find_one({"id": item_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="FAQ item not found")
    updates: dict = {"updated_at": now_iso()}
    if payload.q is not None:
        q = payload.q.strip()
        if not q:
            raise HTTPException(status_code=400, detail="Question cannot be empty")
        if len(q) > 300:
            raise HTTPException(status_code=400, detail="Question too long (max 300 chars)")
        updates["q"] = q
    if payload.a is not None:
        a = payload.a.strip()
        if not a:
            raise HTTPException(status_code=400, detail="Answer cannot be empty")
        if len(a) > 5000:
            raise HTTPException(status_code=400, detail="Answer too long (max 5000 chars)")
        updates["a"] = a
    if payload.published is not None:
        updates["published"] = bool(payload.published)
    if payload.order is not None:
        updates["order"] = int(payload.order)
    await db.faq_items.update_one({"id": item_id}, {"$set": updates})
    merged = {**existing, **updates}
    return _faq_doc_to_public(merged)


@api_router.delete("/admin/faq/{item_id}")
async def delete_faq_item(item_id: str, user=Depends(get_current_admin)):
    res = await db.faq_items.delete_one({"id": item_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="FAQ item not found")
    return {"deleted": True, "id": item_id}


@api_router.post("/admin/faq/reorder")
async def reorder_faq_items(payload: FAQReorder, user=Depends(get_current_admin)):
    """Bulk-set the `order` field on multiple items in a single call — used
    by the admin UI's up/down arrows and drag-to-reorder."""
    if not payload.ordered_ids:
        raise HTTPException(status_code=400, detail="ordered_ids cannot be empty")
    now = now_iso()
    for idx, item_id in enumerate(payload.ordered_ids):
        await db.faq_items.update_one(
            {"id": item_id},
            {"$set": {"order": idx, "updated_at": now}},
        )
    cursor = db.faq_items.find({}, {"_id": 0}).sort("order", 1)
    items = [_faq_doc_to_public(d) async for d in cursor]
    return {"items": items}


# ════════════════════════════════════════════════════════════════════════════
# Admin bulk-email — Gmail SMTP powered
# ════════════════════════════════════════════════════════════════════════════

class BulkEmailSend(BaseModel):
    subject: str
    body_html: str
    segment: str = "all"
    test_email: Optional[str] = None
    preheader: Optional[str] = None


async def _query_recipients_for_segment(segment: str) -> list[str]:
    segment = (segment or "all").lower()
    q: dict = {}
    if segment == "premium":
        q = {"subscription.tier": "premium"}
    elif segment == "vip":
        q = {"subscription.tier": "vip"}
    elif segment == "admins":
        q = {"role": "admin"}
    elif segment == "progress_pass":
        q = {"progress_pass.credits_remaining": {"$gt": 0}}
    elif segment == "free":
        q = {"$or": [
            {"subscription": {"$exists": False}},
            {"subscription.tier": {"$in": [None, "", "free"]}},
        ]}
    cursor = db.users.find(q, {"email": 1, "_id": 0})
    return [d["email"] async for d in cursor if d.get("email")]


@api_router.get("/admin/bulk-email/segments")
async def bulk_email_segments(user=Depends(get_current_admin)):
    segments = ["all", "free", "premium", "vip", "progress_pass", "admins"]
    out = {}
    for s in segments:
        emails = await _query_recipients_for_segment(s)
        out[s] = len(emails)
    return {
        "counts": out,
        "smtp_enabled": email_enabled(),
        "note": (
            "Add SMTP_HOST, SMTP_PORT, SMTP_USERNAME and SMTP_PASSWORD to backend/.env "
            "to enable actual email sending. Without them, sends are no-ops."
        ) if not email_enabled() else None,
    }


@api_router.post("/admin/bulk-email/send")
async def bulk_email_send(payload: BulkEmailSend, user=Depends(get_current_admin)):
    subject = (payload.subject or "").strip()
    body = (payload.body_html or "").strip()
    if not subject or not body:
        raise HTTPException(status_code=400, detail="subject and body_html are required")
    if len(subject) > 500:
        raise HTTPException(status_code=400, detail="subject too long")

    html_wrapped, text_body, _subject = render_bulk_email(subject, body, preheader=payload.preheader or "")

    if payload.test_email:
        addr = payload.test_email.strip().lower()
        if "@" not in addr:
            raise HTTPException(status_code=400, detail="test_email is not a valid address")
        ok = await send_email_async(addr, subject, html_wrapped, text_body)
        return {"test_only": True, "sent": 1 if ok else 0, "failed": 0 if ok else 1, "recipient": addr, "smtp_enabled": email_enabled()}

    recipients = await _query_recipients_for_segment(payload.segment)
    total = len(recipients)
    if total == 0:
        raise HTTPException(status_code=400, detail=f"Segment '{payload.segment}' has no recipients")

    job_id = str(uuid.uuid4())
    now = now_iso()
    await db.bulk_email_jobs.insert_one({
        "id": job_id,
        "admin_id": user["id"],
        "admin_email": user.get("email"),
        "subject": subject,
        "segment": payload.segment,
        "total": total,
        "sent": 0,
        "failed": 0,
        "status": "queued",
        "created_at": now,
        "updated_at": now,
        "smtp_enabled": email_enabled(),
    })

    async def _progress_cb(sent, failed, total_):
        if (sent + failed) % 10 == 0 or (sent + failed) == total_:
            await db.bulk_email_jobs.update_one(
                {"id": job_id},
                {"$set": {"sent": sent, "failed": failed, "status": "sending", "updated_at": now_iso()}},
            )

    async def _run_job():
        try:
            result = await send_bulk_email(
                recipients=recipients,
                subject=subject,
                html_body=html_wrapped,
                text_body=text_body,
                delay_seconds=1.0,
                on_progress=_progress_cb,
            )
            await db.bulk_email_jobs.update_one(
                {"id": job_id},
                {"$set": {
                    "sent": result["sent"],
                    "failed": result["failed"],
                    "failed_emails": result["failed_emails"],
                    "status": "complete",
                    "completed_at": now_iso(),
                    "updated_at": now_iso(),
                }},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Bulk email job %s crashed: %s", job_id, exc)
            await db.bulk_email_jobs.update_one(
                {"id": job_id},
                {"$set": {"status": "error", "error": str(exc), "updated_at": now_iso()}},
            )

    asyncio.create_task(_run_job())

    return {
        "job_id": job_id,
        "queued": total,
        "segment": payload.segment,
        "status": "queued",
        "smtp_enabled": email_enabled(),
    }


@api_router.get("/admin/bulk-email/jobs")
async def bulk_email_jobs_list(user=Depends(get_current_admin), limit: int = 50):
    cursor = db.bulk_email_jobs.find({}, {"_id": 0}).sort("created_at", -1).limit(min(limit, 200))
    items = [d async for d in cursor]
    return {"items": items}


@api_router.get("/admin/bulk-email/jobs/{job_id}")
async def bulk_email_job_detail(job_id: str, user=Depends(get_current_admin)):
    doc = await db.bulk_email_jobs.find_one({"id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found")
    return doc



async def get_current_single_price() -> float:
    """Helper used by the one-time Single Report checkout endpoint."""
    doc = await db.settings.find_one({"key": "single_price"})
    if doc and "value" in doc:
        return float(doc["value"])
    return DEFAULT_SINGLE_PRICE


async def get_extra_report_price_for_user(user: dict) -> tuple[float, str]:
    """Return `(price, source_tier)` for the per-report price the given user
    would pay when buying an ADDITIONAL report beyond their monthly quota.

      - Free / no subscription  → `single_price`  ($129 default)
      - Premium subscriber      → `premium_extra_report_price`  ($89 default)
      - VIP subscriber          → `vip_extra_report_price`      ($59 default)

    `source_tier` is one of {"single", "premium", "vip"} — useful for
    downstream metadata / UI copy.
    """
    tier = (user.get("subscription") or {}).get("tier") if user else None
    if tier == "vip":
        doc = await db.settings.find_one({"key": "vip_extra_report_price"})
        val = float(doc["value"]) if doc and "value" in doc else DEFAULT_VIP_EXTRA_PRICE
        return (val, "vip")
    if tier == "premium":
        doc = await db.settings.find_one({"key": "premium_extra_report_price"})
        val = float(doc["value"]) if doc and "value" in doc else DEFAULT_PREMIUM_EXTRA_PRICE
        return (val, "premium")
    return (await get_current_single_price(), "single")


@api_router.post("/admin/cleanup-raw-uploads")
async def admin_cleanup_raw_uploads(_=Depends(get_current_admin)):
    """One-shot disk cleanup — sweep `/app/backend/uploads/` for orphaned raw
    source files left over from before the automatic post-transcode cleanup
    landed (session 91).

    Two passes:
      PASS 1 — for any report whose `video_filename` already points at the
        `.web.mp4`, delete every other source file with the same report-id
        prefix (raw .mov / .mp4 left over from before auto-cleanup landed).
      PASS 2 — for any report whose `video_filename` is still a raw .mov/.mp4
        BUT a sibling `.web.mp4` already exists on disk (orphaned transcode),
        re-point the doc at the `.web.mp4` AND delete the raw source.

    A whitelist of derivative files (marker, poster, subject crop, anchor
    crops, preview clip) is never touched.
    """
    removed = 0
    repointed = 0
    freed_bytes = 0
    skipped_no_web_version = 0
    errors: list[str] = []

    DERIVATIVE_SUFFIXES = ("-marker.jpg", "-poster.jpg", "-subject.jpg", "-preview.mp4")

    def _is_derivative(name: str) -> bool:
        if any(name.endswith(s) for s in DERIVATIVE_SUFFIXES):
            return True
        if "-anchor" in name:
            return True
        return False

    # ── PASS 1 — reports already pointing at .web.mp4 ───────────────────
    cursor = db.reports.find(
        {"video_filename": {"$regex": r"\.web\.mp4$"}},
        {"_id": 0, "id": 1, "video_filename": 1},
    )
    async for r in cursor:
        report_id = r.get("id")
        web_name = r.get("video_filename")
        if not (report_id and web_name and web_name.endswith(".web.mp4")):
            continue
        if not (UPLOAD_DIR / web_name).exists():
            skipped_no_web_version += 1
            continue
        for stale in UPLOAD_DIR.glob(f"{report_id}.*"):
            name = stale.name
            if name == web_name or _is_derivative(name):
                continue
            try:
                size = stale.stat().st_size
                stale.unlink()
                removed += 1
                freed_bytes += size
                logger.info(f"cleanup pass1: removed orphan {name} ({size // 1024} KB)")
            except Exception as e:
                errors.append(f"pass1 {name}: {e}")

    # ── PASS 2 — reports still pointing at raw, but a .web.mp4 already exists ──
    cursor = db.reports.find(
        {"video_filename": {"$not": {"$regex": r"\.web\.mp4$"}}},
        {"_id": 0, "id": 1, "video_filename": 1},
    )
    async for r in cursor:
        report_id = r.get("id")
        raw_name = r.get("video_filename")
        if not (report_id and raw_name):
            continue
        web_path = UPLOAD_DIR / f"{report_id}.web.mp4"
        if not web_path.exists():
            continue  # no transcoded version available — leave alone
        raw_path = UPLOAD_DIR / raw_name
        # Re-point the doc at the playable file
        try:
            await db.reports.update_one(
                {"id": report_id},
                {"$set": {"video_filename": web_path.name}},
            )
            repointed += 1
        except Exception as e:
            errors.append(f"pass2-update {report_id}: {e}")
            continue
        # Then delete the raw source
        if raw_path.exists() and raw_path.resolve() != web_path.resolve():
            try:
                size = raw_path.stat().st_size
                raw_path.unlink()
                removed += 1
                freed_bytes += size
                logger.info(f"cleanup pass2: repointed {report_id} and removed {raw_name} ({size // 1024} KB)")
            except Exception as e:
                errors.append(f"pass2-unlink {raw_name}: {e}")

    # ── PASS 3 — truly orphaned raw sources (report row deleted from DB) ──
    # For every raw .mov/.mp4 on disk that DOES have a .web.mp4 sibling AND
    # whose report-id prefix has NO matching DB record, delete the raw
    # source. The .web.mp4 is kept (in case someone restores the report row
    # from a backup); only the redundant raw bytes are reclaimed.
    for raw in list(UPLOAD_DIR.glob("*.mov")) + list(UPLOAD_DIR.glob("*.mp4")):
        name = raw.name
        if name.endswith(".web.mp4") or _is_derivative(name):
            continue
        report_id_guess = name.rsplit(".", 1)[0]
        sibling_web = UPLOAD_DIR / f"{report_id_guess}.web.mp4"
        if not sibling_web.exists():
            continue
        # Only delete if there is NO DB record referencing this report-id
        exists_in_db = await db.reports.find_one(
            {"id": report_id_guess}, {"_id": 0, "id": 1}
        )
        if exists_in_db:
            continue  # handled by pass 1 or pass 2 already
        try:
            size = raw.stat().st_size
            raw.unlink()
            removed += 1
            freed_bytes += size
            logger.info(f"cleanup pass3: removed truly-orphaned raw {name} ({size // 1024} KB)")
        except Exception as e:
            errors.append(f"pass3-unlink {name}: {e}")

    return {
        "removed_files": removed,
        "repointed_reports": repointed,
        "freed_bytes": freed_bytes,
        "freed_mb": round(freed_bytes / (1024 * 1024), 2),
        "skipped_no_web_version": skipped_no_web_version,
        "errors": errors[:20],
    }


@api_router.put("/admin/social-links")
async def admin_update_social_links(payload: SocialLinksUpdate, _=Depends(get_current_admin)):
    """Update the public social media URLs shown in the footer.
    Accepts any subset of {twitter_url, facebook_url, linkedin_url, instagram_url};
    each provided value must be a full http(s) URL or an empty string (empty string keeps it hidden)."""
    current = await get_social_links()
    update = {k: (v.strip() if isinstance(v, str) else v) for k, v in payload.dict().items() if v is not None}
    for k, v in update.items():
        if v and not (v.startswith("https://") or v.startswith("http://")):
            raise HTTPException(status_code=400, detail=f"{k} must start with https:// or http://")
        if v and len(v) > 500:
            raise HTTPException(status_code=400, detail=f"{k} is too long")
    merged = {**current, **update}
    await db.settings.update_one(
        {"key": "social_links"},
        {"$set": {"key": "social_links", "value": merged, "updated_at": now_iso()}},
        upsert=True,
    )
    return {"social": merged}


@api_router.get("/admin/active-landing")
async def admin_get_active_landing(_=Depends(get_current_admin)):
    """Return the currently active landing variant. Defaults to 'minimal'."""
    doc = await db.settings.find_one({"key": "active_landing"}, {"_id": 0})
    value = doc.get("value", "minimal") if doc else "minimal"
    if value not in ("full", "minimal"):
        value = "minimal"
    return {"active_landing": value}


@api_router.put("/admin/active-landing")
async def admin_update_active_landing(payload: dict, _=Depends(get_current_admin)):
    """Switch the public landing page between the long 'full' marketing
    page and the short 'minimal' conversion-focused variant."""
    value = (payload or {}).get("active_landing")
    if value not in ("full", "minimal"):
        raise HTTPException(status_code=400, detail="active_landing must be 'full' or 'minimal'")
    await db.settings.update_one(
        {"key": "active_landing"},
        {"$set": {"key": "active_landing", "value": value, "updated_at": now_iso()}},
        upsert=True,
    )
    return {"active_landing": value}


@api_router.post("/admin/reports/{report_id}/unlock")
async def admin_unlock(report_id: str, _=Depends(get_current_admin)):
    res = await db.reports.update_one(
        {"id": report_id},
        {"$set": {"manually_unlocked": True, "paid_at": now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"status": "unlocked"}


@api_router.delete("/admin/reports/{report_id}")
async def admin_delete_report(report_id: str, _=Depends(get_current_admin)):
    doc = await db.reports.find_one({"id": report_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")
    # remove file
    try:
        (UPLOAD_DIR / doc["video_filename"]).unlink(missing_ok=True)
    except Exception:
        pass
    try:
        # Purge ALL PDF versions for this report (current + any stale)
        for old in PDF_DIR.glob(f"{report_id}*.pdf"):
            old.unlink(missing_ok=True)
    except Exception:
        pass
    await db.reports.delete_one({"id": report_id})
    return {"status": "deleted"}


# ============== APP WIRING ==============

# ── Blog & SEO routers (modular extension) ────────────────────────────────
from blog_routes import build_blog_router, mount_blog_uploads
from blog_seo import build_seo_router
from url_video_fetch import build_url_fetch_router, resolve_temp_token_path
from progress_tracking import (
    build_progress_router,
    find_or_create_profile,
    consume_pass_credit,
    _pass_active as _progress_pass_active,
)

api_router.include_router(build_blog_router(
    db=db,
    get_current_admin=get_current_admin,
    get_current_user=get_current_user,
    call_gemini_text=call_gemini_text,
))
api_router.include_router(build_seo_router(db=db))
api_router.include_router(build_url_fetch_router(
    upload_dir=UPLOAD_DIR,
    get_current_user=get_current_user,
))
api_router.include_router(build_progress_router(
    db=db,
    get_current_user=get_current_user,
    call_gemini_text=call_gemini_text,
    stripe_sdk=stripe_sdk,
    upload_dir=UPLOAD_DIR,
    pass_price_usd=float(os.environ.get("PROGRESS_PASS_PRICE_USD", str(DEFAULT_PASS_PRICE))),
    price_currency=PRICE_CURRENCY.lower() if PRICE_CURRENCY else "usd",
    arm_stripe_fn=_arm_real_stripe,
))
mount_blog_uploads(app)

# NOTE: app.include_router(api_router) is called at the very bottom of this
# file so it captures ALL @api_router routes (including scout-access + players
# database endpoints added below the startup handler).

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    # ── Security indexes (idempotent, safe to call every boot) ──
    try:
        # Unique email index — belt+braces for our email-uniqueness check.
        await db.users.create_index("email", unique=True, background=True)
        # TTL on password reset tokens → Mongo auto-deletes when expires_at passes.
        await db.password_reset_tokens.create_index(
            "expires_at", expireAfterSeconds=0, background=True
        )
        await db.password_reset_tokens.create_index("token", unique=True, background=True)
        # TTL cleanup for signup-rate-limit records (1 hour window).
        await db.signup_attempts.create_index(
            "created_at", expireAfterSeconds=3600, background=True
        )
        # Login-attempts records live at most 24h (way past any lockout window).
        await db.login_attempts.create_index("key", unique=True, background=True)
    except Exception:
        logger.exception("Security index creation failed (non-fatal)")

    # Ensure admin user exists (idempotent)
    existing = await db.users.find_one({"email": ADMIN_EMAIL.lower()})
    if not existing:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": ADMIN_EMAIL.lower(),
            "password_hash": hash_password(ADMIN_PASSWORD),
            "full_name": "Elite Scout Admin",
            "role": "admin",
            "created_at": now_iso(),
        })
        logger.info(f"Seeded admin user: {ADMIN_EMAIL}")
    else:
        # always re-set admin's password to keep it in sync with env (idempotent)
        await db.users.update_one(
            {"email": ADMIN_EMAIL.lower()},
            {"$set": {"password_hash": hash_password(ADMIN_PASSWORD), "role": "admin"}},
        )

    # Ensure default price exists
    pr = await db.settings.find_one({"key": "report_price"})
    if not pr:
        await db.settings.insert_one({"key": "report_price", "value": DEFAULT_PRICE, "updated_at": now_iso()})

    # Provision Stripe subscription products + recurring prices (idempotent).
    # Safe no-op if Stripe live keys are missing; only writes to Stripe on the
    # first call after either tier was added or settings were cleared.
    try:
        await _ensure_subscription_products()
    except Exception:
        logger.exception("Subscription product provisioning failed on startup (will retry lazily)")

    # Provision Stripe scout-access subscription products (Fase 2 — scout database).
    try:
        await _ensure_scout_access_products()
    except Exception:
        logger.exception("Scout-access product provisioning failed on startup (will retry lazily)")


# ============== ROUTES: SCOUT ACCESS SUBSCRIPTION (Fase 2) ==============
# Separate paid subscription that unlocks the /players-database search index
# for scouts, agents and clubs. Users can hold both a player subscription
# (Premium/VIP) and a scout access subscription at the same time.

class ScoutVerificationProfile(BaseModel):
    """Verification info captured before checkout — used by admin to review + verify.
    Payment is only step 1; admin verified badge is granted after review."""
    organization_name: Optional[str] = None
    organization_type: Optional[str] = None  # "scouting_agency" | "club" | "solo_scout" | "agent" | "media"
    role_title: Optional[str] = None
    country: Optional[str] = None
    website: Optional[str] = None
    linkedin_url: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class ScoutAccessSubscribe(BaseModel):
    tier: str
    origin_url: str
    verification: Optional[ScoutVerificationProfile] = None


def _scout_reveal_period_state(user_doc: dict) -> dict:
    """Rolls reveal-count over on a fresh billing period. Returns updated fields
    to $set on the user doc so the caller can persist them if desired."""
    sa = user_doc.get("scout_access") or {}
    period_end = sa.get("current_period_end")
    reveal_period_marker = sa.get("reveal_period_marker")
    if period_end and period_end != reveal_period_marker:
        # New period started — reset reveals
        return {"reveals_used_this_period": 0, "reveal_period_marker": period_end}
    return {}


@api_router.get("/scout-access/tiers")
async def public_scout_access_tiers():
    """Public — list scout access tiers and prices for the /scouts landing page."""
    tiers = []
    for tier_id, conf in SCOUT_ACCESS_TIERS.items():
        tiers.append({
            "id": tier_id,
            "name": conf["name"],
            "description": conf["description"],
            "amount": conf["amount"],
            "currency": PRICE_CURRENCY,
            "monthly_reveals": conf["monthly_reveals"],
            "seats": conf["seats"],
        })
    return {"tiers": tiers}


@api_router.get("/scout-access/me")
async def get_my_scout_access(user=Depends(get_current_user)):
    """Returns the caller's active scout access state (or a stub when inactive)."""
    sa = user.get("scout_access") or {}
    active = _has_active_scout_access(user) is not None or user.get("role") == "admin"
    tier_id = sa.get("tier")
    tier_conf = SCOUT_ACCESS_TIERS.get(tier_id, {}) if tier_id else {}
    used = int(sa.get("reveals_used_this_period") or 0)
    limit = tier_conf.get("monthly_reveals")  # None => unlimited
    remaining = None if limit is None else max(0, limit - used)
    return {
        "active": bool(active),
        "tier": tier_id,
        "status": sa.get("status", "inactive"),
        "verified": bool(sa.get("verified")),
        "one_time": bool(sa.get("one_time")),
        "current_period_end": sa.get("current_period_end"),
        "monthly_reveals": limit,
        "reveals_used_this_period": used,
        "reveals_remaining": remaining,
        "seats": tier_conf.get("seats", 1),
        "started_at": sa.get("started_at"),
        "revoked_at": sa.get("revoked_at"),
        "revoked_reason": sa.get("revoked_reason"),
        "verification": user.get("scout_verification") or None,
    }


@api_router.post("/scout-access/subscribe")
async def subscribe_scout_access(payload: ScoutAccessSubscribe, user=Depends(get_current_user)):
    """Create a Stripe Checkout Session for a ONE-TIME scout access purchase.
    Also persists the caller-provided verification profile so admin can review
    the buyer before granting the 'Verified' badge (auto-granted access is
    still gated by successful payment + optional admin revoke)."""
    tier = (payload.tier or "").lower().strip()
    if tier not in SCOUT_ACCESS_TIERS:
        raise HTTPException(400, "Unknown scout access tier")
    if not _embedded_ready():
        raise HTTPException(503, "Scout access checkout not configured. Add Stripe live keys to enable.")
    if _has_active_scout_access(user):
        raise HTTPException(409, "You already have scout access.")

    price_id = await _get_scout_access_price_id(tier)
    if not price_id:
        await _ensure_scout_access_products()
        price_id = await _get_scout_access_price_id(tier)
        if not price_id:
            raise HTTPException(503, f"Stripe scout-access price for '{tier}' not provisioned yet — try again.")

    # Persist the verification info onto the user right away (survives even if
    # the buyer bails from the Stripe page — we still have their intent).
    if payload.verification:
        v = payload.verification.dict(exclude_unset=True)
        if v:
            v["updated_at"] = now_iso()
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"scout_verification": v}},
            )

    origin = payload.origin_url.rstrip("/")
    success_url = f"{origin}/players-database?scout_session={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/scouts?scout_canceled=1"

    metadata = _build_embedded_metadata({
        "kind": "scout_access",
        "tier": tier,
        "user_id": user["id"],
        "user_email": user["email"],
        "billing": "one_time",
    })

    try:
        _arm_real_stripe()
        # ONE-TIME payment (not subscription). Uses mode="payment".
        session_kwargs = dict(
            mode="payment",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata,
            payment_intent_data={"metadata": metadata},
            customer_email=user["email"],
            allow_promotion_codes=True,
        )
        session = stripe_sdk.checkout.Session.create(**session_kwargs)
    except Exception as e:
        logger.exception("Stripe scout-access session create failed")
        raise HTTPException(500, f"Stripe error: {e}")

    await db.payment_transactions.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session.id,
        "user_id": user["id"],
        "user_email": user["email"],
        "report_id": None,
        "kind": "scout_access",
        "tier": tier,
        "ui_mode": "hosted",
        "brand": "ScoutMePlay",
        "amount": SCOUT_ACCESS_TIERS[tier]["amount"],
        "currency": PRICE_CURRENCY,
        "metadata": metadata,
        "payment_status": "initiated",
        "status": "open",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })

    return {"url": session.url, "session_id": session.id}


@api_router.get("/scout-access/status/{session_id}")
async def get_scout_access_status(session_id: str, user=Depends(get_current_user)):
    """Poll endpoint after Stripe redirect back. Idempotently credits scout_access.
    Fase 2 update — one-time payment: no subscription object, lifetime access."""
    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not txn:
        raise HTTPException(404, "Session not found")
    if txn["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(403, "Not authorized")

    if txn.get("payment_status") == "paid" and txn.get("credited"):
        u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
        return {"payment_status": "paid", "status": "complete", "kind": "scout_access",
                "tier": txn.get("tier"), "scout_access": (u or {}).get("scout_access")}

    if not _embedded_ready():
        raise HTTPException(503, "Stripe not configured.")

    try:
        _arm_real_stripe()
        session = stripe_sdk.checkout.Session.retrieve(session_id)
    except Exception as e:
        raise HTTPException(500, f"Stripe error: {e}")

    ps = getattr(session, "payment_status", None) or session.get("payment_status", None)
    if ps == "paid":
        tier_id = txn["tier"]
        tier_conf = SCOUT_ACCESS_TIERS.get(tier_id, {})
        scout_access_state = {
            "tier": tier_id,
            "status": "active",
            "one_time": True,
            "stripe_customer_id": getattr(session, "customer", None) or session.get("customer", None),
            "stripe_payment_intent": getattr(session, "payment_intent", None) or session.get("payment_intent", None),
            "current_period_end": None,  # lifetime
            "monthly_reveals": tier_conf.get("monthly_reveals"),
            "seats": tier_conf.get("seats", 1),
            "reveals_used_this_period": 0,
            "started_at": now_iso(),
            "verified": False,  # admin must review + verify
        }
        role_hint = tier_conf.get("role_hint", "scout_client")
        set_ops = {"scout_access": scout_access_state}
        u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "role": 1})
        if (u or {}).get("role") in (None, "user"):
            set_ops["role"] = role_hint
        await db.users.update_one({"id": user["id"]}, {"$set": set_ops})
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": "paid", "status": "complete", "credited": True, "updated_at": now_iso()}},
        )
        fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
        return {"payment_status": "paid", "status": "complete", "kind": "scout_access",
                "tier": tier_id, "scout_access": (fresh or {}).get("scout_access")}

    return {"payment_status": ps or "pending", "status": "open", "kind": "scout_access"}


# ============== ROUTES: PLAYERS DATABASE (Scout-facing) ==============
# Search index of discoverable players. Access-gated behind an active scout access
# subscription. Contact info is hidden by default and revealed via /reveal endpoint.

def _player_report_summary(reports: list) -> dict:
    """Aggregates a small stats summary from a player's paid reports."""
    if not reports:
        return {"reports_count": 0, "highest_overall": None, "latest_report_id": None,
                "poster_url": None, "positions": []}
    scores = []
    positions = set()
    latest_report_id = reports[0].get("id")
    poster_url = None
    for r in reports:
        pv = r.get("preview") or {}
        overall = pv.get("overall") or pv.get("overall_score")
        if isinstance(overall, (int, float)):
            scores.append(float(overall))
        pd = r.get("player_details") or {}
        if pd.get("position"):
            positions.add(str(pd["position"]))
        if not poster_url and r.get("poster_filename"):
            poster_url = f"/api/uploads/{r['poster_filename']}"
    return {
        "reports_count": len(reports),
        "highest_overall": round(max(scores), 1) if scores else None,
        "latest_report_id": latest_report_id,
        "poster_url": poster_url,
        "positions": sorted(positions),
    }


def _serialize_public_player(user_doc: dict, summary: dict, include_contact: bool = False) -> dict:
    pp = user_doc.get("public_profile") or {}
    avatar_filename = user_doc.get("avatar_filename")
    age = None
    if user_doc.get("birth_year"):
        try:
            age = datetime.now(timezone.utc).year - int(user_doc["birth_year"])
        except Exception:
            age = None
    return {
        "id": user_doc.get("id"),
        "display_name": user_doc.get("full_name"),
        "avatar_url": f"/api/uploads/{avatar_filename}" if avatar_filename else None,
        "age": age,
        "birth_year": user_doc.get("birth_year"),
        "position": pp.get("position"),
        "preferred_foot": pp.get("preferred_foot"),
        "height_cm": pp.get("height_cm"),
        "weight_kg": pp.get("weight_kg"),
        "country": pp.get("country"),
        "club": pp.get("club"),
        "bio": pp.get("bio"),
        "reports_count": summary.get("reports_count", 0),
        "highest_overall": summary.get("highest_overall"),
        "latest_report_id": summary.get("latest_report_id"),
        "poster_url": summary.get("poster_url"),
        "positions_played": summary.get("positions", []),
        "contact_email": user_doc.get("email") if include_contact else None,
        "contact_revealed": include_contact,
    }


@api_router.get("/players-database/search")
async def players_database_search(
    position: Optional[str] = None,
    country: Optional[str] = None,
    min_age: Optional[int] = None,
    max_age: Optional[int] = None,
    preferred_foot: Optional[str] = None,
    min_overall: Optional[float] = None,
    q: Optional[str] = None,
    limit: int = 24,
    skip: int = 0,
    user=Depends(_require_scout_access),
):
    """Paid scout search — returns discoverable players filtered by criteria."""
    limit = max(1, min(int(limit), 60))
    skip = max(0, int(skip))
    query = {"discoverable": True}
    if position:
        query["public_profile.position"] = position.upper()
    if country:
        query["public_profile.country"] = {"$regex": f"^{country}$", "$options": "i"}
    if preferred_foot:
        query["public_profile.preferred_foot"] = preferred_foot.lower()
    if min_age is not None or max_age is not None:
        current_year = datetime.now(timezone.utc).year
        by_query = {}
        if min_age is not None:
            by_query["$lte"] = current_year - int(min_age)
        if max_age is not None:
            by_query["$gte"] = current_year - int(max_age)
        if by_query:
            query["birth_year"] = by_query
    if q:
        query["$or"] = [
            {"full_name": {"$regex": q, "$options": "i"}},
            {"public_profile.club": {"$regex": q, "$options": "i"}},
            {"public_profile.bio": {"$regex": q, "$options": "i"}},
        ]

    total = await db.users.count_documents(query)
    cursor = db.users.find(query, {"_id": 0, "password_hash": 0}).sort("discoverable_updated_at", -1).skip(skip).limit(limit)

    scout_user_id = user["id"]
    revealed = set(
        (user.get("scout_access") or {}).get("revealed_player_ids") or []
    )

    out = []
    async for u in cursor:
        # Aggregate report summary
        r_cursor = db.reports.find(
            {"user_id": u["id"], "$or": [{"is_paid": True}, {"manually_unlocked": True}]},
            {"_id": 0, "id": 1, "player_details": 1, "preview": 1, "poster_filename": 1, "created_at": 1},
        ).sort("created_at", -1).limit(10)
        reports = [r async for r in r_cursor]
        summary = _player_report_summary(reports)
        if min_overall is not None and (summary.get("highest_overall") or 0) < float(min_overall):
            continue
        include_contact = u["id"] in revealed
        out.append(_serialize_public_player(u, summary, include_contact=include_contact))

    return {
        "total": total,
        "limit": limit,
        "skip": skip,
        "results": out,
        "filters_applied": {
            "position": position, "country": country, "min_age": min_age, "max_age": max_age,
            "preferred_foot": preferred_foot, "min_overall": min_overall, "q": q,
        },
        "scout_id": scout_user_id,
    }


@api_router.get("/players-database/player/{player_id}")
async def players_database_player_detail(player_id: str, user=Depends(_require_scout_access)):
    p = await db.users.find_one({"id": player_id, "discoverable": True}, {"_id": 0, "password_hash": 0})
    if not p:
        raise HTTPException(404, "Player not found or not discoverable")
    r_cursor = db.reports.find(
        {"user_id": p["id"], "$or": [{"is_paid": True}, {"manually_unlocked": True}]},
        {"_id": 0, "id": 1, "player_details": 1, "preview": 1, "poster_filename": 1, "created_at": 1},
    ).sort("created_at", -1).limit(10)
    reports = [r async for r in r_cursor]
    summary = _player_report_summary(reports)
    revealed = set((user.get("scout_access") or {}).get("revealed_player_ids") or [])
    include_contact = p["id"] in revealed or user.get("role") == "admin"
    return {
        "player": _serialize_public_player(p, summary, include_contact=include_contact),
        "reports": [
            {
                "id": r["id"],
                "player_details": r.get("player_details"),
                "poster_url": f"/api/uploads/{r['poster_filename']}" if r.get("poster_filename") else None,
                "preview_overall": (r.get("preview") or {}).get("overall") or (r.get("preview") or {}).get("overall_score"),
                "created_at": r.get("created_at"),
            }
            for r in reports
        ],
    }


@api_router.post("/players-database/reveal/{player_id}")
async def players_database_reveal(player_id: str, user=Depends(_require_scout_access)):
    """Deduct one reveal from the scout's monthly quota (or unlimited) and mark the
    player as revealed for THIS scout. Also emails the player that a scout viewed them."""
    p = await db.users.find_one({"id": player_id, "discoverable": True}, {"_id": 0, "password_hash": 0})
    if not p:
        raise HTTPException(404, "Player not found or not discoverable")

    sa = user.get("scout_access") or {}
    tier_conf = SCOUT_ACCESS_TIERS.get(sa.get("tier") or "", {})
    limit = tier_conf.get("monthly_reveals")  # None => unlimited
    revealed = list(sa.get("revealed_player_ids") or [])
    already_revealed = player_id in revealed

    # Roll over period if needed
    rollover = _scout_reveal_period_state({"scout_access": sa})
    used = int(rollover.get("reveals_used_this_period", sa.get("reveals_used_this_period") or 0))

    if not already_revealed:
        if limit is not None and used >= limit:
            raise HTTPException(status_code=402, detail=f"Reveal quota reached ({limit}/month). Upgrade to Scout Pro for unlimited reveals.")
        revealed.append(player_id)
        used += 1

    updates = {
        "scout_access.revealed_player_ids": revealed,
        "scout_access.reveals_used_this_period": used,
    }
    if rollover:
        updates["scout_access.reveal_period_marker"] = rollover.get("reveal_period_marker")

    await db.users.update_one({"id": user["id"]}, {"$set": updates})

    # Fire courtesy notification to the player (never blocks)
    if not already_revealed:
        try:
            scout_name = user.get("full_name") or user.get("email")
            html_body = f"""
            <p>A professional scout has viewed your ScoutMePlay profile.</p>
            <p><strong>{scout_name}</strong> has requested to see your contact information.
            They found you through the ScoutMePlay Scout Database.</p>
            <p>You don't need to do anything — this is a heads-up that your visibility is working.</p>
            <p>If you'd rather not be found by scouts, you can switch off visibility any time from your dashboard.</p>
            """
            from email_templates import render_bulk_email
            html, text, subject = render_bulk_email(
                subject="A scout viewed your ScoutMePlay profile",
                body_html=html_body,
                preheader=f"{scout_name} viewed your profile",
            )
            asyncio.create_task(send_email_async(p["email"], subject, html, text))
        except Exception as exc:
            logger.warning("Scout-reveal courtesy email failed: %s", exc)

    return {
        "ok": True,
        "player_id": player_id,
        "contact_email": p.get("email"),
        "reveals_used_this_period": used,
        "reveals_remaining": None if limit is None else max(0, limit - used),
        "already_revealed": already_revealed,
    }


@app.on_event("shutdown")
async def on_shutdown():
    client.close()


# ============== ADMIN: Scout verification management ==============
# Fase 2 verification workflow — payment grants access, admin manually adds the
# "Verified" badge so real professionals stand out from paying-but-unvetted
# accounts. Admin can also REVOKE access here if abuse is detected.

@api_router.get("/admin/scouts")
async def admin_list_scouts(_=Depends(get_current_admin)):
    """List every user with a scout_access record — verified or not."""
    cursor = db.users.find(
        {"scout_access.status": {"$in": ["active", "revoked"]}},
        {"_id": 0, "password_hash": 0},
    ).sort("scout_access.started_at", -1)
    out = []
    async for u in cursor:
        sa = u.get("scout_access") or {}
        v = u.get("scout_verification") or {}
        out.append({
            "user_id": u.get("id"),
            "email": u.get("email"),
            "full_name": u.get("full_name"),
            "role": u.get("role"),
            "tier": sa.get("tier"),
            "status": sa.get("status"),
            "verified": bool(sa.get("verified")),
            "started_at": sa.get("started_at"),
            "revoked_at": sa.get("revoked_at"),
            "revoked_reason": sa.get("revoked_reason"),
            "verification": {
                "organization_name": v.get("organization_name"),
                "organization_type": v.get("organization_type"),
                "role_title": v.get("role_title"),
                "country": v.get("country"),
                "website": v.get("website"),
                "linkedin_url": v.get("linkedin_url"),
                "phone": v.get("phone"),
                "notes": v.get("notes"),
                "updated_at": v.get("updated_at"),
            },
        })
    return {"scouts": out, "count": len(out)}


class AdminScoutVerifyPayload(BaseModel):
    verified: bool


@api_router.put("/admin/scouts/{user_id}/verify")
async def admin_toggle_verified(user_id: str, payload: AdminScoutVerifyPayload, _=Depends(get_current_admin)):
    """Toggle the 'Verified' badge on a scout/club account. Doesn't affect access."""
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "scout_access": 1})
    if not u:
        raise HTTPException(404, "User not found")
    if not u.get("scout_access"):
        raise HTTPException(400, "User has no scout_access record")
    updates = {
        "scout_access.verified": bool(payload.verified),
        "scout_access.verified_at": now_iso() if payload.verified else None,
    }
    await db.users.update_one({"id": user_id}, {"$set": updates})
    return {"ok": True, "user_id": user_id, "verified": bool(payload.verified)}


class AdminScoutRevokePayload(BaseModel):
    reason: Optional[str] = None


@api_router.put("/admin/scouts/{user_id}/revoke")
async def admin_revoke_scout(user_id: str, payload: AdminScoutRevokePayload, _=Depends(get_current_admin)):
    """Immediately revoke a scout/club's database access (e.g. for abuse)."""
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "scout_access": 1})
    if not u:
        raise HTTPException(404, "User not found")
    if not u.get("scout_access"):
        raise HTTPException(400, "User has no scout_access record")
    updates = {
        "scout_access.status": "revoked",
        "scout_access.revoked_at": now_iso(),
        "scout_access.revoked_reason": (payload.reason or "").strip() or None,
    }
    await db.users.update_one({"id": user_id}, {"$set": updates})
    return {"ok": True, "user_id": user_id, "revoked": True}


@api_router.put("/admin/scouts/{user_id}/restore")
async def admin_restore_scout(user_id: str, _=Depends(get_current_admin)):
    """Restore a previously revoked scout/club."""
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "scout_access": 1})
    if not u or not u.get("scout_access"):
        raise HTTPException(404, "User or scout access not found")
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"scout_access.status": "active", "scout_access.revoked_at": None, "scout_access.revoked_reason": None}},
    )
    return {"ok": True, "user_id": user_id, "restored": True}


# Register the API router LAST so it includes every @api_router route defined above
# (including scout-access + players-database endpoints in Fase 2).
app.include_router(api_router)
