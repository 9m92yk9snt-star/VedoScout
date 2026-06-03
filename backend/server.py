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
  "evaluable_reason": "<ONLY when cannot_evaluate=true: ONE sentence explaining why this skill cannot be assessed from this video, e.g. 'No shooting situations were visible in the footage.'>"
}

When cannot_evaluate=true: score MUST be null, notes brief, evidence may be empty, confidence "low".

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
  "final_summary": "<3-5 sentence encouraging closing summary about THIS PLAYER, plain football language>",
  "evidence_quality_note": "<one paragraph explaining the overall evidence quality of this video — what was strong, what was missing, what kind of follow-up footage would strengthen the report>"
}

RULES FOR TOP-LEVEL "scores":
- These are AGGREGATES. Average the observable sub-skills in each category.
- If MOST sub-skills in a category are cannot_evaluate, score the category honestly low (3-5) and set scores_confidence to "low".
- If the entire category is cannot_evaluate, still give a defensible integer (e.g. 5) but set scores_confidence to "low" and reflect this in evidence_quality_note.

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
async def admin_agent_queue(_=Depends(get_current_admin)):
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
async def admin_deliver_review(report_id: str, payload: AgentReviewSubmit, admin=Depends(get_current_admin)):
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
async def admin_send_agent_message(report_id: str, payload: AgentMessageSubmit, admin=Depends(get_current_admin)):
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

def _pdf_styles():
    styles = getSampleStyleSheet()
    accent = HexColor("#CCFF00")
    muted = HexColor("#94A3B8")
    white_c = HexColor("#FFFFFF")
    styles.add(ParagraphStyle(name="HeroTitle", fontName="Helvetica-Bold", fontSize=28, leading=32, textColor=white_c, spaceAfter=6))
    styles.add(ParagraphStyle(name="HeroSub", fontName="Helvetica", fontSize=11, leading=14, textColor=muted, spaceAfter=18))
    styles.add(ParagraphStyle(name="SectionTitle", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=accent, spaceBefore=14, spaceAfter=8))
    styles.add(ParagraphStyle(name="SubTitle", fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=white_c, spaceBefore=8, spaceAfter=4))
    styles.add(ParagraphStyle(name="BodyW", fontName="Helvetica", fontSize=10, leading=14, textColor=white_c, spaceAfter=6))
    styles.add(ParagraphStyle(name="MutedW", fontName="Helvetica", fontSize=9, leading=12, textColor=muted, spaceAfter=4))
    styles.add(ParagraphStyle(name="Label", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=muted, spaceAfter=2))
    return styles


def _draw_background(canv, doc):
    canv.saveState()
    canv.setFillColor(HexColor("#050A0F"))
    canv.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=1, stroke=0)
    canv.setFillColor(HexColor("#CCFF00"))
    canv.setFont("Helvetica-Bold", 8)
    canv.drawString(2 * cm, 1 * cm, "ELITE SCOUT // PROFESSIONAL PLAYER ANALYSIS")
    canv.setFillColor(HexColor("#94A3B8"))
    canv.drawRightString(doc.pagesize[0] - 2 * cm, 1 * cm, f"Page {doc.page}")
    canv.restoreState()


def _score_table(rows, styles):
    data = [["Attribute", "Score", "Notes"]]
    for label, score, notes in rows:
        data.append([
            Paragraph(label, styles["BodyW"]),
            Paragraph(f"<b>{score}/10</b>", styles["BodyW"]),
            Paragraph(notes, styles["BodyW"]),
        ])
    t = Table(data, colWidths=[4.5 * cm, 2 * cm, 9 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#CCFF00")),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#050A0F")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BACKGROUND", (0, 1), (-1, -1), HexColor("#0F1623")),
        ("TEXTCOLOR", (0, 1), (-1, -1), HexColor("#FFFFFF")),
        ("GRID", (0, 0), (-1, -1), 0.25, HexColor("#1f2937")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
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


def build_pdf(report_doc: dict, output_path: str):
    full = report_doc["full_report"]
    details = report_doc["player_details"]
    styles = _pdf_styles()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    story = []

    # Cover
    story.append(Paragraph("ELITE SCOUT", styles["Label"]))
    story.append(Paragraph(f"{details['player_name'].upper()}", styles["HeroTitle"]))
    story.append(Paragraph(
        f"{details['position'].title()} · Age {details['age']} · {details['preferred_foot'].title()} foot · {details.get('current_club') or 'Independent'}",
        styles["HeroSub"],
    ))

    overall = full.get("scores", {}).get("overall_development", "-")
    story.append(Paragraph(f"<b>Overall Development Score:</b> {overall}/10", styles["BodyW"]))
    story.append(Paragraph(f"<b>Player Type:</b> {full.get('player_type', '-')}", styles["BodyW"]))
    story.append(Spacer(1, 0.4 * cm))

    # Executive Summary
    story.append(Paragraph("EXECUTIVE SUMMARY", styles["SectionTitle"]))
    story.append(Paragraph(full.get("executive_summary", ""), styles["BodyW"]))

    # Overall scores
    story.append(Paragraph("SCORE OVERVIEW", styles["SectionTitle"]))
    sc = full.get("scores", {})
    score_rows = [
        ("Technical", sc.get("technical", "-"), "Composite technical ability"),
        ("Tactical", sc.get("tactical", "-"), "Composite tactical intelligence"),
        ("Physical", sc.get("physical", "-"), "Composite physical attributes"),
        ("Mentality", sc.get("mentality", "-"), "Composite mental attributes"),
        ("Overall Development", sc.get("overall_development", "-"), "Overall development indicator"),
    ]
    story.append(_score_table(score_rows, styles))
    story.append(PageBreak())

    # Technical
    if "technical" in full:
        story.append(Paragraph("TECHNICAL ANALYSIS", styles["SectionTitle"]))
        story.append(_score_table(_section_rows(full["technical"]), styles))

    # Tactical
    if "tactical" in full:
        story.append(Paragraph("TACTICAL ANALYSIS", styles["SectionTitle"]))
        story.append(_score_table(_section_rows(full["tactical"]), styles))

    story.append(PageBreak())

    # Physical
    if "physical" in full:
        story.append(Paragraph("PHYSICAL ANALYSIS", styles["SectionTitle"]))
        story.append(_score_table(_section_rows(full["physical"]), styles))

    # Mentality
    if "mentality" in full:
        story.append(Paragraph("MENTALITY ANALYSIS", styles["SectionTitle"]))
        story.append(_score_table(_section_rows(full["mentality"]), styles))

    story.append(PageBreak())

    # Scout View
    if "scout_view" in full:
        sv = full["scout_view"]
        story.append(Paragraph("SCOUT VIEW · HOW A SCOUT MIGHT ASSESS THIS PLAYER", styles["SectionTitle"]))
        story.append(Paragraph("Key Strengths", styles["SubTitle"]))
        for s in sv.get("key_strengths", []):
            story.append(Paragraph(f"• {s}", styles["BodyW"]))
        story.append(Paragraph("Areas of Concern", styles["SubTitle"]))
        for s in sv.get("areas_of_concern", []):
            story.append(Paragraph(f"• {s}", styles["BodyW"]))
        story.append(Paragraph("Development Priorities", styles["SubTitle"]))
        for s in sv.get("development_priorities", []):
            story.append(Paragraph(f"• {s}", styles["BodyW"]))
        story.append(Paragraph("Appropriate Next Competitive Level", styles["SubTitle"]))
        story.append(Paragraph(sv.get("appropriate_next_level", ""), styles["BodyW"]))
        story.append(Paragraph("Positional Suitability", styles["SubTitle"]))
        story.append(Paragraph(sv.get("positional_suitability", ""), styles["BodyW"]))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(
            "<i>This is an independent development analysis and does not guarantee selection or advancement opportunities.</i>",
            styles["MutedW"],
        ))

    # Potential
    if "potential_assessment" in full:
        pa = full["potential_assessment"]
        story.append(Paragraph("POTENTIAL ASSESSMENT", styles["SectionTitle"]))
        story.append(Paragraph(f"<b>Current Level:</b> {pa.get('current_level', '')}", styles["BodyW"]))
        story.append(Paragraph(f"<b>Development Potential:</b> {pa.get('development_potential', '')}", styles["BodyW"]))
        story.append(Paragraph(f"<b>Recommended Next Step:</b> {pa.get('recommended_next_step', '')}", styles["BodyW"]))
        story.append(Paragraph(f"<b>3-Month Focus:</b> {pa.get('three_month_focus', '')}", styles["BodyW"]))

    story.append(PageBreak())

    # Training Plan
    if "training_plan" in full:
        tp = full["training_plan"]
        story.append(Paragraph("PERSONAL TRAINING PLAN", styles["SectionTitle"]))
        story.append(Paragraph("Five Specific Exercises", styles["SubTitle"]))
        for ex in tp.get("exercises", []):
            story.append(Paragraph(
                f"<b>{ex.get('name', '')}</b> · {ex.get('duration', '')}<br/>{ex.get('description', '')}",
                styles["BodyW"],
            ))
        story.append(Paragraph("Weekly Focus", styles["SubTitle"]))
        story.append(Paragraph(tp.get("weekly_focus", ""), styles["BodyW"]))
        story.append(Paragraph("30-Day Development Plan", styles["SubTitle"]))
        story.append(Paragraph(tp.get("thirty_day_plan", ""), styles["BodyW"]))
        story.append(Paragraph("90-Day Development Plan", styles["SubTitle"]))
        story.append(Paragraph(tp.get("ninety_day_plan", ""), styles["BodyW"]))

    # Video Comments
    if "video_comments" in full and full["video_comments"]:
        story.append(Paragraph("VIDEO COMMENTS", styles["SectionTitle"]))
        for c in full["video_comments"]:
            story.append(Paragraph(
                f"<b>{c.get('timestamp', '')}</b> · {c.get('comment', '')}",
                styles["BodyW"],
            ))

    # Final Summary
    story.append(PageBreak())
    story.append(Paragraph("FINAL SUMMARY", styles["SectionTitle"]))
    story.append(Paragraph(full.get("final_summary", ""), styles["BodyW"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "<i>Scores presented as developmental guidance, not definitive scouting evaluations. Independent feedback only.</i>",
        styles["MutedW"],
    ))

    doc.build(story, onFirstPage=_draw_background, onLaterPages=_draw_background)


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
    docs = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    return docs


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
