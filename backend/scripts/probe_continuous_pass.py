"""One complete local play, adding dense images in the pass-to-finish gap.

Prior request hashes are verified before modifying input. Historical observations
choose only the missing source interval; they are never supplied as model facts.
Typed source observations feed the existing automatic assist resolver.
"""
import argparse
from copy import deepcopy
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

MAPPING_INSTRUCTION = '''Also return "event_mapping" so the observed chain can be
read by the event resolver. Use zero-based indexes into YOUR contact_chain array:
{"pass_chain_index":null,"receive_chain_index":null,"finish_chain_index":null,
 "receiver_is_teammate":null,"same_active_ball":null,"continuous_play":null,
 "pass_actor_unique":null,"finishing_actor_unique":null,"goal_frame":null}.
Use integers only for uniquely supported chain rows, true/false/null for the five
boolean fields, and a supplied source frame ID for goal_frame only when the moving
active ball is established inside the goal. Otherwise leave the relevant fields
null. The receive index identifies reception before the finishing action; do not
confuse a separate teammate, a defender or a further pass with that receiver.
Uniqueness means the attacking actor is established by the before/after movement;
it does not assert an exact visible foot-ball pixel or exclude every slight brush.
Keep source brackets and uncertainty in contact_chain. Describe the actual result
even when a pass, finish, goal or their connection is unsupported. This mapping is
not an instruction to approve an event or to select a particular outcome.
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


def resolve_assist(observed, context, receipt):
    """Translate typed source observations through the existing event resolver.

    No natural-language keyword matching, jersey numbers, expected timestamps or
    target counts choose the actors or action rows. Missing typed evidence stops
    approval. An attacking contact bracket does not invent an exact last touch.
    """
    result = {'status':'UNRESOLVED','reasons':[], 'target_events':[], 'counts':{},
              'independent_visual_correctness_verified':False}
    def stop(reason):
        result['reasons'].append(reason)
        return result
    times = sum((context.get(k,[]) for k in
        ('retained_overview_instants','retained_native_instants','new_bridge_instants')), [])
    lo,hi = context.get('source_start_ms'),context.get('source_end_ms')
    if (type(lo) is not int or type(hi) is not int or not 0 <= lo < hi or not times or
            any(type(ms) is not int or not lo <= ms <= hi for ms in times)):
        return stop('INVALID_SOURCE_CATALOG')
    source_hash=context.get('source_video_sha256','')
    if (not isinstance(source_hash,str) or not re.fullmatch(r'[a-f0-9]{64}',source_hash) or
            receipt.get('source_video_sha256')!=source_hash):
        return stop('SOURCE_INPUT_MISMATCH')
    raw=receipt.get('raw_response')
    payload_hash=(context.get('request_audit') or {}).get('payload_sha256')
    if (receipt.get('status')!='COMPLETED' or receipt.get('origin')!='LIVE_MODEL_REQUEST' or
            not isinstance(raw,str) or not isinstance(payload_hash,str) or
            not re.fullmatch(r'[a-f0-9]{64}',payload_hash) or receipt.get('payload_sha256')!=payload_hash or
            hashlib.sha256(raw.encode()).hexdigest()!=receipt.get('response_sha256')):
        return stop('UNVERIFIED_MODEL_RECEIPT')
    try:
        if json.loads(raw)!=observed:
            return stop('OBSERVATIONS_DIFFER_FROM_RECEIPT')
    except (ValueError,TypeError):
        return stop('INVALID_MODEL_JSON')
    frame_times={f's{ms:09}':ms for ms in times}
    identity=p.assess_actor_identity(observed,context.get('identity_reference_ids',[]),frame_times)
    result['identity_review']=identity
    support=assess_link(observed,identity,frame_times)
    result['link_review']=support
    if support['status']!='ASSIST_SUPPORTED_BY_MODEL_OBSERVATIONS':
        return stop('PHYSICAL_LINK_NOT_ESTABLISHED')
    if context.get('limb_focus'):
        limb=observed.get('contact_ownership_review')
        window=context['limb_focus']
        if (not isinstance(limb,dict) or limb.get('status')!='SUPPORTED' or
                limb.get('release_actor')!=support['releaser'] or
                not isinstance(limb.get('anatomical_side'),str) or
                limb.get('anatomical_side') not in {'LEFT','RIGHT','UNKNOWN'}):
            return stop('RELEASE_LIMB_OWNERSHIP_UNRESOLVED')
        citations=limb.get('frames')
        if (not isinstance(citations,list) or not all(isinstance(f,str) for f in citations) or
                len(set(citations))<2 or any(f not in frame_times or
                    not window['start_ms'] <= frame_times[f] <= window['end_ms'] for f in citations) or
                not isinstance(limb.get('observation'),str) or not limb['observation'].strip()):
            return stop('MISSING_LIMB_SOURCE_EVIDENCE')
    mapping=observed.get('event_mapping')
    if not isinstance(mapping,dict):
        return stop('TYPED_EVENT_MAPPING_REQUIRED')
    for key in ('receiver_is_teammate','same_active_ball','continuous_play',
                'pass_actor_unique','finishing_actor_unique'):
        if mapping.get(key) is not True:
            return stop('UNRESOLVED_EVENT_MAPPING:'+key)
    if observed.get('questions'):
        return stop('EXPLICIT_MODEL_QUESTION_REMAINS')
    indexes=[mapping.get(k) for k in ('pass_chain_index','receive_chain_index','finish_chain_index')]
    chain=observed.get('contact_chain')
    if (not isinstance(chain,list) or any(type(i) is not int or not 0 <= i < len(chain) for i in indexes)
            or not indexes[0] < indexes[1] <= indexes[2]):
        return stop('INVALID_CONTACT_CHAIN_MAPPING')
    one_touch=indexes[1]==indexes[2]
    if one_touch != (mapping.get('one_touch_finish') is True):
        return stop('FIRST_TOUCH_FINISH_NOT_ESTABLISHED')
    rows=[chain[i] for i in indexes]
    def interval(row):
        if not isinstance(row,dict) or not isinstance(row.get('visible_evidence'),str) or not row['visible_evidence'].strip():
            return None
        before,after=(frame_times.get(row.get(k)) if isinstance(row.get(k),str) else None
                      for k in ('before_frame','after_frame'))
        return [before,after] if None not in (before,after) and 0 < after-before <= 1000 else None
    intervals=[interval(row) for row in rows]
    if any(i is None for i in intervals):
        return stop('MISSING_OR_INVALID_CONTACT_BRACKET')
    passing,receiving,finishing=rows
    release_i,receive_i,finish_i=intervals
    link=observed['link_assessment']
    passer,receiver,finisher=(link[k] for k in ('releaser','receiver','finisher'))
    if (passing.get('actor')!=passer or passing.get('recipient')!=receiver or
            receiving.get('actor')!=receiver or receiving.get('recipient') is not None or
            finishing.get('actor')!=finisher or finishing.get('recipient') is not None):
        return stop('CONTACT_ROLES_CONTRADICT_MAPPING')
    if (not release_i[1] <= receive_i[0] < receive_i[1] or
            (not one_touch and receive_i[1] > finish_i[0])):
        return stop('INVALID_PASS_RECEIVE_FINISH_ORDER')
    for row in chain[indexes[0]+1:indexes[2]]:
        if (interval(row) is None or row.get('actor')!=receiver or row.get('recipient') is not None or
                not release_i[1] <= interval(row)[0] <= interval(row)[1] <= finish_i[0]):
            return stop('INTERVENING_CHAIN_ACTION_UNRESOLVED')
    pass_frames=link['same_ball_release_to_receiver']['frames']
    finish_frames=link['receiver_finishing_action']['frames']
    if (not any(release_i[0] <= frame_times[f] <= release_i[1] for f in pass_frames) or
            not any(receive_i[0] <= frame_times[f] <= receive_i[1] for f in pass_frames) or
            sum(finish_i[0] <= frame_times[f] <= finish_i[1] for f in set(finish_frames))<2):
        return stop('LINK_CITATIONS_DO_NOT_SUPPORT_CONTACT_BRACKETS')
    outcome=observed['outcome']
    goal=mapping.get('goal_frame')
    goal_facts=link['goal_from_that_finish']
    outcome_frames=[]
    for fact in outcome.get('evidence',[]) if isinstance(outcome.get('evidence'),list) else [None]:
        if isinstance(fact,str) and fact in frame_times:
            outcome_frames.append(fact)
        elif (isinstance(fact,dict) and isinstance(fact.get('frame'),str) and fact['frame'] in frame_times
                and isinstance(fact.get('observation',fact.get('fact')),str)
                and fact.get('observation',fact.get('fact')).strip()):
            outcome_frames.append(fact['frame'])
        else:
            return stop('INVALID_GOAL_SOURCE_EVIDENCE')
    if (outcome.get('kind')!='GOAL' or not isinstance(goal,str) or goal not in frame_times or
            goal not in outcome_frames or
            goal not in goal_facts['frames'] or frame_times[goal] <= finish_i[1]):
        return stop('MOVING_BALL_GOAL_AFTER_FINISH_NOT_ESTABLISHED')
    packet_id=receipt.get('packet_id')
    if not isinstance(packet_id,str) or not packet_id:
        return stop('SOURCE_PACKET_REQUIRED')
    people=[{k:deepcopy(person[k]) for k in ('person_id','selected','reference_ids','evidence_frames')}
            for person in observed['players']]
    evidence=[{'frame':f,'fact':goal_facts['observation']} for f in goal_facts['frames']
              if frame_times[f]>=finish_i[1]]
    def action(row,kind,actor):
        return {'action_id':kind.lower(),'kind':kind,'actor':actor,
            'start_frame':row['before_frame'],'end_frame':goal,'contact_frame':None,
            'contact_before_frame':row['before_frame'],'contact_after_frame':row['after_frame'],
            'contact_actor_unique':True,'contact_evidence':[
                {'frame':row[k],'fact':row['visible_evidence']} for k in ('before_frame','after_frame')],
            'actor_evidence_frames':[row['before_frame'],row['after_frame']],
            'ball_id':'active:'+packet_id,'same_active_ball':True,'continuous_play':True,
            'outcome_frame':goal,'outcome_evidence':evidence,
            'details':row['visible_evidence']+' Remaining alternatives: '+str(row.get('remaining_alternatives') or '')}
    passing_action=action(passing,'PASS',passer)
    passing_action.update(outcome='TEAMMATE_GOAL',receiver=receiver,finisher=finisher,
        receiver_is_teammate=True,receiver_frame=receiving['after_frame'],shot_frame=None)
    finishing_action=action(finishing,'SHOT',finisher)
    finishing_action['outcome']='GOAL'
    normalized={'plays':[{'start_frame':min(frame_times,key=frame_times.get),
        'end_frame':max(frame_times,key=frame_times.get),'people':people,
        'actions':[passing_action,finishing_action],'questions':[]}]}
    manifest={'source_video_sha256':source_hash,
        'identity_profile':{'canonical_reference_ids':context['identity_reference_ids']},
        'frames':[{'frame_id':fid,'media_ms':ms} for fid,ms in sorted(frame_times.items())]}
    packet={'packet_id':packet_id,'phase':'INITIAL','frame_ids':list(frame_times),
            'reference_ids':context['identity_reference_ids']}
    citation={k:receipt[k] for k in ('packet_id','payload_sha256','response_sha256','origin')}
    resolved=p.resolve_response(normalized,manifest,packet,citation)
    merged=p.reconcile([resolved])
    result['normalized_observations']=normalized
    result['resolver_invalid_rows']=resolved['invalid_rows']
    if (resolved['invalid_rows'] or merged['questions'] or merged['conflicts'] or
            len(merged['target_events'])!=1 or merged['target_events'][0]['event_type']!='ASSIST'):
        return stop('EVENT_RESOLVER_DID_NOT_APPROVE_ASSIST')
    event=merged['target_events'][0]
    event.update(approval_status='APPROVED',receiver_interval_ms=receive_i,
        finishing_contact_interval_ms=finish_i,
        intervening_control=deepcopy(link['intervening_control']),
        defensive_contact=deepcopy(link['defensive_contact']),
        last_touch_actor=outcome.get('last_touch_actor'))
    if one_touch:
        event['one_touch_finish']=True
    result.update(merged,status='APPROVED',reason=event['reason'])
    return result


def prepare(manifest_path,gap_path,profile_path,profile_baseline,local_baseline,output,*,event_mapping=False):
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
    if event_mapping:
        prefix[0]['text']+='\n'+MAPPING_INSTRUCTION
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
    if event_mapping:
        result['comparison']['changed_settings'].append('typed_contact_chain_event_mapping')
    p.write_json(output/'result.json',result)
    return result,{'packet_id':'continuous_pass_link','items':items,'reasoning_effort':'medium','image_detail':'high'},started


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    for name in ('prepared','gap-receipt','resume-profile','profile-baseline','local-baseline','output'):
        cli.add_argument('--'+name,required=True)
    cli.add_argument('--prepare-only',action='store_true')
    cli.add_argument('--event-mapping',action='store_true')
    a=cli.parse_args();result,job,started=prepare(a.prepared,a.gap_receipt,a.resume_profile,a.profile_baseline,a.local_baseline,a.output,event_mapping=a.event_mapping)
    if not a.prepare_only:
        response=t.run_jobs([job],'emergent','gpt-6-astra',deadline=started+120,per_call_s=90,workers=1)[0]
        p.write_json(Path(a.output)/'responses/continuous_pass_link.json',response)
        result.update(status=response['status'],probe_seconds=round(time.monotonic()-started,3))
        if response['status']=='COMPLETED':
            observed=json.loads(response['raw_response']);result['raw_observations']=observed
            allowed={f's{ms:09}' for ms in result['retained_overview_instants']+result['retained_native_instants']+result['new_bridge_instants']}
            result['identity_review']=p.assess_actor_identity(observed,result['identity_reference_ids'],allowed)
            result['experimental_link_decision']=assess_link(observed,result['identity_review'],allowed)
            if a.event_mapping:
                result['automatic_approval']=resolve_assist(observed,result,
                    {**response,'source_video_sha256':result['source_video_sha256']})
                result['target_events']=result['automatic_approval']['target_events']
                result['counts']=result['automatic_approval']['counts']
        p.write_json(Path(a.output)/'result.json',result)
        raise SystemExit(0 if response['status']=='COMPLETED' else 3)
