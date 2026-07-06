"""
identity_verify.py — Layer A of the player-identity guarantee.

After the full report is generated, every evidence frame extracted at a
Gemini-claimed timestamp is cross-checked by a DIFFERENT model family
(OpenAI gpt-4o-mini vision via the Emergent LLM key): "is the tapped player
from the reference crops clearly visible in this frame?". Frames that fail
are re-windowed or dropped so the report never displays the wrong player.

Purely additive and best-effort — any error returns None (inconclusive) and
the pipeline behaves exactly as before this layer existed.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

logger = logging.getLogger(__name__)

VERIFY_PROVIDER = "openai"
VERIFY_MODEL = "gpt-4o"  # calibrated: 4o-mini misses small players; 4o is reliable
MAX_REF_CROPS = 3


def _b64(path: str | Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


async def verify_frame_identity(
    api_key: str,
    session_id: str,
    ref_crop_paths: list[str],
    frame_path: str,
    jersey_name: str = "unclear",
    shorts_name: str = "unclear",
) -> bool | None:
    """Return True (tapped player visible), False (not visible / another
    same-kit player), or None (inconclusive / any error — do not overrule)."""
    try:
        refs = [
            ImageContent(image_base64=_b64(p))
            for p in ref_crop_paths[:MAX_REF_CROPS]
            if p and Path(p).exists()
        ]
        if not refs or not Path(frame_path).exists():
            return None
        chat = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message=(
                "You verify football player identity across images. "
                "Respond with STRICT JSON only — no prose, no markdown."
            ),
        ).with_model(VERIFY_PROVIDER, VERIFY_MODEL)
        prompt = (
            f"The first {len(refs)} image(s) are reference crops of ONE specific youth football player. "
            "First, identify the player's distinctive features from the reference crops yourself "
            "(kit colours, headwear, sleeves, socks, build). An automated kit-colour read said "
            f"'{jersey_name} jersey, {shorts_name} shorts' but it MAY BE INACCURATE — trust the images.\n"
            "The LAST image is a frame from the match video.\n"
            "Question: is that SAME individual player visible anywhere in the frame, even if small?\n"
            'Respond ONLY with JSON: {"match": true|false, "confidence": "high"|"medium"|"low", '
            '"why": "<one short sentence>"}'
        )
        msg = UserMessage(text=prompt, file_contents=[*refs, ImageContent(image_base64=_b64(frame_path))])
        resp = await asyncio.wait_for(chat.send_message(msg), timeout=60)
        text = resp if isinstance(resp, str) else getattr(resp, "text", None) or str(resp)
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        data = json.loads(text[start:end + 1])
        match = bool(data.get("match"))
        conf = str(data.get("confidence", "")).lower()
        logger.info(f"[identity] {session_id}: match={match} conf={conf} why={str(data.get('why'))[:120]}")
        # Conservative policy: only a HIGH-confidence rejection drops a frame;
        # a LOW-confidence approval never counts as verified.
        if match:
            return True if conf in ("high", "medium") else None
        return False if conf == "high" else None
    except Exception as e:
        logger.warning(f"identity verify inconclusive ({session_id}): {e}")
        return None
