"""Physical-link decisions must not mistake hypotheses for observed events."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.probe_continuous_pass import assess_link


def observed():
    def field(status):
        return {'status':status,'frames':['s100','s200'],'observation':'Synthetic before/after motion'}
    return {'players':[{'person_id':'passer','selected':True},{'person_id':'receiver','selected':False}],
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
