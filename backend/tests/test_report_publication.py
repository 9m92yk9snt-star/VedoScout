"""Publication contracts: evidence, honest partial scores, and web/PDF parity."""
from copy import deepcopy
from pathlib import Path
import json
import sys

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from report_publication import publish_report, comparison


def example():
    events = []
    for i, kind in enumerate(('SHOT', 'GOAL', 'ASSIST', 'ASSIST', 'ASSIST', 'DUEL')):
        events.append({'event_id': f'event-{i}', 'canonical_ms': 23000 + i * 7000,
            'canonical_event_type': kind, 'canonical_outcome': 'SAVED' if kind == 'SHOT' else 'TEAMMATE_GOAL',
            'global_target_id': 'GLOBAL_TARGET', 'proof': {'proof_eligible': True, 'outcome_ms': 24000 + i * 7000, 'frame_id': f'frame-{i}', 'frame_ms': 23000 + i * 7000},
            'source_video_sha256': 'synthetic-source',
            'actor_visual_id': 'sequence:p1', 'details': ['White 15 plays the ball. P1 continues; p2 is separate.'],
            'foot': 'UNKNOWN', 'contact_interval_ms': [23000+i*7000, 23100+i*7000]})
    full = {'analysis_authority': {'output': 'SEQUENCE_V1'}, 'evidence_authority_version': 1,
            'video_comments': [], 'action_timeline': [], 'technical': {}, 'mentality': {}}
    for i, (category, key, score) in enumerate((('technical', 'dribbling', 7), ('technical', 'shooting', 8),
            ('mentality', 'confidence', 8), ('mentality', 'work_rate', 9))):
        full[category][key] = {'score': score, 'evidence': [{'event_id': f'event-{i}',
            'canonical_event_ids': [f'event-{i}'], 'identity_verified': True}], 'cannot_evaluate': False}
    full['technical']['weak_foot'] = {'score': None, 'cannot_evaluate': True, 'evidence': []}
    for e in events:
        full['video_comments'].append({'event_id': e['event_id'], 'evidence_id': 'proof-'+e['event_id'],
            'frame_url': '/frames/'+e['event_id']+'.jpg', 'proof_verified': True, 'proof_frame_verified': True,
            'source_video_sha256': 'synthetic-source', 'evidence_time_ms': e['canonical_ms'],
            'frame_time_ms': e['canonical_ms'], 'source_frame_id': e['proof']['frame_id']})
    return {'id': 'synthetic-report', 'analysis_engine': 'SEQUENCE_V1', 'full_report': full,
            'canonical_events': {'events': events, 'source_video_sha256': 'synthetic-source'}, 'video_duration_sec': 76.763596,
            'player_details': {'player_name': 'Test Player', 'jersey_number': '15', 'position': 'Winger', 'age': 11},
            'full_generated_at': '2026-10-19T23:00:43+00:00', 'agent_review': {'status': 'pending'}}


def test_read_only_idempotent_and_date_is_fixed_copenhagen_date():
    original = example()
    saved = deepcopy(original)
    report = publish_report(original)
    assert original == saved
    assert report == publish_report(report)
    assert report['report_publication']['date'] == '20 OCTOBER 2026'


def test_score_excludes_missing_skills_instead_of_zero_and_discloses_weights():
    pub = publish_report(example())['report_publication']
    assert pub['score']['value'] == 7.8  # (7*2+8+8+9)/5
    assert pub['score']['rated_skills'] == 4
    assert pub['score']['total_skills'] == 25
    assert pub['score']['weighted_coverage_pct'] == 16.7  # 5 observed units of the fixed 30-unit winger rubric
    assert pub['score']['weights']['dribbling'] == 2
    assert 'weak_foot' not in pub['score']['weights']


@pytest.mark.parametrize('bad', [None, float('nan'), float('inf'), True, -1, 12])
def test_invalid_or_unbound_score_cannot_manufacture_overall(bad):
    r = example()
    r['full_report']['technical']['shooting']['score'] = bad
    assert publish_report(r)['report_publication']['score']['value'] is None


def test_wrong_event_binding_or_foot_claim_cannot_authorize_score():
    r = example()
    r['full_report']['technical']['dribbling']['evidence'][0]['canonical_event_ids'] = ['other-event']
    r['full_report']['technical']['weak_foot'] = {'score': 10, 'cannot_evaluate': False,
        'evidence': deepcopy(r['full_report']['technical']['shooting']['evidence'])}
    out = publish_report(r)
    assert out['full_report']['technical']['weak_foot']['score'] is None
    assert out['report_publication']['score']['value'] is None


def test_names_exact_snapshot_joins_complete_timeline_and_no_touch_counts():
    r = publish_report(example())
    p = r['report_publication']
    assert len(p['key_actions']) == 5
    assert len(p['view']['actionTimeline']) == 6
    assert r['full_report']['match_stats']['observed_assists'] == 3
    assert r['full_report']['match_stats']['shots'] == 2
    assert r['full_report']['match_stats']['key_passes'] == 0
    assert 'touches_observed' not in r['full_report']['parent_value_metrics']['involvement']
    for m in p['view']['snapshotMoments']:
        assert m['thumb'] == '/frames/'+m['eventId']+'.jpg'
        assert 'Test Player' in m['desc']
        assert '15' not in m['desc'] and 'P1' not in m['desc']
    r['full_report']['video_comments'][0]['proof_frame_verified'] = False
    out = publish_report(r)
    m = next(m for m in out['report_publication']['view']['snapshotMoments'] if m['eventId'] == 'event-0')
    assert m['thumb'] is None  # never borrow another event's frame


def test_academy_is_a_documented_age_rubric_not_a_percentile():
    a = comparison(7.6, 11)
    b = comparison(7.6, 17)
    assert a['label'] == 'Academy' and b['label'] == 'Strong Club'
    assert 'percentile' not in a
    assert comparison(8, 9) is None


def test_pdf_consumes_identical_shared_view_and_all_events(tmp_path):
    pytest.importorskip('reportlab')
    from pdf_v2 import derive_v2, build_pdf_v2
    from pypdf import PdfReader
    r = publish_report(example())
    derived = derive_v2(r)
    for key, value in r['report_publication']['view'].items():
        assert derived[key] == value
    path = tmp_path / 'report.pdf'
    build_pdf_v2(r, str(path))
    reader = PdfReader(path)
    text = '\n'.join(p.extract_text() for p in reader.pages)
    assert '20 OCTOBER 2026' in text
    assert 'COMPLETE ACTION TIMELINE' in text
    assert all(e['event_id'] in text for e in r['canonical_events']['events'])
    assert 'Stronger than' not in text and 'None\'' not in text
    assert 'full ScoutMe Pro Benchmarked Analysis' not in text


def test_non_sequence_reports_keep_existing_contract():
    r = {'full_report': {'scores': {'overall_development': 8}}}
    assert publish_report(r) == r


@pytest.mark.parametrize('field,value', [('source_video_sha256','other-source'), ('evidence_time_ms',999), ('source_frame_id','other-frame')])
def test_same_event_id_cannot_authorize_media_from_another_source_or_time(field, value):
    r = example()
    r['full_report']['video_comments'][0][field] = value
    published = publish_report(r)
    snapshot = next(m for m in published['report_publication']['view']['snapshotMoments'] if m['eventId'] == 'event-0')
    assert snapshot['thumb'] is None
    assert published['report_publication']['key_actions'][0]['proof_verified'] is False
