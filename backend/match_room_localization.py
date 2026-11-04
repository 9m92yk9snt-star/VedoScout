"""Bounded presentation-only perception from the original video and ALL user taps.

No action findings, expected directions or reviewed coordinates enter requests.
Completed receipts are checkpointed before clip encoding, and replayed only for
an identical source, selection, event window and freshly rebuilt request.
"""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time

import cv2
import sequence_pilot as pilot
import sequence_pilot_transport as transport
from match_room_position_evidence import selection_digest, bound_samples
from match_room import position_window
from sequence_run_checkpoint import reusable_receipt
from video_timebase import read_frame_at, read_frames_at

PROMPT = '''Locate the SAME physical player selected by the original human point in the reference image. Reference images identify a person, not an action. Use ALL original human reference images to establish the same requested player. Reference timestamps may span cuts. A reference point that misses a visible person is not positive identity evidence; do not move that point onto a neighbour. Use the timeline to test continuity and competing identities. These context images contain no extra selections. If a cut, disappearance or competing appearance prevents re-identification, keep identity uncertain; never assume the next highlighted player is the target. Output rows only for TIMELINE images. Examine the full timeline independently; never transfer identity to a nearby teammate, recipient or scorer. A jersey number alone, proximity to the ball or the expected role is insufficient when conflicting people are visible.
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



def packet_id(event):
    return 'positions_' + event['event_id']


def prepare(video, selection, event, work, reference_images=None):
    """Bounded source window including duel recovery in existing clip context."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    proof = event['proof']
    start, end, context = position_window(event)
    cap = cv2.VideoCapture(str(video))
    items = [{'type': 'text', 'text': PROMPT}]
    references, frames = [], []
    def image(ms, name, quality=75, decoded=None):
        if decoded is None:
            ok, pixels, actual = read_frame_at(cap, ms/1000)
        else:
            actual_ms, pixels = decoded
            ok, actual = True, actual_ms / 1000
        if not ok:
            raise ValueError('LOCALIZATION_SOURCE_FRAME_UNAVAILABLE')
        scale = min(1, 1920/max(pixels.shape[:2]))
        if scale < 1:
            pixels = cv2.resize(pixels, (round(pixels.shape[1]*scale), round(pixels.shape[0]*scale)), interpolation=cv2.INTER_AREA)
        path = work/(name+'.jpg')
        if not cv2.imwrite(str(path), pixels, [cv2.IMWRITE_JPEG_QUALITY, quality]):
            raise ValueError('LOCALIZATION_SOURCE_FRAME_WRITE_FAILED')
        return {'frame_id': f's{round(actual*1000):09}', 'media_ms': round(actual*1000),
                'path': str(path), 'sha256': pilot.digest(path)}
    try:
        taps = pilot.original_taps(selection)
        if reference_images is not None and (len(reference_images) != len(taps) or any(
                any(saved.get(k) != tap[k] for k in ('reference_id', 'requested_ms', 'box', 'target_point', 'selection_hints'))
                for tap, saved in zip(taps, reference_images))):
            raise ValueError('LOCALIZATION_REFERENCE_CACHE_CHANGED')
        for i, tap in enumerate(taps):
            f = deepcopy(reference_images[i]) if reference_images is not None else image(tap['requested_ms'], tap['reference_id'], 85)
            references.append({**f, **tap})
            items.extend([{'type': 'text', 'text': 'ORIGINAL HUMAN IDENTITY REFERENCE '+json.dumps({
                'frame': f['frame_id'], 'reference_id': tap['reference_id'],
                'point': tap['target_point'], 'box': tap['box'], 'selection_hints': tap['selection_hints']})},
                {'type': 'image', 'path': f['path'], 'sha256': f['sha256']}])
        times = sorted(set(range(start, end+1, 125)) | {end} |
                       {t for t in proof['cited_frames'].values() if start <= t <= end})
        seen = set()
        decoded = {}
        for i, ms in enumerate(times):
            # Bound retained pixels to eight frames while sharing forward decoding.
            if i % 8 == 0:
                decoded.clear()
                decoded = read_frames_at(cap, times[i:i+8])
            frame = decoded.pop(ms, None)
            if frame is None:
                raise ValueError('LOCALIZATION_SOURCE_FRAME_UNAVAILABLE')
            f = image(ms, f'timeline-{i}', decoded=frame)
            del frame
            if f['frame_id'] in seen:
                continue
            seen.add(f['frame_id'])
            frames.append(f)
            items.extend([{'type': 'text', 'text': 'TIMELINE '+json.dumps({
                'frame': f['frame_id'], 'media_ms': f['media_ms']})},
                {'type': 'image', 'path': f['path'], 'sha256': f['sha256']}])
    finally:
        cap.release()
    _, _, request = transport.build_request('emergent', 'gpt-6-astra', items,
        reasoning_effort='medium', image_detail='high', max_output_tokens=10000)
    record = {'version': 2, 'event_id': event['event_id'], 'packet_id': packet_id(event),
              'source_video_sha256': event['source_video_sha256'],
              'original_selection_values_sha256': selection_digest(selection),
              'frames': frames, 'references': references, 'request': request,
              'window_ms': [start, end], 'context_after_ms': context}
    job = {'packet_id': packet_id(event), 'items': items, 'reasoning_effort': 'medium',
           'image_detail': 'high', 'max_output_tokens': 10000}
    return record, job


async def localize(video, doc, *, checkpoint, event_ids=None, run_jobs=None, budget_seconds=420):
    """Observe presentation positions without changing canonical event identity.

    Missing/uncertain measurements suppress graphics, not the factual report.
    Source/model errors are explicit in the persisted per-event audit.
    """
    started = time.monotonic()
    run_jobs = run_jobs or transport.run_jobs
    bundle = deepcopy(doc['canonical_events'])
    if await asyncio.to_thread(pilot.digest, Path(video)) != bundle['source_video_sha256']:
        raise ValueError('LOCALIZATION_SOURCE_CHANGED')
    raw = doc['raw_marker_anchors']
    while isinstance(raw, str):
        raw = json.loads(raw)
    selection = {'raw_marker_anchors': raw}
    pilot.original_taps(selection)
    chosen = set(event_ids if event_ids is not None else
                 [r['event_id'] for r in doc['full_report']['video_comments']])
    candidates = [e for e in bundle['events'] if e['event_id'] in chosen and not e.get('visual_samples')][:8]
    previous = (doc.get('match_room_localization') or {}).get('events') or {}
    audit = {'version': 2, 'source_video_sha256': bundle['source_video_sha256'],
             'original_selection_values_sha256': selection_digest(selection), 'events': {}}
    loop = asyncio.get_running_loop()
    jobs, records, by_packet = [], {}, {}
    reference_images = None
    with tempfile.TemporaryDirectory(prefix='matchroom-positions-') as work:
        for event in candidates:
            eid = event['event_id']
            if time.monotonic()-started >= budget_seconds:
                audit['events'][eid] = {'status': 'NOT_SENT', 'error': 'LOCALIZATION_TIME_BUDGET'}
                continue
            try:
                if reference_images is None:
                    record, job = await asyncio.to_thread(prepare, video, selection, event, Path(work)/eid)
                    reference_images = record.get('references')
                else:
                    record, job = await asyncio.to_thread(prepare, video, selection, event, Path(work)/eid, reference_images)
            except (ValueError, OSError, cv2.error):
                audit['events'][eid] = {'status': 'UNAVAILABLE', 'error': 'LOCALIZATION_PREFLIGHT_FAILED'}
                continue
            records[eid], by_packet[packet_id(event)] = record, event
            old = previous.get(eid) or {}
            cached = old.get('receipt') or {}
            if reusable_receipt(cached, record['request'], provider='emergent',
                                model='gpt-6-astra', packet_id=packet_id(event)):
                record.update(receipt=deepcopy(cached), reused=True)
            else:
                record['reused'] = False
                jobs.append(job)
        def accept(receipt):
            event = by_packet[receipt['packet_id']]
            eid = event['event_id']
            record = records[eid]
            record.update(receipt=deepcopy(receipt), status='UNAVAILABLE')
            if receipt.get('status') == 'COMPLETED':
                try:
                    samples = bound_samples(event, selection, record, validate, packet=packet_id(event))
                    event['visual_samples'] = samples
                    event['localization_method'] = 'EXPLICIT_SOURCE_POSITIONS'
                    if record.get('context_after_ms') == 750:
                        event['graphics_context_ms'] = 750
                    record['status'] = 'OBSERVATIONS_RETURNED'
                    record.pop('error', None)
                except ValueError:
                    record['error'] = 'LOCALIZATION_OBSERVATIONS_REJECTED'
            else:
                record['error'] = receipt.get('error', 'LOCALIZATION_MODEL_FAILED')
            audit['events'][eid] = deepcopy(record)
        for record in records.values():
            if record['reused']:
                accept(record['receipt'])
        await checkpoint(deepcopy(audit))
        def finished(receipt):
            accept(receipt)
            # The transport invokes callbacks sequentially on its owned thread.
            # Persist every completed paid result before the next callback.
            asyncio.run_coroutine_threadsafe(checkpoint(deepcopy(audit)), loop).result()
        if jobs:
            results = await asyncio.to_thread(run_jobs, jobs, 'emergent', 'gpt-6-astra',
                deadline=started+budget_seconds, per_call_s=150, workers=2, on_result=finished)
            for receipt in results:
                accept(receipt)
    audit['elapsed_seconds'] = round(time.monotonic()-started, 3)
    await checkpoint(deepcopy(audit))
    return bundle
