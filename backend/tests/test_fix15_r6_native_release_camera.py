"""Camera-aware contact-to-seed identity; no original-video labels or times."""
from copy import deepcopy
from pathlib import Path
import sys
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ball_trajectory as bt


def frames(width=1000,height=1000,shifts=(0.,0.,0.,0.)):
    result=[]
    for i,shift in enumerate(shifts):
        ms=1000+40*i
        result.append({'media_ms':ms,'scene_id':'s','used_fallback':False,
            'time_authority':'ACTUAL_MEDIA_PTS','players':[],
            'camera_state':'AFFINE_VERIFIED' if i else 'SEED_OR_FIRST_FRAME',
            'frame_dimensions':{'width':width,'height':height,'source':'DECODED_NATIVE_PIXELS'},
            'camera_motion':{'source':'NATIVE_BACKGROUND_AFFINE','units':'DECODED_PIXELS',
                'from_media_ms':ms-40,'to_media_ms':ms,
                'matrix':[[1.,0.,(shift-shifts[i-1])*width],[0.,1.,0.]]} if i else None,
            'ball_candidates':[candidate(.10+shift,width,height)]})
    return result


def candidate(x,width=1000,height=1000,confidence=.10):
    return {'box':{'x':x,'y':.5,'w':12/width,'h':12/height},'confidence':confidence}


def seed(fs):
    return {'media_ms':fs[0]['media_ms'],'state':'MEASURED','proof_eligible':True,
            'time_authority':'ACTUAL_MEDIA_PTS','used_fallback':False,
            **deepcopy(fs[0]['ball_candidates'][0])}


@pytest.mark.parametrize('width,height',[(1000,1000),(1920,1080),(1080,1920)])
def test_camera_acceleration_does_not_break_an_existing_ball_identity(width,height):
    fs=frames(width,height,shifts=(0.,.03,.15,.40))
    before=deepcopy(fs)
    rows=bt.reconstruct_ball_trajectory_from_release_anchor(fs,seed(fs),'s')
    assert [r['media_ms'] for r in rows]==[1000,1040,1080,1120]
    assert all(r['box']==fs[i]['ball_candidates'][0]['box'] for i,r in enumerate(rows))
    assert fs==before


@pytest.mark.parametrize('width,height',[(1000,1000),(1920,1080),(1080,1920)])
def test_first_fast_native_measurement_uses_unchanged_physical_speed_bound(width,height):
    fs=frames(width,height)
    for i,f in enumerate(fs):f['ball_candidates']=[candidate(.10+.12*i*height/width,width,height)]
    rows=bt.reconstruct_ball_trajectory_from_release_anchor(fs,seed(fs),'s')
    assert len(rows)==4
    assert rows[-1]['box']==fs[-1]['ball_candidates'][0]['box']


@pytest.mark.parametrize('width,height',[(1000,1000),(1920,1080),(1080,1920)])
@pytest.mark.parametrize('reverse',[False,True])
def test_native_first_pair_compares_motion_support_not_twelve_percent_of_the_image(width,height,reverse):
    fs=frames(width,height)
    for i,f in enumerate(fs[1:],1):
        f['ball_candidates']=[candidate(.10+.01*i*height/width,width,height,.08),
                              candidate(.10+.10*height/width,width,height,.99)]
        if reverse:f['ball_candidates'].reverse()
    rows=bt.reconstruct_ball_trajectory_from_release_anchor(fs,seed(fs),'s')
    assert len(rows)==4
    assert all(r['box']['x']==pytest.approx(.10+.01*i*height/width) for i,r in enumerate(rows))


@pytest.mark.parametrize('change',[{'camera_motion':None},{'camera_state':'UNRESOLVED'},
    {'used_fallback':True},{'time_authority':'FRAME_INDEX_FPS_FALLBACK'},
    {'cut_barrier':True},{'scene_id':'other'}])
def test_unresolved_native_camera_or_time_never_reconnects_a_release_identity(change):
    fs=frames(shifts=(0.,.03,.15,.40))
    fs[1].update(change)
    rows=bt.reconstruct_ball_trajectory_from_release_anchor(fs,seed(fs),'s')
    assert [r['media_ms'] for r in rows]==[1000]


def test_native_first_observation_between_equal_objects_stays_ambiguous():
    fs=frames()
    fs[1]['ball_candidates']=[candidate(.109,confidence=.08),candidate(.111,confidence=.99)]
    fs[2]['ball_candidates']=[]
    rows=bt.reconstruct_ball_trajectory_from_release_anchor(fs,seed(fs),'s')
    assert [r['media_ms'] for r in rows]==[1000]


def test_missing_camera_measurement_without_a_ball_still_breaks_the_later_chain():
    fs=frames(shifts=(0.,.03,.15,.40))
    fs[1]['ball_candidates']=[]
    fs[1]['camera_motion']=None
    rows=bt.reconstruct_ball_trajectory_from_release_anchor(fs,seed(fs),'s')
    assert [r['media_ms'] for r in rows]==[1000]


def test_native_segment_can_span_one_missing_ball_frame_with_a_measured_camera_chain():
    fs=frames(shifts=(0.,.03,.15,.40))
    fs[1]['ball_candidates']=[]
    rows=bt.reconstruct_ball_trajectory_from_release_anchor(fs,seed(fs),'s')
    assert [r['media_ms'] for r in rows]==[1000,1080,1120]
    assert all(r['state']=='MEASURED' for r in rows)


def test_camera_zoom_rotation_preserve_ball_position_and_established_world_motion():
    fs=frames()
    theta=np.radians(2.)
    linear=1.03*np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])
    step=np.vstack((np.column_stack((linear,[20.,-5.])),[0.,0.,1.]))
    total=np.eye(3)
    for i,f in enumerate(fs[1:],1):
        total=step@total
        center=total@np.array([106.+20*i,506.,1.])
        corners=(total@np.array([[100+20*i,500.,1.],[112+20*i,500.,1.],
                                [100+20*i,512.,1.],[112+20*i,512.,1.]]).T).T
        w=(corners[:,0].max()-corners[:,0].min())/1000
        h=(corners[:,1].max()-corners[:,1].min())/1000
        f['ball_candidates']=[{'box':{'x':center[0]/1000-w/2,'y':center[1]/1000-h/2,'w':w,'h':h},'confidence':.10}]
        f['camera_motion']['matrix']=step[:2].tolist()
    rows=bt.reconstruct_ball_trajectory_from_release_anchor(fs,seed(fs),'s')
    assert len(rows)==4
    assert all(r['box']==fs[i]['ball_candidates'][0]['box'] for i,r in enumerate(rows))


def test_contact_to_exact_seed_binding_uses_the_native_camera_corrected_identity():
    fs=frames(shifts=(0.,.03,.15,.40))
    contact=seed(fs)
    last={**contact,'media_ms':fs[2]['media_ms'],'box':fs[2]['ball_candidates'][0]['box']}
    result=bt.release_anchor_contact_binding(fs,contact,last,'s')
    assert result['status']=='VERIFIED'
    assert result['measured_times_ms']==[1000,1040,1080]


def test_no_native_path_can_certify_an_explicitly_rejected_seed():
    fs=frames(shifts=(0.,.03,.15,.40))
    rejected=seed(fs);rejected['proof_eligible']=False
    assert bt.reconstruct_ball_trajectory_from_release_anchor(fs,rejected,'s')==[]


def test_legacy_first_pair_contract_is_not_changed_by_the_native_path():
    fs=frames()
    for i,f in enumerate(fs):
        f.pop('camera_motion')
        if i:f['ball_candidates']=[candidate(.10+.01*i),candidate(.20,confidence=.99)]
    assert len(bt.reconstruct_ball_trajectory_from_release_anchor(fs,seed(fs),'s'))==1
