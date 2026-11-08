"""Verify exact decoded Orman1000 video frames before any scorer-role review.

Reads the original source MP4 only. No model calls, inference, statistics
changes or output images. Uses actual post-grab media PTS; no FPS arithmetic.
Decoded BGR hashes are tied to the SHA-pinned OpenCV/FFmpeg software setting
documented with the immutable proof manifest.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROOF = ROOT / "testdata/matchroom-completion/orman1000-50s-exact-decoded-pts-hashes.json"


def file_sha256(path):
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda:stream.read(1024*1024),b""):
            h.update(part)
    return h.hexdigest()


def verify(video, expected):
    import cv2
    expected_source=expected["source_video_sha256"]
    if file_sha256(video) != expected_source:
        raise ValueError("NONMATCHING_VIDEO_BYTES")
    wanted={int(k):v for k,v in expected["pts_frame_sha256"].items()}
    if len(wanted)!=7 or not all(len(v)==64 for v in wanted.values()):
        raise ValueError("EXPECTED_SOURCE_FRAME_MANIFEST_CHANGED")
    cap=cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError("VIDEO_CANNOT_BE_DECODED")
    found={}
    frames_examined=0
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC,max(0,min(wanted)-250))
        while frames_examined<180:
            if not cap.grab():break
            t=int(round(cap.get(cv2.CAP_PROP_POS_MSEC)))
            if t>max(wanted)+250:break
            frames_examined+=1
            if t not in wanted:continue
            if t in found:
                raise ValueError("REPEATED_SOURCE_PTS")
            ok,frame=cap.retrieve()
            if not ok:raise ValueError("SOURCE_PIXEL_READ_FAILED")
            if tuple(frame.shape)!=(1920,1080,3):
                raise ValueError("SOURCE_FRAME_DIMENSIONS_CHANGED")
            digest=hashlib.sha256(frame.tobytes()).hexdigest()
            if digest!=wanted[t]:
                raise ValueError("SOURCE_FRAME_PIXELS_CHANGED:"+str(t))
            found[t]=digest
    finally:
        cap.release()
    if set(found)!=set(wanted):
        raise ValueError("SOURCE_EXACT_PTS_NOT_DECODED")
    return {
        "source_video_sha256":expected_source,
        "frame_count":len(found),
        "exact_decoded_pts_verified":sorted(found),
        "all_bgr_sha256_equal":True,
        "source_frame_decoder":"opencv",
        "model_calls":0,"identity_decided":False,
        "finisher_approved":False,
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():ap.error("Output must not exist")
    expected=json.loads(PROOF.read_text())
    result=verify(args.video,expected)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print("ORMAN1000_EXACT_PTS_VERIFICATION="+json.dumps(result))

if __name__=="__main__":
    main()
