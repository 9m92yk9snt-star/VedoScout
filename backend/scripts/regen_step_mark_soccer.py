"""
Regenerate the "Step 02 · MARK" landing image with a proper SOCCER
(association football) player in the phone screen — replacing the accidental
American football / NFL Jets image that Nano Banana previously produced.

Run: cd /app/backend && python scripts/regen_step_mark_soccer.py
"""
import asyncio
import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore

OUT_PATH = Path("/app/backend/static/landing/step-mark.png")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

PROMPT = (
    "Photorealistic close-up cinematic photograph of a hand holding a modern "
    "smartphone in vertical portrait orientation. On the phone screen is a "
    "PAUSED SOCCER MATCH VIDEO (association football / European football / "
    "the round-ball sport) — a young soccer player in a green and white "
    "soccer kit (jersey with sleeves, soccer shorts, soccer socks pulled up "
    "to the knee, football boots with studs), standing on a natural GRASS "
    "SOCCER PITCH with white painted pitch lines (not American football yard "
    "lines). NO helmets. NO shoulder pads. NO American football gear. NO NFL "
    "uniforms. This is SOCCER / FOOTBALL as played in Europe, South America, "
    "and the FIFA World Cup — the sport with a round ball where players "
    "cannot use their hands.\n\n"
    "A user's INDEX FINGER is TAPPING the phone screen — the finger is "
    "clearly touching the glass to draw a NEON VOLT-YELLOW (#CCFF00) "
    "bounding-box rectangle around the soccer player's body, from head to "
    "boots. The bounding box is a bright, crisp, glowing yellow-green outline "
    "(2px thick) with 4 corner handles, clearly visible over the player.\n\n"
    "Blurred cream-white studio background on the left third of the image "
    "(bokeh). Warm natural side-lighting. Very high resolution editorial "
    "commercial photography, sharp focus on the finger + phone screen, film "
    "grain, professional lifestyle-tech aesthetic like an Apple product shot. "
    "The composition should be a landscape wide crop showing hand + phone on "
    "the right half, empty blurred cream space on the left half.\n\n"
    "STRICT REQUIREMENTS: soccer only, no NFL, no American football, no "
    "helmets, no pads, no oval ball. If in doubt, think Premier League, "
    "La Liga, Bundesliga — grass pitch, boots with studs, round ball."
)


async def main():
    api_key = os.environ["EMERGENT_LLM_KEY"]
    # Attempt up to 3 times in case Nano Banana produces American football again
    for attempt in range(1, 4):
        print(f"→ Attempt {attempt}/3 for step-mark.png (soccer only)…")
        chat = LlmChat(
            api_key=api_key,
            session_id=f"scoutmeplay-step-mark-soccer-{attempt}",
            system_message=(
                "You are a commercial editorial photographer specializing in "
                "European football / soccer. Never confuse soccer with "
                "American football / NFL. All players wear soccer kits with no "
                "helmets and no shoulder pads."
            ),
        )
        chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(
            modalities=["image", "text"]
        )
        try:
            _text, images = await chat.send_message_multimodal_response(UserMessage(text=PROMPT))
        except Exception as e:
            print(f"  ✗ Nano Banana error: {e}")
            continue
        if not images:
            print("  ✗ No images returned")
            continue
        img_bytes = base64.b64decode(images[0]["data"])
        OUT_PATH.write_bytes(img_bytes)
        print(f"  ✓ Saved {OUT_PATH} ({len(img_bytes) // 1024} KB)")
        return
    print("Could not regenerate step-mark.png after 3 attempts")


if __name__ == "__main__":
    asyncio.run(main())
