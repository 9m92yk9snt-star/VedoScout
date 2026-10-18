"""Read one unresolved play using nearest original selections and continuous detail.

The previous reply supplies source navigation only. Neither its action wording
nor reference answers are included in the new request. The existing assist
resolver owns approval; a completed model request does not imply approval.
"""
import argparse
import hashlib
import json
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


def prepare(manifest_path,gap_path,output):
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
    prefix=[{'type':'text','text':PROMPT+'\n'+LINK_INSTRUCTION+'\n'+MAPPING_INSTRUCTION+'\n'+ONE_TOUCH_INSTRUCTION}]
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
        detail=[(ms,'native continuous detail',p._save_image(output/f'detail-q{quality}'/f's{ms:09}.jpg',
            pixels[box[1]:box[3]],1280,quality)) for ms,pixels in frames]
        items=list(prefix)
        for ms,label,image in sorted(overview+detail,key=lambda r:(r[0],r[1])):
            items.extend([{'type':'text','text':f'Source frame s{ms:09}; source_ms={ms}; {label}'},
                {'type':'image','path':image['path'],'sha256':image['sha256']}])
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
    args=cli.parse_args();result,job,started=prepare(args.prepared,args.gap_receipt,args.output)
    if not args.prepare_only:
        receipt=t.run_jobs([job],'emergent','gpt-6-astra',deadline=started+120,per_call_s=90,workers=1)[0]
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
