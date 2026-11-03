from copy import deepcopy
import numpy as np
import match_room_contours as contours


def fixture():
    mask = np.zeros((120, 160), np.uint8)
    mask[20:101, 50:71] = 1
    row = {'mask': mask, 'box': [50,20,21,81], 'ground': [.375, 100/120],
           'player_width': .13, 'confidence': .9}
    frames = [{'media_ms': 1000+i*33, 'gray': np.zeros((120,160), np.uint8)} for i in range(16)]
    detections = [[deepcopy(row)] for _ in frames]
    paths = [{i: 0 for i in range(9)}, {i: 0 for i in range(16)}]
    observations = [{'media_ms': 1033, 'ground': [.375, 100/120], 'player_width': .13, 'frame_id': 'f1'}]
    return frames, detections, paths, observations, [1033, 1396]


def test_two_anchors_with_checked_overlap_can_complete_one_direction():
    args = fixture()
    rows = contours.agree_segments(*args)
    assert len(rows) == 1 and len(rows[0]['samples']) == 16
    assert rows[0]['overlap_frames'] == 9


def test_paths_must_reach_both_taps_and_agree_on_shared_frames():
    args = list(fixture())
    args[2] = [{i:0 for i in range(8)}, {i:0 for i in range(8,16)}]
    assert contours.agree_segments(*args) == []
    args = list(fixture())
    args[2][1][5] = 1
    assert contours.agree_segments(*args) == []


def test_missing_contour_is_never_interpolated_or_kept_alive():
    args = list(fixture())
    args[1][6][0]['ground'] = None
    args[3].append({**args[3][0], 'media_ms': 1396, 'frame_id':'f2'})
    segments = contours.agree_segments(*args)
    assert len(segments) == 2
    assert all(s['media_ms'] != 1198 for g in segments for s in g['samples'])
    assert segments[0]['samples'][-1]['media_ms'] == 1165
    assert segments[1]['samples'][0]['media_ms'] == 1231


def test_source_observation_conflict_rejects_instead_of_moving_contour():
    args = list(fixture())
    args[3][0]['ground'] = [.8, .8]
    assert contours.agree_segments(*args) == []
    assert args[1][0][0]['ground'] == [.375, 100/120]


def test_either_visible_boot_can_support_a_stance_point():
    mask = np.zeros((120,160),np.uint8)
    mask[20:75,60:80] = 1
    mask[65:100,50:60] = 1
    mask[65:100,80:90] = 1
    row = {'mask':mask,'player_width':.25}
    for x in (55,85):
        assert contours.agrees_with_observation(row, {'ground':[x/160,99/120],'player_width':.25}, mask.shape)
    assert not contours.agrees_with_observation(row, {'ground':[70/160,30/120],'player_width':.25},mask.shape)


def test_partial_clipped_or_occluded_feet_have_no_ground_point():
    mask = np.zeros((120,160),np.uint8); mask[20:101,50:71] = 1
    assert contours.lower_contour(mask,[50,20,21,81]) is not None
    assert contours.lower_contour(mask,[50,20,21,81],[mask]) is None
    assert contours.lower_contour(mask,[50,20,21,110]) is None
    clipped=np.zeros_like(mask);clipped[30:,50:71]=1
    assert contours.lower_contour(clipped,[50,30,21,90]) is None


def test_packed_mask_preserves_exact_visible_pixels():
    mask=fixture()[1][0][0]['mask']
    packed={'mask_bits':np.packbits(mask),'mask_shape':mask.shape}
    assert np.array_equal(contours.measured_mask(packed),mask)


def test_scene_cut_ends_a_path_before_transport(monkeypatch):
    frames,detections,_,_,_=fixture()
    frames[1]['gray'][:]=255
    monkeypatch.setattr(contours,'transport',lambda *args: (_ for _ in ()).throw(AssertionError('cut crossed')))
    assert contours.follow(frames,detections,0,{'x':.375,'y':.5}) == {0:0}


def test_one_tap_or_no_observations_cannot_start_local_model(monkeypatch):
    monkeypatch.setattr(contours,'read_clip',lambda *args: (_ for _ in ()).throw(AssertionError('decoded')))
    anchor={'t':1.2,'box':{'x':.3,'y':.3,'w':.2,'h':.4},'target_point':{'x':.4,'y':.4}}
    assert contours.contour_segments('missing',[anchor],[],1000,2000)==[]
    assert contours.contour_segments('missing',[anchor],[{'ground':[.4,.7]}],1000,2000)==[]


def test_focused_view_requires_unique_ownership_at_both_original_taps(monkeypatch):
    frames, detections, _, _, _ = fixture()
    seeds = [{'target_point': {'x': .375, 'y': .5},
              'box': {'x': .3, 'y': .2, 'w': .2, 'h': .7}}]*2
    selected = [frames[0], frames[12]]
    calls = []
    def detect(frame, roi, model):
        calls.append((frame['media_ms'], roi))
        return [] if roi[0] == 0 else detections[0]
    monkeypatch.setattr(contours, 'detect_frame', detect)
    roi, cache, attempts = contours.select_seed_view(selected, seeds, object())
    assert [a['owners'] for a in attempts] == [[0, 0], [1, 1]]
    assert roi[0] > 0 and set(cache) == {1000, 1396}
    assert calls[2][1] == calls[3][1] == roi


def test_focused_view_does_not_choose_nearest_or_competing_person(monkeypatch):
    frames, detections, _, _, _ = fixture()
    seeds = [{'target_point': {'x': .375, 'y': .5},
              'box': {'x': .3, 'y': .2, 'w': .2, 'h': .7}}]*2
    monkeypatch.setattr(contours, 'detect_frame', lambda *args: detections[0]*2)
    roi, cache, attempts = contours.select_seed_view([frames[0], frames[12]], seeds, object())
    assert roi is None and cache == {}
    assert all(a['owners'] == [2, 2] for a in attempts)
    monkeypatch.setattr(contours, 'detect_frame', lambda *args: (_ for _ in ()).throw(AssertionError('deadline ignored')))
    assert contours.select_seed_view([frames[0], frames[12]], seeds, object(), deadline=0) == (None, {}, [])
