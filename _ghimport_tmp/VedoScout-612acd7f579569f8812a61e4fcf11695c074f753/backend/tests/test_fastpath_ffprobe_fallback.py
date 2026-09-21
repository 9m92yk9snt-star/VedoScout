"""Regression test for Session 128 — Step 2 "Preparing the footage" hang.

The bug: `_probe_video_codec` in server.py called raw `FFPROBE_BIN` and
returned `("", "")` when ffprobe was missing on the host (Emergent K8s base
image ships no ffprobe). Fast-path check in `transcode_to_web_mp4` then
falls through to a full re-encode which hangs for 8+ min on production for
1:20 clips.

Fix: `probe_codec_pixfmt()` in media_binaries.py now has a 3-tier fallback:
  1. System ffprobe
  2. Parse `ffmpeg -i` stderr banner
  3. Empty tuple (caller re-encodes)

This test ensures tier-2 works on any host where the bundled imageio-ffmpeg
is available — which is the guaranteed production configuration.

Run with:
    cd /app/backend && python -m pytest tests/test_fastpath_ffprobe_fallback.py -v
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from media_binaries import (  # noqa: E402
    FFMPEG_BIN,
    get_duration_seconds,
    probe_codec_pixfmt,
)


def _make_test_mp4(tmp_path: Path) -> Path:
    """Synthesize a 1s H.264/yuv420p mp4 using the bundled ffmpeg."""
    out = tmp_path / "test.mp4"
    subprocess.run(
        [
            FFMPEG_BIN, "-y", "-f", "lavfi",
            "-i", "testsrc=duration=1:size=320x240:rate=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-loglevel", "error",
            str(out),
        ],
        check=True, capture_output=True, timeout=30,
    )
    assert out.exists() and out.stat().st_size > 0
    return out


def test_probe_codec_pixfmt_returns_h264_yuv420p(tmp_path):
    """Fast-path key check — codec/pix_fmt detection must NOT return ('','')."""
    mp4 = _make_test_mp4(tmp_path)
    codec, pix_fmt = probe_codec_pixfmt(mp4)
    assert codec == "h264", f"expected h264, got {codec!r}"
    assert pix_fmt in ("yuv420p", "yuvj420p"), f"expected yuv420p*, got {pix_fmt!r}"


def test_probe_codec_pixfmt_survives_missing_ffprobe(tmp_path, monkeypatch):
    """Force the ffprobe path off and confirm ffmpeg -i banner fallback works."""
    import media_binaries as mb
    monkeypatch.setattr(mb, "_FFPROBE_RESOLVED", None)
    mp4 = _make_test_mp4(tmp_path)
    codec, pix_fmt = mb.probe_codec_pixfmt(mp4)
    assert codec == "h264"
    assert pix_fmt in ("yuv420p", "yuvj420p")


def test_get_duration_seconds_survives_missing_ffprobe(tmp_path, monkeypatch):
    import media_binaries as mb
    monkeypatch.setattr(mb, "_FFPROBE_RESOLVED", None)
    mp4 = _make_test_mp4(tmp_path)
    dur = mb.get_duration_seconds(mp4)
    assert 0.5 < dur < 2.0, f"expected ~1s, got {dur}s"


def test_fastpath_short_circuits_when_already_web_safe(tmp_path):
    """Import server.transcode_to_web_mp4 and verify a fresh h264/yuv420p mp4
    triggers the fast-path (returns quickly, doesn't re-encode)."""
    import time
    from server import transcode_to_web_mp4
    mp4 = _make_test_mp4(tmp_path)
    t0 = time.monotonic()
    out = transcode_to_web_mp4(mp4)
    elapsed = time.monotonic() - t0
    assert out.exists()
    # Fast-path is just a shutil.copy2, must complete in < 1s
    assert elapsed < 1.0, f"fast-path took {elapsed:.2f}s — probably re-encoded"
    assert out.name.endswith(".web.mp4")
