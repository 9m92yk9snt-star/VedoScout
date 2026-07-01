"""Generate football-element backgrounds (Nano Banana) — NO PEOPLE, only objects."""
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
    "chalk white / cream (#F5F1E8), electric lime volt (#CCFF00) as tiny accents. "
    "NO purple/pink/blue/orange. Ultra dark, cinematic, editorial. "
    "ABSOLUTELY NO PEOPLE, NO PLAYERS, NO HUMANS, NO FACES, NO BODY PARTS, NO HANDS, NO LEGS."
)

JOBS = [
    {
        "filename": "bg-radar-tactics.png",
        "prompt": (
            "WIDE 21:9 extreme macro close-up photograph of a coach's dark green "
            "chalkboard filled with hand-drawn football tactical diagrams — white "
            "chalk X's and O's arranged in a 4-3-3 formation, dashed arrows "
            "showing movement between them, small circles for players (dots only), "
            "a curved arrow showing a pass, and one bold volt-lime chalk mark "
            "highlighting a key run. The surface is scuffed, dusty, well-used. "
            "Dramatic side lighting from the right creating shadow across the "
            "board. Editorial still-life photography. " + PALETTE
        ),
    },
    {
        "filename": "bg-scout-hero.png",
        "prompt": (
            "WIDE 21:9 dramatic cinematic photograph of a fresh white chalk touchline "
            "painted on wet grass at night, viewed at extreme low ground-level "
            "angle. The white line stretches diagonally across the frame, catching "
            "faint stadium floodlight from off-camera. Green grass blades individually "
            "visible, some carrying tiny water droplets. Deep black darkness beyond "
            "the line. Moody, atmospheric, editorial. " + PALETTE
        ),
    },
    {
        "filename": "bg-standout-boots.png",
        "prompt": (
            "SQUARE 1:1 extreme close-up macro photograph of a single black football "
            "boot standing on wet green grass, stud pattern clearly visible on the "
            "sole edge, laces tied neatly. Dark moody lighting from one side, deep "
            "shadow on the other. Nothing else in frame. NO leg, NO foot inside "
            "the boot — just the empty boot standing alone on grass. Editorial "
            "product-still-life photography. " + PALETTE
        ),
    },
    {
        "filename": "bg-standout-ball.png",
        "prompt": (
            "SQUARE 1:1 extreme close-up macro photograph of a classic black-and-white "
            "football (soccer ball) sitting on the fresh white chalk line of a "
            "football pitch. The ball's leather panel stitching is visible. Wet "
            "green grass on both sides. Deep dramatic shadow. Overhead moody "
            "lighting. Editorial product photography. NO player, NO foot, NO hands "
            "— just the ball on the line. " + PALETTE
        ),
    },
    {
        "filename": "bg-standout-net.png",
        "prompt": (
            "SQUARE 1:1 dramatic macro photograph of a white football goal net "
            "photographed from close range at an angle, showing the diamond mesh "
            "pattern crisply. Deep black darkness behind the net. A faint stadium "
            "floodlight glow catches the top row of net rope. Nothing behind or "
            "in front of the net. Cinematic, editorial. NO players, NO ball, NO goalkeeper. "
            + PALETTE
        ),
    },
]


async def gen(key, job):
    out = OUT_DIR / job["filename"]
    print("→", job["filename"])
    try:
        chat = LlmChat(api_key=key, session_id=f"smp-bg-{job['filename']}",
                       system_message="You are an elite editorial sports still-life photographer. Never include people in your compositions.")
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
