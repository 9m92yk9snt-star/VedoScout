import numpy as np
from match_room_prediction_cache import CachedSegmenter

class Model:
    sha256='model-a'
    def __init__(self):self.calls=0
    def predict(self,image):
        self.calls+=1
        return [{'box':(0,0,4,4),'score':.875,'class_id':0,'mask':(image[:,:,0]>0).astype(np.uint8)}]

def test_exact_cache_survives_worker_restart_without_mutable_aliases(tmp_path,monkeypatch):
    monkeypatch.setenv('SCOUTMEPLAY_MATCHROOM_ENGINE','opencv')
    image=np.ones((4,4,3),np.uint8);m=Model();c=CachedSegmenter(m,tmp_path,'source')
    c.predict(image)[0]['mask'][:]=0
    next_model=Model();next_cache=CachedSegmenter(next_model,tmp_path,'source')
    assert next_cache.predict(image)[0]['mask'].sum()==16
    assert next_model.calls==0
    changed=image.copy();changed[0,0,0]=0
    assert next_cache.predict(changed)[0]['mask'].sum()==15
    assert next_model.calls==1
    CachedSegmenter(next_model,tmp_path,'different-source').predict(image)
    assert next_model.calls==2
    next_model.sha256='model-b';CachedSegmenter(next_model,tmp_path,'source').predict(image)
    assert next_model.calls==3

def test_corrupt_file_recomputes_and_replaces(tmp_path,monkeypatch):
    monkeypatch.setenv('SCOUTMEPLAY_MATCHROOM_ENGINE','opencv')
    m=Model();c=CachedSegmenter(m,tmp_path,'source');image=np.ones((4,4,3),np.uint8)
    c.predict(image);next(tmp_path.glob('*.npz')).write_bytes(b'broken')
    assert c.predict(image)[0]['mask'].sum()==16
    assert m.calls==2
    c.predict(image);assert m.calls==2


def test_cache_scope_is_opt_in_and_removed_after_worker_failure(monkeypatch):
    import match_room_tracking as tracking
    from pathlib import Path
    import pytest
    events=[{'event_id':'one'}]
    paths=[]
    def run(video,anchors,received):
        if '_contour_prediction_cache' in received[0]:
            path=Path(received[0]['_contour_prediction_cache'])
            assert path.is_dir()
            paths.append(path)
            raise RuntimeError('worker failed')
        assert received is events
        return {},'COMPLETED'
    monkeypatch.setattr(tracking,'_bounded_tracks',run)
    assert tracking.bounded_tracks('video',[],events)==({},'COMPLETED')
    with pytest.raises(RuntimeError):
        tracking.bounded_tracks('video',[],events,reuse_predictions=True)
    assert events==[{'event_id':'one'}]
    assert len(paths)==1 and not paths[0].exists()


def test_empty_predictions_are_reused(tmp_path,monkeypatch):
    monkeypatch.setenv('SCOUTMEPLAY_MATCHROOM_ENGINE','opencv')
    m=Model();calls=[]
    def empty(image):calls.append(1);return []
    m.predict=empty;c=CachedSegmenter(m,tmp_path,'source');image=np.zeros((4,4,3),np.uint8)
    assert c.predict(image)==[]
    assert c.predict(image)==[]
    assert len(calls)==1
