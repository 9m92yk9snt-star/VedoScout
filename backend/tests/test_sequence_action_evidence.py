"""Offline publication/attribution regressions, never fresh model accuracy tests."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
import sequence_pilot as p
import sequence_report_adapter as adapter
from sequence_action_evidence import supported_movements, GOAL_INSTRUCTION
from player_report_copy import action_lesson
from test_sequence_pilot import fixture, bracketed_shot


def movement():
    return {"actor": "passer", "type": "SHIELD_TURN", "decision": "SUPPORTED",
            "before_frame": "s000000500", "movement_frames": ["s000000750"],
            "after_frame": "s000001000", "visible_movement": "Turns with the ball behind his body.",
            "opponent_response": "Opponent follows the turn.", "outcome": "RETAINS"}


def check(rows):
    manifest, _, _ = fixture()
    return supported_movements(rows, actor="passer",
        frames={f['frame_id']: f['media_ms'] for f in manifest['frames']}, bounds=(500, 1250))


@pytest.mark.parametrize("key,value", [
    ("actor", "finisher"), ("type", "LAUDRUP_FEINT"), ("type", []),
    ("decision", "UNCERTAIN"), ("before_frame", "invented"),
    ("after_frame", "s000000500"), ("movement_frames", ["s000001500"]),
    ("movement_frames", ["s000000500"]), ("movement_frames", []),
    ("visible_movement", ""), ("opponent_response", None), ("outcome", []),
])
def test_uncertain_wrong_actor_or_invalid_source_movement_cannot_publish(key, value):
    row = movement(); row[key] = value
    assert check([row]) == []


def test_distinct_movement_is_not_a_successful_take_on_or_erased_by_later_loss():
    manifest, packet, data = fixture()
    manifest['references'] = [{'reference_id': 'r1'}]
    action = data['plays'][0]['actions'][0]
    action.update(kind='DRIBBLE', outcome='INCOMPLETE', movement_observations=[movement()])
    raw = json.dumps(data)
    receipt = {'packet_id': packet['packet_id'], 'status': 'COMPLETED', 'origin': 'LIVE_MODEL_REQUEST',
        'provider': 'SYNTHETIC_TEST_ONLY', 'payload_sha256': 'synthetic',
        'raw_response': raw, 'response_sha256': hashlib.sha256(raw.encode()).hexdigest()}
    result = p.reconcile([p.resolve_response(data, manifest, packet, receipt)])
    assert result['counts'] == {'DRIBBLE': 1}
    result.update(source_video_sha256='source', status='MODEL_OBSERVATIONS_RETURNED',
                  fresh_end_to_end_run=True, model_jobs_completed=1)
    bundle = adapter.canonical_bundle(result, manifest, [receipt])
    event = bundle['events'][0]
    assert len(event['movement_observations']) == 1
    assert 's000000750' in event['proof']['cited_frames']
    assert action_lesson(event)[0] == 'You turn while using your body to protect the ball.'
    report = adapter.build_report({'summary': 'Synthetic observed turn'}, bundle)
    assert report['match_stats']['successful_dribbles'] is None
    # Canonical publication revalidates the evidence instead of trusting a label.
    result['target_events'][0]['movement_observations'][0]['actor'] = 'finisher'
    assert adapter.canonical_bundle(result, manifest, [receipt])['events'][0]['movement_observations'] == []


def test_five_actual_historical_movements_fit_the_contract_without_becoming_live_events():
    saved = json.loads((Path(__file__).resolve().parents[2] /
        'docs/examples/feint-source-sheet-receipts.json').read_text())
    frames = {f['id']: f['source_ms'] for f in saved['cited_source_frames']}
    rows = [{**r, 'actor': 'selected'} for r in saved['observations'] if r['decision'] == 'SUPPORTED']
    assert len(rows) == 5
    # Only contract field adaptation for offline validation, never live replay.
    assert len(supported_movements(rows, actor='selected', frames=frames, bounds=(0, 80000))) == 5
    assert check([movement(), movement()]) == check([movement()])


def test_real_goal_focus_reply_is_admitted_but_earlier_uncertainty_is_not_rewritten():
    saved = json.loads((Path(__file__).resolve().parents[2] /
        'docs/examples/sequence-goal-focus-regression.json').read_text())
    counts = []
    for receipt in saved['receipts']:
        assert hashlib.sha256(receipt['raw_response'].encode()).hexdigest() == receipt['response_sha256']
        resolved = p.reconcile([p.resolve_response(json.loads(receipt['raw_response']),
            saved['manifest'], saved['packet'], receipt)])
        counts.append(resolved['counts'].get('GOAL', 0))
    assert counts == [0, 1]


def test_terminal_contact_focus_is_added_to_existing_job_and_never_to_foot_only_question():
    manifest, packet, _ = fixture()
    data = bracketed_shot()
    data['plays'][0]['questions'] = [{'reason': 'CONTACT', 'action_id': 'a1', 'question': 'Who released it?'}]
    result = p.reconcile([p.resolve_response(data, manifest, packet, {})])
    jobs = p.plan_contact_reviews(manifest, result, complete_terminal_context=True)
    assert len(jobs) == 1 and jobs[0]['goal_attribution_review'] is True
    # Use empty frame list to inspect instructions without image paths in fixture.
    items = p.packet_items({**manifest, 'references': []}, {**jobs[0], 'frame_ids': [], 'reference_ids': []})
    assert GOAL_INSTRUCTION in [i.get('text') for i in items]
    data['plays'][0]['questions'][0]['reason'] = 'FOOT'
    result = p.reconcile([p.resolve_response(data, manifest, packet, {})])
    assert p.plan_contact_reviews(manifest, result, complete_terminal_context=True) == []


def test_supported_movement_does_not_override_contact_or_scorer_uncertainty():
    manifest, packet, _ = fixture(); data = bracketed_shot()
    data['plays'][0]['actions'][0]['movement_observations'] = [movement()]
    data['plays'][0]['questions'] = [{'reason': 'CONTACT', 'action_id': 'a1', 'question': 'Who touched it?'}]
    result = p.reconcile([p.resolve_response(data, manifest, packet, {})])
    assert result['target_events'] == []


def test_movement_player_text_is_shared_by_existing_web_and_pdf_publication():
    from test_report_publication import example, publish_report
    doc = example()
    event = doc['canonical_events']['events'][0]
    event.update(canonical_event_type='DRIBBLE', canonical_outcome='INCOMPLETE',
                 movement_observations=[movement()])
    report = publish_report(doc)
    sentence = 'You turn while using your body to protect the ball.'
    full = next(r for r in report['full_report']['action_timeline'] if r['event_id'] == event['event_id'])
    web = next(r for r in report['report_publication']['view']['actionTimeline'] if r['eventId'] == event['event_id'])
    assert sentence in full['description']
    assert web['description'] == full['description']
