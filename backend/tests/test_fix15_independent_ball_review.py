"""Audited image-reader fallback fixtures, not original-video acceptance."""
from copy import deepcopy
import hashlib
import json

import cv2
import numpy as np
import pytest

import independent_ball_review as classified
import native_goal_review as native_review
import native_ball_reappearance as native
import fix10a_vision_providers as vision
from test_fix15_native_goal_reappearance import fixture, canvas_with, box, run_full, VIDEO_SHA, MODEL_SHA


def inputs():
    pre,g,candidates,images=fixture()
    times=sorted({r['media_ms'] for r in pre+g['occlusion_crossing_audit']['occlusion_rows']
                  +g['ball_reappearance_audit']['post_occlusion_rows']})
    post={r['media_ms']:r for r in g['ball_reappearance_audit']['post_occlusion_rows']}
    before={r['media_ms']:r for r in pre}
    rows=[]
    for i,ms in enumerate(times,1):
        primary=before.get(ms) or post.get(ms)
        b=primary.get('box',primary.get('ball_box')) if primary else None
        if ms not in images:images[ms]=canvas_with(*([b] if b else []),box(.95,.65))
        rows.append({'idx':i,'ball_visible':bool(primary),'ball_box':deepcopy(b),
            'relation':'FIELD_SIDE' if ms<=1000 else 'BEYOND_LINE_INSIDE_MOUTH' if primary else 'OCCLUDED_GOAL_MOUTH',
            'occluder':'PLAYER_BODY' if not primary else 'UNKNOWN','confidence':'high',
            'visible_balls_complete':True,'other_visible_balls':[{'box':box(.95,.65),'confidence':'high'}]})
    data={'ball_classification_protocol':classified.PROTOCOL,
          'frames':[{'idx':i,'visible':True,'p1':g['line']['p1'],'p2':g['line']['p2'],'confidence':'high'}
                    for i in range(1,len(times)+1)],'ball_evidence':rows}
    review={'response_coverage':{'status':'COMPLETED','input_frame_count':len(times)},
            'occlusion_crossing_audit':deepcopy(g['occlusion_crossing_audit']),
            'ball_evidence':deepcopy(g['ball_reappearance_audit']['post_occlusion_rows'])}
    return pre,g,review,images,data,times


def bind(tmp_path,review,images,data,times):
    paths=[]
    for ms in times:
        p=tmp_path/f'{ms}.jpg'
        assert cv2.imwrite(str(p),images[ms])
        paths.append(str(p))
    raw=json.dumps(data,sort_keys=True)
    review['model_review_audit']=vision._model_audit(raw,'synthetic classification fixture',paths,times)
    review['model_review_audit'].update(provider='LOCAL_NATIVE_CPU',model='fixture-image-classifier')
    review['native_reader_input_audit']=classified.bind_input(review,paths,times,images)


def measure(pre,review,images,camera=None,detector=None):
    return native_review.measure_visual_review(review,pre[-1],images,video_sha256=VIDEO_SHA,
        model_sha256=MODEL_SHA,detect_frame=detector or (lambda *_:([],[])),
        camera_estimator=camera or (lambda *_:(np.array([[1.,0.,0.],[0.,1.,0.]]),'fixture-background')),
        reference_history=[(r,images[r['media_ms']]) for r in pre[:-1]])


def test_image_classification_and_native_pixels_can_pass_without_yolo_ball_proposals(tmp_path):
    pre,g,review,images,data,times=inputs();bind(tmp_path,review,images,data,times)
    review['ball_reappearance_identity']={'status':'VERIFIED_SAME_BALL','invented':True}
    snapshot=deepcopy(review)
    audit=measure(pre,review,images)
    link=audit['identity_link']
    assert link['status']=='VERIFIED_SAME_BALL',audit
    assert link['appearance_similarity']>=.90 and link['appearance_margin']>=.12
    assert len(link['stationary_ball_controls'])==1
    assert [r['media_ms'] for r in link['reference_history']]==[900,950]
    assert 'invented' not in link
    assert all(r['box_source']=='INDEPENDENT_IMAGE_CLASSIFIER_WITH_NATIVE_PIXEL_REID'
               for r in audit['post_occlusion_rows'])
    for r in link['after_observations']:
        assert r['classification_source']==classified.SOURCE
        assert 'confidence' not in r and 'model_sha256' not in r
        assert r['classifier_confidence']=='high'
        assert r['native_pixel_sha256']==native._sha(native._crop(images[r['media_ms']],r['box']))
    g['ball_reappearance_audit']=audit
    g['model_review_audit']=deepcopy(review['model_review_audit'])
    result=run_full(pre,g)
    assert result['physical_outcome']=='GOAL_PLANE_CROSSING'
    assert result['ball_proof_gate']['status']=='VERIFIED'
    assert audit['classification_audit']['input_binding']==review['native_reader_input_audit']
    assert review==snapshot


@pytest.mark.parametrize('mutation',['missing_audit','wrong_model_input','wrong_model_response','wrong_pixel_hash'])
def test_final_goal_gate_rechecks_the_classification_provenance(tmp_path,mutation):
    pre,g,review,images,data,times=inputs();bind(tmp_path,review,images,data,times)
    g['ball_reappearance_audit']=measure(pre,review,images)
    g['model_review_audit']=deepcopy(review['model_review_audit'])
    if mutation=='missing_audit':g.pop('model_review_audit')
    elif mutation=='wrong_model_input':g['model_review_audit']['input_sha256']='f'*64
    elif mutation=='wrong_model_response':g['model_review_audit']['raw_response']='different classification'
    elif mutation=='wrong_pixel_hash':g['ball_reappearance_audit']['identity_link']['after_observations'][0]['native_pixel_sha256']='f'*64
    assert run_full(pre,g)['physical_outcome']!='GOAL_PLANE_CROSSING'


@pytest.mark.parametrize('mutation',[
    'protocol_missing','unreviewed_visible_balls','weak_class','weak_alternative',
    'before_is_not_ball','reserve_missing_before','reserve_missing_after',
    'duplicate_idx','duplicate_frame','changed_pixels','changed_encoded_hash',
    'bad_response_hash','user_provider','partial_review','crop_mapping',
    'missing_native_binding','wrong_after_box','camera_missing','camera_singular',
    'unreviewed_local_alternative','flat_pixels','moving_identical_competitor'])
def test_ambiguous_or_unbound_visual_evidence_cannot_create_a_goal(tmp_path,mutation):
    pre,g,review,images,data,times=inputs()
    rows=data['ball_evidence'];first_after=next(r for r in rows if r['idx']==times.index(1667)+1)
    before=next(r for r in rows if r['idx']==times.index(1000)+1)
    camera=None;detector=None
    if mutation=='protocol_missing':data.pop('ball_classification_protocol')
    elif mutation=='unreviewed_visible_balls':first_after['visible_balls_complete']=False
    elif mutation=='weak_class':first_after['confidence']='low'
    elif mutation=='weak_alternative':first_after['other_visible_balls'][0]['confidence']='medium'
    elif mutation=='before_is_not_ball':before['ball_visible']=False;before['ball_box']=None
    elif mutation=='reserve_missing_before':before['other_visible_balls']=[]
    elif mutation=='reserve_missing_after':first_after['other_visible_balls']=[]
    elif mutation=='duplicate_idx':rows[-1]['idx']=rows[-2]['idx']
    elif mutation=='duplicate_frame':data['frames'][-1]['idx']=data['frames'][-2]['idx']
    elif mutation=='wrong_after_box':first_after['ball_box']=box(.60)
    elif mutation=='camera_missing':camera=lambda *_:(None,'missing')
    elif mutation=='camera_singular':camera=lambda *_:(np.zeros((2,3)),'singular')
    elif mutation=='unreviewed_local_alternative':detector=lambda *_:([],[{'box':box(.4),'confidence':.9}])
    elif mutation=='flat_pixels':
        for image in images.values():image[:]=125
    elif mutation=='moving_identical_competitor':
        for ms,cx in zip((1667,1717,1767),(.35,.39,.43)):
            row=next(r for r in rows if r['idx']==times.index(ms)+1)
            row['other_visible_balls'].append({'box':box(cx,.65),'confidence':'high'})
            images[ms]=canvas_with(row['ball_box'],box(.95,.65),box(cx,.65))
    bind(tmp_path,review,images,data,times)
    if mutation=='changed_pixels':images[1717][0,0]=0
    elif mutation=='changed_encoded_hash':review['native_reader_input_audit']['rows'][0]['encoded_input_sha256']='f'*64
    elif mutation=='bad_response_hash':review['model_review_audit']['response_sha256']='f'*64
    elif mutation=='user_provider':review['model_review_audit']['provider']='USER_OBSERVATION'
    elif mutation=='partial_review':review['response_coverage']['status']='PARTIAL'
    elif mutation=='crop_mapping':review['model_review_audit']['response_coordinate_mapping']={'roi':[0,0,1,1]}
    elif mutation=='missing_native_binding':review.pop('native_reader_input_audit')
    audit=measure(pre,review,images,camera,detector)
    assert audit is None or audit['status']=='UNRESOLVED',audit
    if audit:
        assert audit['identity_link']['proof_eligible'] is False
        g['ball_reappearance_audit']=audit
        assert run_full(pre,g)['physical_outcome']!='GOAL_PLANE_CROSSING'


def test_valid_classifier_cannot_supply_identity_when_native_crop_hash_changes(tmp_path):
    pre,_,review,images,data,times=inputs();bind(tmp_path,review,images,data,times)
    rows=classified.extract(review,images,pre[-1]['scene_id'])['rows_by_ms']
    active=[next(r for r in rows[ms] if r['primary']) for ms in (1667,1717,1767)]
    for r in active:r['camera_alignment']={'status':'MEASURED','reference_media_ms':1000,
                                          'affine_to_reference':[[1.,0.,0.],[0.,1.,0.]]}
    active[1]['native_pixel_sha256']=hashlib.sha256(b'other pixels').hexdigest()
    link=native.measure_native_link(pre[-1],[{'track_id':'active','observations':active}],images,video_sha256=VIDEO_SHA)
    assert link['status']=='UNRESOLVED'


def test_provider_selects_valid_image_fallback_automatically(tmp_path,monkeypatch):
    pre,_,review,images,data,times=inputs();bind(tmp_path,review,images,data,times)
    provider=vision.build_shadow_providers(None,'fixture','unused')
    monkeypatch.setattr(provider,'_native_goal_context',lambda:{'video_sha256':VIDEO_SHA,
        'model_sha256':MODEL_SHA,'detect_frame':lambda *_:([],[]),
        'camera_estimator':lambda *_:(np.array([[1.,0.,0.],[0.,1.,0.]]),'fixture-background')})
    audit=provider._measure_goal_reappearance(review,{'rows':pre},images)
    assert audit['identity_link']['status']=='VERIFIED_SAME_BALL'
    assert audit['native_detector_attempt_reason']=='NATIVE_GOAL_REVIEWED_BALL_NOT_INDEPENDENTLY_CLASSIFIED'
    assert provider.goal_calls==0  # No extra reader calls by the fallback.


def test_identity_stays_unresolved_without_the_independent_protocol(tmp_path,monkeypatch):
    pre,_,review,images,data,times=inputs();data.pop('ball_classification_protocol')
    bind(tmp_path,review,images,data,times)
    provider=vision.build_shadow_providers(None,'fixture','unused')
    monkeypatch.setattr(provider,'_native_goal_context',lambda:{'video_sha256':VIDEO_SHA,
        'model_sha256':MODEL_SHA,'detect_frame':lambda *_:([],[]),
        'camera_estimator':lambda *_:(np.array([[1.,0.,0.],[0.,1.,0.]]),'fixture-background')})
    audit=provider._measure_goal_reappearance(review,{'rows':pre},images)
    assert audit['identity_link']['status']=='UNRESOLVED'
    assert 'classification_audit' not in audit


def test_goal_provider_binds_the_single_reader_call_to_its_original_inputs(tmp_path,monkeypatch):
    pre,g,_,images,data,times=inputs()
    for r in pre:
        r.update(confidence=.85,provenance='RELEASE_ANCHORED_NATIVE_CAMERA_MOTION',
                 frame_dimensions={'width':400,'height':300,'source':'DECODED_NATIVE_PIXELS'})
    strike={'media_ms':900,'scene_id':'fixture-scene','status':'VERIFIED_PHYSICAL_RELEASE',
        'proof_eligible':True,'active_ball_anchor':{**deepcopy(pre[0]),'remote_spare_ball_used':False},
        '_goal_review_ball_path':{'source':'VERIFIED_RELEASE_ANCHOR','seed_ms':900,'rows':pre,
            'contact_binding':{'status':'VERIFIED','reason':'MEASURED_CONTACT_TO_EXACT_RELEASE_ANCHOR',
                               'contact_ms':900,'seed_ms':900}}}
    video=tmp_path/'synthetic-video';video.write_bytes(b'synthetic source, not an original football video')
    provider=vision.build_shadow_providers('fixture-no-sdk','fixture',str(video))
    monkeypatch.setattr(vision,'_goal_review_times',lambda *a,**k:times)
    monkeypatch.setattr(vision,'_read_frames',lambda *a:{ms:(ms,im) for ms,im in images.items()})
    monkeypatch.setattr(provider,'_scan_native_goal_gap',lambda *a:None)
    monkeypatch.setattr(provider,'_inspect_goal_gap',lambda *a:None)
    monkeypatch.setattr(provider,'_native_goal_context',lambda:{'video_sha256':VIDEO_SHA,
        'model_sha256':MODEL_SHA,'detect_frame':lambda *_:([],[]),
        'camera_estimator':lambda *_:(np.array([[1.,0.,0.],[0.,1.,0.]]),'fixture-background')})
    data.update(geometry_status='VERIFIED',same_ball_continuity=False,
                crossing='UNRESOLVED',crossing_confidence='low')
    calls=[]
    def reader(_fn,items,**_kwargs):
        args=items[0][0];paths,actual_times=args[2:4]
        assert actual_times==times
        calls.append(actual_times)
        raw=json.dumps(data)
        audit=vision._model_audit(raw,'synthetic fixture reader',paths,actual_times)
        audit.update(provider='LOCAL_NATIVE_CPU',model='fixture-image-classifier')
        result=vision.parse_goal_scene_response(raw,actual_times,audit)
        # Model-supplied event identity must be discarded by the parent.
        result['ball_reappearance_audit']={'identity_link':{'status':'VERIFIED_SAME_BALL','invented':True}}
        result['native_reader_input_audit']={'invented':True}
        return [result]
    monkeypatch.setattr(vision.support_vision_runner,'run_support_vision',reader)
    result=provider.goal_geometry_provider({'dense_window_id':'fixture','start_ms':800,'end_ms':2800},strike)
    assert len(calls)==provider.goal_calls==1
    link=result['ball_reappearance_audit']['identity_link']
    assert link['status']=='VERIFIED_SAME_BALL',result['ball_reappearance_audit']
    assert 'invented' not in link
    assert link['after_observations'][0]['classification_source']==classified.SOURCE
    assert result['visual_crossing_audit']['proof_ready'] is False  # hidden crossing not invented
