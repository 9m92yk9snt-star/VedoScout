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

R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY")
R2_ENDPOINT = (os.environ.get("R2_ENDPOINT") or "").rstrip("/")
R2_BUCKET = os.environ.get("R2_BUCKET")
R2_PUBLIC_URL = (os.environ.get("R2_PUBLIC_URL") or "").rstrip("/")

_client = None


def is_configured() -> bool:
    """True when all R2 env vars are set. Callers should check this before
    using r2_storage helpers and fall back to local disk if False."""
    return bool(R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_ENDPOINT and R2_BUCKET and R2_PUBLIC_URL)


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name="auto",  # R2 uses "auto" — required by boto3 signature
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
                s3={"addressing_style": "path"},  # R2 requires path-style addressing
            ),
        )
    return _client


def public_url(key: str) -> str:
    """Return the public URL for a given object key."""
    return f"{R2_PUBLIC_URL}/{key.lstrip('/')}"


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
        client.upload_fileobj(f, R2_BUCKET, key, ExtraArgs=extra)
    return public_url(key)


def upload_bytes(key: str, data: bytes, content_type: str, cache_seconds: int = 31536000) -> str:
    client = _get_client()
    client.put_object(
        Bucket=R2_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
        CacheControl=f"public, max-age={cache_seconds}, immutable",
    )
    return public_url(key)


def delete_object(key: str) -> bool:
    """Delete an object. Returns True on success, False if it doesn't exist or fails."""
    try:
        _get_client().delete_object(Bucket=R2_BUCKET, Key=key)
        return True
    except (ClientError, BotoCoreError) as e:
        logger.warning(f"R2 delete failed key={key}: {e}")
        return False


def download_to_file(key: str, dest_path: Path) -> bool:
    """Download an object from R2 to a local file (for ffmpeg processing)."""
    try:
        _get_client().download_file(R2_BUCKET, key, str(dest_path))
        return True
    except (ClientError, BotoCoreError) as e:
        logger.warning(f"R2 download failed key={key}: {e}")
        return False


def object_exists(key: str) -> bool:
    try:
        _get_client().head_object(Bucket=R2_BUCKET, Key=key)
        return True
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        logger.warning(f"R2 head_object failed key={key}: {e}")
        return False


def key_from_url(url: Optional[str]) -> Optional[str]:
    """Reverse: extract the object key from a full R2 public URL.

    Returns None if the URL is not an R2 URL (e.g. a legacy /api/uploads/ path).
    Used when we need to delete an object referenced by URL in MongoDB.
    """
    if not url or not R2_PUBLIC_URL:
        return None
    if url.startswith(R2_PUBLIC_URL + "/"):
        return url[len(R2_PUBLIC_URL) + 1:]
    return None
