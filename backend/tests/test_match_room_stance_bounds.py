import numpy as np
from match_room_position_contours import stance_bounds

def row(wide):
    mask=np.zeros((100,100),np.uint8);mask[10:60,45:55]=1
    mask[60:90,25:35 if wide else 50]=1 if wide else 0
    if wide:mask[60:90,65:75]=1
    else:mask[60:90,43:57]=1
    return {'mask':mask,'ground':[.5,.9],'player_width':.3}

def test_spread_legs_have_wider_display_extent_without_changing_identity_width():
    narrow,wide=row(False),row(True)
    a,b=stance_bounds(narrow,100)['stance_bounds'],stance_bounds(wide,100)['stance_bounds']
    assert b[1]-b[0]>a[1]-a[0]*2
    assert wide['player_width']==narrow['player_width']==.3

def test_unknown_ground_cannot_supply_stance_extent():
    r=row(True);r['ground']=None
    assert stance_bounds(r,100)=={}

def test_unreasonably_wide_lower_mask_is_rejected():
    r=row(True);r['player_width']=.01
    assert stance_bounds(r,100)=={}
