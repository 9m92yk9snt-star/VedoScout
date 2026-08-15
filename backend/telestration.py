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
        vals = [max(0.0, min(1000.0, float(v))) / 1000.0 for v in box]

        def _sane(x0, y0, x1, y1):
            if y1 <= y0 or x1 <= x0:
                return None
            w, h = x1 - x0, y1 - y0
            # Sanity: a single player is a small-ish upright box, never most of the frame.
            if w > 0.6 or h > 0.9 or w * h < 0.0004 or w * h > 0.35:
                return None
            return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}

        # Models do not reliably honour [ymin,xmin,ymax,xmax] — return BOTH
        # interpretations; the caller MUST cross-verify each crop before drawing.
        cands = []
        a = _sane(vals[1], vals[0], vals[3], vals[2])  # [y,x,y,x] as asked
        b = _sane(vals[0], vals[1], vals[2], vals[3])  # [x,y,x,y] fallback
        if a:
            cands.append(a)
        if b and b != a:
            cands.append(b)
        return cands or None
    except Exception as e:
        logger.warning(f"[tele] detect failed ({session_id}): {e}")
        return None


async def find_player_double_gated(api_key: str, session_base: str, ref_crops: list[str],
                                   frame_path: str, jersey: str, shorts: str, jersey_number,
                                   jersey_hex: str, shorts_hex: str) -> dict | None:
    """Full safe localization chain for frames WITHOUT a tap anchor.
    detect (full frame) → GPT-4o gate 1 on padded region → zoomed re-detect inside
    the confirmed region → GPT-4o gate 2 on the tight box → blob-refine for feet.
    Any doubt at any gate → None (no graphics, never a wrong ring)."""
    from identity_verify import verify_frame_identity
    from precision_engine import locate_player_in_box
    fp = Path(frame_path)
    cands = await detect_player_bbox(api_key, f"{session_base}-d", ref_crops, frame_path) or []
    try:
        img = Image.open(frame_path).convert("RGB")
    except Exception:
        return None
    W, H = img.size
    for ci, cand in enumerate(cands):
        pw, ph = (cand["x1"] - cand["x0"]) * 0.8, (cand["y1"] - cand["y0"]) * 0.8
        rx0, ry0 = max(0.0, cand["x0"] - pw), max(0.0, cand["y0"] - ph)
        rx1, ry1 = min(1.0, cand["x1"] + pw), min(1.0, cand["y1"] + ph)
        region_path = fp.parent / f".tele_region_{fp.stem}_{ci}.jpg"
        try:
            rc = img.crop((int(rx0 * W), int(ry0 * H), int(rx1 * W), int(ry1 * H)))
            if rc.width < 12 or rc.height < 12:
                continue
            if rc.width < 480:
                s = 480 / rc.width
                rc = rc.resize((480, int(rc.height * s)), Image.LANCZOS)
            rc.save(region_path, "JPEG", quality=92)
            v1 = await verify_frame_identity(api_key, f"{session_base}-g1{ci}", ref_crops,
                                             str(region_path), jersey, shorts, jersey_number)
            if v1 != "confirmed":
                continue
            local = await detect_player_bbox(api_key, f"{session_base}-z{ci}", ref_crops, str(region_path)) or []
        finally:
            region_path.unlink(missing_ok=True)
        for li, lb in enumerate(local):
            gb = {"x0": rx0 + lb["x0"] * (rx1 - rx0), "y0": ry0 + lb["y0"] * (ry1 - ry0),
                  "x1": rx0 + lb["x1"] * (rx1 - rx0), "y1": ry0 + lb["y1"] * (ry1 - ry0)}
            tight_path = fp.parent / f".tele_tight_{fp.stem}_{ci}{li}.jpg"
            try:
                if not crop_box_region(frame_path, gb, str(tight_path), 0.3):
                    continue
                v2 = await verify_frame_identity(api_key, f"{session_base}-g2{ci}{li}", ref_crops,
                                                 str(tight_path), jersey, shorts, jersey_number)
            finally:
                tight_path.unlink(missing_ok=True)
            if v2 != "confirmed":
                continue
            bxywh = {"x": gb["x0"], "y": gb["y0"], "w": gb["x1"] - gb["x0"], "h": gb["y1"] - gb["y0"]}
            refined = locate_player_in_box(frame_path, bxywh, jersey_hex, shorts_hex)
            if refined:
                cx = (refined["x0"] + refined["x1"]) / 2
                cy = (refined["y0"] + refined["y1"]) / 2
                if gb["x0"] <= cx <= gb["x1"] and gb["y0"] <= cy <= gb["y1"]:
                    return {k: float(refined[k]) for k in ("x0", "y0", "x1", "y1")}
            return gb
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
    """Premium grounded marker: spotlight dim + perspective ground ellipse under
    the feet (soft fill, glow, crisp volt ring) + a small name chip with a
    pointer sitting just above the player's head. Overwrites the frame.
    With ring=False (no refined player blob) only the spotlight + chip are drawn —
    an honest fallback that can never point at the wrong spot."""
    try:
        img = Image.open(frame_path).convert("RGB")
        W, H = img.size
        x0, y0, x1, y1 = box["x0"] * W, box["y0"] * H, box["x1"] * W, box["y1"] * H
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        bw, bh = x1 - x0, y1 - y0
        # Height estimate with sanity bounds — generous tap boxes overstate the
        # player, so the chip/ring must never trust bh blindly.
        est_h = min(max(bh, H * 0.045), W * 0.333, H * 0.42)
        rw = min(max(est_h * 0.30, W * 0.024), W * 0.10)
        rh = rw * 0.34
        # ground contact: box bottoms include shadow — pull the ellipse centre up
        # so the feet sit INSIDE the marker, never on its top rim
        feet_y = min(H - 6, y1 - min(bh * 0.08, rh * 0.8))

        # 1 — spotlight: dim everything except a soft ellipse around the player
        dark = ImageEnhance.Brightness(img).enhance(0.52)
        mask = Image.new("L", (W, H), 0)
        md = ImageDraw.Draw(mask)
        rx = max(bw * 1.7, W * 0.13)
        ry = max(bh * 1.1, H * 0.17)
        md.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(int(max(W, H) * 0.055)))
        out = Image.composite(img, dark, mask).convert("RGBA")

        # 2 — grounded ellipse: sized from PLAYER HEIGHT so the player stands
        # inside the marker at any distance; flat perspective, soft fill + glow.
        if ring:
            lw = max(2, int(rw * 0.085))
            feet_y = min(feet_y, H - rh - 4)
            S = 2
            bbox = [(cx - rw) * S, (feet_y - rh) * S, (cx + rw) * S, (feet_y + rh) * S]
            glow_src = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow_src)
            gd.ellipse(bbox, outline=VOLT + (190,), width=lw * 3 * S)
            ov = glow_src.filter(ImageFilter.GaussianBlur(int(lw * 2.2 * S)))
            od = ImageDraw.Draw(ov)
            od.ellipse(bbox, fill=VOLT + (30,))
            od.ellipse(bbox, outline=(14, 34, 20, 150), width=(lw + 2) * S)
            od.ellipse(bbox, outline=VOLT + (235,), width=lw * S)
            ov = ov.resize((W, H), Image.LANCZOS)
            out = Image.alpha_composite(out, ov)

            # 3 — player in front: restore the player's silhouette over the
            # ring so the marker reads as painted on the pitch BEHIND boots
            # and legs — the line never crosses the front of the feet.
            try:
                import numpy as _np
                import cv2 as _cv2
                arr = _np.array(out.convert("RGB"))
                base = _np.array(Image.composite(img, dark, mask).convert("RGB"))
                hsv = _cv2.cvtColor(base, _cv2.COLOR_RGB2HSV)
                ng = _cv2.inRange(hsv, (30, 40, 40), (90, 255, 255)) == 0
                sel = _np.zeros(ng.shape, bool)
                x_lo, x_hi = int(max(0, cx - rw * 0.6)), int(min(W, cx + rw * 0.6))
                y_lo, y_hi = int(max(0, feet_y - rh * 3)), int(min(H, feet_y + rh))
                sel[y_lo:y_hi, x_lo:x_hi] = True
                m2 = (ng & sel).astype(_np.uint8) * 255
                m2 = _cv2.GaussianBlur(m2, (5, 5), 0).astype(_np.float32)[..., None] / 255.0
                out = Image.fromarray((base * m2 + arr * (1 - m2)).astype(_np.uint8)).convert("RGBA")
            except Exception:
                pass

        out.convert("RGB").save(frame_path, "JPEG", quality=90)
        return True
    except Exception as e:
        logger.warning(f"[tele] render failed for {frame_path}: {e}")
        return False
