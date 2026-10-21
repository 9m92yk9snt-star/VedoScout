"""Experimental, source-grounded feint discovery. Never updates a player report.

Two bounded calls: native-video discovery, then independent image-sequence review.
No expected action times, successful outcomes or historical report are supplied.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sequence_pilot as p
import sequence_pilot_transport as t

TYPES = {'BODY_FEINT','DIRECTION_CHANGE','STOP_START','STEP_OVER','SHIELD_TURN','OTHER','UNKNOWN'}
DISCOVERY = '''Review the selected football player's dribbling across the entire supplied video.
Two synchronized views show the SAME footage at normal speed, not separate actions.
Identity references are original user selections; the point/box may include neighbours.
Follow the selected physical person, not whoever has the ball. Reestablish identity
at every cut. Do not infer unseen numbers or contacts. Ignore audio and report prose.
Look for body feints, direction changes, stop-start moves, step-overs and shield-turns.
A carry, receive, ordinary passing preparation or opponent contact is not automatically
a feint. Describe body/ball movement BEFORE, DURING and AFTER, the opponent's visible
response, and whether the player progresses, retains, passes or loses the ball.
Separate the success of a move from the eventual outcome of the whole possession.
Do not invent a specific trick, foot side, weak-foot ability, gaze, mentality or scan.
Return uncertainty when visibility cannot distinguish alternatives. No target count or
expected times are supplied. Find incidents anywhere in the video, including failed ones.
Times are approximate ORIGINAL video seconds, not match-clock or montage duration.
Return JSON {"observations":[{"start_s":0,"move_s":0,"end_s":0,
"type":"BODY_FEINT|DIRECTION_CHANGE|STOP_START|STEP_OVER|SHIELD_TURN|OTHER|UNKNOWN",
"identity_evidence":"visible link to original selection",
"before":"visible fact","movement":"visible fact","opponent_response":"visible fact or UNKNOWN",
"after":"visible fact","outcome":"PROGRESSES|RETAINS|PASSES|LOSES|UNKNOWN",
"uncertainty":"specific limitation or empty"}],"limitations":["..."]}.
Keep each movement interval short; do not describe entire possessions as single tricks.
Empty observations is a valid result.'''
VERIFY = '''Review the chronological actual source frames for each candidate. The discovery
model's observations are HYPOTHESES, not established facts. Independently check selected
identity, movement, opponent response and immediate outcome. Reject a feint when only a
carry, pass preparation or opponent's action is visible. Before/after evidence must be
visible in distinct supplied frame IDs, not inferred from a later goal. A shield-turn
can retain the ball without beating an opponent. A successful first move can precede a
later loss. Occluded foot contacts do not support naming a precise trick or foot side.
Return JSON {"reviews":[{"candidate_id":"c1","decision":"SUPPORTED|REJECTED|UNCERTAIN",
"type":"BODY_FEINT|DIRECTION_CHANGE|STOP_START|STEP_OVER|SHIELD_TURN|OTHER|UNKNOWN",
"identity_frames":["..."],"before_frame":"...","movement_frames":["..."],
"after_frame":"...","visible_movement":"...","opponent_response":"...",
"outcome":"PROGRESSES|RETAINS|PASSES|LOSES|UNKNOWN","reason":"...",
"uncertainty":"..."}]}. Include each candidate exactly once, no invented frame IDs.
Do not return ratings, academy levels, scan counts or report wording.'''


def parse_json(raw):
    text = raw.strip()
    if text.startswith('```'):
        text = text.split('\n',1)[1].rsplit('```',1)[0].strip()
    value = json.loads(text)
    if not isinstance(value,dict): raise ValueError('OBJECT_REQUIRED')
    return value


def candidates(doc,duration):
    rows = doc.get('observations')
    if not isinstance(rows,list) or len(rows)>40: raise ValueError('INVALID_OBSERVATIONS')
    for row in rows:
        times=[row.get(k) for k in ('start_s','move_s','end_s')]
        if not all(type(x) in (int,float) and math.isfinite(x) for x in times):
            raise ValueError('INVALID_SOURCE_TIME')
        if not 0 <= times[0] <= times[1] <= times[2] <= duration:
            raise ValueError('TIME_OUTSIDE_SOURCE')
        if row.get('type') not in TYPES: raise ValueError('INVALID_MOVEMENT_TYPE')
        for key in ('identity_evidence','before','movement','opponent_response','after','uncertainty'):
            if not isinstance(row.get(key),str): raise ValueError('MISSING_VISIBLE_EVIDENCE')
        if row.get('outcome') not in {'PROGRESSES','RETAINS','PASSES','LOSES','UNKNOWN'}:
            raise ValueError('INVALID_OUTCOME')
    # A budget limit is explicit, not an implication that excluded candidates failed.
    return [{**row,'candidate_id':f'c{i+1}'} for i,row in enumerate(sorted(rows,key=lambda x:x['move_s']))]


def validate_reviews(doc, selected, frames):
    rows=doc.get('reviews')
    wanted={r['candidate_id'] for r in selected}
    if not isinstance(rows,list) or len(rows)!=len(wanted) or {r.get('candidate_id') for r in rows}!=wanted:
        raise ValueError('CANDIDATE_COVERAGE_MISMATCH')
    for r in rows:
        allowed={f['id']:f for f in frames if f['candidate_id']==r['candidate_id']}
        if r.get('decision') not in {'SUPPORTED','REJECTED','UNCERTAIN'} or r.get('type') not in TYPES:
            raise ValueError('INVALID_REVIEW_DECISION')
        if r.get('outcome') not in {'PROGRESSES','RETAINS','PASSES','LOSES','UNKNOWN'}:
            raise ValueError('INVALID_REVIEW_OUTCOME')
        for key in ('visible_movement','opponent_response','reason','uncertainty'):
            if not isinstance(r.get(key),str): raise ValueError('REVIEW_EVIDENCE_REQUIRED')
        cited=[r.get('before_frame'),r.get('after_frame')]+r.get('movement_frames',[])+r.get('identity_frames',[])
        if any(x not in allowed for x in cited): raise ValueError('UNSUPPLIED_SOURCE_FRAME')
        if r['decision']=='SUPPORTED':
            if not r.get('identity_frames') or not r.get('movement_frames'):
                raise ValueError('SUPPORTED_WITHOUT_IDENTITY_OR_MOVEMENT')
            before=allowed[r['before_frame']]['source_ms'];after=allowed[r['after_frame']]['source_ms']
            if not before < after or not all(before<=allowed[x]['source_ms']<=after for x in r['movement_frames']):
                raise ValueError('NONCHRONOLOGICAL_EVIDENCE')
            if r['type']=='UNKNOWN':raise ValueError('SUPPORTED_UNKNOWN_MOVEMENT')
    return rows


def execute(items, model, packet, output):
    receipt=t.run_jobs([{'packet_id':packet,'items':items,'reasoning_effort':'low',
                        'image_detail':'high','max_output_tokens':12288}],
                       'emergent',model,deadline=time.monotonic()+210,per_call_s=205,workers=1)[0]
    p.write_json(output/(packet+'-receipt.json'),receipt)
    if receipt.get('status')!='COMPLETED':raise ValueError('MODEL_REQUEST_FAILED:'+str(receipt.get('error')))
    return parse_json(receipt['raw_response'])


def run(video, anchors, output, run_model=False):
    import cv2
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):raise ValueError('OUTPUT_MUST_BE_EMPTY')
    cap=cv2.VideoCapture(str(video))
    fps=cap.get(cv2.CAP_PROP_FPS);count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if not fps or not 1<count/fps<=180:raise ValueError('SOURCE_DURATION_OUTSIDE_PROBE_BUDGET')
    duration=count/fps
    taps=p.original_taps(p.read_json(anchors))
    top=max(0,min(r['box']['y']-r['box']['h'] for r in taps))
    bottom=min(1,max(r['box']['y']+2*r['box']['h'] for r in taps))
    y=int(top*height)//2*2;ch=(min(height,int(bottom*height))-y)//2*2
    if ch<100:raise ValueError('IDENTITY_VIEW_TOO_SMALL')
    refs=[];refaudit=[]
    for r in taps:
        cap.set(cv2.CAP_PROP_POS_MSEC,r['requested_ms']);ok,frame=cap.read()
        actual=round(cap.get(cv2.CAP_PROP_POS_MSEC))
        if not ok or abs(actual-r['requested_ms'])>1000/fps+2:raise ValueError('IDENTITY_FRAME_MISSING')
        b=r['box'];q=r['target_point']
        cv2.rectangle(frame,(round(b['x']*width),round(b['y']*height)),
                      (round((b['x']+b['w'])*width),round((b['y']+b['h'])*height)),(255,255,0),3)
        cv2.drawMarker(frame,(round(q['x']*width),round(q['y']*height)),(255,255,0),cv2.MARKER_CROSS,22,3)
        im=p._save_image(output/(r['reference_id']+'.jpg'),frame,1280,85)
        audit={**r,'source_ms':actual,'image_sha256':im['sha256']}
        refaudit.append(audit)
        refs.extend([{'type':'text','text':'IDENTITY ONLY; original selection at this instant; cross is intended person, NOT ball: '+json.dumps(audit)},
                     {'type':'image','path':im['path'],'sha256':im['sha256']}])
    views=[]
    for name,rate,filters in [('overview',4,'scale=360:-2'),('detail',12,f'crop={width}:{ch}:0:{y},scale=720:-2')]:
        path=output/(name+'.mp4')
        subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-i',str(video),'-an','-vf',filters+f',fps={rate}',
                        '-c:v','libx264','-preset','fast','-crf','30','-pix_fmt','yuv420p',str(path)],check=True,timeout=90)
        views.append({'type':'video','path':str(path.resolve()),'sha256':p.digest(path),'fps':rate})
    items=[{'type':'text','text':DISCOVERY}]+refs
    for name,view in zip(['full overview','detail band; same original time zero'],views):
        items.extend([{'type':'text','text':name},view])
    _,_,audit=t.build_request('emergent','gemini-3.1-pro-preview',items,image_detail='high',reasoning_effort='low',max_output_tokens=12288)
    meta={'schema':'FEINT_PROBE_V1','source_video_sha256':p.digest(video),'anchors_sha256':p.digest(anchors),
          'duration_s':duration,'detail_crop_xywh':[0,y,width,ch],'identity_references':refaudit,
          'discovery_payload':audit,'expected_answers_used':False,'historical_observations_used':False,
          'production_report_modified':False,'status':'PREFLIGHT_ONLY','max_model_calls':2,
          'limits':'Native discovery times approximate. Model observations require independent evaluation; not ground truth.'}
    p.write_json(output/'result.json',meta)
    if not run_model:return meta
    try:
        found=candidates(execute(items,'gemini-3.1-pro-preview','discovery',output),duration)
        meta.update(discovered_candidates=found,verification_candidates=found[:6],unreviewed_candidates=found[6:])
        p.write_json(output/'result.json',meta)
        selected=found[:6];frames=[];reviewitems=[{'type':'text','text':VERIFY}]+refs
        for row in selected:
            cid=row['candidate_id'];mid=row['move_s']
            times=sorted(set([max(0,row['start_s']-.3),min(duration-1/fps,row['end_s']+.3)]+
                             [max(0,min(duration-1/fps,mid+(i-7.5)/8)) for i in range(16)]))
            reviewitems.append({'type':'text','text':'HYPOTHESIS '+json.dumps(row)})
            for i,stamp in enumerate(times):
                cap.set(cv2.CAP_PROP_POS_MSEC,stamp*1000);ok,frame=cap.read();actual=round(cap.get(cv2.CAP_PROP_POS_MSEC))
                if not ok or abs(actual-stamp*1000)>1000/fps+2:raise ValueError('REVIEW_FRAME_MISSING')
                fid=f'{cid}_f{i:02}'
                im=p._save_image(output/(fid+'.jpg'),frame[y:y+ch,:],900,78)
                rec={'id':fid,'candidate_id':cid,'source_ms':actual,'sha256':im['sha256']}
                frames.append(rec)
                reviewitems.extend([{'type':'text','text':json.dumps(rec)},
                                    {'type':'image','path':im['path'],'sha256':im['sha256']}])
        p.write_json(output/'frames.json',frames)
        reviews=validate_reviews(execute(reviewitems,'gpt-6-astra','verification',output),selected,frames) if selected else []
        meta.update(status='MODEL_REVIEW_COMPLETED',reviews=reviews,source_frames=frames,
                    independent_generalisation_tested=False,production_ready=False)
    except Exception as exc:
        meta.update(status='INCOMPLETE',error=str(exc)[:160])
        p.write_json(output/'result.json',meta)
        raise
    finally:cap.release()
    p.write_json(output/'result.json',meta)
    return meta


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--video',required=True);a.add_argument('--anchors',required=True)
    a.add_argument('--output',required=True);a.add_argument('--run-model',action='store_true');args=a.parse_args()
    result=run(Path(args.video),Path(args.anchors),args.output,args.run_model)
    print(json.dumps({'status':result['status'],'source_video_sha256':result['source_video_sha256'],
                      'reviews':result.get('reviews',[]),'production_ready':False}))
