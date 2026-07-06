"""
chunked_upload.py — chunked video upload endpoints that bypass Cloudflare's
~100 MB request-body limit. The browser slices the video into ≤24 MB chunks,
each sent as its own request; we stage them under UPLOAD_DIR/chunks/{upload_id}
and assemble the final file using the standard `url-fetch-{token}.{ext}` temp
naming, so the existing /reports/upload `temp_video_token` path consumes the
result with ZERO changes to the upload pipeline.

Self-contained — no imports from server.py (mirrors url_video_fetch.py).
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

MAX_CHUNK_BYTES = 32 * 1024 * 1024   # per-request cap — safely under Cloudflare's limit
MAX_TOTAL_BYTES = 500 * 1024 * 1024  # 500 MB assembled cap
MAX_CHUNKS = 64
STALE_AFTER_SEC = 12 * 3600
ALLOWED_EXTS = {"mp4", "mov", "m4v", "webm"}


def _assemble(parts: list[Path], final: Path) -> int:
    with final.open("wb") as out:
        for p in parts:
            with p.open("rb") as src:
                shutil.copyfileobj(src, out, length=1024 * 1024)
    return final.stat().st_size


def build_chunked_upload_router(*, upload_dir: Path, get_current_user) -> APIRouter:
    router = APIRouter(tags=["uploads"])
    chunks_root = upload_dir / "chunks"

    def _sweep_stale():
        try:
            if not chunks_root.exists():
                return
            now = time.time()
            for d in chunks_root.iterdir():
                try:
                    if d.is_dir() and now - d.stat().st_mtime > STALE_AFTER_SEC:
                        shutil.rmtree(d, ignore_errors=True)
                except Exception:
                    pass
        except Exception:
            pass

    def _session_dir(upload_id: str, user_id: str) -> tuple[Path, dict]:
        safe = re.sub(r"[^a-f0-9]", "", (upload_id or "").lower())
        if not safe or len(safe) != 32:
            raise HTTPException(400, "Invalid upload_id.")
        d = chunks_root / safe
        meta_path = d / "meta.json"
        if not d.exists() or not meta_path.exists():
            raise HTTPException(404, "Upload session not found or expired. Please restart the upload.")
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            raise HTTPException(500, "Upload session corrupted. Please restart the upload.")
        if meta.get("user_id") != user_id:
            raise HTTPException(403, "Not your upload session.")
        return d, meta

    @router.post("/me/chunked-upload/init")
    async def init_chunked_upload(
        filename: str = Form(...),
        total_size: int = Form(...),
        user=Depends(get_current_user),
    ):
        _sweep_stale()
        if total_size <= 0:
            raise HTTPException(400, "Invalid total_size.")
        if total_size > MAX_TOTAL_BYTES:
            raise HTTPException(
                413,
                f"Video is {total_size // (1024 * 1024)} MB — maximum is "
                f"{MAX_TOTAL_BYTES // (1024 * 1024)} MB. Trim the clip and try again.",
            )
        ext = (filename or "video.mp4").rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXTS:
            ext = "mp4"
        upload_id = uuid.uuid4().hex
        d = chunks_root / upload_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps({
            "user_id": user["id"],
            "ext": ext,
            "total_size": int(total_size),
            "created_at": time.time(),
        }))
        return {"upload_id": upload_id, "chunk_max_bytes": MAX_CHUNK_BYTES}

    @router.post("/me/chunked-upload/chunk")
    async def upload_chunk(
        upload_id: str = Form(...),
        index: int = Form(...),
        chunk: UploadFile = File(...),
        user=Depends(get_current_user),
    ):
        d, _ = _session_dir(upload_id, user["id"])
        if index < 0 or index >= MAX_CHUNKS:
            raise HTTPException(400, "Invalid chunk index.")
        part = d / f"part_{index:05d}"
        size = 0
        try:
            with part.open("wb") as out:
                while True:
                    data = await chunk.read(1024 * 1024)
                    if not data:
                        break
                    size += len(data)
                    if size > MAX_CHUNK_BYTES:
                        raise HTTPException(413, f"Chunk too large (max {MAX_CHUNK_BYTES // (1024 * 1024)} MB).")
                    out.write(data)
        except HTTPException:
            part.unlink(missing_ok=True)
            raise
        d.touch()  # keep the session fresh for the stale sweep
        return {"ok": True, "index": index, "bytes": size}

    @router.post("/me/chunked-upload/complete")
    async def complete_chunked_upload(
        upload_id: str = Form(...),
        total_chunks: int = Form(...),
        user=Depends(get_current_user),
    ):
        d, meta = _session_dir(upload_id, user["id"])
        if total_chunks <= 0 or total_chunks > MAX_CHUNKS:
            raise HTTPException(400, "Invalid chunk count.")
        parts = [d / f"part_{i:05d}" for i in range(int(total_chunks))]
        missing = [i for i, p in enumerate(parts) if not p.exists()]
        if missing:
            raise HTTPException(400, f"Missing chunks: {missing[:5]}. Please retry the upload.")
        token = uuid.uuid4().hex
        final = upload_dir / f"url-fetch-{token}.{meta.get('ext', 'mp4')}"
        try:
            total = await asyncio.to_thread(_assemble, parts, final)
        except Exception:
            final.unlink(missing_ok=True)
            raise HTTPException(500, "Could not assemble the uploaded video. Please retry.")
        if total <= 0 or total > MAX_TOTAL_BYTES:
            final.unlink(missing_ok=True)
            raise HTTPException(413, "Assembled video exceeds the size limit.")
        shutil.rmtree(d, ignore_errors=True)
        return {
            "token": token,
            "size_mb": round(total / (1024 * 1024), 2),
            "stored_filename": final.name,
        }

    @router.post("/me/chunked-upload/abort")
    async def abort_chunked_upload(
        upload_id: str = Form(...),
        user=Depends(get_current_user),
    ):
        d, _ = _session_dir(upload_id, user["id"])
        shutil.rmtree(d, ignore_errors=True)
        return {"ok": True}

    return router
