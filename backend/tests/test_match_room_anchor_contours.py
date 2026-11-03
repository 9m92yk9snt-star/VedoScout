from copy import deepcopy
import time
import numpy as np
import match_room_anchor_contours as anchored


def fixture(monkeypatch):
    mask = np.zeros((100, 100), np.uint8)
    mask[20:80, 30:51] = 1
    row = {'mask': mask, 'box': [30, 20, 21, 60], 'ground': [.4, .79], 'player_width': .2, 'confidence': .9}
    frames = [{'media_ms': t, 'gray': np.zeros((100, 100), np.uint8)} for t in range(900, 1401, 50)]
    detections = [[deepcopy(row)] for _ in frames]
    path = dict.fromkeys(range(len(frames)), 0)
    monkeypatch.setattr(anchored, 'follow', lambda *args: path)
    monkeypatch.setattr(anchored, 'follow_instance', lambda *args: path)
    anchor = {'t': .9, 'box': {'x': .3, 'y': .2, 'w': .2, 'h': .6}, 'target_point': {'x': .4, 'y': .5}}
    obs = [{'frame_id': f'f{t}', 'media_ms': t, 'ground': [.4, .79], 'player_width': .2} for t in (1100, 1350)]
    return frames, detections, anchor, obs, path


def test_one_real_tap_and_two_source_observations_must_all_agree(monkeypatch):
    frames, rows, anchor, obs, _ = fixture(monkeypatch)
    before = deepcopy(obs)
    result = anchored.validate_path(frames, rows, 0, anchor, obs, 1000, 1400)
    assert result['reference_frames'] == ['f1100', 'f1350']
    assert len(result['proof']) == 9 and result['overlap_frames'] == 11
    assert obs == before
    assert anchored.validate_path(frames, rows, 0, anchor, obs[:1], 1000, 1400) is None


def test_wrong_competing_or_unmeasured_source_position_rejects_whole_path(monkeypatch):
    frames, rows, anchor, obs, _ = fixture(monkeypatch)
    for changed in [{**obs[0], 'ground': [.8, .8]}, {**obs[0], 'media_ms': 1110}]:
        assert anchored.validate_path(frames, rows, 0, anchor, [changed, obs[1]], 1000, 1400) is None
    rows[4].append(deepcopy(rows[4][0]))
    assert anchored.validate_path(frames, rows, 0, anchor, obs, 1000, 1400) is None
    rows[4].pop()
    rows[6][0]['ground'] = None
    assert anchored.validate_path(frames, rows, 0, anchor, obs, 1000, 1400) is None


def test_reverse_path_cannot_skip_the_tap_or_disagree_on_identity(monkeypatch):
    frames, rows, anchor, obs, path = fixture(monkeypatch)
    for bad in [{i: v for i, v in path.items() if i != 0}, {**path, 5: 1}]:
        monkeypatch.setattr(anchored, 'follow_instance', lambda *args: bad)
        assert anchored.validate_path(frames, rows, 0, anchor, obs, 1000, 1400) is None


def test_missing_identity_and_truncated_source_frames_reject_whole_clip(monkeypatch):
    frames, rows, anchor, obs, path = fixture(monkeypatch)
    assert anchored.validate_path(frames[:-1], rows[:-1], 0, anchor, obs, 1000, 1400) is None
    monkeypatch.setattr(anchored, 'follow', lambda *args: {i: v for i, v in path.items() if i != 7})
    assert anchored.validate_path(frames, rows, 0, anchor, obs, 1000, 1400) is None


def test_ineligible_context_does_not_start_decoding(monkeypatch):
    _, _, anchor, obs, _ = fixture(monkeypatch)
    monkeypatch.setattr(anchored, 'read_clip', lambda *a, **k: (_ for _ in ()).throw(AssertionError('decoded')))
    for anchors, observations in [([], obs), ([anchor], obs[:1]), ([{**anchor, 't': .1}], obs),
                                  ([{**anchor, 'player_behind': True}], obs), ([anchor, anchor], obs)]:
        assert anchored.anchor_observation_segments('video', anchors, observations, 1000, 1400,
                                                    deadline=time.monotonic()+10, diagnostics={}) == []


def test_output_keeps_one_tap_and_fresh_masks_on_every_proof_frame(monkeypatch):
    import native_player_segmentation
    frames, rows, anchor, obs, _ = fixture(monkeypatch)
    def decode(video, start, end, **kwargs):
        assert kwargs == {'sample_step': 0}
        for f in frames:
            yield {**f, 'image': np.zeros((100, 100, 3), np.uint8)}
    monkeypatch.setattr(anchored, 'read_clip', decode)
    monkeypatch.setattr(anchored, 'detect_frame', lambda frame, *a: rows[(frame['media_ms']-900)//50])
    monkeypatch.setattr(native_player_segmentation, 'PersonSegmenter', lambda: object())
    diagnostics = {}
    result = anchored.anchor_observation_segments('video', [anchor], obs, 1000, 1400,
                                                  deadline=time.monotonic()+10, diagnostics=diagnostics)
    assert result[0]['seed_ms'] == [900]
    assert result[0]['observation_reference_frames'] == ['f1100', 'f1350']
    assert len(result[0]['samples']) == 9
    assert all(s['foreground']['media_ms'] == s['media_ms'] for s in result[0]['samples'])
    assert diagnostics['method'] == anchored.METHOD
