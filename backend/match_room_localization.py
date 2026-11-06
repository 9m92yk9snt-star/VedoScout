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


def bounded_request_runner(run_jobs, maximum):
    """Cap newly submitted jobs across primary AND supplemental batches.

    Reserve before transport: an interrupted call may already have been paid.
    This caps submitted jobs, not retries internal to the existing transport.
    """
    if type(maximum) is not int or maximum < 0:
        raise ValueError('INVALID_GRAPHICS_REQUEST_LIMIT')
    submitted = 0
    def run(jobs, *args, **kwargs):
        nonlocal submitted
        if submitted+len(jobs) > maximum:
            raise ValueError('NEW_GRAPHICS_REQUEST_LIMIT_EXCEEDED')
        submitted += len(jobs)
        return run_jobs(jobs, *args, **kwargs)
    return run


def prepare(video, selection, event, work, reference_images=None, *, window=None):
    """Bounded source window including duel recovery in existing clip context."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    proof = event['proof']
    start, end, context = position_window(event)
    pid = packet_id(event)
    if window is not None:
        start, end = window
        if (type(start) is not int or type(end) is not int
                or not proof['proof_start_ms'] <= start <= end <= proof['proof_end_ms']
                or end-start > 2500):
            raise ValueError('LOCALIZATION_COMPLETION_WINDOW_INVALID')
        context = 0
        pid += f'_coverage_{start}_{end}'
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
    record = {'version': 2, 'event_id': event['event_id'], 'packet_id': pid,
              'source_video_sha256': event['source_video_sha256'],
              'original_selection_values_sha256': selection_digest(selection),
              'frames': frames, 'references': references, 'request': request,
              'window_ms': [start, end], 'context_after_ms': context}
    job = {'packet_id': pid, 'items': items, 'reasoning_effort': 'medium',
           'image_detail': 'high', 'max_output_tokens': 10000}
    return record, job


def completion_windows(event, record):
    """Unobserved clip edges only, retaining the existing 125ms cadence.

    UNCERTAIN/ABSENT rows inside a completed request are not missing work.
    Limit extra work to two windows per event; report any remaining gap.
    """
    frames = record.get('frames') or []
    if not frames:
        return []
    lo, hi = record.get('window_ms') or [frames[0]['media_ms'], frames[-1]['media_ms']]
    proof = event['proof']
    ranges = []
    if proof['proof_start_ms'] < lo:
        ranges.append((proof['proof_start_ms'], max(proof['proof_start_ms'], lo-125)))
    if hi < proof['proof_end_ms']:
        ranges.append((min(hi+125, proof['proof_end_ms']), proof['proof_end_ms']))
    windows = []
    for start, end in ranges:
        while start <= end and len(windows) < 2:
            stop = min(start+2500, end)
            windows.append([start, stop])
            if stop == end:
                break
            start = min(stop+125, end)
    return windows


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
    previous_audit = doc.get('match_room_localization') or {}
    previous = previous_audit.get('events') or {}
    same_context = (previous_audit.get('source_video_sha256') == bundle['source_video_sha256']
                    and previous_audit.get('original_selection_values_sha256') == selection_digest(selection))
    audit = {'version': 2, 'source_video_sha256': bundle['source_video_sha256'],
             'original_selection_values_sha256': selection_digest(selection),
             'events': deepcopy(previous) if same_context else {}}
    loop = asyncio.get_running_loop()
    jobs, records, by_packet = [], {}, {}
    reference_images = None
    with tempfile.TemporaryDirectory(prefix='matchroom-positions-') as work:
        for event in candidates:
            eid = event['event_id']
            if time.monotonic()-started >= budget_seconds:
                audit['events'][eid] = {**deepcopy(previous.get(eid) or {}),
                    'status': 'NOT_SENT', 'error': 'LOCALIZATION_TIME_BUDGET'}
                continue
            try:
                if reference_images is None:
                    record, job = await asyncio.to_thread(prepare, video, selection, event, Path(work)/eid)
                    reference_images = record.get('references')
                else:
                    record, job = await asyncio.to_thread(prepare, video, selection, event, Path(work)/eid, reference_images)
            except (ValueError, OSError, cv2.error):
                audit['events'][eid] = {**deepcopy(previous.get(eid) or {}),
                    'status': 'UNAVAILABLE', 'error': 'LOCALIZATION_PREFLIGHT_FAILED'}
                continue
            records[eid], by_packet[packet_id(event)] = record, event
            old = previous.get(eid) or {}
            # Keep paid supplementary receipts through the initial checkpoint.
            # Each is revalidated against a freshly rebuilt request below.
            record['completion'] = deepcopy(old.get('completion') or {})
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
        # Complete clip edges without changing the original request/cache key.
        # Existing uncertain rows are preserved, never retried to obtain a
        # more convenient identity. Supplemental jobs share the same deadline.
        extra_jobs, extra_records = [], {}
        for event in candidates:
            eid = event['event_id']
            record = records.get(eid)
            if not record or record.get('status') != 'OBSERVATIONS_RETURNED':
                continue
            for window in completion_windows(event, record):
                pid = packet_id(event)+f'_coverage_{window[0]}_{window[1]}'
                if time.monotonic()-started >= budget_seconds:
                    record['completion_error'] = 'LOCALIZATION_TIME_BUDGET'
                    break
                try:
                    extra, job = await asyncio.to_thread(prepare, video, selection, event,
                        Path(work)/pid, reference_images, window=window)
                except (ValueError, OSError, cv2.error):
                    record['completion_error'] = 'LOCALIZATION_PREFLIGHT_FAILED'
                    continue
                cached = (record['completion'].get(pid) or {}).get('receipt') or {}
                extra['reused'] = reusable_receipt(cached, extra['request'],
                    provider='emergent', model='gpt-6-astra', packet_id=pid)
                if extra['reused']:
                    extra['receipt'] = deepcopy(cached)
                else:
                    extra_jobs.append(job)
                record['completion'][pid] = extra
                extra_records[pid] = (event, record, extra)
        def accept_extra(receipt):
            event, record, extra = extra_records[receipt['packet_id']]
            extra.update(receipt=deepcopy(receipt), status='UNAVAILABLE')
            if receipt.get('status') == 'COMPLETED':
                try:
                    rows = bound_samples(event, selection, extra, validate, packet=receipt['packet_id'])
                    if any(not extra['window_ms'][0]-50 <= r['media_ms'] <= extra['window_ms'][1]+50 for r in rows):
                        raise ValueError('LOCALIZATION_COMPLETION_OUTSIDE_WINDOW')
                    # Never silently resolve conflicting low-frame-rate
                    # observations in favour of either request.
                    merged = {r['media_ms']: r for r in event['visual_samples']}
                    if any(r['media_ms'] in merged and merged[r['media_ms']] != r for r in rows):
                        raise ValueError('LOCALIZATION_COMPLETION_OVERLAP')
                    for row in rows:
                        merged.setdefault(row['media_ms'], row)
                    event['visual_samples'] = sorted(merged.values(), key=lambda r:r['media_ms'])
                    extra['status'] = 'OBSERVATIONS_RETURNED'
                    extra.pop('error', None)
                except ValueError:
                    extra['error'] = 'LOCALIZATION_OBSERVATIONS_REJECTED'
            else:
                extra['error'] = receipt.get('error', 'LOCALIZATION_MODEL_FAILED')
            audit['events'][event['event_id']] = deepcopy(record)
        for event, record, extra in extra_records.values():
            if extra['reused']:
                accept_extra(extra['receipt'])
            audit['events'][event['event_id']] = deepcopy(record)
        await checkpoint(deepcopy(audit))
        def finished_extra(receipt):
            accept_extra(receipt)
            asyncio.run_coroutine_threadsafe(checkpoint(deepcopy(audit)), loop).result()
        if extra_jobs:
            results = await asyncio.to_thread(run_jobs, extra_jobs, 'emergent', 'gpt-6-astra',
                deadline=started+budget_seconds, per_call_s=150, workers=2, on_result=finished_extra)
            for receipt in results:
                accept_extra(receipt)
        for event in candidates:
            record = records.get(event['event_id'])
            if record:
                times = [s['media_ms'] for s in event.get('visual_samples') or []]
                record['coverage'] = {
                    'required_window_ms': [event['proof']['proof_start_ms'], event['proof']['proof_end_ms']],
                    'returned_span_ms': [min(times), max(times)] if times else None,
                    'clip_edges_observed': bool(times and min(times) <= event['proof']['proof_start_ms']+50
                                               and max(times) >= event['proof']['proof_end_ms']-50)}
                audit['events'][event['event_id']] = deepcopy(record)
    audit['elapsed_seconds'] = round(time.monotonic()-started, 3)
    await checkpoint(deepcopy(audit))
    return bundle
