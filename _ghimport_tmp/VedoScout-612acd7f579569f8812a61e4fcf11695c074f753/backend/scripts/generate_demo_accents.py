"""Generate cool decorative Nano Banana accents for the demo-video carousel.
These sit BEHIND / AROUND the video card without dominating the section.

Assets produced:
  - demo-tactics-arrow.png    Bright chalk arrow + tactics diagram (transparent-look feel on cream)
  - demo-film-strip.png       Vertical film-strip / VHS scan-line side accent
  - demo-halo-bokeh.png       Warm floodlight halo / bokeh spot to place behind card
"""
import asyncio, base64, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from emergentintegrations.llm.chat import LlmChat, UserMessage

OUT_DIR = Path("/app/backend/static/landing")

JOBS = [
    {
        "filename": "demo-tactics-arrow.png",
        "prompt": (
            "Hand-drawn white CHALK football tactics diagram, drawn on a "
            "TRANSPARENT / EMPTY WARM CREAM background (#F5F1E8). Composition: "
            "one bold curved chalk ARROW sweeping in a graceful diagonal from "
            "upper-left down toward the lower-right, ending in a thick "
            "3-pronged chalk arrowhead. Around the arrow, sparse chalk marks: "
            "one small circle representing a player position, one dashed "
            "chalk line, one hand-scribbled '01' number in the top-left. All "
            "marks are drawn in bright chalk-white (#FFFFFF and off-white "
            "#F3F0E4), with a soft CHALK DUST texture giving them a slight "
            "smudged/eraser feel. Empty warm cream background everywhere else. "
            "STYLE: match a football coach's whiteboard. NO photograph, NO "
            "gradients, NO shading — just clean flat 2D chalk marks on cream. "
            "Aspect ratio 4:3 landscape. Very high res, sharp chalk strokes."
        ),
    },
    {
        "filename": "demo-film-strip.png",
        "prompt": (
            "A vertical FILM STRIP / MOVIE REEL edge, drawn against a warm "
            "cream (#F5F1E8) background. Composition: a single vertical strip "
            "of classic 35mm film — black with white/silver perforations (film "
            "sprocket holes) running down both edges. Inside the strip, 5 "
            "small square film frames stacked vertically, each showing an "
            "abstract silhouette suggesting a soccer moment (ball, player "
            "running, kick pose). The frames are very slightly aged, film "
            "grain visible, warm sepia tones inside each frame. The rest of "
            "the image outside the film strip is EMPTY warm cream — the "
            "strip only takes up the middle 25% of the image. Editorial "
            "cinematography museum-poster aesthetic. Sharp, high resolution, "
            "portrait 9:16 aspect ratio. NO text, NO logos."
        ),
    },
    {
        "filename": "demo-halo-bokeh.png",
        "prompt": (
            "Warm ambient FLOODLIGHT HALO / BOKEH glow on a warm cream "
            "(#F5F1E8) background. Composition: one huge soft circular halo "
            "of warm amber-gold light (#F5C443 core fading to #D89F2A edge) "
            "positioned in the CENTER, bleeding to transparent cream at the "
            "outer edges. Around the halo, 8-12 small out-of-focus bokeh "
            "circles floating like specks of stadium light dust. Subtle "
            "diagonal LIGHT RAYS emanating from the halo (very soft). NO "
            "hard edges. NO photograph. Painterly digital glow effect only. "
            "Square 1:1 aspect ratio. Perfect for use as a 'behind the card' "
            "background layer with mix-blend-mode: multiply. Very high res."
        ),
    },
]


async def one(api_key: str, job: dict) -> bool:
    out = OUT_DIR / job["filename"]
    if out.exists():
        print(f"  · exists {out.name} (skip)")
        return True
    print(f"→ generating {job['filename']} …")
    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"scoutmeplay-demo-accent-{job['filename']}",
            system_message=(
                "You are a cinematic sports poster designer. Produce clean, "
                "editorial decorative accents on plain cream backgrounds — "
                "designed to be layered behind UI elements on a light theme."
            ),
        )
        chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(
            modalities=["image", "text"]
        )
        _t, imgs = await chat.send_message_multimodal_response(UserMessage(text=job["prompt"]))
        if not imgs:
            print(f"  ✗ no images returned")
            return False
        out.write_bytes(base64.b64decode(imgs[0]["data"]))
        print(f"  ✓ saved {out} ({out.stat().st_size // 1024} KB)")
        return True
    except Exception as e:
        print(f"  ✗ error: {e}")
        return False


async def main():
    api_key = os.environ["EMERGENT_LLM_KEY"]
    ok = 0
    for job in JOBS:
        if await one(api_key, job):
            ok += 1
    print(f"\n{ok}/{len(JOBS)} generated")


if __name__ == "__main__":
    asyncio.run(main())
