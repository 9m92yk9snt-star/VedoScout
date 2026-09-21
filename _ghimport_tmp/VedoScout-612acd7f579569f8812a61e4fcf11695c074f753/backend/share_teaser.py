"""share_teaser.py — viral share cards for the free preview.
Generates two personal PNGs (feed 1080x1350 + story 1080x1920) with the
tapped player's photo, name and his ONE revealed score story."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

logger = logging.getLogger("elite-scout")

INK = (11, 31, 20)          # #0B1F14
FOREST = (18, 64, 42)       # #12402A
LIME = (204, 255, 0)        # #CCFF00
CREAM = (245, 241, 232)
PALE = (201, 216, 192)

_FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
_FONT_REG = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"


def load_media_bytes(url: str, upload_dir: Path) -> bytes | None:
    """Resolve a report media URL (/api/uploads/…, /api/media/…, https://…) to bytes."""
    if not url:
        return None
    try:
        if url.startswith("/api/uploads/"):
            p = upload_dir / url[len("/api/uploads/"):]
            return p.read_bytes() if p.exists() else None
        if url.startswith("/api/media/"):
            import r2_storage
            key = url[len("/api/media/"):]
            stream = r2_storage.get_stream(key)
            body = stream.get("Body") if isinstance(stream, dict) else getattr(stream, "read", None) and stream
            if isinstance(stream, dict) and stream.get("Body"):
                return stream["Body"].read()
            return None
        if url.startswith("http"):
            import httpx
            r = httpx.get(url, timeout=20, follow_redirects=True)
            return r.content if r.status_code == 200 else None
    except Exception as e:
        logger.warning("share card: could not load media %s: %s", url, e)
    return None


def _fonts():
    from PIL import ImageFont
    def f(path, size):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()
    return f


def _circle_photo(photo_bytes: bytes, size: int):
    from PIL import Image, ImageDraw, ImageOps
    img = Image.open(BytesIO(photo_bytes)).convert("RGB")
    img = ImageOps.fit(img, (size, size), centering=(0.5, 0.35))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([(0, 0), (size, size)], fill=255)
    return img, mask


def _draw_card(W, H, photo_bytes, first, sub, story_label, story_score, story_line):
    from PIL import Image, ImageDraw
    f = _fonts()
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)

    # subtle top glow
    d.rectangle([(0, 0), (W, 8)], fill=LIME)

    cx = W // 2
    y = int(H * 0.055)
    brand = "SCOUTMEPLAY"
    fb = f(_FONT_BOLD, 44)
    bw = d.textbbox((0, 0), brand, font=fb)[2]
    d.text((cx - bw // 2, y), brand, fill=CREAM, font=fb)
    tag = "EVERY PLAYER HAS A STORY"
    ft = f(_FONT_BOLD, 22)
    tw = d.textbbox((0, 0), tag, font=ft)[2]
    d.text((cx - tw // 2, y + 58), tag, fill=LIME, font=ft)

    # circular photo with lime ring
    psize = int(W * 0.42)
    py = y + 130
    if photo_bytes:
        try:
            photo, mask = _circle_photo(photo_bytes, psize)
            ring = 10
            d.ellipse([(cx - psize // 2 - ring, py - ring),
                       (cx + psize // 2 + ring, py + psize + ring)], fill=LIME)
            img.paste(photo, (cx - psize // 2, py), mask)
        except Exception as e:
            logger.warning("share card: photo failed: %s", e)
            photo_bytes = None
    if not photo_bytes:
        d.ellipse([(cx - psize // 2, py), (cx + psize // 2, py + psize)], fill=FOREST)
        fq = f(_FONT_BOLD, 160)
        qw = d.textbbox((0, 0), "?", font=fq)[2]
        d.text((cx - qw // 2, py + psize // 2 - 100), "?", fill=LIME, font=fq)

    # name + sub
    ny = py + psize + 56
    fn = f(_FONT_BOLD, 76)
    name = first.upper()[:16]
    nw = d.textbbox((0, 0), name, font=fn)[2]
    d.text((cx - nw // 2, ny), name, fill=(255, 255, 255), font=fn)
    fs = f(_FONT_REG, 30)
    sw = d.textbbox((0, 0), sub, font=fs)[2]
    d.text((cx - sw // 2, ny + 92), sub, fill=PALE, font=fs)

    # story chip
    chip_y = ny + 168
    chip_text = f"{story_label.upper()}  ·  {story_score}"
    fc = f(_FONT_BOLD, 42)
    cw2 = d.textbbox((0, 0), chip_text, font=fc)[2]
    pad = 44
    d.rounded_rectangle([(cx - cw2 // 2 - pad, chip_y), (cx + cw2 // 2 + pad, chip_y + 94)],
                        radius=47, fill=LIME)
    d.text((cx - cw2 // 2, chip_y + 24), chip_text, fill=INK, font=fc)
    ftag = f(_FONT_BOLD, 22)
    tg = "DISCOVERED ON VIDEO"
    tgw = d.textbbox((0, 0), tg, font=ftag)[2]
    d.text((cx - tgw // 2, chip_y + 112), tg, fill=PALE, font=ftag)

    # story line (wrapped, max 2 lines)
    if story_line:
        fl = f(_FONT_REG, 32)
        words, lines, cur = story_line.split(), [], ""
        for w2 in words:
            t = (cur + " " + w2).strip()
            if d.textbbox((0, 0), t, font=fl)[2] > W - 160:
                lines.append(cur)
                cur = w2
            else:
                cur = t
        lines.append(cur)
        ly = chip_y + 170
        for ln in lines[:2]:
            lw = d.textbbox((0, 0), ln, font=fl)[2]
            d.text((cx - lw // 2, ly), ln, fill=(255, 255, 255), font=fl)
            ly += 44

    # footer
    ff = f(_FONT_BOLD, 30)
    foot = "scoutmeplay.com"
    fw = d.textbbox((0, 0), foot, font=ff)[2]
    d.text((cx - fw // 2, H - 90), foot, fill=LIME, font=ff)
    return img


def ensure_teaser_cards(report_doc: dict, photo_url: str | None, upload_dir: Path) -> dict:
    """Lazily render both card formats; returns public URLs."""
    rid = report_doc.get("id")
    out_dir = upload_dir / "teaser_cards"
    out_dir.mkdir(parents=True, exist_ok=True)
    feed_p = out_dir / f"{rid}_feed.png"
    story_p = out_dir / f"{rid}_story.png"

    if not (feed_p.exists() and story_p.exists()):
        from score_meaning import build_score_meaning_teaser
        pd = report_doc.get("player_details") or {}
        first = str(pd.get("player_name") or "Player").split(" ")[0]
        bits = []
        if pd.get("age"):
            bits.append(f"AGE {pd['age']}")
        if pd.get("position"):
            bits.append(str(pd["position"]).upper())
        sub = "  ·  ".join(bits) or "FOOTBALL PLAYER"
        t = build_score_meaning_teaser(report_doc)
        unlocked = t.get("unlocked") or {}
        label = unlocked.get("label") or "First discovery"
        score = f"{unlocked.get('score'):.1f}" if isinstance(unlocked.get("score"), (int, float)) else "—"
        line = (unlocked.get("lines") or ["One video. A whole story discovered."])[0].replace("\u2014", "-")
        photo = load_media_bytes(photo_url, upload_dir) if photo_url else None
        _draw_card(1080, 1350, photo, first, sub, label, score, line).save(feed_p, "PNG", optimize=True)
        _draw_card(1080, 1920, photo, first, sub, label, score, line).save(story_p, "PNG", optimize=True)

    return {
        "card_feed_url": f"/api/uploads/teaser_cards/{feed_p.name}",
        "card_story_url": f"/api/uploads/teaser_cards/{story_p.name}",
    }
