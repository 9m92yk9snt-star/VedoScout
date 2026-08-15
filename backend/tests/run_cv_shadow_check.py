"""Manual validation: run cv_shadow on a real report and print/store the metrics."""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import dotenv_values, load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from motor.motor_asyncio import AsyncIOMotorClient
import cv_shadow

RID = sys.argv[1] if len(sys.argv) > 1 else "bd972050-6fc7-40e2-b6c4-8a4d234b9b1e"
ENV = dotenv_values(Path(__file__).resolve().parent.parent / ".env")


async def main():
    db = AsyncIOMotorClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
    doc = await db.reports.find_one({"id": RID}, {"_id": 0})
    if not doc:
        print("REPORT NOT FOUND"); return
    vp = Path(__file__).resolve().parent.parent / "uploads" / (doc.get("video_filename") or "")
    print("video:", vp.name, "exists:", vp.exists(),
          "| anchors:", len(doc.get("anchors") or []),
          "| track pts:", len((doc.get("player_track") or {}).get("points") or []),
          "| t_off:", doc.get("anchor_time_offset"))
    if not vp.exists():
        import r2_storage
        ok = False
        try:
            key = r2_storage.key_from_url(doc.get("video_url_override"))
            if key:
                ok = r2_storage.download_to_file(key, vp)
        except Exception as e:
            print("r2 restore failed:", e)
        print("r2 restore:", ok)
        if not vp.exists():
            return
    out = await asyncio.to_thread(cv_shadow.run_shadow, RID, str(vp), doc)
    print(json.dumps(out, indent=2))
    if out and out.get("status") == "ok":
        await db.reports.update_one({"id": RID}, {"$set": {"cv_shadow": out}})
        print("STORED cv_shadow on report")

asyncio.run(main())
