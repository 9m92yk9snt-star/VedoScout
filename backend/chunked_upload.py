"""
chunked_upload.py — chunked video upload endpoints that bypass Cloudflare's
~100 MB request-body limit. The browser slices the video into ≤24 MB chunks,
each sent as its own request; the assembled file uses the standard
`url-fetch-{token}.{ext}` temp naming, so the existing /reports/upload
`temp_video_token` path consumes the result with ZERO pipeline changes.

Two storage modes:
- R2 + Mongo (production-safe): session meta lives in Mongo, chunk bytes in
  Cloudflare R2 — works across multiple pods / restarts (local pod disk is
  NOT shared behind the load balancer, which caused "Upload session not
  found" mid-upload in production).
- Local disk fallback (dev without R2): original behaviour.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

import r2_storage

logger = logging.getLogger("chunked_upload")

MAX_CHUNK_BYTES = 32 * 1024 * 1024   # per-request cap — safely under Cloudflare's limit
MAX_TOTAL_BYTES = 500 * 1024 * 1024  # 500 MB assembled cap
MAX_CHUNKS = 64
STALE_AFTER_SEC = 12 * 3600
ALLOWED_EXTS = {"mp4", "mov", "m4v", "webm"}

SESSION_COLL = "chunk_upload_sessions"


def _part_key(upload_id: str, index: int) -> str:
    return f"chunks/{upload_id}/part_{index:05d}"


def _clean_id(upload_id: str) -> str:
    safe = re.sub(r"[^a-f0-9]", "", (upload_id or "").lower())
    if not safe or len(safe) != 32:
        raise HTTPException(400, "Invalid upload_id.")
    return safe


def build_chunked_upload_router(*, upload_dir: Path, get_current_user, db=None) -> APIRouter:
    router = APIRouter(tags=["uploads"])
    chunks_root = upload_dir / "chunks"

    def _r2_mode() -> bool:
        return db is not None and r2_storage.is_configured()

    # ---------------- R2 + Mongo session helpers (multi-pod safe) ----------------

    async def _get_session(upload_id: str, user_id: str) -> dict:
        doc = await db[SESSION_COLL].find_one({"_id": upload_id})
        if not doc:
            raise HTTPException(404, "Upload session not found or expired. Please restart the upload.")
        if doc.get("user_id") != user_id:
            raise HTTPException(403, "Not your upload session.")
        return doc

    async def _delete_session(doc: dict) -> None:
        upload_id = doc["_id"]
        for k in (doc.get("parts") or {}):
            try:
                await asyncio.to_thread(r2_storage.delete_object, _part_key(upload_id, int(k)))
            except Exception:
                pass
        await db[SESSION_COLL].delete_one({"_id": upload_id})

    async def _sweep_stale_mongo() -> None:
        try:
            cutoff = time.time() - STALE_AFTER_SEC
            async for doc in db[SESSION_COLL].find({"created_at": {"$lt": cutoff}}):
                await _delete_session(doc)
        except Exception:
            pass

    # ---------------- Local-disk fallback helpers (dev without R2) ----------------

    def _sweep_stale_local():
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
        safe = _clean_id(upload_id)
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

    def _assemble_local(parts: list[Path], final: Path) -> int:
        with final.open("wb") as out:
            for p in parts:
                with p.open("rb") as src:
                    shutil.copyfileobj(src, out, length=1024 * 1024)
        return final.stat().st_size

    def _assemble_from_r2(upload_id: str, total_chunks: int, final: Path) -> int:
        tmp = final.with_suffix(final.suffix + ".part")
        with final.open("wb") as out:
            for i in range(total_chunks):
                if not r2_storage.download_to_file(_part_key(upload_id, i), tmp):
                    raise RuntimeError(f"chunk {i} missing in R2")
                with tmp.open("rb") as src:
                    shutil.copyfileobj(src, out, length=1024 * 1024)
                tmp.unlink(missing_ok=True)
        return final.stat().st_size

    # ------------------------------- endpoints -------------------------------

    @router.post("/me/chunked-upload/init")
    async def init_chunked_upload(
        filename: str = Form(...),
        total_size: int = Form(...),
        user=Depends(get_current_user),
    ):
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
        if _r2_mode():
            await _sweep_stale_mongo()
            await db[SESSION_COLL].insert_one({
                "_id": upload_id,
                "user_id": user["id"],
                "ext": ext,
                "total_size": int(total_size),
                "created_at": time.time(),
                "parts": {},
            })
        else:
            _sweep_stale_local()
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
        if index < 0 or index >= MAX_CHUNKS:
            raise HTTPException(400, "Invalid chunk index.")
        if _r2_mode():
            upload_id = _clean_id(upload_id)
            await _get_session(upload_id, user["id"])
            buf = bytearray()
            while True:
                data = await chunk.read(1024 * 1024)
                if not data:
                    break
                buf.extend(data)
                if len(buf) > MAX_CHUNK_BYTES:
                    raise HTTPException(413, f"Chunk too large (max {MAX_CHUNK_BYTES // (1024 * 1024)} MB).")
            size = len(buf)
            try:
                await asyncio.to_thread(
                    r2_storage.upload_bytes, _part_key(upload_id, index), bytes(buf),
                    "application/octet-stream", 24 * 3600,
                )
            except Exception as e:
                logger.warning(f"chunk R2 upload failed {upload_id}/{index}: {e}")
                raise HTTPException(500, "Could not store this chunk. Please retry.")
            await db[SESSION_COLL].update_one(
                {"_id": upload_id},
                {"$set": {f"parts.{index}": size, "touched_at": time.time()}},
            )
            return {"ok": True, "index": index, "bytes": size}
        # local fallback
        d, _ = _session_dir(upload_id, user["id"])
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
        d.touch()
        return {"ok": True, "index": index, "bytes": size}

    @router.post("/me/chunked-upload/complete")
    async def complete_chunked_upload(
        upload_id: str = Form(...),
        total_chunks: int = Form(...),
        user=Depends(get_current_user),
    ):
        if total_chunks <= 0 or total_chunks > MAX_CHUNKS:
            raise HTTPException(400, "Invalid chunk count.")
        if _r2_mode():
            upload_id = _clean_id(upload_id)
            doc = await _get_session(upload_id, user["id"])
            parts = doc.get("parts") or {}
            missing = [i for i in range(int(total_chunks)) if str(i) not in parts]
            if missing:
                raise HTTPException(400, f"Missing chunks: {missing[:5]}. Please retry the upload.")
            token = uuid.uuid4().hex
            ext = doc.get("ext", "mp4")
            final = upload_dir / f"url-fetch-{token}.{ext}"
            try:
                total = await asyncio.to_thread(_assemble_from_r2, upload_id, int(total_chunks), final)
            except Exception as e:
                final.unlink(missing_ok=True)
                logger.warning(f"chunk assemble failed {upload_id}: {e}")
                raise HTTPException(500, "Could not assemble the uploaded video. Please retry.")
            if total <= 0 or total > MAX_TOTAL_BYTES:
                final.unlink(missing_ok=True)
                raise HTTPException(413, "Assembled video exceeds the size limit.")
            # Mirror the assembled file to R2 so /reports/upload can restore it
            # even when that request lands on a DIFFERENT pod (production).
            try:
                await asyncio.to_thread(
                    r2_storage.upload_file, f"tmp/{final.name}", final, "video/mp4", 24 * 3600,
                )
            except Exception as e:
                logger.warning(f"tmp mirror to R2 failed {final.name}: {e}")
            await _delete_session(doc)
            return {"token": token, "size_mb": round(total / (1024 * 1024), 2), "stored_filename": final.name}
        # local fallback
        d, meta = _session_dir(upload_id, user["id"])
        parts = [d / f"part_{i:05d}" for i in range(int(total_chunks))]
        missing = [i for i, p in enumerate(parts) if not p.exists()]
        if missing:
            raise HTTPException(400, f"Missing chunks: {missing[:5]}. Please retry the upload.")
        token = uuid.uuid4().hex
        final = upload_dir / f"url-fetch-{token}.{meta.get('ext', 'mp4')}"
        try:
            total = await asyncio.to_thread(_assemble_local, parts, final)
        except Exception:
            final.unlink(missing_ok=True)
            raise HTTPException(500, "Could not assemble the uploaded video. Please retry.")
        if total <= 0 or total > MAX_TOTAL_BYTES:
            final.unlink(missing_ok=True)
            raise HTTPException(413, "Assembled video exceeds the size limit.")
        shutil.rmtree(d, ignore_errors=True)
        return {"token": token, "size_mb": round(total / (1024 * 1024), 2), "stored_filename": final.name}

    @router.post("/me/chunked-upload/abort")
    async def abort_chunked_upload(
        upload_id: str = Form(...),
        user=Depends(get_current_user),
    ):
        if _r2_mode():
            upload_id = _clean_id(upload_id)
            doc = await _get_session(upload_id, user["id"])
            await _delete_session(doc)
            return {"ok": True}
        d, _ = _session_dir(upload_id, user["id"])
        shutil.rmtree(d, ignore_errors=True)
        return {"ok": True}

    return router
