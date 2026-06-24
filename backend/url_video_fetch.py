"""
url_video_fetch.py — fetch a video from a public URL (YouTube, Vimeo, Veo, direct MP4)
into the standard `UPLOAD_DIR` so the rest of the upload pipeline can consume it
identically to a file-upload.

Self-contained — no imports from server.py. Call `build_url_fetch_router(...)`
from server.py and include the returned router.

Returns a temp token + preview_url; the existing `/reports/upload` endpoint
should accept that token as an alternative to a file upload.
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
import shutil
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, AnyHttpUrl

log = logging.getLogger("url_video_fetch")

# Soft caps to keep the server healthy
MAX_BYTES = 200 * 1024 * 1024  # 200 MB
DOWNLOAD_TIMEOUT_SEC = 120

ALLOWED_DOMAINS_HINT = (
    "Most public video URLs work: Vimeo, Hudl public shares, "
    "Google Drive shared links, or any direct .mp4 / .mov / .webm URL. "
    "YouTube downloads from our servers are currently blocked by YouTube — "
    "please use one of the alternatives above or upload the file directly. "
    "Veo match recordings are typically several GB and longer than our "
    "5-minute analysis window — please download a short clip from Veo "
    "(Open clip → ⋯ → Download) and upload the MP4 directly."
)


class UrlFetchRequest(BaseModel):
    url: AnyHttpUrl = Field(description="Public URL to a video (Vimeo, Google Drive, direct MP4, …).")


# ---- Domain detection -----------------------------------------------------
_YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "m.youtube.com", "music.youtube.com")
# Veo clip URLs (`app.veo.co/clubs/<club>/clips/<uuid>/`) are NOT supported by
# yt-dlp's Veo extractor (only `/matches/<slug>/`). Veo match recordings are
# also typically 4+ GB / 90-min long — well above our 200 MB / 5-min caps.
# Detect both patterns up-front so we can give a precise, actionable error
# instead of a cryptic yt-dlp "Unsupported URL" or "file not found on disk".
_VEO_CLIP_RX = re.compile(r"^https?://app\.veo\.co/clubs/[^/]+/clips/", re.IGNORECASE)
_VEO_MATCH_RX = re.compile(r"^https?://app\.veo\.co/matches/", re.IGNORECASE)


def _is_youtube(url: str) -> bool:
    u = url.lower()
    return any(h in u for h in _YOUTUBE_HOSTS)


def _veo_help_message() -> str:
    """The one piece of copy users see when they paste a Veo URL we can't
    actually deliver through the pipeline. Keep it concrete and actionable."""
    return (
        "Veo links can't be fetched directly — full matches are several GB. "
        "On Veo, open the clip → ⋯ → Download to save the MP4 to your device, "
        "then use the 'Upload File' tab here. Max 5 min / 200 MB."
    )


def _friendly_error(url: str, raw_msg: str) -> str:
    """Translate a raw yt-dlp error into a user-friendly message.
    YouTube's cloud-IP block is the most common failure in 2026."""
    msg = (raw_msg or "").lower()
    if _is_youtube(url) and (
        "sign in to confirm" in msg
        or "not a bot" in msg
        or "http error 403" in msg
        or "cookies" in msg
        or "no video formats" in msg
        or "drm protected" in msg
    ):
        return (
            "YouTube is currently blocking downloads from our servers (this is a "
            "YouTube-wide issue, not your account). "
            "Please use one of these instead: a Veo or Vimeo link, a Google Drive "
            "shared link (anyone-with-link), a direct .mp4 / .mov URL, or simply "
            "upload the file from your phone or computer."
        )
    if "drm" in msg:
        return "This video is DRM-protected and can't be downloaded. Please upload the file directly."
    if "private" in msg or "login required" in msg or "members" in msg:
        return "This video is private or members-only. Make it public or share a direct download link."
    if "404" in msg or "not found" in msg:
        return "We couldn't find a video at that URL. Check the link is public and complete."
    if "geo" in msg or "country" in msg:
        return "This video is geo-restricted and can't be downloaded from our region."
    if "too large" in msg or "max_filesize" in msg or "filesize" in msg:
        return "That video is larger than our 200 MB limit. Please upload a shorter clip."
    if not raw_msg:
        return "Could not download that video."
    # Generic — keep first 180 chars of yt-dlp's own message
    return f"Could not download that video: {raw_msg[:180]}"


def _safe_size(p: Path) -> int:
    try:
        return p.stat().st_size
    except FileNotFoundError:
        return 0


def _ensure_below_cap(p: Path):
    sz = _safe_size(p)
    if sz > MAX_BYTES:
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(413, f"Video too large ({sz // (1024*1024)} MB). Maximum allowed is 200 MB.")


def _download_with_ytdlp(url: str, target_dir: Path, token: str) -> Path:
    """Use yt-dlp to download to target_dir. Returns final path.

    2026 notes:
      - Uses an `ImpersonateTarget('chrome')` (via curl_cffi) so Vimeo / Veo /
        Google Drive / direct MP4 hosts that fingerprint TLS still serve us.
      - Adds a YouTube player_client fallback chain — the more clients tried, the
        higher chance one of them yields a non-blocked format URL. (YouTube is
        actively blocking server-side IPs from receiving the actual video bytes;
        if every client fails we surface a friendly error pointing to alternatives.)"""
    import yt_dlp  # local import — keeps server start cheap
    from yt_dlp.networking.impersonate import ImpersonateTarget

    outtmpl = str(target_dir / f"url-fetch-{token}.%(ext)s")
    youtube_clients = ["default", "web_safari", "mweb", "android", "ios", "tv"]

    # Prefer mp4 ≤720p; allow DASH (video+audio merge); fall back to anything
    ydl_opts = {
        "outtmpl": outtmpl,
        "format": (
            "bv*[height<=720][protocol!*=m3u8]+ba/"
            "b[ext=mp4][height<=720]/"
            "b[height<=720]/"
            "b"
        ),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "max_filesize": MAX_BYTES,
        "retries": 2,
        "fragment_retries": 2,
        "socket_timeout": 30,
        "merge_output_format": "mp4",
        "concurrent_fragment_downloads": 1,
        # ImpersonateTarget — curl_cffi-backed TLS fingerprint spoofing
        "impersonate": ImpersonateTarget("chrome"),
        "extractor_args": {
            "youtube": {
                "player_client": youtube_clients,
            },
        },
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            candidate = ydl.prepare_filename(info)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(400, _friendly_error(url, str(e)))
    except Exception as e:
        raise HTTPException(500, _friendly_error(url, str(e)))

    final = Path(candidate)
    if not final.exists():
        # yt-dlp sometimes mutates the extension after merge — discover the real one
        for ext in ("mp4", "mkv", "webm", "mov"):
            cand = target_dir / f"url-fetch-{token}.{ext}"
            if cand.exists():
                final = cand
                break
    if not final.exists():
        raise HTTPException(500, "Video downloaded but final file not found on disk.")

    # Normalise to .mp4 extension for the rest of the pipeline (rename only — no transcode)
    if final.suffix.lower() != ".mp4":
        normalised = target_dir / f"url-fetch-{token}.mp4"
        try:
            shutil.move(str(final), str(normalised))
            final = normalised
        except Exception:
            pass

    _ensure_below_cap(final)
    return final


def build_url_fetch_router(*, upload_dir: Path, get_current_user) -> APIRouter:
    router = APIRouter(tags=["uploads"])

    @router.post("/me/url-fetch")
    async def fetch_video_by_url(payload: UrlFetchRequest, user=Depends(get_current_user)):
        url = str(payload.url).strip()
        if len(url) > 1200:
            raise HTTPException(400, "URL is too long.")

        # ── Veo-specific pre-check ───────────────────────────────────────
        # Both Veo URL variants (clip share URLs and full match URLs) end
        # up un-deliverable through our pipeline — clip URLs aren't in the
        # yt-dlp extractor at all, and match URLs resolve to multi-GB
        # 90-minute panoramic recordings that always exceed our 200 MB /
        # 5-min caps. Tell the user exactly what to do instead of
        # exposing the cryptic upstream error.
        if _VEO_CLIP_RX.match(url) or _VEO_MATCH_RX.match(url):
            raise HTTPException(400, _veo_help_message())

        # Per-user temp namespace so we can clean up later if we want
        token = uuid.uuid4().hex
        target_dir = upload_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        # Run blocking yt-dlp in a thread with a hard timeout
        try:
            final = await asyncio.wait_for(
                asyncio.to_thread(_download_with_ytdlp, url, target_dir, token),
                timeout=DOWNLOAD_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            raise HTTPException(504, "Video download timed out (limit 120s). Try a shorter clip or upload directly.")

        size_mb = round(_safe_size(final) / (1024 * 1024), 2)
        # Filename to surface in the UI
        m = re.search(r"([^/\\\?#]+)\.(mp4|mov|mkv|webm|m4v)(?:[?#].*)?$", url, re.IGNORECASE)
        display_name = m.group(0) if m else f"video-from-url-{token[:6]}.mp4"

        return {
            "token": token,
            "filename": display_name,
            "size_mb": size_mb,
            "preview_url": f"/api/uploads/{final.name}",
            "stored_filename": final.name,
        }

    return router


def resolve_temp_token_path(*, upload_dir: Path, token: str) -> Optional[Path]:
    """Look up a previously-fetched temp video by token. Used by /reports/upload."""
    if not token:
        return None
    safe = re.sub(r"[^a-f0-9]", "", token.lower())
    if not safe or len(safe) < 8:
        return None
    for ext in ("mp4", "mkv", "webm", "mov", "m4v"):
        candidate = upload_dir / f"url-fetch-{safe}.{ext}"
        if candidate.exists():
            return candidate
    return None
