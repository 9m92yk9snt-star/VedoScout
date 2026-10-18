"""One complete local play, adding dense images in the pass-to-finish gap.

Prior request hashes are verified before modifying input. Historical observations
choose only the missing source interval; they are never supplied as model facts.
An experimental supported-assist decision remains separate from visual review.
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
from scripts.probe_actor_continuity import prepare as prepare_contacts, verify_baseline


LINK_INSTRUCTION = '''Assess the physical connection in this complete play. Extra
native-pixel images now cover the interval between the earlier release and the
later finishing movement. Identify the actual recipient from the moving ball and
body continuity. An attempted interception or proximity is not an observed touch.
Distinguish a touch from controlled possession or a deliberate intervening pass.
A merely hypothetical touch is not evidence of an interruption. Conversely, do
not assert an unobserved connection: use UNCERTAIN when the supplied motion does
not support the link. A finishing attacker can be identified from a unique short
before/after movement even if the exact foot-ball pixel is obscured; distinguish
that attacking action from an unresolved slight defensive last touch. Report the
observed result, including an unsuccessful result if that is what is visible.
No desired action type, count, outcome or expected event times are supplied.
Keep the existing players/contact_chain/outcome JSON and ADD "link_assessment":
{"releaser":"person ID or null","receiver":"person ID or null",
 "finisher":"person ID or null",
 "same_ball_release_to_receiver":{"status":"SUPPORTED|CONTRADICTED|UNCERTAIN",
 "frames":["s...","s..."],"observation":"concrete visible motion"},
 "receiver_finishing_action":{"status":"SUPPORTED|CONTRADICTED|UNCERTAIN",
 "frames":["s...","s..."],"observation":"concrete before/after movement"},
 "goal_from_that_finish":{"status":"SUPPORTED|CONTRADICTED|UNCERTAIN",
 "frames":["s...","s..."],"observation":"moving active-ball evidence"},
 "intervening_control":{"status":"OBSERVED|NOT_OBSERVED|UNCERTAIN",
 "frames":["s...","s..."],"observation":"control or deliberate intervening pass evidence"},
 "defensive_contact":{"status":"OBSERVED|NOT_OBSERVED|UNCERTAIN",
 "frames":["s...","s..."],"observation":"actual contact evidence or why unresolved"}}.
NOT_OBSERVED control alone cannot establish a pass connection: the separate
same-ball and recipient-finishing links require affirmative motion evidence.
For each field cite supplied source IDs, not identity-example IDs. Do not list
every frame: cite the few decisive before/after instants and retain uncertainty.
'''


def assess_link(observed, identity_review, allowed_frames):
    """Review explicit model observations; never turn missing links into proof."""
    result = {'status':'UNRESOLVED','reasons':[],
        'independent_visual_correctness_verified':False,'target_events':[]}
    if identity_review.get('status') != 'STRUCTURALLY_CONSISTENT':
        result['reasons'].append('IDENTITY_UNRESOLVED'); return result
    if not isinstance(observed,dict):
        result['reasons'].append('INVALID_OBSERVATION_OBJECT'); return result
    outcome=observed.get('outcome',{})
    kind=outcome.get('kind','') if isinstance(outcome,dict) else ''
    if not isinstance(kind,str) or not re.match(r'^GOAL(?:$|[\s:.,])',kind.upper()):
        result['reasons'].append('GOAL_OUTCOME_NOT_ESTABLISHED'); return result
    link = observed.get('link_assessment')
    if not isinstance(link,dict):
        result['reasons'].append('MISSING_LINK_OBSERVATIONS'); return result
    people = {x.get('person_id'):x for x in observed.get('players',[]) if isinstance(x,dict)}
    selected = [pid for pid,person in people.items() if person.get('selected') is True]
    if (len(selected)!=1 or link.get('releaser')!=selected[0] or
            link.get('receiver') not in people or link.get('finisher')!=link.get('receiver') or
            link['receiver']==selected[0] or people[link['receiver']].get('selected') is not False):
        result['reasons'].append('PASSER_RECIPIENT_FINISHER_NOT_ESTABLISHED'); return result
    for name in ('same_ball_release_to_receiver','receiver_finishing_action','goal_from_that_finish',
                 'intervening_control','defensive_contact'):
        field = link.get(name,{})
        if not isinstance(field,dict):
            result['reasons'].append('MISSING_OR_INVALID_SOURCE_EVIDENCE:'+name); continue
        frames = field.get('frames')
        if (not isinstance(frames,list) or not all(isinstance(f,str) for f in frames) or len(set(frames))<2 or
                any(f not in allowed_frames for f in frames) or
                not isinstance(field.get('observation'),str) or not field['observation'].strip()):
            result['reasons'].append('MISSING_OR_INVALID_SOURCE_EVIDENCE:'+name)
    if result['reasons']: return result
    if link['intervening_control'].get('status')=='OBSERVED':
        result.update(status='NO_DIRECT_ASSIST',reasons=['INTERVENING_CONTROL_OR_DELIBERATE_PASS_OBSERVED']); return result
    for name in ('same_ball_release_to_receiver','receiver_finishing_action','goal_from_that_finish'):
        if link[name].get('status')!='SUPPORTED':
            result['reasons'].append('LINK_NOT_SUPPORTED:'+name)
    if link['intervening_control'].get('status')!='NOT_OBSERVED':
        result['reasons'].append('INTERVENING_CONTROL_UNRESOLVED')
    if link['defensive_contact'].get('status') not in {'OBSERVED','NOT_OBSERVED','UNCERTAIN'}:
        result['reasons'].append('INVALID_CONTACT_OBSERVATION')
    if not result['reasons']:
        result.update(status='ASSIST_SUPPORTED_BY_MODEL_OBSERVATIONS',
            releaser=link['releaser'],finisher=link['finisher'])
    return result


def prepare(manifest_path,gap_path,profile_path,profile_baseline,local_baseline,output):
    import cv2
    started, output = time.monotonic(),Path(output)
    if output.exists() and any(output.iterdir()): raise ValueError('OUTPUT_MUST_BE_NEW_OR_EMPTY')
    base,job,_ = prepare_contacts(manifest_path,gap_path,profile_path,output/'baseline',
        link_mode='pass-finish',model='gpt-6-astra',reasoning='medium',
        comparison_baseline=profile_baseline,identity_scope='local')
    saved = p.read_json(local_baseline)
    previous = {**saved,'source_video_sha256':saved['result']['source_video_sha256']}
    comparison = verify_baseline(job['items'],previous,base['source_video_sha256'])
    windows = base['question']['detail_windows']
    if len(windows)!=2: raise ValueError('ONE_PASS_FINISH_GAP_REQUIRED')
    lo,hi = windows[0]['end_ms'],windows[1]['start_ms']
    if not 0 < hi-lo <= 1500: raise ValueError('BRIDGE_SOURCE_BUDGET_EXCEEDED')
    manifest = p.read_json(manifest_path)
    cap = cv2.VideoCapture(manifest['source_video'])
    cap.set(cv2.CAP_PROP_POS_MSEC,max(0,lo-50))
    x0,y0,x1,y1 = base['source_crop_box']
    frames,next_ms = [],lo+1
    try:
        while time.monotonic()-started < 30:
            ok,pixels = cap.read()
            if not ok: break
            ms = round(cap.get(cv2.CAP_PROP_POS_MSEC))
            if ms>=hi: break
            if ms<next_ms: continue
            frames.append((ms,pixels[y0:y1,x0:x1].copy()))
            while next_ms<=ms: next_ms+=1000/24
        else: raise TimeoutError('BRIDGE_PREPARATION_BUDGET_EXCEEDED')
    finally: cap.release()
    detail_times=sorted(set(base['native_source_instants']+[ms for ms,_ in frames]))
    if not frames or max(b-a for a,b in zip(detail_times,detail_times[1:]))>50:
        raise ValueError('CONTINUOUS_DETAIL_COVERAGE_INCOMPLETE')
    original=job['items']
    first=next(i for i,item in enumerate(original) if item['type']=='text' and item['text'].startswith('Source frame '))
    rows=[]
    for i in range(first,len(original),2):
        label,image=original[i:i+2]
        match=re.search(r'source_ms=(\d+)',label['text'])
        if not match: raise ValueError('SOURCE_INSTANT_REQUIRED')
        rows.append((int(match[1]),label['text'],[label,image]))
    prefix=[dict(item) for item in original[:first]]
    prefix[0]={'type':'text','text':prefix[0]['text']+'\n'+LINK_INSTRUCTION}
    chosen=None
    for quality in (85,80,75,70):
        extra=[]
        for ms,pixels in frames:
            image=p._save_image(output/f'bridge-q{quality}'/f's{ms:09}.jpg',pixels,1280,quality)
            label={'type':'text','text':f'Source frame s{ms:09}; source_ms={ms}; native continuous-bridge detail'}
            extra.append((ms,label['text'],[label,{'type':'image','path':image['path'],'sha256':image['sha256']}]))
        items=prefix+[part for _,_,pair in sorted(rows+extra,key=lambda row:(row[0],row[1])) for part in pair]
        try:
            _,_,audit=t.build_request('emergent','gpt-6-astra',items,reasoning_effort='medium',image_detail='high')
        except ValueError as exc:
            if str(exc)!='REQUEST_IMAGE_BUDGET_EXCEEDED': raise
            continue
        chosen=(quality,items,audit);break
    if chosen is None: raise ValueError('REQUEST_IMAGE_BUDGET_EXCEEDED')
    quality,items,audit=chosen
    original_images=[i['sha256'] for i in original if i['type']=='image']
    final_images=[i['sha256'] for i in items if i['type']=='image']
    if any(h not in final_images for h in original_images): raise ValueError('ORIGINAL_SOURCE_IMAGE_REMOVED')
    result={'status':'PREPARED_CONTINUOUS_PASS_PROBE','source_video_sha256':base['source_video_sha256'],
        'source_start_ms':base['question']['start_ms'],'source_end_ms':base['question']['end_ms'],
        'identity_reference_ids':base['identity_reference_ids'],'source_crop_box':base['source_crop_box'],
        'comparison':comparison,'retained_overview_instants':base['full_play_overview_instants'],
        'retained_native_instants':base['native_source_instants'],'new_bridge_instants':[ms for ms,_ in frames],
        'bridge_jpeg_quality':quality,'max_detail_gap_ms':max(b-a for a,b in zip(detail_times,detail_times[1:])),
        'original_image_hashes_retained':True,'request_audit':audit,
        'preparation_seconds':round(time.monotonic()-started,3),'production_pipeline_changed':False,
        'expected_answers_used_as_input':False,'independent_visual_correctness_verified':False,'target_events':[]}
    result['comparison'].update(messages_images_and_source_instants_unchanged=False,
        changed_settings=['added_continuous_bridge_images','explicit_neutral_link_observation_schema'])
    p.write_json(output/'result.json',result)
    return result,{'packet_id':'continuous_pass_link','items':items,'reasoning_effort':'medium','image_detail':'high'},started


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    for name in ('prepared','gap-receipt','resume-profile','profile-baseline','local-baseline','output'):
        cli.add_argument('--'+name,required=True)
    cli.add_argument('--prepare-only',action='store_true')
    a=cli.parse_args();result,job,started=prepare(a.prepared,a.gap_receipt,a.resume_profile,a.profile_baseline,a.local_baseline,a.output)
    if not a.prepare_only:
        response=t.run_jobs([job],'emergent','gpt-6-astra',deadline=started+120,per_call_s=90,workers=1)[0]
        p.write_json(Path(a.output)/'responses/continuous_pass_link.json',response)
        result.update(status=response['status'],probe_seconds=round(time.monotonic()-started,3))
        if response['status']=='COMPLETED':
            observed=json.loads(response['raw_response']);result['raw_observations']=observed
            allowed={f's{ms:09}' for ms in result['retained_overview_instants']+result['retained_native_instants']+result['new_bridge_instants']}
            result['identity_review']=p.assess_actor_identity(observed,result['identity_reference_ids'],allowed)
            result['experimental_link_decision']=assess_link(observed,result['identity_review'],allowed)
        p.write_json(Path(a.output)/'result.json',result)
        raise SystemExit(0 if response['status']=='COMPLETED' else 3)
