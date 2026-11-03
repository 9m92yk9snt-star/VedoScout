"""Bounded presentation-only reuse of tap tracking and camera compensation.

Never changes events, grades or identity authority. No provider/model calls.
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


def endpoint_arrow(previous, current, matrix, width, height):
    """Observed endpoint displacement in the current camera view; not a path."""
    import numpy as np
    if not point(previous.get('ground')) or not point(current.get('ground')):
        return None
    if not 0 < current['media_ms'] - previous['media_ms'] <= 1000:
        return None
    m = np.asarray(matrix, dtype=float)
    if m.shape != (3, 3) or not np.isfinite(m).all() or width <= 0 or height <= 0:
        return None
    p = m @ np.array([previous['ground'][0]*width, previous['ground'][1]*height, 1.])
    tail = [float(p[0]/width), float(p[1]/height)]
    tip = current['ground']
    if not point(tail) or not .008 <= math.dist(tail, tip) <= .3:
        return None
    return [tail, tip]


def observed_motion(video, observations):
    """Reuse the background affine estimator between observed source endpoints.

    Every intervening decoded frame must support the camera transform. Exclude
    a full-height band containing the actor endpoints; no player trajectory is
    assumed when selecting background pixels. Never connect ball observations.
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
            if not (point(previous.get('ground')) and point(current.get('ground'))):
                continue
            if not 0 < current['media_ms']-previous['media_ms'] <= 1000:
                continue
            start, end = previous['media_ms']/1000, current['media_ms']/1000
            frames = _read_window(cap, start-.02, end+.025, 1/30, seed_time=start)
            if len(frames) < 2 or abs(frames[0][0]-start) > .025 or abs(frames[-1][0]-end) > .025:
                continue
            cuts = _cut_flags(frames)
            h, w = frames[0][1].shape
            margin = max(previous.get('player_width', .1), current.get('player_width', .1))
            left = max(0., min(previous['ground'][0], current['ground'][0])-margin)
            right = min(1., max(previous['ground'][0], current['ground'][0])+margin)
            exclude = [(left*w, 0, (right-left)*w, h)]
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
                arrow = endpoint_arrow(previous, current, cumulative, w, h)
                if arrow:
                    current.update(groundTrail=arrow, motion_start_ms=previous['media_ms'],
                                   motion_method='BACKGROUND_AFFINE_ENDPOINTS')
    finally:
        cap.release()
    return samples


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
                  'observed_samples': observed_motion(video, observations)}
        output[event['event_id']] = result
        save()  # keep completed sparse graphics if the optional contour work times out
        try:
            contours = contour_segments(video, anchors, observations, start, end, deadline=deadline)
        except (ImportError, OSError, ValueError, cv2.error):
            contours = []
        if contours:
            result.update(method=METHOD, segments=contours)
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


def bounded_tracks(video, anchors, events):
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


if __name__ == '__main__':
    request = json.loads(Path(sys.argv[1]).read_text())
    result = Path(sys.argv[2])
    compute(**request, checkpoint=result)
    if not result.exists():
        result.write_text('{}')
