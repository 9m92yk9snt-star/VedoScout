"""Continue a nearby original tap into an action using source observations.

One real tap remains the identity anchor. Every observed ground point must
resolve uniquely, independently track back to that tap, and agree with its
forward path. Source observations are not represented as extra human taps.
"""
import math
import time

from match_room_contours import (read_clip, detect_frame, measured_mask, follow,
                                follow_instance, agrees_with_observation)
from player_selection import valid_box, valid_point

METHOD = 'TAP_OBSERVATION_BOUND_CONTOUR'


def validate_path(frames, detections, seed_index, anchor, observations, start, end):
    """Return a complete proof path, or reject it without selecting substitutes."""
    if not frames or frames[-1]['media_ms'] < end-35:
        return None
    path = follow(frames, detections, seed_index, anchor['target_point'])
    proof = [i for i, f in enumerate(frames) if start <= f['media_ms'] <= end]
    if (len(proof) < 5 or frames[proof[0]]['media_ms'] > start+35
            or any(i not in path or detections[i][path[i]]['ground'] is None for i in proof)):
        return None
    checked, overlap = [], []
    for observed in observations:
        i = min(proof, key=lambda k: abs(frames[k]['media_ms']-observed['media_ms']))
        if abs(frames[i]['media_ms']-observed['media_ms']) > 2:
            return None
        owners = [k for k, row in enumerate(detections[i])
                  if row['ground'] is not None and agrees_with_observation(row, observed, frames[i]['gray'].shape)]
        if len(owners) != 1 or path[i] != owners[0]:
            return None
        reverse = follow_instance(frames, detections, i, owners[0])
        shared = sorted(set(path) & set(reverse))
        if (reverse.get(seed_index) != path.get(seed_index) or seed_index not in reverse
                or any(path[k] != reverse[k] for k in shared)
                or not any(shared[j:j+5] == list(range(shared[j], shared[j]+5)) for j in range(max(0, len(shared)-4)))):
            return None
        checked.append(observed['frame_id'])
        overlap.append(len(shared))
    if len(set(checked)) < 2:
        return None
    return {'path': path, 'proof': proof, 'reference_frames': checked, 'overlap_frames': min(overlap)}


def anchor_observation_segments(video, anchors, observations, start, end, *, deadline, diagnostics):
    from match_room_tracking import finite, point, foreground_polygons
    from native_player_segmentation import PersonSegmenter
    diagnostics['status'] = 'UNSUPPORTED_INPUT'
    observed = [s for s in observations if point(s.get('ground')) and finite(s.get('media_ms'))
                and start <= s['media_ms'] <= end and isinstance(s.get('frame_id'), str)
                and finite(s.get('player_width')) and .005 <= s['player_width'] <= .4]
    seeds = [a for a in anchors if finite(a.get('t')) and start-750 <= a['t']*1000 < start
             and valid_box(a.get('box')) and valid_point(a.get('target_point')) and not a.get('player_behind')]
    if (not 0 < end-start <= 2000 or len(observed) < 2 or not seeds
            or max(s['media_ms'] for s in observed)-min(s['media_ms'] for s in observed) < 200):
        return []
    # Use the closest actual selection once. Failure never tries another person.
    seeds.sort(key=lambda s: s['t'], reverse=True)
    if len(seeds) > 1 and abs(seeds[0]['t']-seeds[1]['t']) < .025:
        return []
    seed = seeds[0]
    if end-seed['t']*1000 > 2500 or time.monotonic() >= deadline-1:
        return []
    model = PersonSegmenter()
    frames, detections, roi = [], [], None
    stream = read_clip(video, round(seed['t']*1000)-1, end, sample_step=0)
    try:
        for frame in stream:
            if time.monotonic() >= deadline-1:
                diagnostics['status'] = 'TIME_BUDGET'
                return []
            if roi is None:
                height, width = frame['gray'].shape
                box = seed['box']
                roi = (0, max(0, int((box['y']-.7*box['h'])*height)), width,
                       min(height, math.ceil((box['y']+1.7*box['h'])*height)))
            detections.append(detect_frame(frame, roi, model))
            frame.pop('image')
            frames.append(frame)
    finally:
        stream.close()
    if not frames or abs(frames[0]['media_ms']-seed['t']*1000) > 25:
        diagnostics['status'] = 'SOURCE_FRAME_UNAVAILABLE'
        return []
    result = validate_path(frames, detections, 0, seed, observed, start, end)
    if result is None:
        diagnostics['status'] = 'UNSUPPORTED_CONTINUITY'
        return []
    samples = []
    for i in result['proof']:
        if time.monotonic() >= deadline-1:
            diagnostics['status'] = 'TIME_BUDGET'
            return []
        row = detections[i][result['path'][i]]
        height, width = frames[i]['gray'].shape
        polygons = foreground_polygons([{'class_id': 0, 'mask': measured_mask(d)} for d in detections[i]], width, height)
        if not polygons:
            diagnostics['status'] = 'FOREGROUND_UNAVAILABLE'
            return []
        ms = frames[i]['media_ms']
        fid = f'stance-source:{ms}'
        samples.append({'media_ms': ms, 'frame_id': fid, 'ground': row['ground'],
                        'player_width': row['player_width'], 'confidence': row['confidence'],
                        'foreground': {'method': 'SOURCE_PERSON_MASK', 'frame_id': fid,
                                       'media_ms': ms, 'polygons': polygons}})
    diagnostics.update(status='SUPPORTED_TAP_OBSERVATIONS', method=METHOD,
                       seed_ms=frames[0]['media_ms'], checked_observations=len(result['reference_frames']),
                       overlap_frames=result['overlap_frames'], source_frames=len(frames))
    return [{'id': 'tap-observation:0', 'reference_frame': result['reference_frames'][0],
             'observation_reference_frames': result['reference_frames'], 'seed_ms': [frames[0]['media_ms']],
             'overlap_frames': result['overlap_frames'], 'ground_method': 'LOWER_VISIBLE_CONTOUR',
             'source_frame_coverage': 'COMPLETE', 'samples': samples}]
