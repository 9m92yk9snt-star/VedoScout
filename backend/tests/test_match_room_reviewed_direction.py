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
