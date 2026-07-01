"""
Generate 4 premium Nano Banana images specifically for the /scouts landing page.
Cinematic, executive-tier — targets professional scouts/agents/clubs.

Run: cd /app/backend && python scripts/generate_scouts_landing.py
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

# Dark cinema palette — deep forest greens, warm oranges, brass accents.
# Contrast against the cream Scout landing sections should be intentional.
PALETTE_NOTE = (
    "Palette: deep midnight forest green (#0A1F14 / #1F4F2F), warm brass "
    "(#B8892C), soft chalk white on dark background. Cinematic film-still "
    "quality, subtle rim lighting, moody atmospheric, premium boardroom "
    "editorial aesthetic. NO purple, NO pink, NO neon blue. Very high "
    "resolution, sharp focus, magazine cover quality."
)

JOBS = [
    {
        "filename": "scouts-hero-tunnel.png",
        "prompt": (
            "Wide cinematic film-still, dark stadium tunnel entrance viewed from inside. "
            "Silhouettes of a scout in a dark tailored blazer and a young footballer "
            "walking together toward the light-filled pitch at the tunnel's end. "
            "Dramatic god-rays of golden hour light streaming from the tunnel exit, "
            "concrete brutalist tunnel walls, hazy atmosphere, dust particles catching light. "
            "Composition heavily weighted RIGHT-third (subjects and light), left 60% is "
            "deep shadow — space for large headline overlay. No faces visible, silhouettes only. "
            + PALETTE_NOTE
        ),
    },
    {
        "filename": "scouts-boardroom.png",
        "prompt": (
            "Overhead top-down photograph of an elite football scouting war-room table. "
            "Deep forest-green leather tabletop scattered with: a leather-bound scout's "
            "notebook opened with hand-drawn tactical diagrams, a Montblanc-style pen, "
            "a large paper printout showing a heat-map of a football pitch with pink and "
            "yellow zones, a mobile phone showing a paused video clip of a match, a "
            "small pile of PASSPORTS in different colors, a coffee cup, and a single "
            "football boot placed elegantly at one corner. Warm brass desk-lamp light "
            "from one side casting long dramatic shadows. Executive/boardroom mood. "
            "Editorial magazine photography, very high detail, film grain. "
            + PALETTE_NOTE
        ),
    },
    {
        "filename": "scouts-data-tablet.png",
        "prompt": (
            "Close-up cinematic photograph of a tablet screen resting on dark oak wood. "
            "Screen displays a MODERN, ULTRA-MINIMAL football scouting dashboard with "
            "a radar chart, bar graphs, timeline heat-map, and small player-headshot "
            "thumbnails — rendered in FOREST GREEN and BRASS accents on charcoal-black. "
            "Beside the tablet: a leather notebook, a fountain pen, a football corner-"
            "post flag laid diagonally. Warm side-lighting from behind. Depth of field. "
            "Premium tech-editorial aesthetic — feels like Bloomberg for scouts. "
            + PALETTE_NOTE
        ),
    },
    {
        "filename": "scouts-signing-desk.png",
        "prompt": (
            "Cinematic close-up of two hands over a dark wooden desk — one hand of a "
            "young footballer (visible only from the wrist, wearing a training top "
            "sleeve) and one hand of an older scout (visible only from the wrist, "
            "wearing a suit sleeve with a subtle wristwatch), reaching to sign a paper "
            "contract on a leather blotter. A brass fountain pen rests on the contract. "
            "Warm lamplight from left, deep shadows on right. No faces visible. "
            "Symbolic moment of a scout signing a talent found through the database. "
            "Editorial documentary photography, film grain, very high detail. "
            + PALETTE_NOTE
        ),
    },
]


async def generate_one(api_key: str, job: dict) -> bool:
    out_path = OUT_DIR / job["filename"]
    if out_path.exists():
        print(f"  · exists {out_path.name} (skip)")
        return True
    print(f"→ generating {job['filename']} …")
    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"scoutmeplay-scouts-{job['filename']}",
            system_message="You are an award-winning cinematic sports and boardroom editorial photographer.",
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
        print(f"  ✓ saved {out_path.name} ({len(img_bytes) // 1024} KB)")
        return True
    except Exception as e:
        print(f"  ✗ {job['filename']} failed: {e}")
        return False


async def main():
    api_key = os.environ["EMERGENT_LLM_KEY"]
    ok = 0
    for job in JOBS:
        if await generate_one(api_key, job):
            ok += 1
    print(f"\n{ok}/{len(JOBS)} generated → {OUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
