"""
Elite Football AI Scout Platform - Backend Server
"""
import os
import uuid
import json
import logging
import shutil
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

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
    file: UploadFile = File(...),
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
    # a pre-payment (auto-unlocks the full premium report on completion).
    is_admin = user.get("role") == "admin"
    free_used = bool(user.get("free_preview_used"))
    prepaid = int(user.get("prepaid_uploads", 0) or 0)
    upload_will_be_paid = False
    if not is_admin:
        if free_used and prepaid <= 0:
            current_price = await get_current_price()
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "PREPAY_REQUIRED",
                    "message": f"Your free preview is used. Pay ${current_price:g} to upload your next video — full premium report unlocks instantly.",
                },
            )
        upload_will_be_paid = free_used and prepaid > 0

    # Validate file type
    allowed_mimes = {"video/mp4", "video/quicktime", "video/x-m4v", "video/webm"}
    if file.content_type not in allowed_mimes:
        raise HTTPException(status_code=400, detail=f"Unsupported video format: {file.content_type}. Use MP4, MOV, or WebM.")

    # Save video file
    report_id = str(uuid.uuid4())
    ext = (file.filename or "video.mp4").split(".")[-1].lower()
    if ext not in {"mp4", "mov", "m4v", "webm"}:
        ext = "mp4"
    stored_name = f"{report_id}.{ext}"
    file_path = UPLOAD_DIR / stored_name

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

    # ============== CONSUME ELIGIBILITY ==============
    if not is_admin:
        if upload_will_be_paid:
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


def _serialize_report(doc: dict, include_full: bool) -> dict:
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
    return _serialize_report(doc, include_full=bool(unlocked))


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

    # ===== PAGE 2 — EXECUTIVE SUMMARY + SCORE OVERVIEW =====
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

    # ===== VIDEO COMMENTS =====
    if full.get("video_comments"):
        story.append(PageBreak())
        story += _section_header("Video moments", styles, idx=section_idx)
        section_idx += 1
        vc_rows = []
        for c in full["video_comments"]:
            vc_rows.append([
                Paragraph(f"<font color='#1F4F2F'><b>{c.get('timestamp', '')}</b></font>", styles["BodyW"]),
                Paragraph(c.get("comment", ""), styles["BodyW"]),
            ])
        vct = Table(vc_rows, colWidths=[2.5 * cm, 13.0 * cm])
        vct.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), _PDF_CARD),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW",     (0, 0), (-1, -1), 0.4, _PDF_BORDER),
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

    doc.build(story)


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

    pdf_path = PDF_DIR / f"{report_id}.pdf"
    if not pdf_path.exists():
        build_pdf(doc, str(pdf_path))

    player_name_safe = re.sub(r"[^A-Za-z0-9_-]", "_", doc["player_details"]["player_name"])
    filename = f"EliteScout_{player_name_safe}_Report.pdf"
    return FileResponse(str(pdf_path), media_type="application/pdf", filename=filename)


# ============== PAYMENTS (STRIPE) ==============

@api_router.get("/me/upload-eligibility")
async def get_upload_eligibility(user=Depends(get_current_user)):
    """Tells the frontend whether the user can upload for free, must pre-pay, or is admin."""
    if user.get("role") == "admin":
        return {"eligible": True, "reason": "admin", "free_preview_used": True, "prepaid_uploads": 999}
    free_used = bool(user.get("free_preview_used"))
    prepaid = int(user.get("prepaid_uploads", 0) or 0)
    if not free_used:
        return {"eligible": True, "reason": "free_preview", "free_preview_used": False, "prepaid_uploads": prepaid}
    if prepaid > 0:
        return {"eligible": True, "reason": "prepaid", "free_preview_used": True, "prepaid_uploads": prepaid}
    return {"eligible": False, "reason": "prepay_required", "free_preview_used": True, "prepaid_uploads": 0}


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
            (PDF_DIR / f"{r['id']}.pdf").unlink(missing_ok=True)
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
        (PDF_DIR / f"{report_id}.pdf").unlink(missing_ok=True)
    except Exception:
        pass
    await db.reports.delete_one({"id": report_id})
    return {"status": "deleted"}


# ============== APP WIRING ==============

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
