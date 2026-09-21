"""Generates the Single Report banner image (Nano Banana)."""
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
    "and tiny volt/lime accents (#CCFF00). NO purple/pink/blue. Photo-realistic, "
    "premium sports documentary aesthetic."
)

JOBS = [
    {
        "filename": "single-banner.png",
        "prompt": (
            "Wide cinematic 16:9 photograph: an open premium scout-report binder lying on a "
            "polished dark wood table. The left page shows a clean radar chart in forest "
            "green with neat handwritten annotations; the right page shows a printed "
            "'OVERALL SCORE 8.2' headline with 4 mini bar charts (TECHNICAL, TACTICAL, "
            "PHYSICAL, MENTALITY). A vintage stopwatch and a fountain pen rest on the "
            "binder. Soft warm golden-hour side light. Editorial flat-lay product "
            "photography, ultra detailed, shallow depth of field, slight film grain. " + PALETTE
        ),
    },
    {
        "filename": "single-icon.png",
        "prompt": (
            "Square 1:1 photograph: a single rolled-up rolled scout report tied with a thin "
            "lime-green ribbon, standing upright against a soft cream gradient background. "
            "Editorial product still-life. Shallow depth of field, top-down warm side light. "
            "Minimalist composition. " + PALETTE
        ),
    },
]


async def gen(key, job):
    out = OUT_DIR / job["filename"]
    print("→", job["filename"])
    try:
        chat = LlmChat(api_key=key, session_id=f"smp-single-{job['filename']}",
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
