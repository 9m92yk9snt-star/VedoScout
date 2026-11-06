from copy import deepcopy
import json
import time
import numpy as np
import match_room_position_contours as localized


def test_overlapping_intervals_reuse_only_exact_window_geometry(monkeypatch):
    import match_room_contours as source
    import match_room_tracking as tracking
    mask = np.zeros((100, 100), np.uint8)
    mask[20:80, 30:51] = 1
    row = {'mask': mask, 'box': [30, 20, 21, 60], 'ground': [.4, .79],
           'player_width': .2, 'confidence': .9}
    obs = [{'frame_id': f'f{t}', 'media_ms': t, 'identity_status': 'CONFIRMED',
            'ground': [.4, .79], 'player_box': [.3, .2, .21, .6]} for t in (0, 100, 200, 300)]
    def stream(*args, **kwargs):
        for t in range(0, 301, 25):
            yield {'media_ms': t, 'gray': np.zeros((100, 100), np.uint8),
                   'image': np.zeros((100, 100, 3), np.uint8)}
    monkeypatch.setattr(source, 'read_clip', stream)
    monkeypatch.setattr(source, 'detect_frame', lambda *a: [deepcopy(row)])
    monkeypatch.setattr(localized, 'endpoint_pairs', lambda _: iter([(obs[0], obs[2]), (obs[1], obs[3])]))
    def intervals(frames, detections, pair, **kwargs):
        indices = [i for i, f in enumerate(frames) if pair[0]['media_ms'] <= f['media_ms'] <= pair[1]['media_ms']]
        return [{'indices': indices, 'instances': [0]*len(indices)}]
    monkeypatch.setattr(localized, 'agreed_intervals', intervals)
    monkeypatch.setattr(localized, 'supporting_observations', lambda *a: True)
    original_foreground, original_stance = tracking.foreground_polygons, localized.stance_bounds
    calls = {'foreground': 0, 'stance': 0}
    def foreground(*args):
        calls['foreground'] += 1
        return original_foreground(*args)
    def stance(*args):
        calls['stance'] += 1
        return original_stance(*args)
    monkeypatch.setattr(tracking, 'foreground_polygons', foreground)
    monkeypatch.setattr(localized, 'stance_bounds', stance)
    diagnostics = {}
    def run_window():
        return localized.contour_segments('unused', obs, 0, 300, deadline=time.monotonic()+5,
                                          diagnostics=diagnostics, segmenter=object(), audit_pairs=True)
    first = run_window()
    assert len(first) == 2
    assert sum(len(s['samples']) for s in first) == 18
    assert calls == {'foreground': 13, 'stance': 13}
    assert diagnostics['detector_frames'] == 13
    assert 0 <= diagnostics['detector_seconds'] < 5
    assert diagnostics['source_pairs_expected'] == 2
    assert diagnostics['source_pairs_reached'] == 2
    assert diagnostics['source_pairs_unreached'] == 0
    assert diagnostics['source_segments_accepted'] == 2
    assert diagnostics['source_pairs_no_agreement'] == 0
    assert diagnostics['last_decoded_ms'] == 300
    assert diagnostics['source_pair_results'] == [
        {'start_ms': 0, 'end_ms': 200, 'accepted_segments': 1, 'rejection_codes': []},
        {'start_ms': 100, 'end_ms': 300, 'accepted_segments': 1, 'rejection_codes': []},
    ]
    expected_polygons = original_foreground([{'class_id': 0, 'mask': mask}], 100, 100)
    for segment in first:
        for sample in segment['samples']:
            assert sample['foreground']['polygons'] == expected_polygons
            assert sample['stance_bounds'] == original_stance(row, 100)['stance_bounds']
    # Another source/window never inherits geometry from this invocation.
    second = run_window()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert calls == {'foreground': 26, 'stance': 26}
    assert diagnostics['detector_frames'] == 13  # reset for the new window
    # An unresolved mask at the shared endpoint remains unresolved in both
    # intervals; caching cannot turn a rejection into a drawable cutout.
    calls['foreground'] = 0
    def reject_shared_frame(*args):
        calls['foreground'] += 1
        return None if calls['foreground'] == 5 else original_foreground(*args)
    monkeypatch.setattr(tracking, 'foreground_polygons', reject_shared_frame)
    assert run_window() == []
    assert calls['foreground'] == 5
    assert diagnostics['source_pairs_missing_foreground'] >= 1
    # A diagnosed source conflict must not turn into an accepted segment.
    monkeypatch.setattr(localized, 'supporting_observations', lambda *a: False)
    assert run_window() == []
    assert diagnostics['source_pairs_source_conflict'] == 2
    assert diagnostics['source_segments_accepted'] == 0
    assert len(diagnostics['source_pair_results']) == 2
    assert all(item['rejection_codes'] == ['SOURCE_CONFLICT'] for item in diagnostics['source_pair_results'])
    assert all(item['accepted_segments'] == 0 for item in diagnostics['source_pair_results'])


def fixture(monkeypatch):
    mask = np.zeros((100, 100), np.uint8)
    mask[20:80, 30:51] = 1
    row = {'mask': mask, 'box': [30, 20, 21, 60], 'ground': [.4, .79],
           'player_width': .2, 'confidence': .9}
    frames = [{'media_ms': t, 'gray': np.zeros((100, 100), np.uint8)} for t in range(0, 201, 50)]
    detections = [[deepcopy(row)] for _ in frames]
    path = dict.fromkeys(range(len(frames)), 0)
    monkeypatch.setattr(localized, 'follow_instance', lambda *a, **k: path)
    obs = [{'frame_id': f'f{t}', 'media_ms': t, 'identity_status': 'CONFIRMED',
            'ground': [.4, .79], 'player_width': .2} for t in (0, 200)]
    return frames, detections, obs, path


def run(frames, rows, obs):
    return localized.agreed_intervals(frames, rows, obs, deadline=time.monotonic()+5)


def test_both_localized_endpoints_and_both_full_paths_must_agree(monkeypatch):
    frames, rows, obs, _ = fixture(monkeypatch)
    intervals = run(frames, rows, obs)
    assert intervals == [{'indices': [0, 1, 2, 3, 4], 'instances': [0]*5,
                           'reference_frames': ['f0', 'f200']}]


def test_unknown_identity_between_endpoints_is_not_filtered_out(monkeypatch):
    frames, rows, obs, _ = fixture(monkeypatch)
    obs.insert(1, {'frame_id': 'f100', 'media_ms': 100, 'identity_status': 'UNCERTAIN'})
    assert run(frames, rows, obs) == []


def test_competing_instance_and_unobserved_feet_are_rejected(monkeypatch):
    frames, rows, obs, _ = fixture(monkeypatch)
    rows[0].append(deepcopy(rows[0][0]))
    assert run(frames, rows, obs) == []
    rows[0].pop()
    rows[2][0]['ground'] = None
    assert run(frames, rows, obs) == []


def test_reverse_identity_conflict_or_missing_frame_rejects_interval(monkeypatch):
    frames, rows, obs, path = fixture(monkeypatch)
    for bad in ({**path, 2: 1}, {i: j for i, j in path.items() if i != 2}):
        monkeypatch.setattr(localized, 'follow_instance', lambda f, r, i, j: path if i == 0 else bad)
        assert run(frames, rows, obs) == []


def test_observation_without_exact_source_frame_is_not_snapped(monkeypatch):
    frames, rows, obs, _ = fixture(monkeypatch)
    obs[-1]['media_ms'] = 199
    assert run(frames, rows, obs) == []


def test_sparse_source_time_gap_is_not_bridged(monkeypatch):
    frames, rows, obs, _ = fixture(monkeypatch)
    frames[2]['media_ms'] = 149
    assert run(frames, rows, obs) == []


def test_completed_interval_is_checkpointed_before_later_decode_timeout(monkeypatch):
    import match_room_contours as source
    import native_player_segmentation as segmentation
    import match_room_tracking as tracking
    frames, rows, obs, _ = fixture(monkeypatch)
    for o in obs: o['player_box'] = [.3, .2, .21, .6]
    obs.append({**obs[-1], 'frame_id': 'f400', 'media_ms': 400})
    for frame in frames: frame['image'] = np.zeros((100, 100, 3), np.uint8)
    clock = [0]
    def stream(*args, **kwargs):
        yield from frames
        clock[0] = 99
        yield {'media_ms': 250, 'image': np.zeros((100,100,3), np.uint8), 'gray': frames[0]['gray']}
    monkeypatch.setattr(localized.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(source, 'read_clip', stream)
    monkeypatch.setattr(source, 'detect_frame', lambda *args: deepcopy(rows[0]))
    monkeypatch.setattr(segmentation, 'PersonSegmenter', lambda: object())
    monkeypatch.setattr(tracking, 'foreground_polygons', lambda *args: [[[.3,.2],[.5,.2],[.5,.8]]])
    saved, diagnostic = [], {}
    result = localized.contour_segments('unused', obs, 0, 400, deadline=100,
                                        diagnostics=diagnostic, on_segment=saved.append, audit_pairs=True)
    assert len(saved) == len(result) == 1
    assert result[0]['samples'][-1]['media_ms'] == 200
    assert diagnostic['status'] == 'TIME_BUDGET'
    assert diagnostic['source_pairs_expected'] == 2
    assert diagnostic['source_pairs_reached'] == 1
    assert diagnostic['source_pairs_unreached'] == 1
    assert diagnostic['last_decoded_ms'] == 200
    assert diagnostic['source_pair_results'][-1] == {
        'start_ms': 200, 'end_ms': 400, 'accepted_segments': 0,
        'rejection_codes': ['TIME_BUDGET_BEFORE_ENDPOINT']
    }
    # A normally finished decoder with no exact endpoint must not be
    # misclassified as a deadline overrun or invented source coverage.
    clock[0] = 0
    def missing_endpoint(*args, **kwargs):
        for t in (0, 50, 100, 150, 200):
            yield {'media_ms': t, 'gray': np.zeros((100,100), np.uint8),
                   'image': np.zeros((100,100,3), np.uint8)}
    monkeypatch.setattr(source, 'read_clip', missing_endpoint)
    diagnostic = {}
    segments = localized.contour_segments('unused', obs, 0, 400, deadline=100,
                                          diagnostics=diagnostic, audit_pairs=True)
    assert len(segments) == 1
    assert diagnostic['status'] == 'SUPPORTED_SOURCE_OBSERVATIONS'
    assert diagnostic['source_pairs_unreached'] == 1
    assert diagnostic['source_pair_results'][-1] == {
        'start_ms': 200, 'end_ms': 400, 'accepted_segments': 0,
        'rejection_codes': ['ENDPOINT_NOT_DECODED']
    }
    # Detailed audit is OFF for the real analysis path; enabling it is
    # observational only and cannot change accepted source-bound segments.
    default_diagnostics = {}
    default_segments = localized.contour_segments(
        'unused', obs, 0, 400, deadline=100, diagnostics=default_diagnostics
    )
    assert default_segments == segments
    assert 'source_pair_results' not in default_diagnostics
    assert default_diagnostics['source_pairs_unreached'] == 1


def test_recovery_window_gets_budget_first_without_duplicate_intervals():
    def row(t, valid=True):
        return {'media_ms':t, 'identity_status':'CONFIRMED' if valid else 'UNCERTAIN',
                'ground':[.4,.6] if valid else None, 'player_box':[.3,.3,.2,.3] if valid else None}
    obs=[row(t) for t in range(0,2001,125)]+[row(2125,False)]+[row(t) for t in (2250,2375,2500)]
    assert localized.observation_windows(obs,0,2500)==[(2250,2500),(0,1500),(1500,2000)]


def test_confirmed_hidden_feet_keep_endpoint_pair_but_unknown_identity_breaks_it():
    rows = [{'media_ms': t, 'identity_status': 'CONFIRMED', 'ground': [.4,.7] if t in (0,500) else None}
            for t in (0,125,250,375,500)]
    assert list(localized.endpoint_pairs(rows)) == [(rows[0], rows[-1])]
    rows[2]['identity_status'] = 'UNCERTAIN'
    assert list(localized.endpoint_pairs(rows)) == []


def test_automatic_bridge_keeps_source_ground_absent_and_corrects_camera(monkeypatch):
    import match_room_display_bridge as display
    import motion_compensation
    frames, rows, obs, path = fixture(monkeypatch)
    # The pitch moves right by 1px/frame; player's pitch-space stance is fixed.
    for i, row in enumerate(rows):
        row[0]['ground'] = [.4+i*.01, .79]
    obs[-1]['ground'] = rows[-1][0]['ground']
    rows[2][0]['ground'] = None
    monkeypatch.setattr(motion_compensation, 'estimate_camera', lambda *a: (np.array([[1,0,1],[0,1,0]]), 30))
    interval = localized.agreed_intervals(frames, rows, obs, deadline=time.monotonic()+5, allow_display_bridge=True)[0]
    positions = display.tracked_display_positions(frames, rows, interval, deadline=time.monotonic()+5)
    assert np.allclose(positions[2]['display_ground'], [.42,.79])
    assert positions[2]['source_ground_observation'] is False
    assert rows[2][0]['ground'] is None
    monkeypatch.setattr(motion_compensation, 'estimate_camera', lambda *a: (None, 'cut'))
    assert display.tracked_display_positions(frames, rows, interval, deadline=time.monotonic()+5) is None


def test_display_bridge_still_rejects_reverse_identity_conflict(monkeypatch):
    frames, rows, obs, path = fixture(monkeypatch)
    rows[2][0]['ground'] = None
    monkeypatch.setattr(localized, 'follow_instance', lambda f,r,i,j: path if i == 0 else {**path, 2: 1})
    assert localized.agreed_intervals(frames, rows, obs, deadline=time.monotonic()+5, allow_display_bridge=True) == []


def test_confirmed_pose_without_segmenter_foot_uses_bound_source_endpoint(monkeypatch):
    import match_room_display_bridge as display
    import motion_compensation
    frames, rows, obs, _ = fixture(monkeypatch)
    for row in rows: row[0]['ground'] = None
    monkeypatch.setattr(motion_compensation, 'estimate_camera', lambda *a: (np.array([[1,0,0],[0,1,0]]), 30))
    interval = localized.agreed_intervals(frames, rows, obs, deadline=time.monotonic()+5, allow_display_bridge=True)[0]
    positions = display.tracked_display_positions(frames, rows, interval, deadline=time.monotonic()+5)
    assert len(positions) == len(frames)
    assert positions[0]['display_origin'] == 'BOUND_SOURCE_OBSERVATION'
    assert all(np.allclose(v['display_ground'], [.4,.79]) for v in positions.values())
    assert all(row[0]['ground'] is None for row in rows)
    obs[0]['ground'] = [.8,.79]  # A nearby different player cannot seed the path.
    assert localized.agreed_intervals(frames, rows, obs, deadline=time.monotonic()+5, allow_display_bridge=True) == []


def test_missing_foot_and_box_do_not_split_confirmed_identity_window():
    rows = [{'media_ms': t, 'identity_status': 'CONFIRMED', 'ground': [.4,.7] if t in (0,500) else None}
            for t in (0,125,250,375,500)]
    assert localized.observation_windows(rows, 0, 500) == [(0,500)]


def test_observed_body_box_rejects_opponents_nearby_boot(monkeypatch):
    frames, rows, obs, _ = fixture(monkeypatch)
    for observation in obs: observation['player_box'] = [.3,.2,.21,.6]
    other = deepcopy(rows[0][0]); other['box'] = [45,0,35,80]
    rows[0].append(other)
    assert len(run(frames, rows, obs)) == 1
    rows[0][1]['box'] = rows[0][0]['box']
    assert run(frames, rows, obs) == []


def test_reversible_features_can_complete_but_not_contradict_contour_path(monkeypatch):
    frames, rows, obs, path = fixture(monkeypatch)
    monkeypatch.setattr(localized, 'follow_instance', lambda f,r,i,j: {0:0} if i == 0 else {4:0})
    monkeypatch.setattr(localized, 'feature_paths', lambda *a: (path, path))
    assert len(localized.agreed_intervals(frames, rows, obs, deadline=time.monotonic()+5, allow_display_bridge=True)) == 1
    monkeypatch.setattr(localized, 'follow_instance', lambda f,r,i,j: {0:0,1:1} if i == 0 else {4:0})
    assert localized.agreed_intervals(frames, rows, obs, deadline=time.monotonic()+5, allow_display_bridge=True) == []


def test_endpoint_presentation_is_bound_to_source_bodies_and_keeps_estimates_separate(monkeypatch):
    import cv2
    import motion_compensation
    from match_room_display_bridge import tracked_display_positions
    frames, rows, obs, _ = fixture(monkeypatch)
    for row in rows:
        row[0]['_appearance'] = np.array([[1.,0.]], dtype=np.float32)
    for o in obs: o['player_box'] = [.3,.2,.21,.6]
    interval = localized.source_bound_display_interval(frames, rows, obs)
    assert interval['presentation_only']
    assert interval['instances'] == [0,None,None,None,0]
    monkeypatch.setattr(motion_compensation, 'estimate_camera', lambda *a: (np.array([[1,0,0],[0,1,0]]), 30))
    display = tracked_display_positions(frames, rows, interval, deadline=time.monotonic()+5)
    assert len(display) == 3
    assert all(v['display_estimated'] and not v['source_ground_observation'] for v in display.values())
    assert all(row[0]['ground'] == [.4,.79] for row in rows)
    bad = deepcopy(obs);bad.insert(1, {'media_ms':100,'identity_status':'UNCERTAIN'})
    assert localized.source_bound_display_interval(frames, rows, bad) is None
    rows[-1][0]['_appearance'] = np.array([[0.,1.]], dtype=np.float32)
    assert localized.source_bound_display_interval(frames, rows, obs) is None
    rows[-1][0]['_appearance'] = rows[0][0]['_appearance']
    rows[-1].append(deepcopy(rows[-1][0]))
    assert localized.source_bound_display_interval(frames, rows, obs) is None


def test_presentation_curve_cannot_leave_intermediate_source_body(monkeypatch):
    frames, rows, obs, _ = fixture(monkeypatch)
    support = [{'media_ms':100,'identity_status':'CONFIRMED','player_box':[.3,.2,.21,.6]}]
    interval = {'indices':list(range(5))}
    assert localized.display_fits_source_bodies(frames,interval,{2:{'display_ground':[.4,.79]}},support)
    assert not localized.display_fits_source_bodies(frames,interval,{2:{'display_ground':[.8,.79]}},support)


def test_contact_observations_do_not_create_sub_frame_count_holes():
    rows = [{'media_ms': t, 'identity_status':'CONFIRMED', 'ground':[.4,.7]} for t in (0,17,133,150,267)]
    pairs = list(localized.endpoint_pairs(rows))
    assert all(b['media_ms']-a['media_ms'] >= 125 for a,b in pairs)
    assert pairs[0][0] is rows[0] and pairs[-1][1] is rows[-1]


def test_automatic_flow_exports_endpoint_estimates_without_pixel_identity_claim(monkeypatch):
    import match_room_contours as source
    import native_player_segmentation as segmentation
    import match_room_tracking as tracking
    import motion_compensation
    frames, rows, obs, _ = fixture(monkeypatch)
    for o in obs: o['player_box'] = [.3,.2,.21,.6]
    for frame in frames: frame['image'] = np.zeros((100,100,3), np.uint8)
    monkeypatch.setattr(localized, 'follow_instance', lambda f,r,i,j, **k: {i:j})
    monkeypatch.setattr(localized, 'feature_paths', lambda *a: ({},{}))
    monkeypatch.setattr(source, 'read_clip', lambda *a,**kw: (f for f in deepcopy(frames)))
    monkeypatch.setattr(source, 'detect_frame', lambda *a: deepcopy(rows[0]))
    monkeypatch.setattr(segmentation, 'PersonSegmenter', lambda: object())
    monkeypatch.setattr(tracking, 'foreground_polygons', lambda *a: [[[.3,.2],[.5,.2],[.5,.8]]])
    monkeypatch.setattr(motion_compensation, 'estimate_camera', lambda *a: (np.array([[1,0,0],[0,1,0]]),30))
    segments = localized.contour_segments('unused',obs,0,200,deadline=time.monotonic()+5,diagnostics={})
    assert segments[0]['identity_method'] == 'SOURCE_CONFIRMED_ENDPOINT_BRIDGE'
    middle = segments[0]['samples'][2]
    assert middle['ground'] is None and middle['display_ground'] == [.4,.79]
    assert middle['source_ground_observation'] is False
    monkeypatch.setattr(motion_compensation, 'estimate_camera', lambda *a: (None,'failure'))
    assert localized.contour_segments('unused',obs,0,200,deadline=time.monotonic()+5,diagnostics={}) == []


def test_middle_source_knot_is_shared_by_overlapping_curves_without_rewriting_measurements(monkeypatch):
    frames, rows, obs, _ = fixture(monkeypatch)
    rows[2][0]['ground'] = None
    middle = {'frame_id':'f100','media_ms':100,'identity_status':'CONFIRMED','ground':[.43,.77]}
    obs.insert(1,middle)
    interval = {'indices':list(range(5)), 'instances':[0]*5}
    localized.bind_source_display_knots(frames, rows, interval, obs)
    assert interval['source_endpoint_ground'] == {2:[.43,.77]}
    assert rows[2][0]['ground'] is None
    assert rows[0][0]['ground'] == [.4,.79]
    middle['identity_status'] = 'UNCERTAIN'
    other = {'indices':list(range(5)), 'instances':[0]*5}
    localized.bind_source_display_knots(frames, rows, other, obs)
    assert other['source_endpoint_ground'] == {}



def test_window_camera_cache_preserves_bridge_and_failed_estimates(monkeypatch):
    import match_room_display_bridge as display
    import motion_compensation
    frames, rows, obs, path = fixture(monkeypatch)
    rows[2][0]['ground'] = None
    interval = localized.agreed_intervals(frames, rows, obs, deadline=time.monotonic()+5, allow_display_bridge=True)[0]
    calls=[]
    def estimate(*args):
        calls.append(1)
        return np.array([[1.,0,0],[0,1.,0]]),30
    monkeypatch.setattr(motion_compensation, 'estimate_camera', estimate)
    expected=display.tracked_display_positions(frames,rows,interval,deadline=time.monotonic()+5)
    n=len(calls);cache={}
    actual=display.tracked_display_positions(frames,rows,interval,deadline=time.monotonic()+5,camera_cache=cache)
    assert actual==expected and len(calls)==2*n
    assert display.tracked_display_positions(frames,rows,interval,deadline=time.monotonic()+5,camera_cache=cache)==expected
    assert len(calls)==2*n
    # A new window must calculate again; failed estimates are cached too.
    failed=[]
    monkeypatch.setattr(motion_compensation,'estimate_camera',lambda *args:(failed.append(1) or None,'unavailable'))
    fresh={}
    assert display.tracked_display_positions(frames,rows,interval,deadline=time.monotonic()+5,camera_cache=fresh) is None
    assert display.tracked_display_positions(frames,rows,interval,deadline=time.monotonic()+5,camera_cache=fresh) is None
    assert len(failed)==1


def test_offline_profiler_accepts_only_source_bound_short_windows():
    """Long event playback can be investigated without weakening source gates."""
    import pytest
    from scripts.profile_matchroom_contours import source_window
    room = {'start_ms': 10000, 'end_ms': 12500}
    assert source_window(room, 10000, 11500) == (10000, 11500)
    assert source_window(room, 11000, 12500) == (11000, 12500)
    assert source_window({'start_ms': 100, 'end_ms': 200}) == (100, 200)
    for start, end in (
        (None, None), (None, 11500), (10000, None),
        (9999, 11000), (11000, 12501), (10000, 12000),
        (11000, 11000), (11500, 11000),
    ):
        with pytest.raises(ValueError):
            source_window(room, start, end)
