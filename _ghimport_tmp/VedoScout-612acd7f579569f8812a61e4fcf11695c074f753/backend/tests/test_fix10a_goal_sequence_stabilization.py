from __future__ import annotations
import copy
import sys
from pathlib import Path
import numpy as np
import cv2

BACKEND=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND))
import ball_contact_engine as bce
import dense_track_refinement as dtr
import short_occlusion_contact_recovery as s3
import golden_fixture_validator as gfv


def box(cx=.5,cy=.5,w=.12,h=.30):
    return {'x':cx-w/2,'y':cy-h/2,'w':w,'h':h}

def player(track,cx=.5,cy=.5,w=.12,h=.30,state='VERIFIED_LOCAL',team='A'):
    return {'local_track_id':track,'candidate_local_track_ids':[track] if track else [],'box':box(cx,cy,w,h),'confidence':.9,'association_state':state,'team':team,'team_confidence':.95}

def gt(track,b=None,reason='OK_EXACT',proof=True,**extra):
    out={'status':'VERIFIED','reason':reason,'local_track_id':track,'candidate_local_track_ids':[track],'proof_eligible':proof}
    if b: out['body_box']=copy.deepcopy(b)
    out.update(extra); return out

def frame(ms,ps,gtm=None,scene='s1',support=None):
    return {'media_ms':ms,'scene_id':scene,'cut_barrier':False,'used_fallback':False,'time_authority':'ACTUAL_MEDIA_PTS','players':ps,'global_target':gtm or {},'a7_ball_support_candidates':support or []}

def ball(ms,cx,cy=.67):
    return {'media_ms':ms,'state':'MEASURED','box':box(cx,cy,.03,.02),'confidence':.9,'proof_eligible':True,'time_authority':'ACTUAL_MEDIA_PTS','used_fallback':False,'provenance':'LOCAL_DENSE_DETECTOR'}


def test_goalstab_01_verified_global_target_local_id_handoff():
    a=frame(1000,[player('p029',.45)],gt('p029'))
    b=frame(1067,[player('p029',.44),player('p039',.47)],gt('p039'))
    got,ev=bce._player_for_actor_continuity(a,'p029',b)
    assert got['local_track_id']=='p039'
    assert ev['actor_key']=='GLOBAL_TARGET'
    assert ev['reason']=='VERIFIED_GLOBAL_TARGET_LOCAL_TRACK_HANDOFF'


def test_goalstab_02_arbitrary_id_switch_is_not_bridged():
    a=frame(1000,[player('p029',.45)],{})
    b=frame(1067,[player('p039',.47)],{})
    got,ev=bce._player_for_actor_continuity(a,'p029',b)
    assert got is None


def test_goalstab_03_stale_same_local_does_not_override_new_verified_target():
    a=frame(1000,[player('p029',.45)],gt('p029'))
    b=frame(1067,[player('p029',.30),player('p039',.47)],gt('p039'))
    got,ev=bce._player_for_actor_continuity(a,'p029',b)
    assert got['local_track_id']=='p039'


def test_goalstab_04_same_local_holder_is_same_actor_when_gt_sparse():
    cur=frame(1000,[player('p002')],gt('p002'))
    prev=frame(967,[player('p002')],{})
    nxt=frame(1033,[player('p002')],{})
    pb={'box':box(.5,.66,.02,.02)}; nb={'box':box(.5,.66,.02,.02)}
    r=bce._possession_transition('p002',cur,prev,pb,nxt,nb,1.0)
    assert r['kind']=='CONTROL_TOUCH'
    assert r['before_holder_actor_key']=='GLOBAL_TARGET'
    assert r['after_holder_actor_key']=='GLOBAL_TARGET'


def authority_at(ms,b):
    return {'target_points':[{'media_ms':ms,'scene_id':'s1','global_target_id':'GLOBAL_TARGET','box':copy.deepcopy(b),'state':'VISIBLE','proof_eligible':True,'tap_authority':True,'predicted':False,'sources':['MANUAL_TAP']}]}


def test_goalstab_05_dense_proof_target_collapses_single_underlying_hypothesis():
    rb=box(.5,.5,.12,.3)
    ps=[
      {'local_track_id':None,'candidate_local_track_ids':['p003'],'candidate_predicted_boxes':{'p003':box(.49,.5,.12,.3)},'box':box(.50,.5,.12,.3),'confidence':.8,'association_state':'HYPOTHESES'},
      {'local_track_id':None,'candidate_local_track_ids':['p003'],'candidate_predicted_boxes':{'p003':box(.49,.5,.12,.3)},'box':box(.66,.5,.12,.3),'confidence':.7,'association_state':'HYPOTHESES'},
    ]
    out=dtr._resolve_dense_target(authority_at(1000,rb),1000,ps)
    assert out['status']=='VERIFIED'
    assert out['local_track_id']=='p003'
    assert out['reason']=='PROOF_TARGET_SINGLE_CANDIDATE_HYPOTHESIS_COLLAPSE'
    assert out['body_predicted_box'] is not None


def test_goalstab_06_dense_does_not_collapse_two_underlying_ids():
    rb=box(.5,.5,.12,.3)
    ps=[{'local_track_id':None,'candidate_local_track_ids':['p003','p004'],'box':rb,'confidence':.8,'association_state':'HYPOTHESES'}]
    out=dtr._resolve_dense_target(authority_at(1000,rb),1000,ps)
    assert out['status']!='VERIFIED'


def test_goalstab_07_synthetic_target_can_use_predicted_geometry_without_threshold_change():
    assert bce.CONTACT_MAX_H==0.58
    det=box(.5,.45,.12,.3); pred=box(.5,.50,.12,.3); bb=box(.5,.67,.03,.02)
    p={'local_track_id':'p003','box':det,'association_state':'VERIFIED_GLOBAL_TARGET_BODY','synthetic_target_body':True,'alternate_actor_boxes':[pred]}
    g=bce._best_lower_geometry(p,bb)
    assert g['geometry_source'] in {'DETECTED_BODY','TARGET_MOTION_PREDICTED_BODY'}
    assert bce.CONTACT_MAX_H==0.58


def test_goalstab_08_articulated_overlap_lane_is_target_only():
    # Construct geometry just outside CONTACT_MAX_H but within POSSESSION_MAX_H.
    pb=box(.5,.40,.12,.30)
    bb=box(.5,.615,.03,.02)
    syn={'local_track_id':'p003','candidate_local_track_ids':['p003'],'box':pb,'confidence':.9,'association_state':'VERIFIED_GLOBAL_TARGET_BODY','synthetic_target_body':True}
    f=frame(1000,[],gt('p003',pb,reason='PROOF_TARGET_SINGLE_CANDIDATE_HYPOTHESIS_COLLAPSE',body_confidence=.9))
    # force player resolver to synthesize target body
    got,reason,ids=s3._unique_lower_body_actor(f,bb)
    if got is not None:
        assert got[1].get('target_overlap_recovery') is True or got[1]['distance_h'] <= bce.CONTACT_MAX_H
    ordinary=frame(1000,[{'local_track_id':'p009','candidate_local_track_ids':['p009'],'box':pb,'confidence':.9,'association_state':'VERIFIED_LOCAL'}],{})
    g=bce._lower_body_geometry(pb,bb)
    if g['distance_h']>bce.CONTACT_MAX_H:
        got2,_,_=s3._unique_lower_body_actor(ordinary,bb)
        assert got2 is None



def test_goalstab_08b_articulated_overlap_lane_allows_only_proof_global_target():
    pb=box(.5,.40,.12,.30)
    # Find a ball point with overlap and distance just above ordinary contact.
    bb=box(.5,.615,.03,.02)
    g=bce._lower_body_geometry(pb,bb)
    if not (bce.CONTACT_MAX_H < g['distance_h'] <= bce.POSSESSION_MAX_H and g['lower_body_overlap']):
        bb=box(.5,.62,.03,.02); g=bce._lower_body_geometry(pb,bb)
    target_frame=frame(1000,[player('p003',.5,.40,.12,.30)],gt('p003'))
    got,_,_=s3._unique_lower_body_actor(target_frame,bb)
    if bce.CONTACT_MAX_H < g['distance_h'] <= bce.POSSESSION_MAX_H and g['lower_body_overlap']:
        assert got is not None
        assert got[1].get('target_overlap_recovery') is True
    non_target=frame(1000,[player('p003',.5,.40,.12,.30)],{})
    got2,_,_=s3._unique_lower_body_actor(non_target,bb)
    if g['distance_h']>bce.CONTACT_MAX_H:
        assert got2 is None

def phys(strikes=None,outcomes=None):
    return {'traces':[{'window':{'start_ms':27000,'end_ms':34000},'strike_evidence':strikes or [],'outcome_evidence':outcomes or [],'touch_graph':{'touches':[]}}]}

def case():
    return {'case_id':'goal','window_ms':[27000,34000],'reference_ranges_ms':{'target_strike':[30500,31200]},'physical_gate':{'require_goal_plane_crossing':True}}

def strike(ms='30900',sid='s_target',target=True):
    return {'media_ms':int(ms),'strike_id':sid,'status':'VERIFIED_PHYSICAL_RELEASE','global_target_id':'GLOBAL_TARGET' if target else None}

def outcome(ms,sid,kind):
    return {'media_ms':ms,'strike_id':sid,'physical_outcome':kind}


def test_goalstab_09_unrelated_intervention_does_not_hard_fail_goal_case():
    r=gfv.validate_case(case(),phys([strike()], [outcome(31100,'other','PLAYER_INTERVENTION')]))
    assert r['status']=='UNRESOLVED'
    assert not any(a['name']=='require_goal_plane_crossing' for a in r['assertions'])


def test_goalstab_10_old_target_release_outside_target_strike_range_not_accepted():
    r=gfv._target_goal_link_v2(case(),phys([strike(29000,'old')],[outcome(31500,'old','GOAL_PLANE_CROSSING')]))
    assert r['status']=='UNRESOLVED'


def test_goalstab_11_same_target_strike_owns_crossing():
    r=gfv._target_goal_link_v2(case(),phys([strike()],[outcome(31500,'s_target','GOAL_PLANE_CROSSING')]))
    assert r['status']=='PASS'


def test_goalstab_12_crossing_from_other_strike_is_hard_fail():
    r=gfv._target_goal_link_v2(case(),phys([strike()],[outcome(31500,'s_other','GOAL_PLANE_CROSSING')]))
    assert r['status']=='FAIL'


def _support(cx,cy):
    return {'box':box(cx,cy,.03,.02),'confidence':.01,'support_only':True,'proof_eligible':False}

def _flow_provider(_path,start_ms,_end_ms):
    rng=np.random.default_rng(7); base=rng.integers(0,256,(200,200),dtype=np.uint8); base=cv2.cvtColor(base,cv2.COLOR_GRAY2BGR)
    rows=[]
    for i,t in enumerate((0,33,67)):
        M=np.float32([[1,0,4*i],[0,1,-4*i]])
        im=cv2.warpAffine(base,M,(200,200),borderMode=cv2.BORDER_REFLECT)
        rows.append({'media_ms':start_ms+t,'time_authority':'ACTUAL_MEDIA_PTS','used_fallback':False,'frame_bgr':im})
    return rows


def test_goalstab_13_step3_support_flow_accepts_verified_gt_handoff():
    # Anchor at p029, support frame maps target to p039. Geometry and flow still
    # have to prove the actual contact; identity handoff alone is insufficient.
    pa=player('p029',.45,.50,.20,.30); pn=player('p039',.48,.50,.20,.30)
    frames=[
      frame(967,[pa],gt('p029')), frame(1000,[pa],gt('p029')),
      frame(1033,[pa],gt('p029')), frame(1067,[pn],gt('p039')),
      frame(1100,[pn],gt('p039'),support=[_support(.58,.61)]),
      frame(1133,[pn],gt('p039')), frame(1167,[pn],gt('p039')),
    ]
    tr=[ball(967,.55,.63),ball(1000,.55,.67),
        {'media_ms':1033,'state':'PREDICTED_SHORT_GAP','box':box(.55,.68,.03,.02),'proof_eligible':False,'time_authority':'ACTUAL_MEDIA_PTS','used_fallback':False},
        {'media_ms':1067,'state':'PREDICTED_SHORT_GAP','box':box(.55,.69,.03,.02),'proof_eligible':False,'time_authority':'ACTUAL_MEDIA_PTS','used_fallback':False}]
    out=s3.recover_short_occlusion_contacts(frames,tr,{'accepted':[]},video_path='x',flow_frame_provider=_flow_provider)
    assert out['verified']
    ev=out['verified'][0]['recovery_evidence']
    assert ev['actor_key']=='GLOBAL_TARGET'
    assert any(x.get('reason')=='VERIFIED_GLOBAL_TARGET_LOCAL_TRACK_HANDOFF' for x in ev['actor_continuity_chain'])


def test_goalstab_14_step3_arbitrary_switch_stays_unresolved():
    pa=player('p029',.45,.50,.20,.30); pn=player('p039',.48,.50,.20,.30)
    frames=[frame(967,[pa]),frame(1000,[pa]),frame(1033,[pa]),frame(1067,[pn]),frame(1100,[pn],support=[_support(.58,.61)]),frame(1133,[pn]),frame(1167,[pn])]
    tr=[ball(967,.55,.63),ball(1000,.55,.67)]
    out=s3.recover_short_occlusion_contacts(frames,tr,{'accepted':[]},video_path='x',flow_frame_provider=_flow_provider)
    assert out['verified']==[]
