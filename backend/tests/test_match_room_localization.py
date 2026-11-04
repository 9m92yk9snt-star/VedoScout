"""Synthetic orchestration controls; not visual accuracy evidence."""
import asyncio
from copy import deepcopy
import json
import numpy as np
import pytest
import match_room_localization as loc
from test_match_room_position_evidence import fixture


def test_prepare_preserves_all_ten_original_reference_points(tmp_path, monkeypatch):
    anchors = [{'t': i, 'target_point': {'x': .4, 'y': .5},
                'box': {'x': .3, 'y': .3, 'w': .2, 'h': .3}} for i in range(10)]
    selection = {'raw_marker_anchors': anchors}
    event = {'event_id': 'e', 'source_video_sha256': 'source', 'proof': {
        'proof_start_ms': 2000, 'proof_end_ms': 6000, 'frame_ms': 3000,
        'cited_frames': {'s000003000': 3000}}}
    monkeypatch.setattr(loc.cv2, 'VideoCapture', lambda _: type('Cap', (), {'release': lambda self: None})())
    monkeypatch.setattr(loc, 'read_frame_at', lambda cap, t: (True, np.zeros((80, 60, 3), np.uint8), t))
    batches = []
    def grouped(cap, times):
        batches.append(times)
        return {ms: (ms, np.zeros((80, 60, 3), np.uint8)) for ms in times}
    monkeypatch.setattr(loc, 'read_frames_at', grouped)
    before = deepcopy(selection)
    record, job = loc.prepare('source', selection, event, tmp_path)
    assert batches and max(map(len, batches)) <= 8
    assert [ms for batch in batches for ms in batch] == sorted({f['media_ms'] for f in record['frames']})
    assert len(record['references']) == 10 and selection == before
    assert [r['target_point'] for r in record['references']] == [a['target_point'] for a in anchors]
    assert record['window_ms'] == [2250, 4750]
    assert job['packet_id'] == 'positions_e'
    assert record['request']['payload_bytes'] < 19_500_000


def setup(monkeypatch):
    event, selection, record = fixture()
    selection['raw_marker_anchors'][0]['box'] = {'x': .2, 'y': .2, 'w': .3, 'h': .4}
    record['original_selection_values_sha256'] = loc.selection_digest(selection)
    record['receipt']['packet_id'] = loc.packet_id(event)
    doc = {**selection, 'canonical_events': {'source_video_sha256': 'source', 'events': [event]},
           'full_report': {'video_comments': [{'event_id': event['event_id']}]}}
    monkeypatch.setattr(loc.pilot, 'digest', lambda _: 'source')
    def prepare(video, selected, actual_event, work):
        assert selected == selection and actual_event == event
        return {k: deepcopy(v) for k, v in record.items() if k != 'receipt'}, {'packet_id': loc.packet_id(event)}
    monkeypatch.setattr(loc, 'prepare', prepare)
    return doc, record


def test_completed_positions_checkpoint_and_replay_without_another_call(monkeypatch):
    doc, record = setup(monkeypatch)
    saved, calls = [], []
    async def checkpoint(audit): saved.append(audit)
    def run(*args, **kwargs):
        calls.append(args)
        return [record['receipt']]
    original = deepcopy(doc)
    bundle = asyncio.run(loc.localize('source', doc, checkpoint=checkpoint, run_jobs=run))
    assert doc == original and len(calls) == 1
    assert bundle['events'][0]['visual_samples'][1]['identity_status'] == 'UNCERTAIN'
    assert 'ball' not in bundle['events'][0]['visual_samples'][1]
    doc['match_room_localization'] = saved[-1]
    asyncio.run(loc.localize('source', doc, checkpoint=checkpoint,
                            run_jobs=lambda *a, **k: pytest.fail('paid request on exact replay')))
    assert saved[-1]['events']['event']['reused'] is True


def test_changed_source_stops_before_preparation_or_model(monkeypatch):
    doc, _ = setup(monkeypatch)
    monkeypatch.setattr(loc.pilot, 'digest', lambda _: 'different')
    async def checkpoint(a): pytest.fail('checkpoint before binding')
    with pytest.raises(ValueError, match='SOURCE_CHANGED'):
        asyncio.run(loc.localize('source', doc, checkpoint=checkpoint))


def test_bad_response_is_checkpointed_without_any_graphics(monkeypatch):
    doc, record = setup(monkeypatch); record['receipt']['raw_response'] += 'tampered'
    saved = []
    async def checkpoint(a): saved.append(a)
    bundle = asyncio.run(loc.localize('source', doc, checkpoint=checkpoint,
        run_jobs=lambda *a, **k: [record['receipt']]))
    assert not bundle['events'][0].get('visual_samples')
    assert saved[-1]['events']['event']['error'] == 'LOCALIZATION_OBSERVATIONS_REJECTED'


def test_paid_response_is_persisted_before_batch_failure(monkeypatch):
    doc,record=setup(monkeypatch);saved=[]
    async def checkpoint(a):saved.append(deepcopy(a))
    def interrupted(*args,**kwargs):
        kwargs['on_result'](record['receipt'])
        raise RuntimeError('transport interrupted after result')
    with pytest.raises(RuntimeError,match='transport interrupted'):
        asyncio.run(loc.localize('source',doc,checkpoint=checkpoint,run_jobs=interrupted))
    assert saved[-1]['events']['event']['receipt']==record['receipt']
    assert saved[-1]['events']['event']['status']=='OBSERVATIONS_RETURNED'


def test_missing_grouped_source_frame_stops_before_request(tmp_path, monkeypatch):
    event = {'event_id': 'e', 'source_video_sha256': 'source', 'proof': {
        'proof_start_ms': 2000, 'proof_end_ms': 6000, 'frame_ms': 3000,
        'cited_frames': {'s000003000': 3000}}}
    selection = {'raw_marker_anchors': [{'t': 1, 'target_point': {'x': .4, 'y': .5}, 'box': {'x': .3, 'y': .3, 'w': .2, 'h': .3}}]}
    released = []
    monkeypatch.setattr(loc.cv2, 'VideoCapture', lambda _: type('Cap', (), {'release': lambda self: released.append(True)})())
    monkeypatch.setattr(loc, 'read_frame_at', lambda cap, t: (True, np.zeros((80, 60, 3), np.uint8), t))
    monkeypatch.setattr(loc, 'read_frames_at', lambda cap, times: {})
    monkeypatch.setattr(loc.transport, 'build_request', lambda *a, **k: pytest.fail('request with missing source frame'))
    with pytest.raises(ValueError, match='SOURCE_FRAME_UNAVAILABLE'):
        loc.prepare('source', selection, event, tmp_path)
    assert released == [True]
