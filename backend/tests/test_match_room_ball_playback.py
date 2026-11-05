from copy import deepcopy
import time
import numpy as np
import cv2
import match_room_ball_playback as playback


def fixture(monkeypatch):
    import player_tracking, motion_compensation, native_player_segmentation, video_timebase
    images = [np.full((100, 100, 3), i, np.uint8) for i in range(3)]
    frames = [(1+i*.05, im[:, :, 0], None, None) for i, im in enumerate(images)]
    class Capture:
        index = 0
        def retrieve(self): return True, images[self.index]
        def release(self): pass
    cap = Capture()
    monkeypatch.setattr(cv2, 'VideoCapture', lambda _: cap)
    def read(*a, **k):
        for row, image in zip(frames, images):
            k['on_frame'](row[0], image)
        return frames
    monkeypatch.setattr(player_tracking, '_read_window', read)
    monkeypatch.setattr(player_tracking, '_cut_flags', lambda _: [False]*3)
    monkeypatch.setattr(motion_compensation, 'estimate_camera', lambda *a: (np.array([[1., 0, 10], [0, 1, 0]]), 20))
    monkeypatch.setattr(video_timebase, 'seek_with_preroll', lambda *a: (True, 1., False))
    def grab(_):
        cap.index += 1
        return True, 1+cap.index*.05, False
    monkeypatch.setattr(video_timebase, 'grab_frame_time_seconds', grab)
    calls = []
    def infer(image):
        calls.append(int(image[0, 0, 0]))
        mask = np.zeros(image.shape[:2], np.uint8)
        mask[5:15, 30+calls[-1]:40+calls[-1]] = 1
        return [{'class_id': 0, 'mask': mask}], 'model'
    monkeypatch.setattr(native_player_segmentation, '_instances', infer)
    event = {'canonical_action_type': 'PASS', 'canonical_outcome': 'COMPLETED', 'contact_ms': 1000,
             'causal_chain': {'receiver_visual_id': 'p7'}, 'proof': {'proof_start_ms': 1000, 'proof_end_ms': 1100}}
    observations = [{'frame_id': 'release', 'media_ms': 1000, 'ball': [.4, .7], 'ball_phase': 'RELEASE'},
                    {'frame_id': 'receive', 'media_ms': 1100, 'ball': [.3, .7], 'ball_phase': 'RECEIVED', 'receiver': 'p7',
                     'ball_motion_start_ms': 1000, 'ball_motion_method': 'BACKGROUND_AFFINE_PASS_ENDPOINTS'}]
    return event, observations, calls


def test_moving_direction_compensates_camera_and_measures_every_foreground(monkeypatch):
    event, observations, calls = fixture(monkeypatch)
    original = deepcopy(observations)
    sequences, _ = playback.build_ball_playback('video', event, observations, time.monotonic()+10)
    rows = sequences[0]['samples']
    assert calls == [0, 1, 2]
    assert np.allclose(rows[1]['ballTrail'], [[.5, .7], [.2, .7]])
    assert rows[0]['foreground']['polygons'] != rows[1]['foreground']['polygons']
    assert all(s['foreground']['media_ms'] == s['media_ms'] for s in rows)
    assert sequences[0]['reference_frames'] == ['release', 'receive']
    assert observations == original


def test_one_missing_foreground_discards_whole_sequence(monkeypatch):
    import native_player_segmentation
    event, observations, _ = fixture(monkeypatch)
    original = native_player_segmentation._instances
    monkeypatch.setattr(native_player_segmentation, '_instances', lambda image: ([], 'model') if image[0, 0, 0] == 1 else original(image))
    assert playback.build_ball_playback('video', event, observations, time.monotonic()+10)[0] == []


def test_camera_failure_cut_and_budget_never_publish_partial_arrows(monkeypatch):
    import motion_compensation, player_tracking
    event, observations, calls = fixture(monkeypatch)
    assert playback.build_ball_playback('video', event, observations, time.monotonic())[0] == []
    monkeypatch.setattr(player_tracking, '_cut_flags', lambda _: [False, True, False])
    assert playback.build_ball_playback('video', event, observations, time.monotonic()+10)[0] == []
    monkeypatch.setattr(player_tracking, '_cut_flags', lambda _: [False]*3)
    monkeypatch.setattr(motion_compensation, 'estimate_camera', lambda *a: (None, 'features'))
    assert playback.build_ball_playback('video', event, observations, time.monotonic()+10)[0] == []
    assert calls == []


def test_pass_still_requires_the_same_release_and_receiver(monkeypatch):
    event, observations, calls = fixture(monkeypatch)
    for bad in [{**event, 'canonical_outcome': 'INCOMPLETE'}, {**event, 'contact_ms': 1300},
                {**event, 'causal_chain': {'receiver_visual_id': 'other'}}]:
        assert playback.build_ball_playback('video', bad, observations, time.monotonic()+10)[0] == []
    assert calls == []


def test_encoded_clip_preserves_source_frame_times_including_vfr_gaps(tmp_path, monkeypatch):
    import ast
    import shutil
    import subprocess
    import sys
    import types
    from pathlib import Path
    import match_room_tracking
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        import pytest
        pytest.skip('ffmpeg required for source PTS encoding check')
    source = tmp_path/'source.mp4'
    subprocess.run([ffmpeg, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=96x64:rate=30:duration=2',
                    '-vf', r'select=not(eq(n\,10)+eq(n\,15))', '-vsync', '0', '-c:v', 'libx264', str(source)], check=True)
    tree = ast.parse((Path(__file__).parents[1]/'sequence_report_runtime.py').read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'render_assets')
    namespace = {'Path': Path, 'pilot': types.SimpleNamespace(digest=lambda _: 'source'), 'attach_clip_authority': lambda *a: None}
    exec(compile(ast.Module(body=[next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'validate_rendered_clip'), function], type_ignores=[]), '<renderer>', 'exec'), namespace)
    monkeypatch.setitem(sys.modules, 'media_binaries', types.SimpleNamespace(FFMPEG_BIN=ffmpeg))
    monkeypatch.setattr(match_room_tracking, 'bounded_tracks', lambda *a: ({}, 'NO_TRACK_INPUT'))
    event = {'canonical_action_type': 'DRIBBLE', 'canonical_ms': 1000, 'event_id': 'e', 'source_video_sha256': 'source',
             'proof': {'proof_start_ms': 1007, 'proof_end_ms': 1100, 'frame_ms': 1000, 'frame_id': 'f'}}
    row = {'event_id': 'e', 'sequence_event_native': True, 'source_video_sha256': 'source', 'evidence_time_ms': 1000,
           'source_frame_id': 'f', 'evidence_id': 'proof'}
    assets = namespace['render_assets'](source, {'video_comments': [row]}, {'source_video_sha256': 'source', 'events': [event]}, tmp_path/'assets')
    def times(path):
        cap = cv2.VideoCapture(str(path)); values = []
        while cap.grab(): values.append(cap.get(cv2.CAP_PROP_POS_MSEC))
        cap.release()
        return np.array(values)
    origin = row['tele_clip_start']*1000
    assert abs(origin-266.667) < .001  # requested 257ms was between frames
    source_times = times(source)
    expected = source_times[(source_times >= origin-.001) & (source_times < row['tele_clip_end']*1000)]
    encoded = times(assets[0][2])+origin
    assert len(encoded) == len(expected)
    assert np.max(np.abs(encoded-expected)) < 1
    assert np.max(np.diff(encoded)) > 60  # absent frames were not duplicated
    assert row['tele_clip_timebase'] == 'SOURCE_PTS_ALIGNED'


def test_source_cache_limit_preserves_original_streaming_fallback(monkeypatch):
    event, observations, calls = fixture(monkeypatch)
    monkeypatch.setattr(playback, 'MAX_SOURCE_CACHE_BYTES', 1)
    sequences, diagnostic = playback.build_ball_playback('video', event, observations, time.monotonic()+10)
    assert calls == [0, 1, 2]
    assert len(sequences[0]['samples']) == 3
    assert not diagnostic['failures']
