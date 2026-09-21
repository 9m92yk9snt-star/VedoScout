"""Tests for verify_and_pick_thumbnail in precision_engine.

These tests cover:
 1. graceful failure when video is missing
 2. graceful "no match" fallback to centre timestamp
 3. happy path on a synthetic video where the player's jersey is the
    dominant colour in only one frame of a 5-frame window — that frame
    must be picked and the reticle bbox must be non-null.
"""

from __future__ import annotations
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from precision_engine import (
    PlayerFingerprint,
    verify_and_pick_thumbnail,
)


def _make_fingerprint(jersey_hex="#FF2000", shorts_hex="#000080"):
    return PlayerFingerprint(
        jersey_hex=jersey_hex,
        jersey_name="red",
        shorts_hex=shorts_hex,
        shorts_name="navy",
        body_ratio=2.2,
        crop_path=None,
        box={"x": 0.4, "y": 0.2, "w": 0.2, "h": 0.6},
        confidence="ok",
    )


def _make_synthetic_video(out_path: Path, target_frame_idx: int = 2) -> bool:
    """Generate a 5-frame video where only `target_frame_idx` contains the red jersey.

    Each frame is a 640x360 image:
      - background = green grass
      - all frames: 3 grey rectangles representing teammates
      - target frame: one extra red rectangle (jersey) + navy below (shorts)
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Build frames as PNGs then ffmpeg-stitch them into a 5fps mp4
    tmp_dir = out_path.parent / f"_frames_{out_path.stem}"
    tmp_dir.mkdir(exist_ok=True)
    try:
        for i in range(5):
            img = np.zeros((360, 640, 3), dtype=np.uint8)
            img[:, :] = (40, 90, 30)  # BGR grass (forest-green-ish)
            # 3 grey teammates
            for k, x in enumerate((80, 280, 480)):
                cv2.rectangle(img, (x, 200), (x + 40, 320), (140, 140, 140), -1)
            if i == target_frame_idx:
                # Red jersey + navy shorts in centre
                cv2.rectangle(img, (300, 160), (340, 240), (0, 32, 255), -1)  # BGR red
                cv2.rectangle(img, (300, 240), (340, 320), (128, 0, 0), -1)   # BGR navy
            cv2.imwrite(str(tmp_dir / f"{i:03d}.png"), img)

        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-framerate", "5",
            "-i", str(tmp_dir / "%03d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-vf", "format=yuv420p",
            str(out_path),
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=30)
        return r.returncode == 0 and out_path.exists()
    finally:
        for f in tmp_dir.glob("*.png"):
            try:
                f.unlink()
            except Exception:
                pass
        try:
            tmp_dir.rmdir()
        except Exception:
            pass


def test_verify_thumb_missing_video(tmp_path):
    out_path = tmp_path / "thumb.jpg"
    fp = _make_fingerprint()
    ok, meta = verify_and_pick_thumbnail(
        tmp_path / "nope.mp4", 1.0, fp, out_path,
    )
    assert ok is False
    assert meta["ok"] is False


def test_verify_thumb_picks_red_jersey_frame(tmp_path):
    """The red jersey only appears on frame index 2 (t=0.4s @ 5fps). With a
    window of ±0.5s around t=0.4s we sample all 5 frames; the function must
    pick the red one and return a reticle bbox.
    """
    video = tmp_path / "synth.mp4"
    if not _make_synthetic_video(video, target_frame_idx=2):
        pytest.skip("ffmpeg failed to encode synthetic video")
    out_path = tmp_path / "thumb_picked.jpg"
    fp = _make_fingerprint()
    ok, meta = verify_and_pick_thumbnail(
        video, 0.4, fp, out_path, window=0.5, samples=5,
    )
    assert ok is True
    assert meta["ok"] is True
    assert out_path.exists()
    # Reticle must be present (non-None) and inside [0,1]
    assert meta["reticle"] is not None
    rx = meta["reticle"]
    for k in ("x", "y", "w", "h"):
        assert 0.0 <= rx[k] <= 1.0
    # match_score should be positive
    assert meta["match_score"] > 0.0


def test_verify_thumb_no_match_falls_back(tmp_path):
    """When the jersey colour appears NOWHERE in the window, the function must
    still produce a file (using the original timestamp frame) and meta.ok==True
    BUT meta.reticle stays None and match_score stays 0.
    """
    video = tmp_path / "synth2.mp4"
    # target_frame_idx=99 → red jersey never appears in any of 5 frames
    if not _make_synthetic_video(video, target_frame_idx=99):
        pytest.skip("ffmpeg failed to encode synthetic video")
    out_path = tmp_path / "thumb_nomatch.jpg"
    fp = _make_fingerprint()
    ok, meta = verify_and_pick_thumbnail(
        video, 0.4, fp, out_path, window=0.5, samples=5,
    )
    # File should still be created (fallback to plain extract_frame_at)
    assert ok is True
    assert out_path.exists()
    # No reticle since nothing matched
    assert meta["reticle"] is None
    assert meta["match_score"] == 0.0
