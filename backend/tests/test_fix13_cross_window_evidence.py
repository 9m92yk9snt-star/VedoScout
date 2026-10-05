from copy import deepcopy
import pytest
import cross_window_evidence as join
import fix10b_reconciliation as recon
import test_fix10b_reconciliation as fixture

BOX={'x':.2,'y':.3,'w':.1,'h':.2}
BALL={'x':.5,'y':.7,'w':.01,'h':.01}


def measured(ms):
    return {'media_ms':ms,'box':deepcopy(BALL),'state':'MEASURED','proof_eligible':True,
            'time_authority':'ACTUAL_MEDIA_PTS','used_fallback':False}


def cases():
    target=fixture.strike(1000,'target',target=True)
    scorer=fixture.strike(2600,'right_receiver')
    for s in (target,scorer):
        s['active_ball_anchor']={**measured(s['media_ms']), 'source':'VERIFIED_RELEASE_CONTACT_BALL_AFTER','remote_spare_ball_used':False}
    left=fixture.trace([fixture.touch(1000,'target',target=True),fixture.touch(1500,'left_receiver')],[target],[fixture.outcome(target,goal=False)])
    right=fixture.trace([fixture.touch(2600,'right_receiver')],[scorer],[fixture.outcome(scorer,goal=True,crossing_ms=3000)])
    for tr,name,start,end,track in [(left,'left',900,2300,'left_receiver'),(right,'right',2000,3300,'right_receiver')]:
        tr['trace_id']=name
        tr['window'].update(dense_window_id=name,start_ms=start,end_ms=end)
        tr['decoded_frames']=[{'media_ms':ms,'scene_id':'scene_007','time_authority':'ACTUAL_MEDIA_PTS',
            'players':[{'local_track_id':track,'association_state':'VERIFIED_LOCAL','box':deepcopy(BOX),'team':'target_team'}]}
            for ms in range(start,end+1,50)]
        tr['ball_trajectory']=[measured(ms) for ms in range(start,end+1,50)]
    return [left,right]


def test_verified_overlap_connects_pass_receive_shot_goal_without_rewriting_originals():
    traces=cases(); originals=deepcopy(traces)
    assert not any(p['kind']=='ASSIST' for tr in traces for p in recon.proposals_from_trace(tr))
    proposals=recon.collect_proposals({'traces':traces})
    assists=[p for p in proposals if p['kind']=='ASSIST']
    assert len(assists)==1 and assists[0]['source_trace_ids']==['left','right']
    assert assists[0]['target_track_id'] != assists[0]['scorer_track_id']
    assert traces==originals
    out=recon.reconcile_canonical_events(fixture.canonical([]),{'traces':traces})
    assert out['counts']['ASSIST']==1 and out['counts'].get('GOAL',0)==0


@pytest.mark.parametrize('failure',['scene','ball','cut','pts','ambiguous_body','video','target','team','no_anchor','anchor_gap','bounds'])
def test_cross_window_chains_reject_missing_or_conflicting_measurements(failure):
    traces=cases(); right=traces[1]
    if failure=='scene': right['window']['scene_id']='other'
    elif failure=='ball':
        for b in right['ball_trajectory']: b['box']['x']=.8
    elif failure=='cut': right['decoded_frames'][2]['cut_barrier']=True
    elif failure=='pts': right['decoded_frames'][2]['time_authority']='REQUESTED_TIME'
    elif failure=='ambiguous_body':
        for f in right['decoded_frames']: f['players'].append({**deepcopy(f['players'][0]),'local_track_id':'neighbor'})
    elif failure=='video':
        traces[0]['source_video']={'sha256':'a'};right['source_video']={'sha256':'b'}
    elif failure=='target':
        for tr in traces:
            for f in tr['decoded_frames']:
                f['global_target']={'status':'VERIFIED','proof_eligible':True,'local_track_id':'other' if tr is right else 'left_receiver'}
    elif failure=='no_anchor': right['strike_evidence'][0].pop('active_ball_anchor')
    elif failure=='anchor_gap': right['ball_trajectory'][8]['proof_eligible']=False
    elif failure=='team':
        for f in right['decoded_frames']: f['players'][0]['team']='opponent'
    elif failure=='bounds': right['window']['start_ms']=None
    assert not any(p['kind']=='ASSIST' for p in recon.collect_proposals({'traces':traces}))


def test_identical_local_names_cannot_bind_different_bodies():
    traces=cases()
    for f in traces[1]['decoded_frames']:
        f['players'][0]['local_track_id']='left_receiver';f['players'][0]['box']['x']=.8
    traces[1]['strike_evidence'][0]['player_track_id']='left_receiver'
    assert not join.build({'traces':traces})['links']
    assert not any(p['kind']=='ASSIST' for p in recon.collect_proposals({'traces':traces}))


def test_downstream_review_uses_verified_prior_pass_and_continuous_context():
    import physical_match_reconstruction as physical
    traces=cases()
    original=traces[1]['strike_evidence'][0]
    assert not physical._goal_review_eligibility(original,[original],traces[1]['touch_graph'])['eligible']
    jobs=[{'window':traces[1]['window'],'strike':original,'review':{'lane':'CLARIFICATION'},'eligibility':{'eligible':False}}]
    old=deepcopy(jobs)
    updated,audit=physical._apply_cross_window_review_context(jobs,traces)
    assert updated[0]['review']['lane']=='VERIFIED_CHAIN'
    assert updated[0]['eligibility']['target_release_ms']==1000
    assert updated[0]['eligibility']['source_trace_ids']==['left','right']
    assert audit['links'] and jobs==old
    traces[0]['strike_evidence'][0]['active_ball_anchor']['proof_eligible']=False
    updated,_=physical._apply_cross_window_review_context(jobs,traces)
    assert updated[0]['review']['lane']=='CLARIFICATION'
