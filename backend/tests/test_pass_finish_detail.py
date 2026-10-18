"""Regression: contact review must cover the pass AND its later finish."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.probe_actor_continuity import pass_finish_gap, validate_native_coverage


def saved_chain():
    raw = {'ball_contact_chain':[
        {'type':'pass','before_frame':'s000001000','after_frame':'s000001100','uncertainty':''},
        {'type':'control','before_frame':'s000001200','after_frame':'s000001600','uncertainty':'Receiving foot hidden'},
        {'type':'shot','before_frame':'s000002000','after_frame':'s000002300','uncertainty':''}]}
    response = json.dumps(raw)
    return {'question':{'packet_id':'play','start_ms':0,'end_ms':3500,'detail_start_ms':500,'detail_end_ms':1500},
        'receipt':{'packet_id':'play','status':'COMPLETED','origin':'LIVE_MODEL_REQUEST',
                   'raw_response':response,'response_sha256':hashlib.sha256(response.encode()).hexdigest()}}


def test_later_finish_is_added_even_when_old_detail_window_ended_after_pass():
    saved = saved_chain(); original = deepcopy(saved)
    q = pass_finish_gap(saved)
    assert q['detail_windows'] == [
        {'start_ms':750,'end_ms':1350,'role':'release'},
        {'start_ms':1750,'end_ms':2550,'role':'finish'}]
    assert q['detail_end_ms'] > saved['question']['detail_end_ms']
    assert q['start_ms'] == 0 and q['end_ms'] == 3500
    assert saved == original


def test_pass_coverage_alone_cannot_masquerade_as_complete_contact_evidence():
    windows = pass_finish_gap(saved_chain())['detail_windows']
    release = list(range(750,1351,17))
    with pytest.raises(ValueError,match='COVERAGE_INCOMPLETE'):
        validate_native_coverage(release,windows)
    validate_native_coverage(release+list(range(1750,2551,17)),windows)


def test_contact_navigation_rejects_modified_model_reply():
    saved = saved_chain(); saved['receipt']['raw_response'] += ' '
    with pytest.raises(ValueError,match='INVALID_PRIOR_OBSERVATION'):
        pass_finish_gap(saved)


def test_actual_retained_response_produces_later_finishing_window():
    saved = json.loads((Path(__file__).resolve().parents[2]/'docs/examples/native-pass-finish-gap-receipt.json').read_text())
    q = pass_finish_gap(saved)
    assert q['detail_windows'][-1]['start_ms'] > saved['question']['detail_end_ms']
    assert q['detail_windows'][-1]['end_ms'] < q['end_ms']
