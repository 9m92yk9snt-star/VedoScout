"""
pdf_v2.py — Premium Report V2 PDF builder.

Mirrors the web PremiumReportV2 card layout (frontend/src/components/report-v2)
1:1 on three A4 pages: same sections, same order, same data via a Python port
of derive.js. Pure presentation — never touches scores or analysis logic.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from datetime import datetime, timezone
from xml.sax.saxutils import escape as _xml_escape

from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Paragraph

# ───────────────────────────── palette (V2 spec) ─────────────────────────────
CREAM = HexColor("#F4F0E2")
CARD = HexColor("#FFFFFF")
BORDER = HexColor("#E5DFCE")
FOREST = HexColor("#12402A")
GREEN = HexColor("#1E5B3C")
LIME = HexColor("#7BA05B")
INK = HexColor("#101B12")
BODY = HexColor("#3C4A40")
MUTED = HexColor("#8B957F")
GOLD = HexColor("#E8B32C")
STAR_OFF = HexColor("#DCE3D2")
RING_BG = HexColor("#C9D8C0")
RING_MID = HexColor("#6E9E63")
SOFT = HexColor("#F0F5EC")
SOFT_BORDER = HexColor("#DCE8D6")
CREAM_TEXT = HexColor("#F0EAD8")
FOOT_TEXT = HexColor("#E9EFE2")
FOOT_MUTED = HexColor("#A9BC9C")

PROMO_URL = "https://scoutmeplay.com"

W, H = A4
M = 26.0            # page margin
GAP = 9.0           # card gap
CW = W - 2 * M      # content width

# ───────────────────────────── fonts ─────────────────────────────
_FONT_DIR = Path(__file__).resolve().parent / "fonts"
F_BLACK, F_BOLD, F_BODY, F_SCRIPT = "Helvetica-Bold", "Helvetica-Bold", "Helvetica", "Helvetica-Oblique"
try:
    pdfmetrics.registerFont(TTFont("Barlow-Black", str(_FONT_DIR / "Barlow-Black.ttf")))
    pdfmetrics.registerFont(TTFont("Barlow-Bold", str(_FONT_DIR / "Barlow-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("DMSans", str(_FONT_DIR / "DMSans-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Caveat", str(_FONT_DIR / "Caveat.ttf")))
    F_BLACK, F_BOLD, F_BODY, F_SCRIPT = "Barlow-Black", "Barlow-Bold", "DMSans", "Caveat"
except Exception:
    pass

# ═══════════════════════ derive.js — Python port ═══════════════════════

SKILL_LABELS = {
    "first_touch": "First Touch", "ball_control": "Ball Control", "dribbling": "Dribbling",
    "passing": "Passing", "shooting": "Shooting", "weak_foot": "Weak Foot", "one_v_one": "1v1 Attacking",
    "positioning": "Positioning", "off_ball_movement": "Off-Ball Movement", "scanning": "Scanning",
    "decision_making": "Decision Making", "timing_of_runs": "Timing of Runs",
    "game_understanding": "Game Understanding",
    "acceleration": "Acceleration", "speed": "Speed", "balance": "Balance", "agility": "Agility",
    "intensity": "Intensity", "body_control": "Body Control",
    "confidence": "Confidence", "work_rate": "Work Rate", "courage_in_duels": "Courage in Duels",
    "response_to_mistakes": "Response to Mistakes", "competitive_mindset": "Competitive Drive",
    "focus": "Focus",
}

TIER_PERCENTILE = {
    "elite_academy": {"label": "Top 10%", "width": 90},
    "pro_academy": {"label": "Top 20%", "width": 80},
    "strong_club": {"label": "Top 40%", "width": 60},
    "standard_club": {"label": "Top 60%", "width": 40},
}
TIER_DOTS = {"standard_club": 2, "strong_club": 3, "pro_academy": 4, "elite_academy": 5}
TIER_LABELS = {"standard_club": "Grassroots Club", "strong_club": "Strong Club",
               "pro_academy": "Strong Academy", "elite_academy": "Elite Academy"}
NEXT_TIER = {"standard_club": "strong_club", "strong_club": "pro_academy",
             "pro_academy": "elite_academy", "elite_academy": "elite_academy"}
POSITION_ABBR = {
    "Goalkeeper": "GK", "Centre-back": "CB", "Full-back": "FB", "Wing-back": "WB",
    "Defensive Midfielder": "DM", "Central Midfielder": "CM", "Attacking Midfielder": "AM",
    "Winger": "LW / RW", "Striker": "ST",
}


def ts_to_seconds(ts):
    if not ts or not isinstance(ts, str) or ":" not in ts:
        return None
    try:
        m, s = ts.split(":", 1)
        return int(m) * 60 + int(s)
    except Exception:
        return None


def first_sentences(text, max_len=160):
    if not text:
        return ""
    clean = str(text).strip()
    if len(clean) <= max_len:
        return clean
    cut = clean[:max_len]
    last_dot = cut.rfind(". ")
    return cut[:last_dot + 1] if last_dot > 60 else cut.rstrip() + "…"


def _collect_skills(full):
    out = []
    for cat in ("technical", "tactical", "physical", "mentality"):
        sec = full.get(cat) or {}
        if not isinstance(sec, dict):
            continue
        for key, sk in sec.items():
            if not isinstance(sk, dict):
                continue
            if sk.get("cannot_evaluate") or not isinstance(sk.get("score"), (int, float)):
                continue
            out.append({
                "key": key, "category": cat,
                "label": SKILL_LABELS.get(key, key.replace("_", " ").title()),
                "score": sk["score"],
                "notes": sk.get("notes") or "",
                "confidence": str(sk.get("confidence") or "").lower(),
                "tier": str(sk.get("tier_for_age") or "").lower(),
                "evidence": sk.get("evidence") if isinstance(sk.get("evidence"), list) else [],
                "verdict": sk.get("verdict") or "",
            })
    return out


def _frame_lookup(full):
    comments = full.get("video_comments") if isinstance(full.get("video_comments"), list) else []
    entries = [
        {"ts": c.get("timestamp"), "sec": ts_to_seconds(c.get("timestamp")), "url": c["frame_url"]}
        for c in comments
        if isinstance(c, dict) and c.get("frame_url") and c.get("identity_verified") is not False
    ]
    used = set()

    def find(ts):
        sec = ts_to_seconds(ts)
        best = None
        for e in entries:
            if e["url"] in used:
                continue
            if ts and e["ts"] == ts:
                best = e
                break
            if sec is not None and e["sec"] is not None:
                d = abs(e["sec"] - sec)
                if d <= 8 and (best is None or d < abs((best["sec"] or 999) - sec)):
                    best = e
        if best is None:
            best = next((e for e in entries if e["url"] not in used), None)
        if best:
            used.add(best["url"])
            return best["url"]
        return None

    return find


def derive_v2(report):
    full = report.get("full_report") or {}
    pd = report.get("player_details") or {}
    skills = _collect_skills(full)
    find_frame = _frame_lookup(full)
    scout_view = full.get("scout_view") or {}
    pa = full.get("potential_assessment") or {}
    ob = full.get("overall_benchmark") or {}
    ob_tier = str(ob.get("tier") or "").lower()

    conf_rank = {"high": 2, "medium": 1, "low": 0}
    top_strengths = []
    for s in sorted(skills, key=lambda s: (-s["score"], -conf_rank.get(s["confidence"], 0)))[:4]:
        ev = next((e for e in s["evidence"]
                   if isinstance(e, dict) and e.get("timestamp") and e["timestamp"] != "General"), None)
        ts = ev.get("timestamp") if ev else None
        top_strengths.append({
            "name": s["label"], "score": s["score"], "category": s["category"],
            "note": first_sentences(s["notes"], 130),
            "timestamp": ts, "thumb": find_frame(ts),
        })

    dpd = full.get("development_priorities_detailed")
    if isinstance(dpd, list) and dpd:
        dev_priorities = [{
            "name": p.get("name"), "score": p.get("score") if isinstance(p.get("score"), (int, float)) else None,
            "issue": first_sentences(p.get("issue"), 150), "howTo": first_sentences(p.get("how_to_improve"), 150),
        } for p in dpd[:3]]
    else:
        dev_priorities = []
        for s in sorted(skills, key=lambda s: s["score"])[:3]:
            how = s["verdict"].split("focus on", 1)
            dev_priorities.append({
                "name": s["label"], "score": s["score"],
                "issue": first_sentences(s["notes"], 150),
                "howTo": first_sentences(how[1] if len(how) > 1 else s["verdict"], 150),
            })

    age_comparison = [
        {"name": s["label"], **TIER_PERCENTILE[s["tier"]]}
        for s in sorted(
            [s for s in skills if s["tier"] in TIER_PERCENTILE],
            key=lambda s: (-(TIER_PERCENTILE[s["tier"]]["width"]), -s["score"]),
        )[:6]
    ]

    snap = full.get("snapshot") or {}
    ks = scout_view.get("key_strengths") or []
    dp = scout_view.get("development_priorities") or []
    snapshot = {
        "biggestStrength": snap.get("biggest_strength") or first_sentences(ks[0] if ks else "", 45) or "—",
        "developmentArea": snap.get("biggest_development_area") or first_sentences(dp[0] if dp else "", 45) or "—",
        "hiddenTalent": snap.get("hidden_talent") or first_sentences(ks[-1] if ks else "", 45) or "—",
        "nextMilestone": snap.get("next_milestone") or first_sentences(pa.get("three_month_focus"), 45) or "—",
        "progressNote": snap.get("overall_progress_note") or "On the right track!",
    }

    rm = full.get("development_roadmap") or {}
    roadmap = [
        {"key": "NOW", "text": rm.get("now") or "Build confidence and technical foundation"},
        {"key": "3 MONTHS", "text": rm.get("three_months") or first_sentences(pa.get("three_month_focus"), 60) or "Sharpen the main development area"},
        {"key": "6 MONTHS", "text": rm.get("six_months") or first_sentences(ob.get("what_separates_from_next_tier"), 60) or "Close the gap to the next level"},
        {"key": "12 MONTHS", "text": rm.get("twelve_months") or first_sentences(pa.get("recommended_next_step"), 60) or "High impact in matches"},
    ]

    exercises = (full.get("training_plan") or {}).get("exercises") or []

    def _ex(i, fallback):
        e = exercises[i] if i < len(exercises) else {}
        return {"name": e.get("name") or fallback, "mins": e.get("duration") or ""}

    training_week = [
        {"day": "MON", **_ex(0, "Technical work")},
        {"day": "WED", **_ex(1, "Skill drills")},
        {"day": "FRI", **_ex(2, "Game moves")},
        {"day": "WEEKEND", **_ex(3, "Match Challenge")},
    ]

    ps = full.get("parent_summary") or {}
    paragraphs = ps.get("paragraphs") if isinstance(ps.get("paragraphs"), list) else []
    parent_summary = {
        "headline": ps.get("headline") or first_sentences(full.get("executive_summary"), 110),
        "paragraphs": paragraphs[:2] if paragraphs else [
            t for t in (first_sentences(full.get("executive_summary"), 260),
                        first_sentences(full.get("final_summary"), 260)) if t
        ],
        "goodNews": ps.get("good_news") or first_sentences(pa.get("development_potential"), 220),
    }
    pt = full.get("parent_tips")
    parent_tips = pt[:4] if isinstance(pt, list) and pt else [
        "Praise effort and brave decisions, not just goals.",
        "Encourage trying new skills in games.",
        "Support training, rest and healthy habits.",
        "Be the biggest fan and enjoy the journey together!",
    ]
    cn = full.get("coach_notes")
    if isinstance(cn, list) and cn:
        coach_notes = cn[:6]
    else:
        coach_notes = list(dp[:3])
        if scout_view.get("positional_suitability"):
            coach_notes.append(f"Perfect role: {scout_view['positional_suitability']}")
        if pa.get("three_month_focus"):
            coach_notes.append(f"Focus in training: {first_sentences(pa['three_month_focus'], 90)}")

    so = full.get("scout_outlook") or {}
    next_tier = NEXT_TIER.get(ob_tier, ob_tier)
    dev_pot = pa.get("development_potential") or ""
    scout_outlook = {
        "currentLabel": so.get("current_level_label") or ob.get("tier_label") or TIER_LABELS.get(ob_tier, "—"),
        "currentDots": so.get("current_level_dots") or TIER_DOTS.get(ob_tier, 3),
        "potentialLabel": so.get("potential_level_label") or TIER_LABELS.get(next_tier, "—"),
        "potentialDots": so.get("potential_level_dots") or min(5, TIER_DOTS.get(ob_tier, 3) + 1),
        "readiness": so.get("recruitment_readiness") or (
            "High — Trial Ready" if ob_tier == "elite_academy"
            else "Medium — Keep Developing" if ob_tier == "pro_academy"
            else "Early — Keep Building"),
        "longTerm": so.get("long_term_potential") or ("High" if re.search(r"very high|high", dev_pot, re.I) else "Medium"),
        "longTermNote": so.get("long_term_note") or first_sentences(dev_pot, 140),
    }

    ms = full.get("match_stats") or None
    match_stats = None
    if ms:
        def _duel_pct(v):
            m = re.search(r"(\d+)\s*/\s*(\d+)", str(v or ""))
            return (int(m.group(1)) / int(m.group(2)) * 100) if m and int(m.group(2)) > 0 else 50

        rows = [
            {"label": "Total Actions", "value": ms.get("total_actions"), "pct": min(100, (ms.get("total_actions") or 0) / 80 * 100)},
            {"label": "Successful Dribbles", "value": ms.get("successful_dribbles"), "pct": min(100, (ms.get("successful_dribbles") or 0) / 12 * 100)},
            {"label": "Key Passes", "value": ms.get("key_passes"), "pct": min(100, (ms.get("key_passes") or 0) / 8 * 100)},
            {"label": "Shots", "value": ms.get("shots"), "pct": min(100, (ms.get("shots") or 0) / 8 * 100)},
            {"label": "Duels Won", "value": ms.get("duels_won"), "pct": _duel_pct(ms.get("duels_won"))},
            {"label": "Minutes Analysed", "value": f"{ms.get('minutes_analysed', '—')}'", "pct": min(100, (ms.get("minutes_analysed") or 0) / 90 * 100)},
        ]
        match_stats = [r for r in rows if r["value"] is not None] or None

    vc = [c for c in (full.get("video_comments") or []) if isinstance(c, dict) and c.get("timestamp")]
    vc_best = next(
        (c for c in vc if c.get("frame_url") and c.get("identity_verified") is True),
        next((c for c in vc if c.get("frame_url") and c.get("identity_verified") is not False), vc[0] if vc else None),
    )
    video_highlight = None
    if vc_best:
        video_highlight = {
            "timestamp": vc_best.get("timestamp"), "caption": vc_best.get("comment"),
            "thumb": None if vc_best.get("identity_verified") is False else vc_best.get("frame_url"),
        }

    overall = full.get("scores", {}).get("overall_development")
    overall = overall if isinstance(overall, (int, float)) else None

    return {
        "playerType": full.get("player_type") or "",
        "overall": overall,
        "ageBracket": ob.get("age_bracket_used"),
        "stars": int(overall / 2 + 0.5) if overall is not None else 0,
        "positionAbbr": POSITION_ABBR.get(pd.get("position"), pd.get("position") or "—"),
        "topStrengths": top_strengths, "devPriorities": dev_priorities,
        "ageComparison": age_comparison, "snapshot": snapshot, "roadmap": roadmap,
        "trainingWeek": training_week, "parentSummary": parent_summary,
        "parentTips": parent_tips, "coachNotes": coach_notes, "scoutOutlook": scout_outlook,
        "matchStats": match_stats, "videoHighlight": video_highlight,
        "identityNote": _identity_note(report),
        "actionTimeline": _action_timeline(full),
        "parentsPackage": _parents_package(full),
    }


def _parents_package(full):
    pp = full.get("parents_package")
    if not isinstance(pp, dict):
        return None
    drills = [d for d in (pp.get("home_drills") or [])
              if isinstance(d, dict) and d.get("name") and isinstance(d.get("steps"), list)][:3]
    wt = pp.get("watch_together")
    wt = wt if isinstance(wt, dict) and isinstance(wt.get("moments"), list) else None
    msg = pp.get("message_to_player")
    msg = msg if isinstance(msg, dict) and msg.get("body") else None
    if not (drills or wt or msg):
        return None
    return {"drills": drills, "watch": wt, "message": msg}


def _action_timeline(full):
    out = []
    for a in (full.get("action_timeline") or []):
        if not isinstance(a, dict) or not a.get("timestamp"):
            continue
        if not (a.get("title") or a.get("description")):
            continue
        if str(a.get("identity_confidence", "")).lower() == "low":
            continue
        oc = str(a.get("outcome") or "").lower()
        out.append({
            "timestamp": a["timestamp"],
            "title": a.get("title") or str(a.get("action_type") or "").replace("_", " "),
            "description": first_sentences(a.get("description"), 110),
            "rating": a.get("rating") if isinstance(a.get("rating"), (int, float)) else None,
            "outcome": oc if oc in ("positive", "neutral", "negative") else "neutral",
            "tracked": bool(a.get("tracking_verified")),
        })
    return out[:15]


def _identity_note(report):
    st = report.get("identity_stats") or {}
    checked = st.get("checked") or 0
    verified = st.get("verified") or 0
    if checked > 0 and verified / checked < 0.5:
        return ("Some moments are shown as text only — an image appears only when an "
                "independent AI identity check confirms the player with certainty.")
    return None


# ═══════════════════════ low-level drawing helpers ═══════════════════════

def esc(t):
    return _xml_escape(str(t if t is not None else ""))


def _style(font, size, color, leading=None, align=TA_LEFT, tracking=0):
    return ParagraphStyle(
        f"_{font}{size}{color}{align}", fontName=font, fontSize=size,
        leading=leading or size * 1.35, textColor=color, alignment=align,
    )


def draw_par(c, text, x, y_top, w, style, max_h=200):
    """Draw a wrapped paragraph whose TOP edge sits at y_top. Returns height."""
    p = Paragraph(text, style)
    _, ph = p.wrap(w, max_h)
    p.drawOn(c, x, y_top - ph)
    return ph


def card(c, x, y, w, h, fill=CARD, stroke=BORDER, r=9):
    c.saveState()
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(0.8)
    c.roundRect(x, y, w, h, r, stroke=1, fill=1)
    c.restoreState()


def card_title(c, x, y_top, text, w):
    """Green-square icon chip + tracked uppercase title. Returns height used."""
    c.saveState()
    c.setFillColor(GREEN)
    c.roundRect(x, y_top - 13, 13, 13, 3.2, stroke=0, fill=1)
    c.setFillColor(CARD)
    c.circle(x + 6.5, y_top - 6.5, 2.1, stroke=0, fill=1)
    c.setFillColor(FOREST)
    c.setFont(F_BOLD, 8.6)
    c.drawString(x + 18, y_top - 10.4, str(text).upper())
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.7)
    c.line(x, y_top - 19, x + w, y_top - 19)
    c.restoreState()
    return 25


def draw_star(c, cx, cy, r, color):
    pts = []
    for i in range(10):
        ang = math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    c.saveState()
    c.setFillColor(color)
    p = c.beginPath()
    p.moveTo(*pts[0])
    for pt in pts[1:]:
        p.lineTo(*pt)
    p.close()
    c.drawPath(p, stroke=0, fill=1)
    c.restoreState()


def draw_stars_row(c, cx, cy, n_filled, r=5.4, gap=4.5):
    total_w = 5 * (2 * r) + 4 * gap
    x = cx - total_w / 2 + r
    for i in range(5):
        draw_star(c, x, cy, r, GOLD if i < n_filled else STAR_OFF)
        x += 2 * r + gap


def draw_donut(c, cx, cy, r, pct, thickness=11):
    """Ring gauge: forest for first 68% of progress, lighter green for the rest."""
    c.saveState()
    c.setLineWidth(thickness)
    c.setLineCap(1)
    box = (cx - r, cy - r, cx + r, cy + r)
    c.setStrokeColor(RING_BG)
    c.arc(*box, startAng=0, extent=360)
    if pct > 0:
        split = pct * 0.68
        c.setStrokeColor(FOREST)
        c.arc(*box, startAng=90, extent=-(split * 3.6))
        c.setStrokeColor(RING_MID)
        c.arc(*box, startAng=90 - split * 3.6, extent=-((pct - split) * 3.6))
    c.restoreState()


def draw_bar(c, x, y, w, h, pct, bg=HexColor("#E8E4D5"), fg=GREEN):
    c.saveState()
    c.setFillColor(bg)
    c.roundRect(x, y, w, h, h / 2, stroke=0, fill=1)
    fill_w = max(h, w * max(0.0, min(100.0, pct)) / 100.0)
    c.setFillColor(fg)
    c.roundRect(x, y, fill_w, h, h / 2, stroke=0, fill=1)
    c.restoreState()


def draw_dots(c, x, cy, n_filled, total=5, r=3.4, gap=4.6):
    for i in range(total):
        c.saveState()
        c.setFillColor(GREEN if i < n_filled else HexColor("#D9E0CF"))
        c.circle(x + r + i * (2 * r + gap), cy, r, stroke=0, fill=1)
        c.restoreState()


def draw_cover_image(c, path, x, y, w, h, radius=0):
    """Draw an image object-fit:cover inside the given rect (center-cropped)."""
    try:
        img = PILImage.open(path).convert("RGB")
        iw, ih = img.size
        target = w / h
        if iw / ih > target:
            new_w = int(ih * target)
            left = (iw - new_w) // 2
            img = img.crop((left, 0, left + new_w, ih))
        else:
            new_h = int(iw / target)
            top = (ih - new_h) // 2
            img = img.crop((0, top, iw, top + new_h))
        c.saveState()
        if radius:
            p = c.beginPath()
            p.roundRect(x, y, w, h, radius)
            c.clipPath(p, stroke=0, fill=0)
        c.drawImage(ImageReader(img), x, y, w, h)
        c.restoreState()
        return True
    except Exception:
        return False


# ═══════════════════════ card renderers ═══════════════════════

PAD = 12.0  # inner card padding


def _hero_card(c, d, pd, x, y, w, h, photo_path):
    card(c, x, y, w, h)
    hp = 138.0  # photo band height
    py = y + h - hp
    if not (photo_path and draw_cover_image(c, photo_path, x + 1, py, w - 2, hp - 1, radius=8)):
        c.saveState()
        c.setFillColor(HexColor("#0F2A1A"))
        c.roundRect(x + 1, py, w - 2, hp - 1, 8, stroke=0, fill=1)
        initials = "".join(p[0] for p in str(pd.get("player_name") or "P").split()[:2]).upper()
        c.setFillColor(HexColor("#7BA05B"))
        c.setFont(F_BLACK, 40)
        c.drawCentredString(x + w / 2, py + hp / 2 - 14, initials)
        c.restoreState()
    # position chip (top-right of photo)
    abbr = d["positionAbbr"]
    chip_w = max(46, c.stringWidth(str(abbr), F_BLACK, 13) + 16)
    cx0 = x + w - chip_w - 8
    cy0 = y + h - 8 - 30
    c.saveState()
    c.setFillColor(HexColor("#FFFFFF"))
    c.roundRect(cx0, cy0, chip_w, 30, 6, stroke=0, fill=1)
    c.setFillColor(FOREST)
    c.setFont(F_BLACK, 13)
    c.drawCentredString(cx0 + chip_w / 2, cy0 + 13.5, str(abbr))
    c.setFillColor(MUTED)
    c.setFont(F_BOLD, 4.6)
    c.drawCentredString(cx0 + chip_w / 2, cy0 + 5.5, "PREFERRED POSITION")
    c.restoreState()

    ty = py - 10
    name = str(pd.get("player_name") or "Player").upper()
    ty -= draw_par(c, f"<b>{esc(name)}</b>", x + PAD, ty, w - 2 * PAD,
                   _style(F_BLACK, 15.5, INK, leading=16.5)) + 3
    c.setFillColor(GREEN)
    c.setFont(F_BOLD, 7.4)
    c.drawString(x + PAD, ty - 7, str(pd.get("position") or "").upper())
    ty -= 15
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.7)
    c.line(x + PAD, ty, x + w - PAD, ty)
    ty -= 9
    cols = [("AGE", pd.get("age")), ("FOOT", pd.get("preferred_foot")),
            ("CLUB", pd.get("current_club") or "Independent"), ("TYPE", pd.get("video_type"))]
    cw4 = (w - 2 * PAD) / 4
    for i, (k, v) in enumerate(cols):
        cx = x + PAD + i * cw4
        c.setFillColor(MUTED)
        c.setFont(F_BOLD, 5.4)
        c.drawString(cx, ty - 5, k)
        c.setFillColor(INK)
        c.setFont(F_BOLD, 7.6)
        val = str(v if v is not None else "—").title()
        while c.stringWidth(val, F_BOLD, 7.6) > cw4 - 6 and len(val) > 3:
            val = val[:-2] + "…"
        c.drawString(cx, ty - 15, val)
        if i > 0:
            c.setStrokeColor(BORDER)
            c.line(cx - 4, ty - 18, cx - 4, ty - 2)
    ty -= 28
    c.setFillColor(GREEN)
    c.setFont(F_SCRIPT, 16)
    c.drawString(x + PAD, ty - 10, "Keep inspiring.")


def _parent_summary_card(c, ps, x, y, w, h):
    card(c, x, y, w, h)
    ty = y + h - PAD
    ty -= card_title(c, x + PAD, ty, "Parent Summary", w - 2 * PAD)
    ty -= draw_par(c, f"<b>{esc(ps['headline'])}</b>", x + PAD, ty, w - 2 * PAD,
                   _style(F_BOLD, 10, HexColor("#174A30"), leading=12.6)) + 6
    # Measure the Good News box first so paragraphs never run underneath it.
    gn_para, box_h = None, 0
    if ps.get("goodNews"):
        gn_para = Paragraph(esc(ps["goodNews"]), _style(F_BODY, 7.4, BODY, leading=10.6))
        _, gh = gn_para.wrap(w - 2 * PAD - 44, 100)
        box_h = max(40, gh + 22)
    floor = y + box_h + (18 if box_h else 10)
    body_style = _style(F_BODY, 7.8, BODY, leading=11.4)
    for para in ps["paragraphs"]:
        txt = first_sentences(para, 320)
        p = Paragraph(esc(txt), body_style)
        _, ph = p.wrap(w - 2 * PAD, 400)
        if ty - ph < floor:
            txt = first_sentences(para, 150)
            p = Paragraph(esc(txt), body_style)
            _, ph = p.wrap(w - 2 * PAD, 400)
            if ty - ph < floor:
                break
        p.drawOn(c, x + PAD, ty - ph)
        ty -= ph + 5
    if gn_para:
        by = y + 10
        c.saveState()
        c.setFillColor(SOFT)
        c.setStrokeColor(SOFT_BORDER)
        c.roundRect(x + PAD, by, w - 2 * PAD, box_h, 8, stroke=1, fill=1)
        c.setFillColor(GREEN)
        c.roundRect(x + PAD + 9, by + box_h - 33, 24, 24, 6, stroke=0, fill=1)
        draw_star(c, x + PAD + 21, by + box_h - 21, 6.5, HexColor("#FFFFFF"))
        c.setFillColor(FOREST)
        c.setFont(F_BOLD, 7.6)
        c.drawString(x + PAD + 41, by + box_h - 16, "THE GOOD NEWS")
        c.restoreState()
        _, gh = gn_para.wrap(w - 2 * PAD - 44, 100)
        gn_para.drawOn(c, x + PAD + 41, by + box_h - 22 - gh)


def _overall_score_card(c, d, x, y, w, h):
    card(c, x, y, w, h)
    cx = x + w / 2
    ty = y + h - PAD - 4
    c.setFillColor(FOREST)
    c.setFont(F_BOLD, 8.8)
    c.drawCentredString(cx, ty - 8, "OVERALL DEVELOPMENT")
    c.drawCentredString(cx, ty - 19, "SCORE")
    overall = d["overall"]
    pct = (overall / 10 * 100) if overall is not None else 0
    dy = ty - 78
    draw_donut(c, cx, dy, 42, pct, thickness=11)
    c.setFillColor(INK)
    c.setFont(F_BLACK, 27)
    score_txt = f"{overall:.1f}" if overall is not None else "—"
    c.drawCentredString(cx - 4, dy - 8, score_txt)
    c.setFillColor(MUTED)
    c.setFont(F_BOLD, 8)
    c.drawString(cx - 4 + c.stringWidth(score_txt, F_BLACK, 27) / 2 + 2, dy - 8, "/10")
    ty = dy - 58
    c.setFillColor(INK)
    c.setFont(F_BOLD, 8.6)
    c.drawCentredString(cx, ty, str(d["playerType"]).upper())
    draw_stars_row(c, cx, ty - 13, d["stars"])
    draw_par(c, esc("This score reflects the current level compared to other players "
                    "of the same age in this position."),
             x + PAD + 4, ty - 24, w - 2 * PAD - 8,
             _style(F_BODY, 6.8, HexColor("#68766B"), leading=9.4, align=TA_CENTER))


def _snapshot_card(c, snap, x, y, w, h):
    card(c, x, y, w, h)
    ty = y + h - PAD
    ty -= card_title(c, x + PAD, ty, "Player Snapshot", w - 2 * PAD)
    rows = [("BIGGEST STRENGTH", snap["biggestStrength"]),
            ("DEVELOPMENT AREA", snap["developmentArea"]),
            ("HIDDEN TALENT", snap["hiddenTalent"]),
            ("NEXT MILESTONE", snap["nextMilestone"])]
    for k, v in rows:
        c.setFillColor(MUTED)
        c.setFont(F_BOLD, 5.8)
        c.drawString(x + PAD, ty - 6, k)
        ty -= 9
        ty -= draw_par(c, f"<b>{esc(v)}</b>", x + PAD, ty, w - 2 * PAD,
                       _style(F_BOLD, 7.8, INK, leading=9.8)) + 6
    note = Paragraph(f"<b>{esc(snap['progressNote'])}</b>", _style(F_BOLD, 7.2, GREEN, leading=9.6, align=TA_CENTER))
    _, nh = note.wrap(w - 2 * PAD - 12, 60)
    c.saveState()
    c.setFillColor(SOFT)
    c.setStrokeColor(SOFT_BORDER)
    c.roundRect(x + PAD, y + 9, w - 2 * PAD, nh + 12, 7, stroke=1, fill=1)
    c.restoreState()
    note.drawOn(c, x + PAD + 6, y + 15)


def _match_stats_card(c, stats, x, y, w, h):
    card(c, x, y, w, h)
    ty = y + h - PAD
    ty -= card_title(c, x + PAD, ty, "Match Stats", w - 2 * PAD)
    row_h = (ty - y - 10) / max(1, len(stats))
    for r in stats:
        c.setFillColor(BODY)
        c.setFont(F_BODY, 7.2)
        c.drawString(x + PAD, ty - 8, str(r["label"]))
        c.setFillColor(INK)
        c.setFont(F_BOLD, 8.2)
        c.drawRightString(x + w - PAD, ty - 8, str(r["value"]))
        draw_bar(c, x + PAD, ty - 16, w - 2 * PAD, 3.6, r["pct"])
        ty -= row_h


def _age_comparison_card(c, comp, bracket, x, y, w, h):
    card(c, x, y, w, h)
    ty = y + h - PAD
    title_w = w - 2 * PAD
    ty -= card_title(c, x + PAD, ty, "Vs. Players Same Age", title_w)
    if bracket:
        c.saveState()
        bw = c.stringWidth(str(bracket).upper(), F_BOLD, 5.4) + 10
        c.setFillColor(FOREST)
        c.roundRect(x + w - PAD - bw, ty + 8, bw, 11, 5.5, stroke=0, fill=1)
        c.setFillColor(CREAM_TEXT)
        c.setFont(F_BOLD, 5.4)
        c.drawCentredString(x + w - PAD - bw / 2, ty + 11.4, str(bracket).upper())
        c.restoreState()
    if not comp:
        draw_par(c, esc("Not enough benchmarked skills in this clip."), x + PAD, ty - 4,
                 w - 2 * PAD, _style(F_BODY, 7.2, MUTED, leading=10))
        return
    row_h = (ty - y - 8) / max(1, len(comp))
    for r in comp:
        c.setFillColor(BODY)
        c.setFont(F_BODY, 7.2)
        c.drawString(x + PAD, ty - 8, str(r["name"]))
        c.setFillColor(GREEN)
        c.setFont(F_BOLD, 7.2)
        c.drawRightString(x + w - PAD, ty - 8, str(r["label"]))
        draw_bar(c, x + PAD, ty - 16.5, w - 2 * PAD, 4.4, r["width"], fg=FOREST)
        ty -= row_h


def _top_strengths_card(c, strengths, x, y, w, h, resolve):
    card(c, x, y, w, h)
    ty = y + h - PAD
    ty -= card_title(c, x + PAD, ty, "Top Strengths", w - 2 * PAD)
    if not strengths:
        draw_par(c, esc("No scored skills in this clip."), x + PAD, ty - 4, w - 2 * PAD,
                 _style(F_BODY, 7.4, MUTED, leading=10))
        return
    item_h = (ty - y - 8) / max(1, len(strengths))
    for s in strengths:
        iy_top = ty
        th_w, th_h = 56, min(40, item_h - 12)
        thumb = resolve(s.get("thumb")) if s.get("thumb") else None
        has_thumb = bool(thumb and draw_cover_image(c, thumb, x + PAD, iy_top - 6 - th_h, th_w, th_h, radius=5))
        # No placeholder: unverified moments render as text-only, full width.
        tx = x + PAD + (th_w + 9 if has_thumb else 0)
        tw = w - PAD - tx
        c.setFillColor(INK)
        c.setFont(F_BOLD, 8.4)
        c.drawString(tx, iy_top - 14, str(s["name"]))
        chip_txt = f"{s['score']:.1f}" if isinstance(s["score"], float) else str(s["score"])
        chip_w = c.stringWidth(chip_txt, F_BLACK, 7.4) + 10
        c.saveState()
        c.setFillColor(FOREST)
        c.roundRect(x + w - PAD - chip_w, iy_top - 17.5, chip_w, 12.5, 6, stroke=0, fill=1)
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont(F_BLACK, 7.4)
        c.drawCentredString(x + w - PAD - chip_w / 2, iy_top - 14, chip_txt)
        c.restoreState()
        note_w = tw - chip_w - 6
        draw_par(c, esc(s["note"]), tx, iy_top - 19, max(60, note_w),
                 _style(F_BODY, 6.9, BODY, leading=9.2), max_h=item_h - 22)
        if s.get("timestamp"):
            c.setFillColor(LIME)
            c.setFont(F_BOLD, 6.2)
            c.drawRightString(x + w - PAD, iy_top - 28, f"AT {s['timestamp']}")
        ty -= item_h


def _dev_priorities_card(c, priorities, x, y, w, h):
    card(c, x, y, w, h)
    ty = y + h - PAD
    ty -= card_title(c, x + PAD, ty, "Development Priorities", w - 2 * PAD)
    item_h = (ty - y - 8) / max(1, len(priorities) or 1)
    for i, p in enumerate(priorities, 1):
        iy = ty
        c.saveState()
        c.setFillColor(FOREST)
        c.circle(x + PAD + 8, iy - 12, 8, stroke=0, fill=1)
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont(F_BLACK, 8.6)
        c.drawCentredString(x + PAD + 8, iy - 15, str(i))
        c.restoreState()
        c.setFillColor(INK)
        c.setFont(F_BOLD, 8.6)
        c.drawString(x + PAD + 22, iy - 15, str(p["name"] or "—"))
        if p.get("score") is not None:
            c.setFillColor(MUTED)
            c.setFont(F_BOLD, 6.8)
            c.drawRightString(x + w - PAD, iy - 15, f"Score {p['score']}")
        yy = iy - 26
        for label, key in (("ISSUE", "issue"), ("HOW TO IMPROVE", "howTo")):
            if not p.get(key):
                continue
            c.setFillColor(LIME if label != "ISSUE" else MUTED)
            c.setFont(F_BOLD, 5.6)
            c.drawString(x + PAD + 22, yy - 5, label)
            yy -= 8.5
            yy -= draw_par(c, esc(p[key]), x + PAD + 22, yy, w - PAD - (x + PAD + 22 - x) - PAD,
                           _style(F_BODY, 6.9, BODY, leading=9.2), max_h=item_h) + 3
        ty -= item_h


def _roadmap_card(c, roadmap, x, y, w, h):
    card(c, x, y, w, h)
    ty = y + h - PAD
    ty -= card_title(c, x + PAD, ty, "12-Month Roadmap", w - 2 * PAD)
    lx = x + PAD + 5
    item_h = (ty - y - 10) / max(1, len(roadmap))
    c.saveState()
    c.setStrokeColor(SOFT_BORDER)
    c.setLineWidth(1.4)
    c.line(lx, y + 14, lx, ty - 8)
    c.restoreState()
    for i, r in enumerate(roadmap):
        c.saveState()
        c.setFillColor(FOREST if i == 0 else LIME)
        c.circle(lx, ty - 9, 4, stroke=0, fill=1)
        c.restoreState()
        c.setFillColor(FOREST)
        c.setFont(F_BOLD, 7)
        c.drawString(lx + 12, ty - 11.5, str(r["key"]))
        draw_par(c, esc(r["text"]), lx + 12, ty - 15, w - PAD - (lx + 12 - x) - 4,
                 _style(F_BODY, 7.1, BODY, leading=9.6), max_h=item_h - 14)
        ty -= item_h


def _training_week_card(c, week, x, y, w, h):
    card(c, x, y, w, h)
    ty = y + h - PAD
    ty -= card_title(c, x + PAD, ty, "Weekly Training Plan", w - 2 * PAD)
    item_h = (ty - y - 10) / max(1, len(week))
    for r in week:
        chip_w = 42
        c.saveState()
        c.setFillColor(SOFT)
        c.setStrokeColor(SOFT_BORDER)
        c.roundRect(x + PAD, ty - 18, chip_w, 13, 6.5, stroke=1, fill=1)
        c.setFillColor(GREEN)
        c.setFont(F_BOLD, 5.8)
        c.drawCentredString(x + PAD + chip_w / 2, ty - 14, str(r["day"]))
        c.restoreState()
        mins = str(r.get("mins") or "")
        mins_w = c.stringWidth(mins, F_BOLD, 6.4) + 4 if mins else 0
        draw_par(c, f"<b>{esc(r['name'])}</b>", x + PAD + chip_w + 8, ty - 5,
                 w - 2 * PAD - chip_w - 8 - mins_w, _style(F_BOLD, 7.4, INK, leading=9.4),
                 max_h=item_h - 4)
        if mins:
            c.setFillColor(MUTED)
            c.setFont(F_BOLD, 6.4)
            c.drawRightString(x + w - PAD, ty - 14, mins)
        ty -= item_h


def _parent_tips_card(c, tips, x, y, w, h):
    card(c, x, y, w, h)
    ty = y + h - PAD
    ty -= card_title(c, x + PAD, ty, "Tips for Parents", w - 2 * PAD)
    item_h = (ty - y - 8) / max(1, len(tips))
    for t in tips:
        draw_star(c, x + PAD + 5, ty - 10, 4.6, GOLD)
        draw_par(c, esc(t), x + PAD + 16, ty - 4, w - 2 * PAD - 16,
                 _style(F_BODY, 7.2, BODY, leading=9.8), max_h=item_h - 2)
        ty -= item_h


def _action_timeline_card(c, actions, x, y, w, h):
    card(c, x, y, w, h)
    ty = y + h - PAD
    ty -= card_title(c, x + PAD, ty, "Action Timeline", w - 2 * PAD)
    row_h = (ty - y - 4) / max(1, len(actions))
    lx = x + PAD + 5
    c.saveState()
    c.setStrokeColor(SOFT_BORDER)
    c.setLineWidth(1.2)
    c.line(lx, y + 10, lx, ty - 8)
    c.restoreState()
    orange = HexColor("#DD6B20")
    for a in actions:
        cy = ty - row_h / 2
        col = orange if a.get("outcome") == "negative" else FOREST
        c.saveState()
        c.setFillColor(col)
        c.setStrokeColor(HexColor("#FFFFFF"))
        c.setLineWidth(1.2)
        c.circle(lx, cy, 3.1, stroke=1, fill=1)
        ts = str(a.get("timestamp") or "")
        chip_w = c.stringWidth(ts, F_BLACK, 7) + 10
        c.setFillColor(FOREST)
        c.roundRect(lx + 10, cy - 6.5, chip_w, 13, 5, stroke=0, fill=1)
        c.setFillColor(LIME)
        c.setFont(F_BLACK, 7)
        c.drawCentredString(lx + 10 + chip_w / 2, cy - 2.4, ts)
        tx0 = lx + 16 + chip_w
        c.setFillColor(INK)
        c.setFont(F_BOLD, 7.6)
        title_txt = str(a.get("title") or "").upper()
        c.drawString(tx0, cy + 1.5, title_txt)
        if a.get("tracked"):
            bx = tx0 + c.stringWidth(title_txt, F_BOLD, 7.6) + 5
            lbl = "TRACKED"
            bw2 = c.stringWidth(lbl, F_BLACK, 5.2) + 15
            c.setFillColor(FOREST)
            c.roundRect(bx, cy + 0.2, bw2, 8.5, 3, stroke=0, fill=1)
            c.setStrokeColor(LIME)
            c.setLineWidth(0.9)
            c.lines([(bx + 4, cy + 4.2, bx + 5.4, cy + 2.8), (bx + 5.4, cy + 2.8, bx + 8, cy + 6.2)])
            c.setFillColor(LIME)
            c.setFont(F_BLACK, 5.2)
            c.drawString(bx + 10.5, cy + 3, lbl)
        desc = str(a.get("description") or "")
        max_w = w - PAD - tx0 - 40
        c.setFont(F_BODY, 6.6)
        while desc and c.stringWidth(desc, F_BODY, 6.6) > max_w:
            desc = desc[:-4].rstrip() + "…"
        c.setFillColor(MUTED)
        c.drawString(tx0, cy - 7.5, desc)
        if a.get("rating") is not None:
            c.setFillColor(col)
            c.setFont(F_BLACK, 9)
            c.drawRightString(x + w - PAD, cy - 3, f"{float(a['rating']):.1f}")
        c.restoreState()
        ty -= row_h


def _video_highlight_card(c, vh, x, y, w, h, resolve):
    card(c, x, y, w, h)
    ty = y + h - PAD
    ty -= card_title(c, x + PAD, ty, "Video Highlight", w - 2 * PAD)
    if not vh:
        draw_par(c, esc("No frame-stamped highlight available for this clip."), x + PAD, ty - 4,
                 w - 2 * PAD, _style(F_BODY, 7.4, MUTED, leading=10))
        return
    tw = w - 2 * PAD
    th = tw * 9 / 16
    thumb = resolve(vh.get("thumb")) if vh.get("thumb") else None
    drew = bool(thumb and draw_cover_image(c, thumb, x + PAD, ty - th, tw, th, radius=7))
    if not drew:
        th = 22  # no verified image — timestamp chip renders alone in a slim band
    if vh.get("timestamp"):
        chip = f"AT {vh['timestamp']}"
        cw2 = c.stringWidth(chip, F_BOLD, 7) + 12
        c.saveState()
        c.setFillColorRGB(0, 0, 0, 0.72)
        c.roundRect(x + PAD + 7, ty - th + 7, cw2, 14, 7, stroke=0, fill=1)
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont(F_BOLD, 7)
        c.drawCentredString(x + PAD + 7 + cw2 / 2, ty - th + 11.2, chip)
        c.restoreState()
    draw_par(c, esc(vh.get("caption") or ""), x + PAD, ty - th - 7, tw,
             _style(F_BODY, 7.2, BODY, leading=10), max_h=y + h - th - 40)


def _coach_notes_card(c, notes, x, y, w, h):
    card(c, x, y, w, h)
    ty = y + h - PAD
    ty -= card_title(c, x + PAD, ty, "Notes for the Coach", w - 2 * PAD)
    item_h = (ty - y - 8) / max(1, len(notes) or 1)
    for n in notes:
        c.saveState()
        c.setFillColor(GREEN)
        c.roundRect(x + PAD, ty - 12, 8, 8, 2, stroke=0, fill=1)
        c.setStrokeColor(HexColor("#FFFFFF"))
        c.setLineWidth(1.1)
        c.line(x + PAD + 2, ty - 8.2, x + PAD + 3.6, ty - 9.9)
        c.line(x + PAD + 3.6, ty - 9.9, x + PAD + 6.2, ty - 6.2)
        c.restoreState()
        draw_par(c, esc(n), x + PAD + 14, ty - 4, w - 2 * PAD - 14,
                 _style(F_BODY, 7.2, BODY, leading=9.8), max_h=item_h - 2)
        ty -= item_h


def _scout_outlook_card(c, so, x, y, w, h):
    card(c, x, y, w, h)
    ty = y + h - PAD
    ty -= card_title(c, x + PAD, ty, "Scout Outlook", w - 2 * PAD)
    for label, val_key, dots_key in (("CURRENT LEVEL", "currentLabel", "currentDots"),
                                     ("POTENTIAL LEVEL", "potentialLabel", "potentialDots")):
        c.setFillColor(MUTED)
        c.setFont(F_BOLD, 5.8)
        c.drawString(x + PAD, ty - 7, label)
        c.setFillColor(INK)
        c.setFont(F_BOLD, 8.6)
        c.drawString(x + PAD, ty - 19, str(so[val_key]))
        draw_dots(c, x + w - PAD - 5 * (2 * 3.4 + 4.6), ty - 18.5, int(so[dots_key] or 0))
        ty -= 30
    c.saveState()
    c.setFillColor(SOFT)
    c.setStrokeColor(SOFT_BORDER)
    c.roundRect(x + PAD, ty - 30, w - 2 * PAD, 26, 7, stroke=1, fill=1)
    c.setFillColor(MUTED)
    c.setFont(F_BOLD, 5.6)
    c.drawString(x + PAD + 8, ty - 13, "RECRUITMENT READINESS")
    c.setFillColor(GREEN)
    c.setFont(F_BOLD, 8)
    c.drawString(x + PAD + 8, ty - 24, str(so["readiness"]))
    c.restoreState()
    ty -= 40
    c.setFillColor(MUTED)
    c.setFont(F_BOLD, 5.8)
    c.drawString(x + PAD, ty - 7, "LONG-TERM POTENTIAL")
    c.setFillColor(INK)
    c.setFont(F_BOLD, 8.6)
    c.drawString(x + PAD, ty - 19, str(so["longTerm"]))
    draw_par(c, esc(so.get("longTermNote") or ""), x + PAD, ty - 24, w - 2 * PAD,
             _style(F_BODY, 6.9, BODY, leading=9.4), max_h=ty - y - 14)


# ═══════════════════════ page furniture ═══════════════════════

def _page_bg(c):
    c.saveState()
    c.setFillColor(CREAM)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.restoreState()


def _wordmark(c, x, y, size=19):
    c.setFont(F_BLACK, size)
    c.setFillColor(FOREST)
    c.drawString(x, y, "SCOUT")
    w1 = c.stringWidth("SCOUT", F_BLACK, size)
    c.setFillColor(LIME)
    c.drawString(x + w1, y, "ME")
    w2 = c.stringWidth("ME", F_BLACK, size)
    c.setFillColor(FOREST)
    c.drawString(x + w1 + w2, y, "PLAY")
    return w1 + w2 + c.stringWidth("PLAY", F_BLACK, size)


def _header(c, report_date):
    top = H - M
    _wordmark(c, M, top - 16)
    c.setFillColor(MUTED)
    c.setFont(F_BOLD, 6)
    c.drawString(M, top - 26, "AI POWERED PLAYER ANALYSIS")
    c.setFillColor(INK)
    c.setFont(F_BLACK, 16)
    c.drawCentredString(W / 2, top - 15, "PREMIUM PLAYER REPORT")
    chip = "INDEPENDENT  ·  EVIDENCE-BASED"
    cw2 = c.stringWidth(chip, F_BOLD, 6) + 18
    c.saveState()
    c.setFillColor(FOREST)
    c.roundRect(W / 2 - cw2 / 2, top - 33, cw2, 12, 3, stroke=0, fill=1)
    c.setFillColor(CREAM_TEXT)
    c.setFont(F_BOLD, 6)
    c.drawCentredString(W / 2, top - 29, chip)
    c.restoreState()
    c.setFillColor(MUTED)
    c.setFont(F_BOLD, 6.4)
    c.drawRightString(W - M, top - 12, "REPORT DATE")
    c.setFillColor(INK)
    c.setFont(F_BOLD, 9)
    c.drawRightString(W - M, top - 24, report_date)
    return 48


def _mini_header(c, player_name):
    top = H - M
    _wordmark(c, M, top - 12, size=12)
    c.setFillColor(MUTED)
    c.setFont(F_BOLD, 6.6)
    c.drawRightString(W - M, top - 11, f"PREMIUM PLAYER REPORT · {str(player_name).upper()}")
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.8)
    c.line(M, top - 20, W - M, top - 20)
    return 30


def _page_footer(c, page_no, total=3):
    c.setFillColor(MUTED)
    c.setFont(F_BOLD, 6)
    c.drawString(M, 14, "SCOUTMEPLAY · PREMIUM PLAYER REPORT")
    c.drawRightString(W - M, 14, f"PAGE {page_no} / {total}")


def _forest_footer(c, x, y, w, h):
    c.saveState()
    c.setFillColor(FOREST)
    c.roundRect(x, y, w, h, 9, stroke=0, fill=1)
    c.setFillColor(LIME)
    c.setFont(F_BLACK, 10)
    c.drawString(x + 16, y + h - 24, "\u275d")
    c.setFillColor(FOOT_TEXT)
    draw_par(c, esc("Talent gets you noticed. Character makes you unforgettable."),
             x + 30, y + h - 14, 130, _style(F_BODY, 7.4, FOOT_TEXT, leading=10.4))
    c.setFont(F_BLACK, 13)
    c.setFillColor(FOOT_TEXT)
    c.drawCentredString(x + w / 2, y + h / 2 + 2, "SCOUTMEPLAY")
    c.setFillColor(FOOT_MUTED)
    c.setFont(F_BOLD, 5.6)
    c.drawCentredString(x + w / 2, y + h / 2 - 9, "YOUR JOURNEY. OUR ANALYSIS. YOUR FUTURE.")
    draw_par(c, esc("Thank you for trusting ScoutMePlay. We are excited to be part of your journey!"),
             x + w - 160, y + h - 14, 144, _style(F_BODY, 7.2, FOOT_TEXT, leading=10, align=TA_RIGHT))
    c.restoreState()


def _promo_strip(c, x, y, w, h):
    """Marketing strip for SHARED PDFs only — QR + pro-scout CTA."""
    c.saveState()
    c.setFillColor(CARD)
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.8)
    c.roundRect(x, y, w, h, 9, stroke=1, fill=1)
    qr_side = h - 16
    try:
        import qrcode
        qr = qrcode.QRCode(border=1, box_size=8)
        qr.add_data(PROMO_URL)
        qr.make(fit=True)
        raw = qr.make_image(fill_color=(18, 64, 42), back_color="white")
        img = (raw.get_image() if hasattr(raw, "get_image") else raw).convert("RGB")
        c.drawImage(ImageReader(img), x + w - qr_side - 8, y + 8, qr_side, qr_side)
    except Exception:
        qr_side = 0
    tx = x + 16
    c.setFillColor(FOREST)
    c.setFont(F_BLACK, 11)
    c.drawString(tx, y + h - 26, "PRO SCOUT ANALYSIS FOR EVERY PLAYER")
    c.setFillColor(BODY)
    c.setFont(F_BODY, 7.6)
    c.drawString(tx, y + h - 40, "This report was produced by ScoutMePlay's professional-grade scouting engine.")
    c.setFont(F_BODY, 7.6)
    c.drawString(tx, y + h - 51, "Get your own player report at ")
    lw = c.stringWidth("Get your own player report at ", F_BODY, 7.6)
    c.setFillColor(GREEN)
    c.setFont(F_BOLD, 7.8)
    c.drawString(tx + lw, y + h - 51, "scoutmeplay.com")
    c.restoreState()


def _photo_candidates(doc):
    cands = []
    for ov, fn in (("display_crop_url_override", "display_crop_filename"),
                   ("subject_crop_url_override", "subject_crop_filename"),
                   ("marker_url_override", "marker_filename"),
                   ("poster_url_override", "poster_filename")):
        if doc.get(ov):
            cands.append(doc[ov])
        if doc.get(fn):
            cands.append(f"/api/uploads/{doc[fn]}")
    return cands


def _pick_hero_photo(doc, resolve):
    for url in _photo_candidates(doc):
        p = resolve(url)
        if not p:
            continue
        try:
            with PILImage.open(p) as im:
                iw, ih = im.size
            if iw >= 120 and ih >= 120 and iw / ih >= 0.45:
                return p
        except Exception:
            continue
    return None


def _movement_map_card(c, mm, x, y, w, h):
    """Measured optical-tracking movement map: dark trail panel + metric chips."""
    card(c, x, y, w, h)
    ty = y + h - PAD
    ty -= card_title(c, x + PAD, ty, "Movement Map · Measured Data", w - 2 * PAD)
    # measured chip on the title line
    chip = "MEASURED · OPTICAL TRACKING"
    cw2 = c.stringWidth(chip, F_BLACK, 5.6) + 12
    c.saveState()
    c.setFillColor(FOREST)
    c.roundRect(x + w - PAD - cw2, ty + 8, cw2, 11, 3, stroke=0, fill=1)
    c.setFillColor(HexColor("#CCFF00"))
    c.setFont(F_BLACK, 5.6)
    c.drawCentredString(x + w - PAD - cw2 / 2, ty + 11.4, chip)
    c.restoreState()

    trail = mm.get("trail") or []
    pl_x, pl_top = x + PAD, ty - 4
    pl_w = (w - 3 * PAD) * 0.56
    pl_h = min(pl_w * 9 / 16, pl_top - y - PAD)
    pl_y = pl_top - pl_h
    c.saveState()
    p = c.beginPath()
    p.roundRect(pl_x, pl_y, pl_w, pl_h, 8)
    c.clipPath(p, stroke=0, fill=0)
    c.setFillColor(HexColor("#0D2818"))
    c.rect(pl_x, pl_y, pl_w, pl_h, stroke=0, fill=1)
    c.setStrokeColor(HexColor("#1D4230"))
    c.setLineWidth(0.5)
    for fx in (0.25, 0.5, 0.75):
        c.line(pl_x + pl_w * fx, pl_y, pl_x + pl_w * fx, pl_y + pl_h)
    for fy in (1 / 3, 2 / 3):
        c.line(pl_x, pl_y + pl_h * fy, pl_x + pl_w, pl_y + pl_h * fy)

    def _px(pt):
        return pl_x + float(pt["x"]) * pl_w, pl_y + pl_h - float(pt["y"]) * pl_h

    c.setFillColor(HexColor("#CCFF00"))
    c.setFillAlpha(0.055)
    for pt in trail:
        cx2, cy2 = _px(pt)
        c.circle(cx2, cy2, 13, stroke=0, fill=1)
    c.setFillAlpha(1)
    c.setStrokeColor(HexColor("#CCFF00"))
    c.setStrokeAlpha(0.85)
    c.setLineWidth(1.1)
    c.setLineCap(1)
    prev = None
    for pt in trail:
        cur = _px(pt)
        if prev is not None and pt["t"] - prev[2] <= 0.6:
            c.line(prev[0], prev[1], cur[0], cur[1])
        prev = (cur[0], cur[1], pt["t"])
    c.setStrokeAlpha(1)
    for pt in trail:
        if not pt.get("tap"):
            continue
        cx2, cy2 = _px(pt)
        c.setStrokeColor(HexColor("#FFFFFF"))
        c.setLineWidth(0.9)
        c.circle(cx2, cy2, 3.4, stroke=1, fill=0)
        c.setFillColor(HexColor("#FFFFFF"))
        c.circle(cx2, cy2, 1.1, stroke=0, fill=1)
    c.restoreState()
    c.saveState()
    c.setFillColor(HexColor("#5F7A66"))
    c.setFont(F_BOLD, 5.2)
    c.drawString(pl_x + 6, pl_y + 5, "PLAYER PATH IN FRAME · WHITE RINGS = YOUR TAPS")
    c.restoreState()

    rx = pl_x + pl_w + PAD
    rw = x + w - PAD - rx
    chip_w = (rw - 12) / 3
    stats = [
        (str(mm.get("bursts", 0)), "EXPLOSIVE", "ACTIONS"),
        (f"{mm.get('tracked_seconds', 0)}s", "TRACKED", "PLAY"),
        (str(mm.get("intensity", 0)), "INTENSITY", "INDEX /100"),
    ]
    ch = 52
    for i, (val, l1, l2) in enumerate(stats):
        bx = rx + i * (chip_w + 6)
        card(c, bx, pl_top - ch, chip_w, ch, fill=HexColor("#FBF9F3"), r=7)
        c.setFillColor(INK)
        c.setFont(F_BLACK, 14)
        c.drawCentredString(bx + chip_w / 2, pl_top - ch + 26, val)
        c.setFillColor(MUTED)
        c.setFont(F_BOLD, 5)
        c.drawCentredString(bx + chip_w / 2, pl_top - ch + 15, l1)
        c.drawCentredString(bx + chip_w / 2, pl_top - ch + 8, l2)
    fy2 = pl_top - ch - 10
    fh = 38
    c.saveState()
    c.setFillColor(FOREST)
    c.roundRect(rx, fy2 - fh, rw, fh, 8, stroke=0, fill=1)
    c.setFillColor(HexColor("#A9BC9C"))
    c.setFont(F_BOLD, 5.6)
    c.drawString(rx + 10, fy2 - 13, "FASTEST MEASURED MOMENT")
    c.setFillColor(HexColor("#CCFF00"))
    c.setFont(F_BLACK, 13)
    c.drawString(rx + 10, fy2 - 29, f"{mm.get('top_speed_t', '—')}  ·  {mm.get('top_speed_idx', 0)}/100 PACE")
    c.restoreState()
    draw_par(
        c,
        esc("Measured frame-by-frame with optical tracking seeded by the parent's own player taps — "
            "mathematical data, not AI estimates."),
        rx, fy2 - fh - 8, rw, _style(F_BODY, 6.6, MUTED, leading=9.4),
    )


def _player_twin_card(c, lens, neighbors, x, y, w, h):
    """FIFA Pro similarity — the player's 'style twin' + top-5 nearest pros."""
    card(c, x, y, w, h)
    ty = y + h - PAD
    ty -= card_title(c, x + PAD, ty, "Player Twin · FIFA Pro Similarity", w - 2 * PAD)
    lx = x + PAD
    lw2 = (w - 3 * PAD) * 0.46
    pct = float(lens.get("similarity_pct") or 0)
    c.setFillColor(MUTED)
    c.setFont(F_BOLD, 6)
    c.drawString(lx, ty - 8, "YOUR CLOSEST SENIOR-PRO STYLE MATCH")
    c.setFillColor(INK)
    c.setFont(F_BLACK, 20)
    c.drawString(lx, ty - 28, str(lens.get("name") or "—"))
    sub = " · ".join(s for s in (lens.get("club"), lens.get("league")) if s)
    c.setFillColor(BODY)
    c.setFont(F_BODY, 7.4)
    c.drawString(lx, ty - 40, sub)
    c.setFillColor(FOREST)
    c.setFont(F_BLACK, 30)
    c.drawString(lx, ty - 74, f"{pct:.0f}%")
    pw2 = c.stringWidth(f"{pct:.0f}%", F_BLACK, 30)
    c.setFillColor(MUTED)
    c.setFont(F_BOLD, 7)
    c.drawString(lx + pw2 + 6, ty - 74, "STYLE MATCH")
    draw_bar(c, lx, ty - 86, lw2, 7, pct)
    attrs = [str(a).replace("_", " ").title() for a in (lens.get("nearest_attrs") or [])[:3]]
    if attrs:
        c.setFillColor(MUTED)
        c.setFont(F_BOLD, 5.6)
        c.drawString(lx, ty - 100, "CLOSEST ATTRIBUTES")
        ax = lx
        for a in attrs:
            aw = c.stringWidth(a.upper(), F_BOLD, 6) + 12
            c.saveState()
            c.setFillColor(SOFT)
            c.setStrokeColor(SOFT_BORDER)
            c.roundRect(ax, ty - 116, aw, 12, 6, stroke=1, fill=1)
            c.setFillColor(GREEN)
            c.setFont(F_BOLD, 6)
            c.drawCentredString(ax + aw / 2, ty - 112, a.upper())
            c.restoreState()
            ax += aw + 5
    draw_par(
        c,
        esc(lens.get("why") or ""),
        lx, ty - 126, lw2, _style(F_BODY, 6.6, MUTED, leading=9.4),
    )

    rx = lx + lw2 + PAD
    rw = x + w - PAD - rx
    c.setFillColor(FOREST)
    c.setFont(F_BOLD, 6.4)
    c.drawString(rx, ty - 8, "TOP 5 CLOSEST PROS — REAL SIMILARITY SEARCH")
    ry = ty - 20
    row_h = min(24.0, (ry - y - PAD - 14) / max(1, len(neighbors[:5])))
    for i, n in enumerate(neighbors[:5]):
        cy2 = ry - i * row_h - row_h / 2
        c.saveState()
        c.setFillColor(FOREST if i == 0 else HexColor("#DCE3D2"))
        c.circle(rx + 6, cy2, 6, stroke=0, fill=1)
        c.setFillColor(HexColor("#FFFFFF") if i == 0 else BODY)
        c.setFont(F_BLACK, 6.4)
        c.drawCentredString(rx + 6, cy2 - 2.2, str(i + 1))
        c.setFillColor(INK)
        c.setFont(F_BOLD, 7.6)
        c.drawString(rx + 17, cy2 + 1, str(n.get("name") or ""))
        c.setFillColor(MUTED)
        c.setFont(F_BODY, 5.8)
        club = " · ".join(s for s in (n.get("club"), n.get("position")) if s)
        c.drawString(rx + 17, cy2 - 7, club[:52])
        npct = float(n.get("similarity_pct") or 0)
        draw_bar(c, rx + rw - 74, cy2 - 2.4, 46, 5, npct)
        c.setFillColor(FOREST)
        c.setFont(F_BLACK, 7.6)
        c.drawRightString(rx + rw, cy2 - 2, f"{npct:.0f}%")
        c.restoreState()
    draw_par(
        c,
        esc("Similarity search across 7,473 FIFA-rated senior pros (22 attributes). Style similarity — "
            "not a career prediction. Capped at 92% for honesty."),
        rx, ry - len(neighbors[:5]) * row_h - 4, rw, _style(F_BODY, 6, MUTED, leading=8.6),
    )


PROG_COLORS = {
    "overall": HexColor("#CCFF00"), "technical": HexColor("#7BA05B"),
    "tactical": HexColor("#E8B32C"), "physical": HexColor("#7FB6C9"),
    "mentality": HexColor("#DE8A5A"),
}
ORANGE_DOWN = HexColor("#DD6B20")


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "TH"
    else:
        suf = {1: "ST", 2: "ND", 3: "RD"}.get(n % 10, "TH")
    return f"{n}{suf}"


def _tri(c, cx, cy, s, up=True, color=FOREST):
    c.saveState()
    p = c.beginPath()
    if up:
        p.moveTo(cx - s, cy - s / 1.6)
        p.lineTo(cx + s, cy - s / 1.6)
        p.lineTo(cx, cy + s)
    else:
        p.moveTo(cx - s, cy + s / 1.6)
        p.lineTo(cx + s, cy + s / 1.6)
        p.lineTo(cx, cy - s)
    p.close()
    c.setFillColor(color)
    c.drawPath(p, stroke=0, fill=1)
    c.restoreState()


def _delta_mark(c, cx, cy, direction, color):
    if direction == "flat":
        c.saveState()
        c.setStrokeColor(color)
        c.setLineWidth(1.6)
        c.line(cx - 3, cy, cx + 3, cy)
        c.restoreState()
    else:
        _tri(c, cx, cy, 3.4, up=(direction == "up"), color=color)


def _progress_strip(c, prog, x, y, w, h):
    """Compact page-1 banner: since-date + 5 category delta chips."""
    c.saveState()
    c.setFillColor(FOREST)
    c.roundRect(x, y, w, h, 9, stroke=0, fill=1)
    c.setFillColor(HexColor("#CCFF00"))
    c.setFont(F_BLACK, 8)
    c.drawString(x + 14, y + h - 17, "DEVELOPMENT CURVE")
    sub = f"{_ordinal(prog.get('analysis_number', 2))} ANALYSIS"
    if prog.get("prev_date_label"):
        sub += f" · SINCE {prog['prev_date_label']}"
    if prog.get("days_since") is not None:
        sub += f" ({prog['days_since']} DAYS)"
    c.setFillColor(HexColor("#A9BC9C"))
    c.setFont(F_BOLD, 5.6)
    c.drawString(x + 14, y + h - 27, sub)
    cats = prog.get("categories") or []
    chip_w, gap = 62, 6
    cx0 = x + w - 12 - len(cats) * chip_w - (len(cats) - 1) * gap
    for i, cat in enumerate(cats):
        bx = cx0 + i * (chip_w + gap)
        c.setFillColor(HexColor("#1C5236"))
        c.roundRect(bx, y + 7, chip_w, h - 14, 6, stroke=0, fill=1)
        c.setFillColor(HexColor("#A9BC9C"))
        c.setFont(F_BOLD, 4.6)
        c.drawCentredString(bx + chip_w / 2, y + h - 16, str(cat["label"]).upper())
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont(F_BLACK, 8)
        txt = f"{cat['prev']:.1f} > {cat['cur']:.1f}"
        c.drawCentredString(bx + chip_w / 2 - 5, y + 12, txt)
        col = HexColor("#CCFF00") if cat["dir"] == "up" else (ORANGE_DOWN if cat["dir"] == "down" else HexColor("#A9BC9C"))
        _delta_mark(c, bx + chip_w / 2 + c.stringWidth(txt, F_BLACK, 8) / 2 + 6, y + 15, cat["dir"], col)
    c.restoreState()


def _progress_curve(c, series, x, y, w, h):
    """Dark line-chart panel: one line per category + bold lime overall."""
    c.saveState()
    p = c.beginPath()
    p.roundRect(x, y, w, h, 8)
    c.clipPath(p, stroke=0, fill=0)
    c.setFillColor(HexColor("#0D2818"))
    c.rect(x, y, w, h, stroke=0, fill=1)
    L, R, T, B = 26, 10, 8, 16
    n = len(series)
    vals = [s[k] for s in series for k in ("technical", "tactical", "physical", "mentality", "overall")
            if isinstance(s.get(k), (int, float))]
    lo = max(0, int(min(vals) - 1)) if vals else 2
    hi = min(10, int(max(vals) + 1) + 1) if vals else 10
    if hi - lo < 3:
        lo = max(0, hi - 3)
    span = hi - lo

    def X(i):
        return x + L + i * (w - L - R) / max(1, n - 1)

    def Y(v):
        return y + B + (max(lo, min(hi, v)) - lo) * (h - T - B) / span

    c.setStrokeColor(HexColor("#1D4230"))
    c.setLineWidth(0.5)
    c.setFont(F_BOLD, 5)
    for g in range(lo, hi + 1):
        c.line(x + L, Y(g), x + w - R, Y(g))
        c.setFillColor(HexColor("#5F7A66"))
        c.drawRightString(x + L - 4, Y(g) - 1.6, str(g))
    for key in ("technical", "tactical", "physical", "mentality", "overall"):
        pts = [(X(i), Y(s[key])) for i, s in enumerate(series) if isinstance(s.get(key), (int, float))]
        if len(pts) < 2:
            continue
        c.setStrokeColor(PROG_COLORS[key])
        c.setLineWidth(1.8 if key == "overall" else 0.9)
        c.setLineCap(1)
        for a, b in zip(pts, pts[1:]):
            c.line(a[0], a[1], b[0], b[1])
        if key == "overall":
            for px, py in pts:
                c.setFillColor(PROG_COLORS["overall"])
                c.circle(px, py, 2.2, stroke=0, fill=1)
    c.setFillColor(HexColor("#8FA896"))
    c.setFont(F_BOLD, 5.4)
    for i, s in enumerate(series):
        if s.get("label"):
            c.drawCentredString(X(i), y + 4, s["label"])
    c.restoreState()


def _progress_card(c, prog, x, y, w, h):
    """Full development-curve card: delta chips, improvements, watch, curve."""
    card(c, x, y, w, h)
    ty = y + h - PAD
    ty -= card_title(c, x + PAD, ty, f"Development Curve · {_ordinal(prog.get('analysis_number', 2))} Analysis", w - 2 * PAD)
    sub = f"SINCE {prog.get('prev_date_label') or 'LAST REPORT'}"
    if prog.get("days_since") is not None:
        sub += f" · {prog['days_since']} DAYS"
    c.setFillColor(MUTED)
    c.setFont(F_BOLD, 6)
    c.drawRightString(x + w - PAD, ty + 10, sub)

    cats = prog.get("categories") or []
    chip_w = (w - 2 * PAD - (len(cats) - 1) * 6) / max(1, len(cats))
    ch = 42
    for i, cat in enumerate(cats):
        bx = x + PAD + i * (chip_w + 6)
        is_ov = cat["key"] == "overall_development"
        card(c, bx, ty - ch, chip_w, ch, fill=FOREST if is_ov else HexColor("#FBF9F3"),
             stroke=FOREST if is_ov else BORDER, r=7)
        c.setFillColor(HexColor("#A9BC9C") if is_ov else MUTED)
        c.setFont(F_BOLD, 5)
        c.drawCentredString(bx + chip_w / 2, ty - 11, str(cat["label"]).upper())
        c.setFillColor(HexColor("#FFFFFF") if is_ov else INK)
        c.setFont(F_BLACK, 10)
        txt = f"{cat['prev']:.1f} > {cat['cur']:.1f}"
        c.drawCentredString(bx + chip_w / 2, ty - 24, txt)
        col = (HexColor("#CCFF00") if is_ov else GREEN) if cat["dir"] == "up" else \
            (ORANGE_DOWN if cat["dir"] == "down" else (HexColor("#A9BC9C") if is_ov else MUTED))
        lbl = "stable" if cat["dir"] == "flat" else f"{'+' if cat['delta'] > 0 else ''}{cat['delta']:.1f}"
        c.setFillColor(col)
        c.setFont(F_BLACK, 6.6)
        lw2 = c.stringWidth(lbl, F_BLACK, 6.6)
        c.drawCentredString(bx + chip_w / 2 + 4, ty - 35, lbl)
        _delta_mark(c, bx + chip_w / 2 - lw2 / 2 - 3, ty - 32.6, cat["dir"], col)
    yy = ty - ch - 8

    improvements = prog.get("improvements") or []
    watch = prog.get("watch") or []
    col_h = 30 + max(len(improvements), 1) * 22
    if improvements or watch:
        lw3 = (w - 3 * PAD) * (0.56 if watch else 1.0)
        if improvements:
            card(c, x + PAD, yy - col_h, lw3, col_h, fill=SOFT, stroke=SOFT_BORDER, r=8)
            c.setFillColor(FOREST)
            c.setFont(F_BLACK, 6.6)
            c.drawString(x + PAD + 9, yy - 13, "BIGGEST IMPROVEMENTS")
            iy = yy - 24
            trained_shown = False
            for im in improvements:
                c.setFillColor(INK)
                c.setFont(F_BOLD, 7.4)
                c.drawString(x + PAD + 9, iy - 6, str(im["label"]).upper())
                pill = f"+{im['delta']:.1f}"
                pw2 = c.stringWidth(pill, F_BLACK, 7) + 10
                c.saveState()
                c.setFillColor(GREEN)
                c.roundRect(x + PAD + lw3 - 9 - pw2, iy - 9, pw2, 11, 5.5, stroke=0, fill=1)
                c.setFillColor(HexColor("#FFFFFF"))
                c.setFont(F_BLACK, 7)
                c.drawCentredString(x + PAD + lw3 - 9 - pw2 / 2, iy - 5.6, pill)
                c.restoreState()
                c.setFillColor(MUTED)
                c.setFont(F_BODY, 6.6)
                c.drawRightString(x + PAD + lw3 - 14 - pw2, iy - 5.6, f"{im['prev']:.1f} > {im['cur']:.1f}")
                if im.get("trained") and not trained_shown:
                    trained_shown = True
                    c.setFillColor(GREEN)
                    c.setFont(F_BODY, 5.6)
                    c.drawString(x + PAD + 9, iy - 14.5, "Exactly what your last report asked you to train — and it shows.")
                iy -= 22
        if watch:
            wx = x + PAD + (lw3 + PAD if improvements else 0)
            ww = x + w - PAD - wx
            card(c, wx, yy - col_h, ww, col_h, fill=HexColor("#FFF8E9"), stroke=HexColor("#F0E3C4"), r=8)
            c.setFillColor(HexColor("#8A6D3B"))
            c.setFont(F_BLACK, 6.6)
            c.drawString(wx + 9, yy - 13, "KEEP AN EYE ON")
            iy = yy - 24
            for wd in watch:
                c.setFillColor(HexColor("#6B5A35"))
                c.setFont(F_BOLD, 7.2)
                c.drawString(wx + 9, iy - 6, str(wd["label"]).upper())
                c.setFillColor(HexColor("#8A6D3B"))
                c.setFont(F_BODY, 6.8)
                c.drawRightString(wx + ww - 9, iy - 6, f"{wd['prev']:.1f} > {wd['cur']:.1f}")
                iy -= 15
            draw_par(c, esc("Normal fluctuation — often fewer situations of this type in the new footage."),
                     wx + 9, iy - 2, ww - 18, _style(F_BODY, 5.6, HexColor("#8A6D3B"), leading=7.6),
                     max_h=max(10, iy - (yy - col_h) - 4))
        yy -= col_h + 8

    series = [s for s in (prog.get("series") or []) if isinstance(s.get("overall"), (int, float))]
    if len(series) >= 3 and yy - y - PAD - 14 > 70:
        cv_h = min(105.0, yy - y - PAD - 14)
        _progress_curve(c, series, x + PAD, yy - cv_h, w - 2 * PAD, cv_h)
        yy -= cv_h + 4
    note = (f"Compared: {prog.get('compared_skills', 0)} skills observed in BOTH videos · "
            f"{prog.get('not_comparable', 0)} not comparable · changes under ±0.3 shown as stable.")
    c.setFillColor(MUTED)
    c.setFont(F_BODY, 5.6)
    c.drawString(x + PAD, y + PAD - 4, note)


def _home_drills_card(c, drills, x, y, w, h):
    card(c, x, y, w, h)
    ty = y + h - PAD
    ty -= card_title(c, x + PAD, ty, "Home Training · 10 Minutes a Day", w - 2 * PAD)
    c.setFillColor(GREEN)
    c.setFont(F_BOLD, 6)
    c.drawRightString(x + w - PAD, ty + 10, "NO PITCH NEEDED · JUST A BALL")
    cw3 = (w - 2 * PAD - 2 * GAP) / 3
    for i, dr in enumerate(drills[:3]):
        bx = x + PAD + i * (cw3 + GAP)
        card(c, bx, y + PAD, cw3, ty - y - PAD - 4, fill=HexColor("#FBF9F3"), r=8)
        iy = ty - 14
        mins = f"{dr.get('minutes')} MIN" if dr.get("minutes") else ""
        mw = c.stringWidth(mins, F_BLACK, 6.4) + 10 if mins else 0
        c.setFillColor(INK)
        name_h = draw_par(c, f"<b>{esc(str(dr.get('name', '')).upper())}</b>", bx + 8, iy + 8,
                          cw3 - 16 - mw - 4, _style(F_BOLD, 7.4, INK, leading=9.4))
        if mins:
            c.saveState()
            c.setFillColor(FOREST)
            c.roundRect(bx + cw3 - 8 - mw, iy - 3, mw, 11, 3, stroke=0, fill=1)
            c.setFillColor(HexColor("#CCFF00"))
            c.setFont(F_BLACK, 6.4)
            c.drawCentredString(bx + cw3 - 8 - mw / 2, iy + 0.4, mins)
            c.restoreState()
        iy -= max(name_h, 11) + 2
        if dr.get("equipment"):
            c.setFillColor(MUTED)
            c.setFont(F_BODY, 6)
            c.drawString(bx + 8, iy - 4, f"You need: {dr['equipment']}"[:46])
            iy -= 11
        steps = [s for s in (dr.get("steps") or []) if s][:4]
        steps_html = "<br/>".join(f"<b>{j + 1}.</b> {esc(s)}" for j, s in enumerate(steps))
        sh = draw_par(c, steps_html, bx + 8, iy - 2, cw3 - 16, _style(F_BODY, 6.4, BODY, leading=8.8),
                      max_h=iy - y - PAD - 40)
        iy -= sh + 8
        if dr.get("success_sign") and iy - 30 > y + PAD + 12:
            box_h = min(30.0, iy - y - PAD - 14)
            c.saveState()
            c.setFillColor(SOFT)
            c.setStrokeColor(SOFT_BORDER)
            c.roundRect(bx + 6, iy - box_h, cw3 - 12, box_h, 5, stroke=1, fill=1)
            c.restoreState()
            draw_par(c, esc(dr["success_sign"]), bx + 11, iy - 5, cw3 - 22,
                     _style(F_BODY, 5.8, HexColor("#3C4A40"), leading=7.6), max_h=box_h - 8)
            iy -= box_h + 6
        if dr.get("targets"):
            c.setFillColor(HexColor("#DD6B20"))
            c.setFont(F_BLACK, 5.4)
            c.drawString(bx + 8, y + PAD + 6, f"TRAINS: {str(dr['targets']).upper()}"[:44])


def _watch_together_card(c, wt, x, y, w, h):
    card(c, x, y, w, h)
    ty = y + h - PAD
    ty -= card_title(c, x + PAD, ty, "Watch the Video Together", w - 2 * PAD)
    iy = ty
    if wt.get("intro"):
        ih = draw_par(c, esc(wt["intro"]), x + PAD, iy - 2, w - 2 * PAD,
                      _style(F_BODY, 6.8, MUTED, leading=9.2))
        iy -= ih + 8
    for m in (wt.get("moments") or [])[:3]:
        if not isinstance(m, dict) or not m.get("timestamp"):
            continue
        ts = str(m["timestamp"])
        chip_w = c.stringWidth(ts, F_BLACK, 7) + 12
        txt = f"<b>Pause and say:</b> \u201c{esc(m.get('say_this') or '')}\u201d"
        p = Paragraph(txt, _style(F_BODY, 6.8, BODY, leading=9.2))
        _, phh = p.wrap(w - 2 * PAD - chip_w - 22, 200)
        row_h = max(phh + 12, 24)
        if iy - row_h < y + PAD + 34:
            break
        c.saveState()
        c.setFillColor(HexColor("#FBF9F3"))
        c.setStrokeColor(BORDER)
        c.roundRect(x + PAD, iy - row_h, w - 2 * PAD, row_h, 7, stroke=1, fill=1)
        c.setFillColor(FOREST)
        c.roundRect(x + PAD + 7, iy - row_h / 2 - 6, chip_w, 12, 4, stroke=0, fill=1)
        c.setFillColor(HexColor("#CCFF00"))
        c.setFont(F_BLACK, 7)
        c.drawCentredString(x + PAD + 7 + chip_w / 2, iy - row_h / 2 - 2.2, ts)
        c.restoreState()
        p.drawOn(c, x + PAD + chip_w + 15, iy - row_h / 2 - phh / 2)
        iy -= row_h + 6
    avoid = [a for a in (wt.get("avoid") or []) if a][:2]
    if avoid and iy - 34 > y + PAD:
        box_h = min(40.0, iy - y - PAD - 2)
        c.saveState()
        c.setFillColor(HexColor("#FFF8E9"))
        c.setStrokeColor(HexColor("#F0E3C4"))
        c.roundRect(x + PAD, iy - box_h, w - 2 * PAD, box_h, 7, stroke=1, fill=1)
        c.setFillColor(HexColor("#8A6D3B"))
        c.setFont(F_BLACK, 5.6)
        c.drawString(x + PAD + 9, iy - 11, "GOOD TO AVOID")
        c.restoreState()
        draw_par(c, "<br/>".join(f"× {esc(a)}" for a in avoid), x + PAD + 9, iy - 15,
                 w - 2 * PAD - 18, _style(F_BODY, 6.2, HexColor("#6B5A35"), leading=8.6), max_h=box_h - 16)


def _letter_card(c, msg, x, y, w, h, player_name):
    first = str(player_name or "").split(" ")[0]
    card(c, x, y, w, h, fill=HexColor("#FFFDF2"))
    ty = y + h - PAD
    title = f"A Message for {first}" if first else "A Message for You"
    ty -= card_title(c, x + PAD, ty, title, w - 2 * PAD)
    iy = ty - 2
    if msg.get("greeting"):
        c.setFillColor(FOREST)
        c.setFont(F_SCRIPT, 16)
        c.drawString(x + PAD + 2, iy - 12, str(msg["greeting"]))
        iy -= 20
    bh = draw_par(c, esc(msg.get("body") or ""), x + PAD + 2, iy - 2, w - 2 * PAD - 4,
                  _style(F_SCRIPT, 13, HexColor("#2C3B31"), leading=16.5), max_h=iy - y - PAD - 22)
    iy -= bh + 8
    if msg.get("signoff") and iy > y + PAD + 10:
        draw_par(c, esc(str(msg["signoff"])), x + PAD + 2, iy - 2, w - 2 * PAD - 4,
                 _style(F_SCRIPT, 12, GREEN, leading=15, align=TA_RIGHT), max_h=iy - y - PAD)


def _seal(c, cx, cy, r, label1, label2):
    c.saveState()
    c.setStrokeColor(FOREST)
    c.setLineWidth(1.6)
    c.circle(cx, cy, r, stroke=1, fill=0)
    c.setLineWidth(0.7)
    c.circle(cx, cy, r - 3.5, stroke=1, fill=0)
    draw_star(c, cx, cy + r * 0.36, r * 0.22, GOLD)
    c.setFillColor(FOREST)
    c.setFont(F_BLACK, 6.2)
    c.drawCentredString(cx, cy - 4, label1)
    c.setFont(F_BOLD, 4.6)
    c.drawCentredString(cx, cy - 11.5, label2)
    c.restoreState()


def _diploma_page(c, d, pd, report_date, tracked=False, prog=None):
    """Full-page certificate the player can print and hang on the wall."""
    _page_bg(c)
    c.saveState()
    c.setStrokeColor(FOREST)
    c.setLineWidth(2.2)
    c.roundRect(M, M + 8, W - 2 * M, H - 2 * M - 8, 14, stroke=1, fill=0)
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.9)
    c.roundRect(M + 7, M + 15, W - 2 * M - 14, H - 2 * M - 22, 10, stroke=1, fill=0)
    c.restoreState()

    wm_size = 22
    wm_w = sum(c.stringWidth(s, F_BLACK, wm_size) for s in ("SCOUT", "ME", "PLAY"))
    _wordmark(c, (W - wm_w) / 2, H - 96, size=wm_size)
    c.setFillColor(MUTED)
    c.setFont(F_BOLD, 6.4)
    c.drawCentredString(W / 2, H - 108, "AI POWERED PLAYER ANALYSIS")

    c.saveState()
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.line(W / 2 - 110, H - 128, W / 2 - 14, H - 128)
    c.line(W / 2 + 14, H - 128, W / 2 + 110, H - 128)
    draw_star(c, W / 2, H - 128, 6, GOLD)
    c.restoreState()

    c.setFillColor(INK)
    c.setFont(F_BLACK, 30)
    c.drawCentredString(W / 2, H - 168, "CERTIFICATE OF ANALYSIS")
    chip = "OFFICIAL SCOUTMEPLAY PLAYER ANALYSIS"
    cw2 = c.stringWidth(chip, F_BOLD, 6.4) + 22
    c.saveState()
    c.setFillColor(FOREST)
    c.roundRect(W / 2 - cw2 / 2, H - 190, cw2, 14, 4, stroke=0, fill=1)
    c.setFillColor(CREAM_TEXT)
    c.setFont(F_BOLD, 6.4)
    c.drawCentredString(W / 2, H - 185.4, chip)
    c.restoreState()

    c.setFillColor(MUTED)
    c.setFont(F_BOLD, 8)
    c.drawCentredString(W / 2, H - 238, "T H I S   C E R T I F I E S   T H A T")
    name = str(pd.get("player_name") or "Player")
    c.setFillColor(GREEN)
    c.setFont(F_SCRIPT, 52)
    c.drawCentredString(W / 2, H - 296, name)
    c.saveState()
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    nw = max(220.0, c.stringWidth(name, F_SCRIPT, 52) + 40)
    c.line(W / 2 - nw / 2, H - 310, W / 2 + nw / 2, H - 310)
    c.restoreState()
    bits = [str(pd.get("position") or "").strip()]
    if pd.get("age"):
        bits.append(f"age {pd['age']}")
    if pd.get("current_club"):
        bits.append(str(pd["current_club"]))
    c.setFillColor(BODY)
    c.setFont(F_BODY, 10.5)
    c.drawCentredString(W / 2, H - 332,
                        "has completed a full AI scouting analysis as " + ", ".join(b for b in bits if b))
    if prog:
        ov = next((cat for cat in (prog.get("categories") or []) if cat.get("key") == "overall_development"), None)
        line = f"{_ordinal(prog.get('analysis_number', 2))} ANALYSIS"
        if ov and ov.get("dir") in ("up", "flat"):
            line += " · OVERALL TREND: " + ("IMPROVING" if ov["dir"] == "up" else "STEADY")
        c.setFillColor(GREEN)
        c.setFont(F_BLACK, 8)
        c.drawCentredString(W / 2 + (5 if ov and ov.get("dir") == "up" else 0), H - 350, line)
        if ov and ov.get("dir") == "up":
            tw2 = c.stringWidth(line, F_BLACK, 8)
            _delta_mark(c, W / 2 - tw2 / 2 - 4, H - 347.4, "up", GREEN)

    # overall score donut + stars
    dcy = H - 448
    overall = d.get("overall")
    pct = (float(overall) / 10 * 100) if isinstance(overall, (int, float)) else 0
    draw_donut(c, W / 2, dcy, 56, pct, thickness=12)
    c.setFillColor(INK)
    c.setFont(F_BLACK, 32)
    c.drawCentredString(W / 2, dcy - 8, f"{overall:.1f}" if isinstance(overall, (int, float)) else "—")
    c.setFillColor(MUTED)
    c.setFont(F_BOLD, 8)
    c.drawCentredString(W / 2, dcy - 24, "/10")
    draw_stars_row(c, W / 2, dcy - 84, int(d.get("stars") or 0), r=7, gap=6)
    if d.get("playerType"):
        c.setFillColor(INK)
        c.setFont(F_BLACK, 11)
        c.drawCentredString(W / 2, dcy - 108, str(d["playerType"]).upper())

    # seals
    seals = [("AI SCOUT", "ANALYSED")]
    if tracked:
        seals.append(("OPTICAL", "TRACKING VERIFIED"))
    seals.append(("EVIDENCE", "BASED REPORT"))
    scy = 246
    total_w = len(seals) * 64 + (len(seals) - 1) * 40
    sx = W / 2 - total_w / 2 + 32
    for l1, l2 in seals:
        _seal(c, sx, scy, 32, l1, l2)
        sx += 104

    # date + signature
    base_y = 158
    c.saveState()
    c.setStrokeColor(HexColor("#B9B29A"))
    c.setLineWidth(0.8)
    c.line(M + 70, base_y, M + 210, base_y)
    c.line(W - M - 210, base_y, W - M - 70, base_y)
    c.setFillColor(MUTED)
    c.setFont(F_BOLD, 6.2)
    c.drawCentredString(M + 140, base_y - 11, "DATE OF ANALYSIS")
    c.drawCentredString(W - M - 140, base_y - 11, "SCOUTMEPLAY SCOUTING INTELLIGENCE")
    c.setFillColor(INK)
    c.setFont(F_BOLD, 9)
    c.drawCentredString(M + 140, base_y + 6, report_date)
    c.setFillColor(GREEN)
    c.setFont(F_SCRIPT, 19)
    c.drawCentredString(W - M - 140, base_y + 4, "ScoutMePlay")
    c.restoreState()

    c.setFillColor(MUTED)
    c.setFont(F_SCRIPT, 13)
    c.drawCentredString(W / 2, 104, "Talent gets you noticed. Character makes you unforgettable.")


# ═══════════════════════ main builder ═══════════════════════

def build_pdf_v2(report_doc: dict, output_path: str, image_resolver=None, promo: bool = False):
    """Render the Premium Report V2 card layout to a 3-page A4 PDF.
    promo=True adds the shared-link marketing strip (QR + CTA) on page 3."""
    resolve = image_resolver or (lambda _u: None)
    d = derive_v2(report_doc)
    pd = report_doc.get("player_details") or {}
    player_name = pd.get("player_name") or "Player"

    mm = report_doc.get("movement_map") or {}
    _arch = report_doc.get("archetype") or {}
    _lenses = _arch.get("lenses") if isinstance(_arch.get("lenses"), dict) else {}
    fifa_lens = _lenses.get("fifa") if isinstance(_lenses, dict) else None
    fifa_neighbors = _arch.get("fifa_neighbors") or []
    pp = d.get("parentsPackage")
    prog = report_doc.get("progression")
    prog = prog if isinstance(prog, dict) and prog.get("categories") else None
    has_p4 = bool(mm.get("trail") or fifa_lens or prog)
    total_pages = 4 + (1 if has_p4 else 0) + (1 if pp else 0)

    date_src = report_doc.get("full_generated_at") or report_doc.get("paid_at") or report_doc.get("created_at")
    try:
        dt = datetime.fromisoformat(str(date_src).replace("Z", "+00:00")) if date_src else datetime.now(timezone.utc)
    except Exception:
        dt = datetime.now(timezone.utc)
    report_date = dt.strftime("%d %B %Y").upper()

    c = rl_canvas.Canvas(output_path, pagesize=A4)
    c.setTitle(f"ScoutMePlay Premium Report — {player_name}")
    c.setAuthor("ScoutMePlay")

    # ── PAGE 1 — hero / parent summary / score · snapshot / stats / age ──
    _page_bg(c)
    hh = _header(c, report_date)
    row1_top = H - M - hh - 6
    h1 = 285
    c1, c2, c3 = 158, 205, CW - 158 - 205 - 2 * GAP
    hero_photo = _pick_hero_photo(report_doc, resolve)
    _hero_card(c, d, pd, M, row1_top - h1, c1, h1, hero_photo)
    _parent_summary_card(c, d["parentSummary"], M + c1 + GAP, row1_top - h1, c2, h1)
    _overall_score_card(c, d, M + c1 + c2 + 2 * GAP, row1_top - h1, c3, h1)

    row2_top = row1_top - h1 - GAP
    h2 = 240
    if d["matchStats"]:
        cw3 = (CW - 2 * GAP) / 3
        _snapshot_card(c, d["snapshot"], M, row2_top - h2, cw3, h2)
        _match_stats_card(c, d["matchStats"], M + cw3 + GAP, row2_top - h2, cw3, h2)
        _age_comparison_card(c, d["ageComparison"], d["ageBracket"], M + 2 * (cw3 + GAP), row2_top - h2, cw3, h2)
    else:
        cw2 = (CW - GAP) / 2
        _snapshot_card(c, d["snapshot"], M, row2_top - h2, cw2, h2)
        _age_comparison_card(c, d["ageComparison"], d["ageBracket"], M + cw2 + GAP, row2_top - h2, cw2, h2)

    # signature quote strip in remaining space (progress strip when a curve exists)
    strip_top = row2_top - h2 - GAP
    if strip_top - M > 46:
        sh = 44
        if prog:
            _progress_strip(c, prog, M, strip_top - sh, CW, sh)
        else:
            c.saveState()
            c.setFillColor(HexColor("#EDE8D6"))
            c.roundRect(M, strip_top - sh, CW, sh, 9, stroke=0, fill=1)
            c.setFillColor(GREEN)
            c.setFont(F_SCRIPT, 17)
            c.drawCentredString(W / 2, strip_top - sh / 2 - 6,
                                f"Every session is a step. Keep going, {player_name.split()[0]}!")
            c.restoreState()
    _page_footer(c, 1, total_pages)
    c.showPage()

    # ── PAGE 2 — top strengths / dev priorities · roadmap / training / tips ──
    _page_bg(c)
    mh = _mini_header(c, player_name)
    row3_top = H - M - mh - 4
    h3 = 360
    cs1 = 305
    _top_strengths_card(c, d["topStrengths"], M, row3_top - h3, cs1, h3, resolve)
    _dev_priorities_card(c, d["devPriorities"], M + cs1 + GAP, row3_top - h3, CW - cs1 - GAP, h3)

    row4_top = row3_top - h3 - GAP
    h4 = 330
    cw3 = (CW - 2 * GAP) / 3
    _roadmap_card(c, d["roadmap"], M, row4_top - h4, cw3, h4)
    _training_week_card(c, d["trainingWeek"], M + cw3 + GAP, row4_top - h4, cw3, h4)
    _parent_tips_card(c, d["parentTips"], M + 2 * (cw3 + GAP), row4_top - h4, cw3, h4)
    _page_footer(c, 2, total_pages)
    c.showPage()

    # ── PAGE 3 — video highlight / coach notes / scout outlook + footer ──
    _page_bg(c)
    mh = _mini_header(c, player_name)
    row5_top = H - M - mh - 4
    h5 = 400
    cv1, cv2 = 196, 168
    _video_highlight_card(c, d["videoHighlight"], M, row5_top - h5, cv1, h5, resolve)
    _coach_notes_card(c, d["coachNotes"], M + cv1 + GAP, row5_top - h5, cv2, h5)
    _scout_outlook_card(c, d["scoutOutlook"], M + cv1 + cv2 + 2 * GAP, row5_top - h5,
                        CW - cv1 - cv2 - 2 * GAP, h5)

    fy = row5_top - h5 - GAP - 78
    at = d.get("actionTimeline") or []
    if at:
        reserve = (GAP + 66 if promo else 0) + 40 + M
        avail = row5_top - h5 - 2 * GAP - 78 - reserve
        rows = min(len(at), int((avail - 31) / 19)) if avail > 90 else 0
        if rows >= 3:
            th_at = 31 + rows * 19 + 6
            _action_timeline_card(c, at[:rows], M, row5_top - h5 - GAP - th_at, CW, th_at)
            fy = row5_top - h5 - GAP - th_at - GAP - 78
    _forest_footer(c, M, fy, CW, 78)
    dy = fy - 14
    if promo:
        _promo_strip(c, M, fy - GAP - 66, CW, 66)
        dy = fy - GAP - 66 - 14
    c.setFillColor(MUTED)
    c.setFont(F_BODY, 6.2)
    if d.get("identityNote"):
        c.drawCentredString(W / 2, dy, d["identityNote"])
        dy -= 9
    c.drawCentredString(W / 2, dy,
                        "Independent player development analysis based on submitted video. Not a recruitment guarantee.")
    _page_footer(c, 3, total_pages)
    c.showPage()

    # ── PAGE 4 — development curve + measured movement map + FIFA player twin ──
    if has_p4:
        _page_bg(c)
        mh = _mini_header(c, player_name)
        yy = H - M - mh - 4
        blocks = int(bool(prog)) + int(bool(mm.get("trail"))) + int(bool(fifa_lens))
        if prog:
            series_ok = len([s for s in (prog.get("series") or [])
                             if isinstance(s.get("overall"), (int, float))]) >= 3
            h_pg = 305 if series_ok else 200
            if blocks == 1:
                _progress_card(c, prog, M, (H - h_pg) / 2, CW, h_pg)
            else:
                _progress_card(c, prog, M, yy - h_pg, CW, h_pg)
                yy -= h_pg + GAP
        if mm.get("trail"):
            if blocks == 1:
                h_mm = 235
                _movement_map_card(c, mm, M, (H - h_mm) / 2, CW, h_mm)
            else:
                h_mm = min(235.0, yy - M - 30 - (160 + GAP if fifa_lens else 0))
                if h_mm > 120:
                    _movement_map_card(c, mm, M, yy - h_mm, CW, h_mm)
                    yy -= h_mm + GAP
        if fifa_lens:
            if blocks == 1:
                h_tw = 255
                _player_twin_card(c, fifa_lens, fifa_neighbors, M, (H - h_tw) / 2, CW, h_tw)
            else:
                h_tw = min(255.0, yy - M - 30)
                if h_tw > 150:
                    _player_twin_card(c, fifa_lens, fifa_neighbors, M, yy - h_tw, CW, h_tw)
        _page_footer(c, 4, total_pages)
        c.showPage()

    # ── PAGE — Parents Package (home drills / watch together / letter) ──
    if pp:
        _page_bg(c)
        mh = _mini_header(c, player_name)
        yy = H - M - mh - 4
        if pp.get("drills"):
            h_hd = 258
            _home_drills_card(c, pp["drills"], M, yy - h_hd, CW, h_hd)
            yy -= h_hd + GAP
        if pp.get("watch") or pp.get("message"):
            cols_h = min(300.0, yy - M - 30)
            if cols_h > 140:
                if pp.get("watch") and pp.get("message"):
                    lw3 = (CW - GAP) * 0.53
                    _watch_together_card(c, pp["watch"], M, yy - cols_h, lw3, cols_h)
                    _letter_card(c, pp["message"], M + lw3 + GAP, yy - cols_h, CW - lw3 - GAP, cols_h, player_name)
                elif pp.get("watch"):
                    _watch_together_card(c, pp["watch"], M, yy - cols_h, CW, cols_h)
                else:
                    _letter_card(c, pp["message"], M, yy - cols_h, CW, cols_h, player_name)
        _page_footer(c, 4 + (1 if has_p4 else 0), total_pages)
        c.showPage()

    # ── FINAL PAGE — printable certificate / diploma ──
    _diploma_page(c, d, pd, report_date, tracked=bool(mm.get("trail")), prog=prog)
    _page_footer(c, total_pages, total_pages)
    c.showPage()
    c.save()

