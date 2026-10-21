import json
from copy import deepcopy
from pathlib import Path
import pytest
from scripts.recheck_uncertain_feints import select_uncertain,validate

def test_selection_comes_from_actual_uncertain_model_rows():
    document=json.loads((Path(__file__).parents[2]/'docs/examples/feint-source-sheet-receipts.json').read_text())
    rows=select_uncertain(document,document['source_video_sha256'],document['anchors_sha256'])
    expected=sum(row.get('decision')=='UNCERTAIN' for receipt in document['receipts'] for row in json.loads(receipt['raw_response'])['observations'])
    assert len(rows)==expected
    wrong=deepcopy(document);wrong['receipts'][0]['raw_response']+=' '
    with pytest.raises(ValueError,match='RESPONSE_CHANGED'):select_uncertain(wrong,wrong['source_video_sha256'],wrong['anchors_sha256'])
    with pytest.raises(ValueError,match='SOURCE_OR_SELECTION_MISMATCH'):select_uncertain(document,'another-video',document['anchors_sha256'])

def example():
    frames=[{'id':f'f{i}','candidate_id':'u1','source_ms':i*100} for i in range(5)]
    row=dict(candidate_id='u1',movement_decision='UNCERTAIN',type='OTHER',identity_frames=['f0'],
             before_frame='f0',movement_frames=['f1'],after_frame='f2',visible_movement='passing preparation',
             opponent_response='near ball',uncertainty='foot contact overlaps',outcome='PASSES',
             outcome_decision='SUPPORTED',outcome_frames=['f2','f4'],recipient='TEAMMATE',
             recipient_description='separate white teammate',outcome_explanation='teammate receives and carries')
    return [{'candidate_id':'u1'}],frames,row

def test_uncertain_movement_and_supported_pass_are_independent():
    candidates,frames,r=example();out=validate({'reviews':[r]},candidates,frames)[0]
    assert out['movement_decision']=='UNCERTAIN'
    assert out['outcome']=='PASSES' and out['outcome_decision']=='SUPPORTED'

@pytest.mark.parametrize('change',[
    {'outcome':'LOSES','recipient':'UNKNOWN'},
    {'outcome':'LOSES','recipient':'TEAMMATE'},
    {'outcome_frames':['f4']},
    {'outcome_frames':['f0','f1']},
    {'outcome_frames':['invented','f4']},
    {'recipient':'OPPONENT'},
    {'outcome':'UNKNOWN'},
])
def test_possession_claim_needs_its_own_evidence(change):
    candidates,frames,r=example();r.update(change)
    with pytest.raises(ValueError):validate({'reviews':[r]},candidates,frames)

def test_other_candidate_frames_cannot_support_this_outcome():
    candidates,frames,r=example();frames[-1]['candidate_id']='u2'
    with pytest.raises(ValueError):validate({'reviews':[r]},candidates,frames)

def test_retained_context_receipt_corrects_pass_without_promoting_uncertain_feints():
    import hashlib
    document=json.loads((Path(__file__).parents[2]/'docs/examples/feint-uncertainty-context-receipt.json').read_text())
    receipt=document['receipt']
    assert hashlib.sha256(receipt['raw_response'].encode()).hexdigest()==receipt['response_sha256']
    assert receipt['payload_sha256']==document['request_audit']['payload_sha256']
    reviews=validate(json.loads(receipt['raw_response']),document['candidates'],document['frames'])
    passage=next(r for r in reviews if r['candidate_id']=='u4')
    assert passage['movement_decision']=='REJECTED'
    assert passage['outcome']=='PASSES' and passage['recipient']=='TEAMMATE'
    assert all(r['movement_decision']!='SUPPORTED' for r in reviews)
    assert document['accepted_for_production_statistics'] is False
