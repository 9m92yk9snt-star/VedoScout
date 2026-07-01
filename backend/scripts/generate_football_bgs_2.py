"""Generate 2 more forest-green-friendly football backgrounds (Nano Banana) — NO PEOPLE."""
import asyncio, base64, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore

OUT_DIR = Path("/app/backend/static/landing")

PALETTE = (
    "STRICT palette: deep forest green (#1F4F2F), deep ink black (#0A0F0D), "
    "chalk white / cream (#F5F1E8) accents. Electric lime volt (#CCFF00) only "
    "as extremely subtle highlights. NO purple/pink/blue/orange. Cinematic, "
    "editorial, dark and premium. "
    "ABSOLUTELY NO PEOPLE, NO PLAYERS, NO HUMANS, NO FACES, NO BODY PARTS, "
    "NO HANDS, NO LEGS, NO SILHOUETTES OF PEOPLE."
)

JOBS = [
    {
        "filename": "bg-benchmark-tunnel.png",
        "prompt": (
            "WIDE 21:9 dramatic cinematic photograph shot from deep inside a dark "
            "stadium tunnel, looking outward through the exit toward a brightly-lit "
            "empty football pitch beyond. Concrete tunnel walls in deep shadow "
            "on both sides, bright glowing rectangle at the far end showing the "
            "green pitch and stadium floodlights. Faint white paint markings on "
            "the tunnel floor. Absolute emptiness — no players, no staff. Deep, "
            "moody, ceremonial. Editorial sports photography. " + PALETTE
        ),
    },
    {
        "filename": "bg-archetype-aerial.png",
        "prompt": (
            "WIDE 21:9 aerial top-down drone photograph of an empty football pitch "
            "at night, illuminated by stadium floodlights. The dark green grass "
            "is crisply painted with bright white lines — center circle, penalty "
            "boxes, midfield line, corner arcs — forming a perfect symmetrical "
            "diagram. Deep shadows around the edges. Absolutely no players, no "
            "ball, no goals inside frame — only the geometric pitch layout on "
            "dark green grass. Editorial, cinematic. " + PALETTE
        ),
    },
]


async def gen(key, job):
    out = OUT_DIR / job["filename"]
    print("→", job["filename"])
    try:
        chat = LlmChat(api_key=key, session_id=f"smp-bg2-{job['filename']}",
                       system_message="You are an elite editorial sports photographer specializing in empty stadium and pitch photography. NEVER include people, silhouettes, or body parts in any composition.")
        chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
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
