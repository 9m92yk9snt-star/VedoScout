"""Admin-only download route; DB reads and private temporary files only."""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from report_evidence_export import (build_export, validate_report_id, MAX_MODEL_CALLS,
                                    MAX_AUDIT_BYTES, AuditRecords)


async def _collect_run_audit(collection, report_id, *, limit, max_bytes=MAX_AUDIT_BYTES):
    """Read-only, report-scoped audit records; never cross-report, never raises."""
    if collection is None:
        return None
    records = AuditRecords()
    cursor = None
    try:
        cursor = collection.find({"report_id": report_id}, {"_id": 0}).batch_size(1).limit(limit + 1)
        async for record in cursor:
            if not records.retain(record, limit=limit, max_bytes=max_bytes):
                break
    except Exception as exc:
        records.omissions.append(f"audit_read_failed:{type(exc).__name__}")
    finally:
        if cursor is not None:
            await cursor.close()
    return records


class PrivateExportResponse(FileResponse):
    """Clean private bytes and release capacity even if sending disconnects."""
    def __init__(self, *args, cleanup, **kwargs):
        super().__init__(*args, **kwargs)
        self.cleanup = cleanup

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.cleanup()


def create_report_export_router(*, db, upload_dir, source_root, admin_dependency,
                                object_reader=None):
    router = APIRouter()
    busy = asyncio.Semaphore(1)

    @router.get("/admin/reports/{report_id}/evidence-export")
    async def evidence_export(report_id: str, include_video: bool = True,
                              _admin=Depends(admin_dependency)):
        try:
            validate_report_id(report_id)
        except ValueError:
            raise HTTPException(400, "Invalid report ID") from None
        doc = await db.reports.find_one({"id": report_id}, {"_id": 0})
        if doc is None:
            raise HTTPException(404, "Report not found")
        try:
            await asyncio.wait_for(busy.acquire(), timeout=0.1)
        except asyncio.TimeoutError:
            raise HTTPException(429, "An export is already running. Try again shortly.") from None
        private = None
        response_ready = False
        try:
            run_records = await asyncio.wait_for(_collect_run_audit(
                getattr(db, "analysis_runs", None), report_id, limit=MAX_MODEL_CALLS), 10)
            model_call_records = await asyncio.wait_for(_collect_run_audit(
                getattr(db, "analysis_model_calls", None), report_id, limit=MAX_MODEL_CALLS), 10)
            private = Path(tempfile.mkdtemp(prefix="scout-admin-export-"))
            os.chmod(private, 0o700)
            output = private / f"{report_id}-evidence.zip"
            task = asyncio.create_task(asyncio.to_thread(
                build_export, doc, output, upload_dir=upload_dir, source_root=source_root,
                object_reader=object_reader, include_video=include_video,
                run_records=run_records, model_call_records=model_call_records))
            try:
                summary = await asyncio.shield(task)
            except asyncio.CancelledError:
                # Let the worker finish before removing its private workspace.
                try:
                    await task
                except Exception:
                    pass
                raise
            def cleanup():
                shutil.rmtree(private, ignore_errors=True)
                busy.release()

            response = PrivateExportResponse(output, cleanup=cleanup,
                media_type="application/zip", filename=output.name,
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                         "X-Export-Missing-Count": str(summary["missing_count"])})
            response_ready = True
            return response
        except asyncio.CancelledError:
            if private:
                shutil.rmtree(private, ignore_errors=True)
            raise
        except Exception:
            if private:
                shutil.rmtree(private, ignore_errors=True)
            # Storage/DB exception text can contain credentials. Do not expose it.
            raise HTTPException(500, "Could not build evidence export") from None
        finally:
            if not response_ready:
                busy.release()

    return router
