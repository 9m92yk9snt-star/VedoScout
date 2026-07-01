"""
Resilient ffmpeg / ffprobe binary resolvers.

The Emergent Kubernetes base image DOES NOT ship ffmpeg. In preview it also
sometimes drops the /usr/bin/ffmpeg binary on container rollout (recurring
issue documented in the handoff). To make video analysis survive both
environments, we prefer:

  1. `imageio-ffmpeg`'s bundled static ffmpeg binary (shipped as a Python
     wheel — always present after `pip install imageio-ffmpeg`).
  2. System `/usr/bin/ffmpeg` when available.

For ffprobe (not bundled by imageio-ffmpeg), we fall back to:
  1. System `/usr/bin/ffprobe`.
  2. Duration extraction via opencv (cv2.VideoCapture) — see get_duration_seconds().

Usage:
    from media_binaries import FFMPEG_BIN, FFPROBE_BIN, get_duration_seconds
    subprocess.run([FFMPEG_BIN, "-i", src, ...])
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _resolve_ffmpeg() -> str:
    """Resolve ffmpeg binary path. Prefers imageio-ffmpeg's bundled static
    binary over the system one — guarantees availability on deployment."""
    try:
        import imageio_ffmpeg  # type: ignore
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).exists():
            return bundled
    except Exception as e:
        logger.warning(f"imageio-ffmpeg not available: {e}")
    system = shutil.which("ffmpeg")
    if system:
        return system
    # Last-resort: return "ffmpeg" — subprocess will raise FileNotFoundError
    # which callers already handle. This keeps behaviour predictable.
    return "ffmpeg"


def _resolve_ffprobe() -> str:
    """Resolve ffprobe binary path. imageio-ffmpeg does NOT bundle ffprobe,
    so we only look for the system one. Callers should also implement a
    non-ffprobe fallback (e.g. opencv-based duration)."""
    system = shutil.which("ffprobe")
    if system:
        return system
    return "ffprobe"


FFMPEG_BIN = _resolve_ffmpeg()
FFPROBE_BIN = _resolve_ffprobe()


def get_duration_seconds(video_path) -> float:
    """Return video duration in seconds — works with or without ffprobe.

    Try ffprobe first (fast); fall back to opencv (already imported by
    precision_engine, so no extra runtime cost) if ffprobe is unavailable.
    Returns 0.0 on total failure.
    """
    import subprocess
    # Attempt 1: ffprobe (fast, exact)
    try:
        r = subprocess.run(
            [
                FFPROBE_BIN, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True, timeout=15, text=True,
        )
        if r.returncode == 0 and r.stdout.strip():
            return float(r.stdout.strip())
    except Exception as e:
        logger.info(f"ffprobe unavailable, falling back to opencv: {e}")

    # Attempt 2: opencv (imports cv2 lazily — precision_engine already loads it)
    try:
        import cv2  # type: ignore
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return 0.0
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        cap.release()
        if fps > 0 and frame_count > 0:
            return float(frame_count) / float(fps)
    except Exception as e:
        logger.warning(f"opencv duration fallback failed: {e}")

    return 0.0
