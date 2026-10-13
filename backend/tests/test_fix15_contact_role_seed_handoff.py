"""A fresh weak seed must not erase a later measured release at role review."""
from copy import deepcopy

import pytest
import ball_trajectory as bt
import contact_role_resolver as roles
import physical_match_reconstruction as physical
import shot_outcome_engine as outcome
from test_fix15_r6_native_seed_selection import setup


def fixture(width=1000,height=1000):
    frames,contact,weak=setup(width,height)
    for ms in range(1140,1421,40):
        frame=deepcopy(frames[-1]);frame['media_ms']=ms
        frame['camera_motion'].update(from_media_ms=frames[-1]['media_ms'],to_media_ms=ms)
        frame['ball_candidates']=[{'box':{'x':.20+(ms-1000)/1000*.30*height/width,
                                         'y':.50,'w':12/width,'h':12/height},'confidence':.40}]
        frames.append(frame)
    for f in frames:
        f['players']=[{'local_track_id':'p1','association_state':'VERIFIED_LOCAL',
            'box':{'x':.20-40/width,'y':.51-100/height,'w':80/width,'h':100/height}}]
        f['global_target']={'status':'VERIFIED','proof_eligible':True,'local_track_id':'p1'}
    touch={'touch_id':'t','media_ms':1000,'end_ms':1000,'scene_id':'synthetic','player_track_id':'p1',
        'status':'VERIFIED','proof_eligible':True,'global_target_id':'GLOBAL_TARGET',
        'global_target_resolution':{'status':'VERIFIED'},'trajectory_change':.8,
        'possession_kinds':['RECEIVE'],'possession_after':'p1','contact_geometry':{'distance_h':.08},
        'ball_at_contact':contact,'ball_after':weak}
    return frames,{'touches':[touch]}


@pytest.mark.parametrize('width,height',[(1000,1000),(1920,1080),(1080,1920)])
def test_role_and_strike_use_the_same_measured_seed_without_lowering_any_gate(width,height):
    frames,graph=fixture(width,height);before=deepcopy((frames,graph));touch=graph['touches'][0]
    old=bt.select_release_ball_trajectory(frames,touch['ball_after'],'synthetic',[],
        anchor_required=True,contact_ball=touch['ball_at_contact'],contact_required=True)
    assert old['rows']==[] and old['contact_binding']['status']=='REJECTED'
    reviewed=roles.apply_contact_roles(graph,{},dense_frames=frames,ball_trajectory=[])
    t=reviewed['touches'][0]
    assert t['ball_after']==touch['ball_after'] and t['ball_after']['confidence']==.035
    assert t['contact_role_seed_qualification']['qualified_seed_ms']==1060
    assert t['release_ball_binding']['status']=='VERIFIED'
    assert t['contact_role']['role']=='RELEASE'
    assert t['contact_role']['source']=='A4_DELAYED_MEASURED_SEPARATION'
    assert t['contact_role']['evidence']['strong_separation_samples']>=roles.DELAYED_MIN_STRONG
    assert bt.RELEASE_REACQUIRE_MIN_CONFIDENCE==.04
    strikes=outcome.find_strike_releases(reviewed,[])
    assert len(strikes)==1
    path=physical._strike_ball_paths(strikes,reviewed,frames,[])[0]
    assert path['seed_ms']==t['contact_role_seed_qualification']['qualified_seed_ms']
    assert strikes[0]['release_seed_qualification']['contact_binding']==t['release_ball_binding']
    assert (frames,graph)==before


def test_qualified_ball_identity_without_strong_separation_is_still_control():
    frames,graph=fixture()
    for f in frames[4:]:
        f['ball_candidates'][0]['box']['x']=.23
    result=roles.apply_contact_roles(graph,{},dense_frames=frames,ball_trajectory=[])
    t=result['touches'][0]
    assert t['release_ball_binding']['status']=='VERIFIED'
    assert t['contact_role_seed_qualification']['qualified_seed_ms']==1060
    assert t['contact_role']['role']=='RECEIVE_CONTROL'
    assert outcome.find_strike_releases(result,[])==[]


@pytest.mark.parametrize('mutation',['rejected','external','missing_contact','unproved_contact',
                                    'predicted_seed','weak_source_not_native','camera_gap','cut',
                                    'source_box_mismatch','competing_seed','missing_body','recontact','spare_flag'])
def test_rejected_or_ambiguous_evidence_cannot_create_a_release(mutation):
    frames,graph=fixture();touch=graph['touches'][0]
    if mutation=='rejected':touch['ball_after']['identity_rejection']='EXPLICIT_REJECTION'
    elif mutation=='external':touch['ball_after']['source']='EXTERNAL_REQUIRED_ANCHOR'
    elif mutation=='missing_contact':touch['ball_at_contact']=None
    elif mutation=='unproved_contact':touch['ball_at_contact']['proof_eligible']=False
    elif mutation=='predicted_seed':touch['ball_after']['state']='PREDICTED_SHORT_GAP'
    elif mutation=='weak_source_not_native':frames[1]['ball_candidates'][0]['state']='SEARCH_ONLY'
    elif mutation=='camera_gap':frames[1]['camera_motion']=None
    elif mutation=='cut':frames[1]['cut_barrier']=True
    elif mutation=='source_box_mismatch':touch['ball_after']['box']['x']+=.005
    elif mutation=='competing_seed':
        rival=deepcopy(frames[2]['ball_candidates'][0]);rival['box']['x']+=.001
        frames[2]['ball_candidates'].append(rival)
    elif mutation=='missing_body':
        for f in frames[4:]:f['players']=[]
    elif mutation=='recontact':
        graph['touches'].append({**deepcopy(touch),'touch_id':'again','media_ms':1500,'end_ms':1500})
    elif mutation=='spare_flag':touch['ball_after']['remote_spare_ball_used']=True
    before=deepcopy((frames,graph))
    global_spare=[{'media_ms':1100,'state':'MEASURED','proof_eligible':True,
                   'box':{'x':.9,'y':.2,'w':.01,'h':.01}}]
    result=roles.apply_contact_roles(graph,{},dense_frames=frames,ball_trajectory=global_spare)
    assert result['touches'][0]['contact_role']['role']=='RECEIVE_CONTROL'
    assert outcome.find_strike_releases(result,[])==[]
    assert (frames,graph)==before


@pytest.mark.parametrize('mutation',['release','unverified'])
def test_reassessment_clears_qualification_metadata_when_no_seed_was_remeasured(mutation):
    frames,graph=fixture();t=graph['touches'][0]
    t['contact_role_seed_qualification']={'status':'QUALIFIED','qualified_seed_ms':99999}
    if mutation=='release':t['possession_kinds']=['RELEASE']
    else:t['status']='CANDIDATE_OCCLUDED';t['proof_eligible']=False
    before=deepcopy(graph)
    result=roles.apply_contact_roles(graph,{},dense_frames=frames,ball_trajectory=[])
    assert 'contact_role_seed_qualification' not in result['touches'][0]
    assert graph==before


def test_forged_or_stale_qualification_record_does_not_supply_a_new_seed():
    frames,graph=fixture();t=graph['touches'][0]
    t['contact_role_seed_qualification']={'status':'QUALIFIED','qualified_seed_ms':99999}
    t['ball_after']['identity_rejection']='EXPLICIT_REJECTION'
    result=roles.apply_contact_roles(graph,{},dense_frames=frames,ball_trajectory=[])
    assert 'contact_role_seed_qualification' not in result['touches'][0]
    assert result['touches'][0]['release_ball_binding']['status']=='REJECTED'
    assert outcome.find_strike_releases(result,[])==[]
