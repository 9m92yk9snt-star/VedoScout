"""Source-frame pass direction and fresh foreground for moving Match Room clips.

The line joins observed ball endpoints in each camera view. It is not a measured
trajectory between them. Incomplete sequences are discarded atomically.
"""
import time

METHOD = 'SOURCE_FRAME_BALL_DIRECTION'
MAX_FRAMES = 150
MAX_SEGMENTS = 16


def build_ball_playback(video, event, observations, deadline):
    import cv2
    import numpy as np
    from match_room_tracking import finite, point, foreground_polygons
    from player_tracking import _read_window, _cut_flags
    from motion_compensation import estimate_camera
    from native_player_segmentation import _instances
    from video_timebase import seek_with_preroll, grab_frame_time_seconds

    segments, failures = [], []
    cap = cv2.VideoCapture(str(video))
    try:
        for arrival in observations:
            method = arrival.get('ball_motion_method')
            if method not in ('BACKGROUND_AFFINE_BALL_ENDPOINTS', 'BACKGROUND_AFFINE_PASS_ENDPOINTS'):
                continue
            releases = [s for s in observations if s.get('media_ms') == arrival.get('ball_motion_start_ms') and point(s.get('ball'))]
            if len(releases) != 1 or not point(arrival.get('ball')):
                continue
            release = releases[0]
            start, end = release['media_ms'], arrival['media_ms']
            is_pass = method == 'BACKGROUND_AFFINE_PASS_ENDPOINTS'
            if not event['proof']['proof_start_ms'] <= start < end <= event['proof']['proof_end_ms'] or end-start > (2000 if is_pass else 300):
                continue
            if is_pass:
                receiver = (event.get('causal_chain') or {}).get('receiver_visual_id')
                if (event.get('canonical_action_type') != 'PASS' or event.get('canonical_outcome') != 'COMPLETED'
                        or not finite(event.get('contact_ms')) or abs(start-event['contact_ms']) > 80
                        or release.get('ball_phase') != 'RELEASE' or arrival.get('ball_phase') != 'RECEIVED'
                        or not receiver or arrival.get('receiver') != receiver
                        or sum(s.get('ball_phase') == 'RELEASE' and point(s.get('ball')) and abs(s['media_ms']-event['contact_ms']) <= 80 for s in observations) != 1
                        or sum(s.get('ball_phase') == 'RECEIVED' and s.get('receiver') == receiver and point(s.get('ball')) for s in observations) != 1):
                    continue
            elif any(start < s['media_ms'] < end for s in observations):
                continue
            if len(segments) >= MAX_SEGMENTS or time.monotonic() >= deadline-1:
                failures.append('BUDGET')
                break
            # A short source-bound fade after reception, only within the proof.
            until = min(end+250, event['proof']['proof_end_ms'])
            if event.get('localization_method') == 'EXPLICIT_SOURCE_POSITIONS':
                # Explicit unknown rows are hard stops; never fade past the
                # last observed endpoint into unobserved or uncertain video.
                until = end
            frames = _read_window(cap, start/1000-.001, until/1000+.001, 0, seed_time=start/1000)
            endpoint = next((i for i, f in enumerate(frames) if abs(f[0]*1000-end) <= 2), None)
            if (not 2 <= len(frames) <= MAX_FRAMES or endpoint is None
                    or abs(frames[0][0]*1000-start) > 2
                    or any(not 0 < b[0]-a[0] <= .075 for a, b in zip(frames, frames[1:]))
                    or any(_cut_flags(frames))):
                failures.append('SOURCE_FRAMES')
                continue
            h, w = frames[0][1].shape
            xs = [s[k][0] for s in (release, arrival) for k in ('ball', 'ground') if point(s.get(k))]
            margin = max(release.get('player_width', .1), arrival.get('player_width', .1))
            exclude = [(max(0., x-margin)*w, 0, (min(1., x+margin)-max(0., x-margin))*w, h) for x in xs]
            cameras = [np.eye(3)]
            for a, b in zip(frames, frames[1:]):
                if time.monotonic() >= deadline-1:
                    break
                matrix, _ = estimate_camera(a[1], b[1], exclude)
                if matrix is None:
                    break
                cameras.append(np.vstack([matrix, [0, 0, 1]]) @ cameras[-1])
            if len(cameras) != len(frames):
                failures.append('CAMERA_OR_BUDGET')
                continue
            inverse = np.linalg.inv(cameras[endpoint])
            initial = np.array([release['ball'][0]*w, release['ball'][1]*h, 1.])
            destination = inverse @ np.array([arrival['ball'][0]*w, arrival['ball'][1]*h, 1.])
            rows = []
            ok, t, fallback = seek_with_preroll(cap, start/1000)
            for source, camera in zip(frames, cameras):
                if time.monotonic() >= deadline-1:
                    break
                while ok and t < source[0]-.001:
                    ok, t, fallback = grab_frame_time_seconds(cap)
                if not ok or fallback or abs(t-source[0]) > .002:
                    break
                ok_pixels, pixels = cap.retrieve()
                if not ok_pixels:
                    break
                trail = [(camera @ p)[:2] / [w, h] for p in (initial, destination)]
                # Camera projection may legitimately put the recipient offscreen.
                # SVG clipping handles it; unbounded/invalid transforms do not.
                if not all(np.isfinite(p).all() and (p >= -1).all() and (p <= 2).all() for p in trail):
                    break
                height, width = pixels.shape[:2]
                top = max(0, int((min(p[1] for p in trail)-.3)*height))
                bottom = min(height, int((max(p[1] for p in trail)+.06)*height)+1)
                if bottom <= top:
                    break
                instances, _ = _instances(pixels[top:bottom])
                polygons = foreground_polygons(instances, width, height, top)
                if not polygons:
                    break
                ms = round(t*1000)
                fid = f'ball-source:{ms}'
                rows.append({'media_ms': ms, 'frame_id': fid,
                             'ballTrail': [p.tolist() for p in trail],
                             'foreground': {'method': 'SOURCE_PERSON_MASK', 'media_ms': ms,
                                            'frame_id': fid, 'polygons': polygons}})
            if len(rows) != len(frames):
                failures.append('FOREGROUND_OR_BUDGET')
                continue
            segments.append({'method': METHOD, 'start_ms': start, 'arrival_ms': end,
                             'end_ms': rows[-1]['media_ms'], 'reference_frames': [release['frame_id'], arrival['frame_id']],
                             'samples': rows})
    finally:
        cap.release()
    return segments, {'status': 'COMPLETE' if segments else 'UNAVAILABLE', 'failures': failures}
