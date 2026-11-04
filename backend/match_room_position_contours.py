"""Local contour agreement between independently localized source observations.

Call only after binding model receipts with match_room_position_evidence.
These seeds are model observations, never original human selections. Nothing
is drawn across an uncertain identity, an unmeasured foot, or conflicting flow.
"""
import time
from match_room_contours import agrees_with_observation, follow_instance

METHOD = 'SOURCE_OBSERVATION_INSTANCE_CONTOUR'


def agreed_intervals(frames, detections, observations, *, deadline):
    """Require both endpoint observations and both complete optical paths."""
    if not frames or len(frames) != len(detections):
        return []
    by_time = {f['media_ms']: i for i, f in enumerate(frames)}
    accepted = []
    for a, b in zip(observations, observations[1:]):
        if time.monotonic() >= deadline:
            break
        # Empty/uncertain rows are deliberate barriers; do not filter them out.
        if any(s.get('identity_status') != 'CONFIRMED' or not s.get('ground') for s in (a, b)):
            continue
        ai, bi = by_time.get(a['media_ms']), by_time.get(b['media_ms'])
        if ai is None or bi is None or bi-ai < 4 or not 0 < b['media_ms']-a['media_ms'] <= 250:
            continue
        local, rows = frames[ai:bi+1], detections[ai:bi+1]
        if any(not 0 < y['media_ms']-x['media_ms'] <= 75 for x, y in zip(local, local[1:])):
            continue
        owners = []
        for index, observation in ((0, a), (len(local)-1, b)):
            candidates = [j for j, row in enumerate(rows[index])
                          if row.get('ground') is not None and
                          agrees_with_observation(row, observation, local[index]['gray'].shape)]
            owners.append(candidates[0] if len(candidates) == 1 else None)
        if None in owners:
            continue
        forward = follow_instance(local, rows, 0, owners[0])
        backward = follow_instance(local, rows, len(local)-1, owners[1])
        if any(i not in forward or forward.get(i) != backward.get(i)
               or rows[i][forward[i]].get('ground') is None for i in range(len(local))):
            continue
        accepted.append({'indices': list(range(ai, bi+1)),
                         'instances': [forward[i] for i in range(len(local))],
                         'reference_frames': [a['frame_id'], b['frame_id']]})
    return accepted


def contour_segments(video, observations, start, end, *, deadline, diagnostics, on_segment=None):
    """Bounded short proof only. Partial valid intervals stay separate."""
    from native_player_segmentation import PersonSegmenter
    from match_room_contours import read_clip, detect_frame, measured_mask
    from match_room_tracking import foreground_polygons
    diagnostics.update(status='UNSUPPORTED_INPUT', method=METHOD)
    boxes = [s['player_box'] for s in observations
             if s.get('identity_status') == 'CONFIRMED' and s.get('ground') and s.get('player_box')]
    if not 0 < end-start <= 1500 or len(boxes) < 2:
        return []
    pairs = [(a, b) for a, b in zip(observations, observations[1:])
             if all(s.get('identity_status') == 'CONFIRMED' and s.get('ground') for s in (a, b))
             and start <= a['media_ms'] < b['media_ms'] <= end
             and b['media_ms']-a['media_ms'] <= 250]
    if not pairs:
        return []
    start, end = min(a['media_ms'] for a, _ in pairs), max(b['media_ms'] for _, b in pairs)
    boxes = [s['player_box'] for pair in pairs for s in pair if s.get('player_box')]
    model = PersonSegmenter()
    frames, detections, segments = [], [], []
    pending = {b['media_ms']: (a, b) for a, b in pairs}
    stream = read_clip(video, start, end, sample_step=0)
    timed_out = False
    try:
        for frame in stream:
            if time.monotonic() >= deadline-1:
                timed_out = True
                break
            h, w = frame['gray'].shape
            # Keep competitors in one fixed full-width detector view.
            top = max(0, int((min(b[1] for b in boxes)-.1)*h))
            bottom = min(h, int((max(b[1]+b[3] for b in boxes)+.1)*h)+1)
            detections.append(detect_frame(frame, (0, top, w, bottom), model))
            frame.pop('image')
            frames.append(frame)
            pair = pending.get(frame['media_ms'])
            if pair is None:
                continue
            # Complete and preserve each independently checked interval before
            # decoding more frames. A later timeout cannot erase earlier proof.
            intervals = agreed_intervals(frames, detections, pair, deadline=deadline)
            for interval in intervals:
                samples = []
                for i, j in zip(interval['indices'], interval['instances']):
                    h, w = frames[i]['gray'].shape
                    polygons = foreground_polygons([{'class_id': 0, 'mask': measured_mask(d)}
                                                    for d in detections[i]], w, h)
                    if not polygons:
                        samples = []
                        break
                    row, ms = detections[i][j], frames[i]['media_ms']
                    fid = f'position-contour:{ms}'
                    samples.append({'media_ms': ms, 'frame_id': fid, 'ground': row['ground'],
                                    'player_width': row['player_width'], 'confidence': row['confidence'],
                                    'foreground': {'method': 'SOURCE_PERSON_MASK', 'frame_id': fid,
                                                   'media_ms': ms, 'polygons': polygons}})
                if samples:
                    refs = interval['reference_frames']
                    segment = {'id': f"position-contour:{samples[0]['media_ms']}:{samples[-1]['media_ms']}",
                               'reference_frame': refs[0], 'observation_reference_frames': refs,
                               'overlap_frames': len(samples),
                               'ground_method': 'LOWER_VISIBLE_CONTOUR',
                               'source_frame_coverage': 'COMPLETE_SEGMENT', 'samples': samples}
                    segments.append(segment)
                    if on_segment is not None:
                        on_segment(segment)
    finally:
        stream.close()
    diagnostics.update(status='TIME_BUDGET' if timed_out else
                       'SUPPORTED_SOURCE_OBSERVATIONS' if segments else 'NO_AGREED_INTERVAL',
                       decoded_frames=len(frames), agreed_intervals=len(segments))
    return segments
