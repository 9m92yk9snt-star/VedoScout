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


def prepare(manifest_path, gap_path, profile_path, output):
    import cv2
    from cv_detect import PersonDetector
    started, output = time.monotonic(), Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('OUTPUT_MUST_BE_NEW_OR_EMPTY')
    manifest, gap, profile = (p.read_json(x) for x in (manifest_path, gap_path, profile_path))
    q = unresolved_gap(gap)
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
    if (len(times) < 2 or times[0]-q['detail_start_ms'] > 35 or q['detail_end_ms']-times[-1] > 35 or
            max(b-a for a,b in zip(times,times[1:])) > 35 or times != sorted(set(times))):
        raise ValueError('NATIVE_CONTACT_COVERAGE_INCOMPLETE')
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
    ids = list(dict.fromkeys(manifest['identity_profile']['canonical_reference_ids']+[r['reference_id'] for r in local]))
    for rid in ids:
        r = refs[rid]
        items.extend([{'type':'text','text':'Original identity example '+rid},
                      {'type':'image','path':r['path'],'sha256':r['sha256']}])
    spatial, _ = spatial_reference_items(manifest, {'core_start_ms':q['start_ms']}, local, output/'spatial')
    items.extend(spatial)
    rows = [(f['media_ms'], 'full-play overview', f) for f in manifest['frames']
            if q['start_ms'] <= f['media_ms'] <= q['end_ms']]
    for ms, pixels in frames:
        im = p._save_image(output/'detail'/f's{ms:09}.jpg', pixels[box[1]:box[3]], 1280, 85)
        rows.append((ms, 'native contact detail', {'frame_id':f's{ms:09}', **im}))
    for ms, label, im in sorted(rows, key=lambda row:(row[0],row[1])):
        items.extend([{'type':'text','text':f"Source frame {im['frame_id']}; source_ms={ms}; {label}"},
                      {'type':'image','path':im['path'],'sha256':im['sha256']}])
    model = 'gemini-3.8-flash'
    _, _, audit = t.build_request('emergent', model, items, reasoning_effort='low', image_detail='high')
    result = {'status':'PREPARED_ACTOR_CONTINUITY_PROBE','origin_run':gap['origin_run'],
        'identity_reference_ids':ids,
        'prior_response_sha256':gap['receipt']['response_sha256'],'source_video_sha256':source_hash,
        'question':q, 'source_crop_box':box,'detector_source_sha256':detector.model_sha256,
        'detector_samples':samples,'detector_forwards':len(samples),'native_source_instants':times,
        'full_play_overview_instants':[ms for ms,label,_ in rows if label == 'full-play overview'],
        'request_audit':audit,'source_preparation_seconds':round(time.monotonic()-started,3),
        'production_pipeline_changed':False,'expected_answers_used_as_input':False,
        'independent_visual_correctness_verified':False,'target_events':[]}
    p.write_json(output/'result.json', result)
    return result, {'packet_id':'unresolved_actor','items':items,'reasoning_effort':'low','image_detail':'high'}, started


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ('prepared','gap-receipt','resume-profile','output'):
        cli.add_argument('--'+name, required=True)
    cli.add_argument('--prepare-only', action='store_true')
    a = cli.parse_args()
    result, job, started = prepare(a.prepared, a.gap_receipt, a.resume_profile, a.output)
    if not a.prepare_only:
        response = t.run_jobs([job],'emergent','gemini-3.8-flash',deadline=started+90,per_call_s=45,workers=1)[0]
        p.write_json(Path(a.output)/'responses/unresolved_actor.json',response)
        result.update(status=response['status'],probe_seconds=round(time.monotonic()-started,3))
        if response['status'] == 'COMPLETED':
            result['raw_observations'] = json.loads(response['raw_response'])
            result['identity_review'] = p.assess_actor_identity(result['raw_observations'],
                result['identity_reference_ids'], [f's{ms:09}' for ms in
                    result['native_source_instants']+result['full_play_overview_instants']])
        p.write_json(Path(a.output)/'result.json',result)
        raise SystemExit(0 if response['status'] == 'COMPLETED' else 3)

