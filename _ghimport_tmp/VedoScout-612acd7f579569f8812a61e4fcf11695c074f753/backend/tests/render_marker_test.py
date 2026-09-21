"""Local visual check of the ground-integrated marker (no DB writes, no LLM)."""
import sys, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import dotenv_values
import cv2
from pymongo import MongoClient
import telestration, tele_clip

RID = "d8c04d5d-6618-4db2-a128-865447478ef6"
T = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
ENV = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
db = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
doc = db.reports.find_one({"id": RID}, {"_id": 0, "video_filename": 1, "player_track": 1})
vp = Path(__file__).resolve().parent.parent / "uploads" / doc["video_filename"]
pts = doc["player_track"]["points"]
near = min(pts, key=lambda p: abs(float(p["t"]) - T))
print("track point at", near["t"], {k: round(float(near[k]), 3) for k in ("x", "y", "w", "h")})

cap = cv2.VideoCapture(str(vp))
fps = cap.get(cv2.CAP_PROP_FPS)
cap.set(cv2.CAP_PROP_POS_FRAMES, int(float(near["t"]) * fps))
ok, frame = cap.read()
cap.release()
cv2.imwrite("/tmp/marker_raw.jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
shutil.copy("/tmp/marker_raw.jpg", "/tmp/marker_static.jpg")
box = {"x0": float(near["x"]), "y0": float(near["y"]),
       "x1": float(near["x"]) + float(near["w"]), "y1": float(near["y"]) + float(near["h"])}
print("static:", telestration.render_telestration("/tmp/marker_static.jpg", box, ring=True))

res = tele_clip.generate_tracked_clip(str(vp), T, pts, "/tmp/marker_clip.mp4", "X", 2.5, 3.5)
print("clip:", res)
if res:
    cap = cv2.VideoCapture("/tmp/marker_clip.mp4")
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    for i, f in enumerate([n // 4, n // 2, 3 * n // 4]):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ok, fr = cap.read()
        if ok:
            cv2.imwrite(f"/tmp/marker_clip_f{i}.jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, 88])
    cap.release()
print("DONE")
