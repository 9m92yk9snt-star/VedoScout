"""Validate tracker drift fix: run track_player on a real report and compare
coverage inside known-bad (empty) windows vs normal segments."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient
from player_tracking import track_player

RID = sys.argv[1] if len(sys.argv) > 1 else "d8c04d5d-6618-4db2-a128-865447478ef6"
ENV = dotenv_values(Path(__file__).resolve().parent.parent / ".env")


async def main():
    db = AsyncIOMotorClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
    d = await db.reports.find_one({"id": RID}, {"_id": 0, "anchors": 1, "player_track": 1,
                                                "anchor_time_offset": 1, "video_filename": 1,
                                                "cv_shadow.prod_verify.empty_windows": 1})
    vp = Path(__file__).resolve().parent.parent / "uploads" / d["video_filename"]
    old = d["player_track"]["points"]
    new = track_player(str(vp), d["anchors"], float(d.get("anchor_time_offset") or 0))
    ew = ((d.get("cv_shadow") or {}).get("prod_verify") or {}).get("empty_windows") or []

    def in_windows(pts, wins):
        return sum(1 for p in pts if any(w[0] <= p["t"] <= w[1] for w in wins))

    print(f"OLD: {len(old)} pts, span {old[0]['t']}->{old[-1]['t']}, in empty-windows: {in_windows(old, ew)}")
    np_ = new["points"]
    print(f"NEW: {len(np_)} pts, span {np_[0]['t']}->{np_[-1]['t']}, in empty-windows: {in_windows(np_, ew)}")
    print("NEW doubts:", [(m['t'], m['reason']) for m in new.get('doubt_moments') or []])
    # normal-zone retention (outside empty windows)
    def outside(pts):
        return sum(1 for p in pts if not any(w[0] <= p["t"] <= w[1] for w in ew))
    print(f"points OUTSIDE empty-windows: old={outside(old)} new={outside(np_)}")

asyncio.run(main())
