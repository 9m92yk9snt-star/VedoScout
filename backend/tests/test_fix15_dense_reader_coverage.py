"""One image call must retain a brief native reappearance without expected times."""
from copy import deepcopy
import hashlib
import json

import numpy as np
import pytest

import goal_review_sampling as sampling
import fix10a_vision_providers as vision
from test_fix10a_native_goal_focus import job


def fixture(shift=0):
    d=job();s,p=d['strike'],d['shot_track']
    s['media_ms']+=shift;s['active_ball_anchor']['media_ms']+=shift
    p['seed_ms']+=shift;p['contact_binding']['seed_ms']+=shift;p['contact_binding']['contact_ms']+=shift
    for r in p['rows']:
        r['media_ms']+=shift;r['frame_dimensions'].update(width=80,height=60)
    times=sampling.native_gap_times(1200+shift,start_ms=shift,end_ms=4000+shift)
    original=vision._goal_review_times(1000+shift,4000+shift,12,focus_end_ms=1200+shift,anchor_ms=1100+shift)
    images={ms:np.full((60,80,3),ms%255,np.uint8) for ms in set(times+original+[r['media_ms'] for r in p['rows']])}
    scan={'source':'BOUNDED_NATIVE_GOAL_GAP_INSPECTION','status':'SEARCH_ONLY','proof_eligible':False,
          'canonical_events_applied':0,'reason':'NATIVE_GAP_SEARCH_COMPLETE_GOAL_GEOMETRY_STILL_REQUIRED',
          'sample_count':len(times),'native_frame_dimensions':{'width':80,'height':60},
          'rows':[{'media_ms':ms,'time_authority':'ACTUAL_MEDIA_PTS',
                   'source_bgr_pixel_sha256':hashlib.sha256(images[ms].tobytes()).hexdigest()} for ms in times]}
    return d,original,scan,images


def plan(d,original,scan,images,budget=64):
    return sampling.dense_reader_times(original,d['strike'],d['shot_track'],scan,images,
        budget=budget,start_ms=d['window']['start_ms'],end_ms=d['window']['end_ms'])


@pytest.mark.parametrize('shift',[0,30000,150000])
def test_complete_native_loss_is_retained_at_arbitrary_media_times(shift):
    d,original,scan,images=fixture(shift)
    d['window']['start_ms']+=shift;d['window']['end_ms']+=shift
    before=deepcopy((d,original,scan))
    times=plan(d,original,scan,images)
    assert set(r['media_ms'] for r in scan['rows'])<=set(times)
    assert {original[0],original[-1],d['strike']['media_ms'],d['shot_track']['seed_ms']}<=set(times)
    assert times==sorted(set(times)) and len(times)<=64
    # Every 100 ms visibility interval has at least five native images.
    native=[r['media_ms'] for r in scan['rows']]
    for start in range(native[0],native[-1]-100):
        assert len([ms for ms in times if start<=ms<=start+100])>=5
    assert (d,original,scan)==before


@pytest.mark.parametrize('mutation',['budget','changed_pixels','missing_pixels','wrong_dimensions','foreign_source',
    'wrong_hash','requested_time','rejected_contact','predicted_path','duplicate_time','missing_row',
    'unbounded_gap','too_many_frames','proof_claim','event_write'])
def test_incomplete_or_foreign_scan_cannot_expand_reader_input(mutation):
    d,original,scan,images=fixture();budget=64
    if mutation=='budget':budget=12
    elif mutation=='changed_pixels':images[scan['rows'][3]['media_ms']][0,0]=42
    elif mutation=='missing_pixels':images.pop(scan['rows'][3]['media_ms'])
    elif mutation=='wrong_dimensions':scan['native_frame_dimensions']['width']=81
    elif mutation=='foreign_source':scan['source']='USER_ANNOTATION'
    elif mutation=='wrong_hash':scan['rows'][3]['source_bgr_pixel_sha256']='f'*64
    elif mutation=='requested_time':scan['rows'][3]['time_authority']='REQUESTED_MEDIA_TIME'
    elif mutation=='rejected_contact':d['shot_track']['contact_binding']['status']='REJECTED'
    elif mutation=='predicted_path':d['shot_track']['rows'][-1]['state']='PREDICTED_SHORT_GAP'
    elif mutation=='duplicate_time':scan['rows'][3]['media_ms']=scan['rows'][2]['media_ms']
    elif mutation=='missing_row':scan['rows'].pop(3)
    elif mutation=='unbounded_gap':scan['rows'][-1]['media_ms']+=2000
    elif mutation=='too_many_frames':scan['rows']*=2;scan['sample_count']=len(scan['rows'])
    elif mutation=='proof_claim':scan['proof_eligible']=True
    elif mutation=='event_write':scan['canonical_events_applied']=1
    assert plan(d,original,scan,images,budget) is None


@pytest.mark.usefixtures('inline_support_vision')
def test_provider_sends_complete_bounded_loss_to_exactly_one_existing_reader(monkeypatch):
    d,original,scan,images=fixture();captured=[]
    strike={**d['strike'],'_goal_review_ball_path':d['shot_track']}
    monkeypatch.setattr(vision,'_read_frames',lambda _video,times:{ms:(ms,images[ms]) for ms in times})
    def prepared(_self,_strike,_path,native_images,_start,_end):
        native_images.update(images)
        return scan
    monkeypatch.setattr(vision.ShadowVisionProviders,'_scan_native_goal_gap',prepared)
    monkeypatch.setattr(vision.ShadowVisionProviders,'_inspect_goal_gap',lambda *a:None)
    async def reader(_key,_session,paths,times,**kwargs):
        captured.append(list(times))
        return {'frames':[],'ball_evidence':[],'geometry_status':'UNRESOLVED','proof_ready':False}
    monkeypatch.setattr(vision,'read_goal_scene_evidence',reader)
    provider=vision.build_shadow_providers('fixture','dense-reader','unused')
    result=provider.goal_geometry_provider(d['window'],strike)
    assert len(captured)==provider.goal_calls==1
    assert set(r['media_ms'] for r in scan['rows'])<=set(captured[0])
    assert len(captured[0])<=64 and result['status']=='UNRESOLVED'
    provider.goal_geometry_provider(d['window'],strike)
    assert provider.goal_calls==1


def test_large_complete_response_is_not_silently_truncated(tmp_path):
    p=tmp_path/'image';p.write_bytes(b'fixture')
    raw=json.dumps({'reason':'x'*60000})
    audit=vision._model_audit(raw,'fixture',[str(p)],[1000])
    assert audit['raw_response']==raw
    assert hashlib.sha256(audit['raw_response'].encode()).hexdigest()==audit['response_sha256']
