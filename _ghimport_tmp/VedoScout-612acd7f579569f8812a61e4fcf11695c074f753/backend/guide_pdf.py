"""guide_pdf.py — free lead-magnet PDF: "The 5 Things Every Football Parent Gets Wrong"."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

ROOT = Path(__file__).parent
OUT = ROOT / "uploads" / "guide"
OUT.mkdir(parents=True, exist_ok=True)

GUIDE_VERSION = 1
GUIDE_PATH = OUT / f"scoutmeplay-parent-guide.v{GUIDE_VERSION}.pdf"

FOREST = HexColor("#1F4F2F")
INK = HexColor("#0A0F0D")
CREAM = HexColor("#F5F1E8")
LIME = HexColor("#CCFF00")
GREY = HexColor("#6B6F66")

W, H = A4

_FONTS_OK = False


def _register_fonts():
    global _FONTS_OK
    if _FONTS_OK:
        return
    for name, fname in [("Barlow-Black", "Barlow-Black.ttf"), ("Barlow-Bold", "Barlow-Bold.ttf"),
                        ("DMSans", "DMSans-Regular.ttf"), ("Caveat", "Caveat.ttf")]:
        try:
            pdfmetrics.registerFont(TTFont(name, str(ROOT / "fonts" / fname)))
        except Exception:
            pass
    _FONTS_OK = True


def _f(name, fallback="Helvetica"):
    try:
        pdfmetrics.getFont(name)
        return name
    except Exception:
        return fallback


def _wrap(c, text, font, size, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if c.stringWidth(t, font, size) <= max_w:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _para(c, text, x, y, font, size, max_w, leading, color=INK):
    c.setFont(font, size)
    c.setFillColor(color)
    for ln in _wrap(c, text, font, size, max_w):
        c.drawString(x, y, ln)
        y -= leading
    return y


MISTAKES = [
    {
        "n": 1,
        "title": "The car ride home",
        "body": "It happens in the first sixty seconds of the drive. You ask what went wrong. Your child is still in the game — heart racing, emotions raw. All they hear is that you were disappointed.",
        "check": "After the last match, did you start talking about the game before your child did?",
        "fix": "No football talk for the first ten minutes. Then one line: \"I loved watching you play.\" Nothing else. No review. No coaching. Try it this weekend.",
    },
    {
        "n": 2,
        "title": "Mistaking pressure for dedication",
        "body": "More sessions. More camps. More private coaching. It looks like dedication — but it's the fastest way to burn a player out by fifteen. Love of the game is the engine; protect it above everything.",
        "check": "Does your child still play football for fun outside organised training — garden, park, street?",
        "fix": "Keep at least two football-free days a week. Free play counts double: it builds touch, creativity and joy at the same time.",
    },
    {
        "n": 3,
        "title": "Only noticing match day",
        "body": "The habits that decide a player's path don't show up on game day. They show up months later — sleep, food, touches on the ball between sessions. Most parents never link the two.",
        "check": "Do you know what your child did with a ball between last week's sessions?",
        "fix": "Help them build one tiny weekday routine: 15 minutes of wall passes or ball mastery, three days a week. Small, boring, unbeatable.",
    },
    {
        "n": 4,
        "title": "Praising the wrong things",
        "body": "You're rewarding goals. Scouts are watching something else entirely: decisions, movement off the ball, reactions after mistakes, communication. Praise what the game actually values.",
        "check": "Think of your last three compliments after football. Were they all about goals or results?",
        "fix": "Praise one decision per match instead: \"That pass you chose in the second half — brilliant thinking.\" Decisions are trainable; praise makes them stick.",
    },
    {
        "n": 5,
        "title": "Your expectations, their dream",
        "body": "This is the one nobody admits. It's not about their effort — it's about your expectations. When the dream quietly becomes the parent's, the player starts performing for approval instead of joy.",
        "check": "If your child chose to stop competitive football tomorrow, would they feel safe telling you?",
        "fix": "Say it out loud this week: \"I love watching you play — whatever level you play at.\" Then let their ambition set the pace, with you right behind it.",
    },
]


def _footer(c, page_label=""):
    c.setFillColor(GREY)
    c.setFont(_f("DMSans"), 8)
    c.drawString(48, 30, "ScoutMePlay — The 5 Things Every Football Parent Gets Wrong")
    if page_label:
        c.drawRightString(W - 48, 30, page_label)


def build_guide_pdf() -> Path:
    if GUIDE_PATH.exists():
        return GUIDE_PATH
    _register_fonts()
    c = rl_canvas.Canvas(str(GUIDE_PATH), pagesize=A4)

    # ── COVER ──
    c.setFillColor(FOREST)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(LIME)
    c.rect(0, H - 14, W, 14, stroke=0, fill=1)
    c.setFillColor(CREAM)
    c.setFont(_f("Barlow-Bold"), 15)
    c.drawString(56, H - 78, "SCOUT")
    lw = c.stringWidth("SCOUT", _f("Barlow-Bold"), 15)
    c.setFillColor(LIME)
    c.drawString(56 + lw, H - 78, "ME")
    c.setFillColor(CREAM)
    c.drawString(56 + lw + c.stringWidth("ME", _f("Barlow-Bold"), 15), H - 78, "PLAY")
    c.setFillColor(LIME)
    c.setFont(_f("DMSans"), 10)
    c.drawString(56, H - 250, "A FREE GUIDE FOR FOOTBALL FAMILIES")
    c.setFillColor(CREAM)
    c.setFont(_f("Barlow-Black"), 54)
    y = H - 320
    for ln in ["THE 5 THINGS", "EVERY FOOTBALL", "PARENT GETS", "WRONG"]:
        c.drawString(54, y, ln)
        y -= 60
    c.setFillColor(HexColor("#DFE8DA"))
    y -= 14
    y = _para(c, "Every mistake comes with a self-check and a fix you can use the same day. Written by people who love football and care about kids.",
              56, y, _f("DMSans"), 12.5, W - 180, 19, HexColor("#DFE8DA"))
    c.setFillColor(LIME)
    c.circle(W - 110, 130, 46, stroke=0, fill=1)
    c.setFillColor(INK)
    c.setFont(_f("Barlow-Black"), 13)
    c.drawCentredString(W - 110, 136, "FREE")
    c.drawCentredString(W - 110, 120, "GUIDE")
    c.showPage()

    # ── INTRO ──
    c.setFillColor(CREAM)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(FOREST)
    c.setFont(_f("Barlow-Black"), 30)
    c.drawString(56, H - 96, "A NOTE BEFORE YOU START")
    y = H - 140
    for para in [
        "You're reading this because you care. That already puts your child ahead — the research on youth sport is remarkably clear that supportive parents matter more than any training programme.",
        "But caring parents make predictable mistakes. We've seen them from the touchline, in the car park and in thousands of match videos. Not because parents don't try — because nobody ever tells them.",
        "This guide covers the five biggest ones. Each comes with a self-check (be honest) and a fix you can use this week. None of them require extra training hours. All of them protect the thing that actually builds players: the love of the game.",
    ]:
        y = _para(c, para, 56, y, _f("DMSans"), 12.5, W - 130, 20)
        y -= 12
    c.setFont(_f("Caveat", "Helvetica-Oblique"), 26)
    c.setFillColor(FOREST)
    c.drawString(56, y - 24, "— The ScoutMePlay team")
    _footer(c, "Introduction")
    c.showPage()

    # ── 5 MISTAKE PAGES ──
    for m in MISTAKES:
        c.setFillColor(CREAM)
        c.rect(0, 0, W, H, stroke=0, fill=1)
        c.setFillColor(FOREST)
        c.rect(0, H - 150, W, 150, stroke=0, fill=1)
        c.setFillColor(LIME)
        c.setFont(_f("Barlow-Black"), 64)
        c.drawString(56, H - 110, f"#{m['n']}")
        c.setFillColor(CREAM)
        c.setFont(_f("Barlow-Black"), 27)
        c.drawString(150, H - 84, "MISTAKE " + str(m["n"]))
        c.setFont(_f("Barlow-Bold"), 17)
        c.setFillColor(HexColor("#CFE3C8"))
        c.drawString(150, H - 112, m["title"].upper())

        y = H - 200
        y = _para(c, m["body"], 56, y, _f("DMSans"), 13, W - 130, 21)

        # self-check box
        y -= 26
        box_top = y
        check_lines = _wrap(c, m["check"], _f("DMSans"), 12.5, W - 190)
        box_h = 58 + len(check_lines) * 19
        c.setFillColor(HexColor("#EAE3D2"))
        c.roundRect(56, box_top - box_h, W - 112, box_h, 8, stroke=0, fill=1)
        c.setFillColor(FOREST)
        c.setFont(_f("Barlow-Bold"), 11)
        c.drawString(76, box_top - 28, "SELF-CHECK")
        _para(c, m["check"], 76, box_top - 50, _f("DMSans"), 12.5, W - 190, 19)

        # fix box
        y = box_top - box_h - 22
        fix_lines = _wrap(c, m["fix"], _f("DMSans"), 12.5, W - 190)
        fix_h = 58 + len(fix_lines) * 19
        c.setFillColor(FOREST)
        c.roundRect(56, y - fix_h, W - 112, fix_h, 8, stroke=0, fill=1)
        c.setFillColor(LIME)
        c.setFont(_f("Barlow-Bold"), 11)
        c.drawString(76, y - 28, "THE FIX — TRY IT THIS WEEK")
        _para(c, m["fix"], 76, y - 50, _f("DMSans"), 12.5, W - 190, 19, CREAM)

        _footer(c, f"Mistake {m['n']} of 5")
        c.showPage()

    # ── CLOSING ──
    c.setFillColor(FOREST)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(LIME)
    c.setFont(_f("Barlow-Black"), 34)
    c.drawString(56, H - 110, "WHAT HAPPENS NEXT")
    y = H - 160
    for para in [
        "Pick ONE mistake from this guide — the one that stung a little when you read it. Work on that one for the next month. Nothing else.",
        "And when you want to see your child's game the way a scout sees it — the decisions, the movement, the things goals never show — that's exactly what we built ScoutMePlay for.",
        "Upload one match video and get a free preview of your child's play. No card required to start.",
    ]:
        y = _para(c, para, 56, y, _f("DMSans"), 13, W - 130, 21, CREAM)
        y -= 14
    c.setFillColor(LIME)
    c.roundRect(56, y - 64, 260, 44, 22, stroke=0, fill=1)
    c.setFillColor(INK)
    c.setFont(_f("Barlow-Black"), 14)
    c.drawCentredString(56 + 130, y - 49, "SCOUTMEPLAY.COM")
    c.setFillColor(HexColor("#9FB89B"))
    c.setFont(_f("DMSans"), 9)
    c.drawString(56, 48, "© ScoutMePlay — share this guide freely with other football families.")
    c.showPage()

    c.save()
    return GUIDE_PATH
