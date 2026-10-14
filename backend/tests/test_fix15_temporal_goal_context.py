"""Search/focus/context must improve inspection without manufacturing goals."""
from copy import deepcopy
import json
import hashlib

import cv2
import numpy as np
import pytest

import temporal_ball_search as temporal
import native_goal_frame as goal_frame
import native_ball_reappearance as native
import goal_context_observations as context
import goal_review_sampling as sampling
import fix10a_vision_providers as vision
from test_fix15_native_goal_reappearance import fixture,ball,canvas_with,detected,VIDEO_SHA
from test_fix10a_native_goal_focus import job
from test_fix15_r6_native_goal_parser import payload
from test_fix15_native_goal_reappearance import run_full
import goal_reappearance


def alignments(times,reference=1000):
    return {str(ms):{'status':'MEASURED','reference_media_ms':reference,
                    'affine_to_reference':[[1.,0.,0.],[0.,1.,0.]]} for ms in times}


def test_known_ball_pixels_open_after_search_without_any_semantic_detection():
    pre,_,_,images=fixture(reserve=False)
    before=deepcopy(images)
    result=temporal.search(pre[-1],images,alignments(images),video_sha256=VIDEO_SHA)
    assert result['reason']=='TEMPORAL_CANDIDATES_REQUIRE_INDEPENDENT_BALL_AND_GOAL_REVIEW'
    assert result['candidate_tracks']
    assert any(t['motion_diameters']>=.5 for t in result['candidate_tracks'])
    assert result['proof_eligible'] is False and result['canonical_events_applied']==0
    candidates=[{'track_id':t['track_id'],'observations':t['observations']} for t in result['candidate_tracks']]
    assert native.measure_native_link(pre[-1],candidates,images,video_sha256=VIDEO_SHA)['status']=='UNRESOLVED'
    assert all(np.array_equal(images[ms],before[ms]) for ms in images)


def test_camera_pan_does_not_prioritize_a_stationary_reference_patch():
    before=ball(1000,.60)
    images={1000:canvas_with(before['box'])}
    camera=alignments([1000,1667,1717,1767])
    for ms,shift in [(1667,0),(1717,20),(1767,40)]:
        images[ms]=canvas_with(detected(ms,.6+shift/400)['box'])
        camera[str(ms)]['affine_to_reference'][0][2]=-shift
    result=temporal.search(before,images,camera,video_sha256=VIDEO_SHA)
    assert result['suggested_review_ms']==[]
    assert result['proof_eligible'] is False


@pytest.mark.parametrize('mutation',['user_reference','missing_camera','singular_camera','foreign_camera','bad_pts','changed_pixels'])
def test_foreign_or_unmeasured_inputs_cannot_become_temporal_evidence(mutation):
    pre,_,_,images=fixture(reserve=False);before=pre[-1];camera=alignments(images)
    if mutation=='user_reference':before['source']='USER_ANNOTATION'
    elif mutation=='missing_camera':camera.pop('1717')
    elif mutation=='singular_camera':camera['1717']['affine_to_reference']=[[0,0,0],[0,0,0]]
    elif mutation=='foreign_camera':camera['1717']['reference_media_ms']=999
    elif mutation=='bad_pts':images['not pts']=images[1667]
    elif mutation=='changed_pixels':images[1717]=images[1717].astype(np.float32)
    result=temporal.search(before,images,camera,video_sha256=VIDEO_SHA)
    assert result['suggested_review_ms']==[]
    assert not result['candidate_tracks']
    assert result['proof_eligible'] is False


def test_user_history_cannot_supply_reference_appearance():
    pre,_,_,images=fixture(reserve=False)
    row={**pre[-2],'source':'USER_OBSERVATION'}
    result=temporal.search(pre[-1],images,alignments(images),video_sha256=VIDEO_SHA,
                           reference_history=[(row,images[1000])])
    assert result['reference_history']==[]


@pytest.mark.parametrize('shift',[0,10000])
def test_native_candidates_refocus_one_reader_budget_preserving_contact_and_terminal(shift):
    d=job();s,p=d['strike'],d['shot_track']
    s['media_ms']+=shift;s['active_ball_anchor']['media_ms']+=shift
    p['seed_ms']+=shift;p['contact_binding']['seed_ms']+=shift;p['contact_binding']['contact_ms']+=shift
    for row in p['rows']:row['media_ms']+=shift
    original=vision._goal_review_times(1000+shift,4000+shift,12,focus_end_ms=1200+shift,anchor_ms=1100+shift)
    candidates={'source':'TEMPORAL_NATIVE_APPEARANCE_SEARCH','status':'SEARCH_ONLY','proof_eligible':False,
                'canonical_events_applied':0,'suggested_review_ms':[1667+shift,1717+shift,1767+shift]}
    selected=sampling.refocus_reader_times(original,s,p,candidates,budget=12,start_ms=shift,end_ms=4000+shift)
    assert len(selected)<=12
    assert {1000+shift,1100+shift,1150+shift,1200+shift,3600+shift,1667+shift,1717+shift,1767+shift}<=set(selected)
    assert selected==sorted(set(selected))
    candidates['source']='USER_OBSERVATION'
    assert sampling.refocus_reader_times(original,s,p,candidates,budget=12,start_ms=shift,end_ms=4000+shift)==original


def test_refocus_retains_before_history_at_its_actual_pts_without_more_reader_images():
    data=job();strike,path=data['strike'],data['shot_track']
    path['rows'].extend([{**deepcopy(path['rows'][-1]),'media_ms':ms} for ms in (1250,1300,1350)])
    original=vision._goal_review_times(1000,4000,12,focus_end_ms=1350,anchor_ms=1100)
    assert 1250 not in original and 1300 not in original
    appearance={'source':'TEMPORAL_NATIVE_APPEARANCE_SEARCH','status':'SEARCH_ONLY',
        'proof_eligible':False,'canonical_events_applied':0,
        'suggested_review_ms':[1667,1717,1767,1800,1850,1900]}
    before=deepcopy(data)
    selected=sampling.refocus_reader_times(original,strike,path,appearance,budget=12,start_ms=0,end_ms=4000)
    assert {1250,1300,1350,1667,1717,1767}<=set(selected)
    assert {strike['media_ms'],path['seed_ms'],original[-1]}<=set(selected)
    assert len(selected)==12 and selected==sorted(set(selected))
    assert data==before
    # A small budget must preserve the old plan rather than discard required
    # contact/terminal context to fit new after candidates.
    small=vision._goal_review_times(1000,4000,5,focus_end_ms=1350,anchor_ms=1100)
    assert sampling.refocus_reader_times(small,strike,path,appearance,budget=5,start_ms=0,end_ms=4000)==small


@pytest.mark.parametrize('shift',[0,30000])
def test_six_unclassified_proposals_cannot_remove_the_original_short_gap_coverage(shift):
    data=job();strike,path=data['strike'],data['shot_track']
    path['rows'].extend([{**deepcopy(path['rows'][-1]),'media_ms':ms} for ms in (1250,1300,1350)])
    strike['media_ms']+=shift;strike['active_ball_anchor']['media_ms']+=shift
    path['seed_ms']+=shift;path['contact_binding']['seed_ms']+=shift;path['contact_binding']['contact_ms']+=shift
    for row in path['rows']:row['media_ms']+=shift
    original=vision._goal_review_times(1000+shift,4000+shift,12,focus_end_ms=1350+shift,anchor_ms=1100+shift)
    appearance={'source':'TEMPORAL_NATIVE_APPEARANCE_SEARCH','status':'SEARCH_ONLY',
        'proof_eligible':False,'canonical_events_applied':0,
        'suggested_review_ms':[ms+shift for ms in (1417,1717,1767,1967,2133,2217)]}
    selected=sampling.refocus_reader_times(original,strike,path,appearance,budget=12,start_ms=shift,end_ms=4000+shift)
    assert {1250+shift,1300+shift,1350+shift,1417+shift,1717+shift,1767+shift}<=set(selected)
    assert len((set(original)-{1000+shift,1100+shift,1350+shift,3600+shift})&set(selected))>=3
    assert 2025+shift in selected  # the original 75%-horizon observation
    assert len(selected)==12


@pytest.mark.usefixtures('inline_support_vision')
def test_provider_passes_original_before_and_proposed_after_images_to_one_review(monkeypatch):
    data=job();strike,path=data['strike'],data['shot_track']
    path['rows'].extend([{**deepcopy(path['rows'][-1]),'media_ms':ms} for ms in (1250,1300,1350)])
    captured={'reviews':0}
    def read(_path,times):
        return {ms:(ms,np.full((32,32,3),ms%256,np.uint8)) for ms in times}
    def scan(_self,_strike,_path,images,_start,_end):
        for ms in (1250,1300,1350,1667,1717,1767):
            images[ms]=np.full((32,32,3),ms%256,np.uint8)
        return {'status':'SEARCH_ONLY','appearance_search':{
            'source':'TEMPORAL_NATIVE_APPEARANCE_SEARCH','status':'SEARCH_ONLY',
            'proof_eligible':False,'canonical_events_applied':0,'suggested_review_ms':[1667,1717,1767]}}
    def write(file,image):
        captured.setdefault('pixel_values',[]).append(int(image[0,0,0]))
        file.write_bytes(b'fixture');return True
    async def review(_key,_session,_files,times,*,ball_reference=None):
        captured['reviews']+=1;captured['times']=times;captured['reference']=ball_reference
        return {'geometry_status':'UNRESOLVED','frames':[],'reason':'fixture_no_goal_verdict'}
    monkeypatch.setattr(vision,'_read_frames',read)
    monkeypatch.setattr(vision.ShadowVisionProviders,'_scan_native_goal_gap',scan)
    monkeypatch.setattr(vision,'_write_jpg',write)
    monkeypatch.setattr(vision,'read_goal_scene_evidence',review)
    provider=vision.ShadowVisionProviders('injected-test-key','test').bind_video_path('dummy')
    result=provider.goal_geometry_provider(data['window'],sampling.provider_strike(data))
    assert captured['reviews']==provider.goal_calls==1
    assert {1250,1300,1350,1667,1717,1767}<=set(captured['times'])
    assert len(captured['times'])<=vision.MAX_GOAL_FRAMES
    assert captured['pixel_values']==[ms%256 for ms in captured['times']]
    assert captured['reference']['media_ms']==path['seed_ms']
    assert result['sampling_audit']['native_appearance_focus_used'] is True
    assert result['status']=='UNRESOLVED' and result['visual_crossing_audit']['proof_ready'] is False


def test_goal_frame_image_rectangle_does_not_certify_goal_depth():
    image=np.full((300,400,3),(40,110,40),np.uint8)
    cv2.line(image,(120,80),(340,80),(220,220,220),5)
    cv2.line(image,(120,80),(120,205),(220,220,220),5)
    cv2.line(image,(340,80),(340,205),(220,220,220),5)
    result=goal_frame.inspect({1000:image,1100:image.copy()})
    assert any(r['projected_frame_candidates'] for r in result['rows'])
    assert result['depth_verified'] is False and result['proof_eligible'] is False
    assert result['status']=='SEARCH_ONLY'


def context_rows():
    return [{'idx':i,'same_goalkeeper_tracked':True,'head_visible':True,'gloves_visible':True,
             'head_direction':'IMAGE_RIGHT','arms_gloves_direction':'IMAGE_RIGHT',
             'foot_contact_visible':i==1,'release_foot':'RIGHT','active_ball_outside_posts':'NOT_VISIBLE',
             'visible_possession':'NONE_VISIBLE','confidence':'high'} for i in range(1,4)]


def test_all_positive_context_cues_cannot_create_a_hidden_crossing():
    data=payload();data['context_evidence']=context_rows()
    data['ball_evidence'][1].update(ball_visible=False,ball_box=None,relation='OCCLUDED_GOAL_MOUTH',occluder='PLAYER_BODY')
    parsed=vision.parse_goal_scene_response(json.dumps(data),[1000,1100,1200])
    assert parsed['contextual_support_evidence']['status']=='COMPLETED'
    assert parsed['contextual_support_evidence']['rows'][0]['release_foot']=='RIGHT'
    assert parsed['contextual_support_evidence']['absence_proves_no_hidden_contact'] is False
    assert parsed['proof_ready'] is False
    assert parsed['proof_reason']=='STRUCTURED_WHOLE_BALL_CROSSING_NOT_PROVEN'


def test_unseen_keeper_parts_and_missing_context_stay_unknown():
    rows=context_rows();rows[0].update(gloves_visible=False,head_visible=False,foot_contact_visible=False)
    parsed=context.parse(rows[:2],[1000,1100,1200])
    assert parsed['status']=='PARTIAL_RESPONSE' and parsed['missing_media_ms']==[1200]
    assert parsed['rows'][0]['arms_gloves_direction']==parsed['rows'][0]['head_direction']=='UNKNOWN'
    assert parsed['rows'][0]['release_foot']=='UNKNOWN'
    assert context.parse([rows[0],rows[0]],[1000,1100,1200])['status']=='INVALID_CONTEXT_RESPONSE'


def airborne_fixture():
    pre,g,_,images=fixture(reserve=False)
    line={'p1':{'x':.4,'y':.6},'p2':{'x':.98,'y':.6}}
    for row in g['line_by_ms']:row['line']=deepcopy(line)
    g['line']=deepcopy(line)
    for row in g['field_side_by_ms']:row['point']={'x':.6,'y':.8}
    rows=[{'media_ms':r['media_ms'],'ball_visible':True,'ball_box':deepcopy(r['box']),
           'confidence':'high','relation':'FIELD_SIDE','ball_airborne':True,
           'depth_relation':'IN_FRONT_OF_GOAL','depth_basis':'PERSPECTIVE_TO_GOAL_FRAME'} for r in pre]
    rows.extend({**deepcopy(r),'ball_airborne':None,'depth_relation':'UNKNOWN','depth_basis':'UNKNOWN'}
                for r in g['occlusion_crossing_audit']['occlusion_rows'])
    rows.extend({**deepcopy(r),'ball_airborne':False,'depth_relation':'INSIDE_GOAL_VOLUME',
                 'depth_basis':'VISIBLE_NET_CONTACT'} for r in g['ball_reappearance_audit']['post_occlusion_rows'])
    times=[r['media_ms'] for r in rows]
    data={'frames':[{'idx':i,'visible':True,'p1':line['p1'],'p2':line['p2'],'confidence':'high'}
                    for i in range(1,len(times)+1)],
          'ball_evidence':[{**r,'idx':i+1} for i,r in enumerate(rows)]}
    raw=json.dumps(data)
    g['response_coverage']={'status':'COMPLETED','input_frame_count':len(times)}
    g['model_review_audit']={'provider':'openai','model':'synthetic-fixture-no-sdk','raw_response':raw,
        'media_ms':times,'response_sha256':hashlib.sha256(raw.encode()).hexdigest(),
        'input_sha256':hashlib.sha256(b''.join(im.tobytes() for _,im in sorted(images.items()))).hexdigest()}
    return pre,g,data


def test_airborne_field_position_is_not_confused_with_ground_line_image_side():
    pre,g,_=airborne_fixture()
    m=goal_reappearance._metrics(pre[-1]['box'],g,pre[-1]['media_ms'])
    assert m['field_signed_distance']<0  # image position, not the ball's 3D depth
    result=run_full(pre,g)
    assert result['ball_proof_gate']['status']=='VERIFIED'
    segment=result['goal_plane_crossing']['evidence'][0]
    assert segment['before_field_space_authority']=='AUDITED_AIRBORNE_WORLD_RELATION'
    assert segment['airborne_depth_audit']['direct_hidden_crossing_observed'] is False
    assert segment['crossing_interval_ms']==[1000,1667]


@pytest.mark.parametrize('mutation',['missing_audit','bad_hash','user_provider','one_before','wrong_before_box',
                                     'unclear_depth','not_airborne','missing_after_depth','wrong_input_count','missing_frames'])
def test_airborne_depth_cannot_come_from_unbound_context_or_reactions(mutation):
    pre,g,data=airborne_fixture();audit=g['model_review_audit']
    if mutation=='missing_audit':g.pop('model_review_audit')
    elif mutation=='bad_hash':audit['response_sha256']='0'*64
    elif mutation=='user_provider':audit['provider']='USER_OBSERVATION'
    elif mutation=='one_before':data['ball_evidence'][0]['depth_relation']='UNKNOWN';data['ball_evidence'][1]['depth_relation']='UNKNOWN'
    elif mutation=='wrong_before_box':data['ball_evidence'][2]['ball_box']['x']=.1
    elif mutation=='unclear_depth':data['ball_evidence'][2]['depth_basis']='UNKNOWN'
    elif mutation=='not_airborne':data['ball_evidence'][2]['ball_airborne']=False
    elif mutation=='missing_after_depth':data['ball_evidence'][-1]['depth_relation']='UNKNOWN'
    elif mutation=='wrong_input_count':g['response_coverage']['input_frame_count']=1
    elif mutation=='missing_frames':data['frames']=[]
    if mutation in {'one_before','wrong_before_box','unclear_depth','not_airborne','missing_after_depth','missing_frames'}:
        audit['raw_response']=json.dumps(data)
        audit['response_sha256']=hashlib.sha256(audit['raw_response'].encode()).hexdigest()
    assert run_full(pre,g)['goal_plane_crossing']['status']!='VERIFIED'
