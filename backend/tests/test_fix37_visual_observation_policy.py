"""Source/model policy regressions; replies below are explicit test doubles."""
import ast
import hashlib
from pathlib import Path

import pytest

import precision_engine as precision
import video_model_input as video


@pytest.mark.parametrize('builder', [precision.build_preview_prompt, precision.build_full_prompt])
def test_music_or_legacy_volume_rows_cannot_change_the_analysis_prompt(builder):
    fingerprint = precision.PlayerFingerprint('#fff', 'white', '#000', 'black', 2., None, {}, 'ok')
    kwargs = dict(base_prompt='Player {player_details}', fingerprint=fingerprint,
                  player_details={'player_name': 'Selected player'})
    empty = builder(**kwargs, audio_events=[])
    loud = builder(**kwargs, audio_events=[precision.AudioEvent(9123.45, 80., 'goal')])
    assert loud == empty
    assert '9123.45' not in loud and 'AUDIO EVIDENCE' not in loud
    assert 'State clearly observed actions directly' in loud
    assert 'Missing sound cannot' in loud and 'Preserve uncertainty' in loud


def test_report_generation_and_recovery_no_longer_call_the_audio_extractor():
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'server.py').read_text())
    # A load also catches passing it to asyncio.to_thread, not just direct calls.
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Load) and node.id == 'extract_audio_events']
    task = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'generate_full_report_task')
    assert not any(isinstance(n, ast.AsyncFunctionDef) and n.name == '_audio_core' for n in ast.walk(task))


def test_uncertain_or_unknown_model_data_is_never_rewritten_as_confirmed():
    observation = {'details': 'He might have scored; the ball is possibly beyond the line.',
                   'outcome': 'UNKNOWN', 'confidence': 'low', 'source_ms': [1000, 1033],
                   'nested': [None, {'same_ball': False, 'evidence_note': 'Likely a stationary spare.'}]}
    assert precision.scrub_hedging(observation) == observation
    assert 'did scored' not in precision.scrub_hedging(observation)['details']


async def test_same_single_video_request_carries_visual_policy_without_altering_source(monkeypatch, tmp_path):
    source, reference = tmp_path/'source.mp4', tmp_path/'reference.jpg'
    source.write_bytes(b'unchanged source including any soundtrack')
    reference.write_bytes(b'original selected-player pixels')
    calls = []
    def direct(*args):
        calls.append(args)
        return {'raw_response': '{"outcome":"UNKNOWN"}'}
    monkeypatch.setattr(video, '_direct_gemini_video', direct)
    result = await video.read_video('test-key', 'policy', 'Observe this sequence.', str(source), [str(reference)],
                                   transport='gemini-rest', fps=8., system_message='Preserve schema.')
    assert len(calls) == 1
    args = calls[0]
    assert args[1:5] == ('Observe this sequence.', str(source), [str(reference)], 8.)
    assert args[5].startswith(video.VISUAL_OBSERVATION_POLICY)
    assert 'Preserve schema.' in args[5]
    audit = result['video_input']
    assert audit['event_evidence_policy'] == 'VISUAL_OBSERVATION_ONLY'
    assert audit['model_video_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert audit['reference_sha256'] == [hashlib.sha256(reference.read_bytes()).hexdigest()]
    assert audit['system_instruction_sha256'] == hashlib.sha256(args[5].encode()).hexdigest()
    assert result['raw_response'] == '{"outcome":"UNKNOWN"}'
