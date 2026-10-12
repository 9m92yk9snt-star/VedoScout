"""Reserve/global ball contacts cannot become the selected shot's outcome."""
from copy import deepcopy
import pytest
import shot_outcome_engine as engine


def fixture():
    def ball(ms,x):
        return {"media_ms":ms,"scene_id":"s","state":"MEASURED","proof_eligible":True,
            "time_authority":"ACTUAL_MEDIA_PTS","used_fallback":False,"cut_barrier":False,
            "box":{"x":x,"y":.45,"w":.02,"h":.02}}
    rows=[ball(1040,.4),ball(1080,.5),ball(1120,.6),ball(1160,.5),ball(1200,.4)]
    strike={"strike_id":"shot","media_ms":1000,"scene_id":"s","player_track_id":"shooter",
        "status":"VERIFIED_PHYSICAL_RELEASE","proof_eligible":True,"active_ball_anchor":deepcopy(rows[0])}
    touch={"touch_id":"contact","media_ms":1120,"end_ms":1120,"representative_ms":1120,
        "scene_id":"s","player_track_id":"defender","status":"VERIFIED","proof_eligible":True,
        "trajectory_change":.9,"ball_before":deepcopy(rows[1]),"ball_at_contact":deepcopy(rows[2]),
        "ball_after":deepcopy(rows[3]),"possession_after":None}
    return strike,rows,touch


def outcome(strike,rows,touch):
    return engine.reconstruct_post_strike_outcome(strike,rows,{"touches":[touch]})


def test_real_three_point_same_ball_deflection_still_counts_as_intervention():
    strike,rows,touch=fixture()
    result=outcome(strike,rows,touch)
    assert result['physical_outcome']=='PLAYER_INTERVENTION'
    assert result['intervention_ball_binding']['status']=='VERIFIED'
    assert result['intervention_ball_binding']['measured_times_ms']==[1080,1120,1160]
    assert result['canonical_event_type'] is None


def test_later_reserve_contact_cannot_intervene_when_the_shot_path_has_ended():
    strike,rows,touch=fixture()
    for key in ['media_ms','end_ms','representative_ms']:touch[key]=1900
    for key in ['ball_before','ball_at_contact','ball_after']:
        touch[key]['media_ms']+=780;touch[key]['box']['x']=.9
    result=outcome(strike,rows,touch)
    assert result['intervention']['status']=='NONE'
    assert result['physical_outcome']=='UNRESOLVED'
    assert result['intervention_ball_binding']['required'] is True
    assert result['intervention_ball_binding']['status']=='REJECTED'
    assert result['goal_plane_crossing']['status']=='UNRESOLVED'
    assert result['save_evidence']['status']=='UNRESOLVED'


@pytest.mark.parametrize('phase',['ball_before','ball_at_contact','ball_after'])
def test_another_ball_at_the_same_time_cannot_supply_any_of_the_three_phases(phase):
    strike,rows,touch=fixture();touch[phase]['box']['x']=.9
    assert outcome(strike,rows,touch)['intervention']['status']=='NONE'


@pytest.mark.parametrize('field,value',[
    ('proof_eligible',False),('state','SEARCH_ONLY'),('state','PREDICTED_SHORT_GAP'),
    ('time_authority','REQUESTED_MEDIA_TIME'),('used_fallback',True),('cut_barrier',True),
    ('cut',True),('scene_id','foreign'),('media_ms',1120.0),
])
def test_non_proof_contact_ball_cannot_bind(field,value):
    strike,rows,touch=fixture();touch['ball_at_contact'][field]=value
    assert outcome(strike,rows,touch)['intervention']['status']=='NONE'


@pytest.mark.parametrize('corruption',['missing_before','missing_contact','missing_after','duplicate_time',
    'row_not_proof','row_predicted','row_fallback','row_cut','unverified_touch','rejected_anchor',
    'wrong_anchor','touch_other_scene','touch_bad_interval'])
def test_incomplete_or_ambiguous_selected_path_fails_closed(corruption):
    strike,rows,touch=fixture()
    if corruption=='missing_before':touch.pop('ball_before')
    elif corruption=='missing_contact':touch.pop('ball_at_contact')
    elif corruption=='missing_after':touch.pop('ball_after')
    elif corruption=='duplicate_time':rows.append(deepcopy(rows[2]))
    elif corruption=='row_not_proof':rows[2]['proof_eligible']=False
    elif corruption=='row_predicted':rows[2]['state']='PREDICTED_SHORT_GAP'
    elif corruption=='row_fallback':rows[2]['used_fallback']=True
    elif corruption=='row_cut':rows[2]['cut_barrier']=True
    elif corruption=='unverified_touch':touch['proof_eligible']=False
    elif corruption=='rejected_anchor':strike['active_ball_anchor']['proof_eligible']=False
    elif corruption=='wrong_anchor':strike['active_ball_anchor']['box']['x']=.9
    elif corruption=='touch_other_scene':touch['scene_id']='foreign'
    elif corruption=='touch_bad_interval':touch['end_ms']=None
    assert outcome(strike,rows,touch)['intervention']['status']=='NONE'


def test_earlier_unrelated_ball_touch_cannot_mask_a_later_valid_deflection():
    strike,rows,touch=fixture();unrelated=deepcopy(touch)
    unrelated.update(touch_id='reserve',media_ms=1100,end_ms=1100,representative_ms=1100)
    unrelated['ball_at_contact']['box']['x']=.9
    result=engine.reconstruct_post_strike_outcome(strike,rows,{'touches':[unrelated,touch]})
    assert result['intervention']['touch_id']=='contact'
    assert result['intervention_ball_binding']['status']=='VERIFIED'


def test_binding_does_not_mutate_the_original_contact_path_or_anchor():
    strike,rows,touch=fixture();original=deepcopy((strike,rows,touch))
    outcome(strike,rows,touch)
    assert (strike,rows,touch)==original


def test_legacy_no_anchor_contract_remains_compatible_without_creating_a_goal():
    strike,rows,touch=fixture();strike.pop('active_ball_anchor')
    for key in ['ball_before','ball_at_contact','ball_after']:touch.pop(key)
    result=outcome(strike,rows,touch)
    assert result['physical_outcome']=='PLAYER_INTERVENTION'
    assert result['intervention_ball_binding']['required'] is False
    assert result['goal_plane_crossing']['status']=='UNRESOLVED'
