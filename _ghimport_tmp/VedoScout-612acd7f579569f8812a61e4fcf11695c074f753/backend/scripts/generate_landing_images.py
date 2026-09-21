"""
Generate 4 premium landing/dashboard images via Nano Banana (Gemini).
Saves PNG files to /app/backend/static/landing/ which FastAPI serves
under /static/landing/<file>.

Run: cd /app/backend && python scripts/generate_landing_images.py
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

# Cream/forest/volt palette only — match existing site exactly.
PALETTE_NOTE = (
    "Color palette is STRICTLY cream off-white background (#F4EFE6), "
    "deep forest green (#1F4F2F), and tiny volt/lime accents (#CCFF00). "
    "NO purple, no pink, no blue. Photo-realistic, premium sports documentary."
)

JOBS = [
    {
        "filename": "hero-pitch.png",
        "prompt": (
            "Cinematic wide aerial photograph of a professional football pitch at dusk, "
            "viewed from behind a goal, immaculate green grass with white chalk lines, "
            "stadium floodlights creating soft golden hour rim-light, mist hanging low. "
            "One silhouetted youth player in the centre line, holding a ball under arm. "
            "Slight film grain, shallow depth of field. Subject occupies right third — "
            "left half is empty cream-toned sky for headline overlay. "
            "Premium scouting documentary aesthetic, very high detail. "
            + PALETTE_NOTE
        ),
    },
    {
        "filename": "how-it-works.png",
        "prompt": (
            "Top-down flat-lay photograph of a tactical scouting workspace on cream paper "
            "background: a smartphone showing a paused football video clip, a paper "
            "scout's notebook with hand-drawn arrows and Xs and Os, a Sharpie pen, a "
            "stopwatch, and a single football boot. Organised, minimalist composition. "
            "Soft natural top-down lighting. Editorial sports-magazine look. "
            + PALETTE_NOTE
        ),
    },
    {
        "filename": "feature-analysis.png",
        "prompt": (
            "Close-up macro photograph of a tablet screen displaying a football player "
            "performance dashboard: a radar chart and bar graphs in forest green and "
            "lime accents on cream background. Tablet rests on a wooden table next to a "
            "leather scout notebook. Shallow depth of field. Ultra-clean, premium "
            "consumer-tech editorial photography. "
            + PALETTE_NOTE
        ),
    },
    {
        "filename": "social-proof-player.png",
        "prompt": (
            "Portrait photograph of a confident U16 youth football player in a clean "
            "forest-green training kit, holding a ball, looking calmly off-camera. "
            "Soft cream-toned studio background. Editorial sports-portrait aesthetic, "
            "natural light, subtle film grain. Anonymous (no logo on kit). "
            + PALETTE_NOTE
        ),
    },
]


async def generate_one(api_key: str, job: dict) -> bool:
    out_path = OUT_DIR / job["filename"]
    print(f"→ generating {job['filename']} …")
    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"scoutmeplay-landing-{job['filename']}",
            system_message="You are an expert premium sports editorial photographer.",
        )
        chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(
            modalities=["image", "text"]
        )
        msg = UserMessage(text=job["prompt"])
        _text, images = await chat.send_message_multimodal_response(msg)
        if not images:
            print(f"  ✗ no images returned for {job['filename']}")
            return False
        img_bytes = base64.b64decode(images[0]["data"])
        out_path.write_bytes(img_bytes)
        print(f"  ✓ saved {out_path} ({len(img_bytes) // 1024} KB)")
        return True
    except Exception as e:
        print(f"  ✗ ERROR {job['filename']}: {e}")
        return False


async def main():
    api_key = os.getenv("EMERGENT_LLM_KEY")
    if not api_key:
        print("EMERGENT_LLM_KEY missing from env")
        sys.exit(1)
    successes = 0
    for job in JOBS:
        ok = await generate_one(api_key, job)
        if ok:
            successes += 1
        await asyncio.sleep(0.5)
    print(f"\nDone: {successes}/{len(JOBS)} images saved to {OUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
