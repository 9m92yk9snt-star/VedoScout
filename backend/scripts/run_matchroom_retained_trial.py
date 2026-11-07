"""Regenerate report graphics from retained ALL-tap model evidence.

No source-analysis or report-writing calls. The explicit --run-model option
permits only the selected report clips' presentation-position requests.
"""
import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sequence_pilot as pilot
import sequence_report_adapter as adapter
import sequence_report_runtime as runtime
import match_room_localization as localization
from scripts.run_sequence_report_trial import ReportStore
from scripts.run_matchroom_single_tap_trial import prepare as reconstruct


def retained(root):
    doc=pilot.read_json(root/'docs/examples/sequence-report-source-checkpoint.json')
    audit=doc['sequence_audit']
    manifest={'source_video_sha256':audit['source_video_sha256'],'original_taps_sha256':audit['original_taps_sha256'],
              'frames':audit['source_frames'],'references':audit['references']}
    bundle=adapter.canonical_bundle(audit['result'],manifest,audit['receipts'])
    raw=doc['raw_marker_anchors']
    while isinstance(raw,str):raw=json.loads(raw)
    original=pilot.read_json(root/'testdata/sequence-pilot-orman400/anchors.json')['raw_marker_anchors']
    while isinstance(original,str):original=json.loads(original)
    if raw!=original:raise ValueError('ORIGINAL_SELECTIONS_CHANGED')
    prose={}
    for receipt in pilot.read_json(root/'docs/examples/sequence-report-sections-receipts.json')['writer_receipts']:
        import hashlib
        if hashlib.sha256(receipt['raw_response'].encode()).hexdigest()!=receipt['response_sha256']:
            raise ValueError('WRITER_RECEIPT_CHANGED')
        prose.update(json.loads(receipt['raw_response']))
    doc.update(raw_marker_anchors=raw,canonical_events=bundle,full_report=adapter.build_report(prose,bundle))
    return doc


async def run(args):
    root=Path(__file__).resolve().parents[2]
    doc=retained(root)
    video,_=reconstruct(root/'testdata/sequence-pilot-orman400',args.work)
    if pilot.digest(video)!=doc['canonical_events']['source_video_sha256']:raise ValueError('SOURCE_CHANGED')
    selection={'raw_marker_anchors':doc['raw_marker_anchors']}
    (args.work/'single-tap.json').unlink()
    pilot.write_json(args.work/'all-taps.json',selection)
    ids=[r['event_id'] for r in doc['full_report']['video_comments']][:args.event_limit]
    args.output.mkdir(parents=True,exist_ok=False)
    if args.resume_document:
        previous=pilot.read_json(args.resume_document)
        if previous['raw_marker_anchors']!=doc['raw_marker_anchors']:raise ValueError('RESUME_SELECTIONS_CHANGED')
        doc['match_room_localization']=previous.get('match_room_localization') or {}
    if not args.run_model:
        preflight=[]
        for e in doc['canonical_events']['events']:
            if e['event_id'] in ids:
                record,_=localization.prepare(video,selection,e,args.work/('preflight-'+e['event_id']))
                preflight.append({'event_id':e['event_id'],'references':len(record['references']),
                                  'frames':len(record['frames']),'payload_bytes':record['request']['payload_bytes']})
        print(json.dumps({'scope':'PREFLIGHT_ONLY','human_taps':len(pilot.original_taps(selection)),'requests':preflight}))
        return
    store=ReportStore(doc)
    bounded_jobs = localization.bounded_request_runner(
        localization.transport.run_jobs, args.max_new_requests)
    async def localize(video, document, *, checkpoint):
        return await localization.localize(video,document,checkpoint=checkpoint,event_ids=ids,run_jobs=bounded_jobs)
    async def publish(path,mime):return '/api/uploads/frames/'+path.name
    try:
        await runtime.persist_assets(store,doc,video,args.output/'frames',publish,localizer=localize)
        store.doc['full_report_status']='ready'
    finally:
        store.doc['test_scope']={'source_analysis_reused':True,'report_prose_reused':True,
            'normal_asset_pipeline':True,'position_event_ids':ids,'human_taps':len(pilot.original_taps(selection)),
            'production_database_used':False,'notifications_sent':0}
        pilot.write_json(args.output/'report-document.json',store.doc)
        rows=store.doc.get('full_report',{}).get('video_comments',[])
        summary={'status':store.doc.get('full_report_status'),'scope':store.doc['test_scope'],
            'graphics':[{'event_id':r['event_id'],'tracking':r.get('match_room',{}).get('tracking_status'),
                'samples':len(r.get('match_room',{}).get('samples',[])),
                'segments':len((r.get('match_room',{}).get('tracking') or {}).get('segments',[])),
                'ball_segments':len((r.get('match_room',{}).get('tracking') or {}).get('ball_playback',[]))} for r in rows]}
        pilot.write_json(args.output/'summary.json',summary)
        print(json.dumps(summary),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--run-model',action='store_true');ap.add_argument('--event-limit',type=int,choices=range(1,9),default=1)
    ap.add_argument('--resume-document',type=Path)
    ap.add_argument('--max-new-requests',type=int,choices=range(9),default=8)
    asyncio.run(run(ap.parse_args()))
