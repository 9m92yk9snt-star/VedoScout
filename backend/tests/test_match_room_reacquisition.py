from copy import deepcopy
import time
import numpy as np
import match_room_reacquisition as recovery


def fixture():
    mask=np.zeros((120,160),np.uint8);mask[20:101,50:71]=1
    row={'mask':mask,'box':[50,20,21,81],'ground':[.375,100/120],'player_width':.13,'confidence':.9}
    frames=[{'media_ms':1000+i*33,'gray':np.zeros((120,160),np.uint8),'image':np.zeros((120,160,3),np.uint8)} for i in range(10)]
    rows=[[deepcopy(row)] for _ in frames]
    engine=recovery.AdaptiveAssociator(frames,[0,9],[{'x':.375,'y':.5}]*2,lambda i:rows[i],lambda i:rows[i])
    observations=[{'media_ms':frames[i]['media_ms'],'ground':row['ground'],'player_width':.13,'frame_id':f'f{i}'} for i in [0,9]]
    return engine,observations


def test_reacquisition_segments_require_both_source_observations():
    engine,obs=fixture()
    for i in range(1,9):engine.fill(i)
    result={'identity_link_passed_on_this_clip':True,'shared_frames':5,'samples':[{'media_ms':f['media_ms'],'ground':[.375,100/120],'player_width':.13,'detection_index':0} for f in engine.frames]}
    assert recovery.segments_for_review(engine,result,obs)[0]['identity_reference_frames']==['f0','f9']
    assert recovery.segments_for_review(engine,result,obs[:1])==[]
    assert recovery.segments_for_review(engine,result,[obs[0],{**obs[1],'ground':[.9,.9]}])==[]
    assert recovery.segments_for_review(engine,{**result,'identity_link_passed_on_this_clip':False},obs)==[]


def test_deadline_prevents_more_inference_and_locked_rows_cannot_be_replaced():
    engine,_=fixture();engine.fill(2);row=engine.rows[2];engine.locked.add(2);engine.fill(2,True);assert engine.rows[2] is row
    engine.deadline=time.monotonic()-1
    try:engine.fill(3)
    except TimeoutError:pass
    else:raise AssertionError('Expired inference was allowed')


def test_vector_votes_match_scalar_rounding_edges_repeats_and_empty():
    import match_room_contours as contours
    rng = np.random.default_rng(412)
    masks = [rng.integers(0, 3, (12, 17), dtype=np.uint8),
             np.zeros((12, 17), dtype=np.uint8), np.ones((12, 17), dtype=np.uint8)]
    points = np.array([[-.5, 0], [-.51, 0], [0, -.5], [0, -.51],
                       [16.49, 11.49], [16.5, 11.5], [17, 12],
                       [1.5, 2.5], [1.5, 2.5], [2.5, 3.5]])
    for mask in masks:
        for values in [points, points.astype(np.float32), points[::2],
                       rng.uniform(-5, 20, (100, 2)), np.empty((0, 2))]:
            original_mask, original_points = mask.copy(), values.copy()
            expected = sum(contours.owns(mask, point) for point in values)
            assert recovery.count_owned(mask, values) == expected
            np.testing.assert_array_equal(mask, original_mask)
            np.testing.assert_array_equal(values, original_points)


def test_vector_votes_preserve_nonfinite_scalar_behavior():
    import match_room_contours as contours
    points = np.array([[np.nan, 2], [3, np.inf], [-np.inf, 1], [1e30, 3], [1, 1]])
    mask = np.ones((4, 4), np.uint8)
    with np.errstate(invalid='ignore'):
        assert recovery.count_owned(mask, points) == sum(contours.owns(mask, point) for point in points)


def test_invalid_source_never_loads_recovery_model(monkeypatch):
    import player_segmentation_assets as assets
    engine, _ = fixture()
    originals = engine.frames
    seeds = [{'t': 1., 'target_point': {'x': .375, 'y': .5}},
             {'t': 1.297, 'target_point': {'x': .375, 'y': .5}}]
    def forbidden(*args, **kwargs):
        raise AssertionError('Invalid source must not load or verify a model')
    monkeypatch.setattr(assets, 'ensure_model_asset', forbidden)
    monkeypatch.setattr(recovery.cv2.dnn, 'readNetFromONNX', forbidden)
    gaps = deepcopy(originals)
    gaps[4]['media_ms'] += 100
    duplicate = deepcopy(originals)
    duplicate[4]['media_ms'] = duplicate[3]['media_ms']
    cut = deepcopy(originals)
    cut[4]['gray'][:] = 255
    for frames in (originals[:2], originals[2:], gaps, duplicate, cut):
        monkeypatch.setattr(recovery.contours, 'read_clip', lambda *args, frames=frames: iter(frames))
        assert recovery.reacquire('source', seeds, [], object(), (0,0,160,120), None, {}) == []


def test_expired_recovery_never_loads_model(monkeypatch):
    import pytest
    import player_segmentation_assets as assets
    engine, _ = fixture()
    seeds = [{'t': 1., 'target_point': {'x': .375, 'y': .5}},
             {'t': 1.297, 'target_point': {'x': .375, 'y': .5}}]
    monkeypatch.setattr(recovery.contours, 'read_clip', lambda *args: iter(engine.frames))
    monkeypatch.setattr(assets, 'ensure_model_asset', lambda *a: pytest.fail('Expired model load'))
    with pytest.raises(TimeoutError):
        recovery.reacquire('source', seeds, [], object(), (0,0,160,120), time.monotonic()-1, {})


def test_valid_recovery_keeps_verified_model_and_seed_inputs(monkeypatch):
    import player_segmentation_assets as assets
    engine, _ = fixture()
    seeds = [{'t': 1., 'target_point': {'x': .375, 'y': .5}},
             {'t': 1.297, 'target_point': {'x': .375, 'y': .5}}]
    calls = []
    net = object()
    monkeypatch.setattr(recovery.contours, 'read_clip', lambda *args: iter(engine.frames))
    monkeypatch.setattr(assets, 'ensure_model_asset', lambda path, sha: calls.append(('verify', path, sha)))
    def load(path):
        assert calls == [('verify', recovery.MODEL_PATH, recovery.MODEL_SHA256)]
        calls.append(('load', path))
        return net
    monkeypatch.setattr(recovery.cv2.dnn, 'readNetFromONNX', load)
    def select(frames, actual_seeds, model, *, deadline):
        assert frames[0] is engine.frames[0] and frames[1] is engine.frames[-1]
        assert actual_seeds is seeds and model.net is net
        calls.append(('select',))
        return None, {}, []
    monkeypatch.setattr(recovery.contours, 'select_seed_view', select)
    assert recovery.reacquire('source', seeds, [], object(), (0,0,160,120), None, {}) == []
    assert [c[0] for c in calls] == ['verify', 'load', 'select']


def textured_adaptive(kind=recovery.AdaptiveAssociator):
    engine, _ = fixture()
    rng = np.random.default_rng(812)
    image = rng.integers(0, 256, (120,160,3), dtype=np.uint8)
    source_frames = engine.frames + [{**engine.frames[-1], 'media_ms': 1330}]
    frames = [{**f, 'image': image.copy(),
               'gray': recovery.cv2.cvtColor(image, recovery.cv2.COLOR_BGR2GRAY)} for f in source_frames]
    mask = np.zeros((120,160),np.uint8)
    mask[20:101,50:71] = 1
    row = {'mask':mask, 'box':[50,20,21,81], 'ground':[.375,100/120],
           'player_width':.13, 'confidence':.9}
    return kind(frames, [0,len(frames)-1], [{'x':.375,'y':.5}]*2,
                lambda i:[deepcopy(row)], lambda i:[deepcopy(row)])


def test_new_detection_preserves_unaffected_optical_pairs(monkeypatch):
    engine = textured_adaptive()
    engine.fill(1)
    original = engine.pair(0,1,0)
    assert original['valid'] > 6 and original['votes'][0][0] > 6
    reverse = engine.pair(1,0,0)
    unaffected = engine.pair(0,9,0)
    def forbidden(*a, **k):
        raise AssertionError('Unchanged image pair must not recompute optical flow')
    monkeypatch.setattr(recovery.cv2, 'goodFeaturesToTrack', forbidden)
    engine.fill(2)
    assert engine.pair(0,1,0) is original
    assert engine.pair(1,0,0) is reverse
    assert engine.pair(0,9,0) is unaffected
    engine.fill(1, True)
    assert (0,1,0) not in engine.pair_cache
    assert (1,0,0) not in engine.pair_cache
    assert engine.pair(0,9,0) is unaffected


def test_upgraded_detection_recomputes_votes_in_both_directions():
    engine = textured_adaptive()
    engine.fill(1)
    before = engine.pair(0,1,0)
    engine.pair(1,0,0)
    def replacement(i):
        row = deepcopy(engine.rows[i][0])
        row['mask'][:] = 0
        return [row]
    engine.large_detect = replacement
    engine.fill(1, True)
    changed = [engine.pair(0,1,0), engine.pair(1,0,0)]
    assert changed[0] != before
    engine.pair_cache.clear()
    assert [engine.pair(0,1,0), engine.pair(1,0,0)] == changed


def test_selective_pair_reuse_preserves_complete_bidirectional_review(monkeypatch):
    class FullInvalidation(recovery.AdaptiveAssociator):
        def fill(self, i, large=False):
            before = (set(self.small_done),set(self.upgraded))
            super().fill(i,large)
            if before != (self.small_done,self.upgraded):
                self.pair_cache.clear()
    feature = recovery.cv2.goodFeaturesToTrack
    counts = []
    def counted(*args, **kwargs):
        counts[-1] += 1
        return feature(*args, **kwargs)
    monkeypatch.setattr(recovery.cv2,'goodFeaturesToTrack',counted)
    results = []
    for kind in (FullInvalidation, recovery.AdaptiveAssociator):
        counts.append(0)
        results.append(textured_adaptive(kind).review())
    assert results[0] == results[1]
    assert results[1]['identity_link_passed_on_this_clip']
    assert counts[1] < counts[0]
