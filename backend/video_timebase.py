"""FIX 03 — canonical video timebase helpers.

Canonical time = the source/processed video's wall-clock MEDIA time
(PTS via OpenCV CAP_PROP_POS_MSEC) in seconds/milliseconds. Uploaded phone
video may be VFR: frame_index/fps arithmetic is NEVER authoritative — it is
only an explicit, clearly marked last resort when a backend reports no usable
media time. Zero new dependencies, zero model calls, deterministic.
"""
from __future__ import annotations

import cv2


def seek_seconds(cap, seconds: float) -> None:
    """Seek by canonical media time (never CAP_PROP_POS_FRAMES)."""
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(seconds)) * 1000.0)


def seek_ms(cap, ms: float) -> None:
    """Seek by canonical media time in milliseconds."""
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(ms)))


def frame_time_or_fallback(pos_ms, frame_index, fps):
    """(seconds, used_fallback) — pure decision core.

    POS_MSEC (PTS media time) is authoritative. 0.0 is a valid time only for
    the very first frame; otherwise a non-positive report means the backend
    gave no usable media time and the EXPLICIT last resort frame_index/fps
    is used (flagged True)."""
    if isinstance(pos_ms, (int, float)) and not isinstance(pos_ms, bool):
        if pos_ms > 0.0 or (pos_ms == 0.0 and (frame_index or 0) <= 0):
            return float(pos_ms) / 1000.0, False
    f = float(fps) if fps and float(fps) > 0 else 0.0
    return ((float(frame_index or 0) / f) if f else 0.0), True


def next_frame_time_seconds(cap, fps=None):
    """(seconds, used_fallback) for the frame the next read()/grab() returns.

    Query BEFORE decoding: CAP_PROP_POS_MSEC reports the media position of
    the upcoming frame. Falls back explicitly to POS_FRAMES/fps only when the
    backend reports no usable media time."""
    ms = cap.get(cv2.CAP_PROP_POS_MSEC)
    idx = cap.get(cv2.CAP_PROP_POS_FRAMES)
    return frame_time_or_fallback(ms, idx, fps)


def read_frame_at(cap, seconds: float, fps=None):
    """Canonical-time random access: seek by media time, decode one frame.
    Returns (ok, frame_or_None, actual_media_seconds)."""
    seek_seconds(cap, seconds)
    t, _fb = next_frame_time_seconds(cap, fps)
    ok, frame = cap.read()
    return ok, (frame if ok else None), t


def should_sample(t, prev_sample_t, interval) -> bool:
    """HZ sampling by ELAPSED MEDIA TIME between samples — never frame count."""
    return prev_sample_t is None or (t - prev_sample_t) >= interval - 1e-6


def sample_dt(t, prev_sample_t, interval) -> float:
    """Real media-time delta between processed samples (physics dt)."""
    return (t - prev_sample_t) if prev_sample_t is not None else float(interval)


def media_duration_seconds(video_path):
    """Authoritative media duration via the existing ffprobe→ffmpeg→opencv
    chain in media_binaries (no new probe implementation). Returns None when
    unavailable so callers apply their own explicit last-resort fallback."""
    try:
        from media_binaries import get_duration_seconds
        d = float(get_duration_seconds(str(video_path)) or 0.0)
        return d if d > 0 else None
    except Exception:
        return None
