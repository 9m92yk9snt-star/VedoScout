"""
Premium image set v2 — adds more depth + WOW-factor imagery for the landing.

Run: cd /app/backend && python scripts/generate_landing_images_v2.py

Saves to /app/backend/static/landing/ (served via /api/static/landing/<file>).
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

OUT_DIR = Path("/app/backend/static/landing")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PALETTE = (
    "Color palette is STRICTLY cream off-white (#F4EFE6), deep forest green "
    "(#1F4F2F), and tiny volt/lime accents (#CCFF00). NO purple/pink/blue. "
    "Photo-realistic, premium sports documentary aesthetic, very high detail."
)

JOBS = [
    {
        "filename": "hero-action.png",
        "prompt": (
            "DRAMATIC cinematic photograph of a young U14 male football player "
            "in mid-stride sprinting with the ball at his feet on a green pitch, "
            "low golden-hour rim light, slight motion blur on the legs, dust "
            "particles kicking up. Shallow depth of field, blurred grass and "
            "distant goal in background. Subject occupies the right two-thirds "
            "of the frame, intense focused expression. Wears anonymous forest-"
            "green training kit (no logos, no number). Editorial sports magazine "
            "cover quality. Vertical 4:5 ratio. " + PALETTE
        ),
    },
    {
        "filename": "hero-report-card.png",
        "prompt": (
            "Vertical 3D render of a premium scout-report card mockup floating "
            "against a soft cream gradient background. The card has a dark forest "
            "green header strip reading 'SCOUT REPORT', below that a giant "
            "lime-green '7.8/10' score number, below that 4 mini horizontal bar "
            "graphs labelled TECHNICAL, TACTICAL, PHYSICAL, MENTALITY (each at "
            "different fill levels in forest green with lime tips). Card has "
            "subtle drop shadow and rounded corners, slight 6-degree rotation. "
            "Clean editorial design-system aesthetic, like a Figma export. "
            "Vertical 3:4 ratio. " + PALETTE
        ),
    },
    {
        "filename": "step-upload.png",
        "prompt": (
            "Square photograph from above: a hand holding an iPhone displaying "
            "a paused football clip on screen, with a green progress bar showing "
            "'Uploading 42%'. Phone rests on a cream-coloured surface next to a "
            "scout's pencil. Soft natural overhead light, premium product-shot "
            "feel. Minimalist composition. Square 1:1 ratio. " + PALETTE
        ),
    },
    {
        "filename": "step-mark.png",
        "prompt": (
            "Square close-up photograph of a fingertip tapping an iPhone screen "
            "that shows a paused football video with a lime-green bounding box "
            "drawn around one player. Soft cream background bokeh. Editorial "
            "product photography. Square 1:1 ratio. " + PALETTE
        ),
    },
    {
        "filename": "step-report.png",
        "prompt": (
            "Square photograph from above of an open premium scout report "
            "printed on heavy cream paper, with neat hand-drawn pen annotations "
            "and a radar chart in forest green ink. A fountain pen rests on the "
            "page. Soft warm natural light. Editorial flat-lay. Square 1:1 "
            "ratio. " + PALETTE
        ),
    },
    {
        "filename": "feature-strip.png",
        "prompt": (
            "Wide cinematic photograph: panoramic view of a U13 football "
            "training session at dusk, three players in forest-green kit "
            "performing cone drills in the foreground, mist hanging over a "
            "stadium in the deep background, golden-hour lighting. Hyper-wide "
            "21:9 aspect ratio. Premium sports documentary look. " + PALETTE
        ),
    },
]


async def generate_one(api_key: str, job: dict) -> bool:
    out_path = OUT_DIR / job["filename"]
    print(f"→ generating {job['filename']} …")
    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"scoutmeplay-landing-v2-{job['filename']}",
            system_message="You are an expert premium sports editorial photographer.",
        )
        chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(
            modalities=["image", "text"]
        )
        msg = UserMessage(text=job["prompt"])
        _text, images = await chat.send_message_multimodal_response(msg)
        if not images:
            print(f"  ✗ no images for {job['filename']}")
            return False
        out_path.write_bytes(base64.b64decode(images[0]["data"]))
        print(f"  ✓ saved {out_path.name} ({out_path.stat().st_size // 1024} KB)")
        return True
    except Exception as e:
        print(f"  ✗ ERROR {job['filename']}: {e}")
        return False


async def main():
    api_key = os.getenv("EMERGENT_LLM_KEY")
    if not api_key:
        print("EMERGENT_LLM_KEY missing")
        sys.exit(1)
    ok = 0
    for job in JOBS:
        if await generate_one(api_key, job):
            ok += 1
        await asyncio.sleep(0.4)
    print(f"\nDone: {ok}/{len(JOBS)} v2 images")


if __name__ == "__main__":
    asyncio.run(main())
