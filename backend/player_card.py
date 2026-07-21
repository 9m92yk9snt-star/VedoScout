"""
player_card.py — FIFA-style shareable player card (Instagram story 1080×1920).

Server-side PIL render: player photo (display crop), overall score, position,
stars and TEC/TAC/PHY/MEN category stats in the ScoutMePlay forest/gold look.
Pure presentation — reads the same full_report data as the web report / PDF.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from pdf_v2 import derive_v2, _collect_skills, POSITION_ABBR

W, H = 1080, 1920

CREAM = (244, 240, 226)
CARD_TOP = (18, 59, 39)
CARD_BOT = (8, 28, 18)
FOREST = (18, 64, 42)
LIME = (165, 221, 95)
LIME_SOFT = (123, 160, 91)
GOLD = (232, 179, 44)
GOLD_DIM = (232, 179, 44, 150)
CREAM_TEXT = (240, 234, 216)
MUTED_ON_DARK = (150, 175, 152)
STAR_OFF = (60, 88, 66)

_FONT_DIR = Path(__file__).resolve().parent / "fonts"


def _font(name: str, size: int):
    try:
        return ImageFont.truetype(str(_FONT_DIR / name), size)
    except Exception:
        return ImageFont.load_default()


def _tlen(draw, text, font):
    return draw.textlength(text, font=font)


def _fit_font(draw, text, name, start_size, max_w, min_size=30):
    size = start_size
    while size > min_size and _tlen(draw, text, _font(name, size)) > max_w:
        size -= 4
    return _font(name, size)


def _vertical_gradient(w, h, top, bot):
    strip = Image.new("RGB", (1, h))
    for yy in range(h):
        t = yy / max(1, h - 1)
        strip.putpixel((0, yy), tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    return strip.resize((w, h))


def _radial_glow(size, color, alpha):
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse([size * 0.2, size * 0.2, size * 0.8, size * 0.8], fill=(*color, alpha))
    return glow.filter(ImageFilter.GaussianBlur(size // 6))


def _star_points(cx, cy, r):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    return pts


def _category_stats(full):
    skills = _collect_skills(full or {})
    out = []
    for key, label in (("technical", "TEC"), ("tactical", "TAC"),
                       ("physical", "PHY"), ("mentality", "MEN")):
        vals = [s["score"] for s in skills if s["category"] == key]
        out.append((label, f"{sum(vals) / len(vals):.1f}" if vals else "—"))
    return out


def _rounded_photo(photo_path, side, radius):
    img = Image.open(photo_path).convert("RGB")
    iw, ih = img.size
    m = min(iw, ih)
    img = img.crop(((iw - m) // 2, (ih - m) // 2, (iw + m) // 2, (ih + m) // 2))
    img = img.resize((side, side), Image.LANCZOS)
    mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, side, side], radius, fill=255)
    return img, mask


def build_player_card(report_doc: dict, output_path: str, photo_path: str | None = None):
    d = derive_v2(report_doc)
    pd = report_doc.get("player_details") or {}
    full = report_doc.get("full_report") or {}

    base = Image.new("RGB", (W, H), CREAM)
    # soft brand glows on the cream backdrop
    base.paste(Image.new("RGB", (W, H), CREAM), (0, 0))
    g1 = _radial_glow(900, LIME, 42)
    base.paste(g1, (W - 620, -260), g1)
    g2 = _radial_glow(1100, FOREST, 34)
    base.paste(g2, (-420, H - 760), g2)
    draw = ImageDraw.Draw(base)

    # ── top wordmark ──
    f_wm = _font("Barlow-Black.ttf", 64)
    seg = [("SCOUT", FOREST), ("ME", (123, 160, 91)), ("PLAY", FOREST)]
    total = sum(_tlen(draw, s, f_wm) for s, _ in seg)
    x = (W - total) / 2
    for s, col in seg:
        draw.text((x, 96), s, font=f_wm, fill=col)
        x += _tlen(draw, s, f_wm)
    f_sub = _font("Barlow-Bold.ttf", 26)
    sub = "P R O   S C O U T   A N A L Y S I S"
    draw.text(((W - _tlen(draw, sub, f_sub)) / 2, 178), sub, font=f_sub, fill=(107, 124, 106))

    # ── the card ──
    cx0, cy0, cx1, cy1 = 110, 270, W - 110, 1590
    cw, ch = cx1 - cx0, cy1 - cy0
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([cx0 + 6, cy0 + 22, cx1 + 6, cy1 + 22], 52, fill=(10, 25, 15, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(24))
    base.paste(shadow, (0, 0), shadow)

    grad = _vertical_gradient(cw, ch, CARD_TOP, CARD_BOT)
    card_mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(card_mask).rounded_rectangle([0, 0, cw, ch], 52, fill=255)
    base.paste(grad, (cx0, cy0), card_mask)

    # lime glow inside top of card
    inner_glow = _radial_glow(760, LIME, 34)
    glow_layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    glow_layer.paste(inner_glow, (-220, -300), inner_glow)
    glow_masked = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    glow_masked.paste(glow_layer, (0, 0), card_mask)
    base.paste(glow_masked, (cx0, cy0), glow_masked)

    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle([cx0 + 14, cy0 + 14, cx1 - 14, cy1 - 14], 42, outline=GOLD_DIM, width=3)

    # ── score block (top-left, FIFA style) ──
    overall = d["overall"]
    score_txt = f"{overall:.1f}" if overall is not None else "—"
    f_score = _font("Barlow-Black.ttf", 170)
    draw.text((cx0 + 62, cy0 + 44), score_txt, font=f_score, fill=GOLD)
    f_lab = _font("Barlow-Bold.ttf", 27)
    draw.text((cx0 + 68, cy0 + 218), "OVERALL", font=f_lab, fill=MUTED_ON_DARK)
    abbr = str(d["positionAbbr"])
    f_pos = _font("Barlow-Black.ttf", 78 if len(abbr) <= 3 else 54)
    draw.text((cx0 + 64, cy0 + 258), abbr, font=f_pos, fill=CREAM_TEXT)
    age = pd.get("age")
    if age is not None:
        chip = f"AGE {age}"
        f_chip = _font("Barlow-Bold.ttf", 28)
        tw = _tlen(draw, chip, f_chip)
        draw.rounded_rectangle([cx0 + 64, cy0 + 366, cx0 + 64 + tw + 36, cy0 + 414], 24,
                               fill=None, outline=LIME_SOFT, width=2)
        draw.text((cx0 + 82, cy0 + 374), chip, font=f_chip, fill=LIME)

    # ── photo (top-right) ──
    ps = 430
    px, py = cx1 - ps - 64, cy0 + 58
    if photo_path:
        try:
            img, mask = _rounded_photo(photo_path, ps, 34)
            base.paste(img, (px, py), mask)
            draw.rounded_rectangle([px, py, px + ps, py + ps], 34, outline=(*LIME_SOFT, 210), width=3)
        except Exception:
            photo_path = None
    if not photo_path:
        draw.rounded_rectangle([px, py, px + ps, py + ps], 34, fill=(12, 40, 26), outline=(*LIME_SOFT, 210), width=3)
        initials = "".join(p[0] for p in str(pd.get("player_name") or "P").split()[:2]).upper()
        f_init = _font("Barlow-Black.ttf", 160)
        tw = _tlen(draw, initials, f_init)
        draw.text((px + (ps - tw) / 2, py + ps / 2 - 100), initials, font=f_init, fill=LIME_SOFT)

    # ── name ──
    name = str(pd.get("player_name") or "PLAYER").upper()
    f_name = _fit_font(draw, name, "Barlow-Black.ttf", 96, cw - 140)
    nw = _tlen(draw, name, f_name)
    ny = cy0 + 560
    draw.text((cx0 + (cw - nw) / 2, ny), name, font=f_name, fill=CREAM_TEXT)

    # ── player type (script accent) ──
    ptype = str(d["playerType"] or "").strip()
    if ptype:
        f_type = _fit_font(draw, ptype, "Caveat.ttf", 64, cw - 220, min_size=40)
        tw = _tlen(draw, ptype, f_type)
        draw.text((cx0 + (cw - tw) / 2, ny + 120), ptype, font=f_type, fill=LIME)

    # ── stars ──
    sy = ny + 250
    n = d["stars"]
    r = 26
    gap = 26
    total_w = 5 * 2 * r + 4 * gap
    sx = cx0 + (cw - total_w) / 2 + r
    for i in range(5):
        draw.polygon(_star_points(sx, sy, r), fill=GOLD if i < n else STAR_OFF)
        sx += 2 * r + gap

    # ── divider ──
    dy = sy + 76
    draw.line([cx0 + 90, dy, cx1 - 90, dy], fill=(46, 82, 58), width=2)

    # ── 4 category stats ──
    stats = _category_stats(full)
    col_w = (cw - 160) / 4
    f_val = _font("Barlow-Black.ttf", 76)
    f_stat = _font("Barlow-Bold.ttf", 28)
    for i, (label, val) in enumerate(stats):
        colx = cx0 + 80 + i * col_w
        vw = _tlen(draw, val, f_val)
        draw.text((colx + (col_w - vw) / 2, dy + 40), val, font=f_val, fill=CREAM_TEXT)
        lw = _tlen(draw, label, f_stat)
        draw.text((colx + (col_w - lw) / 2, dy + 130), label, font=f_stat, fill=LIME_SOFT)
        if i > 0:
            draw.line([colx - 2, dy + 52, colx - 2, dy + 150], fill=(46, 82, 58), width=2)

    # ── card footer ──
    f_foot = _font("Barlow-Bold.ttf", 26)
    foot = "SCOUTMEPLAY  ·  PRO SCOUT REPORT"
    fw = _tlen(draw, foot, f_foot)
    draw.text((cx0 + (cw - fw) / 2, cy1 - 78), foot, font=f_foot, fill=MUTED_ON_DARK)

    # ── CTA below card ──
    f_cta1 = _font("Barlow-Bold.ttf", 34)
    cta1 = "GET YOUR OWN PLAYER REPORT"
    draw.text(((W - _tlen(draw, cta1, f_cta1)) / 2, cy1 + 92), cta1, font=f_cta1, fill=(90, 105, 90))
    f_cta2 = _font("Barlow-Black.ttf", 56)
    cta2 = "scoutmeplay.com"
    draw.text(((W - _tlen(draw, cta2, f_cta2)) / 2, cy1 + 142), cta2, font=f_cta2, fill=FOREST)

    base.save(output_path, "PNG", optimize=True)
    return output_path
