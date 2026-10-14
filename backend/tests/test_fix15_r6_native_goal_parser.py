"""The existing goal-response gates also work without any SDK transport."""
from copy import deepcopy
from pathlib import Path
import sys,json,asyncio
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fix10a_vision_providers as vision


def payload():
    return {'geometry_status':'VERIFIED',
        'frames':[{'idx':i,'visible':True,'p1':{'x':.2,'y':.8},'p2':{'x':.8,'y':.8},'confidence':'high'}
                  for i in range(1,4)],
        'ball_evidence':[{'idx':i,'ball_visible':True,'relation':relation,
            'ball_box':{'x':.5,'y':.75+.04*(i-1),'w':.01,'h':.01},'confidence':'high'}
            for i,relation in enumerate(('FIELD_SIDE','ON_OR_STRADDLING_LINE','BEYOND_LINE_INSIDE_MOUTH'),1)],
        'same_ball_continuity':True,'first_crossing_idx':3,'crossing':'CROSSED','crossing_confidence':'high'}


def forbid(*a,**k):raise AssertionError('No model or network transport is allowed')


def test_native_parser_preserves_actual_local_model_provenance_without_sdk(monkeypatch):
    monkeypatch.setattr(vision,'LlmChat',forbid)
    audit={'provider':'LOCAL_NATIVE_CPU','model':'synthetic-local-fixture',
           'model_sha256':'fixture-model','kernel_network_filter':'SECCOMP_ERRNO_EPERM'}
    before=deepcopy(audit)
    result=vision.parse_goal_scene_response(json.dumps(payload()),[1000,1100,1200],audit)
    assert result['proof_ready'] is True
    assert result['model_review_audit']==before
    assert result['first_crossing_media_ms']==1200
    assert audit==before
    result['model_review_audit']['model']='mutated-copy'
    assert audit==before


@pytest.mark.parametrize('times',[[1000],[],[1000,1000,1200],[1000,1200,1100],
    [-1,1000,1200],[True,1100,1200],[1000.0,1100,1200],['1000',1100,1200],None])
def test_native_parser_rejects_noncanonical_or_duplicate_time_inputs(times):
    result=vision.parse_goal_scene_response(json.dumps(payload()),times)
    assert result['proof_ready'] is False
    assert result['crossing']=='UNRESOLVED'


@pytest.mark.parametrize('raw',[None,{},'','not JSON','[]','{"crossing":"CROSSED"}'])
def test_native_parser_does_not_invent_missing_structured_evidence(raw):
    result=vision.parse_goal_scene_response(raw,[1000,1100,1200])
    assert result['proof_ready'] is False
    assert result['geometry_status']=='UNRESOLVED'


def test_intermediate_body_occlusion_cannot_become_continuous_whole_ball_crossing():
    data=payload()
    data['ball_evidence'][1].update(ball_visible=False,relation='OCCLUDED_GOAL_MOUTH',
                                    occluder='GOALKEEPER_BODY',ball_box=None)
    result=vision.parse_goal_scene_response(json.dumps(data),[1000,1100,1200])
    assert result['proof_ready'] is False
    assert result['proof_reason']=='STRUCTURED_WHOLE_BALL_CROSSING_NOT_PROVEN'


def test_omitted_input_image_stays_an_explicit_coverage_gap():
    data=payload();data['ball_evidence'].pop(1)
    result=vision.parse_goal_scene_response(json.dumps(data),[1000,1100,1200])
    assert result['proof_ready'] is False
    assert result['response_coverage']['missing_media_ms']==[1100]


def test_native_and_existing_reader_apply_the_same_proof_rules(monkeypatch,tmp_path):
    data=payload()
    class Chat:
        def __init__(self,**k):pass
        def with_model(self,*a):return self
        def with_params(self,**k):return self
        async def send_message(self,*a):return json.dumps(data)
    monkeypatch.setattr(vision,'LlmChat',Chat)
    paths=[]
    for i in range(3):
        p=tmp_path/f'fixture-{i}.jpg';p.write_bytes(b'fixture-only');paths.append(str(p))
    existing=asyncio.run(vision.read_goal_scene_evidence('test-only','fixture',paths,[1000,1100,1200]))
    native=vision.parse_goal_scene_response(json.dumps(data),[1000,1100,1200],{'provider':'LOCAL_NATIVE_CPU'})
    existing.pop('model_review_audit');native.pop('model_review_audit')
    assert native==existing
