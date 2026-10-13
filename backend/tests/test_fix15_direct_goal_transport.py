"""Real transport structure and failure semantics with no live credentials/calls."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error

import pytest

from scripts.direct_openai_goal_transport import DirectGoalChat, Payload


def chat():
    return DirectGoalChat(api_key='fixture-not-a-real-key',session_id='fixture',system_message='visible pixels only').with_model('openai','gpt-4o')


def message():
    return Payload(text='inspect both images',file_contents=[Payload(image_base64='fixture-a'),Payload(image_base64='fixture-b')])


def test_request_uses_direct_endpoint_and_images_without_emergent(monkeypatch):
    seen=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,_maximum):return json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'{"frames":[]}'}}]}).encode()
    def send(request,timeout):
        seen.append((request,timeout));return Response()
    monkeypatch.setattr('urllib.request.urlopen',send)
    assert asyncio.run(chat().send_message(message()))=='{"frames":[]}'
    request,timeout=seen[0];payload=json.loads(request.data)
    assert request.full_url=='https://api.openai.com/v1/chat/completions'
    assert payload['store'] is False and payload['model']=='gpt-4o'
    assert [r['type'] for r in payload['messages'][1]['content']]==['text','image_url','image_url']
    assert timeout<=55 and len(seen)==1


@pytest.mark.parametrize('finish',['length','content_filter',None])
def test_truncated_or_refused_response_cannot_supply_goal_evidence(monkeypatch,finish):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,_maximum):return json.dumps({'choices':[{'finish_reason':finish,'message':{'content':'{"goal":true}'}}]}).encode()
    monkeypatch.setattr('urllib.request.urlopen',lambda *a,**k:Response())
    with pytest.raises(RuntimeError,match='INCOMPLETE_RESPONSE'):
        asyncio.run(chat().send_message(message()))


def test_http_failure_has_no_retry_or_sensitive_response_output(monkeypatch):
    calls=[]
    def fail(*args,**kwargs):
        calls.append(1)
        raise urllib.error.HTTPError('https://api.openai.com/v1/chat/completions',401,'sensitive fixture',{},None)
    monkeypatch.setattr('urllib.request.urlopen',fail)
    c=chat()
    with pytest.raises(RuntimeError,match='^DIRECT_OPENAI_HTTP_401$'):
        asyncio.run(c.send_message(message()))
    with pytest.raises(RuntimeError,match='SECOND_CALL_BLOCKED'):
        asyncio.run(c.send_message(message()))
    assert calls==[1]


def test_explicit_transport_selection_survives_a_fresh_reader_process():
    backend=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c',
        "import fix10a_vision_providers as v; from scripts.direct_openai_goal_transport import DirectGoalChat,Payload; "
        "assert v.LlmChat is DirectGoalChat and v.UserMessage is Payload and v.ImageContent is Payload"],
        cwd=backend,env={**os.environ,'SCOUTMEPLAY_DIRECT_GOAL_TEST':'1'},
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
    assert result.returncode==0
