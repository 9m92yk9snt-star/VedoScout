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
