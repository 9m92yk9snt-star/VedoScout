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
