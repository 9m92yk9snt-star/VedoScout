"""One source-grounded actor review with native-rate, detector-bounded detail.

The detector chooses a common viewing region only: no tracks, player identities,
ball identities or event decisions are inferred from its boxes. All source-play
overview instants remain in the request. Expected event answers are never read.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sequence_pilot as p
import sequence_pilot_transport as t
from scripts.probe_native_play import spatial_reference_items


def unresolved_gap(saved):
    receipt = saved['receipt']
    if (receipt.get('status') != 'COMPLETED' or receipt.get('origin') != 'LIVE_MODEL_REQUEST'
            or hashlib.sha256(receipt['raw_response'].encode()).hexdigest() != receipt['response_sha256']):
        raise ValueError('INVALID_PRIOR_OBSERVATION')
    raw = json.loads(receipt['raw_response'])
    outcome = raw.get('outcome', {})
    if (not outcome.get('uncertainty') or
            not str(outcome.get('last_touch_player', '')).lower().startswith('unknown')):
        raise ValueError('NO_UNRESOLVED_FINISHING_ACTOR')
    question = saved['question']
    if (question['packet_id'] != receipt['packet_id'] or
            not question['start_ms'] <= question['detail_start_ms'] < question['detail_end_ms'] <= question['end_ms']):
        raise ValueError('INVALID_CONTACT_INTERVAL')
    return question


def pass_finish_gap(saved):
    """Derive both detail windows from an actual observed pass/shot chain."""
    receipt = saved['receipt']
    if (receipt.get('status') != 'COMPLETED' or receipt.get('origin') != 'LIVE_MODEL_REQUEST'
            or hashlib.sha256(receipt['raw_response'].encode()).hexdigest() != receipt['response_sha256']):
        raise ValueError('INVALID_PRIOR_OBSERVATION')
    raw, q = json.loads(receipt['raw_response']), dict(saved['question'])
    if q['packet_id'] != receipt['packet_id']:
        raise ValueError('INVALID_CONTACT_INTERVAL')
    def instant(value):
        if not isinstance(value, str) or not re.fullmatch(r's\d{9}', value):
            raise ValueError('EXACT_OBSERVED_SOURCE_FRAME_REQUIRED')
        return int(value[1:])
    chain = raw.get('ball_contact_chain', [])
    passes = [a for a in chain if a.get('type') == 'pass']
    if len(passes) != 1:
        raise ValueError('ONE_OBSERVED_PASS_REQUIRED')
    passing = passes[0]
    shots = [a for a in chain if a.get('type') == 'shot' and
             instant(a.get('before_frame')) > instant(passing.get('after_frame'))]
    if len(shots) != 1 or not any(a.get('uncertainty') for a in chain):
        raise ValueError('ONE_UNRESOLVED_PASS_FINISH_CHAIN_REQUIRED')
    windows = []
    for role, action in (('release', passing), ('finish', shots[0])):
        lo, hi = instant(action.get('before_frame')), instant(action.get('after_frame'))
        if not q['start_ms'] <= lo <= hi <= q['end_ms']:
            raise ValueError('OBSERVED_CONTACT_OUTSIDE_SOURCE_PLAY')
        windows.append({'start_ms':max(q['start_ms'],lo-250),
                        'end_ms':min(q['end_ms'],hi+250),'role':role})
    if windows[0]['end_ms'] >= windows[1]['start_ms']:
        raise ValueError('DISTINCT_CONTACT_WINDOWS_REQUIRED')
    if sum(w['end_ms']-w['start_ms'] for w in windows) > 3000:
        raise ValueError('CONTACT_DETAIL_BUDGET_EXCEEDED')
    q.update(reason='OBSERVED_PASS_RECEIVE_FINISH_LINK', detail_windows=windows,
             detail_start_ms=windows[0]['start_ms'],detail_end_ms=windows[-1]['end_ms'],
             selection_policy='PRIOR_SOURCE_CITED_PASS_AND_LATER_SHOT_NOT_REFERENCE_ANSWERS')
    return q


def validate_native_coverage(times, windows):
    """Missing the later finish must fail, even when the pass is fully covered."""
    if times != sorted(set(times)):
        raise ValueError('NATIVE_CONTACT_COVERAGE_INCOMPLETE')
    for window in windows:
        points = [ms for ms in times if window['start_ms'] <= ms <= window['end_ms']]
        if (len(points) < 2 or points[0]-window['start_ms'] > 35 or
                window['end_ms']-points[-1] > 35 or max(b-a for a,b in zip(points,points[1:])) > 35):
            raise ValueError('NATIVE_CONTACT_COVERAGE_INCOMPLETE')


def viewing_band(rows, width, height):
    """Union all detected people, with body-height margins; no target choice."""
    boxes = [box for row in rows for box in row]
    if not boxes:
        raise ValueError('NO_PERSON_GEOMETRY_FOR_DETAIL')
    if any(not all(math.isfinite(float(v)) for v in b[:4]) or b[2] <= 0 or b[3] <= 0 for b in boxes):
        raise ValueError('INVALID_PERSON_GEOMETRY')
    top = max(0., min(b[1] - b[3]*.5 for b in boxes))
    bottom = min(1., max(b[1] + b[3]*1.5 for b in boxes))
    y0, y1 = max(0, int(top*height)), min(height, math.ceil(bottom*height))
    if y1-y0 < 2:
        raise ValueError('EMPTY_DETAIL_BAND')
    return [0, y0, width, y1]


def verify_baseline(items, saved, source_hash):
    old = saved['receipt']
    if (saved['source_video_sha256'] != source_hash or old['origin'] != 'LIVE_MODEL_REQUEST' or
            old['status'] != 'COMPLETED' or old['requested_model'] not in {'gemini-3.8-flash','gpt-6-astra'} or
            hashlib.sha256(old['raw_response'].encode()).hexdigest() != old['response_sha256']):
        raise ValueError('INVALID_COMPARISON_BASELINE')
    _, _, before = t.build_request('emergent',old['requested_model'],items,
        reasoning_effort=old.get('requested_reasoning_effort','low'),image_detail='high')
    if before['payload_sha256'] != old['payload_sha256']:
        raise ValueError('COMPARISON_INPUT_NOT_IDENTICAL')
    return {'origin_run':saved['origin_run'],'baseline_payload_sha256':old['payload_sha256'],
            'messages_images_and_source_instants_unchanged':True,
            'changed_settings':[]}


def reference_ids_for_play(manifest, local, scope):
    if scope == 'local':
        if not local:
            raise ValueError('ORIGINAL_IN_PLAY_SELECTION_REQUIRED')
        return [r['reference_id'] for r in local]
    if scope != 'profile':
        raise ValueError('INVALID_IDENTITY_SCOPE')
    return list(dict.fromkeys(manifest['identity_profile']['canonical_reference_ids']+
                              [r['reference_id'] for r in local]))


def prepare(manifest_path, gap_path, profile_path, output, *, link_mode='finisher',
            model='gemini-3.8-flash', reasoning='low', comparison_baseline=None,identity_scope='profile'):
    import cv2
    from cv_detect import PersonDetector
    started, output = time.monotonic(), Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('OUTPUT_MUST_BE_NEW_OR_EMPTY')
    if model not in {'gemini-3.8-flash','gpt-6-astra'} or reasoning not in {'low','medium'}:
        raise ValueError('UNREVIEWED_PROBE_SETTINGS')
    if model == 'gpt-6-astra' and comparison_baseline is None:
        raise ValueError('ALTERNATE_MODEL_REQUIRES_MEASURED_BASELINE')
    manifest, gap, profile = (p.read_json(x) for x in (manifest_path, gap_path, profile_path))
    if link_mode not in {'finisher','pass-finish'}:
        raise ValueError('INVALID_LINK_MODE')
    q = pass_finish_gap(gap) if link_mode == 'pass-finish' else unresolved_gap(gap)
    windows = q.get('detail_windows', [{'start_ms':q['detail_start_ms'],'end_ms':q['detail_end_ms']}])
    source_hash = p.digest(manifest['source_video'])
    if any(x['source_video_sha256'] != source_hash for x in (manifest, gap, profile)):
        raise ValueError('SOURCE_INPUT_MISMATCH')
    receipt = profile['receipt']
    if (receipt['status'] != 'COMPLETED' or receipt['origin'] != 'LIVE_MODEL_REQUEST' or
            hashlib.sha256(receipt['raw_response'].encode()).hexdigest() != receipt['response_sha256'] or
            sorted(i['sha256'] for i in receipt['images']) != sorted(r['sha256'] for r in manifest['references'])):
        raise ValueError('IDENTITY_PROFILE_UNRESOLVED')
    manifest = p.apply_identity_profile(manifest, json.loads(receipt['raw_response']))
    cv2.setNumThreads(2)
    detector = PersonDetector(enabled=True)
    if not detector.ok:
        raise ValueError('LOCAL_PERSON_DETECTOR_UNAVAILABLE')
    cap = cv2.VideoCapture(manifest['source_video'])
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0, q['detail_start_ms']-50))
    frames, samples, next_detect = [], [], q['detail_start_ms']
    try:
        while time.monotonic()-started < 25:
            ok, pixels = cap.read()
            if not ok:
                break
            ms = round(cap.get(cv2.CAP_PROP_POS_MSEC))
            if ms > q['detail_end_ms']:
                break
            if ms < q['detail_start_ms']:
                continue
            if not any(w['start_ms'] <= ms <= w['end_ms'] for w in windows):
                continue
            frames.append((ms, pixels))
            if ms >= next_detect:
                boxes = detector.detect(pixels)
                samples.append({'media_ms': ms, 'boxes_xywh_conf': boxes})
                next_detect = ms+250
        else:
            raise TimeoutError('DETAIL_PREPARATION_BUDGET_EXCEEDED')
    finally:
        cap.release()
    times = [ms for ms, _ in frames]
    validate_native_coverage(times, windows)
    box = viewing_band([s['boxes_xywh_conf'] for s in samples], width, height)
    items = [{'type':'text','text':
        'Read this one complete football play and the new original-source contact detail. '
        'Identify the selected physical person from the original identity references. '
        'Follow each visible white player before and after the contact, keeping people separate. '
        'Determine who releases the active ball, who next touches it and who finishes. '
        'A foot-ball instant may be hidden: cite visible before/after body and ball movement, '
        'and state whether the actor is uniquely determined or alternatives remain. '
        'Do not invent intervening possession or touches. A detector chose only a common '
        'viewing band containing all detected people: it supplies no identities or contact facts. '
        'Full-play overviews remain available outside that band. Native detail is every decoded '
        'source instant in the unresolved interval, with original source times. '
        'reference_ids must list only POSITIVE same-person matches to the original identity '
        'examples; put negative comparisons in appearance. evidence_frames must list supplied '
        'source frames showing that physical person. A player positively matching a selected '
        'identity example cannot simultaneously be selected=false. If examples appear to match '
        'different physical players, keep identity unresolved rather than choosing between them. '
        'Do not infer identity from a jersey number which is not readable. No expected actions, '
        'times, count or outcomes are provided. Do not force a verdict if hidden. '
        'Return JSON {"players":[{"person_id":"p1","selected":null,"appearance":"visible features",'
        '"reference_ids":["r1"],"evidence_frames":["s..."]}],"contact_chain":[{"actor":"p1","kind":"observed action",'
        '"before_frame":"s...","after_frame":"s...","recipient":null,'
        '"visible_evidence":"before/after movement","remaining_alternatives":"unresolved or empty"}],'
        '"outcome":{"kind":"observed result or UNKNOWN","last_touch_actor":null,'
        '"evidence":["s..."],"uncertainty":"unresolved or empty"}}.'}]
    refs = {r['reference_id']:r for r in manifest['references']}
    local = [r for r in refs.values() if q['start_ms'] <= r['media_ms'] <= q['end_ms']]
    profile_ids = reference_ids_for_play(manifest,local,'profile')
    ids = reference_ids_for_play(manifest,local,identity_scope)
    def reference_parts(ref_ids):
        return [part for rid in ref_ids for part in
            ({'type':'text','text':'Original identity example '+rid},
             {'type':'image','path':refs[rid]['path'],'sha256':refs[rid]['sha256']})]
    prefix = items[:]
    items.extend(reference_parts(ids))
    context_start = len(items)
    spatial, _ = spatial_reference_items(manifest, {'core_start_ms':q['start_ms']}, local, output/'spatial')
    items.extend(spatial)
    rows = []
    for f in manifest['frames']:
        if q['start_ms'] <= f['media_ms'] <= q['end_ms']:
            image = f
            if link_mode == 'pass-finish':
                image = {'frame_id':f['frame_id'], **p._save_image(output/'overview'/(f['frame_id']+'.jpg'),
                    cv2.imread(f['path']),768,70)}
            rows.append((f['media_ms'],'full-play overview',image))
    for ms, pixels in frames:
        im = p._save_image(output/'detail'/f's{ms:09}.jpg', pixels[box[1]:box[3]], 1280, 85)
        rows.append((ms, 'native contact detail', {'frame_id':f's{ms:09}', **im}))
    for ms, label, im in sorted(rows, key=lambda row:(row[0],row[1])):
        items.extend([{'type':'text','text':f"Source frame {im['frame_id']}; source_ms={ms}; {label}"},
                      {'type':'image','path':im['path'],'sha256':im['sha256']}])
    comparison = None
    if comparison_baseline:
        baseline = p.read_json(comparison_baseline)
        # Reproduce the prior full input before removing any out-of-play references.
        comparison_items = prefix+reference_parts(profile_ids)+items[context_start:]
        comparison = verify_baseline(comparison_items,baseline,source_hash)
        old = baseline['receipt']
        changes = []
        if model != old['requested_model']:
            changes += ['model','provider_completion_budget_parameter']
        if reasoning != old.get('requested_reasoning_effort','low'):
            changes.append('reasoning_effort')
        if ids != profile_ids:
            changes.append('identity_reference_scope')
        comparison.update(changed_settings=changes,
            messages_images_and_source_instants_unchanged=ids==profile_ids,
            source_play_images_and_timestamps_unchanged=True,
            removed_out_of_play_reference_ids=[rid for rid in profile_ids if rid not in ids])
    _, _, audit = t.build_request('emergent', model, items, reasoning_effort=reasoning, image_detail='high')
    result = {'status':'PREPARED_ACTOR_CONTINUITY_PROBE','origin_run':gap['origin_run'],
        'link_mode':link_mode,
        'model':model,'reasoning_effort':reasoning,'comparison':comparison,
        'identity_scope':identity_scope,
        'identity_reference_ids':ids,
        'prior_response_sha256':gap['receipt']['response_sha256'],'source_video_sha256':source_hash,
        'question':q, 'source_crop_box':box,'detector_source_sha256':detector.model_sha256,
        'detector_samples':samples,'detector_forwards':len(samples),'native_source_instants':times,
        'full_play_overview_instants':[ms for ms,label,_ in rows if label == 'full-play overview'],
        'request_audit':audit,'source_preparation_seconds':round(time.monotonic()-started,3),
        'production_pipeline_changed':False,'expected_answers_used_as_input':False,
        'independent_visual_correctness_verified':False,'target_events':[]}
    p.write_json(output/'result.json', result)
    return result, {'packet_id':'unresolved_actor','items':items,'reasoning_effort':reasoning,'image_detail':'high'}, started


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ('prepared','gap-receipt','resume-profile','output'):
        cli.add_argument('--'+name, required=True)
    cli.add_argument('--prepare-only', action='store_true')
    cli.add_argument('--link-mode', choices=['finisher','pass-finish'], default='finisher')
    cli.add_argument('--model',choices=['gemini-3.8-flash','gpt-6-astra'],default='gemini-3.8-flash')
    cli.add_argument('--reasoning',choices=['low','medium'],default='low')
    cli.add_argument('--comparison-baseline')
    cli.add_argument('--identity-scope',choices=['profile','local'],default='profile')
    a = cli.parse_args()
    result, job, started = prepare(a.prepared, a.gap_receipt, a.resume_profile, a.output,link_mode=a.link_mode,
        model=a.model,reasoning=a.reasoning,comparison_baseline=a.comparison_baseline,identity_scope=a.identity_scope)
    if not a.prepare_only:
        response = t.run_jobs([job],'emergent',a.model,deadline=started+(120 if a.model=='gpt-6-astra' else 90),
            per_call_s=90 if a.model=='gpt-6-astra' else 45,workers=1)[0]
        p.write_json(Path(a.output)/'responses/unresolved_actor.json',response)
        result.update(status=response['status'],probe_seconds=round(time.monotonic()-started,3))
        if response['status'] == 'COMPLETED':
            result['raw_observations'] = json.loads(response['raw_response'])
            result['identity_review'] = p.assess_actor_identity(result['raw_observations'],
                result['identity_reference_ids'], [f's{ms:09}' for ms in
                    result['native_source_instants']+result['full_play_overview_instants']])
        p.write_json(Path(a.output)/'result.json',result)
        raise SystemExit(0 if response['status'] == 'COMPLETED' else 3)

