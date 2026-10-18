"""Physical-link decisions must not mistake hypotheses for observed events."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.probe_continuous_pass import assess_link, resolve_assist


def observed():
    def field(status):
        return {'status':status,'frames':['s100','s200'],'observation':'Synthetic before/after motion'}
    return {'players':[{'person_id':'passer','selected':True},{'person_id':'receiver','selected':False}],
        'outcome':{'kind':'GOAL'},
        'link_assessment':{'releaser':'passer','receiver':'receiver','finisher':'receiver',
            'same_ball_release_to_receiver':field('SUPPORTED'),
            'receiver_finishing_action':field('SUPPORTED'),'goal_from_that_finish':field('SUPPORTED'),
            'intervening_control':field('NOT_OBSERVED'),'defensive_contact':field('UNCERTAIN')}}


def review(data,identity='STRUCTURALLY_CONSISTENT'):
    return assess_link(data,{'status':identity},{'s100','s200'})


def test_hypothetical_touch_alone_does_not_veto_three_affirmatively_supported_links():
    result=review(observed())
    assert result['status']=='ASSIST_SUPPORTED_BY_MODEL_OBSERVATIONS'
    assert not result['independent_visual_correctness_verified'] and result['target_events']==[]


@pytest.mark.parametrize('name',['same_ball_release_to_receiver','receiver_finishing_action','goal_from_that_finish'])
def test_absence_of_opponent_control_cannot_fill_an_unresolved_link(name):
    data=observed();data['link_assessment'][name]['status']='UNCERTAIN'
    assert review(data)['status']=='UNRESOLVED'


def test_observed_intervening_control_breaks_direct_assist_even_when_other_fields_claim_support():
    data=observed();data['link_assessment']['intervening_control']['status']='OBSERVED'
    assert review(data)['status']=='NO_DIRECT_ASSIST'


def test_opponent_control_uncertain_does_not_pass():
    data=observed();data['link_assessment']['intervening_control']['status']='UNCERTAIN'
    assert review(data)['status']=='UNRESOLVED'


@pytest.mark.parametrize('frames',[['s100','invented'],['s100'],None,{},[{},'s100']])
def test_invented_missing_or_malformed_citations_cannot_support_approval(frames):
    data=observed();data['link_assessment']['same_ball_release_to_receiver']['frames']=frames
    assert review(data)['status']=='UNRESOLVED'


def test_self_goal_and_identity_conflict_cannot_become_an_assist():
    data=observed();data['link_assessment']['finisher']='passer'
    assert review(data)['status']=='UNRESOLVED'
    assert review(observed(),'UNRESOLVED')['status']=='UNRESOLVED'


def test_missing_new_observations_keeps_historical_reply_unapproved():
    assert review({'players':[]})['status']=='UNRESOLVED'


@pytest.mark.parametrize('kind',['SAVED','NO_GOAL','UNKNOWN',None])
def test_supported_goal_link_cannot_override_a_conflicting_overall_outcome(kind):
    data=observed();data['outcome']['kind']=kind
    assert review(data)['status']=='UNRESOLVED'


def mapped_observation():
    """Entirely synthetic input; these tests are not model perception evidence."""
    def fid(ms): return f's{ms:09}'
    def row(actor,before,after,recipient=None):
        return {'actor':actor,'recipient':recipient,'before_frame':fid(before),'after_frame':fid(after),
                'visible_evidence':'Synthetic actor and moving-ball evidence','remaining_alternatives':'Possible slight brush'}
    def fact(status,instants):
        return {'status':status,'frames':[fid(ms) for ms in instants],
                'observation':'Synthetic source motion through this link'}
    data={'players':[
        {'person_id':'passer','selected':True,'reference_ids':['r1'],'evidence_frames':[fid(100),fid(200)]},
        {'person_id':'receiver','selected':False,'reference_ids':[],'evidence_frames':[fid(300),fid(500)]}],
        'contact_chain':[row('passer',100,200,'receiver'),row('receiver',300,400),row('receiver',500,600)],
        'outcome':{'kind':'GOAL','last_touch_actor':None,'evidence':[fid(700),fid(800)]},
        'link_assessment':{'releaser':'passer','receiver':'receiver','finisher':'receiver',
            'same_ball_release_to_receiver':fact('SUPPORTED',[100,200,300,400]),
            'receiver_finishing_action':fact('SUPPORTED',[400,500,600]),
            'goal_from_that_finish':fact('SUPPORTED',[600,700,800]),
            'intervening_control':fact('NOT_OBSERVED',[200,300]),
            'defensive_contact':fact('UNCERTAIN',[200,300])},
        'event_mapping':{'pass_chain_index':0,'receive_chain_index':1,'finish_chain_index':2,
            'receiver_is_teammate':True,'same_active_ball':True,'continuous_play':True,
            'pass_actor_unique':True,'finishing_actor_unique':True,'goal_frame':fid(800)}}
    context={'source_video_sha256':'a'*64,'source_start_ms':0,'source_end_ms':900,
        'retained_overview_instants':list(range(0,901,100)),'identity_reference_ids':['r1'],
        'request_audit':{'payload_sha256':'b'*64}}
    return data,context


def mapped_review(data=None,context=None):
    if data is None: data,context=mapped_observation()
    raw=json.dumps(data)
    receipt={'origin':'LIVE_MODEL_REQUEST','status':'COMPLETED','fixture_origin':'SYNTHETIC_TEST_ONLY',
        'packet_id':'synthetic','source_video_sha256':context['source_video_sha256'],
        'payload_sha256':'b'*64,'raw_response':raw,'response_sha256':hashlib.sha256(raw.encode()).hexdigest()}
    return resolve_assist(data,context,receipt)


def test_typed_chain_uses_existing_resolver_to_approve_passer_assist_without_invented_contact():
    data,context=mapped_observation(); unchanged=deepcopy((data,context))
    result=mapped_review(data,context)
    assert result['status']=='APPROVED' and result['counts']=={'ASSIST':1}
    event=result['target_events'][0]
    assert event['actor']=='passer' and event['receiver']==event['finisher']=='receiver'
    assert event['reason']=='VISIBLE_DIRECT_ASSIST' and event['proof_eligible']
    assert event['contact_ms'] is None and event['contact_interval_ms']==[100,200]
    assert event['receiver_interval_ms']==[300,400] and event['finishing_contact_interval_ms']==[500,600]
    assert event['defensive_contact']['status']=='UNCERTAIN' and event['last_touch_actor'] is None
    assert (data,context)==unchanged


@pytest.mark.parametrize('key',['receiver_is_teammate','same_active_ball','continuous_play',
    'pass_actor_unique','finishing_actor_unique'])
@pytest.mark.parametrize('value',[False,None,'true'])
def test_typed_chain_requires_each_positive_link_instead_of_filling_missing_evidence(key,value):
    data,context=mapped_observation();data['event_mapping'][key]=value
    assert mapped_review(data,context)['target_events']==[]


@pytest.mark.parametrize('mutation',[
    lambda d:d['link_assessment']['intervening_control'].update(status='OBSERVED'),
    lambda d:d['link_assessment']['same_ball_release_to_receiver'].update(status='UNCERTAIN'),
    lambda d:d['link_assessment']['receiver_finishing_action'].update(status='CONTRADICTED'),
    lambda d:d['contact_chain'][0].update(recipient='other'),
    lambda d:d['contact_chain'][2].update(actor='passer'),
    lambda d:d['contact_chain'][1].update(recipient='another_teammate'),
    lambda d:d['contact_chain'][1].update(before_frame='s000000100'),
    lambda d:d['contact_chain'][2].update(after_frame='invented'),
    lambda d:d['event_mapping'].update(pass_chain_index=True),
    lambda d:d['event_mapping'].update(finish_chain_index=1),
    lambda d:d['event_mapping'].update(goal_frame='s000000600'),
    lambda d:d['outcome'].update(kind='SAVED'),
    lambda d:d.update(questions=[{'reason':'CONTACT'}]),
    lambda d:d['players'][1].update(selected=True,reference_ids=['r1']),
    lambda d:d['link_assessment']['same_ball_release_to_receiver'].update(frames=['s000000700','s000000800']),
])
def test_contradictions_wrong_roles_and_unresolved_brackets_cannot_become_approved_assists(mutation):
    data,context=mapped_observation();mutation(data)
    result=mapped_review(data,context)
    assert result['status']=='UNRESOLVED' and not result['target_events']


def test_changed_reply_source_or_request_hash_cannot_reuse_a_live_receipt():
    data,context=mapped_observation();raw=json.dumps(data)
    receipt={'origin':'LIVE_MODEL_REQUEST','status':'COMPLETED','packet_id':'synthetic',
        'source_video_sha256':context['source_video_sha256'],'payload_sha256':'b'*64,
        'raw_response':raw,'response_sha256':hashlib.sha256(raw.encode()).hexdigest()}
    for key,value in [('source_video_sha256','c'*64),('payload_sha256','c'*64),
                      ('response_sha256','c'*64),('origin','SYNTHETIC_TEST_ONLY')]:
        changed={**receipt,key:value}
        assert resolve_assist(data,context,changed)['target_events']==[]
    data['event_mapping']['goal_frame']='s000000700'
    assert resolve_assist(data,context,receipt)['reasons']==['OBSERVATIONS_DIFFER_FROM_RECEIPT']


@pytest.mark.parametrize('one_touch',[True,False,None])
def test_first_time_finish_needs_explicit_unique_receiving_strike_not_an_invented_extra_touch(one_touch):
    data,context=mapped_observation()
    data['contact_chain'].pop(1)
    data['event_mapping'].update(receive_chain_index=1,finish_chain_index=1,one_touch_finish=one_touch)
    data['link_assessment']['same_ball_release_to_receiver']['frames']=[f's{ms:09}' for ms in (100,200,500,600)]
    result=mapped_review(data,context)
    if one_touch is True:
        assert result['status']=='APPROVED' and result['counts']=={'ASSIST':1}
        event=result['target_events'][0]
        assert event['one_touch_finish'] is True and event['receiver_interval_ms']==event['finishing_contact_interval_ms']
        assert event['contact_ms'] is None
    else:
        assert result['target_events']==[] and result['reasons']==['FIRST_TOUCH_FINISH_NOT_ESTABLISHED']


def test_claimed_one_touch_finish_cannot_contradict_separate_receiving_and_striking_rows():
    data,context=mapped_observation();data['event_mapping']['one_touch_finish']=True
    assert mapped_review(data,context)['target_events']==[]


@pytest.mark.parametrize('side',['LEFT','RIGHT','UNKNOWN'])
def test_limb_review_requires_supported_owner_without_forcing_a_preferred_kicking_side(side):
    data,context=mapped_observation();context['limb_focus']={'start_ms':100,'end_ms':200}
    assert mapped_review(data,context)['reasons']==['RELEASE_LIMB_OWNERSHIP_UNRESOLVED']
    data['contact_ownership_review']={'status':'SUPPORTED','release_actor':'passer','anatomical_side':side,
        'frames':['s000000100','s000000200'],'observation':'Synthetic body-to-foot and outgoing-ball motion'}
    assert mapped_review(data,context)['status']=='APPROVED'
    data['contact_ownership_review']['status']='UNCERTAIN'
    assert mapped_review(data,context)['target_events']==[]


@pytest.mark.parametrize('frames',[['s000000100'],['s000000100','s000000300'],['invented','s000000200']])
def test_leg_count_or_unsupplied_out_of_window_frames_cannot_replace_release_evidence(frames):
    data,context=mapped_observation();context['limb_focus']={'start_ms':100,'end_ms':200}
    data['contact_ownership_review']={'status':'SUPPORTED','release_actor':'passer','anatomical_side':'RIGHT',
        'frames':frames,'observation':'Synthetic motion','leg_map':[{'visible_leg_count':6}]}
    assert mapped_review(data,context)['target_events']==[]


@pytest.mark.parametrize('fact_key',['observation','fact'])
def test_source_cited_goal_facts_are_accepted_without_inventing_missing_frame_ids(fact_key):
    data,context=mapped_observation()
    data['outcome']['evidence']=[{'frame':fid,fact_key:'The moving ball is inside the goal'}
                                for fid in data['outcome']['evidence']]
    assert mapped_review(data,context)['status']=='APPROVED'
    data['outcome']['evidence'][0]['frame']='not_supplied'
    assert mapped_review(data,context)['reasons']==['INVALID_GOAL_SOURCE_EVIDENCE']


def test_another_actors_intervening_chain_action_prevents_direct_assist():
    data,context=mapped_observation()
    extra=deepcopy(data['contact_chain'][1]);extra.update(actor='opponent',before_frame='s000000200',after_frame='s000000300')
    data['contact_chain'].insert(1,extra)
    data['event_mapping'].update(receive_chain_index=2,finish_chain_index=3)
    assert mapped_review(data,context)['reasons']==['INTERVENING_CHAIN_ACTION_UNRESOLVED']


def test_historical_untyped_actual_reply_cannot_be_promoted_by_inventing_missing_mapping():
    path=Path(__file__).resolve().parents[2]/'docs/examples/native-continuous-pass-receipt.json'
    saved=json.loads(path.read_text())
    result=resolve_assist(json.loads(saved['raw_response']),saved['result'],saved)
    assert result['status']=='UNRESOLVED' and result['reasons']==['TYPED_EVENT_MAPPING_REQUIRED']


def test_actual_live_reply_replays_to_the_same_approved_assist_through_the_event_resolver():
    path=Path(__file__).resolve().parents[2]/'docs/examples/native-assist-approval-receipt.json'
    saved=json.loads(path.read_text());context=saved['result']
    result=resolve_assist(json.loads(saved['raw_response']),context,saved)
    assert result==context['automatic_approval']
    assert result['status']=='APPROVED' and result['counts']=={'ASSIST':1}
    event=result['target_events'][0]
    assert event['approval_status']=='APPROVED' and event['reason']=='VISIBLE_DIRECT_ASSIST'
    assert event['contact_ms'] is None and event['contact_basis']=='BRACKETED_VISUAL_SEQUENCE'
    assert event['actor']!=event['receiver']==event['finisher']
    assert event['receipts'][0]['response_sha256']==saved['response_sha256']
    assert event['defensive_contact']['status']=='UNCERTAIN'
    # Replaying a real reply checks the code path; it is not a second model read.
