"""Independent last-mile source-pixel checks for Orman1000 role review.

A review JSON's claimed WHITE kit is not pixel authority. This offline-only
audit reads exact original decoded source frames and requires visible light
fabric inside each submitted physical person box. It NEVER identifies the
scorer, infers hidden contact, or performs model calls. Passing is necessary,
not sufficient, for the external independent human role decision.
"""
import hashlib
from pathlib import Path

SOURCE = "fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2"
FRAMES = {
    "s000050331": (50331, "4c1daa279d50b4a447c9406e1b25f6ff0f0f34dfbe4880372dfbdf983ddf92b1"),
    "s000050648": (50648, "ba5d26a54b40fec01d29fa02a53d8ec51c5e5d246ff50c6ade8d33e8953be9f3"),
}
MIN_LIGHT_KIT_FRACTION = .10


def _file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def white_kit_pixel_ratio(frame, box):
    """Measure actual light/low-saturation pixels in a supported source box.

    Light pixels need not belong to a player: line markings, glare, and other
    people can exist. This is deliberately only a contradiction check.
    """
    import cv2
    import numpy as np
    from orman1000_role_spatial_gate import valid_rect
    if not valid_rect(box) or frame is None or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("SOURCE_ROLE_BOX_OR_PIXELS_INVALID")
    height,width=frame.shape[:2]
    x,y,w,h=box
    x0,y0=round(x*width),round(y*height)
    x1,y1=round((x+w)*width),round((y+h)*height)
    if x1<=x0 or y1<=y0:
        raise ValueError("SOURCE_ROLE_CROP_EMPTY")
    hsv=cv2.cvtColor(frame[y0:y1,x0:x1],cv2.COLOR_BGR2HSV)
    value=hsv[:,:,2]
    saturation=hsv[:,:,1]
    return float(np.mean((value>135)&(saturation<75)))


def validate_source_role_pixels(source_video, role):
    """Return immutable facts, or refuse. No claim of goal/assist approval."""
    import cv2
    from video_timebase import read_frame_at
    if _file_hash(source_video) != SOURCE:
        raise ValueError("ROLE_SOURCE_VIDEO_HASH_CHANGED")
    boxes=(role or {}).get("source_finisher_boxes")
    if not isinstance(boxes,dict) or set(boxes)!=set(FRAMES):
        raise ValueError("TWO_SOURCE_WHITE_FINISHER_BOXES_REQUIRED")
    cap=cv2.VideoCapture(str(source_video))
    if not cap.isOpened():
        raise ValueError("ROLE_SOURCE_VIDEO_UNREADABLE")
    ratios={}
    try:
        for frame_id,(ms,expected_sha) in FRAMES.items():
            ok,frame,real_s=read_frame_at(cap,ms/1000)
            if not ok or frame is None or round(real_s*1000)!=ms:
                raise ValueError("ROLE_SOURCE_EXACT_FRAME_PTS_NOT_PROVEN")
            if hashlib.sha256(frame.tobytes()).hexdigest()!=expected_sha:
                raise ValueError("ROLE_SOURCE_DECODED_PIXEL_SHA_CHANGED")
            ratio=white_kit_pixel_ratio(frame,boxes[frame_id])
            ratios[frame_id]=round(ratio,6)
            if ratio<MIN_LIGHT_KIT_FRACTION:
                raise ValueError("ROLE_REVIEW_BOX_NOT_VISIBLY_WHITE:"+frame_id)
    finally:
        cap.release()
    return {
        "source_video_sha256":SOURCE,
        "exact_source_frame_sha256_verified":True,
        "light_kit_fraction_in_source_box":ratios,
        "minimum_fraction":MIN_LIGHT_KIT_FRACTION,
        "white_person_identity_automatically_approved":False,
        "model_calls":0,
    }


def validate_uploaded_archive_role(archive_path, role):
    """Use the exact source MP4 INSIDE the previously SHA-verified ZIP."""
    import shutil
    import tempfile
    import zipfile
    from pathlib import Path
    with zipfile.ZipFile(archive_path) as archive:
        expected = [
            name for name in archive.namelist()
            if name.startswith("video/canonical_web-") and name.endswith(".web.mp4")
        ]
        if len(expected)!=1 or archive.testzip() is not None:
            raise ValueError("EXACT_SOURCE_WEB_VIDEO_ARCHIVE_REQUIRED")
        with tempfile.TemporaryDirectory(prefix="orman1000-role-source-") as temporary:
            filename=Path(temporary)/"canonical.web.mp4"
            with archive.open(expected[0]) as src, filename.open("wb") as dst:
                shutil.copyfileobj(src,dst,1024*1024)
            return validate_source_role_pixels(filename,role)
