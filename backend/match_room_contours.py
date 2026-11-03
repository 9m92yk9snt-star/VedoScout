"""Short, presentation-only instance contours checked from two original taps.

Reuses the repository's pinned local person segmenter. No provider requests,
identity promotion, event/grade edits, mask propagation or inferred foot pose.
The ground point is the lower visible silhouette, not an anatomical landmark.
"""
import math
import time

import cv2
import numpy as np

from player_selection import valid_box, valid_point
import video_timebase

METHOD = 'TAP_BIDIRECTIONAL_INSTANCE_CONTOUR'
MAX_SECONDS = 3.0
MAX_FRAMES = 96
MAX_GAP_MS = 75


def read_clip(video, start, end):
    """Decode once, retaining actual post-grab media times and no FPS fallback."""
    cap = cv2.VideoCapture(str(video))
    count = 0
    try:
        ok, stamp, fallback = video_timebase.seek_with_preroll(cap, max(0, start/1000))
        previous = None
        while ok and stamp*1000 <= end+1 and count < MAX_FRAMES:
            if (not fallback and stamp*1000 >= start-1
                    and video_timebase.should_sample(stamp, previous, 1/35)):
                valid, image = cap.retrieve()
                if valid:
                    height, width = image.shape[:2]
                    image = cv2.resize(image, (720, round(height*720/width)))
                    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                    yield {'media_ms': round(stamp*1000), 'image': image, 'gray': gray}
                    count += 1
                    previous = stamp
            ok, stamp, fallback = video_timebase.grab_frame_time_seconds(cap)
    finally:
        cap.release()


def lower_contour(mask, box, other_masks=()):
    """Use measured bottom pixels; suppress clipped/partial/occluded contours."""
    ys, xs = np.nonzero(mask)
    if len(xs) < 60:
        return None
    x, y, width, height = box
    if width <= 0 or height/width < 1.05 or ys.max() < y + height*.9:
        return None
    # Never call the edge of a cropped ROI a visible boot.
    if xs.min() <= 1 or xs.max() >= mask.shape[1]-2 or ys.max() >= mask.shape[0]-2:
        return None
    low = ys >= np.percentile(ys, 98)
    lx, ly = xs[low], ys[low]
    if any(np.mean(other[ly, lx] > 0) > .15 for other in other_masks):
        return None
    # Centre over the visible stance instead of hopping from boot to boot.
    # Height still comes from measured bottom pixels, never a box offset.
    near_ground = ys >= ys.max()-height*.12
    return [float((xs[near_ground].min()+xs[near_ground].max())/2), float(np.median(ly))]


def detect_frame(frame, roi, segmenter):
    x0, y0, x1, y1 = roi
    image = frame['image']
    height, width = image.shape[:2]
    instances = segmenter.predict(image[y0:y1, x0:x1])
    # NMS boxes can leave two almost identical masks of one player. Suppress
    # only >85% mask IoU duplicates; overlapping players remain alternatives.
    unique = []
    for instance in sorted(instances, key=lambda r: r['score'], reverse=True):
        if any(instance.get('class_id') == other.get('class_id') and mask_iou(instance['mask'], other['mask']) > .85 for other in unique):
            continue
        unique.append(instance)
    instances = unique
    result = []
    for i, instance in enumerate(instances):
        if instance.get('class_id') != 0 or instance['score'] < .55:
            continue
        local = instance['mask'].copy()
        for item in instances:
            if item.get('class_id') == 32:
                local[item['mask'] > 0] = 0
        ground = lower_contour(local, instance['box'],
                               [other['mask'] for j, other in enumerate(instances)
                                if j != i and other.get('class_id') == 0])
        mask = np.zeros(image.shape[:2], np.uint8)
        mask[y0:y1, x0:x1] = local
        x, y, bw, bh = instance['box']
        result.append({'mask_bits': np.packbits(mask), 'mask_shape': mask.shape, 'box': [x+x0, y+y0, bw, bh],
                       'ground': [(ground[0]+x0)/width, (ground[1]+y0)/height] if ground else None,
                       'player_width': min(bw, bh*.4)/width, 'confidence': float(instance['score'])})
    return result


def measured_mask(row):
    if 'mask' in row:  # useful for in-memory callers and unit fixtures
        return row['mask']
    return np.unpackbits(row['mask_bits'], count=math.prod(row['mask_shape'])).reshape(row['mask_shape'])


def owns(mask, point):
    x, y = np.round(point).astype(int)
    return 0 <= x < mask.shape[1] and 0 <= y < mask.shape[0] and bool(mask[y, x])


def mask_iou(a, b):
    return np.count_nonzero((a > 0) & (b > 0))/max(1, np.count_nonzero((a > 0) | (b > 0)))


def seed_candidates(rows, target, shape):
    height, width = shape
    return [i for i, row in enumerate(rows)
            if owns(measured_mask(row), [target['x']*width, target['y']*height])]


def select_seed_view(frames, seeds, segmenter, *, deadline=None):
    """Choose one fixed view using both original taps, before dense inference.

    A full-width view can make the selected person too small for the local
    model. Retry the union of the original boxes with one body-width of context.
    Both taps must resolve uniquely in that same view. Never move the crop to
    chase a lost player, select the nearest person, or relax association gates.
    """
    height, width = frames[0]['gray'].shape
    boxes = [s['box'] for s in seeds]
    mx, my = max(b['w'] for b in boxes), max(b['h'] for b in boxes)*.7
    top = max(0, int((min(b['y'] for b in boxes)-my)*height))
    bottom = min(height, math.ceil((max(b['y']+b['h'] for b in boxes)+my)*height))
    wide = (0, top, width, bottom)
    focused = (max(0, int((min(b['x'] for b in boxes)-mx)*width)), top,
               min(width, math.ceil((max(b['x']+b['w'] for b in boxes)+mx)*width)), bottom)
    attempts = []
    for roi in dict.fromkeys((wide, focused)):
        rows = []
        for frame in frames:
            if deadline is not None and time.monotonic() >= deadline:
                return None, {}, attempts
            rows.append(detect_frame(frame, roi, segmenter))
        counts = [len(seed_candidates(d, s['target_point'], f['gray'].shape))
                  for f, s, d in zip(frames, seeds, rows)]
        attempts.append({'roi': list(roi), 'owners': counts})
        if counts == [1, 1]:
            return roi, {f['media_ms']: d for f, d in zip(frames, rows)}, attempts
    return None, {}, attempts


def transport(previous, current, instance, candidates):
    """Warp for association only; every displayed contour is freshly detected."""
    height, width = previous.shape
    shape = (480, round(height*480/width))
    previous = cv2.resize(previous, shape)
    current = cv2.resize(current, shape)
    flow = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_FAST).calc(current, previous, None)
    yy, xx = np.mgrid[:shape[1], :shape[0]].astype(np.float32)
    source = cv2.resize(measured_mask(instance), shape, interpolation=cv2.INTER_NEAREST)
    warped = cv2.remap(source, xx+flow[:, :, 0], yy+flow[:, :, 1], cv2.INTER_NEAREST)
    scores = sorted([(mask_iou(warped, cv2.resize(measured_mask(row), shape, interpolation=cv2.INTER_NEAREST)), i)
                     for i, row in enumerate(candidates)], reverse=True)
    if not scores or scores[0][0] < .5 or (len(scores) > 1 and scores[1][0] > .25):
        return None
    return scores[0][1]


def follow(frames, detections, seed_index, target):
    candidates = seed_candidates(detections[seed_index], target, frames[seed_index]['gray'].shape)
    if len(candidates) != 1:
        return {}
    source = candidates[0]
    result = {seed_index: source}
    for direction in (-1, 1):
        chosen = source
        previous = seed_index
        for i in range(seed_index+direction, len(frames) if direction > 0 else -1, direction):
            gap = abs(frames[i]['media_ms']-frames[previous]['media_ms'])
            if not 0 < gap <= MAX_GAP_MS:
                break
            # Same conservative cut threshold as the existing optical tracker.
            a = cv2.resize(frames[previous]['gray'], (160, 90))
            b = cv2.resize(frames[i]['gray'], (160, 90))
            if float(cv2.absdiff(a, b).mean()) > 45:
                break
            chosen = transport(frames[previous]['gray'], frames[i]['gray'],
                               detections[previous][chosen], detections[i])
            if chosen is None:
                break
            result[i] = chosen
            previous = i
    return result


def agrees_with_observation(row, observed, shape):
    """A source observation can name either boot; compare with visible lower body.

    Comparing two arbitrary boot centers rejects valid changes of planted foot.
    This gate never calibrates or shifts the measured silhouette to the model.
    """
    height, width = shape
    ys, xs = np.nonzero(measured_mask(row))
    if not len(xs):
        return False
    lower = ys >= ys.min()+(ys.max()-ys.min())*.65
    x, y = observed['ground'][0]*width, observed['ground'][1]*height
    distance = np.min(np.hypot(xs[lower]-x, ys[lower]-y))
    return distance <= max(3, min(row['player_width'], observed.get('player_width', .01))*width*.2)


def agree_segments(frames, detections, paths, observations, seeds):
    """Fuse two tap-origin paths only after agreement on shared source frames.

    At least one path must reach both original taps, and the shared overlap must
    cover >=5 consecutive frames. Never average conflicting paths or draw a
    missing contour. Forward and backward tracking need not fail at the same
    pose: a supported path can complete the other's missing tail.
    """
    if len(paths) != 2 or seeds[0] == seeds[1]:
        return []
    indices = [min(range(len(frames)), key=lambda i: abs(frames[i]['media_ms']-t)) for t in seeds]
    shared = sorted(set(paths[0]) & set(paths[1]))
    if (not any(all(i in path for i in indices) for path in paths)
            or any(paths[0][i] != paths[1][i] for i in shared)
            or not any(shared[j:j+5] == list(range(shared[j], shared[j]+5)) for j in range(max(0, len(shared)-4)))):
        return []
    groups = []
    previous_index = None
    for i, frame in enumerate(frames):
        chosen = paths[0].get(i, paths[1].get(i))
        if chosen is None:
            previous_index = None
            continue
        row = detections[i][chosen]
        # Identity must remain supported in every intervening frame. A short
        # missing foot measurement may be bridged by presentation only.
        if row['ground'] is None:
            continue
        if previous_index is None or frame['media_ms']-frames[previous_index]['media_ms'] > 200:
            groups.append([])
        groups[-1].append((i, row))
        previous_index = i
    accepted = []
    for group in groups:
        if len(group) < 3:
            continue
        support = []
        conflict = False
        for observed in observations:
            if not observed.get('ground'):
                continue
            i, row = min(group, key=lambda p: abs(frames[p[0]]['media_ms']-observed['media_ms']))
            if abs(frames[i]['media_ms']-observed['media_ms']) > 40:
                continue
            if not agrees_with_observation(row, observed, frames[0]['gray'].shape):
                conflict = True
                break
            support.append(observed['frame_id'])
        if not conflict and support:
            rows = [{'media_ms': frames[i]['media_ms'], 'ground': row['ground'],
                     'player_width': row['player_width'], 'confidence': row['confidence']} for i,row in group]
            accepted.append({'id': f'contour:{len(accepted)}', 'reference_frame': support[0],
                             'reference_frames': support, 'seed_ms': list(seeds),
                             'overlap_frames': len(shared),
                             'ground_method': 'LOWER_VISIBLE_CONTOUR', 'presentation_gap_ms': 200, 'samples': rows})
    return accepted


def contour_segments(video, anchors, observations, start, end, *, deadline=None, diagnostics=None):
    """Fail closed if two nearby human taps or a pinned local asset are absent."""
    diagnostic = diagnostics if diagnostics is not None else {}
    diagnostic['status'] = 'UNSUPPORTED_INPUT'
    seeds = [a for a in anchors if isinstance(a.get('t'), (int, float))
             and start <= a['t']*1000 <= end and valid_box(a.get('box'))
             and valid_point(a.get('target_point')) and not a.get('player_behind')]
    if len(seeds) < 2 or not observations:
        return []
    seeds = sorted(seeds, key=lambda a: a['t'])
    pairs = [(a, b) for i, a in enumerate(seeds) for b in seeds[i+1:]
             if .15 <= b['t']-a['t'] <= 2.5]
    if not pairs:
        return []
    a, b = max(pairs, key=lambda pair: pair[1]['t']-pair[0]['t'])
    lo, hi = max(start, round(a['t']*1000)-400), min(end, round(b['t']*1000)+400)
    if hi-lo > MAX_SECONDS*1000:
        return []
    from native_player_segmentation import PersonSegmenter
    segmenter = PersonSegmenter()
    selected_frames = []
    for seed in (a, b):
        at = round(seed['t']*1000)
        candidates = list(read_clip(video, at-25, at+25))
        if not candidates:
            diagnostic['status'] = 'SOURCE_FRAME_UNAVAILABLE'
            return []
        frame = min(candidates, key=lambda f: abs(f['media_ms']-at))
        if abs(frame['media_ms']-at) > 25:
            diagnostic['status'] = 'SOURCE_FRAME_UNAVAILABLE'
            return []
        selected_frames.append(frame)
    roi, seed_rows, attempts = select_seed_view(selected_frames, (a, b), segmenter, deadline=deadline)
    diagnostic.update(seed_views=attempts, seed_ms=[f['media_ms'] for f in selected_frames])
    if roi is None:
        diagnostic['status'] = 'TIME_BUDGET' if deadline is not None and time.monotonic() >= deadline else 'UNRESOLVED_SELECTION'
        return []
    frames, detections = [], []
    stream = read_clip(video, lo, hi)
    try:
        for frame in stream:
            if deadline is not None and time.monotonic() >= deadline:
                diagnostic['status'] = 'TIME_BUDGET'
                return []
            cached = seed_rows.get(frame['media_ms'])
            detections.append(cached if cached is not None else detect_frame(frame, roi, segmenter))
            frame.pop('image')
            frames.append(frame)
    finally:
        stream.close()
    if len(frames) < 3:
        return []
    indices = [min(range(len(frames)), key=lambda i: abs(frames[i]['media_ms']-s['t']*1000)) for s in (a,b)]
    if any(abs(frames[i]['media_ms']-s['t']*1000) > 25 for i,s in zip(indices, (a,b))):
        return []
    paths = [follow(frames, detections, i, seed['target_point']) for i,seed in zip(indices, (a,b))]
    diagnostic.update(path_frames=[len(p) for p in paths],
                      shared_frames=len(set(paths[0]) & set(paths[1])))
    segments = agree_segments(frames, detections, paths, observations,
                              [frames[i]['media_ms'] for i in indices])
    diagnostic['status'] = 'SUPPORTED_CONTOURS' if segments else 'UNSUPPORTED_CONTINUITY'
    return segments
