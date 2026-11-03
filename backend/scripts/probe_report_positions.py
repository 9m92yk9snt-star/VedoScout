"""One bounded source-only localization request for an existing report event.

Never edits action findings or represents model observations as human taps.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import sequence_pilot as pilot
import sequence_pilot_transport as transport
from video_timebase import read_frame_at
from scripts.run_matchroom_single_tap_trial import prepare

PROMPT = '''Locate the SAME physical player selected by the original human point in the reference image. Reference images identify a person, not an action. Use the chronological identity-context images to test continuity from the original tap to the output timeline. These context images contain no extra selections. If a cut, disappearance or competing appearance prevents re-identification, keep identity uncertain; never assume the next highlighted player is the target. Output rows only for TIMELINE images. Examine the full timeline independently; never transfer identity to a nearby teammate, recipient or scorer. A jersey number alone, proximity to the ball or the expected role is insufficient when conflicting people are visible.
Return JSON {"frames":[...]} with exactly one row for EVERY supplied timeline frame, in order. Each row: {"frame":"source frame ID","target_status":"CONFIRMED|UNCERTAIN|ABSENT","identity_evidence":"visible reason for this decision","feet_visible":true|false,"ground":[x,y] or null,"box":[x,y,w,h] or null,"active_ball_status":"CONFIRMED|UNCERTAIN|ABSENT","ball":[x,y] or null}.
Coordinates are normalized in the full uncropped source image. Ground is the observed contact with the pitch under the selected player's feet, never an estimated hidden point or the midpoint of a falling body. Box encloses the selected visible person only. When feet are hidden ground must be null. Confirm identity after occlusion only from visible continuity/appearance excluding competing players. If uncertain, target_status=UNCERTAIN and ground/box=null. Do not interpolate or invent positions through a duel, fall, cut or occlusion. Confirm the active ball only when distinguishable from spare balls and other objects; otherwise ball=null. Do not predict where a kick will go. Report all missing observations explicitly. No result, scores, prior positions or expected motion are provided.'''


def validate(raw, frames):
    rows = json.loads(raw.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip())
    rows = rows.get('frames')
    if not isinstance(rows, list) or [r.get('frame') for r in rows if isinstance(r, dict)] != [f['frame_id'] for f in frames]:
        raise ValueError('COMPLETE_ORDERED_FRAME_COVERAGE_REQUIRED')
    def point(p):
        return isinstance(p,list) and len(p)==2 and all(type(x) in (int,float) and 0 <= x <= 1 for x in p)
    for r in rows:
        if r.get('target_status') not in ('CONFIRMED','UNCERTAIN','ABSENT') or r.get('active_ball_status') not in ('CONFIRMED','UNCERTAIN','ABSENT'):
            raise ValueError('EXPLICIT_OBSERVATION_STATUS_REQUIRED')
        if r.get('target_status') != 'CONFIRMED' and (r.get('ground') is not None or r.get('box') is not None):
            raise ValueError('UNCONFIRMED_PLAYER_COORDINATES')
        if r.get('ground') is not None and (r.get('feet_visible') is not True or not point(r['ground'])):
            raise ValueError('UNOBSERVED_GROUND')
        if r.get('ball') is not None and (r.get('active_ball_status') != 'CONFIRMED' or not point(r['ball'])):
            raise ValueError('UNOBSERVED_BALL')
        b=r.get('box')
        if b is not None and (not isinstance(b,list) or len(b)!=4 or not point(b[:2]) or not point(b[2:]) or b[2]<=0 or b[3]<=0 or b[0]+b[2]>1 or b[1]+b[3]>1):
            raise ValueError('INVALID_PERSON_BOX')
        if not isinstance(r.get('identity_evidence'),str) or not r['identity_evidence'].strip():
            raise ValueError('IDENTITY_EVIDENCE_REQUIRED')
    return [{**r,'media_ms':f['media_ms']} for r,f in zip(rows,frames)]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--report',type=Path,required=True);ap.add_argument('--work',type=Path,required=True);ap.add_argument('--run-model',action='store_true');args=ap.parse_args()
    doc=pilot.read_json(args.report)
    if doc.get('full_report_status')!='ready':raise ValueError('READY_REPORT_REQUIRED')
    video,selection=prepare(Path(__file__).resolve().parents[2]/'testdata/sequence-pilot-orman400',args.work)
    bundle=doc['canonical_events']; source=pilot.digest(video)
    if source!=bundle['source_video_sha256'] or selection['raw_marker_anchors']!=doc['raw_marker_anchors']:raise ValueError('SOURCE_SELECTION_MISMATCH')
    row=doc['full_report']['video_comments'][0]
    event=next(e for e in bundle['events'] if e['event_id']==row['event_id'])
    lo=max(0,event['proof']['proof_start_ms']-750);hi=event['proof']['proof_end_ms']+750
    if hi-lo>5000:raise ValueError('FOCUSED_WINDOW_REQUIRED')
    cap=cv2.VideoCapture(str(video));items=[{'type':'text','text':PROMPT}];frames=[]
    def image(ms,name, max_edge=1920, quality=75):
        ok,pixels,actual=read_frame_at(cap,ms/1000)
        if not ok:raise ValueError('SOURCE_FRAME_UNAVAILABLE')
        scale=min(1,max_edge/max(pixels.shape[:2]))
        if scale<1:pixels=cv2.resize(pixels,(round(pixels.shape[1]*scale),round(pixels.shape[0]*scale)),interpolation=cv2.INTER_AREA)
        path=args.work/(name+'.jpg');cv2.imwrite(str(path),pixels,[cv2.IMWRITE_JPEG_QUALITY,quality])
        return {'frame_id':'s'+str(round(actual*1000)).zfill(9),'media_ms':round(actual*1000),'path':str(path),'sha256':pilot.digest(path)}
    for tap in pilot.original_taps(selection):
        f=image(tap['requested_ms'],tap['reference_id'],quality=85);items += [{'type':'text','text':'ORIGINAL HUMAN IDENTITY REFERENCE '+json.dumps({'frame':f['frame_id'],'point':tap['target_point'],'box':tap['box']})},{'type':'image','path':f['path'],'sha256':f['sha256']}]
    # Source-only continuity context; never treat a model box as a human tap.
    context=[]
    first_tap=min(t['requested_ms'] for t in pilot.original_taps(selection))
    if lo-first_tap>35000:raise ValueError('BOUNDED_IDENTITY_CONTEXT_REQUIRED')
    for i,ms in enumerate(range(first_tap,lo,500)):
        f=image(ms,'context-'+str(i),max_edge=960,quality=75);context.append(f)
        items += [{'type':'text','text':'IDENTITY CONTEXT (not an output row) '+json.dumps({'frame':f['frame_id'],'media_ms':f['media_ms']})},{'type':'image','path':f['path'],'sha256':f['sha256']}]
    times=sorted(set(list(range(lo,hi+1,83))+list(event['proof']['cited_frames'].values())+[hi]));seen=set()
    for i,ms in enumerate(times):
        f=image(ms,'timeline-'+str(i))
        if f['frame_id'] in seen:continue
        seen.add(f['frame_id']);frames.append(f)
        items += [{'type':'text','text':'TIMELINE '+json.dumps({'frame':f['frame_id'],'media_ms':f['media_ms']})},{'type':'image','path':f['path'],'sha256':f['sha256']}]
    cap.release()
    _,_,request=transport.build_request('emergent','gpt-6-astra',items,reasoning_effort='medium',image_detail='high',max_output_tokens=12000)
    output={'source_video_sha256':source,'event_id':event['event_id'],'human_tap_count':1,'frames':frames,'identity_context':context,'request':request,'prompt':PROMPT,'reviewed_positions_supplied':False,'report_modified':False,'status':'PREFLIGHT_ONLY'}
    pilot.write_json(args.work/'positions-result.json',output)
    print(json.dumps({'frames':len(frames),'payload_bytes':request['payload_bytes'],'event_id':event['event_id']}),flush=True)
    if args.run_model:
        receipt=transport.run_jobs([{'packet_id':'positions_001','items':items,'reasoning_effort':'medium','image_detail':'high','max_output_tokens':12000}], 'emergent','gpt-6-astra',deadline=time.monotonic()+215,per_call_s=210,workers=1)[0]
        output['receipt']=receipt;output['status']='MODEL_REQUEST_FAILED'
        pilot.write_json(args.work/'positions-result.json',output)
        if receipt.get('status')!='COMPLETED':raise RuntimeError('POSITION_REQUEST_FAILED')
        output['observations']=validate(receipt['raw_response'],frames);output['status']='OBSERVATIONS_RETURNED_NOT_VISUALLY_VERIFIED'
        pilot.write_json(args.work/'positions-result.json',output)
        print(json.dumps({'status':output['status'],'ground_samples':sum(r.get('ground') is not None for r in output['observations']),'ball_samples':sum(r.get('ball') is not None for r in output['observations'])}))

if __name__=='__main__':main()
