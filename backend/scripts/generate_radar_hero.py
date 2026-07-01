"""Generate the cinematic radar-hero background image (Nano Banana)."""
import asyncio, base64, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore

OUT_DIR = Path("/app/backend/static/landing")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PALETTE = (
    "STRICT palette: deep ink black (#0A0F0D), deep forest green (#1F4F2F), "
    "electric lime volt (#CCFF00) as micro-accents ONLY. NO purple/pink/blue/orange. "
    "Cinematic editorial sports magazine photography, dark, dramatic, premium."
)

JOBS = [
    {
        "filename": "radar-hero-stadium.png",
        "prompt": (
            "WIDE 21:9 cinematic photograph shot from behind the goal line looking "
            "up at a fully-lit night football stadium. Dozens of white-hot floodlights "
            "beaming down through swirling mist. Empty pitch below, absolute darkness "
            "in the stands. Extreme moodiness. Ground-level low angle, wet grass "
            "reflecting the lights. NO players, NO ball, NO logos. "
            "Editorial cover-shot quality. Ultra dark, cinematic, premium. " + PALETTE
        ),
    },
    {
        "filename": "radar-hero-tactics.png",
        "prompt": (
            "WIDE 21:9 top-down photograph of a coach's tactics chalkboard — matte "
            "dark forest-green surface with white chalk football-pitch markings drawn "
            "on it (half circle, penalty box, centre circle), a pencil resting on the "
            "left edge, and a small leather notebook in the corner. Dramatic side "
            "light from the right, deep shadows on the left. Nothing else on the board. "
            "Editorial still-life photography. Ultra premium, moody. " + PALETTE
        ),
    },
]


async def gen(key, job):
    out = OUT_DIR / job["filename"]
    print("→", job["filename"])
    try:
        chat = LlmChat(api_key=key, session_id=f"smp-radar-{job['filename']}",
                       system_message="You are an elite editorial sports photographer.")
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
