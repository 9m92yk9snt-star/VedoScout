"""Bounded source-context reread of model-returned uncertain movements.

Selects intervals from raw model receipts, never user reference times. No report
or canonical event result is supplied. Movement and possession decisions differ.
"""
import argparse,json,math,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import sequence_pilot as p
import sequence_pilot_transport as t
from scripts.probe_feint_evidence import parse_json,TYPES

PROMPT='''Examine the selected football player's uncertain movement hypotheses using
these chronological source-frame sheets. The supplied prior wording is an unverified
hypothesis. Original user selections establish identity only; the cross is NOT the ball.
Read each sheet left-to-right, top-to-bottom. Each tile has its own source ID and time.
Follow the active ball and each physical person through the entire supplied context.
Keep the selected passer, recipient and eventual shooter separate. An opponent near
or reaching towards the ball is not necessarily in controlled possession. Do not
infer interception from a single crowded frame. Follow the recipient after release.
A continued selected-player run does not make that player the recipient or finisher.
Evaluate the movement independently of the subsequent possession outcome. A turn may
retain possession locally even if a later challenge loses the ball. A direction change
need not deceive or beat an opponent. A passing preparation need not be a feint.
State UNKNOWN/UNCERTAIN when contact, actor or recipient remains obscured. Do not guess
foot side, specific tricks, scanning or personality. No expected answers are supplied.
Return JSON {"reviews":[{"candidate_id":"u1","movement_decision":"SUPPORTED|UNCERTAIN|REJECTED",
"type":"BODY_FEINT|DIRECTION_CHANGE|STOP_START|STEP_OVER|SHIELD_TURN|OTHER|UNKNOWN",
"identity_frames":["..."],"before_frame":"...","movement_frames":["..."],"after_frame":"...",
"visible_movement":"...","opponent_response":"...","uncertainty":"...",
"outcome":"PROGRESSES|RETAINS|PASSES|LOSES|UNKNOWN","outcome_decision":"SUPPORTED|UNCERTAIN",
"outcome_frames":["..."],"recipient":"SELF|TEAMMATE|OPPONENT|UNKNOWN",
"recipient_description":"visible distinguishing features; do not invent a number",
"outcome_explanation":"visible sequence and its limitations"}]}.
Include every candidate once. Cite only that candidate's supplied source IDs.
A SUPPORTED LOSES needs visible opponent-controlled possession; SUPPORTED PASSES needs
a visibly distinct teammate recipient. An uncertain movement cannot create a scored
successful/failed dribble merely because its later possession outcome is clear.'''


def select_uncertain(document,source_sha,anchors_sha):
    if document.get('source_video_sha256')!=source_sha or document.get('anchors_sha256')!=anchors_sha:
        raise ValueError('SOURCE_OR_SELECTION_MISMATCH')
    rows=[]
    for receipt in document.get('receipts',[]):
        if receipt.get('status')!='COMPLETED' or receipt.get('origin')!='LIVE_MODEL_REQUEST':
            raise ValueError('LIVE_RECEIPT_REQUIRED')
        if p.hashlib.sha256(receipt['raw_response'].encode()).hexdigest()!=receipt.get('response_sha256'):
            raise ValueError('RESPONSE_CHANGED')
        byid={f['id']:f for f in document['cited_source_frames']}
        for row in parse_json(receipt['raw_response']).get('observations',[]):
            if row.get('decision')!='UNCERTAIN':continue
            lo=byid[row['before_frame']]['source_ms'];hi=byid[row['after_frame']]['source_ms']
            rows.append({**row,'candidate_id':f'u{len(rows)+1}','interval_ms':[lo,hi],
                         'origin_receipt_sha256':receipt['response_sha256']})
    if not 1<=len(rows)<=4:raise ValueError('UNCERTAINTY_REVIEW_BUDGET_EXCEEDED')
    return rows


def validate(doc,candidates,frames):
    rows=doc.get('reviews');wanted={r['candidate_id'] for r in candidates}
    if not isinstance(rows,list) or len(rows)!=len(wanted) or {r.get('candidate_id') for r in rows}!=wanted:
        raise ValueError('CANDIDATE_COVERAGE_MISMATCH')
    for r in rows:
        available={f['id']:f for f in frames if f['candidate_id']==r['candidate_id']}
        if r.get('movement_decision') not in {'SUPPORTED','UNCERTAIN','REJECTED'} or r.get('type') not in TYPES:
            raise ValueError('INVALID_MOVEMENT_DECISION')
        if r.get('outcome_decision') not in {'SUPPORTED','UNCERTAIN'}:raise ValueError('OUTCOME_DECISION_REQUIRED')
        for key in ['identity_frames','movement_frames','outcome_frames']:
            if not isinstance(r.get(key),list):raise ValueError('FRAME_LIST_REQUIRED')
        cited=[r.get('before_frame'),r.get('after_frame')]+r['identity_frames']+r['movement_frames']+r['outcome_frames']
        if any(x not in available for x in cited):raise ValueError('UNSUPPLIED_SOURCE_FRAME')
        before=available[r['before_frame']]['source_ms'];after=available[r['after_frame']]['source_ms']
        if before>=after or not all(before<=available[x]['source_ms']<=after for x in r['movement_frames']):
            raise ValueError('NONCHRONOLOGICAL_MOVEMENT')
        if r['movement_decision']=='SUPPORTED' and (not r['identity_frames'] or not r['movement_frames'] or r['type']=='UNKNOWN'):
            raise ValueError('MOVEMENT_EVIDENCE_REQUIRED')
        if r.get('outcome') not in {'PROGRESSES','RETAINS','PASSES','LOSES','UNKNOWN'} or r.get('recipient') not in {'SELF','TEAMMATE','OPPONENT','UNKNOWN'}:
            raise ValueError('INVALID_POSSESSION_OUTCOME')
        if r['outcome_decision']=='SUPPORTED':
            if r['outcome']=='UNKNOWN' or len(set(r['outcome_frames']))<2:raise ValueError('OUTCOME_EVIDENCE_REQUIRED')
            if max(available[x]['source_ms'] for x in r['outcome_frames'])<after:raise ValueError('OUTCOME_AFTER_ACTION_REQUIRED')
            if r['outcome']=='PASSES' and r['recipient']!='TEAMMATE':raise ValueError('TEAMMATE_RECIPIENT_REQUIRED')
            if r['outcome']=='LOSES' and r['recipient']!='OPPONENT':raise ValueError('OPPONENT_CONTROL_REQUIRED')
        for key in ['visible_movement','opponent_response','uncertainty','recipient_description','outcome_explanation']:
            if not isinstance(r.get(key),str):raise ValueError('VISIBLE_EVIDENCE_REQUIRED')
    return rows


def run(video,anchors,previous,output,run_model=False):
    import cv2
    from PIL import Image,ImageDraw,ImageFont
    begun=time.monotonic();out=Path(output);out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('OUTPUT_MUST_BE_EMPTY')
    old=p.read_json(previous);candidates=select_uncertain(old,p.digest(video),p.digest(anchors))
    cap=cv2.VideoCapture(str(video));fps=cap.get(cv2.CAP_PROP_FPS);count=round(cap.get(cv2.CAP_PROP_FRAME_COUNT));duration=count/fps
    width=round(cap.get(cv2.CAP_PROP_FRAME_WIDTH));height=round(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    taps=p.original_taps(p.read_json(anchors));y=max(0,int(min(r['box']['y']-r['box']['h'] for r in taps)*height));bottom=min(height,int(max(r['box']['y']+2*r['box']['h'] for r in taps)*height))
    needed={round(r['requested_ms']*fps/1000) for r in taps};plans={}
    for r in candidates:
        lo=max(0,r['interval_ms'][0]/1000-1);hi=min(duration-1/fps,r['interval_ms'][1]/1000+4)
        plans[r['candidate_id']]=sorted({round((lo+i/8)*fps) for i in range(math.ceil((hi-lo)*8))})
        needed.update(plans[r['candidate_id']])
    # One forward decode; no repeated GOP seeks, no synthetic motion or new tracking.
    saved={};i=-1
    for index in sorted(needed):
        while i<index:
            if not cap.grab():raise ValueError('SOURCE_FRAME_MISSING')
            i+=1
        ok,pixels=cap.retrieve()
        if not ok:raise ValueError('SOURCE_FRAME_MISSING')
        path=out/f'raw-{index:06}.jpg';cv2.imwrite(str(path),pixels,[cv2.IMWRITE_JPEG_QUALITY,95]);saved[index]=(path,round(cap.get(cv2.CAP_PROP_POS_MSEC)))
    cap.release();items=[{'type':'text','text':PROMPT}];reference_audit=[]
    for r in taps:
        path,actual=saved[round(r['requested_ms']*fps/1000)];pixels=cv2.imread(str(path));b=r['box'];q=r['target_point']
        cv2.rectangle(pixels,(round(b['x']*width),round(b['y']*height)),(round((b['x']+b['w'])*width),round((b['y']+b['h'])*height)),(255,255,0),3)
        cv2.drawMarker(pixels,(round(q['x']*width),round(q['y']*height)),(255,255,0),cv2.MARKER_CROSS,22,3)
        image=p._save_image(out/(r['reference_id']+'.jpg'),pixels,1280,85);reference_audit.append({**r,'actual_ms':actual,'image_sha256':image['sha256']})
        items.extend([{'type':'text','text':'IDENTITY ONLY '+json.dumps(r)}, {'type':'image','path':image['path'],'sha256':image['sha256']}])
    frames=[];font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',18);tilew=432;tileh=round((bottom-y)/width*tilew)
    for candidate in candidates:
        cid=candidate['candidate_id'];indices=plans[cid]
        items.append({'type':'text','text':'UNCERTAIN HYPOTHESIS '+json.dumps(candidate)})
        for sheetno in range(math.ceil(len(indices)/12)):
            sheet=Image.new('RGB',(tilew*3,(tileh+30)*4),'#132119');draw=ImageDraw.Draw(sheet);labels=[]
            for tile,index in enumerate(indices[sheetno*12:(sheetno+1)*12]):
                path,actual=saved[index];im=Image.open(path).crop((0,y,width,bottom)).resize((tilew,tileh),Image.Resampling.LANCZOS)
                fid=f'{cid}_f{index:06}';x=tile%3*tilew;z=tile//3*(tileh+30);sheet.paste(im,(x,z+30));draw.text((x+5,z+5),f'{fid} | {actual/1000:.3f}s',fill='white',font=font)
                rec={'id':fid,'candidate_id':cid,'source_frame_index':index,'source_ms':actual,'source_jpeg_sha256':p.digest(path)};labels.append(rec);frames.append(rec)
            path=out/f'{cid}-sheet{sheetno:02}.jpg';sheet.save(path,quality=65)
            items.extend([{'type':'text','text':'SOURCE SHEET '+json.dumps(labels)}, {'type':'image','path':str(path.resolve()),'sha256':p.digest(path)}])
    _,_,audit=t.build_request('emergent','gpt-6-astra',items,reasoning_effort='low',image_detail='high',max_output_tokens=12288)
    result={'schema':'FEINT_UNCERTAINTY_CONTEXT_V1','status':'PREFLIGHT_ONLY','source_video_sha256':p.digest(video),
            'anchors_sha256':p.digest(anchors),'previous_receipts_sha256':p.digest(previous),'candidates':candidates,
            'frames':frames,'references':reference_audit,'request_audit':audit,'preparation_seconds':round(time.monotonic()-begun,3),
            'max_model_calls':1,'expected_answers_used':False,'production_report_modified':False,'unrelated_video_validated':False}
    p.write_json(out/'result.json',result)
    if not run_model:return result
    receipt=t.run_jobs([{'packet_id':'uncertainty_context','items':items,'reasoning_effort':'low','image_detail':'high','max_output_tokens':12288}],
                       'emergent','gpt-6-astra',deadline=time.monotonic()+210,per_call_s=205,workers=1)[0]
    p.write_json(out/'receipt.json',receipt)
    try:
        if receipt.get('status')!='COMPLETED':raise ValueError('MODEL_REQUEST_FAILED:'+str(receipt.get('error')))
        result.update(reviews=validate(parse_json(receipt['raw_response']),candidates,frames),status='MODEL_REVIEW_COMPLETED')
    except Exception as exc:
        result.update(status='INCOMPLETE',error=str(exc)[:160]);p.write_json(out/'result.json',result);raise
    p.write_json(out/'result.json',result);print(json.dumps({'status':result['status'],'reviews':result['reviews']}));return result

if __name__=='__main__':
    a=argparse.ArgumentParser()
    for name in ['video','anchors','previous','output']:a.add_argument('--'+name,required=True)
    a.add_argument('--run-model',action='store_true');v=a.parse_args()
    run(Path(v.video),Path(v.anchors),Path(v.previous),v.output,v.run_model)
