"""One source-bound position request; never edits reports or approval state."""
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.probe_matchroom_pass_model import unpack
from sequence_pilot_transport import build_request, run_jobs


def main():
    source,digest=unpack('testdata/matchroom-contact-detail/packet.enc.json')
    manifest=json.loads(Path('testdata/matchroom-contact-detail/manifest.json').read_text())
    if digest!=manifest['packet_sha256'] or source['source_video_sha256']!=manifest['source_video_sha256']:
        raise ValueError('SOURCE_BINDING_CHANGED')
    with tempfile.TemporaryDirectory() as directory:
        job=source['job']
        for item in job['items']:
            if item['type']!='image':continue
            data=base64.b64decode(source['images'][item['sha256']],validate=True)
            if hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('IMAGE_CHANGED')
            path=Path(directory)/(item['sha256']+'.jpg');path.write_bytes(data);item['path']=str(path)
        _,_,audit=build_request('emergent','gpt-6-astra',job['items'],reasoning_effort='medium',image_detail='high',max_output_tokens=7000)
        if audit!=source['request']:raise ValueError('REQUEST_CHANGED')
        # Equal total/call budgets prevent the transport reserving a retry.
        receipts=run_jobs([job],'emergent','gpt-6-astra',deadline=time.monotonic()+180,per_call_s=180,workers=1)
        result={'source_video_sha256':source['source_video_sha256'],'packet_sha256':digest,
                'status':'CANDIDATE_REQUIRES_SOURCE_CHECK','model_calls_requested':1,
                'report_written':False,'approval_changed':False,'receipts':receipts}
        path=Path(os.environ['RUNNER_TEMP'])/'pass-contact-detail-result.json';path.write_text(json.dumps(result,indent=2))
        print('PASS_CONTACT_DETAIL_RESULT='+json.dumps(result),flush=True)
        return 0 if len(receipts)==1 and receipts[0].get('status')=='COMPLETED' else 3

if __name__=='__main__':raise SystemExit(main())
