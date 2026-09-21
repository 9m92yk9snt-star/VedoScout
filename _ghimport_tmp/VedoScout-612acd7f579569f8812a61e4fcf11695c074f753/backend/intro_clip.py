"""
intro_clip.py — Shareable cinematic intro clip (1080×1920 MP4, story format).

Server-side render of the report's cinematic intro as a short silent video:
dark film-bar opening → player's best frame + name + moment line → overall
score counting up → ScoutMePlay end card. Encoded with imageio_ffmpeg
(H.264 / yuv420p / faststart) so it plays everywhere social media expects.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from pdf_v2 import derive_v2, _pick_hero_photo

W, H = 1080, 1920
FPS = 24
BAR_H = 130
PAN_PX = 180

VOLT = (204, 255, 0)
WHITE = (255, 255, 255)
FOREST_DARK = (10, 26, 15)
INK = (18, 33, 26)

_FONT_DIR = Path(__file__).resolve().parent / "fonts"


def _font(name, size):
    try:
        return ImageFont.truetype(str(_FONT_DIR / name), size)
    except Exception:
        return ImageFont.load_default()


def _sp(s):
    return " ".join(list(str(s)))


def _ramp(t, t0, dur):
    if dur <= 0:
        return 1.0 if t >= t0 else 0.0
    return max(0.0, min(1.0, (t - t0) / dur))


def _ease_out(p):
    return 1 - (1 - p) ** 3


def _wrap(draw, text, font, max_w, max_lines):
    words = str(text or "").split()
    lines, cur = [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w_
            if len(lines) == max_lines:
                cur = ""
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and words and " ".join(lines).count(" ") + max_lines - 1 < len(words) - 1:
        lines[-1] = lines[-1].rstrip(" ,.") + "…"
    return lines or ["—"]


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


def _vgrad(w, h, c1, c2):
    strip = Image.new("RGB", (1, h))
    for yy in range(h):
        t = yy / max(1, h - 1)
        strip.putpixel((0, yy), tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    return strip.resize((w, h))


def _darken(img, factor):
    return img.point(lambda v: int(v * factor))


def _centered_text(draw, y, text, font, fill):
    tw = draw.textlength(text, font=font)
    draw.text((W / 2 - tw / 2, y), text, font=font, fill=fill)


def _paste_alpha(base, layer, opacity):
    if opacity <= 0:
        return
    if opacity >= 1:
        base.paste(layer, (0, 0), layer)
    else:
        a = layer.split()[3].point(lambda v: int(v * opacity))
        base.paste(layer, (0, 0), a)


def _pick_moment(doc):
    d = derive_v2(doc)
    moments = [m for m in (d.get("snapshotMoments") or []) if isinstance(m, dict)]
    for m in moments:
        if m.get("thumb") and m.get("timestamp"):
            return m
    for m in moments:
        if m.get("thumb"):
            return m
    return moments[0] if moments else {}


def _build_layers(doc, moment, demo):
    """Pre-render all static RGBA text layers + the end card."""
    scratch = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    def layer():
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        return im, ImageDraw.Draw(im)

    # "SCOUTMEPLAY PRESENTS"
    l_presents, dp = layer()
    _centered_text(dp, 560, _sp("SCOUTMEPLAY  PRESENTS"), _font("Barlow-Bold.ttf", 30), VOLT + (255,))

    # player name (up to 2 lines)
    name = str((doc.get("player_details") or {}).get("player_name") or "Player").upper()
    f_name = _font("Barlow-Black.ttf", 118)
    lines = _wrap(scratch, name, f_name, 960, 2)
    if any(scratch.textlength(ln, font=f_name) > 960 for ln in lines):
        f_name = _font("Barlow-Black.ttf", 88)
        lines = _wrap(scratch, name, f_name, 960, 2)
    l_name, dn = layer()
    ny = 690
    for ln in lines:
        _centered_text(dn, ny, ln, f_name, WHITE + (255,))
        ny += int(f_name.size * 1.04)

    # moment line: "MINUTE ts" + title
    l_moment, dm = layer()
    my = ny + 46
    ts = moment.get("timestamp")
    if ts:
        _centered_text(dm, my, _sp(f"MINUTE  {ts}"), _font("Barlow-Bold.ttf", 38), VOLT + (255,))
        my += 66
    title = moment.get("title")
    if title and title != "—":
        f_t = _font("DMSans-Regular.ttf", 46)
        for ln in _wrap(scratch, f"{title}.", f_t, 900, 2):
            _centered_text(dm, my, ln, f_t, (240, 240, 235, 255))
            my += 60

    # score label + story line
    l_scorelabel, dl = layer()
    _centered_text(dl, 1180, _sp("OVERALL  SCORE"), _font("Barlow-Bold.ttf", 34), (255, 255, 255, 185))
    l_story, ds = layer()
    _centered_text(ds, 1430, _sp("YOUR  STORY  STARTS  HERE"), _font("Barlow-Bold.ttf", 28), (255, 255, 255, 130))

    # demo chip
    l_demo = None
    if demo:
        l_demo, dd = layer()
        f_chip = _font("Barlow-Bold.ttf", 26)
        chip = "DEMO SAMPLE — PREMIUM REPORTS OPEN LIKE THIS"
        cw = scratch.textlength(chip, font=f_chip)
        x0, y0 = W / 2 - cw / 2 - 22, 172
        dd.rounded_rectangle((x0, y0, x0 + cw + 44, y0 + 52), radius=26, fill=(0, 0, 0, 150), outline=VOLT + (90,), width=2)
        dd.text((x0 + 22, y0 + 11), chip, font=f_chip, fill=VOLT + (255,))

    # end card
    endcard = _vgrad(W, H, (14, 36, 21), FOREST_DARK)
    de = ImageDraw.Draw(endcard)
    f_word = _font("Barlow-Black.ttf", 92)
    scout_w = de.textlength("SCOUT", font=f_word)
    me_w = de.textlength("ME", font=f_word)
    play_w = de.textlength("PLAY", font=f_word)
    total = scout_w + me_w + 40 + play_w
    x0 = W / 2 - total / 2
    wy = 830
    de.text((x0, wy), "SCOUT", font=f_word, fill=WHITE)
    de.rounded_rectangle((x0 + scout_w + 10, wy + 6, x0 + scout_w + me_w + 30, wy + 100), radius=12, fill=VOLT)
    de.text((x0 + scout_w + 20, wy), "ME", font=f_word, fill=INK)
    de.text((x0 + scout_w + me_w + 40, wy), "PLAY", font=f_word, fill=WHITE)
    _centered_text(de, wy + 130, _sp("YOUR JOURNEY. OUR ANALYSIS. YOUR FUTURE."), _font("Barlow-Bold.ttf", 24), (169, 188, 156))
    _centered_text(de, wy + 210, "scoutmeplay.com", font=_font("Barlow-Bold.ttf", 44), fill=VOLT)
    if demo:
        _centered_text(de, wy + 290, "Sample player — get your own report", _font("DMSans-Regular.ttf", 32), (200, 210, 195))
    de.rectangle((0, 0, W, BAR_H), fill=(0, 0, 0))
    de.rectangle((0, H - BAR_H, W, H), fill=(0, 0, 0))

    return {
        "presents": l_presents, "name": l_name, "moment": l_moment,
        "scorelabel": l_scorelabel, "story": l_story, "demo": l_demo,
        "endcard": endcard,
    }


def build_intro_clip(report_doc: dict, output_path: str, image_resolver=None) -> None:
    resolve = image_resolver or (lambda _u: None)
    demo = bool(report_doc.get("demo"))
    moment = _pick_moment(report_doc)
    overall = ((report_doc.get("full_report") or {}).get("scores") or {}).get("overall_development")
    target = float(overall) if isinstance(overall, (int, float)) else None

    # background image (cover 1080×2100 for a slow vertical pan)
    img_path = None
    if moment.get("thumb"):
        img_path = resolve(moment["thumb"])
    if not img_path:
        img_path = _pick_hero_photo(report_doc, resolve)
    if img_path:
        try:
            src = Image.open(img_path).convert("RGB")
        except Exception:
            src = None
    else:
        src = None
    if src is not None:
        base_img = _cover(src, W, H + PAN_PX)
    else:
        base_img = _vgrad(W, H + PAN_PX, (27, 68, 48), (11, 31, 20))
    bg_sharp = _darken(base_img, 0.55)
    bg_blur = _darken(base_img, 0.32).filter(ImageFilter.GaussianBlur(6))

    layers = _build_layers(report_doc, moment, demo)
    black = Image.new("RGB", (W, H), (5, 5, 5))
    f_score = _font("Barlow-Black.ttf", 330)

    total_dur = 8.7
    n_frames = int(total_dur * FPS)

    tmp_path = str(output_path) + ".tmp.mp4"
    gen = imageio_ffmpeg.write_frames(
        tmp_path, (W, H), fps=FPS, codec="libx264",
        pix_fmt_in="rgb24", pix_fmt_out="yuv420p", macro_block_size=1,
        output_params=["-movflags", "+faststart", "-crf", "23", "-preset", "veryfast"],
    )
    gen.send(None)
    try:
        for i in range(n_frames):
            t = i / FPS

            if t < 1.3:
                frame = black.copy()
            else:
                pan = int(_ramp(t, 1.3, 6.0) * PAN_PX)
                sharp = bg_sharp.crop((0, pan, W, pan + H))
                img_op = _ramp(t, 1.3, 0.6)
                if img_op < 1:
                    frame = Image.blend(black, sharp, img_op)
                else:
                    frame = sharp
                blur_mix = _ramp(t, 4.3, 0.5)
                if blur_mix > 0:
                    frame = Image.blend(frame, bg_blur.crop((0, pan, W, pan + H)), blur_mix)

            # presents (pulsing during the dark opening)
            p_op = 0.55 + 0.45 * abs(math.sin(t * math.pi / 0.9)) if t < 1.3 else 0.85
            _paste_alpha(frame, layers["presents"], p_op)

            # scene 2 — name + moment (fade in, then out as the score arrives)
            out_op = 1 - _ramp(t, 4.3, 0.4)
            _paste_alpha(frame, layers["name"], _ramp(t, 1.5, 0.5) * out_op)
            _paste_alpha(frame, layers["moment"], _ramp(t, 1.9, 0.5) * out_op)
            if layers["demo"] is not None:
                _paste_alpha(frame, layers["demo"], _ramp(t, 1.5, 0.5))

            # scene 3 — score count-up
            score_op = _ramp(t, 4.5, 0.4)
            if score_op > 0 and target is not None:
                value = target * _ease_out(_ramp(t, 4.5, 1.7))
                s_layer = Image.new("RGBA", (W, 460), (0, 0, 0, 0))
                sd = ImageDraw.Draw(s_layer)
                txt = f"{value:.1f}"
                tw = sd.textlength(txt, font=f_score)
                sd.text((W / 2 - tw / 2, 20), txt, font=f_score, fill=VOLT + (255,))
                if score_op >= 1:
                    frame.paste(s_layer, (0, 740), s_layer)
                else:
                    a = s_layer.split()[3].point(lambda v: int(v * score_op))
                    frame.paste(s_layer, (0, 740), a)
                _paste_alpha(frame, layers["scorelabel"], score_op)
            _paste_alpha(frame, layers["story"], _ramp(t, 6.2, 0.5))

            # film bars
            fd = ImageDraw.Draw(frame)
            fd.rectangle((0, 0, W, BAR_H), fill=(0, 0, 0))
            fd.rectangle((0, H - BAR_H, W, H), fill=(0, 0, 0))

            # scene 4 — end card crossfade
            end_mix = _ramp(t, 7.3, 0.6)
            if end_mix > 0:
                frame = Image.blend(frame, layers["endcard"], end_mix)

            gen.send(frame.tobytes())
    finally:
        gen.close()
    os.replace(tmp_path, output_path)
