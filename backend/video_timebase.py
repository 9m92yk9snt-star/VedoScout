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

    pos_ms must be the POS_MSEC value read AFTER grab()/decode — OpenCV/FFmpeg
    bases it on picture_pts, which is only established by the grabbed frame.
    0.0 is a valid time only for the very first frame; otherwise a
    non-positive report means the backend gave no usable media time and the
    EXPLICIT last resort frame_index/fps is used (flagged True)."""
    if isinstance(pos_ms, (int, float)) and not isinstance(pos_ms, bool):
        if pos_ms > 0.0 or (pos_ms == 0.0 and (frame_index or 0) <= 0):
            return float(pos_ms) / 1000.0, False
    f = float(fps) if fps and float(fps) > 0 else 0.0
    return ((float(frame_index or 0) / f) if f else 0.0), True


def grab_frame_time_seconds(cap, fps=None):
    """Sequential decoding step: grab() the next frame, THEN read its media
    timestamp. Returns (ok, seconds, used_fallback) for the grabbed frame;
    the caller may retrieve() to obtain that exact frame.

    Contract (OpenCV/FFmpeg): CAP_PROP_POS_MSEC is picture_pts, established
    by the grabbed/decoded frame — never assign a pre-grab timestamp to a
    post-grab frame."""
    if not cap.grab():
        return False, 0.0, False
    ms = cap.get(cv2.CAP_PROP_POS_MSEC)
    idx = cap.get(cv2.CAP_PROP_POS_FRAMES)  # position AFTER grab = next index
    grabbed_index = int(idx) - 1 if idx and idx > 0 else 0
    t, fb = frame_time_or_fallback(ms, grabbed_index, fps)
    return True, t, fb


def read_frame_at(cap, seconds: float, fps=None, max_forward: int = 240):
    """Canonical random access: seek by media time, then decode FORWARD until
    the first frame whose ACTUAL PTS reaches T (a container seek may land on
    an earlier keyframe). Returns (ok, frame_or_None, actual_media_seconds)
    — the timestamp of the frame actually used, never the requested T."""
    target = max(0.0, float(seconds))
    seek_seconds(cap, target)
    last_t = None
    for _ in range(max_forward):
        ok, t, _fb = grab_frame_time_seconds(cap, fps)
        if not ok:
            break
        last_t = t
        if t >= target - 1e-3:
            ok2, frame = cap.retrieve()
            return ok2, (frame if ok2 else None), t
    return False, None, (last_t if last_t is not None else target)


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
