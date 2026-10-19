"""Read one unresolved play using nearest original selections and continuous detail.

The previous reply supplies source navigation only. Neither its action wording
nor reference answers are included in the new request. The existing assist
resolver owns approval; a completed model request does not imply approval.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import sequence_pilot as p
import sequence_pilot_transport as t
from scripts.probe_actor_continuity import unresolved_gap, viewing_band, validate_native_coverage
from scripts.probe_native_play import spatial_reference_items
from scripts.probe_continuous_pass import LINK_INSTRUCTION, MAPPING_INSTRUCTION, resolve_assist


PROMPT = '''Read this complete chronological football play and original-source
detail. Match the selected physical person using the original human selections.
Identity examples before/after the play are separate identity-only instants, not
part of the contact chain. No new in-play selection or predicted track exists.
Compare visible appearance and continuous movement; a readable number can help,
but never guess a hidden number or transfer identity to the eventual recipient.
Keep every physical player separate before, during and after an occlusion.
Use reference_ids only for POSITIVE same-person matches; put negative comparisons
in appearance. If different people appear to match the selected references, keep
identity unresolved. Source evidence_frames must cite this play's source images.
Follow the active ball from the buildup through the outcome. A reaching leg or
proximity alone does not prove a touch. Separate a slight brush from controlled
possession or an intervening deliberate pass. A dive does not prove an outcome;
follow the moving ball and distinguish stationary spares. Describe concrete body
and ball movement on both sides of hidden contact and retain real alternatives.
No expected actions, counts, times or outcomes are supplied.
Return JSON {"players":[{"person_id":"p1","selected":null,"appearance":"visible features",
"reference_ids":[],"evidence_frames":[]}],"contact_chain":[{"actor":"p1",
"kind":"observed action","before_frame":"s...","after_frame":"s...",
"recipient":null,"visible_evidence":"before/after movement",
"remaining_alternatives":"unresolved alternatives or empty"}],
"outcome":{"kind":"observed result or UNKNOWN","last_touch_actor":null,
"evidence":[],"uncertainty":"unresolved alternatives or empty"}}.
'''

ONE_TOUCH_INSTRUCTION = '''For a genuine first-time finish, reception and striking
may be the SAME uniquely supported action. Add "one_touch_finish":true/false/null
to event_mapping. As an exception to the separate-reception example above,
receive_chain_index may equal finish_chain_index ONLY when one_touch_finish is
true and the first receiving contact itself is the supported finishing action.
Do not invent a separate receiving touch or settled possession. For separate
reception/finish rows use one_touch_finish=false. Keep null when unresolved.
'''

LIMB_INSTRUCTION = '''Additional synchronized lower-body crops cover a user-supplied
navigation instant. The user supplied WHERE to inspect, not an input action label,
contact actor, kicking side, recipient or expected result. First trace every
nearby player's torso/shorts to their own knees, socks and boots across the source
sequence; distinguish anatomical left/right from screen left/right. Count only
visible or motion-supported limbs. An unused/unseen leg is not, by subtraction,
evidence of another person's touch. Compare ball motion before/after the relevant
foot movement and follow any outgoing ball to its next actual toucher and finish.
Keep both a continued individual action and a possible release to another player
as alternatives until the visible motion distinguishes them. Do not infer a pass
or strike from a following run alone. No hidden joints or intervening touches may
be invented. Give only a few decisive source citations, not per-frame rows.
ADD "contact_ownership_review":{
"status":"SUPPORTED|CONTRADICTED|UNCERTAIN","release_actor":null,
"anatomical_side":"LEFT|RIGHT|UNKNOWN","frames":["s...","s..."],
"observation":"concrete selected-player release evidence or why unresolved",
"leg_map":[{"actor":"person ID","visible_leg_count":0,
"frames":["s..."],"observation":"body-to-foot continuity, not inferred touch"}],
"limitations":"occluded or ambiguous limbs"}.
SUPPORTED here means a release of the active ball BY the selected person is
uniquely supported in the lower-body review window; it does not itself establish
its recipient, a finish or a goal. Those need the separate contact-chain links.
'''


def temporal_references(references,start,end):
    """Prefer actual in-play taps; otherwise take the nearest temporal neighbours.

    Include adjacent examples within 500ms of either neighbour. This is a fixed
    time-only rule, not selection by model opinion, appearance or event outcome.
    """
    refs=sorted(references,key=lambda r:(r['media_ms'],r['reference_id']))
    local=[r for r in refs if start <= r['media_ms'] <= end]
    if local:
        return local
    before=[r for r in refs if r['media_ms'] < start]
    after=[r for r in refs if r['media_ms'] > end]
    if not before or not after:
        raise ValueError('BRACKETING_ORIGINAL_SELECTIONS_REQUIRED')
    return ([r for r in before if before[-1]['media_ms']-r['media_ms'] <= 500]+
            [r for r in after if r['media_ms']-after[0]['media_ms'] <= 500])


def source_question(saved):
    question=dict(unresolved_gap(saved))
    observed=json.loads(saved['receipt']['raw_response'])
    starts=[]
    for row in observed.get('selected_player_actions',[]):
        fid=row.get('before_frame')
        if not isinstance(fid,str) or not re.fullmatch(r's\d{9}',fid):
            raise ValueError('SOURCE_CITED_BUILDUP_REQUIRED')
        ms=int(fid[1:])
        if not question['start_ms'] <= ms <= question['end_ms']:
            raise ValueError('BUILDUP_OUTSIDE_SOURCE_PLAY')
        starts.append(ms)
    if not starts:
        raise ValueError('SOURCE_CITED_BUILDUP_REQUIRED')
    question['detail_start_ms']=max(question['start_ms'],min(starts+[question['detail_start_ms']])-250)
    if not 0 < question['detail_end_ms']-question['detail_start_ms'] <= 3000:
        raise ValueError('CONTINUOUS_DETAIL_BUDGET_EXCEEDED')
    question['selection_policy']='PRIOR_SOURCE_CITED_BUILDUP_THROUGH_UNRESOLVED_CONTACT'
    return question


def contact_focus(saved,source_hash):
    receipt=saved['receipt'] if 'receipt' in saved else saved
    if (saved['source_video_sha256']!=source_hash or receipt.get('origin')!='LIVE_MODEL_REQUEST' or
            receipt.get('status')!='COMPLETED' or
            hashlib.sha256(receipt['raw_response'].encode()).hexdigest()!=receipt['response_sha256']):
        raise ValueError('INVALID_FOCUS_RECEIPT')
    raw=json.loads(receipt['raw_response']);index=(raw.get('event_mapping') or {}).get('finish_chain_index')
    chain=raw.get('contact_chain',[])
    if type(index) is not int or not 0 <= index < len(chain):
        raise ValueError('SOURCE_CITED_FINISHING_BRACKET_REQUIRED')
    ids=[chain[index].get(k) for k in ('before_frame','after_frame')]
    if any(not isinstance(fid,str) or not re.fullmatch(r's\d{9}',fid) for fid in ids):
        raise ValueError('SOURCE_CITED_FINISHING_BRACKET_REQUIRED')
    lo,hi=[int(fid[1:]) for fid in ids]
    if not 0 < hi-lo <= 1000: raise ValueError('INVALID_FOCUS_BRACKET')
    return {'start_ms':lo-100,'end_ms':hi+100,'navigation_response_sha256':receipt['response_sha256']}


def geometry_cluster(samples,width,height,band):
    """Largest horizontal person cluster with generous margins, no identities."""
    crops=[]
    for sample in samples:
        # PersonDetector returns normalized TOP-LEFT x/y/width/height.
        boxes=sorted(sample['boxes_xywh_conf'],key=lambda b:b[0])
        groups=[]
        for b in boxes:
            left=b[0]
            if groups and (left-max(x[0]+x[2] for x in groups[-1]))*width <= .5*max(b[3],max(x[3] for x in groups[-1]))*height:
                groups[-1].append(b)
            else: groups.append([b])
        groups=[g for g in groups if len(g)>=2]
        if not groups: continue
        group=max(groups,key=len);margin=max(b[3] for b in group)*height
        crops.append([min(b[0] for b in group)*width-.75*margin,
            min(b[1] for b in group)*height-.3*margin,
            max(b[0]+b[2] for b in group)*width+.75*margin,
            max(b[1]+b[3] for b in group)*height+.3*margin])
    if not crops: raise ValueError('NO_SEPARATE_PERSON_CLUSTER_FOR_FOCUS')
    box=[max(band[0],math.floor(min(b[0] for b in crops))),
        max(band[1],math.floor(min(b[1] for b in crops))),
        min(band[2],math.ceil(max(b[2] for b in crops))),
        min(band[3],math.ceil(max(b[3] for b in crops)))]
    if box[2]-box[0]<2 or box[3]-box[1]<2 or box==band:
        raise ValueError('NO_NEW_SOURCE_FOCUS_VIEW')
    return box


def limb_region(centre,question,samples,width,height,band):
    if type(centre) is not int:
        raise ValueError('INTEGER_SOURCE_NAVIGATION_REQUIRED')
    lo,hi=centre-350,centre+350
    if not question['detail_start_ms'] <= lo < hi <= question['detail_end_ms']:
        raise ValueError('LIMB_WINDOW_OUTSIDE_SOURCE_DETAIL')
    nearby=[s for s in samples if abs(s['media_ms']-centre)<=350]
    body=geometry_cluster(nearby,width,height,band)
    feet=[body[0],round(body[1]+.45*(body[3]-body[1])),body[2],body[3]]
    if feet[3]-feet[1]<2:raise ValueError('EMPTY_LOWER_BODY_SOURCE_REGION')
    return {'centre_ms':centre,'start_ms':lo,'end_ms':hi,'source_crop_box':feet,
        'body_source_crop_box':body,'navigation_origin':'USER_SUPPLIED_TIMESTAMP_ONLY',
        'expected_action_or_side_supplied':False}


def comparison_panels(frames,limb,output,quality):
    """Stack four native-pixel instants; labels live outside unchanged crops."""
    import cv2
    import numpy as np
    chosen=[(ms,pixels) for ms,pixels in frames if limb['start_ms'] <= ms <= limb['end_ms']][::2]
    rows=[];audit=[];box=limb['source_crop_box']
    for start in range(0,len(chosen)-3,4):
        group=chosen[start:start+4];cells=[]
        for ms,pixels in group:
            crop=pixels[box[1]:box[3],box[0]:box[2]]
            cell=cv2.copyMakeBorder(crop,22,0,0,0,cv2.BORDER_CONSTANT,value=(0,0,0))
            cv2.putText(cell,f's{ms:09} / source_ms={ms}',(6,16),cv2.FONT_HERSHEY_SIMPLEX,.42,(255,255,255),1)
            cells.append(cell)
        panel=np.concatenate(cells,axis=0)
        if max(panel.shape[:2])>1280:raise ValueError('COMPARISON_PANEL_WOULD_RESIZE_SOURCE_PIXELS')
        image=p._save_image(Path(output)/f'comparison-{start//4:02}.jpg',panel,1280,quality)
        instants=[ms for ms,_ in group]
        rows.extend([{'type':'text','text':'Synchronized lower-body comparison, TOP TO BOTTOM: '+
            json.dumps([f's{ms:09}' for ms in instants])+'. Original source pixels; labels outside each crop. No interpolated motion or new person/event annotation.'},
            {'type':'image','path':image['path'],'sha256':image['sha256']}])
        audit.append({'source_instants':instants,'source_crop_box':box,'sha256':image['sha256'],
                      'native_pixels_not_resized':True,'labels_outside_source_crop':True})
    if not audit:raise ValueError('INSUFFICIENT_NATIVE_COMPARISON_FRAMES')
    return rows,audit


def prepare(manifest_path,gap_path,output,*,focus_receipt=None,limb_focus_ms=None,limb_panels=False):
    import cv2
    from cv_detect import PersonDetector
    started=time.monotonic();output=Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('OUTPUT_MUST_BE_NEW_OR_EMPTY')
    manifest,saved=(p.read_json(path) for path in (manifest_path,gap_path))
    source_hash=p.digest(manifest['source_video'])
    if any(d['source_video_sha256']!=source_hash for d in (manifest,saved)):
        raise ValueError('SOURCE_INPUT_MISMATCH')
    question=source_question(saved)
    refs=temporal_references(manifest['references'],question['start_ms'],question['end_ms'])
    cv2.setNumThreads(2)
    detector=PersonDetector(enabled=True)
    if not detector.ok:
        raise ValueError('LOCAL_PERSON_DETECTOR_UNAVAILABLE')
    cap=cv2.VideoCapture(manifest['source_video'])
    width,height=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.set(cv2.CAP_PROP_POS_MSEC,max(0,question['detail_start_ms']-50))
    frames,samples,next_detect=[],[],question['detail_start_ms']
    try:
        while time.monotonic()-started < 25:
            ok,pixels=cap.read()
            if not ok: break
            ms=round(cap.get(cv2.CAP_PROP_POS_MSEC))
            if ms > question['detail_end_ms']: break
            if ms < question['detail_start_ms']: continue
            frames.append((ms,pixels))
            if ms >= next_detect:
                samples.append({'media_ms':ms,'boxes_xywh_conf':detector.detect(pixels)})
                next_detect=ms+250
        else:
            raise TimeoutError('DETAIL_PREPARATION_BUDGET_EXCEEDED')
    finally:
        cap.release()
    times=[ms for ms,_ in frames]
    validate_native_coverage(times,[{'start_ms':question['detail_start_ms'],'end_ms':question['detail_end_ms']}])
    box=viewing_band([s['boxes_xywh_conf'] for s in samples],width,height)
    limb=limb_region(limb_focus_ms,question,samples,width,height,box) if limb_focus_ms is not None else None
    if limb_panels and not limb:raise ValueError('COMPARISON_REQUIRES_LIMB_NAVIGATION')
    focus=None
    if focus_receipt:
        focus=contact_focus(p.read_json(focus_receipt),source_hash)
        if not question['detail_start_ms'] <= focus['start_ms'] < focus['end_ms'] <= question['detail_end_ms']:
            raise ValueError('FOCUS_OUTSIDE_PREPARED_SOURCE_DETAIL')
        centre=(focus['start_ms']+focus['end_ms'])/2
        nearby=[s for s in samples if abs(s['media_ms']-centre)<=300]
        focus['source_crop_box']=geometry_cluster(nearby,width,height,box)
    prefix=[{'type':'text','text':PROMPT+'\n'+LINK_INSTRUCTION+'\n'+MAPPING_INSTRUCTION+'\n'+ONE_TOUCH_INSTRUCTION}]
    if focus:
        prefix[0]['text']+='\nSome contact images now use a tighter native-pixel viewing region containing the largest person cluster. Geometry chooses only the view, never an identity or action. The unchanged whole-play overview and surrounding full-width detail retain context. Compare each visible player\'s separate head, torso, limbs and body movement before and after overlap. Test both same-person continuity and a possible distinct teammate: do not assume either. A running/following motion alone is not a uniquely established strike. Keep the actor unresolved if another player remains a plausible finisher.'
    if limb:
        prefix[0]['text']+='\n'+LIMB_INSTRUCTION
    if limb_panels:
        prefix[0]['text']+='\nThe additional comparison panels show consecutive lower-body instants simultaneously. An occluded hip/knee at the instant of contact does NOT by itself make ownership uncertain: positive boot/sock appearance and movement before/after, anatomical reach and the independently accounted alternative legs can uniquely support ownership. An uninterrupted visible hip-to-knee-to-boot chain at every instant is not required. Conversely, counting remaining unseen legs alone is insufficient. State exactly which observed motion supports the owner and which alternatives are excluded; retain uncertainty if another foot is still physically plausible. These criteria apply equally to any player and kicking side.'
    for ref in refs:
        prefix.extend([{'type':'text','text':'IDENTITY ONLY: original selection '+ref['reference_id']+
            ', source_ms='+str(ref['media_ms'])+'. It is outside this play unless its instant lies inside the play bounds.'},
            {'type':'image','path':ref['path'],'sha256':ref['sha256']}])
    spatial,spatial_audit=spatial_reference_items(manifest,{'core_start_ms':question['start_ms']},refs,output/'identity-context')
    prefix.extend(spatial)
    overview=[]
    for frame in manifest['frames']:
        if question['start_ms'] <= frame['media_ms'] <= question['end_ms']:
            image=p._save_image(output/'overview'/(frame['frame_id']+'.jpg'),cv2.imread(frame['path']),768,70)
            overview.append((frame['media_ms'],'whole-play overview',image))
    chosen=None
    for quality in (85,80,75,70):
        detail=[]
        for ms,pixels in frames:
            crop=focus['source_crop_box'] if focus and focus['start_ms'] <= ms <= focus['end_ms'] else box
            label='native continuous detail; source crop='+json.dumps(crop)
            detail.append((ms,label,p._save_image(output/f'detail-q{quality}'/f's{ms:09}.jpg',
                pixels[crop[1]:crop[3],crop[0]:crop[2]],1280,quality)))
            if limb and limb['start_ms'] <= ms <= limb['end_ms']:
                foot=limb['source_crop_box']
                detail.append((ms,'synchronized lower-body view; source crop='+json.dumps(foot),
                    p._save_image(output/f'limb-q{quality}'/f's{ms:09}.jpg',
                        pixels[foot[1]:foot[3],foot[0]:foot[2]],1280,quality)))
        items=list(prefix)
        for ms,label,image in sorted(overview+detail,key=lambda r:(r[0],r[1])):
            items.extend([{'type':'text','text':f'Source frame s{ms:09}; source_ms={ms}; {label}'},
                {'type':'image','path':image['path'],'sha256':image['sha256']}])
        panels=[]
        if limb_panels:
            extra,panels=comparison_panels(frames,limb,output/f'comparison-q{quality}',quality)
            items.extend(extra)
        try:
            _,_,audit=t.build_request('emergent','gpt-6-astra',items,reasoning_effort='medium',image_detail='high')
        except ValueError as exc:
            if str(exc)!='REQUEST_IMAGE_BUDGET_EXCEEDED': raise
            continue
        chosen=(quality,items,audit);break
    if chosen is None: raise ValueError('REQUEST_IMAGE_BUDGET_EXCEEDED')
    quality,items,audit=chosen
    result={'status':'PREPARED_UNANCHORED_PLAY','source_video_sha256':source_hash,
        'original_taps_sha256':manifest['original_taps_sha256'],
        'source_start_ms':question['start_ms'],'source_end_ms':question['end_ms'],
        'question':question,'navigation_response_sha256':saved['receipt']['response_sha256'],
        'identity_reference_ids':[r['reference_id'] for r in refs],
        'identity_policy':'IN_PLAY_OR_NEAREST_BRACKETING_RAW_SELECTIONS_WITH_500MS_NEIGHBOURS',
        'in_play_original_selection_count':sum(question['start_ms'] <= r['media_ms'] <= question['end_ms'] for r in refs),
        'identity_source_audit':spatial_audit,'source_crop_box':box,'detector_samples':samples,
        'contact_focus':focus,
        'limb_focus':limb,
        'limb_comparison_panels':panels,
        'retained_overview_instants':[ms for ms,_,_ in overview],'retained_native_instants':times,
        'new_bridge_instants':[],'detail_jpeg_quality':quality,'max_detail_gap_ms':max(b-a for a,b in zip(times,times[1:])),
        'request_audit':audit,'preparation_seconds':round(time.monotonic()-started,3),
        'production_pipeline_changed':False,'expected_answers_used_as_input':False,
        'historical_action_wording_sent':False,'target_events':[],'counts':{},
        'independent_visual_correctness_verified':False}
    p.write_json(output/'result.json',result)
    return result,{'packet_id':'unanchored_play','items':items,'reasoning_effort':'medium','image_detail':'high'},started


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    for key in ('prepared','gap-receipt','output'):cli.add_argument('--'+key,required=True)
    cli.add_argument('--prepare-only',action='store_true')
    cli.add_argument('--focus-receipt')
    cli.add_argument('--limb-focus-ms',type=int)
    cli.add_argument('--limb-panels',action='store_true')
    args=cli.parse_args();result,job,started=prepare(args.prepared,args.gap_receipt,args.output,focus_receipt=args.focus_receipt,limb_focus_ms=args.limb_focus_ms,limb_panels=args.limb_panels)
    if not args.prepare_only:
        receipt=t.run_jobs([job],'emergent','gpt-6-astra',deadline=started+(150 if result['limb_focus'] else 120),
            per_call_s=120 if result['limb_focus'] else 90,workers=1)[0]
        p.write_json(Path(args.output)/'responses/unanchored_play.json',receipt)
        result.update(status=receipt['status'],probe_seconds=round(time.monotonic()-started,3))
        if receipt['status']=='COMPLETED':
            observed=json.loads(receipt['raw_response']);result['raw_observations']=observed
            result['automatic_approval']=resolve_assist(observed,result,
                {**receipt,'source_video_sha256':result['source_video_sha256']})
            result['target_events']=result['automatic_approval']['target_events']
            result['counts']=result['automatic_approval']['counts']
        p.write_json(Path(args.output)/'result.json',result)
        raise SystemExit(0 if receipt['status']=='COMPLETED' else 3)
