"""Mobile enrichment image set — 5 graphics for richer mobile experience.

Run: cd /app/backend && python scripts/generate_mobile_assets.py
"""
import asyncio, base64, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore

OUT_DIR = Path("/app/backend/static/landing")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PALETTE = (
    "STRICT palette: cream off-white (#F4EFE6), deep forest green (#1F4F2F), "
    "and tiny volt/lime accents (#CCFF00). NO purple/pink/blue. "
    "Premium editorial photography, ultra detailed."
)

JOBS = [
    {
        "filename": "hero-action-portrait.png",
        "prompt": (
            "VERTICAL 9:16 cinematic portrait photograph of a young U14 male football player "
            "in mid-stride sprinting with the ball at his feet on a green pitch, low "
            "golden-hour rim light, slight motion blur on the legs, dust particles kicking "
            "up. Subject occupies center of frame, intense focused expression. Wears "
            "anonymous forest-green training kit (no logos, no number). Shallow depth of "
            "field, blurred grass and distant goal in background. Editorial sports magazine "
            "quality. VERTICAL 9:16 RATIO (PORTRAIT). " + PALETTE
        ),
    },
    {
        "filename": "imagestrip-mobile.png",
        "prompt": (
            "SQUARE 1:1 cinematic photograph: panoramic-style view of a U13 football "
            "training session at dusk, three players in forest-green kit performing cone "
            "drills in the foreground, mist hanging over a stadium in the deep background, "
            "golden-hour lighting. Square 1:1 ratio. " + PALETTE
        ),
    },
    {
        "filename": "badge-free.png",
        "prompt": (
            "Square 1:1 minimal 3D-rendered circular badge against a soft cream background. "
            "Forest green circular ring with a glossy cream center, in the centre a single "
            "thin lime-green outlined star symbol. Premium product-mock aesthetic, soft "
            "studio light, shallow depth of field. Square 1:1 ratio. " + PALETTE
        ),
    },
    {
        "filename": "badge-single.png",
        "prompt": (
            "Square 1:1 minimal 3D-rendered circular badge against a soft cream background. "
            "Forest-green outer ring with a glossy black center, in the centre a single "
            "lime-green outlined trophy symbol. Premium product-mock aesthetic, soft studio "
            "light, shallow depth of field. Square 1:1 ratio. " + PALETTE
        ),
    },
    {
        "filename": "badge-premium.png",
        "prompt": (
            "Square 1:1 minimal 3D-rendered circular badge against a dark forest-green "
            "background. Lime-green outer ring with a glossy forest-green center, in the "
            "centre a single lime-green outlined star or chevron symbol. Premium "
            "product-mock aesthetic. Square 1:1 ratio. " + PALETTE
        ),
    },
    {
        "filename": "badge-vip.png",
        "prompt": (
            "Square 1:1 minimal 3D-rendered circular badge against a black background. "
            "Gold (#F5C443) outer ring with a glossy black center, in the centre a single "
            "gold outlined crown symbol. Ultra-premium product-mock aesthetic, soft studio "
            "light. Square 1:1 ratio. NO COLORS OUTSIDE: cream, forest green, lime green, "
            "black, gold (#F5C443). NO purple/pink/blue."
        ),
    },
]


async def gen(key, job):
    out = OUT_DIR / job["filename"]
    print("→", job["filename"])
    try:
        chat = LlmChat(api_key=key, session_id=f"smp-mob-{job['filename']}",
                       system_message="You are an elite editorial photographer & product designer.")
        chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image","text"])
        _t, imgs = await chat.send_message_multimodal_response(UserMessage(text=job["prompt"]))
        if not imgs:
            print(" ✗ no img")
            return False
        out.write_bytes(base64.b64decode(imgs[0]["data"]))
        print(f" ✓ {out.name} {out.stat().st_size // 1024} KB")
        return True
    except Exception as e:
        print(" ✗", e)
        return False


async def main():
    k = os.getenv("EMERGENT_LLM_KEY")
    ok = 0
    for j in JOBS:
        if await gen(k, j):
            ok += 1
        await asyncio.sleep(0.4)
    print(f"\n{ok}/{len(JOBS)} saved")


if __name__ == "__main__":
    asyncio.run(main())
