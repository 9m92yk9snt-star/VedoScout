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
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple

import bcrypt
import jwt as pyjwt
from dotenv import load_dotenv
import httpx
from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form, Request, status, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
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

# ---- Setup ----
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

UPLOAD_DIR = ROOT_DIR / "uploads"
PDF_DIR = ROOT_DIR / "pdfs"
UPLOAD_DIR.mkdir(exist_ok=True)
# Bump this whenever PDF rendering changes (new sections, layout shifts, etc.).
# Each PDF is cached on disk keyed by report_id + this version, so a bump
# invalidates every stale PDF without losing the current ones.
PDF_RENDER_VERSION = 9  # v9 = 60-Second Scout Summary page + footer report ID


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
DEFAULT_PRICE = float(os.environ.get("DEFAULT_REPORT_PRICE_USD", "1"))
PRICE_CURRENCY = os.environ.get("DEFAULT_REPORT_CURRENCY", "usd").lower()

# ---- App ----
app = FastAPI(title="Elite Football AI Scout API")
api_router = APIRouter(prefix="/api")

# Mount uploads as static (under /api so Kubernetes ingress routes it to backend)
app.mount("/api/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

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
    when the video file is missing or ffmpeg fails."""
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

    enriched = []
    for idx, c in enumerate(comments):
        if not isinstance(c, dict):
            enriched.append(c)
            continue
        ts = c.get("timestamp", "")
        out_path = frames_dir / f"frame_{idx:02d}.jpg"
        if not out_path.exists():
            ok = False
            if have_video:
                seconds = _ts_to_seconds(ts)
                if seconds is not None:
                    ok = _extract_video_frame(video_path, seconds, out_path)
            if not ok:
                _make_placeholder_frame(ts, c.get("comment", ""), out_path)
        out = dict(c)
        out["frame_url"] = f"/api/uploads/frames/{report_id}/{out_path.name}"
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
    password: str = Field(min_length=6)
    full_name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    created_at: str


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


class CheckoutInit(BaseModel):
    report_id: str
    origin_url: str


class PrepayUploadInit(BaseModel):
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

🎯 GROUND RULE — EVIDENCE OR SILENCE
Every observation must come from what you actually SAW in the clip. If you can't see it, say so — never invent.

🎯 LANGUAGE
Plain, natural football coach language. AVOID jargon like "press-resistant", "scanning frequency", "line-breaking", "half-turn", "high-intensity transitions", "vertical progression". Use phrases like "stays calm under pressure", "always looks around before the ball arrives", "his left foot is dangerous", "gets tired late in the game".

🎯 PLAYER IDENTIFICATION
A reference frame is attached. The player to analyse is the ONE CIRCLED IN BRIGHT GREEN with the label "THIS PLAYER". Track ONLY that player. Note their jersey colour, number, body type, hair, distinguishing features. Ignore everyone else.

🎯 CONTENT CONTEXT (from pre-analysis)
CONTENT_TYPE: {content_type}
PLAYER_VISIBILITY: {player_visible}
CAMERA_DISTANCE: {camera_distance}

🎯 PLAYER DETAILS
{player_details}

Produce a JSON object EXACTLY in this format:

{
  "player_type": "<short, friendly label e.g. 'Smart playmaker with a strong left foot' — based on observation>",
  "brief_summary": "<2-3 sentences about how THE CIRCLED PLAYER plays based ONLY on what you saw>",
  "top_strengths": ["<observed strength 1>", "<observed strength 2>", "<observed strength 3>"],
  "area_for_improvement": "<one specific area, only if visible in the clip — otherwise 'Need more footage to spot an improvement area'>",
  "evidence_note": "<one short sentence about what kind of moments you observed (e.g., 'Saw 5 clear touches and 2 passes in the clip')>",
  "confidence": "high" | "medium" | "low",
  "confidence_reason": "<one sentence — e.g. 'Player visible for most of the clip with multiple touches' or 'Only 2 brief on-ball moments visible'>",
  "sample_section": {
    "title": "Sample: Technical Snapshot",
    "content": "<3-4 sentence teaser of the deeper technical breakdown — still in natural football language, still evidence-based>"
  }
}

CRITICAL:
- Independent developmental feedback — do NOT imply trials, contracts, selection
- Evidence-only — never invent or guess
- Return ONLY valid JSON, no markdown, no commentary
"""


FULL_REPORT_PROMPT = """You are an experienced football scout writing a PREMIUM, EVIDENCE-BASED development report for a young player.

🎯 GROUND RULE — EVIDENCE OR SILENCE
Every score and every claim must come from something you actually OBSERVED in the video. If you cannot see it, set "cannot_evaluate": true with a reason. NEVER guess.

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


async def call_gemini_with_video(session_id: str, prompt: str, video_path: str, marker_path: Optional[str] = None) -> dict:
    """Send a video file (+ optional marker image) + prompt to Gemini and return parsed JSON."""
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message="You are an experienced football coach giving honest, friendly feedback to a young player and their family. You speak in plain, natural football language — never jargon. You ALWAYS respond with valid JSON only.",
    ).with_model("gemini", "gemini-2.5-pro")

    file_contents = []
    if marker_path and Path(marker_path).exists():
        marker_file = FileContentWithMimeType(
            file_path=marker_path,
            mime_type="image/jpeg",
        )
        file_contents.append(marker_file)
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
async def signup(payload: UserSignup):
    existing = await db.users.find_one({"email": payload.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = str(uuid.uuid4())
    user_doc = {
        "id": user_id,
        "email": payload.email.lower(),
        "password_hash": hash_password(payload.password),
        "full_name": payload.full_name,
        "role": "user",
        "created_at": now_iso(),
    }
    await db.users.insert_one(user_doc)
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
async def login(payload: UserLogin):
    user = await db.users.find_one({"email": payload.email.lower()})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user["id"], user["email"], user["role"])
    return TokenResponse(
        access_token=token,
        user=UserPublic(
            id=user["id"],
            email=user["email"],
            full_name=user["full_name"],
            role=user["role"],
            created_at=user["created_at"],
        ),
    )


@api_router.get("/auth/me", response_model=UserPublic)
async def me(user=Depends(get_current_user)):
    return UserPublic(
        id=user["id"],
        email=user["email"],
        full_name=user["full_name"],
        role=user["role"],
        created_at=user["created_at"],
    )


# ============== ROUTES: VIDEO UPLOAD & FREE PREVIEW ==============

@api_router.get("/settings/price")
async def public_price():
    doc = await db.settings.find_one({"key": "report_price"}, {"_id": 0})
    value = doc.get("value", DEFAULT_PRICE) if doc else DEFAULT_PRICE
    # `price_dkk` is kept only as a legacy alias for older frontend builds
    return {"price": float(value), "currency": PRICE_CURRENCY, "price_dkk": float(value)}


async def get_current_price() -> float:
    doc = await db.settings.find_one({"key": "report_price"})
    if doc and "value" in doc:
        return float(doc["value"])
    return DEFAULT_PRICE


@api_router.post("/reports/upload")
async def upload_video_and_create_preview(
    background: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    temp_video_token: Optional[str] = Form(None),
    marker_image: UploadFile = File(...),
    marker_timestamp: float = Form(0.0),
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

    # Save marker image (the frame with the player circled)
    marker_filename = f"{report_id}-marker.jpg"
    marker_path = UPLOAD_DIR / marker_filename
    with marker_path.open("wb") as buffer:
        shutil.copyfileobj(marker_image.file, buffer)

    # Convert video to a web-friendly MP4 (H.264) so it plays in every browser.
    web_path = transcode_to_web_mp4(file_path)
    web_filename = web_path.name

    # Enforce 5-minute (300 sec) cap server-side
    duration_sec = get_video_duration_seconds(web_path)
    if duration_sec > 305:  # tiny buffer for rounding
        # cleanup
        for p in {file_path, web_path, marker_path}:
            try:
                p.unlink()
            except Exception:
                pass
        raise HTTPException(
            status_code=400,
            detail=f"Video is {duration_sec / 60:.1f} minutes. Maximum is 5 minutes — please trim and try again.",
        )

    # Generate poster thumbnail from the playable video
    poster_path = generate_poster(web_path)
    poster_filename = poster_path.name if poster_path else None

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
    details_str = json.dumps(details, ensure_ascii=False)

    # Build a short preview clip (15s window around the marker) for the FREE preview
    preview_clip_path = make_preview_clip(web_path, marker_seconds=marker_timestamp, window_seconds=15)

    # ============== CONTENT GATE ==============
    # Validate the clip is actually football and the player is visible. Rejects
    # non-football videos, unwatchable footage, or clips where the marked player
    # never appears. This protects users from spending tokens / paying for noise.
    gate = await run_content_gate(report_id, preview_clip_path, marker_path)
    rejection = gate_rejection_message(gate)
    if rejection:
        for p in {file_path, web_path, marker_path, preview_clip_path}:
            try:
                p.unlink()
            except Exception:
                pass
        if poster_path:
            try:
                poster_path.unlink()
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=rejection)

    # Generate FREE preview synchronously (Gemini receives marker image + short clip).
    # The prompt is content-aware: it adapts to the gate's content_type and visibility findings.
    try:
        preview_prompt = (
            PREVIEW_PROMPT
            .replace("{player_details}", details_str)
            .replace("{content_type}", str(gate.get("content_type", "other")))
            .replace("{player_visible}", str(gate.get("player_visible", "clear")))
            .replace("{camera_distance}", str(gate.get("camera_distance", "medium")))
        )
        preview = await call_gemini_with_video(
            session_id=f"preview-{report_id}",
            prompt=preview_prompt,
            video_path=str(preview_clip_path),
            marker_path=str(marker_path),
        )
    except HTTPException:
        # Cleanup on failure
        for p in {file_path, web_path, marker_path, preview_clip_path}:
            try:
                p.unlink()
            except Exception:
                pass
        if poster_path:
            try:
                poster_path.unlink()
            except Exception:
                pass
        raise
    except Exception as e:
        logger.exception("Preview generation failed")
        for p in {file_path, web_path, marker_path, preview_clip_path}:
            try:
                p.unlink()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"AI preview generation failed: {str(e)}")

    # Persist report
    report_doc = {
        "id": report_id,
        "user_id": user["id"],
        "user_email": user["email"],
        "player_details": details,
        "video_filename": web_filename,
        "original_video_filename": stored_name if stored_name != web_filename else None,
        "poster_filename": poster_filename,
        "marker_filename": marker_filename,
        "marker_timestamp": float(marker_timestamp),
        "video_duration_sec": duration_sec,
        "video_size_bytes": file_size,
        "content_gate": gate,
        "preview": preview,
        "full_report": None,
        "is_paid": bool(upload_will_be_paid),
        "manually_unlocked": False,
        "created_at": now_iso(),
        "paid_at": now_iso() if upload_will_be_paid else None,
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
    if not is_admin:
        if used_pass_credit:
            # Burn one Progress Pass credit and trigger full report generation
            await consume_pass_credit(db, user["id"])
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"last_upload_at": now_iso()}},
            )
            background.add_task(generate_full_report_task, report_id)
        elif upload_will_be_paid:
            # Pre-paid upload — consume one credit; full report will be auto-generated below
            await db.users.update_one(
                {"id": user["id"]},
                {"$inc": {"prepaid_uploads": -1}, "$set": {"last_upload_at": now_iso()}},
            )
            # Schedule full premium report generation (same path as paid checkout flow)
            background.add_task(generate_full_report_task, report_id)
        elif not free_used:
            # First free preview consumed
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"free_preview_used": True, "last_upload_at": now_iso()}},
            )

    return {
        "id": report_id,
        "player_details": details,
        "video_url": f"/api/uploads/{web_filename}",
        "poster_url": f"/api/uploads/{poster_filename}" if poster_filename else None,
        "marker_url": f"/api/uploads/{marker_filename}",
        "preview": preview,
        "is_paid": False,
        "created_at": report_doc["created_at"],
    }


@api_router.get("/reports/mine")
async def my_reports(user=Depends(get_current_user)):
    docs = await db.reports.find(
        {"user_id": user["id"]},
        {"_id": 0, "full_report": 0},
    ).sort("created_at", -1).to_list(100)
    for d in docs:
        d["video_url"] = f"/api/uploads/{d['video_filename']}"
        d["poster_url"] = f"/api/uploads/{d['poster_filename']}" if d.get("poster_filename") else None
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
    poster_filename = doc.get("poster_filename")
    marker_filename = doc.get("marker_filename")
    out = {
        "id": doc["id"],
        "user_id": doc["user_id"],
        "user_email": doc.get("user_email"),
        "player_details": doc["player_details"],
        "video_url": f"/api/uploads/{doc['video_filename']}",
        "poster_url": f"/api/uploads/{poster_filename}" if poster_filename else None,
        "marker_url": f"/api/uploads/{marker_filename}" if marker_filename else None,
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
async def generate_full_report(report_id: str, user=Depends(get_current_user)):
    """Generate the full premium report (called after payment confirmed or by admin)."""
    doc = await db.reports.find_one({"id": report_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")
    if doc["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    unlocked = doc.get("is_paid") or doc.get("manually_unlocked") or user["role"] == "admin"
    if not unlocked:
        raise HTTPException(status_code=402, detail="Payment required")

    if doc.get("full_report"):
        return {"status": "exists", "report_id": report_id}

    file_path = UPLOAD_DIR / doc["video_filename"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Video file missing")

    marker_path = None
    if doc.get("marker_filename"):
        mp = UPLOAD_DIR / doc["marker_filename"]
        if mp.exists():
            marker_path = str(mp)

    details_str = json.dumps(doc["player_details"], ensure_ascii=False)
    # Pull the gate info captured at upload time so the full report adapts to content type.
    gate = doc.get("content_gate") or {}
    try:
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
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Full report generation failed")
        raise HTTPException(status_code=500, detail=f"AI full report failed: {str(e)}")

    await db.reports.update_one(
        {"id": report_id},
        {"$set": {"full_report": full, "full_generated_at": now_iso()}},
    )
    return {"status": "generated", "report_id": report_id}


async def generate_full_report_task(report_id: str) -> None:
    """Fire-and-forget full report generation (used after Stripe payment OR auto-paid uploads)."""
    try:
        doc = await db.reports.find_one({"id": report_id})
        if not doc or doc.get("full_report"):
            return
        file_path = UPLOAD_DIR / doc["video_filename"]
        if not file_path.exists():
            logger.warning(f"generate_full_report_task: video missing for {report_id}")
            return

        marker_path = None
        if doc.get("marker_filename"):
            mp = UPLOAD_DIR / doc["marker_filename"]
            if mp.exists():
                marker_path = str(mp)

        details_str = json.dumps(doc["player_details"], ensure_ascii=False)
        gate = doc.get("content_gate") or {}
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
        )
        await db.reports.update_one(
            {"id": report_id},
            {"$set": {"full_report": full, "full_generated_at": now_iso()}},
        )
    except Exception:
        logger.exception(f"generate_full_report_task failed for {report_id}")


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
            "video_url": f"/api/uploads/{d['video_filename']}",
            "poster_url": f"/api/uploads/{d['poster_filename']}" if d.get("poster_filename") else None,
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
        textColor=_PDF_INK, leftIndent=12, bulletIndent=0, spaceAfter=4,
    ))
    return styles


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

    # Footer line + brand + page number
    canv.setStrokeColor(_PDF_BORDER)
    canv.setLineWidth(0.4)
    canv.line(1.6 * cm, 1.55 * cm, w - 1.6 * cm, 1.55 * cm)

    canv.setFillColor(_PDF_FOREST)
    canv.setFont("Helvetica-Bold", 7.5)
    canv.drawString(1.6 * cm, 1.05 * cm, "SCOUTMEPLAY · MENTALKIDS")
    canv.setFillColor(_PDF_MUTED)
    canv.setFont("Helvetica", 7.5)
    canv.drawString(5.4 * cm, 1.05 * cm, "Professional player development report")
    canv.drawRightString(w - 1.6 * cm, 1.05 * cm, f"Page {doc.page}")

    canv.restoreState()


def _draw_cover_background(canv, doc):
    """Cover page background: cream + large forest panel on the left,
    big ScoutMePlay wordmark at the top.
    """
    canv.saveState()
    w, h = doc.pagesize

    # Cream base
    canv.setFillColor(_PDF_CREAM)
    canv.rect(0, 0, w, h, fill=1, stroke=0)

    # Forest left panel (1/3 width)
    panel_w = w * 0.34
    canv.setFillColor(_PDF_FOREST)
    canv.rect(0, 0, panel_w, h, fill=1, stroke=0)

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

    # Bottom-left footer on the green panel
    canv.setFillColor(HexColor("#FFFFFFAA"))
    canv.setFont("Helvetica", 7)
    canv.drawString(1.6 * cm, 1.0 * cm, "MENTALKIDS / Denmark")
    canv.setFont("Helvetica-Bold", 7)
    canv.drawString(1.6 * cm, 0.55 * cm, "SCOUTMEPLAY.COM")

    canv.restoreState()


# ---- Reusable visual primitives ----

def _section_header(title: str, styles, idx: int = None):
    """Forest eyebrow + big ink title + thin forest underline.
    Returned as a Table so the underline visually 'hangs' under the title."""
    eyebrow_text = f"SECTION {idx:02d}" if idx else "ANALYSIS"
    eyebrow = Paragraph(eyebrow_text, styles["SectionEyebrow"])
    head = Paragraph(title, styles["SectionTitle"])

    # underline accent (thin green line)
    line = Table([[""]], colWidths=[2.4 * cm], rowHeights=[0.07 * cm])
    line.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _PDF_FOREST),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [eyebrow, head, line, Spacer(1, 0.35 * cm)]


def _score_pill(score) -> str:
    """Inline score formatting for table cells."""
    try:
        s = float(score)
        return f"<font color='#1F4F2F'><b>{s:g}</b></font><font color='#9CA3AF'> / 10</font>"
    except Exception:
        return "<font color='#9CA3AF'>—</font>"


def _score_table(rows, styles):
    """Premium attribute table with alternating cream rows + forest accents."""
    data = [["ATTRIBUTE", "SCORE", "NOTES"]]
    for label, score, notes in rows:
        data.append([
            Paragraph(f"<b>{label}</b>", styles["BodyW"]),
            Paragraph(_score_pill(score), styles["BodyW"]),
            Paragraph(notes or "—", styles["BodyMuted"]),
        ])
    t = Table(data, colWidths=[4.5 * cm, 2.5 * cm, 9 * cm], repeatRows=1)
    style = [
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), _PDF_FOREST),
        ("TEXTCOLOR",  (0, 0), (-1, 0), HexColor("#FFFFFF")),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 8),
        ("ALIGN",      (0, 0), (-1, 0), "LEFT"),
        ("ALIGN",      (1, 0), (1, 0),  "CENTER"),
        # Body
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.25, _PDF_BORDER),
    ]
    # Alternate row backgrounds
    for i in range(1, len(data)):
        bg = _PDF_CARD if i % 2 == 1 else _PDF_CREAM_S
        style.append(("BACKGROUND", (0, i), (-1, i), bg))
    # Score column right-accent
    style.append(("ALIGN", (1, 1), (1, -1), "CENTER"))
    t.setStyle(TableStyle(style))
    return t


def _list_bullets(items, styles):
    """Forest-bulleted list."""
    flow = []
    for s in items or []:
        flow.append(Paragraph(
            f"<font color='#1F4F2F'><b>▸</b></font>&nbsp;&nbsp;{s}",
            styles["BodyW"],
        ))
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
    """Big quoted highlight on the cover page."""
    rows = [
        [Paragraph("OVERALL DEVELOPMENT", styles["Label"]),
         Paragraph("PLAYER TYPE", styles["Label"])],
        [Paragraph(f"<font color='#1F4F2F' size='28'><b>{overall}</b></font>"
                   f"<font color='#9CA3AF' size='14'> /10</font>", styles["BodyW"]),
         Paragraph(f"<font size='13'><b>{player_type or 'Independent'}</b></font>", styles["BodyW"])],
    ]
    t = Table(rows, colWidths=[5.6 * cm, 5.6 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _PDF_CARD),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("TOPPADDING",    (0, 0), (0, 0),   12),
        ("TOPPADDING",    (0, 1), (-1, 1),  4),
        ("BOTTOMPADDING", (0, 1), (-1, 1),  14),
        ("BOTTOMPADDING", (0, 0), (-1, 0),  0),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.4, _PDF_BORDER),
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
        score_para = Paragraph(
            "<font color='#D97706' size='8'><b>NEED MORE FOOTAGE</b></font>",
            styles["BodyW"],
        )
    else:
        score_para = Paragraph(
            f"<font color='#1F4F2F' size='22'><b>{score if score is not None else '—'}</b></font>"
            f"<font color='#9CA3AF' size='10'> / 10</font>",
            styles["BodyW"],
        )
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
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (0, 0),   "TOP"),
        ("VALIGN",        (1, 0), (1, 0),   "TOP"),
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

    # Score + Archetype card (2 cols)
    score_block = Paragraph(
        f"<font color='#1F4F2F' size='8'><b>SCOUT SCORE</b></font><br/>"
        f"<font color='#0A0F0D' size='36'><b>{overall_str}</b></font>"
        f"<font color='#0A0F0D' size='14'> / 10</font>",
        styles["BodyW"],
    )
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
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
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
    hero_left = Paragraph(
        f"<font color='#FFFFFF' size='7.5'><b>HOW YOU COMPARE</b></font><br/>"
        f"<font color='#FFFFFF' size='40'><b>{overall_score if overall_score is not None else '—'}</b></font>"
        f"<font color='#FFFFFF99' size='14'> /10</font><br/>"
        f"<font color='#FFFFFF' size='9'><b>{tier_label.upper()}</b></font>"
        + (f"<br/><font color='#FFFFFF80' size='7'><b>CALIBRATED FOR {bracket.upper()}</b></font>" if bracket else ""),
        styles["BodyW"],
    )

    hero_right_html = ""
    if pct:
        hero_right_html += f"<font color='#FFFFFF' size='11'>{pct}</font><br/><br/>"
    if nxt:
        hero_right_html += (
            f"<font color='#FFFFFF99' size='7'><b>REALISTIC NEXT STEP</b></font><br/>"
            f"<font color='#FFFFFF' size='9.5'>{nxt}</font><br/><br/>"
        )
    if sep:
        hero_right_html += (
            f"<font color='#FFFFFF99' size='7'><b>TO REACH THE NEXT TIER</b></font><br/>"
            f"<font color='#FFFFFF' size='9.5'>{sep}</font>"
        )
    hero_right = Paragraph(hero_right_html or "—", styles["BodyW"])

    hero = Table([[hero_left, hero_right]], colWidths=[5.4 * cm, 10.1 * cm])
    hero.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _PDF_FOREST),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("TOPPADDING",    (0, 0), (-1, -1), 18),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LINEAFTER",     (0, 0), (0, 0),   0.4, HexColor("#FFFFFF22")),
    ]))
    flow.append(hero)
    flow.append(Spacer(1, 0.45 * cm))

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
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("BACKGROUND",    (0, 0), (-1, -1), _PDF_CARD),
        ("BOX",           (0, 0), (-1, -1), 0.4, _PDF_BORDER),
    ]
    for i, k in enumerate(_TIER_ORDER):
        if k == tier_key:
            landscape_style.append(("BACKGROUND", (i, 0), (i, 0), _PDF_CREAM_S))
            landscape_style.append(("LINEBELOW", (i, 0), (i, 0), 2.5, _PDF_FOREST))
    landscape.setStyle(TableStyle(landscape_style))
    flow.append(Paragraph("TIER LANDSCAPE", styles["Label"]))
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
        Paragraph("<font color='#9CA3AF' size='6.5'><b>ATTRIBUTE</b></font>", styles["BodyW"]),
        Paragraph("<font color='#9CA3AF' size='6.5'><b>IMPORTANCE</b></font>", styles["BodyW"]),
        Paragraph("<font color='#9CA3AF' size='6.5'><b>PRO RANGE</b></font>", styles["BodyW"]),
        Paragraph("<font color='#9CA3AF' size='6.5'><b>PLAYER</b></font>", styles["BodyW"]),
        Paragraph("<font color='#9CA3AF' size='6.5'><b>STATE</b></font>", styles["BodyW"]),
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
            color = "#1F4F2F" if i < weight else "#E5E7EB"
            dots += f"<font color='{color}'>●</font> "

        attr_p = Paragraph(
            f"<font color='#0A0F0D' size='10'><b>{it.get('label', '')}</b></font><br/>"
            f"<font color='#6B7280' size='7.5'>{it.get('why_matters', '')}</font>",
            styles["BodyW"],
        )
        rows.append([
            attr_p,
            Paragraph(f"<font size='9'>{dots}</font>", styles["BodyW"]),
            Paragraph(f"<font color='#0A0F0D' size='10'><b>{it.get('pro_academy_range', '—')}</b></font>", styles["BodyW"]),
            Paragraph(
                f"<font color='#1F4F2F' size='18'><b>{it.get('player_score') if it.get('player_score') is not None else '—'}</b></font>",
                styles["BodyW"],
            ),
            Paragraph(state_html, styles["BodyW"]),
        ])

    table = Table(rows, colWidths=[6.5 * cm, 2.4 * cm, 2.0 * cm, 1.6 * cm, 3.0 * cm])
    style = [
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("ALIGN",         (3, 1), (3, -1),  "CENTER"),
        ("ALIGN",         (2, 1), (2, -1),  "CENTER"),
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
        story += _section_header("Technical analysis", styles, idx=section_idx)
        story += _skill_section_block(full["technical"], styles)
        story.append(Spacer(1, 0.4 * cm))
        section_idx += 1

    if "tactical" in full:
        story.append(PageBreak())
        story += _section_header("Tactical analysis", styles, idx=section_idx)
        story += _skill_section_block(full["tactical"], styles)
        section_idx += 1

    story.append(PageBreak())

    # ===== PHYSICAL & MENTALITY =====
    if "physical" in full:
        story += _section_header("Physical analysis", styles, idx=section_idx)
        story += _skill_section_block(full["physical"], styles)
        story.append(Spacer(1, 0.4 * cm))
        section_idx += 1

    if "mentality" in full:
        story.append(PageBreak())
        story += _section_header("Mentality analysis", styles, idx=section_idx)
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
                ex_rows.append([
                    Paragraph(f"<font color='#1F4F2F'><b>{i:02d}</b></font>", styles["BodyW"]),
                    Paragraph(
                        f"<b>{ex.get('name', '—')}</b> &nbsp;·&nbsp; "
                        f"<font color='#6B7280'>{ex.get('duration', '')}</font><br/>"
                        f"{ex.get('description', '')}",
                        styles["BodyW"],
                    ),
                ])
            et = Table(ex_rows, colWidths=[1.0 * cm, 14.5 * cm])
            et.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), _PDF_CARD),
                ("LEFTPADDING",   (0, 0), (-1, -1), 10),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
                ("TOPPADDING",    (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("VALIGN",        (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW",     (0, 0), (-1, -1), 0.4, _PDF_BORDER),
                ("LINEBEFORE",    (0, 0), (0, -1), 2.0, _PDF_FOREST),
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


# ============== PAYMENTS (STRIPE) ==============

@api_router.get("/me/upload-eligibility")
async def get_upload_eligibility(user=Depends(get_current_user)):
    """Tells the frontend whether the user can upload for free, must pre-pay, or is admin."""
    if user.get("role") == "admin":
        return {"eligible": True, "reason": "admin", "free_preview_used": True, "prepaid_uploads": 999,
                "progress_pass": {"active": False, "credits_remaining": 0}}
    free_used = bool(user.get("free_preview_used"))
    prepaid = int(user.get("prepaid_uploads", 0) or 0)
    pass_state = _progress_pass_active(user)
    if not free_used:
        return {"eligible": True, "reason": "free_preview", "free_preview_used": False,
                "prepaid_uploads": prepaid, "progress_pass": pass_state}
    if prepaid > 0:
        return {"eligible": True, "reason": "prepaid", "free_preview_used": True,
                "prepaid_uploads": prepaid, "progress_pass": pass_state}
    if pass_state.get("active"):
        return {"eligible": True, "reason": "progress_pass", "free_preview_used": True,
                "prepaid_uploads": 0, "progress_pass": pass_state}
    return {"eligible": False, "reason": "prepay_required", "free_preview_used": True,
            "prepaid_uploads": 0, "progress_pass": pass_state}


@api_router.post("/payments/prepay-upload")
async def create_prepay_upload_checkout(payload: PrepayUploadInit, request: Request, user=Depends(get_current_user)):
    """Stripe checkout for a single upload credit. On success, +1 prepaid_uploads."""
    price = await get_current_price()

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
    price = await get_current_price()
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

    return {"received": True}





# ============== ADMIN ROUTES ==============

@api_router.get("/admin/stats")
async def admin_stats(_=Depends(get_current_admin)):
    total_users = await db.users.count_documents({"role": "user"})
    total_uploads = await db.reports.count_documents({})
    total_paid = await db.reports.count_documents({"$or": [{"is_paid": True}, {"manually_unlocked": True}]})

    cursor = db.payment_transactions.find({"payment_status": "paid"}, {"_id": 0, "amount": 1, "currency": 1})
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
    # collect emails with paid reports in a single pass
    paid_emails = set()
    async for r in db.reports.find(
        {"$or": [{"is_paid": True}, {"manually_unlocked": True}]},
        {"_id": 0, "user_email": 1},
    ):
        if r.get("user_email"):
            paid_emails.add(r["user_email"].lower())
    # paid-report counts per user_id for richer display
    report_counts: Dict[str, int] = {}
    async for r in db.reports.find({}, {"_id": 0, "user_id": 1}):
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
    async for r in db.reports.find({"user_id": user_id}, {"_id": 0, "id": 1, "video_filename": 1, "poster_filename": 1, "marker_filename": 1}):
        for fname_key in ("video_filename", "poster_filename", "marker_filename"):
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
        # The Origin/Referer must look like a real browser submission for FormSubmit to accept it
        origin = "https://scout-ai-pro-1.preview.emergentagent.com"
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
        d["video_url"] = f"/api/uploads/{d['video_filename']}"
        d["poster_url"] = f"/api/uploads/{d['poster_filename']}" if d.get("poster_filename") else None
    return docs


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
    pass_price_usd=float(os.environ.get("PROGRESS_PASS_PRICE_USD", "599")),
    price_currency=PRICE_CURRENCY.lower() if PRICE_CURRENCY else "usd",
    arm_stripe_fn=_arm_real_stripe,
))
mount_blog_uploads(app)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
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


@app.on_event("shutdown")
async def on_shutdown():
    client.close()
