import json
from copy import deepcopy
from match_room import samples, presentation, from_receipts

FRAMES = {'s1': {'media_ms': 1000}, 's2': {'media_ms': 1250},
          'cropped': {'media_ms': 1400, 'source_crop_box': [0, 20, 720, 800]}}
ROW = {'frame': 's1', 'actor': 'p1', 'plane': 'FULL_FRAME', 'confidence': 'HIGH',
       'visible': True, 'ground': [.4, .8], 'player_width': .06,
       'ball': [.5, .8], 'active_ball_verified': True}


def parse(rows):
    return samples(rows, actor='p1', frames=FRAMES, start=900, end=1500)


def test_only_observed_active_ball_and_visible_ground_survive():
    assert parse([ROW])[0]['ground'] == [.4, .8]
    assert 'ball' not in parse([{**ROW, 'active_ball_verified': False}])[0]
    assert parse([{**ROW, 'ground': None, 'active_ball_verified': False}]) == []


def test_reject_other_actor_crop_unknown_frame_occlusion_and_invalid_points():
    for change in [{'actor':'p2'}, {'frame':'cropped'}, {'frame':'unknown'},
                   {'visible':False}, {'confidence':'LOW'}, {'plane':'CROP'}]:
        assert parse([{**ROW, **change}]) == []
    assert parse([{**ROW,'ground':[float('nan'),.5],'ball':[True,.5]}]) == []
    assert parse([{**ROW,'ground':[1.2,.5],'player_width':True,'ball':[-.1,.5]}]) == []


def test_scope_and_frame_allowlist():
    assert samples([ROW], actor='p1', frames=FRAMES, start=1100, end=1500) == []
    assert samples([ROW], actor='p1', frames=FRAMES, start=0, end=2000, allowed={'s2'}) == []


def test_graphics_rebuilt_from_receipt_not_intermediate_event():
    event = {'actor_scope':'packet:0','actor':'p1','source_action_keys':['packet:0:a1'],
             'start_ms':900,'end_ms':1500,'visual_samples':[{'ground':[0,0]}]}
    receipt={'packet_id':'packet','raw_response':json.dumps({'plays':[{'actions':[
        {'action_id':'a1','actor':'p1','visual_samples':[ROW]}]}]})}
    found=from_receipts(event, {'frames':[{'frame_id':k,**v} for k,v in FRAMES.items()]}, [receipt])
    assert found[0]['ground']==[.4,.8]
    assert from_receipts({**event,'actor_scope':'other:0'}, {'frames':[]}, [receipt]) == []


def test_presentation_preserves_exact_source_times_and_never_invents_stops():
    event={'event_id':'e1','source_video_sha256':'sha','canonical_action_type':'SHOT',
           'canonical_outcome':'GOAL','contact_ms':1234,'details':['Shoots under pressure.'],
           'proof':{'proof_start_ms':900,'proof_end_ms':2500,'frame_ms':1250,'outcome_ms':2300}}
    before=deepcopy(event); room=presentation(event)
    assert [s['media_ms'] for s in room['stops']]==[1234,2300]
    assert room['samples']==[] and event==before
    event['proof']['outcome_ms']=None
    assert len(presentation(event)['stops'])==1
