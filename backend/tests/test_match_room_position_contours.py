from copy import deepcopy
import time
import numpy as np
import match_room_position_contours as localized


def fixture(monkeypatch):
    mask = np.zeros((100, 100), np.uint8)
    mask[20:80, 30:51] = 1
    row = {'mask': mask, 'box': [30, 20, 21, 60], 'ground': [.4, .79],
           'player_width': .2, 'confidence': .9}
    frames = [{'media_ms': t, 'gray': np.zeros((100, 100), np.uint8)} for t in range(0, 201, 50)]
    detections = [[deepcopy(row)] for _ in frames]
    path = dict.fromkeys(range(len(frames)), 0)
    monkeypatch.setattr(localized, 'follow_instance', lambda *a: path)
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
                                        diagnostics=diagnostic, on_segment=saved.append)
    assert len(saved) == len(result) == 1
    assert result[0]['samples'][-1]['media_ms'] == 200
    assert diagnostic['status'] == 'TIME_BUDGET'


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
    monkeypatch.setattr(localized, 'follow_instance', lambda f,r,i,j: {i:j})
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
