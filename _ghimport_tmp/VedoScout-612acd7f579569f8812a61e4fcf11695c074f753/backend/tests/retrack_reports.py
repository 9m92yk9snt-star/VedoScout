"""Re-track reports with the fixed tracker and persist + refresh shadow."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import dotenv_values, load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from motor.motor_asyncio import AsyncIOMotorClient
from player_tracking import track_player

ENV = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
RIDS = sys.argv[1:]


async def main():
    db = AsyncIOMotorClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
    for rid in RIDS:
        d = await db.reports.find_one({"id": rid}, {"_id": 0, "anchors": 1,
                                                    "anchor_time_offset": 1,
                                                    "video_filename": 1,
                                                    "video_url_override": 1})
        vp = Path(__file__).resolve().parent.parent / "uploads" / d["video_filename"]
        if not vp.exists():
            import r2_storage
            key = r2_storage.key_from_url(d.get("video_url_override"))
            if key:
                r2_storage.download_to_file(key, vp)
        if not vp.exists():
            print(rid[:8], "NO VIDEO")
            continue
        new = track_player(str(vp), d["anchors"], float(d.get("anchor_time_offset") or 0))
        await db.reports.update_one({"id": rid}, {"$set": {"player_track": new}})
        print(rid[:8], "track updated:", len(new["points"]), "pts,",
              len(new["segments"]), "segs, doubts:",
              [(m["t"], m["reason"][:20]) for m in new.get("doubt_moments") or []])

asyncio.run(main())
