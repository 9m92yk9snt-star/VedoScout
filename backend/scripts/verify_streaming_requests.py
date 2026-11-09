"""Offline before/after equality of real localization JPEGs and request bytes."""
import argparse, hashlib, importlib.util, json, subprocess, tempfile, time, zipfile
from pathlib import Path
import match_room_localization as current
import sequence_pilot_transport as transport


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('video',type=Path);p.add_argument('export_zip',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args()
    baseline='fb271c18000bcbc71f51b443f87fd48beedd02bc'
    source=subprocess.check_output(['git','show',baseline+':backend/match_room_localization.py'],text=True)
    with zipfile.ZipFile(args.export_zip) as z:
        report=json.loads(z.read('report.json'))
        retained=json.loads(z.read('sequence/match-room-localization.json'))
    with args.video.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    if report['canonical_events']['source_video_sha256']!=sha:raise ValueError('Source mismatch')
    events=[e for e in report['canonical_events']['events'] if e['event_id'] in retained['events']]
    if not events:raise ValueError('No retained events to compare')
    selection={'raw_marker_anchors':report['raw_marker_anchors']}
    rows=[];references=[None,None]
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'before.py';path.write_text(source)
        spec=importlib.util.spec_from_file_location('before_localization',path)
        before=importlib.util.module_from_spec(spec);spec.loader.exec_module(before)
        for event in events:
            windows=[None]
            for wi,window in enumerate(windows):
                outputs=[];timings=[]
                for i,module in enumerate((before,current)):
                    started=time.perf_counter()
                    record,job=module.prepare(args.video,selection,event,Path(tmp)/str(i)/event['event_id']/str(wi),references[i],window=window)
                    references[i]=record['references']
                    wire=transport.build_request('emergent','gpt-6-astra',job['items'],reasoning_effort=job['reasoning_effort'],image_detail=job['image_detail'],max_output_tokens=job['max_output_tokens'])
                    outputs.append((record,wire));timings.append(time.perf_counter()-started)
                a,b=outputs
                assert a[1]==b[1], 'Wire bytes or request audit changed'
                for key in ('frames','references'):
                    assert [{k:v for k,v in f.items() if k!='path'} for f in a[0][key]]==[{k:v for k,v in f.items() if k!='path'} for f in b[0][key]],key
                rows.append({'event_id':event['event_id'],'window':window,'frames':len(a[0]['frames']),'references':len(a[0]['references']),'wire_equal':True,'before_after_seconds':timings})
                if wi==0:windows.extend(current.completion_windows(event,a[0]))
    result={'baseline_commit':baseline,'source_sha256':sha,'requests':rows,'all_equal':True,'scope':'Offline request construction only; no provider calls or total-analysis latency claim.'}
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
