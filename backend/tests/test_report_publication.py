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
        assert 'Test Player' not in m['title']  # the section already identifies the player
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


def test_concise_pdf_uses_shared_facts_and_keeps_full_audit_in_data(tmp_path):
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
    assert 'COMPLETE ACTION TIMELINE' not in text
    assert 'Evidence reference:' not in text
    assert all(e['event_id'] not in text for e in r['canonical_events']['events'])
    assert len(r['report_publication']['view']['actionTimeline']) == 6
    links = [a.get_object()['/A']['/URI'] for p in reader.pages for a in p.get('/Annots', [])]
    assert all(any(url.endswith('#event-' + a['event_id']) for url in links) for a in r['report_publication']['key_actions'])
    assert 'GROW YOUR GAME' not in text and 'NEXT MATCH MISSIONS' not in text
    assert 'KEY ACTIONS' in text
    assert all(f'PAGE {i + 1} / {len(reader.pages)}' in p.extract_text() for i,p in enumerate(reader.pages))
    assert 'Stronger than' not in text and 'None\'' not in text
    assert 'full ScoutMe Pro Benchmarked Analysis' not in text
    skills_page = next(p.extract_text().upper() for p in reader.pages if 'THE NUMBERS, TRANSLATED' in p.extract_text().upper())
    assert all(label in skills_page for label in ('TECHNICAL', 'MENTALITY', 'DRIBBLING', 'SHOOTING', 'CONFIDENCE', 'WORK RATE'))
    first_page = reader.pages[0].extract_text()
    assert all(label in first_page for label in ("SCOUT'S FIRST IMPRESSION", 'OVERALL OBSERVED', 'MATCH STATS', 'ACADEMY RUBRIC REFERENCE'))
    assert 'COMPLETE ACTION TIMELINE' not in first_page
    assert 'Contact window' not in '\n'.join(p.extract_text() for p in reader.pages[:5])


def test_pdf_images_keep_entire_frame_aspect_ratio(tmp_path):
    from PIL import Image
    from pdf_v2 import draw_contain_image
    source = tmp_path / 'wide-frame.jpg'
    Image.new('RGB', (1600, 900)).save(source)
    class RecordingCanvas:
        def saveState(self): pass
        def restoreState(self): pass
        def setFillColor(self, *_): pass
        def roundRect(self, *_, **kw): pass
        def drawImage(self, image, x, y, w, h): self.size = (w, h)
    canvas = RecordingCanvas()
    assert draw_contain_image(canvas, source, 0, 0, 300, 100)
    w, h = canvas.size
    assert w / h == pytest.approx(1600 / 900)
    assert w <= 300 and h <= 100
    assert draw_contain_image(canvas, None, 0, 0, 300, 100) is False


def test_original_pdf_theme_and_native_frames_survive_paginated_render(tmp_path):
    from PIL import Image
    from pypdf import PdfReader
    from pypdf.generic import ContentStream
    from pdf_v2 import build_pdf_v2, CREAM
    source = tmp_path / 'native-frame.jpg'
    Image.new('RGB', (1600, 900), '#32794b').save(source)
    output = tmp_path / 'classic-report.pdf'
    report = publish_report(example())
    report['display_crop_url_override'] = '/test-native.jpg'
    build_pdf_v2(report, str(output), image_resolver=lambda _: str(source))
    reader = PdfReader(output)
    fills = [tuple(float(n) for n in args) for args, op in ContentStream(reader.pages[0].get_contents(), reader).operations if op == b'rg']
    assert any(rgb == pytest.approx(CREAM.rgb(), abs=.00001) for rgb in fills)
    assert all(image.image.size == (1600, 900) for image in reader.pages[0].images)
    assert len(reader.pages[0].images) == 1
    assert sum(len(page.get('/Annots', [])) for page in reader.pages) == 5
    assert f'PAGE {len(reader.pages)} / {len(reader.pages)}' in reader.pages[-1].extract_text()


def test_original_cover_snapshot_and_training_grids_are_preserved(monkeypatch, tmp_path):
    import pdf_v2 as pdf
    captured = {}
    for name in ('_hero_card', '_parent_summary_card', '_overall_score_card', '_snapshot_moment_card',
                 '_top_strengths_card', '_dev_priorities_card', '_roadmap_card', '_training_week_card', '_parent_tips_card', '_sm_rich_card'):
        original = getattr(pdf, name)
        def wrapper(*args, _original=original, _name=name, **kwargs):
            captured.setdefault(_name, []).append(args)
            return _original(*args, **kwargs)
        monkeypatch.setattr(pdf, name, wrapper)
    pdf.build_pdf_v2(publish_report(example()), str(tmp_path / 'original-grids.pdf'))
    # Exact geometry from the uploaded Premium V2 PDF: no substitute card grids.
    assert captured['_hero_card'][0][3:7] == pytest.approx((26, pdf.H - 365, 158, 285))
    assert captured['_parent_summary_card'][0][2:6] == pytest.approx((193, pdf.H - 365, 205, 285))
    snapshot = [args[2:6] for args in captured['_snapshot_moment_card']]
    assert len(snapshot) == 4
    assert snapshot[0][0] == snapshot[2][0] == 26
    assert snapshot[1][0] == snapshot[3][0] == pytest.approx(26 + (pdf.CW + pdf.GAP) / 2)
    assert snapshot[0][1] == snapshot[1][1] and snapshot[2][1] == snapshot[3][1]
    assert all(args[4:6] == pytest.approx((305, 360)) for args in captured['_top_strengths_card'])
    grouped = captured['_sm_rich_card']
    assert [args[1]['category'] for args in grouped] == ['technical', 'tactical', 'physical', 'mentality']
    assert all(args[5] == 128 for args in grouped)
    assert all(s['category'] == args[1]['category'] for args in grouped for s in args[1]['category_skills'])
    assert sum(len(args[1]['category_skills']) for args in grouped) == 4
    assert all(args[5] == 330 for key in ('_roadmap_card', '_training_week_card', '_parent_tips_card') for args in captured[key])


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


def test_player_story_is_shared_and_only_uses_bound_verified_observations():
    r = publish_report(example())
    p = r['report_publication']
    assert p['view']['parentSummary']['paragraphs'] == r['full_report']['parent_summary']['paragraphs']
    assert len(p['view']['parentSummary']['paragraphs']) > 1
    assert r['score_context']['overall']['line'] == p['narrative']['score_explanation']
    bound = {c['event_id'] for c in r['full_report']['video_comments'] if c['proof_verified']}
    assert set(p['narrative']['event_ids']) <= bound
    assert 'rated skills from this video' in p['narrative']['score_explanation']
    # Removing proof must not leave an apparently evidenced player-story paragraph.
    original = example()
    for c in original['full_report']['video_comments']:
        c['proof_verified'] = False
    out = publish_report(original)
    assert out['report_publication']['narrative']['event_ids'] == []
    assert len(out['full_report']['parent_summary']['paragraphs']) == 1


def test_cover_uses_larger_saved_full_body_reference_without_replacing_user_photo(tmp_path):
    from PIL import Image
    from pdf_v2 import _pick_hero_photo
    sources = {}
    for name in ('original', 'small', 'large', 'partial', 'no-mask'):
        path = tmp_path / (name + '.jpg')
        Image.new('RGB', (120, 240)).save(path)
        sources['/' + name] = str(path)
    def anchor(name, size, **extra):
        return {'crop_r2_url': '/' + name, 'box': {'w': size, 'h': size},
                'body_ratio': 2.0, 'visible_mask': {'width': 96, 'height': 192}, **extra}
    doc = {'photo_source': 'video_crop', 'report_publication': {'version': 3},
           'display_crop_url_override': '/original', 'anchors': [
           anchor('small', .1), anchor('partial', .5, visibility='partial'),
           anchor('no-mask', .4, visible_mask=None), anchor('large', .2)]}
    assert _pick_hero_photo(doc, sources.get) == sources['/large']
    doc['photo_source'] = 'upload'
    assert _pick_hero_photo(doc, sources.get) == sources['/original']


def test_strengths_explain_the_bound_action_and_its_possible_team_value():
    r = publish_report(example())
    for strength in r['report_publication']['view']['topStrengths']:
        assert strength['observation']
        assert strength['teamContribution']
        assert strength['note'] == strength['observation'] + ' ' + strength['teamContribution']
        assert strength['eventId'] in {e['event_id'] for e in r['canonical_events']['events']}
    from report_publication import strength_explanation
    skill = {'key': 'competitive_mindset', 'evidence': [{'what': 'Attempts to recover the ball. The opponent shields it.'}]}
    observed, value = strength_explanation(skill, {'canonical_event_type': 'DUEL'}, 'Player')
    assert 'keeps challenging' in observed
    assert 'can make it harder' in value
    assert 'wins' not in observed.lower()
