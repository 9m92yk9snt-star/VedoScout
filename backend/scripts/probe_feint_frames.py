"""Alternative whole-source discovery using exact chronological source-frame IDs.

No native-video timestamps, old candidate times or expected answers are loaded.
"""
import argparse,json,math,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import sequence_pilot as p
import sequence_pilot_transport as t
from scripts.probe_feint_evidence import parse_json,TYPES

PROMPT='''Review this chronological football source interval for the originally selected
physical player's feints and evasive dribbling. Identity reference crosses mark the user
selection, NOT the ball. A broad selection can contain neighbours; follow the intended
person by body, readable kit number and continuous movement. Never transfer identity to
whoever receives the ball. Reestablish identity after a cut.
Contact sheets are read left-to-right then top-to-bottom. EVERY tile has its own exact
source-frame ID and source timestamp. Sheets continue in chronological order. These
are distinct source frames, not simultaneous players or a tactical drawing.
Find short body feints (weight/body goes one way, ball/exit another), direction changes,
stop-start moves, step-overs and shield-turns. Distinguish them from ordinary running,
carrying, passing preparation and an opponent's tackle. A player can retain the ball
without beating the defender. A first move can work before a later loss. Observe the
opponent's actual movement; do not invent a wrong-way reaction. A direction change may
be supported even when deceptive intent or an opponent beaten cannot be established.
For each distinct movement cite actual before/during/after frame IDs and describe
body movement, ball motion, opponent response and immediate outcome. Keep observations
local to the movement, not an entire possession. Report failed and uncertain incidents.
Do not infer a specific trick or foot side when hidden. No scan/personality/academy
judgment. No expected incident times, counts or successful results are supplied.
Return JSON {"observations":[{"type":"BODY_FEINT|DIRECTION_CHANGE|STOP_START|STEP_OVER|SHIELD_TURN|OTHER|UNKNOWN",
"decision":"SUPPORTED|UNCERTAIN","identity_reference_ids":["r1"],
"identity_frames":["s000001"],"before_frame":"s000001",
"movement_frames":["s000002"],"after_frame":"s000003",
"visible_movement":"specific visible body and ball changes",
"opponent_response":"visible response or UNKNOWN",
"outcome":"PROGRESSES|RETAINS|PASSES|LOSES|UNKNOWN",
"uncertainty":"specific limitation or empty"}],"limitations":["..."]}.
Only supplied frame/reference IDs are allowed. Empty observations is valid.
Do not fill this response with goals, shots or assists that contain no relevant movement.'''


def validate(doc,frames,refs):
    rows=doc.get('observations')
    if not isinstance(rows,list) or len(rows)>30:raise ValueError('INVALID_OBSERVATIONS')
    lookup={f['id']:f for f in frames};refids={r['reference_id'] for r in refs}
    for r in rows:
        if r.get('type') not in TYPES or r.get('decision') not in {'SUPPORTED','UNCERTAIN'}:
            raise ValueError('INVALID_DECISION')
        for k in ['identity_frames','movement_frames','identity_reference_ids']:
            if not isinstance(r.get(k),list) or not r[k]:raise ValueError('MISSING_CITATIONS')
        if not set(r['identity_reference_ids'])<=refids:raise ValueError('UNKNOWN_REFERENCE')
        cited=[r.get('before_frame'),r.get('after_frame')]+r['movement_frames']+r['identity_frames']
        if any(f not in lookup for f in cited):raise ValueError('UNKNOWN_SOURCE_FRAME')
        lo=lookup[r['before_frame']]['source_ms'];hi=lookup[r['after_frame']]['source_ms']
        if not lo<hi or not all(lo<=lookup[f]['source_ms']<=hi for f in r['movement_frames']):
            raise ValueError('NONCHRONOLOGICAL_MOVEMENT')
        if r.get('outcome') not in {'PROGRESSES','RETAINS','PASSES','LOSES','UNKNOWN'}:raise ValueError('INVALID_OUTCOME')
        for k in ['visible_movement','opponent_response','uncertainty']:
            if not isinstance(r.get(k),str):raise ValueError('MISSING_VISIBLE_EVIDENCE')
        if r['decision']=='SUPPORTED' and r['type']=='UNKNOWN':raise ValueError('UNKNOWN_MOVEMENT_SUPPORTED')
        r['source_interval_ms']=[lo,hi]
    return rows


def run(video,anchors,output,run_model=False):
    import cv2
    from PIL import Image,ImageDraw,ImageFont
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('OUTPUT_MUST_BE_EMPTY')
    cap=cv2.VideoCapture(str(video));fps=cap.get(cv2.CAP_PROP_FPS);count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration=count/fps
    if not 1<duration<=80:raise ValueError('THREE_CALL_SOURCE_BUDGET_EXCEEDED')
    width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    taps=p.original_taps(p.read_json(anchors));refs=[];refaudit=[]
    top=max(0,min(r['box']['y']-r['box']['h'] for r in taps));bottom=min(1,max(r['box']['y']+2*r['box']['h'] for r in taps))
    y=int(top*height);bottom=int(bottom*height);tilew=432;tileh=round((bottom-y)/width*tilew)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',18)
    for r in taps:
        cap.set(cv2.CAP_PROP_POS_MSEC,r['requested_ms']);ok,pixels=cap.read()
        if not ok:raise ValueError('REFERENCE_FRAME_MISSING')
        b=r['box'];q=r['target_point']
        cv2.rectangle(pixels,(round(b['x']*width),round(b['y']*height)),(round((b['x']+b['w'])*width),round((b['y']+b['h'])*height)),(255,255,0),3)
        cv2.drawMarker(pixels,(round(q['x']*width),round(q['y']*height)),(255,255,0),cv2.MARKER_CROSS,22,3)
        im=p._save_image(out/(r['reference_id']+'.jpg'),pixels,1280,85);refaudit.append({**r,'image_sha256':im['sha256']})
        refs.extend([{'type':'text','text':'IDENTITY ONLY '+json.dumps(r)}, {'type':'image','path':im['path'],'sha256':im['sha256']}])
    jobs=[];packets=[];allframes=[]
    # Fixed coverage of the entire source, not selected moments. 2s boundary overlap.
    for chunk,start in enumerate(range(0,math.ceil(duration),27)):
        end=min(duration,start+29);frames=[];sheets=[]
        stamps=[start+i/8 for i in range(math.ceil((end-start)*8)) if start+i/8<duration]
        for sheetno in range(math.ceil(len(stamps)/12)):
            sheet=Image.new('RGB',(3*tilew,4*(tileh+30)),'#132119');draw=ImageDraw.Draw(sheet);labels=[]
            for tile,stamp in enumerate(stamps[sheetno*12:(sheetno+1)*12]):
                cap.set(cv2.CAP_PROP_POS_MSEC,stamp*1000);ok,pixels=cap.read();actual=round(cap.get(cv2.CAP_PROP_POS_MSEC))
                if not ok or abs(actual-stamp*1000)>1000/fps+2:raise ValueError('SOURCE_FRAME_UNAVAILABLE')
                fid=f's{round(stamp*1000):06}'
                rgb=cv2.cvtColor(pixels[y:bottom,:],cv2.COLOR_BGR2RGB)
                image=Image.fromarray(rgb).resize((tilew,tileh),Image.Resampling.LANCZOS)
                x=tile%3*tilew;z=tile//3*(tileh+30);sheet.paste(image,(x,z+30))
                draw.text((x+6,z+5),f'{fid} | {actual/1000:.3f}s',fill='white',font=font)
                rec={'id':fid,'source_ms':actual,'source_frame_index':round(cap.get(cv2.CAP_PROP_POS_FRAMES))-1}
                frames.append(rec);labels.append(rec)
            path=out/f'chunk{chunk}-sheet{sheetno:02}.jpg';sheet.save(path,quality=88)
            sheets.extend([{'type':'text','text':'SOURCE SHEET '+json.dumps(labels)}, {'type':'image','path':str(path.resolve()),'sha256':p.digest(path)}])
        pid=f'frames_{chunk}'
        items=[{'type':'text','text':PROMPT}]+refs+sheets
        _,_,audit=t.build_request('emergent','gpt-6-astra',items,reasoning_effort='low',image_detail='high')
        packets.append({'packet_id':pid,'start_s':start,'end_s':end,'frames':frames,'request_audit':audit})
        jobs.append({'packet_id':pid,'items':items,'reasoning_effort':'low','image_detail':'high','max_output_tokens':12288})
        allframes.extend(frames)
    cap.release()
    result={'schema':'FEINT_SOURCE_SHEETS_V1','status':'PREFLIGHT_ONLY','source_video_sha256':p.digest(video),
            'anchors_sha256':p.digest(anchors),'duration_s':duration,'sample_fps':8,'crop_xyxy':[0,y,width,bottom],
            'packets':packets,'references':refaudit,'expected_answers_used':False,'historical_observations_used':False,
            'max_model_calls':len(jobs),'production_ready':False,'unrelated_video_validated':False,
            'caveat':'Source citations and model claims are documented; factual correctness requires independent source review.'}
    p.write_json(out/'result.json',result)
    if not run_model:return result
    receipts=t.run_jobs(jobs,'emergent','gpt-6-astra',deadline=time.monotonic()+420,per_call_s=205,workers=2,
                       on_result=lambda r:p.write_json(out/(r['packet_id']+'-receipt.json'),r))
    try:
        observations=[]
        for receipt,packet in zip(receipts,packets):
            if receipt.get('status')!='COMPLETED':raise ValueError('MODEL_REQUEST_FAILED:'+str(receipt.get('error')))
            rows=validate(parse_json(receipt['raw_response']),packet['frames'],taps)
            observations.extend([{**row,'packet_id':packet['packet_id']} for row in rows])
        # Preserve overlaps explicitly rather than falsely claiming distinct take-on counts.
        result.update(status='MODEL_REVIEW_COMPLETED',observations=observations,overlap_deduplicated=False)
    except Exception as exc:
        result.update(status='INCOMPLETE',error=str(exc)[:160]);p.write_json(out/'result.json',result);raise
    p.write_json(out/'result.json',result)
    print(json.dumps({'status':result['status'],'observations':result['observations']}))
    return result

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--video',required=True);a.add_argument('--anchors',required=True)
    a.add_argument('--output',required=True);a.add_argument('--run-model',action='store_true');v=a.parse_args()
    run(Path(v.video),Path(v.anchors),v.output,v.run_model)
