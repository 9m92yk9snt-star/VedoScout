"""
snapshot_card.py — Shareable SNAPSHOT moment card (Instagram 1080×1350 PNG).

Server-side PIL render of one snapshot moment (same data as web/PDF snapshot
section): colored category header bar + timestamp, real frame with tactical
annotation, title + description, ScoutMePlay branding footer.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pdf_v2 import derive_v2

W, H = 1080, 1350
CREAM = (244, 240, 226)
CARD_BG = (251, 250, 242)
BORDER = (229, 223, 206)
INK = (18, 33, 26)
FOREST = (18, 64, 42)
GREEN = (30, 91, 60)
MUTED = (92, 102, 87)
VOLT = (204, 255, 0)

HEADERS = {
    "strength": ((30, 61, 37), (46, 84, 53)),
    "noticed": ((30, 61, 37), (46, 84, 53)),
    "hidden": ((122, 74, 16), (178, 109, 28)),
    "develop": ((94, 29, 27), (152, 50, 43)),
}
LABELS = {"strength": "BIGGEST STRENGTH", "noticed": "SCOUT NOTICED",
          "hidden": "HIDDEN TALENT", "develop": "BIGGEST DEVELOPMENT AREA"}

_FONT_DIR = Path(__file__).resolve().parent / "fonts"


def _font(name, size):
    try:
        return ImageFont.truetype(str(_FONT_DIR / name), size)
    except Exception:
        return ImageFont.load_default()


def _wrap(draw, text, font, max_w, max_lines):
    words = str(text or "").split()
    lines, cur, truncated = [], "", False
    for i, w_ in enumerate(words):
        t = (cur + " " + w_).strip()
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w_
            if len(lines) == max_lines:
                truncated = True
                cur = ""
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if truncated and lines:
        lines[-1] = lines[-1].rstrip(" ,.") + "…"
    return lines


def _hgrad(w, h, c1, c2):
    strip = Image.new("RGB", (w, 1))
    for xx in range(w):
        t = xx / max(1, w - 1)
        strip.putpixel((xx, 0), tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    return strip.resize((w, h))


def _cover(img, w, h):
    iw, ih = img.size
    target = w / h
    if iw / ih > target:
        nw = int(ih * target)
        left = (iw - nw) // 2
        img = img.crop((left, 0, left + nw, ih))
    else:
        nh = int(iw / target)
        top = (ih - nh) // 2
        img = img.crop((0, top, iw, top + nh))
    return img.resize((w, h), Image.LANCZOS)


# ── annotation primitives (y-down, same relative coords as the web SVG) ──

def _dashed_line(draw, p1, p2, color, width=8, dash=26, gap=18):
    x1, y1 = p1
    x2, y2 = p2
    dist = math.hypot(x2 - x1, y2 - y1)
    if dist == 0:
        return
    ux, uy = (x2 - x1) / dist, (y2 - y1) / dist
    pos = 0.0
    while pos < dist:
        end = min(pos + dash, dist)
        draw.line([(x1 + ux * pos, y1 + uy * pos), (x1 + ux * end, y1 + uy * end)], fill=color, width=width)
        pos = end + gap


def _dashed_ellipse(draw, bbox, color, width=8, seg=16, gap=12):
    ang = 0
    while ang < 360:
        draw.arc(bbox, start=ang, end=min(ang + seg, 360), fill=color, width=width)
        ang += seg + gap


def _arrow_head(draw, tip, angle_deg, color, size=26, width=8):
    a = math.radians(angle_deg)
    for da in (math.radians(150), -math.radians(150)):
        ex = tip[0] + size * math.cos(a + da)
        ey = tip[1] + size * math.sin(a + da)
        draw.line([tip, (ex, ey)], fill=color, width=width)


def _annot(draw, kind, x, y, w, h):
    kind = "circle" if kind == "space" else (kind or "")
    if kind in ("path", "arrow"):
        col = (126, 211, 33)
        p1 = (x + 0.38 * w, y + 0.64 * h)
        p2 = (x + 0.58 * w, y + 0.46 * h)
        draw.line([p1, p2], fill=col, width=9)
        _arrow_head(draw, p2, math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0])), col, size=30, width=9)
        if kind == "path":
            _dashed_ellipse(draw, (x + 0.14 * w, y + 0.72 * h, x + 0.46 * w, y + 0.84 * h), col)
    elif kind == "scan":
        col = (255, 255, 255)
        p1 = (x + 0.72 * w, y + 0.21 * h)
        p2 = (x + 0.46 * w, y + 0.21 * h)
        _dashed_line(draw, p1, p2, col)
        _arrow_head(draw, p2, 180, col, size=28, width=9)
        r = 9
        draw.ellipse((p1[0] + 18 - r, p1[1] - r, p1[0] + 18 + r, p1[1] + r), fill=col)
    elif kind == "run":
        col = (245, 166, 35)
        pts = []
        p0, pc, p1 = (x + 0.20 * w, y + 0.82 * h), (x + 0.42 * w, y + 0.64 * h), (x + 0.58 * w, y + 0.38 * h)
        for i in range(25):
            t = i / 24
            bx = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * pc[0] + t ** 2 * p1[0]
            by = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * pc[1] + t ** 2 * p1[1]
            pts.append((bx, by))
        for i in range(0, len(pts) - 1, 2):
            draw.line([pts[i], pts[i + 1]], fill=col, width=9)
        _arrow_head(draw, p1, math.degrees(math.atan2(p1[1] - pc[1], p1[0] - pc[0])), col, size=28, width=9)
        r = 0.075 * h
        cx, cy = x + 0.64 * w, y + 0.28 * h
        _dashed_ellipse(draw, (cx - r, cy - r, cx + r, cy + r), col)
    elif kind == "circle":
        _dashed_ellipse(draw, (x + 0.43 * w, y + 0.715 * h, x + 0.77 * w, y + 0.845 * h), (232, 68, 46))


def _icon(draw, key, cx, cy, r=20):
    white = (255, 255, 255)
    if key == "strength":
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rad = r if i % 2 == 0 else r * 0.42
            pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        draw.polygon(pts, fill=white)
    elif key == "noticed":
        draw.ellipse((cx - r * 1.3, cy - r * 0.72, cx + r * 1.3, cy + r * 0.72), outline=white, width=5)
        draw.ellipse((cx - r * 0.38, cy - r * 0.38, cx + r * 0.38, cy + r * 0.38), fill=white)
    elif key == "hidden":
        draw.polygon([(cx, cy - r * 1.05), (cx + r * 0.85, cy + r * 0.35), (cx - r * 0.85, cy + r * 0.35)], fill=white)
        draw.ellipse((cx - r * 0.85, cy - r * 0.15, cx + r * 0.85, cy + r * 1.0), fill=white)
    else:
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=white, width=5)
        draw.ellipse((cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55), outline=white, width=5)
        draw.ellipse((cx - r * 0.18, cy - r * 0.18, cx + r * 0.18, cy + r * 0.18), fill=white)


def build_snapshot_card(report_doc: dict, key: str, output_path: str, image_resolver=None) -> None:
    d = derive_v2(report_doc)
    moment = next((m for m in (d.get("snapshotMoments") or []) if m.get("key") == key), None)
    if not moment:
        raise ValueError(f"No snapshot moment for key {key}")
    resolve = image_resolver or (lambda _u: None)

    base = Image.new("RGB", (W, H), CREAM)
    bd = ImageDraw.Draw(base)

    # top eyebrow
    eyebrow = "M A T C H   S N A P S H O T"
    f_eb = _font("Barlow-Bold.ttf", 26)
    bd.text((W / 2 - bd.textlength(eyebrow, font=f_eb) / 2, 42), eyebrow, font=f_eb, fill=FOREST)

    # ── card ──
    CX, CY, CW_, CH_ = 46, 100, W - 92, 980
    HB = 96
    PH = 590
    card = Image.new("RGB", (CW_, CH_), CARD_BG)
    cd = ImageDraw.Draw(card)

    g1, g2 = HEADERS.get(key, HEADERS["noticed"])
    card.paste(_hgrad(CW_, HB, g1, g2), (0, 0))
    _icon(cd, key, 62, HB // 2)
    f_lab = _font("Barlow-Bold.ttf", 36)
    cd.text((104, HB / 2 - 21), LABELS.get(key, ""), font=f_lab, fill=(255, 255, 255))
    ts = moment.get("timestamp")
    if ts:
        f_ts = _font("Barlow-Black.ttf", 44)
        tw = cd.textlength(str(ts), font=f_ts)
        cd.text((CW_ - 36 - tw, HB / 2 - 26), str(ts), font=f_ts, fill=(255, 255, 255))
        cd.line([(CW_ - 60 - tw, 22), (CW_ - 60 - tw, HB - 22)], fill=(255, 255, 255, 90), width=3)

    # photo
    thumb_path = resolve(moment.get("thumb")) if moment.get("thumb") else None
    photo = None
    if thumb_path:
        try:
            photo = _cover(Image.open(thumb_path).convert("RGB"), CW_, PH)
        except Exception:
            photo = None
    if photo is None:
        photo = _hgrad(CW_, PH, (27, 68, 48), (11, 31, 20)).convert("RGB")
        pdr = ImageDraw.Draw(photo)
        pdr.line([(0, PH // 2), (CW_, PH // 2)], fill=(255, 255, 255, 26), width=3)
        pdr.ellipse((CW_ / 2 - 110, PH / 2 - 110, CW_ / 2 + 110, PH / 2 + 110), outline=(70, 100, 80), width=3)
    pd = ImageDraw.Draw(photo)
    _annot(pd, moment.get("annot"), 0, 0, CW_, PH)
    card.paste(photo, (0, HB))

    # title + desc
    ty = HB + PH + 34
    f_title = _font("Barlow-Black.ttf", 54)
    for line in _wrap(cd, moment.get("title") or "", f_title, CW_ - 88, 2):
        cd.text((44, ty), line, font=f_title, fill=INK)
        ty += 62
    desc = moment.get("desc")
    if desc and desc != "—":
        ty += 8
        f_desc = _font("DMSans-Regular.ttf", 31)
        for line in _wrap(cd, desc, f_desc, CW_ - 88, 3):
            cd.text((44, ty), line, font=f_desc, fill=MUTED)
            ty += 42

    # rounded-corner paste
    mask = Image.new("L", (CW_, CH_), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, CW_ - 1, CH_ - 1), radius=30, fill=255)
    base.paste(card, (CX, CY), mask)
    bd.rounded_rectangle((CX, CY, CX + CW_ - 1, CY + CH_ - 1), radius=30, outline=BORDER, width=2)

    # ── branding footer ──
    fy = CY + CH_ + 58
    f_word = _font("Barlow-Black.ttf", 58)
    scout_w = bd.textlength("SCOUT", font=f_word)
    me_w = bd.textlength("ME", font=f_word)
    play_w = bd.textlength("PLAY", font=f_word)
    total = scout_w + me_w + 26 + play_w
    x0 = W / 2 - total / 2
    bd.text((x0, fy), "SCOUT", font=f_word, fill=INK)
    bd.rounded_rectangle((x0 + scout_w + 6, fy + 2, x0 + scout_w + me_w + 20, fy + 62), radius=8, fill=VOLT)
    bd.text((x0 + scout_w + 13, fy), "ME", font=f_word, fill=INK)
    bd.text((x0 + scout_w + me_w + 26, fy), "PLAY", font=f_word, fill=INK)
    f_tag = _font("Barlow-Bold.ttf", 24)
    tag = "Y O U R   J O U R N E Y .   O U R   A N A L Y S I S .   Y O U R   F U T U R E ."
    bd.text((W / 2 - bd.textlength(tag, font=f_tag) / 2, fy + 78), tag, font=f_tag, fill=MUTED)
    f_url = _font("Barlow-Bold.ttf", 30)
    bd.text((W / 2 - bd.textlength("scoutmeplay.com", font=f_url) / 2, fy + 120), "scoutmeplay.com", font=f_url, fill=GREEN)

    base.save(output_path, "PNG")
