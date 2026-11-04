"""Local contour agreement between independently localized source observations.

Call only after binding model receipts with match_room_position_evidence.
These seeds are model observations, never original human selections. Nothing
is drawn across uncertain source identity. Pixel paths remain measurement
evidence; source-confirmed endpoint bridges are explicitly presentation only.
"""
import time
from match_room_contours import agrees_with_observation, follow_instance

METHOD = 'SOURCE_OBSERVATION_INSTANCE_CONTOUR'


def refinement_model():
    """Load the pinned, local medium segmenter only after a small-model miss."""
    import cv2
    from native_player_segmentation import PersonSegmenter
    from match_room_reacquisition import MODEL_PATH, MODEL_SHA256
    from player_segmentation_assets import ensure_model_asset
    ensure_model_asset(MODEL_PATH, MODEL_SHA256)
    model = PersonSegmenter.__new__(PersonSegmenter)
    model.net = cv2.dnn.readNetFromONNX(str(MODEL_PATH))
    model.sha256 = MODEL_SHA256
    return model


def _adjacent_endpoint_pairs(observations):
    """Missing feet may be bridged; a missing identity may never be skipped."""
    previous = None
    last_time = None
    for row in observations:
        if last_time is not None and not 0 < row['media_ms']-last_time <= 250:
            previous = None
        last_time = row['media_ms']
        if row.get('identity_status') != 'CONFIRMED':
            previous = None
            continue
        if not row.get('ground'):
            continue
        if previous is not None and row['media_ms']-previous['media_ms'] <= 800:
            yield previous, row
        previous = row


def endpoint_pairs(observations):
    """Keep tightly spaced observations inside an independently checked window.

    A 17ms contact observation must not split a valid track into sub-five-frame
    pieces. Borrow adjacent endpoint context, never skip an identity barrier.
    """
    pairs = list(_adjacent_endpoint_pairs(observations))
    seen = set()
    for i, (a, b) in enumerate(pairs):
        if b['media_ms']-a['media_ms'] < 125:
            if i and pairs[i-1][1] is a and b['media_ms']-pairs[i-1][0]['media_ms'] <= 800:
                a = pairs[i-1][0]
            if (b['media_ms']-a['media_ms'] < 125 and i+1 < len(pairs)
                    and pairs[i+1][0] is b and pairs[i+1][1]['media_ms']-a['media_ms'] <= 800):
                b = pairs[i+1][1]
        key = (a['media_ms'], b['media_ms'])
        if key not in seen:
            seen.add(key)
            yield a, b


def agrees_with_source_box(row, observation, shape):
    """Bind the lower contour to the observed body, not a nearby opponent's boot."""
    box = observation.get('player_box')
    if not box:
        return True
    h, w = shape
    x, y, bw, bh = row['box']
    ox, oy, ow, oh = [box[0]*w, box[1]*h, box[2]*w, box[3]*h]
    intersection = max(0, min(x+bw, ox+ow)-max(x, ox))*max(0, min(y+bh, oy+oh)-max(y, oy))
    return intersection/max(1, bw*bh+ow*oh-intersection) >= .5


def feature_paths(frames, rows, owners, deadline):
    """Reuse appearance and reversible feature links; never motion prediction."""
    import cv2
    from match_room_reacquisition import IdentityAssociator
    if any('_appearance' not in row for detections in rows for row in detections):
        return {}, {}
    engine = IdentityAssociator.__new__(IdentityAssociator)
    engine.frames, engine.rows = frames, rows
    engine.indices, engine.sources = [0, len(frames)-1], owners
    engine.shape = frames[0]['gray'].shape
    engine.pair_cache = {}
    engine.histograms = [[row['_appearance'] for row in detections] for detections in rows]
    paths = []
    for at, owner, step in ((0, owners[0], 1), (len(frames)-1, owners[1], -1)):
        path = {at: owner}
        for k in range(at+step, len(frames) if step == 1 else -1, step):
            if time.monotonic() >= deadline-1 or not 0 < abs(frames[k]['media_ms']-frames[at]['media_ms']) <= 75:
                break
            a = cv2.resize(frames[at]['gray'], (160,90))
            b = cv2.resize(frames[k]['gray'], (160,90))
            if float(cv2.absdiff(a,b).mean()) > 45:
                break
            owner = engine.feature_link(at, k, owner)
            if owner is None:
                break
            path[k] = owner
            at = k
        paths.append(path)
    return paths


def agreed_intervals(frames, detections, observations, *, deadline, allow_display_bridge=False):
    """Require both endpoint observations and both complete optical paths."""
    if not frames or len(frames) != len(detections):
        return []
    by_time = {f['media_ms']: i for i, f in enumerate(frames)}
    accepted = []
    for a, b in (endpoint_pairs(observations) if allow_display_bridge else zip(observations, observations[1:])):
        if time.monotonic() >= deadline:
            break
        # Empty/uncertain rows are deliberate barriers; do not filter them out.
        if any(s.get('identity_status') != 'CONFIRMED' or not s.get('ground') for s in (a, b)):
            continue
        ai, bi = by_time.get(a['media_ms']), by_time.get(b['media_ms'])
        if ai is None or bi is None or bi-ai < 4 or not 0 < b['media_ms']-a['media_ms'] <= (800 if allow_display_bridge else 250):
            continue
        local, rows = frames[ai:bi+1], detections[ai:bi+1]
        if any(not 0 < y['media_ms']-x['media_ms'] <= 75 for x, y in zip(local, local[1:])):
            continue
        owners = []
        for index, observation in ((0, a), (len(local)-1, b)):
            candidates = [j for j, row in enumerate(rows[index])
                          if (allow_display_bridge or row.get('ground') is not None) and
                          agrees_with_observation(row, observation, local[index]['gray'].shape) and
                          agrees_with_source_box(row, observation, local[index]['gray'].shape)]
            owners.append(candidates[0] if len(candidates) == 1 else None)
        if None in owners:
            continue
        forward = follow_instance(local, rows, 0, owners[0])
        backward = follow_instance(local, rows, len(local)-1, owners[1])
        if (allow_display_bridge and not any(forward[i] != backward[i] for i in set(forward) & set(backward))
                and any(i not in forward or i not in backward for i in range(len(local)))):
            ff, bb = feature_paths(local, rows, owners, deadline)
            if all(i in ff and ff.get(i) == bb.get(i) for i in range(len(local))):
                # A feature path may complete a missing link, never contradict
                # an already observed instance from either contour direction.
                if all(ff[i] == j for path in (forward, backward) for i, j in path.items()):
                    forward, backward = ff, bb
        if any(i not in forward or forward.get(i) != backward.get(i)
               or (not allow_display_bridge and rows[i][forward[i]].get('ground') is None) for i in range(len(local))):
            continue
        accepted.append({'indices': list(range(ai, bi+1)),
                         'instances': [forward[i] for i in range(len(local))],
                         'reference_frames': [a['frame_id'], b['frame_id']]})
        if allow_display_bridge:
            accepted[-1]['source_endpoint_ground'] = {i: observation['ground']
                for i, j, observation in ((ai, owners[0], a), (bi, owners[1], b))
                if detections[i][j].get('ground') is None}
    return accepted


def source_bound_display_interval(frames, detections, observations):
    """The approved endpoint-based presentation when dense optical links fail.

    Source identity remains the authority. This estimates display positions;
    it never asserts a newly measured foot or a pixel-tracked middle identity.
    """
    import cv2
    from match_room_reacquisition import IdentityAssociator
    import numpy as np
    if len(observations) < 2 or any(o.get('identity_status') != 'CONFIRMED' for o in observations):
        return None
    a, b = observations[0], observations[-1]
    if not a.get('ground') or not b.get('ground') or not 0 < b['media_ms']-a['media_ms'] <= 800:
        return None
    by_time = {f['media_ms']: i for i,f in enumerate(frames)}
    ai, bi = by_time.get(a['media_ms']), by_time.get(b['media_ms'])
    if ai is None or bi is None or bi-ai < 4:
        return None
    if any(not 0 < frames[i+1]['media_ms']-frames[i]['media_ms'] <= 75 for i in range(ai,bi)):
        return None
    owners = []
    for i, observation in ((ai,a),(bi,b)):
        if not observation.get('player_box'):
            return None
        h,w = frames[i]['gray'].shape
        x,y = observation['ground'][0]*w, observation['ground'][1]*h
        candidates = []
        for j,row in enumerate(detections[i]):
            bx,by,bw,bh = row['box']
            if (agrees_with_source_box(row, observation, (h,w)) and
                    bx-bw*.2 <= x <= bx+bw*1.2 and by+bh*.6 <= y <= by+bh*1.2):
                candidates.append(j)
        if len(candidates) != 1:
            return None
        owners.append(candidates[0])
    first, last = detections[ai][owners[0]], detections[bi][owners[1]]
    if '_appearance' not in first or '_appearance' not in last:
        return None
    if any(not np.isfinite(row['_appearance']).all() or row['_appearance'].sum() <= 0 for row in (first,last)):
        return None
    distance = cv2.compareHist(first['_appearance'], last['_appearance'], cv2.HISTCMP_BHATTACHARYYA)
    if not np.isfinite(distance) or distance > IdentityAssociator.APPEARANCE_LIMIT:
        return None
    return {'indices':list(range(ai,bi+1)), 'instances':[owners[0]]+[None]*(bi-ai-1)+[owners[1]],
            'reference_frames':[a['frame_id'],b['frame_id']], 'presentation_only':True,
            'source_endpoint_ground':{by_time[o['media_ms']]:o['ground'] for o in observations
                                      if o.get('ground') and o['media_ms'] in by_time and
                                      (o not in (a,b) or detections[by_time[o['media_ms']]][owners[0] if o is a else owners[1]].get('ground') is None)}}


def supporting_observations(frames, detections, interval, observations):
    chosen = dict(zip(interval['indices'], interval['instances']))
    times = {frames[i]['media_ms']:i for i in interval['indices']}
    for observed in observations:
        if observed.get('identity_status') != 'CONFIRMED' or observed['media_ms'] not in times:
            return False
        if interval.get('presentation_only') or not observed.get('ground'):
            continue
        i = times[observed['media_ms']]
        row = detections[i][chosen[i]]
        if not agrees_with_source_box(row, observed, frames[i]['gray'].shape):
            return False
    return True


def display_fits_source_bodies(frames, interval, display, observations):
    """Reject a curve that leaves an independently observed player's lower body."""
    times = {frames[i]['media_ms']:i for i in interval['indices']}
    for observed in observations:
        i = times[observed['media_ms']]
        if i not in display or not observed.get('player_box'):
            continue
        x,y = display[i]['display_ground']
        bx,by,bw,bh = observed['player_box']
        if not (bx-bw*.3 <= x <= bx+bw*1.3 and by+bh*.55 <= y <= by+bh*1.3):
            return False
    return True


def observation_windows(observations, start, end):
    """Partition confirmed identity runs; prioritize recovery.

    Unknown identity is a barrier; hidden feet retain the identity run. Windows share only one observation, so
    no interval is processed twice. Recovery is checked independently at both
    ends and gets budget before optional repetition of the pre-occlusion run.
    """
    groups, current, interrupted = [], [], False
    for row in observations:
        if not start <= row['media_ms'] <= end:
            continue
        valid = row.get('identity_status') == 'CONFIRMED'
        gap = current and row['media_ms']-current[-1]['media_ms'] > 250
        if not valid or gap:
            if current: groups.append((interrupted, current))
            current = []
            interrupted = True
        if valid: current.append(row)
    if current: groups.append((interrupted, current))
    windows = []
    for recovery, rows in groups:
        grounded = [i for i, row in enumerate(rows) if row.get('ground')]
        if len(grounded) < 2:
            continue
        rows = rows[grounded[0]:grounded[-1]+1]
        at = 0
        while at < len(rows)-1:
            last = max(i for i in range(at, len(rows)) if rows[i].get('ground') and rows[i]['media_ms']-rows[at]['media_ms'] <= 1500)
            if last == at: break
            needs_recovery = recovery or any(not r.get('ground') for r in rows[:at+1])
            windows.append((needs_recovery, rows[at]['media_ms'], rows[last]['media_ms']))
            at = last
    # Most recent recovery first; uninterrupted evidence retains source order.
    windows.sort(key=lambda w: (not w[0], -w[1] if w[0] else w[1]))
    return [(a, b) for _, a, b in windows]


def contour_segments(video, observations, start, end, *, deadline, diagnostics, on_segment=None, segmenter=None):
    """Bounded short proof only. Partial valid intervals stay separate."""
    from native_player_segmentation import PersonSegmenter
    from match_room_contours import read_clip, detect_frame, measured_mask
    from match_room_tracking import foreground_polygons
    diagnostics.update(status='UNSUPPORTED_INPUT', method=METHOD)
    boxes = [s['player_box'] for s in observations
             if s.get('identity_status') == 'CONFIRMED' and s.get('ground') and s.get('player_box')]
    if not 0 < end-start <= 1500 or len(boxes) < 2:
        return []
    pairs = [(a, b) for a, b in endpoint_pairs(observations)
             if start <= a['media_ms'] < b['media_ms'] <= end]
    if not pairs:
        return []
    start, end = min(a['media_ms'] for a, _ in pairs), max(b['media_ms'] for _, b in pairs)
    boxes = [s['player_box'] for pair in pairs for s in pair if s.get('player_box')]
    model = segmenter if segmenter is not None else PersonSegmenter()
    frames, detections, segments = [], [], []
    pending = {}
    for a, b in pairs:
        prior = pending.get(b['media_ms'])
        if prior is None or a['media_ms'] < prior[0]['media_ms']:
            pending[b['media_ms']] = (a,b)
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
            roi = (0, top, w, bottom)
            detections.append(detect_frame(frame, roi, model))
            import cv2
            hsv = cv2.cvtColor(frame['image'], cv2.COLOR_BGR2HSV)
            for row in detections[-1]:
                hist = cv2.calcHist([hsv], [0,1], measured_mask(row), [24,16], [0,180,0,256])
                row['_appearance'] = cv2.normalize(hist, None, norm_type=cv2.NORM_L1)
            frame.pop('image')
            frames.append(frame)
            pair = pending.get(frame['media_ms'])
            if pair is None:
                continue
            # Complete and preserve each independently checked interval before
            # decoding more frames. A later timeout cannot erase earlier proof.
            intervals = agreed_intervals(frames, detections, pair, deadline=deadline, allow_display_bridge=True)
            support = [o for o in observations if pair[0]['media_ms'] <= o['media_ms'] <= pair[1]['media_ms']]
            if not intervals:
                # When a pose hides the detector's foot/body, use the last
                # source-bound visible endpoint and the independently reacquired
                # endpoint. Intermediate confirmed source positions shape the
                # approved curve; none becomes a new pixel observation.
                last_end = max((s['samples'][-1]['media_ms'] for s in segments), default=start)
                if segments and frame['media_ms'] == end and frame['media_ms']-last_end < 125:
                    last_end = segments[-1]['samples'][0]['media_ms']
                candidates = [o for o in observations if o.get('ground') and
                              max(start, last_end, frame['media_ms']-800) <= o['media_ms'] < frame['media_ms']]
                for candidate in candidates:
                    candidate_support = [o for o in observations if candidate['media_ms'] <= o['media_ms'] <= frame['media_ms']]
                    estimate = source_bound_display_interval(frames, detections, candidate_support)
                    if estimate is not None:
                        intervals, support = [estimate], candidate_support
                        break
            for interval in intervals:
                if not supporting_observations(frames, detections, interval, support):
                    continue
                interval['reference_frames'] = [o['frame_id'] for o in support if o.get('ground')]
                from match_room_display_bridge import tracked_display_positions
                display = tracked_display_positions(frames, detections, interval, deadline=deadline)
                if display is None or not display_fits_source_bodies(frames, interval, display, support):
                    continue
                samples = []
                for i, j in zip(interval['indices'], interval['instances']):
                    h, w = frames[i]['gray'].shape
                    polygons = foreground_polygons([{'class_id': 0, 'mask': measured_mask(d)}
                                                    for d in detections[i]], w, h)
                    if not polygons:
                        samples = []
                        break
                    ms = frames[i]['media_ms']
                    if j is not None:
                        row = detections[i][j]
                    else:
                        ai, bi = interval['indices'][0], interval['indices'][-1]
                        first = detections[ai][interval['instances'][0]]
                        last = detections[bi][interval['instances'][-1]]
                        u = (ms-frames[ai]['media_ms'])/(frames[bi]['media_ms']-frames[ai]['media_ms'])
                        row = {'ground':None, 'player_width':first['player_width']+(last['player_width']-first['player_width'])*u,
                               'confidence':min(first['confidence'], last['confidence'])}
                    fid = f'position-contour:{ms}'
                    samples.append({'media_ms': ms, 'frame_id': fid, 'ground': row['ground'],
                                    **display.get(i, {}),
                                    'player_width': row['player_width'], 'confidence': row['confidence'],
                                    'foreground': {'method': 'SOURCE_PERSON_MASK', 'frame_id': fid,
                                                   'media_ms': ms, 'polygons': polygons}})
                if samples:
                    refs = interval['reference_frames']
                    segment = {'id': f"position-contour:{samples[0]['media_ms']}:{samples[-1]['media_ms']}",
                               'reference_frame': refs[0], 'observation_reference_frames': refs,
                               'overlap_frames': len(samples),
                               'segmenter_sha256': getattr(model, 'sha256', None),
                               'ground_method': 'CAMERA_SPACE_DISPLAY_BRIDGE' if display else 'LOWER_VISIBLE_CONTOUR',
                               'identity_method': 'SOURCE_CONFIRMED_ENDPOINT_BRIDGE' if interval.get('presentation_only') else 'BIDIRECTIONAL_INSTANCE_AGREEMENT',
                               'camera_method': 'BACKGROUND_AFFINE' if display else None,
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
