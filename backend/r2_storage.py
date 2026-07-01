"""
Cloudflare R2 object storage helpers.

Uses boto3 with the S3-compatible R2 endpoint. Files are addressed by an
"object key" (e.g. "demo_videos/abc123.web.mp4"). MongoDB stores the key,
and the resolver builds the public URL at read-time via `public_url(key)`.

Env vars (from /app/backend/.env):
    R2_ACCESS_KEY_ID
    R2_SECRET_ACCESS_KEY
    R2_ENDPOINT           https://<account>.r2.cloudflarestorage.com
    R2_BUCKET             e.g. "scoutmeplay"
    R2_PUBLIC_URL         e.g. "https://storage.scoutmeplay.com"

If R2_* are not all set, `is_configured()` returns False and callers should
fall back to local disk storage.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger(__name__)


def _cfg():
    """Read env vars lazily. r2_storage is imported before server.py's
    load_dotenv() runs, so we can't read them at module-import time."""
    return {
        "access_key": os.environ.get("R2_ACCESS_KEY_ID"),
        "secret_key": os.environ.get("R2_SECRET_ACCESS_KEY"),
        "endpoint": (os.environ.get("R2_ENDPOINT") or "").rstrip("/"),
        "bucket": os.environ.get("R2_BUCKET"),
        "public_url": (os.environ.get("R2_PUBLIC_URL") or "").rstrip("/"),
    }


# Kept for backward-compat / debug logging — DO NOT reference in code paths
# that run before load_dotenv() finishes.
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY")
R2_ENDPOINT = (os.environ.get("R2_ENDPOINT") or "").rstrip("/")
R2_BUCKET = os.environ.get("R2_BUCKET")
R2_PUBLIC_URL = (os.environ.get("R2_PUBLIC_URL") or "").rstrip("/")

_client = None


def is_configured() -> bool:
    """True when all R2 env vars are set. Callers should check this before
    using r2_storage helpers and fall back to local disk if False."""
    c = _cfg()
    return bool(c["access_key"] and c["secret_key"] and c["endpoint"] and c["bucket"] and c["public_url"])


def _get_client():
    global _client
    if _client is None:
        c = _cfg()
        _client = boto3.client(
            "s3",
            endpoint_url=c["endpoint"],
            aws_access_key_id=c["access_key"],
            aws_secret_access_key=c["secret_key"],
            region_name="auto",  # R2 uses "auto" — required by boto3 signature
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
                s3={"addressing_style": "path"},  # R2 requires path-style addressing
            ),
        )
    return _client


def _bucket() -> str:
    return _cfg()["bucket"]


def public_url(key: str) -> str:
    """Return the public URL for a given object key.

    If R2_PUBLIC_URL starts with "/" it's a backend-relative path (proxy mode):
    the backend streams the object at that endpoint (see server.py
    `/api/media/{key:path}`). Otherwise it's a full HTTPS URL (e.g. custom
    domain or pub-*.r2.dev subdomain — object is served directly by R2).
    """
    base = _cfg()["public_url"]
    return f"{base}/{key.lstrip('/')}"


def get_stream(key: str, range_header: Optional[str] = None):
    """Fetch an object from R2 as a streaming body. Supports HTTP Range requests
    for video seeking. Returns the boto3 GetObject response dict — caller streams
    response["Body"] chunks back to the client and forwards ContentLength /
    ContentRange / ContentType headers.
    """
    kwargs = {"Bucket": _bucket(), "Key": key}
    if range_header:
        kwargs["Range"] = range_header
    return _get_client().get_object(**kwargs)


def upload_file(key: str, local_path: Path, content_type: str, cache_seconds: int = 31536000) -> str:
    """Upload a local file to R2. Returns the public URL.

    cache_seconds defaults to 1 year — content is immutable (URLs contain a
    UUID), so long-cache is safe and reduces R2 Class B ops.
    """
    client = _get_client()
    extra = {
        "ContentType": content_type,
        "CacheControl": f"public, max-age={cache_seconds}, immutable",
    }
    with open(local_path, "rb") as f:
        client.upload_fileobj(f, _bucket(), key, ExtraArgs=extra)
    return public_url(key)


def upload_bytes(key: str, data: bytes, content_type: str, cache_seconds: int = 31536000) -> str:
    client = _get_client()
    client.put_object(
        Bucket=_bucket(),
        Key=key,
        Body=data,
        ContentType=content_type,
        CacheControl=f"public, max-age={cache_seconds}, immutable",
    )
    return public_url(key)


def delete_object(key: str) -> bool:
    """Delete an object. Returns True on success, False if it doesn't exist or fails."""
    try:
        _get_client().delete_object(Bucket=_bucket(), Key=key)
        return True
    except (ClientError, BotoCoreError) as e:
        logger.warning(f"R2 delete failed key={key}: {e}")
        return False


def download_to_file(key: str, dest_path: Path) -> bool:
    """Download an object from R2 to a local file (for ffmpeg processing)."""
    try:
        _get_client().download_file(_bucket(), key, str(dest_path))
        return True
    except (ClientError, BotoCoreError) as e:
        logger.warning(f"R2 download failed key={key}: {e}")
        return False


def object_exists(key: str) -> bool:
    try:
        _get_client().head_object(Bucket=_bucket(), Key=key)
        return True
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        logger.warning(f"R2 head_object failed key={key}: {e}")
        return False


def key_from_url(url: Optional[str]) -> Optional[str]:
    """Reverse: extract the object key from a full R2 URL or backend proxy path.

    Returns None if the URL is not R2-related (e.g. a legacy /api/uploads/ path).
    Used when we need to delete an object referenced by URL in MongoDB.
    """
    base = _cfg()["public_url"]
    if not url or not base:
        return None
    prefix = base + "/"
    if url.startswith(prefix):
        return url[len(prefix):]
    return None
