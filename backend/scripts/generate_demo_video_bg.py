"""Generate the header background for the "Watch the workflow" demo-video
carousel section on the landing page."""
import asyncio, base64, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from emergentintegrations.llm.chat import LlmChat, UserMessage

OUT = Path("/app/backend/static/landing/demo-video-section-bg.png")

PROMPT = (
    "Ultra-cinematic wide-format background image for a football scouting app "
    "landing page section titled 'Watch the workflow'. Composition: an "
    "atmospheric, moody, dark football pitch at dusk — the grass just visible "
    "as deep emerald green under sparse floodlight beams cutting diagonally "
    "from top-right. Fine grain rain visible in the light beams. The pitch "
    "itself is empty of players. A single soccer ball rests on the chalk-white "
    "penalty spot, centered but low in the frame. Atmospheric fog rolls across "
    "the pitch. The mood is like a cold winter training session at midnight — "
    "hushed, focused, professional. Palette: near-black ink `#0A0F0D`, deep "
    "emerald `#0F3A20`, warm floodlight amber `#F5C443` in the beams, chalk "
    "white on the penalty spot. NO people. NO faces. NO helmets (this is "
    "soccer, not American football). NO text overlays. Very wide 16:6 crop, "
    "editorial magazine cinematography, film grain, 4K quality. Composition "
    "should be dark enough to overlay white text on top."
)


async def main():
    api_key = os.environ["EMERGENT_LLM_KEY"]
    print("Generating demo-video-section-bg.png…")
    chat = LlmChat(api_key=api_key, session_id="scoutmeplay-demo-bg",
                   system_message="You are a cinematic sports editorial photographer.")
    chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
    _t, imgs = await chat.send_message_multimodal_response(UserMessage(text=PROMPT))
    if not imgs:
        print("No image"); return
    OUT.write_bytes(base64.b64decode(imgs[0]["data"]))
    print(f"Saved {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    asyncio.run(main())
