"""Identity contradictions must not become selected-player scoring credit."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sequence_pilot as p


def actors():
    return {'players':[
        {'person_id':'passer','selected':True,'reference_ids':['r1'],'evidence_frames':['s100']},
        {'person_id':'finisher','selected':False,'reference_ids':[],'evidence_frames':['s200']}]}


def test_consistent_identity_is_only_structural_and_does_not_approve_events():
    r = p.assess_actor_identity(actors(), ['r1','r2'], ['s100','s200'])
    assert r['status'] == 'STRUCTURALLY_CONSISTENT'
    assert not r['independent_visual_correctness_verified'] and r['target_events'] == []


@pytest.mark.parametrize('selected', [False, None, True])
def test_different_people_matching_one_selected_profile_remain_unresolved(selected):
    data = actors()
    data['players'][1].update(reference_ids=['r2'], selected=selected)
    r = p.assess_actor_identity(data, ['r1','r2'], ['s100','s200'])
    assert r['status'] == 'UNRESOLVED'
    assert r['conflicting_person_ids'] == ['finisher','passer']


@pytest.mark.parametrize('change', [
    {'reference_ids':[]}, {'reference_ids':['invented']}, {'evidence_frames':['s999']},
    {'evidence_frames':[]}, {'reference_ids':None}, {'selected':'true'}])
def test_missing_or_invented_identity_support_does_not_pass(change):
    data = actors(); data['players'][0].update(change)
    assert p.assess_actor_identity(data, ['r1'], ['s100','s200'])['status'] == 'UNRESOLVED'


def test_real_retained_actor_response_requires_typed_identity_review():
    path = Path(__file__).resolve().parents[2]/'docs/examples/native-actor-continuity-receipt.json'
    saved = json.loads(path.read_text())
    result = saved['result']
    frames = [f's{ms:09}' for ms in result['native_source_instants']+result['full_play_overview_instants']]
    actual = json.loads(saved['receipt']['raw_response'])
    review = p.assess_actor_identity(actual, ['r2','r6','r7'], frames)
    assert review['status'] == 'UNRESOLVED'
    assert 'UNTYPED_IDENTITY_EVIDENCE' in review['reasons']
    assert review['target_events'] == []


def test_main_resolver_blocks_credit_when_canonical_matches_split_between_people():
    # Synthetic input exercises the actual event resolver, not a model verdict.
    from test_sequence_pilot import fixture
    manifest, packet, data = fixture()
    manifest['identity_profile'] = {'canonical_reference_ids':['r1','r2']}
    packet['reference_ids'].append('r2')
    data['plays'][0]['people'][1]['reference_ids'] = ['r2']
    resolved = p.resolve_response(data, manifest, packet, {})
    assert any(q['reason'] == 'IDENTITY_CONFLICT' for q in resolved['questions'])
    assert p.reconcile([resolved])['target_events'] == []


def test_negative_comparison_without_positive_match_preserves_valid_credit():
    from test_sequence_pilot import fixture
    manifest, packet, data = fixture()
    manifest['identity_profile'] = {'canonical_reference_ids':['r1']}
    data['plays'][0]['people'][1]['appearance'] = 'Unlike r1; different physical player'
    assert p.reconcile([p.resolve_response(data, manifest, packet, {})])['counts'] == {'ASSIST':1}
