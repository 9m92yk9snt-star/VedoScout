"""
telestration.py — TV-style spotlight graphics on VERIFIED evidence frames.

Pipeline (strict, double-verified):
1. Gemini locates the tapped player's bounding box in the frame (refs attached).
2. The proposed box is cropped and cross-checked by GPT-4o (verify_frame_identity)
   — a DIFFERENT model family must confirm it is the tapped player.
3. Only on a CONFIRMED verdict is the graphic rendered (spotlight dim + volt
   ring under the feet + name chip). Failure mode is always "no graphic",
   never "wrong graphic".
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType

logger = logging.getLogger(__name__)

DETECT_PROVIDER = "gemini"
DETECT_MODEL = "gemini-2.5-pro"
VOLT = (204, 255, 0)
INK = (10, 25, 15)


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()


async def detect_player_bbox(
    api_key: str, session_id: str, ref_crop_paths: list[str], frame_path: str,
) -> dict | None:
    """Gemini locates the tapped player in the frame. Returns a normalized
    bbox dict {x0,y0,x1,y1} in 0..1 or None (not found / low confidence / error)."""
    try:
        files = [
            FileContentWithMimeType(file_path=p, mime_type="image/jpeg")
            for p in ref_crop_paths[:3]
            if p and Path(p).exists()
        ]
        if not files or not Path(frame_path).exists():
            return None
        n_refs = len(files)
        files.append(FileContentWithMimeType(file_path=str(frame_path), mime_type="image/jpeg"))
        chat = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message="You are a precise vision detection system. Respond with STRICT JSON only — no prose.",
        ).with_model(DETECT_PROVIDER, DETECT_MODEL)
        chat.extra_params = {"timeout": 60.0, "temperature": 0.0}
        prompt = (
            f"The first {n_refs} image(s) are reference crops of ONE specific football player "
            "(the player at the CENTRE of each crop — they may be partially hidden). "
            "The LAST image is a frame from the match video.\n"
            "Locate that SAME individual player in the frame. Match kit, build, hair, socks and boots "
            "against the references — do NOT pick a teammate in an identical kit unless the individual "
            "features match. If you cannot find them with confidence, answer found=false.\n"
            'Respond ONLY with JSON: {"found": true|false, "box_2d": [ymin, xmin, ymax, xmax] '
            '(integers 0-1000, a TIGHT box around the full body of the player in the LAST image), '
            '"confidence": "high"|"medium"|"low"}'
        )
        resp = await asyncio.wait_for(
            chat.send_message(UserMessage(text=prompt, file_contents=files)), timeout=75,
        )
        text = resp if isinstance(resp, str) else getattr(resp, "text", None) or str(resp)
        s, e = text.find("{"), text.rfind("}")
        if s < 0 or e <= s:
            return None
        data = json.loads(text[s:e + 1])
        conf = str(data.get("confidence", "")).lower()
        logger.info(f"[tele] {session_id}: found={data.get('found')} conf={conf} box={data.get('box_2d')}")
        if not data.get("found") or conf == "low":
            return None
        box = data.get("box_2d")
        if not (isinstance(box, list) and len(box) == 4):
            return None
        y0, x0, y1, x1 = [max(0.0, min(1000.0, float(v))) / 1000.0 for v in box]
        if y1 <= y0 or x1 <= x0:
            return None
        w, h = x1 - x0, y1 - y0
        # Sanity: a single player is a small-ish upright box, never most of the frame.
        if w > 0.6 or h > 0.9 or w * h < 0.0004 or w * h > 0.35:
            return None
        return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
    except Exception as e:
        logger.warning(f"[tele] detect failed ({session_id}): {e}")
        return None


def crop_box_region(frame_path: str, box: dict, out_path: str, pad: float = 0.18) -> bool:
    """Crop the proposed bbox (with padding) for the cross-model verification step."""
    try:
        img = Image.open(frame_path).convert("RGB")
        W, H = img.size
        bw, bh = (box["x1"] - box["x0"]) * W, (box["y1"] - box["y0"]) * H
        px, py = bw * pad, bh * pad
        l = max(0, int(box["x0"] * W - px))
        t = max(0, int(box["y0"] * H - py))
        r = min(W, int(box["x1"] * W + px))
        b = min(H, int(box["y1"] * H + py))
        if r - l < 8 or b - t < 8:
            return False
        crop = img.crop((l, t, r, b))
        if crop.width < 220:
            s = 220 / crop.width
            crop = crop.resize((220, int(crop.height * s)), Image.LANCZOS)
        crop.save(out_path, "JPEG", quality=92)
        return True
    except Exception as e:
        logger.warning(f"[tele] crop failed: {e}")
        return False


def render_telestration(frame_path: str, box: dict, label: str = "YOUR PLAYER",
                        ring: bool = True, chip_top: float | None = None) -> bool:
    """Draw spotlight dim + volt ring under the feet + name chip. Overwrites the frame.
    With ring=False (no refined player blob) only the spotlight + chip are drawn —
    an honest fallback that can never point at the wrong spot."""
    try:
        img = Image.open(frame_path).convert("RGB")
        W, H = img.size
        x0, y0, x1, y1 = box["x0"] * W, box["y0"] * H, box["x1"] * W, box["y1"] * H
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        bw, bh = x1 - x0, y1 - y0
        feet_y = min(H - 6, y1 - bh * 0.02)

        # 1 — spotlight: dim everything except a soft ellipse around the player
        dark = ImageEnhance.Brightness(img).enhance(0.52)
        mask = Image.new("L", (W, H), 0)
        md = ImageDraw.Draw(mask)
        rx = max(bw * 1.7, W * 0.13)
        ry = max(bh * 1.1, H * 0.17)
        md.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(int(max(W, H) * 0.055)))
        out = Image.composite(img, dark, mask).convert("RGBA")

        # 2 — volt ring under the feet (2x supersampled for crisp anti-aliasing)
        out = out.convert("RGBA")
        if ring:
            S = 2
            ov = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)
            rw = min(max(bw * 0.6, W * 0.045), W * 0.22)
            rh = rw * 0.32
            feet_y = min(feet_y, H - rh - 4)  # keep the full ellipse inside the frame
            lw = max(3, int(W / 230))
            od.ellipse([(cx - rw) * S, (feet_y - rh) * S, (cx + rw) * S, (feet_y + rh) * S],
                       outline=VOLT + (255,), width=lw * S)
            od.ellipse([(cx - rw * 0.68) * S, (feet_y - rh * 0.68) * S,
                        (cx + rw * 0.68) * S, (feet_y + rh * 0.68) * S],
                       outline=VOLT + (110,), width=max(1, lw // 2) * S)
            glow = ov.filter(ImageFilter.GaussianBlur(7 * S))
            ov = Image.alpha_composite(glow, ov).resize((W, H), Image.LANCZOS)
            out = Image.alpha_composite(out, ov)

        # 3 — name chip above the player (clamped inside the frame)
        d = ImageDraw.Draw(out)
        fs = max(15, int(W / 46))
        font = _font(fs)
        label = str(label or "YOUR PLAYER")[:18]
        tw = d.textlength(label, font=font)
        pad_x = int(fs * 0.62)
        chip_h = int(fs * 1.9)
        dot_r = fs * 0.22
        chip_w = tw + 2 * pad_x + dot_r * 2 + fs * 0.5
        chx = min(max(6, cx - chip_w / 2), W - chip_w - 6)
        top_ref = min(y0, chip_top * H) if chip_top is not None else y0
        chy = max(6, top_ref - chip_h - 10)
        d.rounded_rectangle([chx, chy, chx + chip_w, chy + chip_h],
                            radius=int(chip_h / 2.4), fill=INK + (235,))
        dcx = chx + pad_x + dot_r
        d.ellipse([dcx - dot_r, chy + chip_h / 2 - dot_r, dcx + dot_r, chy + chip_h / 2 + dot_r], fill=VOLT)
        d.text((dcx + dot_r + fs * 0.32, chy + (chip_h - fs) / 2 - fs * 0.08),
               label, font=font, fill=(255, 255, 255))

        out.convert("RGB").save(frame_path, "JPEG", quality=90)
        return True
    except Exception as e:
        logger.warning(f"[tele] render failed for {frame_path}: {e}")
        return False
