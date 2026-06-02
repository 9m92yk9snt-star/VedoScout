"""
One-off migration: for any existing report whose video_filename is .mov / .webm,
transcode it to a web-friendly .mp4 (H.264 + AAC + faststart) and generate a poster.
Updates the report record so the frontend serves the new file.

Run from /app/backend:  python migrate_videos.py
"""
import asyncio
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
UPLOAD_DIR = ROOT / "uploads"

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


def transcode(src: Path) -> Path:
    out = src.with_suffix(".web.mp4")
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
        "-vf", "scale='min(1280,iw)':-2",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-loglevel", "error",
        str(out),
    ]
    print(f"transcoding: {src.name} -> {out.name}")
    r = subprocess.run(cmd, capture_output=True, timeout=300)
    if r.returncode != 0:
        print(f"  FAILED: {r.stderr[:200]}")
        return src
    return out


def poster(src: Path) -> Path | None:
    out = src.with_suffix(".poster.jpg")
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-ss", "00:00:02", "-vframes", "1",
        "-vf", "scale='min(1280,iw)':-2",
        "-q:v", "4", "-loglevel", "error",
        str(out),
    ]
    print(f"poster: {src.name} -> {out.name}")
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    if r.returncode != 0:
        return None
    return out if out.exists() else None


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    cursor = db.reports.find({})
    migrated = 0
    async for doc in cursor:
        fn = doc.get("video_filename", "")
        if not fn or doc.get("demo"):
            continue
        ext = fn.rsplit(".", 1)[-1].lower()
        # Already a web mp4 — skip if poster is also present
        if fn.endswith(".web.mp4") and doc.get("poster_filename"):
            continue
        src = UPLOAD_DIR / fn
        if not src.exists():
            print(f"skip (missing file): {fn}")
            continue

        # If it's already an .mp4 (and not a .web.mp4), still re-encode for faststart consistency
        # but only if not already web.mp4
        if fn.endswith(".web.mp4"):
            web_path = src  # already converted
        else:
            web_path = transcode(src)
        poster_path = poster(web_path)

        update = {
            "video_filename": web_path.name,
            "poster_filename": poster_path.name if poster_path else None,
            "original_video_filename": fn if fn != web_path.name else doc.get("original_video_filename"),
        }
        await db.reports.update_one({"id": doc["id"]}, {"$set": update})
        print(f"  updated report {doc['id']}: video={web_path.name} poster={poster_path.name if poster_path else 'none'}")
        migrated += 1

    print(f"\nMigrated {migrated} report(s).")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
