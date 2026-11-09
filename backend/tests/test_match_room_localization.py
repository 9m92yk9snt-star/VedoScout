"""Synthetic orchestration controls; not visual accuracy evidence."""
import asyncio
from copy import deepcopy
import json
import numpy as np
import pytest
import match_room_localization as loc
from test_match_room_position_evidence import fixture


def test_request_limit_is_shared_by_primary_and_completion_batches():
    calls = []
    run = loc.bounded_request_runner(lambda jobs, *a, **k: calls.extend(jobs), 1)
    run([{'packet_id': 'primary'}])
    with pytest.raises(ValueError, match='REQUEST_LIMIT_EXCEEDED'):
        run([{'packet_id': 'completion'}])
    assert calls == [{'packet_id': 'primary'}]
    zero = loc.bounded_request_runner(lambda *a, **k: pytest.fail('paid call'), 0)
    with pytest.raises(ValueError, match='REQUEST_LIMIT_EXCEEDED'):
        zero([{}])


def test_interrupted_transport_still_consumes_reserved_request_allowance():
    calls=[]
    def failed(jobs):
        calls.append(jobs)
        raise RuntimeError('response interrupted')
    run=loc.bounded_request_runner(failed, 1)
    with pytest.raises(RuntimeError): run([{}])
    with pytest.raises(ValueError, match='REQUEST_LIMIT_EXCEEDED'): run([{}])
    assert len(calls)==1


def test_selective_retry_keeps_other_paid_event_receipts(monkeypatch):
    doc, primary, extra = completion_setup(monkeypatch)
    audit=doc['match_room_localization']
    audit.update(source_video_sha256='source',
                 original_selection_values_sha256=primary['original_selection_values_sha256'])
    audit['events']['other']={'receipt': {'retained': 'paid result'}, 'status': 'OBSERVATIONS_RETURNED'}
    saved=[]
    async def checkpoint(a): saved.append(deepcopy(a))
    asyncio.run(loc.localize('source',doc,checkpoint=checkpoint,event_ids=['event'],
        run_jobs=lambda *a,**k:[extra['receipt']]))
    assert all(a['events']['other']==audit['events']['other'] for a in saved)
    audit['source_video_sha256']='different'
    saved.clear()
    asyncio.run(loc.localize('source',doc,checkpoint=checkpoint,event_ids=[],
        run_jobs=lambda *a,**k:pytest.fail('no selected jobs')))
    assert 'other' not in saved[-1]['events']


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
        return ((ms, (ms, np.zeros((80, 60, 3), np.uint8))) for ms in times)
    monkeypatch.setattr(loc, 'iter_frames_at', grouped)
    before = deepcopy(selection)
    record, job = loc.prepare('source', selection, event, tmp_path)
    assert len(batches) == 1
    assert [ms for batch in batches for ms in batch] == sorted({f['media_ms'] for f in record['frames']})
    assert len(record['references']) == 10 and selection == before
    assert [r['target_point'] for r in record['references']] == [a['target_point'] for a in anchors]
    assert record['window_ms'] == [2250, 4750]
    assert job['packet_id'] == 'positions_e'
    assert record['request']['payload_bytes'] < 19_500_000
    tail, tail_job = loc.prepare('source', selection, event, tmp_path/'tail',
                                 record['references'], window=[4875, 6000])
    assert tail_job['packet_id'] == 'positions_e_coverage_4875_6000'
    assert [f['media_ms'] for f in tail['frames']][0] == 4875
    assert tail['frames'][-1]['media_ms'] == 6000
    assert tail['references'] == record['references']
    for window in ([0, 100], [2000, 6001], [2000, 5000]):
        with pytest.raises(ValueError, match='COMPLETION_WINDOW_INVALID'):
            loc.prepare('source', selection, event, tmp_path/'bad', window=window)


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
    monkeypatch.setattr(loc, 'iter_frames_at', lambda cap, times: iter(()))
    monkeypatch.setattr(loc.transport, 'build_request', lambda *a, **k: pytest.fail('request with missing source frame'))
    with pytest.raises(ValueError, match='SOURCE_FRAME_UNAVAILABLE'):
        loc.prepare('source', selection, event, tmp_path)
    assert released == [True]


def test_completion_windows_cover_real_dribble_tail_without_repeating_primary():
    event = {'proof': {'proof_start_ms': 7500, 'proof_end_ms': 12133}}
    record = {'window_ms': [7500, 10000], 'frames': [{'media_ms': 7500}, {'media_ms': 10000}]}
    assert loc.completion_windows(event, record) == [[10125, 12133]]
    # Short final tails still include the end, and long clips remain bounded.
    event['proof']['proof_end_ms'] = 12700
    assert loc.completion_windows(event, record) == [[10125, 12625], [12700, 12700]]
    event['proof']['proof_end_ms'] = 60000
    assert len(loc.completion_windows(event, record)) == 2


def test_missing_edges_are_not_uncertain_interior_rows():
    event = {'proof': {'proof_start_ms': 0, 'proof_end_ms': 5000}}
    record = {'window_ms': [1000, 4000], 'frames': [{'media_ms': 1000}, {'media_ms': 4000}]}
    assert loc.completion_windows(event, record) == [[0, 875], [4125, 5000]]


def completion_setup(monkeypatch):
    import hashlib
    doc, primary = setup(monkeypatch)
    event = doc['canonical_events']['events'][0]
    event['proof']['proof_end_ms'] = 600
    primary['window_ms'] = [100, 300]
    primary['packet_id'] = loc.packet_id(event)
    extra = deepcopy(primary)
    extra['packet_id'] += '_coverage_425_600'
    extra['window_ms'] = [425, 600]
    rows = json.loads(primary['receipt']['raw_response'])['frames']
    for row, ms in zip(rows, (425, 500, 600)):
        row['frame'] = f's{ms:09}'
    extra['frames'] = [{'frame_id': r['frame'], 'media_ms': ms, 'sha256': str(ms)} for r, ms in zip(rows, (425, 500, 600))]
    extra['request']['payload_sha256'] = 'b'*64
    extra['receipt'].update(packet_id=extra['packet_id'], payload_sha256='b'*64,
        raw_response=json.dumps({'frames': rows}), images=[{'sha256': str(ms)} for ms in (425, 500, 600)])
    extra['receipt']['response_sha256'] = hashlib.sha256(extra['receipt']['raw_response'].encode()).hexdigest()
    def prepare(video, selection, actual, work, reference_images=None, *, window=None):
        assert actual['event_id'] == event['event_id']
        chosen = extra if window else primary
        if window: assert window == [425, 600]
        return {k: deepcopy(v) for k,v in chosen.items() if k != 'receipt'}, {'packet_id': chosen['packet_id']}
    monkeypatch.setattr(loc, 'prepare', prepare)
    doc['match_room_localization'] = {'events': {event['event_id']: deepcopy(primary)}}
    return doc, primary, extra


def test_only_missing_tail_is_paid_and_both_receipts_replay(monkeypatch):
    doc, primary, extra = completion_setup(monkeypatch)
    saved, calls = [], []
    async def checkpoint(audit): saved.append(deepcopy(audit))
    def run(jobs, *args, **kwargs):
        calls.extend(j['packet_id'] for j in jobs)
        kwargs['on_result'](extra['receipt'])
        return [extra['receipt']]
    bundle = asyncio.run(loc.localize('source', doc, checkpoint=checkpoint, run_jobs=run))
    assert calls == [extra['packet_id']]
    samples = bundle['events'][0]['visual_samples']
    assert [r['media_ms'] for r in samples] == [100, 200, 300, 425, 500, 600]
    assert samples[1]['identity_status'] == samples[4]['identity_status'] == 'UNCERTAIN'
    assert 'ground' not in samples[1] and 'ground' not in samples[4]
    assert saved[-1]['events']['event']['receipt'] == primary['receipt']
    doc['match_room_localization'] = saved[-1]
    again = asyncio.run(loc.localize('source', doc, checkpoint=checkpoint,
        run_jobs=lambda *a,**k: pytest.fail('duplicate paid call')))
    assert again == bundle
    assert all(s['events']['event'].get('completion') for s in saved[-3:])


def test_completed_tail_survives_transport_interruption(monkeypatch):
    doc, primary, extra = completion_setup(monkeypatch)
    saved = []
    async def checkpoint(audit): saved.append(deepcopy(audit))
    def run(jobs, *args, **kwargs):
        kwargs['on_result'](extra['receipt'])
        raise RuntimeError('interrupted after supplementary receipt')
    with pytest.raises(RuntimeError, match='supplementary'):
        asyncio.run(loc.localize('source', doc, checkpoint=checkpoint, run_jobs=run))
    record = saved[-1]['events']['event']
    assert record['receipt'] == primary['receipt']
    assert record['completion'][extra['packet_id']]['receipt'] == extra['receipt']
    doc['match_room_localization'] = saved[-1]
    asyncio.run(loc.localize('source', doc, checkpoint=checkpoint,
        run_jobs=lambda *a,**k: pytest.fail('paid request after saved result')))


def test_invalid_tail_preserves_primary_observations(monkeypatch):
    doc, primary, extra = completion_setup(monkeypatch)
    extra['receipt']['raw_response'] += 'tampered'
    saved=[]
    async def checkpoint(a): saved.append(a)
    bundle=asyncio.run(loc.localize('source',doc,checkpoint=checkpoint,
        run_jobs=lambda *a,**k:[extra['receipt']]))
    assert [r['media_ms'] for r in bundle['events'][0]['visual_samples']] == [100,200,300]
    assert saved[-1]['events']['event']['completion'][extra['packet_id']]['error']=='LOCALIZATION_OBSERVATIONS_REJECTED'


def test_preflight_failure_preserves_paid_receipts_without_using_them(monkeypatch):
    doc, primary, extra = completion_setup(monkeypatch)
    doc['match_room_localization']['events']['event']['completion'] = {extra['packet_id']: extra}
    def broken(*args, **kwargs): raise ValueError('decode failed')
    monkeypatch.setattr(loc, 'prepare', broken)
    saved=[]
    async def checkpoint(a): saved.append(a)
    bundle=asyncio.run(loc.localize('source',doc,checkpoint=checkpoint,
        run_jobs=lambda *a,**k:pytest.fail('model after failed preflight')))
    record=saved[-1]['events']['event']
    assert record['receipt']==primary['receipt']
    assert record['completion'][extra['packet_id']]['receipt']==extra['receipt']
    assert not bundle['events'][0].get('visual_samples')


def test_exhausted_shared_budget_does_not_start_supplement(monkeypatch):
    doc, primary, extra = completion_setup(monkeypatch)
    clock=[0.]
    prepare=loc.prepare
    def slow(*args, **kwargs):
        result=prepare(*args, **kwargs)
        clock[0]=421.
        return result
    monkeypatch.setattr(loc, 'prepare', slow)
    monkeypatch.setattr(loc.time, 'monotonic', lambda:clock[0])
    saved=[]
    async def checkpoint(a): saved.append(a)
    bundle=asyncio.run(loc.localize('source',doc,checkpoint=checkpoint,
        run_jobs=lambda *a,**k:pytest.fail('model after shared deadline')))
    assert [r['media_ms'] for r in bundle['events'][0]['visual_samples']]==[100,200,300]
    assert saved[-1]['events']['event']['completion_error']=='LOCALIZATION_TIME_BUDGET'
    assert saved[-1]['events']['event']['coverage']['clip_edges_observed'] is False
