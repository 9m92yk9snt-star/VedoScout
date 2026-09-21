"""Generate a premium footer background asset for the landing-page SiteFooter.
Replaces the plain flat black bg-ink so the footer looks intentional and
premium. Also generates a subtle emerald divider pattern."""
import asyncio, base64, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from emergentintegrations.llm.chat import LlmChat, UserMessage

OUT_MAIN = Path("/app/backend/static/landing/footer-hero-turf.png")
OUT_TEXTURE = Path("/app/backend/static/landing/footer-noise-grain.png")

PROMPT_MAIN = (
    "Ultra-wide 32:9 cinematic hero background image for the FOOTER section of "
    "a premium football scouting app landing page. Composition: an aerial "
    "half-view of an empty football pitch at midnight, chalk lines glowing "
    "under moody stadium floodlights. Deep near-black ink `#0A1A12` sky "
    "occupies the top 60% with tiny warm floodlight halos softly glowing in "
    "the far distance like distant suns. Bottom 40% is the emerald pitch "
    "`#0F3A20` fading to almost black with a subtle grass-blade texture — "
    "chalk-white lines (penalty box, center line hint) barely visible as "
    "glowing whisper strokes. Fine misty fog rolling across mid-frame. "
    "Editorial magazine cinematography — hushed, focused, luxurious. No "
    "players, no faces, no text, no logos, no helmets. Palette: near-black "
    "ink, deep emerald forest, chalk white glow, warm amber `#F5C443` in "
    "distant lights only. 32:9 ultra-wide aspect ratio. Must be dark enough "
    "to overlay bright white text with high contrast. Grain and film-scan "
    "texture for authentic feel. Do NOT include stadium seats or crowds — "
    "keep it minimal, luxurious, empty-pitch mystique."
)

PROMPT_TEXTURE = (
    "Seamless tileable premium noise + grain texture, 512x512 pixels, dark "
    "ink base color `#0A1A12` with barely-visible fine emerald `#1F4F2F` "
    "specks and warm amber `#F5C443` micro-particles at very low opacity. "
    "Think of luxury magazine paper stock with tiny gold-flake ink dust. "
    "Very subtle — the texture should be readable as a background but not "
    "distracting. Must be seamlessly tileable in both x and y. No shapes, no "
    "lines, no text — pure atmospheric grain and light noise."
)


async def gen(out_path: Path, prompt: str, session_id: str):
    api_key = os.environ["EMERGENT_LLM_KEY"]
    print(f"Generating {out_path.name}…")
    chat = LlmChat(api_key=api_key, session_id=session_id,
                   system_message="You are a cinematic sports editorial photographer.")
    chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
    _t, imgs = await chat.send_message_multimodal_response(UserMessage(text=prompt))
    if not imgs:
        print(f"[!] No image returned for {out_path.name}"); return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(base64.b64decode(imgs[0]["data"]))
    print(f"[OK] wrote {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")
    return True


async def main():
    ok1 = await gen(OUT_MAIN, PROMPT_MAIN, "scoutmeplay-footer-main")
    ok2 = await gen(OUT_TEXTURE, PROMPT_TEXTURE, "scoutmeplay-footer-grain")
    print(f"\nDone. main={'ok' if ok1 else 'FAIL'}  texture={'ok' if ok2 else 'FAIL'}")


if __name__ == "__main__":
    asyncio.run(main())
