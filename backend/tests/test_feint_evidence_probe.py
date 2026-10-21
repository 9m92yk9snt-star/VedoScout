from copy import deepcopy
import pytest
from scripts.probe_feint_evidence import candidates,validate_reviews

def row():
    return dict(start_s=1,move_s=1.5,end_s=2,type='BODY_FEINT',identity_evidence='selection r1',
                before='approaches',movement='shifts body',opponent_response='steps',after='carries',
                outcome='PROGRESSES',uncertainty='')

@pytest.mark.parametrize('time',[float('nan'),float('inf'),True,-1,4])
def test_invalid_discovery_time(time):
    r=row();r['move_s']=time
    with pytest.raises(ValueError):candidates({'observations':[r]},3)

def test_no_move_is_valid_and_does_not_force_a_count():
    assert candidates({'observations':[]},3)==[]

def test_failed_move_retained_and_no_expected_timestamp_filter():
    r=row();r.update(start_s=110,move_s=110.5,end_s=111,outcome='LOSES')
    assert candidates({'observations':[r]},120)[0]['outcome']=='LOSES'

def fixture():
    selected=candidates({'observations':[row()]},3)
    frames=[dict(id=f'f{i}',source_ms=i*100,candidate_id='c1') for i in range(3)]
    review=dict(candidate_id='c1',decision='SUPPORTED',type='BODY_FEINT',identity_frames=['f0'],
                before_frame='f0',movement_frames=['f1'],after_frame='f2',visible_movement='shift',
                opponent_response='step',outcome='PROGRESSES',reason='visible sequence',uncertainty='')
    return selected,frames,review

def test_supported_requires_supplied_chronological_evidence():
    selected,frames,r=fixture()
    assert validate_reviews({'reviews':[r]},selected,frames)==[r]
    for change in [dict(after_frame='invented'),dict(identity_frames=[]),dict(movement_frames=[]),
                   dict(after_frame='f0'),dict(candidate_id='other'),dict(type='UNKNOWN'),
                   dict(outcome='GOAL')]:
        wrong=deepcopy(r);wrong.update(change)
        with pytest.raises(ValueError):validate_reviews({'reviews':[wrong]},selected,frames)

def test_rejection_not_promoted_and_missing_review_cannot_pass():
    selected,frames,r=fixture();r.update(decision='REJECTED',reason='ordinary passing preparation')
    assert validate_reviews({'reviews':[r]},selected,frames)[0]['decision']=='REJECTED'
    with pytest.raises(ValueError):validate_reviews({'reviews':[]},selected,frames)

def test_cross_candidate_frame_cannot_support_movement():
    selected,frames,r=fixture();frames[1]['candidate_id']='c2'
    with pytest.raises(ValueError):validate_reviews({'reviews':[r]},selected,frames)
