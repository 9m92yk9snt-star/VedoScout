"""One-off backfill: flush marker + subject_crop JPGs to R2 for every report
that doesn't yet have a marker_url_override / subject_crop_url_override. Uses
the same helper the live pipeline uses so behaviour is identical. Safe to
re-run — idempotent by design.

Run with:
    python -m tests.backfill_r2_marker
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import db, _flush_preview_artifacts_to_r2, r2_storage  # noqa: E402


async def main() -> None:
    if not r2_storage.is_configured():
        print("R2 not configured — skipping backfill")
        return
    total = flushed = errored = 0
    cursor = db.reports.find(
        {
            "$or": [
                {"marker_url_override": {"$in": [None, ""]}},
                {"subject_crop_url_override": {"$in": [None, ""]}},
                {"marker_url_override": {"$exists": False}},
                {"subject_crop_url_override": {"$exists": False}},
            ]
        },
        {"id": 1},
    )
    async for doc in cursor:
        total += 1
        try:
            await _flush_preview_artifacts_to_r2(doc["id"])
            flushed += 1
        except Exception as e:  # noqa: BLE001
            errored += 1
            print(f"  ✗ {doc['id']}: {e}")
    print(f"\nBackfill done — scanned {total}, flushed {flushed}, errored {errored}")


if __name__ == "__main__":
    asyncio.run(main())
