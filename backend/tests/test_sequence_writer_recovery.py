"""Writer truncation recovery without accepting incomplete evidence or rerunning source."""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sequence_report_runtime as runtime
import sequence_pilot_transport as transport
import sequence_run_checkpoint as checkpoint

@pytest.mark.parametrize('kind,attempts', [('LENGTH',3), ('BLOCKED',1), ('OTHER',1), ('INVALID',1)])
def test_only_token_truncation_retries_and_reuses_expanded_result(monkeypatch,kind,attempts):
    calls=[]
    async def send(jobs,provider,model,**kwargs):
        job=deepcopy(jobs[0]);calls.append(job)
        if len(calls)==1:
            return [{'packet_id':job['packet_id'],'status':'ERROR',
                     'error':'INCOMPLETE_MODEL_RESPONSE','response_stop_kind':kind}]
        raw=json.dumps({k:{} for k in runtime.WRITER_SECTIONS[int(job['packet_id'][-1])-1]})
        audit=transport.build_request(provider,model,job['items'],
            reasoning_effort=job.get('reasoning_effort'),max_output_tokens=job['max_output_tokens'])[2]
        return [{**audit,'packet_id':job['packet_id'],'status':'COMPLETED','origin':'LIVE_MODEL_REQUEST',
                 'provider':provider,'requested_model':model,'raw_response':raw,
                 'response_sha256':hashlib.sha256(raw.encode()).hexdigest()}]
    monkeypatch.setattr(transport,'run_jobs_async',send)
    if kind!='LENGTH':
        with pytest.raises(runtime.ReportWriterFailure): asyncio.run(runtime.write_facts('prompt'))
    else:
        result=asyncio.run(runtime.write_facts('prompt'))
        assert [c['max_output_tokens'] for c in calls]==[12288,32768,12288]
        async def forbidden(*a,**kw): pytest.fail('Paid writer work repeated')
        monkeypatch.setattr(transport,'run_jobs_async',forbidden)
        again=asyncio.run(runtime.write_facts('prompt',previous_receipts=result['receipts']))
        assert again['report']==result['report']
    assert len(calls)==attempts


def test_repeated_truncation_stops_without_partial_report(monkeypatch):
    calls=[]
    async def send(jobs,*a,**kw):
        calls.append(deepcopy(jobs))
        return [{'status':'ERROR','error':'INCOMPLETE_MODEL_RESPONSE','response_stop_kind':'LENGTH'}]
    monkeypatch.setattr(transport,'run_jobs_async',send)
    with pytest.raises(runtime.ReportWriterFailure) as exc: asyncio.run(runtime.write_facts('prompt'))
    assert len(calls)==len(exc.value.receipts)==2


@pytest.mark.parametrize('provider,body',[
 ('emergent',{'choices':[{'finish_reason':'length'}],'usage':{'completion_tokens':12288,'secret':'private'}}),
 ('gemini',{'candidates':[{'finishReason':'MAX_TOKENS'}],'usageMetadata':{'thoughtsTokenCount':9000}})])
def test_worker_keeps_safe_diagnostics_on_incomplete_response(monkeypatch,provider,body):
    class Response:
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def read(self,*a): return json.dumps(body).encode()
    class Pipe:
        def send(self,value): self.value=value
        def close(self): pass
    monkeypatch.setenv(transport.KEY_ENV[provider],'synthetic')
    monkeypatch.setattr(transport.urllib.request,'urlopen',lambda *a,**kw:Response())
    pipe=Pipe();transport._worker(pipe,{'packet_id':'report_section_1','items':[]},provider,'gemini-2.5-pro',180)
    assert pipe.value['status']=='ERROR'
    assert pipe.value['response_stop_kind']=='LENGTH'
    assert pipe.value['error']=='INCOMPLETE_MODEL_RESPONSE'
    assert 'raw_response' not in pipe.value and 'private' not in json.dumps(pipe.value)


def test_writer_only_migration_rejects_source_logic_changes():
    saved=checkpoint._PRE_WRITER_RECOVERY_CODE
    current=checkpoint.code_fingerprint()
    assert checkpoint.writer_source_code_compatible(saved,current)
    for key in saved:
        if key not in {'sequence_report_runtime.py','sequence_pilot_transport.py','sequence_run_checkpoint.py'}:
            changed={**current,key:'changed'}
            assert not checkpoint.writer_source_code_compatible(saved,changed)
    assert not checkpoint.writer_source_code_compatible({**saved,'sequence_report_runtime.py':'unknown'},current)
