import numpy as np
from match_room_ball_playback import kick_anchor

def fixture():
    obs=[{'frame_id':f'f{i}','media_ms':1000+i*100,'ball':[.2+i*.1,.5]} for i in range(3)]
    event={'canonical_action_type':'SHOT','contact_ms':1000}
    # Camera moved the original contact point left; keep the projected point,
    # not its obsolete coordinates in the first image.
    prev={'kick_reference_frames':['f0','f1'],'arrival_ms':1100,'end_ms':1100,
          'samples':[{'ballTrail':[[.15,.5],[.3,.5]],'kickTrail':[[.15,.5],[.3,.5]]}]}
    return obs,event,prev

def test_contact_anchor_survives_camera_motion():
    o,e,p=fixture()
    a,r=kick_anchor([p],e,o,o[1],o[2],np.array([30.,50.,1.]),np.array([40.,50.,1.]),100,100)
    assert np.allclose(a,[15,50,1]) and r==['f0','f1','f2']

def test_never_bridge_unknown_or_direction_reversal():
    o,e,p=fixture()
    for observations,dest in [(o+[{'frame_id':'unknown','media_ms':1150}],40),(o,20)]:
        assert kick_anchor([p],e,observations,o[1],o[2],np.array([30.,50.,1.]),np.array([dest,50.,1.]),100,100)==(None,[])

def test_missing_chain_cannot_restart_at_later_ball():
    o,e,p=fixture()
    assert kick_anchor([],e,o,o[1],o[2],np.array([30.,50.,1.]),np.array([40.,50.,1.]),100,100)==(None,[])
    a,r=kick_anchor([],e,o,o[0],o[1],np.array([20.,50.,1.]),np.array([30.,50.,1.]),100,100)
    assert np.allclose(a,[20,50,1]) and r==['f0','f1']
