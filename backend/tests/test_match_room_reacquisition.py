from copy import deepcopy
import time
import numpy as np
import match_room_reacquisition as recovery


def fixture():
    mask=np.zeros((120,160),np.uint8);mask[20:101,50:71]=1
    row={'mask':mask,'box':[50,20,21,81],'ground':[.375,100/120],'player_width':.13,'confidence':.9}
    frames=[{'media_ms':1000+i*33,'gray':np.zeros((120,160),np.uint8),'image':np.zeros((120,160,3),np.uint8)} for i in range(10)]
    rows=[[deepcopy(row)] for _ in frames]
    engine=recovery.AdaptiveAssociator(frames,[0,9],[{'x':.375,'y':.5}]*2,lambda i:rows[i],lambda i:rows[i])
    observations=[{'media_ms':frames[i]['media_ms'],'ground':row['ground'],'player_width':.13,'frame_id':f'f{i}'} for i in [0,9]]
    return engine,observations


def test_reacquisition_segments_require_both_source_observations():
    engine,obs=fixture()
    for i in range(1,9):engine.fill(i)
    result={'identity_link_passed_on_this_clip':True,'shared_frames':5,'samples':[{'media_ms':f['media_ms'],'ground':[.375,100/120],'player_width':.13,'detection_index':0} for f in engine.frames]}
    assert recovery.segments_for_review(engine,result,obs)[0]['identity_reference_frames']==['f0','f9']
    assert recovery.segments_for_review(engine,result,obs[:1])==[]
    assert recovery.segments_for_review(engine,result,[obs[0],{**obs[1],'ground':[.9,.9]}])==[]
    assert recovery.segments_for_review(engine,{**result,'identity_link_passed_on_this_clip':False},obs)==[]


def test_deadline_prevents_more_inference_and_locked_rows_cannot_be_replaced():
    engine,_=fixture();engine.fill(2);row=engine.rows[2];engine.locked.add(2);engine.fill(2,True);assert engine.rows[2] is row
    engine.deadline=time.monotonic()-1
    try:engine.fill(3)
    except TimeoutError:pass
    else:raise AssertionError('Expired inference was allowed')
