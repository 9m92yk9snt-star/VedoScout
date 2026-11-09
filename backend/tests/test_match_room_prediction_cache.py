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


def test_truncated_packed_mask_is_recomputed_not_zero_padded(tmp_path,monkeypatch):
    monkeypatch.setenv('SCOUTMEPLAY_MATCHROOM_ENGINE','opencv')
    m=Model();c=CachedSegmenter(m,tmp_path,'source');image=np.ones((4,4,3),np.uint8)
    c.predict(image);path=next(tmp_path.glob('*.npz'))
    with np.load(path,allow_pickle=False) as data:
        stored={key:data[key].copy() for key in data.files}
    stored['bits']=stored['bits'][:1]
    np.savez_compressed(path,**stored)
    assert c.predict(image)[0]['mask'].sum()==16
    assert m.calls==2


def test_invalid_cache_metadata_recomputes_instead_of_interrupting(tmp_path,monkeypatch):
    monkeypatch.setenv('SCOUTMEPLAY_MATCHROOM_ENGINE','opencv')
    m=Model();c=CachedSegmenter(m,tmp_path,'source');image=np.ones((4,4,3),np.uint8)
    c.predict(image);path=next(tmp_path.glob('*.npz'))
    with np.load(path,allow_pickle=False) as data:
        stored={key:data[key].copy() for key in data.files}
    stored['meta']='null'
    np.savez_compressed(path,**stored)
    assert c.predict(image)[0]['mask'].sum()==16
    assert m.calls==2


def test_pinned_onnx_runtime_exact_prediction_cache_parity(tmp_path, monkeypatch):
    """Use the real serving CPU engine, not just a fake predictor.

    This is a no-provider-call parity test. It does not approve full-report
    graphics, source identity, latency, or enabling the cache in production.
    """
    import cv2
    from native_player_segmentation import PersonSegmenter

    monkeypatch.setenv('SCOUTMEPLAY_MATCHROOM_ENGINE', 'onnxruntime')
    model = PersonSegmenter()  # Checks the SHA-pinned graph from repository parts.
    original = model.predict
    calls = []

    def counted(image):
        calls.append(1)
        return original(image)

    model.predict = counted
    image = np.full((160, 256, 3), (52, 128, 48), dtype=np.uint8)
    cv2.rectangle(image, (90, 24), (115, 120), (180, 80, 35), -1)
    cv2.circle(image, (102, 17), 12, (180, 80, 35), -1)

    first = CachedSegmenter(model, tmp_path, 'verified-source').predict(image)
    second = CachedSegmenter(model, tmp_path, 'verified-source').predict(image)
    assert calls == [1], 'Identical pixels must not cause a second ONNX inference'
    assert len(first) == len(second)
    for actual, reused in zip(first, second):
        assert actual['box'] == reused['box']
        assert actual['class_id'] == reused['class_id']
        assert actual['score'] == reused['score']
        assert np.array_equal(actual['mask'], reused['mask'])

    changed = image.copy()
    changed[0, 0, 0] ^= 1
    CachedSegmenter(model, tmp_path, 'verified-source').predict(changed)
    assert calls == [1, 1], 'Changed pixels must always run real inference'


def test_medium_refinement_reuses_only_identical_source_model_pixels(tmp_path, monkeypatch):
    import match_room_tracking as tracking
    import match_room_position_contours as contours
    import match_room
    monkeypatch.setenv('SCOUTMEPLAY_MATCHROOM_ENGINE', 'opencv')
    model = Model()
    monkeypatch.setattr(contours, 'refinement_model', lambda: model)
    monkeypatch.setattr(match_room, 'presentation_window', lambda event: (0, 250))
    image = np.ones((4, 4, 3), np.uint8)
    seen = []
    def render(video, observations, lo, hi, **kwargs):
        rows = kwargs['segmenter'].predict(image)
        seen.append((rows[0]['score'], rows[0]['mask'].copy()))
        rows[0]['mask'][:] = 0
        return []
    monkeypatch.setattr(contours, 'contour_segments', render)
    event = {'event_id': 'e', 'source_video_sha256': 'source',
             'localization_method': 'EXPLICIT_SOURCE_POSITIONS',
             'visual_samples': [{'media_ms': 0}],
             '_display_refinement_windows': [[0, 125], [125, 250]]}
    tracking.compute_refinement('video', [], [event])
    assert model.calls == 2  # Default remains uncached.
    scoped = {**event, '_contour_prediction_cache': str(tmp_path)}
    tracking.compute_refinement('video', [], [scoped])
    assert model.calls == 3
    tracking.compute_refinement('video', [], [scoped])
    assert model.calls == 3  # New wrapper can read the previous worker's entry.
    tracking.compute_refinement('video', [], [{**scoped, 'source_video_sha256': 'other'}])
    assert model.calls == 4
    model.sha256 = 'model-b'
    tracking.compute_refinement('video', [], [scoped])
    assert model.calls == 5
    image[0, 0, 0] = 0
    tracking.compute_refinement('video', [], [scoped])
    assert model.calls == 6
    assert all(score == .875 for score, _ in seen)
    assert all(mask.sum() == 16 for _, mask in seen[:-2])
    assert all(mask.sum() == 15 for _, mask in seen[-2:])
    assert '_contour_prediction_cache' not in event
