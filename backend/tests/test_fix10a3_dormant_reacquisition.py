import sys
from pathlib import Path
BACKEND=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND))
import ball_trajectory as bt

def ball(x,y=.4,conf=.8,w=.02,h=.02):return {'box':{'x':x,'y':y,'w':w,'h':h},'confidence':conf}
def frame(ms,balls=None,cut=False):return {'media_ms':ms,'ball_candidates':list(balls or []),'cut_barrier':cut,'used_fallback':False,'time_authority':'ACTUAL_MEDIA_PTS'}

def test_existing_continuity():
 o=bt.reconstruct_ball_trajectory([frame(1000,[ball(.1)]),frame(1040,[ball(.8,conf=.98),ball(.12,conf=.52)])]);assert o[1]['state']=='MEASURED' and abs(o[1]['box']['x']-.12)<1e-9

def test_short_gap_stays_nonproof_prediction():
 o=bt.reconstruct_ball_trajectory([frame(1000,[ball(.1)]),frame(1040,[ball(.14)]),frame(1120,[])]);assert o[2]['state']=='PREDICTED_SHORT_GAP' and o[2]['proof_eligible'] is False

def test_dormant_gap_exposes_no_synthetic_ball():
 o=bt.reconstruct_ball_trajectory([frame(1000,[ball(.1)]),frame(1040,[ball(.14)]),frame(1240,[])]);assert o[2]['state']=='MISSING' and o[2]['box'] is None and o[2]['proof_eligible'] is False and o[2]['provenance']=='DORMANT_REACQUIRE_WAIT'

def test_distant_one_frame_noise_cannot_hijack_dormant_trajectory():
 o=bt.reconstruct_ball_trajectory([frame(1000,[ball(.10)]),frame(1040,[ball(.14)]),frame(1240,[ball(.80,conf=.99)]),frame(1280,[ball(.38,conf=.45)])]);assert o[2]['state']=='MISSING' and o[2]['box'] is None and o[2]['provenance']=='DORMANT_REACQUIRE_DISCONTINUITY_REJECTED';assert o[3]['state']=='MEASURED' and abs(o[3]['box']['x']-.38)<1e-9

def test_false_and_correct_candidate_same_reacquisition_frame_prefers_linked_path():
 o=bt.reconstruct_ball_trajectory([frame(1000,[ball(.10)]),frame(1040,[ball(.14)]),frame(1240,[]),frame(1280,[ball(.82,conf=.99),ball(.38,conf=.34)])]);assert o[3]['state']=='MEASURED' and abs(o[3]['box']['x']-.38)<1e-9 and o[3]['candidates'][0]['prior_hypothesis'] is not None

def test_after_dormant_expiry_unrelated_candidate_may_bootstrap_new_track():
 o=bt.reconstruct_ball_trajectory([frame(1000,[ball(.10)]),frame(1040,[ball(.14)]),frame(1600,[ball(.82,conf=.9)])]);assert o[2]['state']=='MEASURED' and abs(o[2]['box']['x']-.82)<1e-9

def test_scene_cut_is_hard_barrier_even_inside_dormant_window():
 o=bt.reconstruct_ball_trajectory([frame(1000,[ball(.10)]),frame(1040,[ball(.14)]),frame(1240,[ball(.82,conf=.9)],cut=True)]);assert o[2]['state']=='MEASURED' and o[2]['cut_barrier'] is True and abs(o[2]['box']['x']-.82)<1e-9

def player_at_foot(x, y=.40, h=.20, w=.08):
    # box whose foot centre is approximately (x,y)
    return {'local_track_id':'p001','association_state':'VERIFIED_LOCAL','box':{'x':x-w/2,'y':y-h,'w':w,'h':h}}

def frame_players(ms, balls=None, players=None, cut=False):
    row=frame(ms,balls,cut=cut); row['players']=list(players or []); return row

def test_dormant_player_supported_direction_and_scale_change_can_reacquire():
    # Last measured trajectory points right around x=.14. After a football touch,
    # a larger motion-blurred proposal near a verified player's foot may change
    # direction/scale without becoming touch authority.
    candidate=ball(.50, y=.40, conf=.08, w=.05, h=.03)
    out=bt.reconstruct_ball_trajectory([
        frame_players(1000,[ball(.10)]),
        frame_players(1040,[ball(.14)]),
        frame_players(1240,[candidate],[player_at_foot(.525,.43)]),
    ])
    assert out[2]['state']=='MEASURED'
    assert abs(out[2]['box']['x']-.50)<1e-9
    assert out[2]['candidates'][0]['player_foot_support_h'] <= bt.DORMANT_PLAYER_SUPPORT_H
    assert 'touch' not in out[2] and 'scorer' not in out[2]

def test_dormant_candidate_outside_player_support_still_cannot_hijack():
    # A player exists, but not close enough to support a discontinuous reboot.
    out=bt.reconstruct_ball_trajectory([
        frame_players(1000,[ball(.10)]),
        frame_players(1040,[ball(.14)]),
        frame_players(1240,[ball(.80,conf=.99)],[player_at_foot(.70,.40)]),
        frame_players(1280,[ball(.38,conf=.40)],[player_at_foot(.40,.42)]),
    ])
    assert out[2]['state']=='MISSING'
    assert out[3]['state']=='MEASURED'
    assert abs(out[3]['box']['x']-.38)<1e-9
