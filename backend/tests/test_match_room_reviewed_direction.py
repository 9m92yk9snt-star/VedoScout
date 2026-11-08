import hashlib
import time
import pytest
from match_room_reviewed_direction import build_reviewed_direction


def review(source):
    return {'status':'OWNER_APPROVED_DIRECTION','review_id':'owner-review','event_id':'event',
            'source_video_sha256':source,'reference_ms':1000,'start_ms':1000,'end_ms':1100,
            'direction':[[.4,.6],[.5,.55]]}


@pytest.mark.parametrize('change', [
    {'status':'PENDING'}, {'event_id':'other'}, {'source_video_sha256':'other'},
    {'review_id':None}, {'direction':[[.4,.6],[float('nan'),.5]]},
    {'direction':[[.4,.6],[1.1,.5]]},
])
def test_review_must_be_approved_and_bound_before_any_decode(tmp_path, change):
    r={**review('source'),**change}
    with pytest.raises(ValueError,match='BINDING_REQUIRED'):
        build_reviewed_direction(tmp_path/'absent.mp4','event','source',r,time.monotonic()+5)


def test_actual_video_hash_is_required(tmp_path):
    p=tmp_path/'video.mp4';p.write_bytes(b'wrong source')
    with pytest.raises(ValueError,match='SOURCE_MISMATCH'):
        build_reviewed_direction(p,'event','expected',review('expected'),time.monotonic()+5)


@pytest.mark.parametrize('change',[{'reference_ms':1101},{'end_ms':2600},{'start_ms':True}])
def test_review_window_is_short_ordered_and_integer(tmp_path,change):
    with pytest.raises(ValueError,match='WINDOW_INVALID'):
        build_reviewed_direction(tmp_path/'absent','event','source',{**review('source'),**change},time.monotonic()+5)


@pytest.mark.parametrize('animation', [
    {}, [], {'kind':'OBSERVED_BALL','arrival_ms':1050},
    {'kind':'RECONSTRUCTED_PASS','arrival_ms':True},
    {'kind':'RECONSTRUCTED_PASS','arrival_ms':1000},
    {'kind':'RECONSTRUCTED_PASS','arrival_ms':1101},
])
def test_invalid_animation_rejected_before_decode(tmp_path, animation):
    r={**review('source'), 'animation':animation}
    with pytest.raises(ValueError, match='ANIMATION_INVALID'):
        build_reviewed_direction(tmp_path/'absent','event','source',r,time.monotonic()+5)


@pytest.mark.parametrize("expire_on_last_mask", [False, True])
def test_animated_output_moves_tip_but_preserves_masks_and_pending_status(tmp_path, monkeypatch, expire_on_last_mask):
    import numpy as np
    import cv2
    import video_timebase
    import motion_compensation
    import native_player_segmentation
    import match_room_tracking
    class Capture:
        def __init__(self, *_): self.stamp = 1000
        def retrieve(self): return True, np.zeros((100,100,3),np.uint8)
        def release(self): pass
    monkeypatch.setattr(cv2,'VideoCapture',Capture)
    monkeypatch.setattr(video_timebase,'seek_with_preroll',lambda cap,t:(True,1.,False))
    def advance(cap):
        cap.stamp += 50
        return cap.stamp <= 1100, cap.stamp/1000, False
    monkeypatch.setattr(video_timebase,'grab_frame_time_seconds',advance)
    monkeypatch.setattr(motion_compensation,'estimate_camera',lambda *a:(np.eye(2,3),None))
    monkeypatch.setattr(native_player_segmentation,'_instances',lambda *a:([],None))
    polygons=[[[.1,.1],[.2,.1],[.2,.2]]]
    monkeypatch.setattr(match_room_tracking,'foreground_polygons',lambda *a:polygons)
    p=tmp_path/'clip';p.write_bytes(b'test');sha=hashlib.sha256(p.read_bytes()).hexdigest()
    if expire_on_last_mask:
        clock = [0.]
        calls = [0]
        released = []
        monkeypatch.setattr(time, 'monotonic', lambda: clock[0])
        monkeypatch.setattr(Capture, 'release', lambda self: released.append(True))
        def slow_last_mask(*args):
            calls[0] += 1
            if calls[0] == 3:
                clock[0] = 6.
            return [], None
        monkeypatch.setattr(native_player_segmentation, '_instances', slow_last_mask)
        with pytest.raises(ValueError, match='TIME_OR_BUDGET'):
            build_reviewed_direction(p, 'event', sha, review(sha), 5.)
        assert calls[0] == 3 and released == [True]
        return
    static=build_reviewed_direction(p,'event',sha,review(sha),time.monotonic()+5)
    animated=build_reviewed_direction(p,'event',sha,{**review(sha),'playback_status':'VERIFIED',
        'animation':{'kind':'RECONSTRUCTED_PASS','arrival_ms':1100}},time.monotonic()+5)
    assert animated['playback_status']=='PENDING'
    assert animated['is_measured_ball_trajectory'] is False
    assert animated['samples'][0]['directionTrail'][1]==pytest.approx([.4,.6])
    assert animated['samples'][1]['directionTrail'][1]==pytest.approx([.45,.575])
    assert animated['samples'][2]['directionTrail'][1]==pytest.approx([.5,.55])
    for old,new in zip(static['samples'],animated['samples']):
        assert old['foreground']==new['foreground']
        assert old['directionTrail'][1]==pytest.approx([.5,.55])


def test_expired_budget_does_not_open_source(tmp_path):
    with pytest.raises(ValueError, match='TIME_OR_BUDGET'):
        build_reviewed_direction(tmp_path/'absent', 'event', 'source', review('source'), 0)
