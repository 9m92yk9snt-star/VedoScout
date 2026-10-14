"""Search alternatives are retained, but never become contact authority.

Only synthetic geometry is used. No original-video time, action or jersey label
enters these regression tests.
"""
from copy import deepcopy
from pathlib import Path
import sys
import pytest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ball_trajectory as bt
import ball_contact_engine as contact


def ball(x, y=.5, confidence=.8, *, width=1000, height=1000):
    return {"box": {"x": x, "y": y, "w": 12/width, "h": 12/height},
            "confidence": confidence}


def native_frames(width=1000, height=1000, camera_offsets=(0.,0.,0.,0.)):
    frames=[]
    for i,offset in enumerate(camera_offsets):
        ms=1000+40*i
        frames.append({"media_ms":ms,"scene_id":"s","used_fallback":False,
            "time_authority":"ACTUAL_MEDIA_PTS",
            "frame_dimensions":{"width":width,"height":height,"source":"DECODED_NATIVE_PIXELS"},
            "camera_state":"AFFINE_VERIFIED" if i else "SEED_OR_FIRST_FRAME",
            "camera_motion":{"source":"NATIVE_BACKGROUND_AFFINE","units":"DECODED_PIXELS",
                "from_media_ms":ms-40,"to_media_ms":ms,
                "matrix":[[1.,0.,(offset-camera_offsets[i-1])*width],[0.,1.,0.]]} if i else None,
            "ball_candidates":[ball(.10+offset,width=width,height=height)],"players":[]})
    return frames


@pytest.mark.parametrize("native",[False,True])
@pytest.mark.parametrize("reverse",[False,True])
def test_persistent_reserve_cannot_erase_a_new_low_confidence_search_path(native,reverse):
    fs=native_frames()
    if not native:
        for f in fs:f.pop("camera_motion")
    for i,f in enumerate(fs[1:],1):
        f['ball_candidates'].append(ball(.75+.01*i,confidence=.08))
        if reverse:f['ball_candidates'].reverse()
    before=deepcopy(fs)
    rows=bt.reconstruct_ball_trajectory(fs)
    alternate=[c for c in rows[-1]['search_candidates'] if c['box']['x']>.7]
    assert len(alternate)==1
    assert alternate[0]['search_observations']==3
    assert alternate[0]['search_first_ms']==1040
    assert alternate[0]['proof_eligible'] is False
    assert alternate[0]['state']=='SEARCH_ONLY'
    assert all(r['state']=='MEASURED' and r['box']['x']==pytest.approx(.10) for r in rows)
    assert fs==before


def test_one_frame_high_confidence_object_cannot_replace_or_seed_release_authority():
    fs=native_frames()
    fs[1]['ball_candidates'].append(ball(.85,confidence=.99))
    rows=bt.reconstruct_ball_trajectory(fs)
    extra=next(c for c in rows[1]['search_candidates'] if c['box']['x']>.8)
    assert extra['search_observations']==1
    assert rows[1]['box']['x']==pytest.approx(.10)
    assert bt.reconstruct_ball_trajectory_from_release_anchor(fs,extra,'s')==[]
    assert contact.resolve_contacts(contact.detect_contact_candidates(fs,rows))['accepted']==[]


def test_missing_search_point_is_not_exported_but_may_reassociate_within_the_bound():
    fs=native_frames()
    fs[1]['ball_candidates'].append(ball(.75,confidence=.08))
    fs[3]['ball_candidates'].append(ball(.77,confidence=.08))
    rows=bt.reconstruct_ball_trajectory(fs)
    assert not any(c['box']['x']>.7 for c in rows[2]['search_candidates'])
    final=next(c for c in rows[3]['search_candidates'] if c['box']['x']>.7)
    assert final['search_observations']==2
    assert final['search_first_ms']==1040
    assert final['proof_eligible'] is False


def test_search_gap_beyond_bound_starts_a_new_object_not_false_confirmation():
    fs=native_frames()
    fs[1]['ball_candidates'].append(ball(.75,confidence=.08))
    later=deepcopy(fs[-1]);later['media_ms']=1400
    later['camera_motion']=None
    later['ball_candidates']=[ball(.77,confidence=.08)]
    rows=bt.reconstruct_ball_trajectory(fs+[later])
    extra=next(c for c in rows[-1]['search_candidates'] if c['box']['x']>.7)
    assert extra['search_observations']==1
    assert extra['search_first_ms']==1400


def test_cut_resets_authoritative_and_search_tracks():
    fs=native_frames()
    for f in fs[1:]:f['ball_candidates'].append(ball(.75,confidence=.08))
    fs[-1]['cut_barrier']=True
    rows=bt.reconstruct_ball_trajectory(fs)
    assert all(c['search_observations']==1 and c['search_first_ms']==1120
               for c in rows[-1]['search_candidates'])


def test_search_memory_and_export_are_bounded_with_many_objects():
    fs=native_frames(camera_offsets=(0.,)*30)
    for i,f in enumerate(fs):
        f['ball_candidates'] += [ball(.3+j*.02,confidence=.2+j*.002) for j in range(25)]
    rows=bt.reconstruct_ball_trajectory(fs)
    assert all(len(r['search_candidates'])<=bt.MAX_SEARCH_HYPOTHESES for r in rows)
    assert all(not c['proof_eligible'] for r in rows for c in r['search_candidates'])
    assert all(len(r['candidates'])<=bt.MAX_HYPOTHESES for r in rows)


@pytest.mark.parametrize("width,height",[(1000,1000),(1920,1080),(1080,1920)])
def test_accelerating_camera_preserves_the_same_measured_object(width,height):
    fs=native_frames(width,height,camera_offsets=(0.,.03,.15,.40))
    rows=bt.reconstruct_ball_trajectory(fs)
    assert all(r['state']=='MEASURED' for r in rows)
    assert all(r['box']['x']==pytest.approx(fs[i]['ball_candidates'][0]['box']['x']) for i,r in enumerate(rows))
    assert all(rows[i]['candidates'][0]['prior_hypothesis'] is not None for i in range(1,len(rows)))


@pytest.mark.parametrize("width,height",[(1000,1000),(1920,1080),(1080,1920)])
def test_physical_speed_envelope_uses_native_pixels_not_a_normalized_square(width,height):
    fs=native_frames(width,height)
    # Exactly 3 frame-heights/s in all aspect ratios, inside unchanged 4H/s.
    for i,f in enumerate(fs):
        f['ball_candidates']=[ball(.10+i*.04*3*height/width,width=width,height=height)]
    rows=bt.reconstruct_ball_trajectory(fs)
    assert all(r['state']=='MEASURED' for r in rows)
    assert all(rows[i]['candidates'][0]['prior_hypothesis'] is not None for i in range(1,len(rows)))


def test_native_short_gap_prediction_includes_measured_camera_movement():
    fs=native_frames(camera_offsets=(0.,.02,.10,.15))
    fs[2]['ball_candidates']=[]
    rows=bt.reconstruct_ball_trajectory(fs)
    assert rows[2]['state']=='PREDICTED_SHORT_GAP'
    assert rows[2]['box']['x']==pytest.approx(.20)
    assert rows[2]['proof_eligible'] is False
    assert rows[3]['state']=='MEASURED'


@pytest.mark.parametrize('change',[{'camera_motion':None},{'camera_state':'UNRESOLVED'},
    {'used_fallback':True},{'time_authority':'FRAME_INDEX_FPS_FALLBACK'}])
def test_invalid_native_camera_chain_cannot_silently_use_screen_coordinates(change):
    fs=native_frames(camera_offsets=(0.,.03,.15,.40))
    fs[1].update(change)
    rows=bt.reconstruct_ball_trajectory(fs)
    assert rows[1]['state']=='MISSING'
    assert rows[1]['proof_eligible'] is False
    assert rows[1]['provenance']=='NATIVE_CAMERA_ASSOCIATION_UNAVAILABLE'


def test_legacy_screen_coordinate_contract_remains_unchanged():
    fs=native_frames(camera_offsets=(0.,.03,.15,.40))
    for f in fs:f.pop('camera_motion')
    rows=bt.reconstruct_ball_trajectory(fs)
    assert rows[-1]['state']=='PREDICTED_SHORT_GAP'


def test_camera_rotation_and_zoom_move_position_size_and_velocity_consistently():
    fs=native_frames()
    b=fs[0]['ball_candidates'][0]['box']
    center=np.array([(b['x']+b['w']/2)*1000,(b['y']+b['h']/2)*1000,1.])
    theta=np.radians(2.)
    linear=1.03*np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])
    matrix=np.column_stack((linear,[40.,-10.]))
    hom=np.vstack((matrix,[0.,0.,1.]))
    corners=np.array([[b['x']*1000,b['y']*1000,1.],[(b['x']+b['w'])*1000,b['y']*1000,1.],
        [b['x']*1000,(b['y']+b['h'])*1000,1.],[(b['x']+b['w'])*1000,(b['y']+b['h'])*1000,1.]])
    for f in fs[1:]:
        center=hom@center;corners=(hom@corners.T).T
        w=(corners[:,0].max()-corners[:,0].min())/1000
        h=(corners[:,1].max()-corners[:,1].min())/1000
        f['camera_motion']['matrix']=matrix.tolist()
        f['ball_candidates']=[{'box':{'x':center[0]/1000-w/2,'y':center[1]/1000-h/2,'w':w,'h':h},'confidence':.8}]
    rows=bt.reconstruct_ball_trajectory(fs)
    assert all(r['state']=='MEASURED' for r in rows)


@pytest.mark.parametrize('reverse',[False,True])
def test_search_cannot_choose_between_equal_geometric_objects_by_confidence(reverse):
    fs=native_frames()
    fs[1]['ball_candidates'].append(ball(.75,confidence=.10))
    choices=[ball(.745,confidence=.10),ball(.755,confidence=.99)]
    fs[2]['ball_candidates']+=choices[::-1] if reverse else choices
    rows=bt.reconstruct_ball_trajectory(fs)
    alternatives=[c for c in rows[2]['search_candidates'] if c['box']['x']>.7]
    assert len(alternatives)==2
    assert all(c['search_observations']==1 and c['search_motion_support'] is None for c in alternatives)
    assert len({c['search_track_id'] for c in alternatives})==2


def test_one_proposal_between_two_previous_search_objects_is_not_an_identity_link():
    fs=native_frames()
    fs[1]['ball_candidates']+=[ball(.74),ball(.76)]
    fs[2]['ball_candidates'].append(ball(.75))
    rows=bt.reconstruct_ball_trajectory(fs)
    middle=next(c for c in rows[2]['search_candidates'] if c['box']['x']>.7)
    assert middle['search_observations']==1
    assert middle['search_first_ms']==1080


def test_search_track_identity_survives_candidate_order_changes():
    fs=native_frames()
    for i,f in enumerate(fs[1:]):f['ball_candidates'].append(ball(.75+i*.01,confidence=.08))
    rows=bt.reconstruct_ball_trajectory(fs)
    altered=deepcopy(fs)
    for f in altered:f['ball_candidates'].reverse()
    again=bt.reconstruct_ball_trajectory(altered)
    for a,b in zip(rows,again):
        assert {c['search_track_id']:c['search_observations'] for c in a['search_candidates']}=={
            c['search_track_id']:c['search_observations'] for c in b['search_candidates']}


@pytest.mark.parametrize('change',[{'proof_eligible':False},{'used_fallback':True},
    {'state':'SEARCH_ONLY'},{'state':'PREDICTED_SHORT_GAP'},
    {'time_authority':'FRAME_INDEX_FPS_FALLBACK'},{'confidence':float('nan')},
    {'confidence':float('inf')},{'confidence':True},{'confidence':'0.99'}])
def test_explicit_nonproof_or_invalid_proposal_cannot_be_recycled_into_authority(change):
    fs=native_frames()
    for f in fs:f['ball_candidates'][0].update(change)
    rows=bt.reconstruct_ball_trajectory(fs)
    assert all(r['state']=='MISSING' and not r['proof_eligible'] for r in rows)
    assert all(r['search_candidates']==[] for r in rows)
