"""
Resilient ffmpeg / ffprobe binary resolvers.

The Emergent Kubernetes base image DOES NOT ship ffmpeg. In preview it also
sometimes drops the /usr/bin/ffmpeg binary on container rollout (recurring
issue documented in the handoff). To make video analysis survive both
environments, we prefer:

  1. `imageio-ffmpeg`'s bundled static ffmpeg binary (shipped as a Python
     wheel — always present after `pip install imageio-ffmpeg`).
  2. System `/usr/bin/ffmpeg` when available.

For ffprobe (NOT bundled by imageio-ffmpeg) we use a 3-tier fallback:
  1. System `/usr/bin/ffprobe`.
  2. Parse `ffmpeg -i <src>` stderr output (ffmpeg itself dumps codec/duration
     metadata to stderr on every invocation — no ffprobe needed).
  3. opencv (cv2.VideoCapture) — last-resort for duration only.

Usage:
    from media_binaries import FFMPEG_BIN, FFPROBE_BIN, get_duration_seconds,
                               probe_codec_pixfmt
    subprocess.run([FFMPEG_BIN, "-i", src, ...])
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

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


def _resolve_ffprobe() -> Optional[str]:
    """Resolve ffprobe binary path. imageio-ffmpeg does NOT bundle ffprobe,
    so we only look for the system one. Returns None if unavailable — all
    callers must use `probe_codec_pixfmt()` / `get_duration_seconds()` which
    fall back to `ffmpeg -i` stderr parsing when this is None."""
    return shutil.which("ffprobe")


FFMPEG_BIN = _resolve_ffmpeg()
_FFPROBE_RESOLVED = _resolve_ffprobe()
# Kept for backwards-compat — modules import this by name. When ffprobe is
# missing on the host the fallback helpers below still work via ffmpeg -i.
FFPROBE_BIN = _FFPROBE_RESOLVED or "ffprobe"


# ── ffmpeg -i stderr parsing helpers ────────────────────────────────────────
# ffmpeg dumps stream metadata to stderr and exits non-zero because we don't
# give it an output file. That's fine — we just want the diagnostic banner.
# Sample banner line we parse:
#   Stream #0:0(und): Video: h264 (High) (avc1 / 0x31637661), yuv420p, 1920x1080
_CODEC_LINE_RE = re.compile(
    r"Stream #\d+:\d+.*?: Video:\s*([A-Za-z0-9_]+)"     # codec (h264, hevc, vp9, …)
    r".*?,\s*([a-z0-9]+p?[0-9]*(?:le)?)",               # pix_fmt (yuv420p, yuv420p10le, …)
    re.IGNORECASE,
)
_DURATION_LINE_RE = re.compile(
    r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", re.IGNORECASE
)


def _ffmpeg_stderr_banner(video_path) -> str:
    """Run `ffmpeg -i <src>` and capture its stderr banner. ffmpeg exits with
    code 1 because no output is provided — that's expected; we only want the
    metadata dump. 6 s hard cap so pathological inputs never block."""
    try:
        r = subprocess.run(
            [FFMPEG_BIN, "-hide_banner", "-i", str(video_path)],
            capture_output=True, timeout=6, text=True,
        )
        # stderr is where ffmpeg dumps stream info even on error exit
        return (r.stderr or "") + (r.stdout or "")
    except Exception as e:
        logger.info(f"ffmpeg banner probe failed: {e}")
        return ""


def probe_codec_pixfmt(video_path) -> Tuple[str, str]:
    """Return (codec_name, pix_fmt) for the first video stream, or ('', '')
    on failure. 3-tier fallback:
      1. System ffprobe (fastest, exact CSV output).
      2. `ffmpeg -i` stderr banner parsing — works everywhere ffmpeg does.
      3. Empty tuple → caller treats it as "unknown, always re-encode".
    """
    # Tier 1: system ffprobe
    if _FFPROBE_RESOLVED:
        try:
            r = subprocess.run(
                [
                    _FFPROBE_RESOLVED, "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=codec_name,pix_fmt",
                    "-of", "csv=p=0",
                    str(video_path),
                ],
                capture_output=True, timeout=5, text=True,
            )
            if r.returncode == 0 and r.stdout.strip():
                parts = r.stdout.strip().split(",")
                return (
                    parts[0].strip().lower(),
                    (parts[1].strip().lower() if len(parts) > 1 else ""),
                )
        except Exception as e:
            logger.info(f"ffprobe direct call failed, falling back to ffmpeg -i: {e}")

    # Tier 2: parse ffmpeg -i stderr banner
    banner = _ffmpeg_stderr_banner(video_path)
    m = _CODEC_LINE_RE.search(banner)
    if m:
        codec = m.group(1).strip().lower()
        pix_fmt = m.group(2).strip().lower()
        return (codec, pix_fmt)

    # Tier 3: unknown — caller will fall through to full re-encode
    return ("", "")


def get_duration_seconds(video_path) -> float:
    """Return video duration in seconds — works with or without ffprobe.

    Try ffprobe first (fast); fall back to `ffmpeg -i` banner parsing; final
    fallback to opencv. Returns 0.0 on total failure.
    """
    # Tier 1: system ffprobe
    if _FFPROBE_RESOLVED:
        try:
            r = subprocess.run(
                [
                    _FFPROBE_RESOLVED, "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(video_path),
                ],
                capture_output=True, timeout=15, text=True,
            )
            if r.returncode == 0 and r.stdout.strip():
                return float(r.stdout.strip())
        except Exception as e:
            logger.info(f"ffprobe duration failed, falling back to ffmpeg -i: {e}")

    # Tier 2: ffmpeg -i banner
    banner = _ffmpeg_stderr_banner(video_path)
    m = _DURATION_LINE_RE.search(banner)
    if m:
        try:
            h, m_, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return h * 3600 + m_ * 60 + s
        except Exception:
            pass

    # Tier 3: opencv (imports cv2 lazily — precision_engine already loads it)
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
