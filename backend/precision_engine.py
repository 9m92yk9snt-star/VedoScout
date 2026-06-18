"""
ScoutMePlay — Precision Scout pipeline.

A multi-signal video analysis engine. The goal is to make the AI find the
marked player reliably and describe what they did with confident, evidence-
backed language. No hedging, no confidence badges, no pre-pay verification.

Three independent signals are extracted *before* Gemini is asked to reason:

  1. Visual fingerprint   — jersey colour, shorts colour, body ratio, crop
  2. Audio event timeline — RMS spike timestamps (likely goals / loud plays)
  3. Player details        — typed by the user (already provided to upload)

Gemini receives all three as priors, plus the full clip + the marker image.
This dramatically reduces tracking loss and hallucinated events.
"""

from __future__ import annotations

import json
import logging
import math
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ── Colour naming helpers ─────────────────────────────────────────────

# Common kit colour palette — used to give the AI a human-readable name
# (e.g. "navy blue jersey, white shorts") instead of just hex.
_KIT_COLOURS = [
    ("white",        (240, 240, 240)),
    ("light grey",   (200, 200, 200)),
    ("grey",         (140, 140, 140)),
    ("black",        (25, 25, 25)),
    ("red",          (200, 35, 40)),
    ("dark red",     (130, 25, 30)),
    ("orange",       (235, 120, 30)),
    ("yellow",       (240, 215, 50)),
    ("green",        (35, 145, 60)),
    ("dark green",   (15, 75, 35)),
    ("light blue",   (110, 175, 230)),
    ("blue",         (35, 80, 200)),
    ("navy blue",    (20, 35, 90)),
    ("purple",       (110, 50, 180)),
    ("pink",         (235, 140, 195)),
    ("brown",        (110, 75, 50)),
    ("beige",        (215, 195, 165)),
    ("maroon",       (110, 30, 50)),
    ("teal",         (30, 145, 145)),
]


def _name_colour(rgb: tuple[int, int, int]) -> str:
    """Map an RGB triple to the closest plain-language kit colour."""
    r, g, b = rgb
    best = "unknown"
    best_d = float("inf")
    for name, (cr, cg, cb) in _KIT_COLOURS:
        d = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if d < best_d:
            best_d = d
            best = name
    return best


def _hex_from_rgb(rgb: tuple[int, int, int]) -> str:
    return "#{0:02X}{1:02X}{2:02X}".format(*rgb)


def extract_frame_at(video_path: str | Path, t_seconds: float, out_path: str | Path) -> bool:
    """Extract a single still frame from `video_path` at time `t_seconds` to `out_path`.

    Returns True on success, False otherwise. Used to grab the per-anchor frame so
    we can crop each anchor's subject patch from the actual video, not from a
    pre-rendered marker image.
    """
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", f"{max(0.0, float(t_seconds)):.3f}",
                "-i", str(video_path),
                "-frames:v", "1",
                "-q:v", "3",
                str(out_path),
            ],
            check=True,
            timeout=30,
        )
        return Path(out_path).exists() and Path(out_path).stat().st_size > 0
    except Exception as e:
        logger.warning(f"extract_frame_at failed at t={t_seconds}: {e}")
        return False


def _dominant_colour(pixels: np.ndarray, k: int = 3) -> tuple[int, int, int]:
    """k-means colour clustering; returns the most populous cluster centre.

    `pixels` is an (N, 3) array in BGR (OpenCV order) or RGB. We normalise to RGB.
    """
    if pixels.size == 0:
        return (128, 128, 128)
    sample = pixels
    if sample.shape[0] > 4000:
        idx = np.random.choice(sample.shape[0], 4000, replace=False)
        sample = sample[idx]
    sample = sample.astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centres = cv2.kmeans(
        sample, k, None, criteria, 4, cv2.KMEANS_PP_CENTERS
    )
    counts = np.bincount(labels.flatten(), minlength=k)
    dominant = centres[int(np.argmax(counts))]
    r, g, b = (int(round(c)) for c in dominant[::-1])  # BGR → RGB
    return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


# ── Visual fingerprint ────────────────────────────────────────────────

@dataclass
class PlayerFingerprint:
    """Auto-detected visual identity of the marked player."""

    jersey_hex: str
    jersey_name: str
    shorts_hex: str
    shorts_name: str
    body_ratio: float           # height / width of the marked box
    crop_path: Optional[str]    # path to the saved subject crop (jpg)
    box: dict                   # original normalised box {x, y, w, h}
    confidence: str             # internal sanity tag — never shown to user

    def to_prompt_block(self) -> str:
        """Compact human-readable block fed to Gemini as a prior."""
        return (
            "LOCKED PLAYER FINGERPRINT (auto-detected from the user's mark — this is the ONLY "
            "player to analyse):\n"
            f"  • Jersey colour: {self.jersey_name} ({self.jersey_hex})\n"
            f"  • Shorts colour: {self.shorts_name} ({self.shorts_hex})\n"
            f"  • Body ratio (h/w): {self.body_ratio:.2f}\n"
            "If multiple players share the jersey colour, prefer the one matching the shorts "
            "colour and body ratio. If you cannot see the locked player in a moment, write "
            'OFF-CAMERA for that moment — never describe a different player.'
        )


def _crop_box_from_image(
    img_bgr: np.ndarray, box: dict
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Convert a normalised box (0-1) to pixel coords, clamp, and crop."""
    h, w = img_bgr.shape[:2]
    bx = max(0.0, min(1.0, float(box.get("x", 0))))
    by = max(0.0, min(1.0, float(box.get("y", 0))))
    bw = max(0.01, min(1.0 - bx, float(box.get("w", 0.2))))
    bh = max(0.01, min(1.0 - by, float(box.get("h", 0.3))))
    x0 = int(round(bx * w))
    y0 = int(round(by * h))
    x1 = int(round((bx + bw) * w))
    y1 = int(round((by + bh) * h))
    x0, x1 = sorted((max(0, x0), min(w, x1)))
    y0, y1 = sorted((max(0, y0), min(h, y1)))
    return img_bgr[y0:y1, x0:x1].copy(), (x0, y0, x1, y1)


def extract_player_fingerprint(
    marker_image_path: str | Path,
    box: dict,
    crop_save_path: str | Path | None = None,
) -> PlayerFingerprint:
    """Extract jersey/shorts colours and body proportions from the marked patch.

    The box is the user-drawn rectangle around their player on the marked frame.
    All coords are normalised 0..1.
    """
    img = cv2.imread(str(marker_image_path), cv2.IMREAD_COLOR)
    if img is None:
        # Fallback fingerprint — we still need the AI to know the user marked someone,
        # but we don't have a real colour read.
        return PlayerFingerprint(
            jersey_hex="#888888",
            jersey_name="unclear",
            shorts_hex="#888888",
            shorts_name="unclear",
            body_ratio=2.0,
            crop_path=None,
            box=box,
            confidence="low",
        )

    crop, (x0, y0, x1, y1) = _crop_box_from_image(img, box)
    if crop.size == 0:
        return PlayerFingerprint(
            jersey_hex="#888888",
            jersey_name="unclear",
            shorts_hex="#888888",
            shorts_name="unclear",
            body_ratio=2.0,
            crop_path=None,
            box=box,
            confidence="low",
        )

    ch, cw = crop.shape[:2]
    # Jersey region — middle-upper third of the body (avoid head & arms outline noise)
    j_top = int(ch * 0.18)
    j_bot = int(ch * 0.55)
    jersey = crop[j_top:j_bot, int(cw * 0.20):int(cw * 0.80)]
    jersey_px = jersey.reshape(-1, 3) if jersey.size else np.empty((0, 3), dtype=np.uint8)

    # Shorts region — lower 35% of the body
    s_top = int(ch * 0.60)
    s_bot = int(ch * 0.92)
    shorts = crop[s_top:s_bot, int(cw * 0.20):int(cw * 0.80)]
    shorts_px = shorts.reshape(-1, 3) if shorts.size else np.empty((0, 3), dtype=np.uint8)

    jersey_rgb = _dominant_colour(jersey_px, k=3) if jersey_px.size else (136, 136, 136)
    shorts_rgb = _dominant_colour(shorts_px, k=3) if shorts_px.size else (136, 136, 136)

    body_ratio = ch / max(1, cw)

    crop_path_out: Optional[str] = None
    if crop_save_path:
        try:
            cv2.imwrite(str(crop_save_path), crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            crop_path_out = str(crop_save_path)
        except Exception as e:
            logger.warning(f"Could not save subject crop: {e}")

    return PlayerFingerprint(
        jersey_hex=_hex_from_rgb(jersey_rgb),
        jersey_name=_name_colour(jersey_rgb),
        shorts_hex=_hex_from_rgb(shorts_rgb),
        shorts_name=_name_colour(shorts_rgb),
        body_ratio=round(body_ratio, 2),
        crop_path=crop_path_out,
        box={
            "x": float(box.get("x", 0)),
            "y": float(box.get("y", 0)),
            "w": float(box.get("w", 0)),
            "h": float(box.get("h", 0)),
        },
        confidence="ok",
    )


# ── Audio event timeline ──────────────────────────────────────────────

@dataclass
class AudioEvent:
    t: float        # timestamp in seconds
    peak_db: float  # rms peak in dBFS (relative)
    kind: str       # always "loud_event" for now

    def to_dict(self) -> dict:
        return asdict(self)


def extract_audio_events(
    video_path: str | Path,
    *,
    min_gap_seconds: float = 3.0,
    top_n: int = 8,
) -> list[AudioEvent]:
    """Detect timestamps with sudden audio volume spikes.

    Crowd cheers, whistle bursts and shouts all show up as RMS peaks. Goals
    and big plays almost always coincide with one — so the AI gets to cross-
    check its visual interpretation against this independent signal.

    Returns at most `top_n` events, sorted by time.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        return []

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)

    try:
        # Downmix to mono 16 kHz — small file, fast to scan.
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(video_path),
                "-ac", "1", "-ar", "16000",
                "-vn", str(wav_path),
            ],
            check=True,
            timeout=120,
        )
    except Exception as e:
        logger.warning(f"audio extraction failed: {e}")
        try:
            wav_path.unlink(missing_ok=True)
        except Exception:
            pass
        return []

    try:
        with wave.open(str(wav_path), "rb") as wav:
            sr = wav.getframerate()
            n_frames = wav.getnframes()
            raw = wav.readframes(n_frames)
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    finally:
        try:
            wav_path.unlink(missing_ok=True)
        except Exception:
            pass

    if audio.size == 0 or sr <= 0:
        return []

    # Rolling RMS in 0.5 s windows, step 0.25 s.
    win = int(sr * 0.5)
    step = int(sr * 0.25)
    if win <= 0:
        return []

    rms_values: list[tuple[float, float]] = []  # (timestamp, rms)
    for start in range(0, len(audio) - win, step):
        seg = audio[start:start + win]
        rms = float(np.sqrt(np.mean(seg ** 2) + 1e-12))
        rms_values.append((start / sr, rms))

    if not rms_values:
        return []

    rms_arr = np.array([r for _, r in rms_values])
    median = float(np.median(rms_arr) + 1e-9)
    # Convert spike magnitude to dB-ish relative scale
    spike_threshold = median * 1.8

    events: list[AudioEvent] = []
    # Walk sorted by descending rms, keep peaks separated by min_gap_seconds.
    order = np.argsort(-rms_arr)
    for idx in order:
        t, rms = rms_values[idx]
        if rms < spike_threshold:
            break
        # Enforce minimum gap so we don't return 5 tightly packed peaks of the same cheer
        if any(abs(t - e.t) < min_gap_seconds for e in events):
            continue
        peak_db = 20.0 * math.log10(rms / median)
        events.append(AudioEvent(t=round(t, 2), peak_db=round(peak_db, 1), kind="loud_event"))
        if len(events) >= top_n:
            break

    events.sort(key=lambda e: e.t)
    return events


def audio_events_to_prompt_block(events: list[AudioEvent]) -> str:
    if not events:
        return (
            "AUDIO EVIDENCE: no significant audio peaks detected in the clip "
            "(quiet recording or short clip)."
        )
    rows = [f"  • {e.t:>5.2f}s — loud_event ({e.peak_db:+.1f} dB vs baseline)" for e in events]
    return (
        "AUDIO EVIDENCE — independent timestamps where the crowd / shouts / "
        "whistle spiked. A real goal or big play almost always lines up with one:\n"
        + "\n".join(rows)
    )


# ── Prompt builders ───────────────────────────────────────────────────

# Hard rules every Gemini call gets. Pure confident voice, no hedging.
CONFIDENT_VOICE_RULES = """
LANGUAGE & VOICE RULES (absolute, no exceptions):

1. CONFIDENT VOICE ONLY. Write like a professional scout. Never use the words
   "appears to", "seems to", "likely", "possibly", "might have", "looks like".
   Either you observed something and you state it as a fact, or you write
   OFF-CAMERA for that moment.

2. NEVER INVENT EVENTS. Goals, shots, dribbles past defender, key passes,
   tackles, saves — only state them when you actually saw them happen on the
   locked player. If the marked player scored, that overrides everything else.

3. CROSS-CHECK AGAINST AUDIO. If the AUDIO EVIDENCE block lists a loud peak
   near a moment you described, use that as confirmation. If you described a
   goal and there is no audio peak nearby, double-check that the ball really
   crossed the line — do not output a goal you are unsure of.

4. LOCK ON THE FINGERPRINT. The "LOCKED PLAYER FINGERPRINT" block tells you
   exactly what jersey + shorts + body to track. Ignore every other player.

5. NO confidence ratings in your prose. Do not write "high confidence" or
   "I am 80% sure" anywhere in the user-facing text. (You still output the
   structured confidence fields the schema requires — those are for internal
   use only.)
"""


def build_anchor_ensemble_block(anchor_descriptions: list[dict]) -> str:
    """Prompt block describing N anchors of the same player at different timestamps.

    Each item in `anchor_descriptions` is {t: float, jersey_name, shorts_name, body_ratio}.
    The actual anchor crop images are attached separately as file_contents — this is the
    written instruction telling Gemini what those crops are.
    """
    if not anchor_descriptions:
        return ""
    rows = []
    for i, a in enumerate(anchor_descriptions, start=1):
        rows.append(
            f"  • Anchor {i} @ {float(a.get('t', 0)):.2f}s — "
            f"jersey {a.get('jersey_name', '?')}, shorts {a.get('shorts_name', '?')}, "
            f"body ratio {float(a.get('body_ratio', 0)):.2f}"
        )
    return (
        f"MULTI-ANCHOR LOCK — {len(anchor_descriptions)} confirmed sightings of the SAME player "
        "at different moments in the video. The first N images attached are these anchors in order. "
        "Use ALL of them as the visual reference — the player you must analyse is the one matching "
        "every anchor. Ignore all other players.\n"
        + "\n".join(rows)
    )


def build_preview_prompt(
    base_prompt: str,
    fingerprint: PlayerFingerprint,
    audio_events: list[AudioEvent],
    player_details: dict,
    content_type: str = "other",
    player_visible: str = "clear",
    camera_distance: str = "medium",
    anchors: list[dict] | None = None,
) -> str:
    """Wrap the existing preview prompt with the new precision priors."""
    details_str = json.dumps(player_details, ensure_ascii=False)
    primed = (
        base_prompt
        .replace("{player_details}", details_str)
        .replace("{content_type}", str(content_type))
        .replace("{player_visible}", str(player_visible))
        .replace("{camera_distance}", str(camera_distance))
    )
    anchor_block = build_anchor_ensemble_block(anchors or [])
    sections = [
        anchor_block,
        fingerprint.to_prompt_block(),
        audio_events_to_prompt_block(audio_events),
        CONFIDENT_VOICE_RULES,
        primed,
    ]
    return "\n\n".join(s for s in sections if s)


def build_full_prompt(
    base_prompt: str,
    fingerprint: PlayerFingerprint,
    audio_events: list[AudioEvent],
    player_details: dict,
    content_type: str = "other",
    quality: str = "good",
    player_visible: str = "clear",
    camera_distance: str = "medium",
    games_detected: int = 1,
    anchors: list[dict] | None = None,
) -> str:
    details_str = json.dumps(player_details, ensure_ascii=False)
    primed = (
        base_prompt
        .replace("{player_details}", details_str)
        .replace("{content_type}", str(content_type))
        .replace("{quality}", str(quality))
        .replace("{player_visible}", str(player_visible))
        .replace("{camera_distance}", str(camera_distance))
        .replace("{games_detected}", str(games_detected))
    )
    anchor_block = build_anchor_ensemble_block(anchors or [])
    sections = [
        anchor_block,
        fingerprint.to_prompt_block(),
        audio_events_to_prompt_block(audio_events),
        CONFIDENT_VOICE_RULES,
        primed,
    ]
    return "\n\n".join(s for s in sections if s)


# ── Post-process confident voice scrubber ─────────────────────────────

# In case Gemini occasionally slips and outputs hedging language anyway,
# we strip it on the way out. Pure safety net.
_HEDGE_REPLACEMENTS = [
    (r"\bappears to be\b", "is"),
    (r"\bappears to\b", ""),
    (r"\bseems to be\b", "is"),
    (r"\bseems to\b", ""),
    (r"\blikely\b", ""),
    (r"\bpossibly\b", ""),
    (r"\bmight have\b", "did"),
    (r"\blooks like\b", "is"),
    (r"\bprobably\b", ""),
    (r"\bperhaps\b", ""),
]


def _scrub_text(text: str) -> str:
    import re
    if not isinstance(text, str):
        return text
    out = text
    for pat, repl in _HEDGE_REPLACEMENTS:
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    # Collapse double spaces created by deletions.
    out = re.sub(r" {2,}", " ", out).strip()
    # Capitalise sentences that lost their first word.
    out = re.sub(r"(^|\. )([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)
    return out


def scrub_hedging(payload):
    """Recursively walk a dict/list returned by Gemini and remove hedging language."""
    if isinstance(payload, dict):
        return {k: scrub_hedging(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [scrub_hedging(v) for v in payload]
    if isinstance(payload, str):
        return _scrub_text(payload)
    return payload


__all__ = [
    "PlayerFingerprint",
    "AudioEvent",
    "extract_frame_at",
    "extract_player_fingerprint",
    "extract_audio_events",
    "audio_events_to_prompt_block",
    "build_anchor_ensemble_block",
    "build_preview_prompt",
    "build_full_prompt",
    "scrub_hedging",
    "CONFIDENT_VOICE_RULES",
    "verify_and_pick_thumbnail",
]


# ── Thumbnail re-verification ─────────────────────────────────────────
#
# Goal: when generating per-timestamp thumbnails for the final report, we
# don't blindly trust the raw `ts` value from Gemini. Instead we sample a
# small window (±1.0 s) of candidate frames around the timestamp and pick
# the one whose pixels best match the LOCKED PLAYER's jersey + shorts
# fingerprint. Then we draw a small volt-green reticle around the matching
# region so the reader sees AT A GLANCE which player on screen the comment
# refers to.
#
# This dramatically improves report credibility — even if Gemini's
# timestamp is off by 600-800 ms, the thumbnail still shows the right
# player rather than a random teammate caught in a different moment.

def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = (h or "#888888").lstrip("#")
    if len(h) != 6:
        return (136, 136, 136)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (136, 136, 136)


def _color_match_mask_bgr(frame_bgr: np.ndarray, target_rgb: tuple[int, int, int], tol: int = 55) -> np.ndarray:
    """Return a boolean mask of pixels close to `target_rgb` in the BGR frame."""
    b, g, r = cv2.split(frame_bgr)
    tr, tg, tb = target_rgb
    dist2 = (r.astype(np.int32) - tr) ** 2 + (g.astype(np.int32) - tg) ** 2 + (b.astype(np.int32) - tb) ** 2
    return dist2 < (tol * tol)


def verify_and_pick_thumbnail(
    video_path: str | Path,
    seconds: float,
    fingerprint,  # PlayerFingerprint
    out_path: str | Path,
    *,
    window: float = 1.0,
    samples: int = 5,
    reticle: bool = True,
) -> tuple[bool, dict]:
    """Pick the best thumbnail in a small time window around `seconds` and save it.

    Returns (ok, meta). `meta` carries the chosen timestamp, the match score
    (proportion of jersey-matching pixels in the largest connected region), and
    the reticle bounding box in normalised 0..1 coordinates (so the frontend
    could draw an overlay if wanted).
    """
    video_path = Path(video_path)
    out_path = Path(out_path)
    meta = {
        "picked_ts": float(seconds),
        "match_score": 0.0,
        "reticle": None,
        "window_used": float(window),
        "samples": int(samples),
        "ok": False,
    }
    if not video_path.exists():
        return False, meta

    jersey_rgb = _hex_to_rgb(getattr(fingerprint, "jersey_hex", "#888888"))
    shorts_rgb = _hex_to_rgb(getattr(fingerprint, "shorts_hex", "#888888"))

    # Sample N candidate timestamps evenly across [s-window, s+window]
    offsets = np.linspace(-window, window, max(2, samples))
    candidates = []  # (ts, frame_bgr, score, bbox)

    tmp_dir = out_path.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)

    for off in offsets:
        ts = max(0.0, float(seconds) + float(off))
        tmp_frame = tmp_dir / f".verify_{out_path.stem}_{ts:.2f}.jpg"
        ok = extract_frame_at(video_path, ts, tmp_frame)
        if not ok or not tmp_frame.exists():
            continue
        img = cv2.imread(str(tmp_frame), cv2.IMREAD_COLOR)
        try:
            tmp_frame.unlink(missing_ok=True)
        except Exception:
            pass
        if img is None or img.size == 0:
            continue

        # Combined match mask: jersey AND shorts pixels both contribute (jersey weighted higher)
        mj = _color_match_mask_bgr(img, jersey_rgb, tol=55)
        ms = _color_match_mask_bgr(img, shorts_rgb, tol=55)
        mask = (mj.astype(np.uint8) * 2) + (ms.astype(np.uint8) * 1)
        # Strict mask: pixels close to either colour
        any_match = ((mj | ms).astype(np.uint8) * 255)

        # Find connected components — biggest blob is likely the player
        n_lbl, labels, stats, _ = cv2.connectedComponentsWithStats(any_match, connectivity=8)
        if n_lbl <= 1:
            candidates.append((ts, img, 0.0, None))
            continue

        # Skip background label 0; pick the largest blob with area within plausible range
        h, w = img.shape[:2]
        total_px = float(h * w)
        best_idx = -1
        best_area = 0
        for i in range(1, n_lbl):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 200:
                continue
            # too huge => probably background (sky, pitch line); cap
            if area > total_px * 0.12:
                continue
            if area > best_area:
                best_area = area
                best_idx = i

        if best_idx < 0:
            candidates.append((ts, img, 0.0, None))
            continue

        x = int(stats[best_idx, cv2.CC_STAT_LEFT])
        y = int(stats[best_idx, cv2.CC_STAT_TOP])
        bw = int(stats[best_idx, cv2.CC_STAT_WIDTH])
        bh = int(stats[best_idx, cv2.CC_STAT_HEIGHT])

        # Score = jersey-matched pixels in box / total box area, weighted by box centrality
        sub = mask[y:y + bh, x:x + bw]
        if sub.size == 0:
            candidates.append((ts, img, 0.0, None))
            continue
        jersey_density = float((sub > 0).sum()) / float(sub.size)
        # Penalise very narrow boxes (a sliver isn't a player)
        aspect = bh / max(1, bw)
        aspect_factor = 1.0 if 1.2 <= aspect <= 4.0 else 0.55
        score = jersey_density * aspect_factor

        bbox_norm = {
            "x": x / w, "y": y / h,
            "w": bw / w, "h": bh / h,
        }
        candidates.append((ts, img, score, bbox_norm))

    if not candidates:
        # Last-resort: just dump the original timestamp frame, no reticle
        ok = extract_frame_at(video_path, float(seconds), out_path)
        meta["ok"] = ok
        return ok, meta

    # Pick best by score; if all-zero, pick centermost timestamp
    candidates.sort(key=lambda c: (c[2], -abs(c[0] - float(seconds))), reverse=True)
    best_ts, best_img, best_score, best_bbox = candidates[0]
    if best_score <= 0:
        # Just use the requested ts thumbnail, no reticle
        ok = extract_frame_at(video_path, float(seconds), out_path)
        meta["ok"] = ok
        return ok, meta

    # Draw a volt-green reticle around the matched region
    out_img = best_img.copy()
    if reticle and best_bbox:
        h, w = out_img.shape[:2]
        bx = int(best_bbox["x"] * w)
        by = int(best_bbox["y"] * h)
        bw = int(best_bbox["w"] * w)
        bh = int(best_bbox["h"] * h)
        # Slight padding outward
        pad = int(max(bw, bh) * 0.18)
        bx2 = max(0, bx - pad)
        by2 = max(0, by - pad)
        bw2 = min(w - bx2, bw + 2 * pad)
        bh2 = min(h - by2, bh + 2 * pad)
        # OpenCV uses BGR — volt #CCFF00 is RGB(204,255,0) → BGR(0,255,204)
        volt_bgr = (0, 255, 204)
        thickness = max(2, min(w, h) // 240)
        # Outer subtle halo
        cv2.rectangle(out_img, (bx2 - 2, by2 - 2), (bx2 + bw2 + 2, by2 + bh2 + 2), volt_bgr, 1)
        # Main rectangle
        cv2.rectangle(out_img, (bx2, by2), (bx2 + bw2, by2 + bh2), volt_bgr, thickness)
        # Corner ticks (L-shaped, white)
        c = min(bw2, bh2) // 5
        white = (255, 255, 255)
        for (x0, y0, dx, dy) in [
            (bx2, by2, 1, 1),
            (bx2 + bw2, by2, -1, 1),
            (bx2, by2 + bh2, 1, -1),
            (bx2 + bw2, by2 + bh2, -1, -1),
        ]:
            cv2.line(out_img, (x0, y0), (x0 + dx * c, y0), white, max(2, thickness - 1))
            cv2.line(out_img, (x0, y0), (x0, y0 + dy * c), white, max(2, thickness - 1))

    # Downscale to keep file size reasonable (max 720 wide)
    h, w = out_img.shape[:2]
    if w > 720:
        scale = 720 / w
        out_img = cv2.resize(out_img, (720, int(h * scale)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(out_path), out_img, [int(cv2.IMWRITE_JPEG_QUALITY), 88])

    meta.update({
        "picked_ts": float(best_ts),
        "match_score": float(round(best_score, 4)),
        "reticle": best_bbox,
        "ok": True,
    })
    return True, meta
