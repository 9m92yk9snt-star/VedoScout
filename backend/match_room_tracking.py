"""Bounded presentation-only reuse of tap tracking and camera compensation.

Never changes events, grades or identity authority. No LLM/provider requests.
A measured box is a ground proxy, not a measured foot landmark.
"""
import json
import math
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MAX_GAP_MS = 120
MAX_EVENTS = 8
TIMEOUT_S = 25


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def point(p):
    return isinstance(p, list) and len(p) == 2 and all(finite(x) and 0 <= x <= 1 for x in p)


def bind_segments(points, observations, start, end):
    """Require a same-action observed ground position in each unbroken track.

    Calibrate the ground proxy within the tracked box from that observation.
    Never bridge gaps or join independent seeds: caller runs each seed separately.
    """
    groups = []
    for p in sorted(points, key=lambda p: p.get('t', -1)):
        if not all(finite(p.get(k)) for k in ('t', 'x', 'y', 'w', 'h', 'conf')):
            continue
        ms = round(p['t'] * 1000)
        if not start <= ms <= end or p['conf'] < .55 or min(p['w'], p['h']) <= 0:
            continue
        if not groups or not 0 < ms - round(groups[-1][-1]['t'] * 1000) <= MAX_GAP_MS:
            groups.append([])
        groups[-1].append(p)
    result = []
    for group in groups:
        if len(group) < 3:
            continue
        matches = []
        conflict = False
        for s in observations:
            if not point(s.get('ground')) or not finite(s.get('media_ms')):
                continue
            p = min(group, key=lambda p: abs(p['t'] * 1000 - s['media_ms']))
            if abs(p['t'] * 1000 - s['media_ms']) > 80:
                continue
            x, y = s['ground']
            u, v = (x-p['x'])/p['w'], (y-p['y'])/p['h']
            if not (-.15 <= u <= 1.15 and .55 <= v <= 1.2):
                conflict = True
                break
            matches.append((abs(p['t']*1000-s['media_ms']), u, v, s['frame_id']))
        if conflict or not matches:
            continue
        _, u, v, fid = min(matches)
        samples = []
        for p in group:
            ground = [p['x'] + u*p['w'], p['y'] + v*p['h']]
            if not point(ground):
                samples = []
                break
            samples.append({'media_ms': round(p['t']*1000), 'ground': ground,
                            'player_width': p['w'], 'confidence': p['conf']})
        if samples:
            result.append({'samples': samples, 'points': group, 'reference_frame': fid})
    return result


def add_motion(segment, motion):
    """Draw only measured camera-compensated displacement, in current view."""
    w, h = motion.get('w', 0), motion.get('h', 0)
    if not w or not h:
        return
    samples = {s['media_ms']: s for s in segment['samples']}
    for interval in motion.get('samples', []):
        if interval.get('ok') is not True:
            continue
        a, b = round(interval['t0']*1000), round(interval['t1']*1000)
        if a not in samples or b not in samples or not 0 < b-a <= MAX_GAP_MS:
            continue
        rx, ry = interval['rx']/w, interval['ry']/h
        if not all(finite(x) for x in (rx, ry)) or not .003 <= math.hypot(rx, ry) <= .08:
            continue
        tip = samples[b]['ground']
        tail = [tip[0]-rx, tip[1]-ry]
        if point(tail):
            samples[b]['groundTrail'] = [tail, tip]
            samples[b]['motion_from_ms'] = a


def endpoint_arrow(previous, current, matrix, width, height, *, field='ground', max_gap=1000, max_distance=.3):
    """Observed endpoint displacement in the current camera view; not a path."""
    import numpy as np
    if not point(previous.get(field)) or not point(current.get(field)):
        return None
    if not 0 < current['media_ms'] - previous['media_ms'] <= max_gap:
        return None
    m = np.asarray(matrix, dtype=float)
    if m.shape != (3, 3) or not np.isfinite(m).all() or width <= 0 or height <= 0:
        return None
    p = m @ np.array([previous[field][0]*width, previous[field][1]*height, 1.])
    tail = [float(p[0]/width), float(p[1]/height)]
    tip = current[field]
    if not point(tail) or not .008 <= math.dist(tail, tip) <= max_distance:
        return None
    return [tail, tip]


def observed_motion(video, observations, *, ball_gap_ms=300, separate_bands=False):
    """Reuse the background affine estimator between observed source endpoints.

    Every intervening decoded frame must support the camera transform. Exclude
    a full-height band containing the actor endpoints; no player trajectory is
    assumed when selecting background pixels. Active-ball endpoints have their
    own <=300ms gate and displacement; player motion never supplies ball motion.
    """
    import cv2
    import numpy as np
    from copy import deepcopy
    from player_tracking import _read_window, _cut_flags
    from motion_compensation import estimate_camera
    samples = sorted(deepcopy(observations), key=lambda s: s['media_ms'])
    cap = cv2.VideoCapture(str(video))
    try:
        for previous, current in zip(samples, samples[1:]):
            gap = current['media_ms']-previous['media_ms']
            ground = 0 < gap <= 1000 and all(point(s.get('ground')) for s in (previous, current))
            ball = 0 < gap <= ball_gap_ms and all(point(s.get('ball')) for s in (previous, current))
            if not (ground or ball):
                continue
            start, end = previous['media_ms']/1000, current['media_ms']/1000
            frames = _read_window(cap, start-.02, end+.025, 1/30, seed_time=start)
            if len(frames) < 2 or abs(frames[0][0]-start) > .025 or abs(frames[-1][0]-end) > .025:
                continue
            cuts = _cut_flags(frames)
            h, w = frames[0][1].shape
            margin = max(previous.get('player_width', .1), current.get('player_width', .1))
            endpoints = [s[key][0] for s in (previous, current) for key in ('ground', 'ball') if point(s.get(key))]
            left = max(0., min(endpoints)-margin)
            right = min(1., max(endpoints)+margin)
            exclude = [(left*w, 0, (right-left)*w, h)]
            if separate_bands:
                exclude = [(max(0., x-margin)*w, 0, (min(1., x+margin)-max(0., x-margin))*w, h) for x in endpoints]
            cumulative = np.eye(3)
            valid = True
            for i in range(1, len(frames)):
                if cuts[i] or not 0 < frames[i][0]-frames[i-1][0] <= .12:
                    valid = False
                    break
                matrix, _ = estimate_camera(frames[i-1][1], frames[i][1], exclude)
                if matrix is None:
                    valid = False
                    break
                cumulative = np.vstack([matrix, [0, 0, 1]]) @ cumulative
            if valid:
                arrow = endpoint_arrow(previous, current, cumulative, w, h) if ground else None
                if arrow:
                    current.update(groundTrail=arrow, motion_start_ms=previous['media_ms'],
                                   motion_method='BACKGROUND_AFFINE_ENDPOINTS')
                ball_arrow = endpoint_arrow(previous, current, cumulative, w, h,
                                            field='ball', max_gap=ball_gap_ms, max_distance=.8 if ball_gap_ms > 300 else .3) if ball else None
                if ball_arrow:
                    current.update(ballTrail=ball_arrow, ball_motion_start_ms=previous['media_ms'],
                                   ball_motion_method='BACKGROUND_AFFINE_BALL_ENDPOINTS')
    finally:
        cap.release()
    return samples


def pass_motion(video, event, observations):
    """A confirmed release-to-reception direction, never a predicted pass lane.

    Coordinates still describe only endpoints in the reception camera view.
    The path between them is not claimed to be straight or fully observed.
    """
    if event.get('canonical_action_type') != 'PASS' or event.get('canonical_outcome') != 'COMPLETED':
        return observations
    contact = event.get('contact_ms')
    receiver = (event.get('causal_chain') or {}).get('receiver_visual_id')
    if not finite(contact) or not isinstance(receiver, str) or not receiver:
        return observations
    release = [s for s in observations if s.get('ball_phase') == 'RELEASE' and point(s.get('ball')) and abs(s['media_ms']-contact) <= 80]
    arrival = [s for s in observations if s.get('ball_phase') == 'RECEIVED' and s.get('receiver') == receiver and point(s.get('ball'))]
    if len(release) != 1 or len(arrival) != 1:
        return observations
    a, b = release[0], arrival[0]
    start, end = event['proof']['proof_start_ms'], event['proof']['proof_end_ms']
    if not start <= a['media_ms'] < b['media_ms'] <= end or b['media_ms']-a['media_ms'] > 2000:
        return observations
    clean = [{k: v for k, v in s.items() if k not in ('ballTrail', 'ball_motion_start_ms', 'ball_motion_method')} for s in (a, b)]
    pair = observed_motion(video, clean, ball_gap_ms=2000, separate_bands=True)
    if not pair[-1].get('ballTrail'):
        return observations
    return [{**s, 'ballTrail': pair[-1]['ballTrail'],
             'ball_motion_start_ms': a['media_ms'],
             'ball_motion_method': 'BACKGROUND_AFFINE_PASS_ENDPOINTS'}
            if s is b else s for s in observations]


def foreground_polygons(instances, width, height, y_offset=0):
    """Conservative visible-person cutouts; no identity or hidden-body inference."""
    import cv2
    import numpy as np
    polygons = []
    for item in instances:
        if item.get('class_id') != 0:
            continue
        mask = cv2.dilate(item['mask'].astype('uint8'), np.ones((5, 5), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            if cv2.contourArea(contour) < 4:
                continue
            contour = cv2.approxPolyDP(contour, .5, True).reshape(-1, 2)
            if not 3 <= len(contour) <= 512 or len(polygons) >= 48:
                return None  # never silently omit a person because of payload limits
            polygons.append([[round(float(x)/width, 6), round(float(y+y_offset)/height, 6)] for x, y in contour])
    return polygons or None


def add_foreground(video, observations, deadline):
    """Measure occluders on arrow endpoint frames only, within the existing budget."""
    import cv2
    from native_player_segmentation import _instances
    from video_timebase import read_frame_at
    cap = cv2.VideoCapture(str(video))
    try:
        for sample in observations:
            if time.monotonic() >= deadline - 1:
                break
            if not sample.get('ballTrail'):
                continue
            ok, frame, pts = read_frame_at(cap, sample['media_ms']/1000)
            if not ok or abs(pts*1000-sample['media_ms']) > 2:
                continue
            height, width = frame.shape[:2]
            ys = [p[1] for p in sample['ballTrail']]
            if point(sample.get('ground')):
                ys.append(sample['ground'][1])
            top = max(0, int((min(ys)-.3)*height))
            bottom = min(height, int((max(ys)+.06)*height)+1)
            instances, _ = _instances(frame[top:bottom])
            polygons = foreground_polygons(instances, width, height, top)
            if polygons:
                sample['foreground'] = {'method': 'SOURCE_PERSON_MASK', 'frame_id': sample['frame_id'],
                                        'media_ms': round(pts*1000), 'polygons': polygons}
    finally:
        cap.release()


def compute(video, anchors, events, checkpoint=None):
    import cv2
    from player_tracking import track_player
    from motion_compensation import compute_motion_samples
    from match_room_contours import contour_segments, METHOD
    cv2.setNumThreads(2)
    deadline = time.monotonic() + TIMEOUT_S - 3
    output = {}
    def save():
        if checkpoint is not None:
            temporary = Path(str(checkpoint)+'.tmp')
            temporary.write_text(json.dumps(output))
            temporary.replace(checkpoint)
    for event in events[:MAX_EVENTS]:
        if time.monotonic() >= deadline:
            break
        observations = event.get('visual_samples') or []
        if not observations:
            continue
        start, end = event['proof']['proof_start_ms'], event['proof']['proof_end_ms']
        result = {'version': 1, 'source_video_sha256': event['source_video_sha256'],
                  'event_id': event['event_id'], 'method': 'TAP_OPTICAL_GROUND_PROXY', 'segments': [],
                  'observed_samples': pass_motion(video, event, observed_motion(video, observations))}
        output[event['event_id']] = result
        save()  # keep completed sparse graphics if the optional contour work times out
        try:
            add_foreground(video, result['observed_samples'], deadline)
        except (ImportError, OSError, ValueError, cv2.error):
            pass  # graphics remain optional; no unmasked replacement is invented
        save()
        diagnostic = {}
        try:
            contours = contour_segments(video, anchors, observations, start, end, deadline=deadline,
                                        diagnostics=diagnostic)
        except (ImportError, OSError, ValueError, cv2.error):
            contours = []
            diagnostic['status'] = 'CONTOUR_UNAVAILABLE'
        result['contour_diagnostics'] = diagnostic
        if contours:
            result.update(method=diagnostic.get('method', METHOD), segments=contours)
            save()
            continue
        seeds = [a for a in anchors if finite(a.get('t')) and start-1500 <= a['t']*1000 <= end+1500]
        # At most two short windows per event, nearest to actual visual evidence.
        seeds.sort(key=lambda a: min(abs(a['t']*1000-s['media_ms']) for s in observations))
        segments = []
        for seed_index, seed in enumerate(seeds[:2]):
            if time.monotonic() >= deadline:
                break
            track = track_player(video, [seed], span=1.5)
            for group in bind_segments(track['points'], observations, start, end):
                motion = compute_motion_samples(video, {'points': group['points']})
                add_motion(group, motion)
                group.pop('points')
                group['id'] = f'{seed_index}:{len(segments)}'
                segments.append(group)
        result['segments'] = segments
        save()
    return output


def _bounded_event(video, anchors, events):
    """One owned child, hard wall-clock bound; failure keeps sparse graphics."""
    if not anchors or not any(e.get('visual_samples') for e in events):
        return {}, 'NO_TRACK_INPUT'
    with tempfile.TemporaryDirectory(prefix='matchroom-track-') as work:
        request, result = Path(work)/'input.json', Path(work)/'output.json'
        request.write_text(json.dumps({'video': str(video), 'anchors': anchors, 'events': events[:MAX_EVENTS]}))
        try:
            subprocess.run([sys.executable, str(Path(__file__).resolve()), str(request), str(result)],
                           timeout=TIMEOUT_S, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return json.loads(result.read_text()), 'COMPLETED'
        except subprocess.TimeoutExpired:
            try:
                completed = json.loads(result.read_text())
                if isinstance(completed, dict) and completed:
                    return completed, 'PARTIAL_TIMEOUT'
            except (OSError, ValueError):
                pass
            return {}, 'TRACKING_UNAVAILABLE'
        except (subprocess.SubprocessError, OSError, ValueError):
            return {}, 'TRACKING_UNAVAILABLE'


def bounded_tracks(video, anchors, events):
    """One bounded child per distinct clip; repeated report cards share results.

    At most MAX_EVENTS sequential children, each hard-limited to TIMEOUT_S.
    A difficult earlier clip cannot consume a later clip's inference budget.
    """
    if not anchors or not any(e.get('visual_samples') for e in events):
        return {}, 'NO_TRACK_INPUT'
    unique,seen = [],set()
    for index,event in enumerate(events):
        key = event.get('event_id') or f'input:{index}'
        if key in seen or not event.get('visual_samples'):
            continue
        seen.add(key)
        unique.append(event)
        if len(unique) >= MAX_EVENTS:
            break
    output,statuses = {},[]
    for event in unique:
        result,status = _bounded_event(video,anchors,[event])
        output.update(result)
        statuses.append(status)
    if all(s == 'COMPLETED' for s in statuses):
        return output,'COMPLETED'
    if len(statuses) == 1:
        return output,statuses[0]
    return output,'PARTIAL_TIMEOUT' if 'PARTIAL_TIMEOUT' in statuses else 'TRACKING_PARTIAL'


if __name__ == '__main__':
    request = json.loads(Path(sys.argv[1]).read_text())
    result = Path(sys.argv[2])
    compute(**request, checkpoint=result)
    if not result.exists():
        result.write_text('{}')
