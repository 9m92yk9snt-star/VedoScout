"""No-identity test for byte-bound decoded PTS hashing of source clip."""
import hashlib
import pytest
import numpy as np
import cv2

from scripts.verify_orman1000_frame_hashes import verify


class Frames:
    def __init__(self, frame, positions):
        self.frame=frame
        self.positions=positions
        self.i=-1
        self.closed=False
    def isOpened(self):return True
    def set(self,*args):return True
    def grab(self):
        self.i+=1
        return self.i<len(self.positions)
    def get(self, prop):
        assert prop==cv2.CAP_PROP_POS_MSEC
        return self.positions[self.i]
    def retrieve(self):
        return True,self.frame.copy()
    def release(self):self.closed=True


def test_actual_pts_hashes_are_verified_without_model_or_fps_fallback(tmp_path,monkeypatch):
    video=tmp_path/"source.mp4"
    video.write_bytes(b"source-pixel-proof-test")
    pixels=np.zeros((1920,1080,3),dtype=np.uint8)
    pixels[800:803,160:164]=[21,84,117]
    times=[49715,49881,50081,50331,50431,50648,51131]
    digest=hashlib.sha256(pixels.tobytes()).hexdigest()
    expected={
        "source_video_sha256":hashlib.sha256(video.read_bytes()).hexdigest(),
        "pts_frame_sha256":{str(t):digest for t in times}
    }
    decoders=[]
    def make(_):
        decoder=Frames(pixels,times)
        decoders.append(decoder)
        return decoder
    monkeypatch.setattr(cv2,"VideoCapture",make)
    verified=verify(video,expected)
    assert verified["exact_decoded_pts_verified"]==times
    assert verified["all_bgr_sha256_equal"] is True
    assert verified["finisher_approved"] is False
    assert verified["model_calls"]==0
    assert len(decoders)==1 and decoders[0].closed
    forged=dict(expected,source_video_sha256="bad-video")
    with pytest.raises(ValueError,match="NONMATCHING_VIDEO_BYTES"):
        verify(video,forged)
    forged=dict(expected,pts_frame_sha256={**expected["pts_frame_sha256"],"50331":"f"*64})
    with pytest.raises(ValueError,match="SOURCE_FRAME_PIXELS_CHANGED:50331"):
        verify(video,forged)


def test_missing_exact_source_pts_are_never_interpolated(tmp_path,monkeypatch):
    video=tmp_path/"source.mp4"
    video.write_bytes(b"pinned-test-video")
    frame=np.zeros((1920,1080,3),dtype=np.uint8)
    times=[49715,49881,50081,50331,50431,50648,51131]
    wanted=hashlib.sha256(frame.tobytes()).hexdigest()
    expected={"source_video_sha256":hashlib.sha256(video.read_bytes()).hexdigest(),
              "pts_frame_sha256":{str(t):wanted for t in times}}
    monkeypatch.setattr(cv2,"VideoCapture",lambda _:Frames(frame,times[:-1]))
    with pytest.raises(ValueError,match="SOURCE_EXACT_PTS_NOT_DECODED"):
        verify(video,expected)
