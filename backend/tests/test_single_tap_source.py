import hashlib
import json
from scripts.run_matchroom_single_tap_trial import prepare


def test_selected_original_tap_is_preserved_without_extra_identity_inputs(tmp_path):
    source = tmp_path / 'source'
    parts = source / 'video-parts'
    parts.mkdir(parents=True)
    for i in range(43):
        (parts / f'{i:03}.bin').write_bytes(bytes([i]))
    anchors = [{'t': i, 'box': {'x': .1, 'y': .2, 'w': .2, 'h': .3},
                'target_point': {'x': .2, 'y': .3}} for i in range(5)]
    data = json.dumps({'raw_marker_anchors': anchors}).encode()
    (source / 'anchors.json').write_bytes(data)
    (source / 'SHA256SUMS').write_text(
        hashlib.sha256(bytes(range(43))).hexdigest() + '  video/source.mp4\n' +
        hashlib.sha256(data).hexdigest() + '  anchors.json\n')
    video, selection = prepare(source, tmp_path / 'work', tap_index=4)
    assert video.read_bytes() == bytes(range(43))
    assert selection == {'raw_marker_anchors': [anchors[4]]}
    assert json.loads((source / 'anchors.json').read_text())['raw_marker_anchors'] == anchors


def test_trial_preserves_validated_complete_source_checkpoint(tmp_path, monkeypatch):
    import asyncio
    from scripts import run_sequence_report_trial as runner
    from types import SimpleNamespace
    video = tmp_path / 'source.mp4'
    video.write_bytes(b'source')
    anchors = {'raw_marker_anchors': [{'t': 1}]}
    prior = {'id': 'sequence-full-report-trial', 'full_report_status': 'failed',
             **anchors, 'sequence_retry': {'checkpoint': 'partial'},
             'sequence_audit': {'checkpoint': 'complete'},
             'sequence_timings': {'source_analysis_seconds': 772.645}}
    checkpoint = tmp_path / 'prior.json'
    checkpoint.write_text(json.dumps(prior))
    calls = []
    monkeypatch.setattr(runner.sequence_report_runtime, 'retained_retry', lambda *a: True)
    def validate(doc, source, selection):
        assert source == hashlib.sha256(b'source').hexdigest()
        assert selection == hashlib.sha256(json.dumps(anchors, sort_keys=True).encode()).hexdigest()
        calls.append('validated')
        return True
    monkeypatch.setattr(runner.sequence_report_runtime, 'retained_source', validate)
    def harness(video, doc, output, **kwargs):
        assert calls == ['validated']
        assert doc['sequence_audit'] == prior['sequence_audit']
        assert doc['sequence_timings'] == prior['sequence_timings']
        assert doc['sequence_audit'] is not prior['sequence_audit']
        async def finish(report_id):
            doc['full_report_status'] = 'ready'
        return {'generate_full_report_task': finish}, SimpleNamespace(doc=doc, states=[]), [], []
    monkeypatch.setattr(runner, 'server_harness', harness)
    asyncio.run(runner.trial(video, anchors, tmp_path / 'out', retry_document=checkpoint))
    import pytest
    monkeypatch.setattr(runner.sequence_report_runtime, 'retained_source', lambda *a: None)
    with pytest.raises(ValueError, match='COMPLETE_SOURCE_CHECKPOINT_CHANGED'):
        asyncio.run(runner.trial(video, anchors, tmp_path / 'rejected', retry_document=checkpoint))
