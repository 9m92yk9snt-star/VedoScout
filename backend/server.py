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
JWT_SECRET = os.environ["JWT_SECRET_KEY"]
JWT_ALG = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXP_MIN = int(os.environ.get("JWT_EXPIRES_MINUTES", "1440"))
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
DEFAULT_PRICE = float(os.environ.get("DEFAULT_REPORT_PRICE_DKK", "399"))

# ---- App ----
app = FastAPI(title="Elite Football AI Scout API")
api_router = APIRouter(prefix="/api")

# Mount uploads as static
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

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
    price_dkk: float


class CheckoutInit(BaseModel):
    report_id: str
    origin_url: str


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

PREVIEW_PROMPT = """You are an experienced football coach giving honest, friendly feedback to a young player or their parent. Watch the video and write a short FREE PREVIEW using NATURAL, EVERYDAY FOOTBALL LANGUAGE — the way a real coach talks to a 14-year-old and their family. AVOID jargon like "press-resistant", "scanning frequency", "line-breaking", "half-turn", "high-intensity transitions", "block", "vertical progression". Instead say things like "stays calm under pressure", "always looks around before the ball arrives", "his left foot is dangerous", "gets tired late in the game", "smart playmaker", "reads the game well".

Produce a JSON object EXACTLY in this format (no extra fields, no commentary outside JSON):

{
  "player_type": "<short, friendly label e.g. 'Smart playmaker with a strong left foot' or 'Box-to-box midfielder with engine'>",
  "brief_summary": "<2-3 sentences in plain football language describing how he plays and what makes him stand out>",
  "top_strengths": ["<strength 1 in plain words>", "<strength 2>", "<strength 3>"],
  "area_for_improvement": "<one specific thing to work on, in simple words>",
  "sample_section": {
    "title": "Sample: Technical Snapshot",
    "content": "<3-4 sentence preview teaser of the deeper technical breakdown — still in natural football language>"
  }
}

The player provided these details: {player_details}

Important: This is independent developmental feedback. Do NOT imply trials, contracts, or academy selection. Return ONLY valid JSON."""


FULL_REPORT_PROMPT = """You are an experienced football coach writing a PREMIUM development report for a young player and their family. Watch the video THOROUGHLY. Write in NATURAL, EVERYDAY FOOTBALL LANGUAGE — the way a real coach talks. AVOID jargon like "press-resistant", "scanning frequency", "line-breaking passes", "half-turn", "high-intensity transitions", "vertical progression", "false-9 in possession systems". Instead use plain language: "stays calm when defenders close him down", "always looks around before getting the ball", "his left foot can find any pass", "gets tired late in matches", "ready to step up to a stronger team", "best as a creative #10 behind the striker".

Each rating field must be an integer 1-10. Narrative fields should be specific, encouraging, and substantive (2-4 sentences each unless otherwise noted). Speak directly about the player ("he", "she", or use the name) — not abstractly.

Produce a JSON object EXACTLY in this format:

{
  "player_type": "<short friendly label>",
  "executive_summary": "<4-6 sentences describing the player's style and what makes him stand out, in plain football language>",
  "technical": {
    "first_touch": {"score": 1-10, "notes": "<specific observation in plain words>"},
    "ball_control": {"score": 1-10, "notes": "..."},
    "dribbling": {"score": 1-10, "notes": "..."},
    "passing": {"score": 1-10, "notes": "..."},
    "shooting": {"score": 1-10, "notes": "..."},
    "weak_foot": {"score": 1-10, "notes": "..."},
    "one_v_one": {"score": 1-10, "notes": "..."}
  },
  "tactical": {
    "positioning": {"score": 1-10, "notes": "..."},
    "off_ball_movement": {"score": 1-10, "notes": "..."},
    "scanning": {"score": 1-10, "notes": "..."},
    "decision_making": {"score": 1-10, "notes": "..."},
    "timing_of_runs": {"score": 1-10, "notes": "..."},
    "game_understanding": {"score": 1-10, "notes": "..."}
  },
  "physical": {
    "acceleration": {"score": 1-10, "notes": "..."},
    "speed": {"score": 1-10, "notes": "..."},
    "balance": {"score": 1-10, "notes": "..."},
    "agility": {"score": 1-10, "notes": "..."},
    "intensity": {"score": 1-10, "notes": "..."},
    "body_control": {"score": 1-10, "notes": "..."}
  },
  "mentality": {
    "confidence": {"score": 1-10, "notes": "..."},
    "work_rate": {"score": 1-10, "notes": "..."},
    "courage_in_duels": {"score": 1-10, "notes": "..."},
    "response_to_mistakes": {"score": 1-10, "notes": "..."},
    "competitive_mindset": {"score": 1-10, "notes": "..."},
    "focus": {"score": 1-10, "notes": "..."}
  },
  "scout_view": {
    "key_strengths": ["<3-5 bullets in plain football language>"],
    "areas_of_concern": ["<2-4 bullets in plain language>"],
    "development_priorities": ["<3-4 bullets — what to focus on next>"],
    "appropriate_next_level": "<e.g. 'Ready to step up to a stronger U15 team' — plain language, no jargon>",
    "positional_suitability": "<which positions suit him best, in plain words e.g. 'Best as a creative #10 behind a striker'>"
  },
  "potential_assessment": {
    "current_level": "<plain words describing where he is right now>",
    "development_potential": "<honest, encouraging assessment of how much he can grow>",
    "recommended_next_step": "<concrete next step in plain words>",
    "three_month_focus": "<main focus for the next 90 days, simple words>"
  },
  "training_plan": {
    "exercises": [
      {"name": "<exercise — short, clear>", "description": "<2 sentence drill description in everyday language>", "duration": "<e.g. '15 min'>"},
      {"name": "...", "description": "...", "duration": "..."},
      {"name": "...", "description": "...", "duration": "..."},
      {"name": "...", "description": "...", "duration": "..."},
      {"name": "...", "description": "...", "duration": "..."}
    ],
    "weekly_focus": "<a paragraph on what to focus on each training session this week — plain words>",
    "thirty_day_plan": "<paragraph on 30-day development plan in plain language>",
    "ninety_day_plan": "<paragraph on 90-day development plan in plain language>"
  },
  "video_comments": [
    {"timestamp": "<MM:SS or 'General'>", "comment": "<specific observation in plain football words>"},
    {"timestamp": "...", "comment": "..."}
  ],
  "scores": {
    "technical": 1-10,
    "tactical": 1-10,
    "physical": 1-10,
    "mentality": 1-10,
    "overall_development": 1-10
  },
  "final_summary": "<3-5 sentence encouraging closing summary, plain football language>"
}

Player details: {player_details}

CRITICAL: This is independent developmental analysis. Do NOT imply trials, contracts, or selection. Use language like 'developmental guidance' rather than 'scouting evaluation'. Use 'next level to aim for' rather than 'should be signed'. Write the way a real football coach talks — warm, specific, and clear. Return ONLY valid JSON, no markdown, no commentary."""


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


async def call_gemini_with_video(session_id: str, prompt: str, video_path: str) -> dict:
    """Send a video file + prompt to Gemini and return parsed JSON."""
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message="You are an experienced football coach giving honest, friendly feedback to a young player and their family. You speak in plain, natural football language — never jargon. You ALWAYS respond with valid JSON only.",
    ).with_model("gemini", "gemini-2.5-pro")

    video_file = FileContentWithMimeType(
        file_path=video_path,
        mime_type="video/mp4",
    )
    user_message = UserMessage(text=prompt, file_contents=[video_file])
    response = await chat.send_message(user_message)
    response_text = response if isinstance(response, str) else str(response)
    try:
        return extract_json(response_text)
    except Exception as e:
        logger.error(f"Failed to parse Gemini response: {e}\n{response_text[:500]}")
        raise HTTPException(status_code=500, detail="AI analysis returned invalid format. Please try again.")


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
    if doc:
        return {"price_dkk": doc.get("value", DEFAULT_PRICE), "currency": "dkk"}
    return {"price_dkk": DEFAULT_PRICE, "currency": "dkk"}


async def get_current_price() -> float:
    doc = await db.settings.find_one({"key": "report_price"})
    if doc and "value" in doc:
        return float(doc["value"])
    return DEFAULT_PRICE


@api_router.post("/reports/upload")
async def upload_video_and_create_preview(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    player_name: str = Form(...),
    age: int = Form(...),
    position: str = Form(...),
    preferred_foot: str = Form(...),
    current_club: Optional[str] = Form(None),
    video_type: str = Form(...),
    description: str = Form(...),
    user=Depends(get_current_user),
):
    # Validate file type
    allowed_mimes = {"video/mp4", "video/quicktime", "video/x-m4v", "video/webm"}
    if file.content_type not in allowed_mimes:
        raise HTTPException(status_code=400, detail=f"Unsupported video format: {file.content_type}. Use MP4, MOV, or WebM.")

    # Save file
    report_id = str(uuid.uuid4())
    ext = (file.filename or "video.mp4").split(".")[-1].lower()
    if ext not in {"mp4", "mov", "m4v", "webm"}:
        ext = "mp4"
    stored_name = f"{report_id}.{ext}"
    file_path = UPLOAD_DIR / stored_name

    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_size = file_path.stat().st_size

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

    # Generate FREE preview synchronously
    try:
        preview = await call_gemini_with_video(
            session_id=f"preview-{report_id}",
            prompt=PREVIEW_PROMPT.replace("{player_details}", details_str),
            video_path=str(file_path),
        )
    except HTTPException:
        # Cleanup
        try:
            file_path.unlink()
        except Exception:
            pass
        raise
    except Exception as e:
        logger.exception("Preview generation failed")
        try:
            file_path.unlink()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"AI preview generation failed: {str(e)}")

    # Persist report
    report_doc = {
        "id": report_id,
        "user_id": user["id"],
        "user_email": user["email"],
        "player_details": details,
        "video_filename": stored_name,
        "video_size_bytes": file_size,
        "preview": preview,
        "full_report": None,
        "is_paid": False,
        "manually_unlocked": False,
        "created_at": now_iso(),
        "paid_at": None,
    }
    await db.reports.insert_one(report_doc)

    return {
        "id": report_id,
        "player_details": details,
        "video_url": f"/uploads/{stored_name}",
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
        d["video_url"] = f"/uploads/{d['video_filename']}"
    return docs


def _serialize_report(doc: dict, include_full: bool) -> dict:
    out = {
        "id": doc["id"],
        "user_id": doc["user_id"],
        "user_email": doc.get("user_email"),
        "player_details": doc["player_details"],
        "video_url": f"/uploads/{doc['video_filename']}",
        "preview": doc.get("preview"),
        "is_paid": doc.get("is_paid", False),
        "manually_unlocked": doc.get("manually_unlocked", False),
        "demo": doc.get("demo", False),
        "created_at": doc.get("created_at"),
        "paid_at": doc.get("paid_at"),
    }
    if include_full:
        out["full_report"] = doc.get("full_report")
    return out


@api_router.get("/reports/{report_id}")
async def get_report(report_id: str, user=Depends(get_current_user)):
    doc = await db.reports.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")
    if doc["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    unlocked = doc.get("is_paid") or doc.get("manually_unlocked") or user["role"] == "admin"
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

    details_str = json.dumps(doc["player_details"], ensure_ascii=False)
    try:
        full = await call_gemini_with_video(
            session_id=f"full-{report_id}",
            prompt=FULL_REPORT_PROMPT.replace("{player_details}", details_str),
            video_path=str(file_path),
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

@api_router.post("/payments/checkout")
async def create_checkout(payload: CheckoutInit, request: Request, user=Depends(get_current_user)):
    report = await db.reports.find_one({"id": payload.report_id})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    if report.get("is_paid"):
        raise HTTPException(status_code=400, detail="Report already paid")

    price_dkk = await get_current_price()

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
    }

    session_req = CheckoutSessionRequest(
        amount=float(price_dkk),
        currency="dkk",
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
        "amount": float(price_dkk),
        "currency": "dkk",
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

    # On success, mark report paid (idempotent)
    if new_payment_status == "paid":
        report = await db.reports.find_one({"id": txn["report_id"]})
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
        report_id = metadata.get("report_id")
        if report_id:
            txn = await db.payment_transactions.find_one({"session_id": session_id})
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


# ============== ADMIN ROUTES ==============

@api_router.get("/admin/stats")
async def admin_stats(_=Depends(get_current_admin)):
    total_users = await db.users.count_documents({"role": "user"})
    total_uploads = await db.reports.count_documents({})
    total_paid = await db.reports.count_documents({"$or": [{"is_paid": True}, {"manually_unlocked": True}]})

    cursor = db.payment_transactions.find({"payment_status": "paid"}, {"_id": 0, "amount": 1, "currency": 1})
    revenue_dkk = 0.0
    async for tx in cursor:
        if tx.get("currency", "").lower() == "dkk":
            revenue_dkk += float(tx.get("amount", 0))
    return {
        "total_users": total_users,
        "total_uploads": total_uploads,
        "total_paid_reports": total_paid,
        "revenue_dkk": revenue_dkk,
    }


@api_router.get("/admin/users")
async def admin_users(_=Depends(get_current_admin)):
    docs = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    return docs


@api_router.get("/admin/reports")
async def admin_reports(_=Depends(get_current_admin)):
    docs = await db.reports.find({}, {"_id": 0, "full_report": 0}).sort("created_at", -1).to_list(500)
    for d in docs:
        d["video_url"] = f"/uploads/{d['video_filename']}"
    return docs


@api_router.get("/admin/payments")
async def admin_payments(_=Depends(get_current_admin)):
    docs = await db.payment_transactions.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return docs


@api_router.put("/admin/price")
async def admin_update_price(payload: PriceUpdate, _=Depends(get_current_admin)):
    if payload.price_dkk <= 0:
        raise HTTPException(status_code=400, detail="Price must be > 0")
    await db.settings.update_one(
        {"key": "report_price"},
        {"$set": {"key": "report_price", "value": float(payload.price_dkk), "updated_at": now_iso()}},
        upsert=True,
    )
    return {"price_dkk": payload.price_dkk}


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
