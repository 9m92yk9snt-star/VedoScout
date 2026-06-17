"""
Unit tests for the Precision Scout pipeline.

Covers:
  • Visual fingerprint extraction from a synthesized marker frame
  • Audio event detection from a synthesized wav clip
  • Hedging scrubber strips weasel language
  • Prompt builders assemble priors + base prompt correctly
"""

import io
import math
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

import cv2
import numpy as np
import pytest

from precision_engine import (
    AudioEvent,
    PlayerFingerprint,
    audio_events_to_prompt_block,
    build_full_prompt,
    build_preview_prompt,
    extract_audio_events,
    extract_player_fingerprint,
    scrub_hedging,
)


# ── Fingerprint ───────────────────────────────────────────────────────


def _synthetic_marker(jersey_bgr, shorts_bgr, size=(640, 360)) -> str:
    """Render a 640x360 field-green frame with a player body at the centre."""
    w, h = size
    img = np.full((h, w, 3), (60, 90, 60), dtype=np.uint8)  # field green
    x0, y0 = int(0.45 * w), int(0.40 * h)
    x1, y1 = int(0.55 * w), int(0.80 * h)
    # Jersey (upper) — fills the top 50% of the body box
    img[y0:y0 + int(0.5 * (y1 - y0)), x0:x1] = jersey_bgr
    # Shorts (lower) — fills the bottom 40% of the body box
    img[y0 + int(0.6 * (y1 - y0)):y1, x0:x1] = shorts_bgr
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()
    cv2.imwrite(tmp.name, img)
    return tmp.name


def test_fingerprint_detects_jersey_and_shorts_colour():
    """A navy jersey + white shorts should be detected as such."""
    # OpenCV uses BGR order, but the colour-namer normalises to RGB
    path = _synthetic_marker(jersey_bgr=(140, 30, 20), shorts_bgr=(240, 240, 240))
    fp = extract_player_fingerprint(path, {"x": 0.45, "y": 0.40, "w": 0.10, "h": 0.40})
    assert fp.jersey_name in {"navy blue", "blue", "dark green"}, fp.jersey_name
    assert fp.shorts_name in {"white", "light grey"}, fp.shorts_name
    assert fp.jersey_hex.startswith("#")
    assert fp.shorts_hex.startswith("#")
    assert 1.8 < fp.body_ratio < 6.0
    Path(path).unlink(missing_ok=True)


def test_fingerprint_red_jersey_dark_shorts():
    """Red jersey + black shorts (classic AC Milan / Liverpool kit)."""
    path = _synthetic_marker(jersey_bgr=(35, 35, 200), shorts_bgr=(25, 25, 25))  # BGR red / black
    fp = extract_player_fingerprint(path, {"x": 0.45, "y": 0.40, "w": 0.10, "h": 0.40})
    assert fp.jersey_name in {"red", "dark red", "maroon"}, fp.jersey_name
    assert fp.shorts_name in {"black", "grey"}, fp.shorts_name
    Path(path).unlink(missing_ok=True)


def test_fingerprint_handles_missing_image_gracefully():
    fp = extract_player_fingerprint("/nonexistent.jpg", {"x": 0, "y": 0, "w": 0.2, "h": 0.3})
    assert fp.jersey_name == "unclear"
    assert fp.confidence == "low"


def test_fingerprint_prompt_block_mentions_jersey():
    fp = PlayerFingerprint(
        jersey_hex="#141E8C", jersey_name="navy blue",
        shorts_hex="#F0F0F0", shorts_name="white",
        body_ratio=2.3, crop_path=None, box={"x": 0, "y": 0, "w": 0.1, "h": 0.4},
        confidence="ok",
    )
    block = fp.to_prompt_block()
    assert "LOCKED PLAYER FINGERPRINT" in block
    assert "navy blue" in block
    assert "white" in block
    assert "2.30" in block
    assert "OFF-CAMERA" in block  # tells the AI what to do when it can't see the player


# ── Audio events ──────────────────────────────────────────────────────


def _synth_wav(duration_s: float, sr: int = 16000, peak_at_s: float | None = None) -> str:
    """Write a mono wav file. If peak_at_s is set, insert a loud 0.5s burst there."""
    n = int(duration_s * sr)
    data = (np.random.randn(n) * 0.02).astype(np.float32)  # quiet noise floor
    if peak_at_s is not None:
        i0 = int(peak_at_s * sr)
        i1 = min(n, i0 + int(0.5 * sr))
        # 0.5 sec burst at amplitude ~0.6 (cheer-like)
        t = np.arange(i1 - i0) / sr
        burst = 0.6 * (np.sin(2 * np.pi * 800 * t) + np.sin(2 * np.pi * 1100 * t)) / 2.0
        data[i0:i1] += burst.astype(np.float32)
    data = np.clip(data, -1.0, 1.0)
    pcm = (data * 32767).astype(np.int16)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    with wave.open(tmp.name, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return tmp.name


def _wav_to_mp4(wav_path: str) -> str:
    """Wrap a wav into a tiny mp4 so extract_audio_events can run ffmpeg on it."""
    mp4 = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    mp4.close()
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=64x64:d=10",
            "-i", wav_path,
            "-c:v", "libx264", "-c:a", "aac",
            "-shortest", mp4.name,
        ],
        check=True,
        timeout=60,
    )
    return mp4.name


def test_audio_events_picks_up_loud_burst():
    wav = _synth_wav(10.0, peak_at_s=5.0)
    mp4 = _wav_to_mp4(wav)
    try:
        events = extract_audio_events(mp4, top_n=3)
        # The burst lands around the 5s mark — we should pick it up
        assert any(4.0 <= e.t <= 6.0 for e in events), f"expected a peak near 5s, got {events}"
    finally:
        Path(wav).unlink(missing_ok=True)
        Path(mp4).unlink(missing_ok=True)


def test_audio_events_empty_for_silent_clip():
    wav = _synth_wav(5.0, peak_at_s=None)
    mp4 = _wav_to_mp4(wav)
    try:
        events = extract_audio_events(mp4, top_n=3)
        # Pure-noise clip — every "peak" is essentially the same as the median, so we
        # might still get one or two false positives, but should be a small number.
        assert len(events) <= 2, f"silent clip produced too many spikes: {events}"
    finally:
        Path(wav).unlink(missing_ok=True)
        Path(mp4).unlink(missing_ok=True)


def test_audio_events_prompt_block_lists_timestamps():
    events = [AudioEvent(t=12.3, peak_db=6.1, kind="loud_event")]
    block = audio_events_to_prompt_block(events)
    assert "12.30s" in block
    assert "+6.1 dB" in block

    empty_block = audio_events_to_prompt_block([])
    assert "no significant audio peaks" in empty_block


# ── Hedging scrubber ──────────────────────────────────────────────────


def test_scrub_strips_hedging_words():
    inp = {
        "summary": "Almin appears to be a smart playmaker who seems to scan well.",
        "evidence_note": "Likely 3 touches were observed. Probably a good clip.",
        "nested": {"deep": "He might have scored possibly from the box."},
    }
    out = scrub_hedging(inp)
    text = out["summary"] + " " + out["evidence_note"] + " " + out["nested"]["deep"]
    for banned in ("appears to", "seems to", "likely", "probably", "possibly", "might have"):
        assert banned not in text.lower(), f"hedge word survived: {banned} in {text}"


def test_scrub_preserves_normal_text():
    inp = "Almin scored at 0:34 from inside the box."
    assert scrub_hedging(inp) == inp


def test_scrub_handles_lists_and_numbers():
    inp = ["He appears to be fast.", 7, None, {"foo": "Probably yes."}]
    out = scrub_hedging(inp)
    assert "appears to" not in out[0].lower()
    assert out[1] == 7
    assert out[2] is None
    assert "probably" not in out[3]["foo"].lower()


# ── Prompt assembly ───────────────────────────────────────────────────


def test_preview_prompt_includes_priors_and_voice_rules():
    fp = PlayerFingerprint(
        jersey_hex="#141E8C", jersey_name="navy blue",
        shorts_hex="#F0F0F0", shorts_name="white",
        body_ratio=2.3, crop_path=None, box={}, confidence="ok",
    )
    base = "PLAYER DETAILS\n{player_details}\nCONTENT: {content_type}\nVIS: {player_visible}\nDIST: {camera_distance}"
    prompt = build_preview_prompt(
        base_prompt=base,
        fingerprint=fp,
        audio_events=[AudioEvent(t=8.0, peak_db=5.2, kind="loud_event")],
        player_details={"player_name": "Almin", "age": 14},
        content_type="full_match",
        player_visible="clear",
        camera_distance="medium",
    )
    assert "LOCKED PLAYER FINGERPRINT" in prompt
    assert "navy blue" in prompt
    assert "8.00s" in prompt
    assert "CONFIDENT VOICE ONLY" in prompt
    assert "Almin" in prompt
    assert "full_match" in prompt


def test_full_prompt_does_not_leave_placeholder_braces():
    fp = PlayerFingerprint(
        jersey_hex="#FFFFFF", jersey_name="white",
        shorts_hex="#000000", shorts_name="black",
        body_ratio=2.0, crop_path=None, box={}, confidence="ok",
    )
    base = "X{player_details}Y{content_type}Z{quality}A{player_visible}B{camera_distance}C{games_detected}D"
    prompt = build_full_prompt(
        base_prompt=base,
        fingerprint=fp,
        audio_events=[],
        player_details={"foo": "bar"},
        content_type="training",
        quality="good",
        player_visible="clear",
        camera_distance="far",
        games_detected=2,
    )
    assert "{player_details}" not in prompt
    assert "{content_type}" not in prompt
    assert "{games_detected}" not in prompt
    assert '"foo": "bar"' in prompt
    assert "training" in prompt
    assert "2" in prompt
