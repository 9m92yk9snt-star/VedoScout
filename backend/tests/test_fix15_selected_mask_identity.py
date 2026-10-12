"""A point on a foreground rectangle cannot override selected visible pixels."""
from copy import deepcopy
import numpy as np
import pytest
import player_selection as ps
import unified_identity_authority as uia
import dense_track_refinement as dense
import football_scene_graph as graph

BOX = {"x": .2, "y": .2, "w": .4, "h": .6}
POINT = {"x": .42, "y": .5}

def mask():
    a=np.zeros((192,96),np.uint8);a[30:160,45:90]=1
    runs=[];last=0;count=0
    for v in a.ravel():
        if v==last:count+=1
        else:runs.append(count);last=int(v);count=1
    runs.append(count)
    return {"width":96,"height":192,"runs":runs,"method":"user_fixture"}

def authority(with_mask=True):
    a={"t":1.,"box":deepcopy(BOX),"target_point":deepcopy(POINT)}
    if with_mask:a['visible_mask']=mask()
    return uia.build_unified_identity_authority(anchors=[a])

def body(name, box):
    return {"local_track_id":name,"association_state":"VERIFIED_LOCAL","box":box}

BYSTANDER={"x":.15,"y":.1,"w":.30,"h":.75}
OWNER={"x":.38,"y":.25,"w":.22,"h":.50}

def test_selected_mask_is_preserved_only_on_user_tap_authority():
    a=authority();before=deepcopy(a)
    row=next(r for r in a['target_points'] if r['primary_source']=='USER_TAP')
    assert row['visible_mask']==mask()
    for ms in [900,1100,1500]:
        selected,_=uia.resolve_target_at(a,ms,proof_required=False,max_interp_ms=250)
        assert selected is None or selected.get('visible_mask') is None
    assert a==before

@pytest.mark.parametrize('consumer',[dense._resolve_dense_target,graph._target_candidates])
def test_unique_point_bystander_is_not_proof_when_it_misses_selected_foreground(consumer):
    players=[body('foreground_bystander',BYSTANDER)]
    before=deepcopy(players)
    r=consumer(authority(),1000,players)
    assert r['proof_eligible'] is False
    assert r['local_track_id'] is None
    assert r['reason']=='TAP_POINT_BODY_MASK_CONFLICT'
    assert players==before

@pytest.mark.parametrize('consumer',[dense._resolve_dense_target,graph._target_candidates])
@pytest.mark.parametrize('reverse',[False,True])
def test_mask_constraint_removes_foreground_bystander_without_moving_point(consumer,reverse):
    players=[body('bystander',BYSTANDER),body('selected',OWNER)]
    if reverse:players.reverse()
    r=consumer(authority(),1000,players)
    assert r['proof_eligible'] is True and r['local_track_id']=='selected'

@pytest.mark.parametrize('consumer',[dense._resolve_dense_target,graph._target_candidates])
def test_mask_is_not_a_confidence_tiebreak_between_two_compatible_bodies(consumer):
    r=consumer(authority(),1000,[body('a',OWNER),body('b',OWNER)])
    assert r['proof_eligible'] is False and r['reason']=='TAP_POINT_BODY_AMBIGUOUS'

@pytest.mark.parametrize('consumer',[dense._resolve_dense_target,graph._target_candidates])
def test_point_only_legacy_selection_stays_unchanged(consumer):
    r=consumer(authority(False),1000,[body('legacy',BYSTANDER)])
    assert r['proof_eligible'] is True and r['local_track_id']=='legacy'

@pytest.mark.parametrize('scale',[1.,100.,1920.])
def test_coverage_is_foreground_only_and_coordinate_unit_invariant(scale):
    selected=tuple(BOX[k]*scale for k in ('x','y','w','h'))
    owner=tuple(OWNER[k]*scale for k in ('x','y','w','h'))
    other=tuple(BYSTANDER[k]*scale for k in ('x','y','w','h'))
    point=(POINT['x']*scale,POINT['y']*scale)
    assert ps.mask_foreground_coverage(owner,selected,mask())==1.
    assert ps.mask_foreground_coverage(other,selected,mask())<.90
    assert ps.body_indices_at_point([other,owner],point,selection_box=selected,visible_mask=mask())==[1]

@pytest.mark.parametrize('invalid',[None,{}, {'width':96,'height':192,'runs':[18432]},
    {'width':96,'height':192,'runs':[True,18431]}, {'width':96,'height':192,'runs':[0,18433]},
    {'width':96,'height':192,'runs':[18412,19,1]}])
def test_invalid_mask_never_supplies_coverage(invalid):
    assert ps.mask_foreground_coverage(OWNER,BOX,invalid) is None

@pytest.mark.parametrize('invalid',[None,{},[0,0,0,1],[0,0,1,float('nan')],[0,0,True,1]])
def test_invalid_selection_geometry_never_supplies_coverage(invalid):
    assert ps.mask_foreground_coverage(OWNER,invalid,mask()) is None

def test_excluded_body_remains_excluded_even_when_mask_fits():
    box=tuple(OWNER[k] for k in ('x','y','w','h'))
    assert ps.body_indices_at_point([box],(.42,.5),[(.43,.5)],selection_box=BOX,visible_mask=mask())==[]

def test_mask_foreground_outside_body_is_not_replaced_by_the_broad_box_background():
    assert ps.mask_foreground_coverage(BYSTANDER,BOX,mask())==pytest.approx(1/3)

@pytest.mark.parametrize('include_owner',[False,True])
def test_coarse_tap_pinning_uses_mask_in_pixel_coordinates(include_owner):
    import player_identity_timeline as timeline
    def pixels(b):return (b['x']*480,b['y']*270,b['w']*480,b['h']*270)
    detections=[{'box':pixels(BYSTANDER),'emb':{'ident':'foreground'}}]
    if include_owner:detections.append({'box':pixels(OWNER),'emb':{'ident':'selected'}})
    observations=[{'media_ms':ms,'width':480,'height':270,'cam_dx':0.,'cam_dy':0.,'cut':False,
        'time_authority':'ACTUAL_MEDIA_PTS','used_fallback':False,'detections':deepcopy(detections)} for ms in range(0,2200,200)]
    tap={'media_ms':1000,'decoded_media_ms':1000,'box':pixels(BOX),
         'target_point':(POINT['x']*480,POINT['y']*270),'visible_mask':mask()}
    result=timeline.assemble_timeline(observations,[tap],lambda _:0.)
    assert result['recovery']['tap_point_pins']==int(include_owner)
    assert result['recovery']['tap_point_unresolved']==int(not include_owner)
