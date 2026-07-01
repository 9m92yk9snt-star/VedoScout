"""Report page enrichment — warm football-feel images for section dividers."""
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
    "lime accents (#CCFF00). NO purple/pink/blue. Editorial sports magazine "
    "photography. Warm, human, hopeful — premium but never cold."
)

JOBS = [
    {
        "filename": "report-hero-divider.png",
        "prompt": (
            "WIDE 21:9 cinematic photograph: empty professional football pitch "
            "at golden-hour, mist hanging low, a single ball resting on the centre "
            "spot under warm side-light. Stadium silhouette in deep background, "
            "blurred. Editorial sports magazine cover, evocative, hopeful. "
            "Wide 21:9 ratio. " + PALETTE
        ),
    },
    {
        "filename": "pillar-technical.png",
        "prompt": (
            "Square 1:1 cinematic close-up: a youth football boot striking a ball "
            "with the inside of the foot on a green pitch, sharp focus on the "
            "contact point, grass particles flying, warm low afternoon light. "
            "Editorial close-up product/sport photography. Square. " + PALETTE
        ),
    },
    {
        "filename": "pillar-tactical.png",
        "prompt": (
            "Square 1:1 cinematic over-the-shoulder photograph of a U13 footballer "
            "scanning the pitch before receiving a pass, his head turned to look "
            "for space, blurred opponents in background, soft late-afternoon "
            "light. Editorial sports magazine. Square. " + PALETTE
        ),
    },
    {
        "filename": "pillar-physical.png",
        "prompt": (
            "Square 1:1 dynamic motion photograph of a young footballer mid-"
            "sprint with the ball at his feet, knees high, slight motion blur on "
            "the legs only, golden-hour rim light, blurred pitch background. "
            "Editorial sports action photography. Square. " + PALETTE
        ),
    },
    {
        "filename": "pillar-mental.png",
        "prompt": (
            "Square 1:1 intimate portrait photograph of a young footballer in "
            "training kit, calm focused expression, looking forward, one hand on "
            "his hip, soft natural light from the side, cream/forest blurred "
            "training-ground background. Editorial sports portrait. Square. "
            + PALETTE
        ),
    },
    {
        "filename": "scout-avatar.png",
        "prompt": (
            "Square 1:1 editorial portrait: a faceless scout (camera angle from "
            "the side, only profile and hands visible, holding a small leather "
            "notebook and a pencil, wearing a forest-green training jacket). Soft "
            "cream-toned blurred background. Premium documentary feel. Square. "
            + PALETTE
        ),
    },
]


async def gen(key, job):
    out = OUT_DIR / job["filename"]
    print("→", job["filename"])
    try:
        chat = LlmChat(api_key=key, session_id=f"smp-rep-{job['filename']}",
                       system_message="You are an elite editorial sports photographer.")
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
