import shutil
import subprocess
import cv2
import numpy as np
import pytest
from match_room_tracking import _MotionWindowReader
from player_tracking import _read_window


def test_cached_windows_preserve_vfr_frames_and_per_interval_phase(tmp_path):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        pytest.skip('ffmpeg required')
    source = tmp_path/'source.mp4'
    subprocess.run([ffmpeg, '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    'testsrc2=size=96x64:rate=60:duration=2', '-vf',
                    r'select=not(eq(n\,10)+eq(n\,15)+eq(n\,40))', '-vsync', '0',
                    '-c:v', 'libx264', str(source)], check=True)
    old, new = cv2.VideoCapture(str(source)), cv2.VideoCapture(str(source))
    reader = _MotionWindowReader(new)
    try:
        for start,end in [(0,.133),(.133,.25),(.25,.383),(.383,.5),(.5,.75),(.75,.883),(.9,1.6),(.3,.45)]:
            expected = _read_window(old,start-.02,end+.025,1/30,seed_time=start)
            actual = reader.read(start,end)
            assert [x[0] for x in actual] == [x[0] for x in expected]
            assert all(np.array_equal(a,b) for x,y in zip(actual,expected) for a,b in zip(x[1:],y[1:]))
    finally:
        old.release();new.release()


def test_dense_cache_limit_uses_original_window(monkeypatch):
    import player_tracking
    calls=[]
    def read(*args,**kwargs):
        calls.append(kwargs)
        return [None]*96 if kwargs.get('max_frames') else ['fallback']
    monkeypatch.setattr(player_tracking,'_read_window',read)
    reader = _MotionWindowReader(object())
    assert reader.read(1,1.1) == ['fallback']
    assert calls[0]['max_frames'] == 96
    assert 'max_frames' not in calls[1]
    assert reader.frames == []
