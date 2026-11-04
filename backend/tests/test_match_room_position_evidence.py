"""Synthetic protocol tests, not model accuracy evidence."""
from copy import deepcopy
import hashlib
import json
import pytest
from match_room_position_evidence import bound_samples, selection_digest
from scripts.probe_report_positions import validate


def fixture():
    selection = {'raw_marker_anchors': [{'t': .05, 'target_point': {'x': .3, 'y': .4}}]}
    event = {'event_id': 'event', 'source_video_sha256': 'source',
             'proof': {'proof_start_ms': 100, 'proof_end_ms': 300}}
    rows = [dict(frame=f's{ms:09}', target_status='CONFIRMED',
                 identity_evidence='Source appearance and continuity', feet_visible=True,
                 ground=[.3, .6], box=[.2, .3, .2, .3],
                 active_ball_status='CONFIRMED', ball=[.5, .6]) for ms in (100, 200, 300)]
    rows[1].update(target_status='UNCERTAIN', ground=None, box=None, feet_visible=False)
    raw = json.dumps({'frames': rows})
    result = {'event_id': 'event', 'source_video_sha256': 'source',
              'original_selection_values_sha256': selection_digest(selection),
              'frames': [{'frame_id': r['frame'], 'media_ms': ms, 'sha256': str(ms)}
                         for r, ms in zip(rows, (100, 200, 300))],
              'request': {'payload_sha256': 'a'*64},
              'receipt': {'packet_id': 'positions_001', 'provider': 'emergent',
                          'requested_model': 'gpt-6-astra', 'origin': 'LIVE_MODEL_REQUEST',
                          'status': 'COMPLETED', 'payload_sha256': 'a'*64,
                          'raw_response': raw, 'response_sha256': hashlib.sha256(raw.encode()).hexdigest(),
                          'images': [{'sha256': str(ms)} for ms in (100, 200, 300)]}}
    return event, selection, result


def test_uncertain_identity_keeps_barrier_without_player_or_ball_coordinates():
    event, selection, result = fixture()
    before = deepcopy(result)
    rows = bound_samples(event, selection, result, validate)
    assert rows[0]['ground'] == [.3, .6]
    assert rows[2]['ball'] == [.5, .6]
    assert rows[1] == {'frame_id': 's000000200', 'media_ms': 200,
                       'identity_status': 'UNCERTAIN', 'active_ball_status': 'CONFIRMED'}
    assert result == before


@pytest.mark.parametrize('field,value', [('event_id', 'other'), ('source_video_sha256', 'other'),
                                       ('original_selection_values_sha256', 'other')])
def test_other_event_source_or_selection_is_not_promoted(field, value):
    event, selection, result = fixture()
    result[field] = value
    with pytest.raises(ValueError, match='SOURCE_SELECTION_EVENT_MISMATCH'):
        bound_samples(event, selection, result, validate)


def test_altered_response_and_unbound_source_frame_are_rejected():
    event, selection, result = fixture()
    changed = deepcopy(result)
    changed['receipt']['raw_response'] += ' '
    with pytest.raises(ValueError, match='RECEIPT_MISMATCH'):
        bound_samples(event, selection, changed, validate)
    result['frames'][1]['sha256'] = 'not-sent'
    with pytest.raises(ValueError, match='SOURCE_FRAMES_MISMATCH'):
        bound_samples(event, selection, result, validate)


def test_uncertain_ball_is_not_filled_from_adjacent_confirmed_balls():
    event, selection, result = fixture()
    rows = json.loads(result['receipt']['raw_response'])
    rows['frames'][2].update(active_ball_status='UNCERTAIN', ball=None)
    raw = json.dumps(rows)
    result['receipt'].update(raw_response=raw, response_sha256=hashlib.sha256(raw.encode()).hexdigest())
    samples = bound_samples(event, selection, result, validate)
    assert 'ground' in samples[2] and 'ball' not in samples[2]


def test_ball_can_continue_after_identified_player_exits_but_not_across_uncertainty():
    event, selection, result = fixture()
    rows = json.loads(result['receipt']['raw_response'])
    for r in rows['frames'][1:]:
        r.update(target_status='ABSENT',ground=None,box=None,feet_visible=False)
    def bind():
        raw=json.dumps(rows)
        result['receipt'].update(raw_response=raw,response_sha256=hashlib.sha256(raw.encode()).hexdigest())
        return bound_samples(event,selection,result,validate)
    assert all('ball' in r for r in bind())
    rows['frames'][1]['target_status']='UNCERTAIN'
    assert 'ball' not in bind()[2]
    rows['frames'][0].update(target_status='ABSENT',ground=None,box=None,feet_visible=False)
    assert all('ball' not in r for r in bind())


def test_duel_recovery_uses_clip_context_without_changing_canonical_proof():
    from match_room import position_window, presentation_window
    event, selection, result = fixture()
    event['proof']['frame_ms'] = 100
    event['proof']['proof_end_ms'] = 200
    event['canonical_action_type'] = 'DUEL'
    before = deepcopy(event)
    start,end,context = position_window(event)
    result.update(context_after_ms=context, window_ms=[start,end])
    assert bound_samples(event,selection,result,validate)[-1]['media_ms'] == 300
    assert event == before and presentation_window(event) == (100,200)
    event.update(localization_method='EXPLICIT_SOURCE_POSITIONS', graphics_context_ms=750)
    assert presentation_window(event) == (100,950)
    assert event['proof']['proof_end_ms'] == 200
    result['context_after_ms'] = 751
    with pytest.raises(ValueError,match='CONTEXT_NOT_IN_ENCODED_CLIP'):
        bound_samples(event,selection,result,validate)
    result['context_after_ms'] = 750
    event['canonical_action_type'] = 'PASS'
    with pytest.raises(ValueError,match='CONTEXT_NOT_IN_ENCODED_CLIP'):
        bound_samples(event,selection,result,validate)
