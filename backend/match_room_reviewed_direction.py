"""Project an explicitly reviewed direction; never create ball observations."""
import hashlib
import time

import cv2
import numpy as np


def build_reviewed_direction(video, event_id, source_sha256, review, deadline):
    from video_timebase import seek_with_preroll, grab_frame_time_seconds
    from motion_compensation import estimate_camera
    from native_player_segmentation import _instances
    from match_room_tracking import foreground_polygons, point

    if (review.get('status') != 'OWNER_APPROVED_DIRECTION'
            or review.get('event_id') != event_id
            or review.get('source_video_sha256') != source_sha256
            or not review.get('review_id')
            or not isinstance(review.get('direction'), list)
            or len(review['direction']) != 2 or not all(point(p) for p in review['direction'])):
        raise ValueError('REVIEWED_DIRECTION_BINDING_REQUIRED')
    ref, start, end = (review.get(k) for k in ('reference_ms', 'start_ms', 'end_ms'))
    if (any(type(t) is not int for t in (ref, start, end))
            or not 0 <= ref <= start < end or end-ref > 1500):
        raise ValueError('REVIEWED_DIRECTION_WINDOW_INVALID')
    animation = review.get('animation')
    if animation is not None and (
            not isinstance(animation, dict)
            or animation.get('kind') != 'RECONSTRUCTED_PASS'
            or type(animation.get('arrival_ms')) is not int
            or not start < animation['arrival_ms'] <= end):
        raise ValueError('REVIEWED_DIRECTION_ANIMATION_INVALID')
    digest = hashlib.sha256()
    with open(video, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != source_sha256:
        raise ValueError('REVIEWED_DIRECTION_SOURCE_MISMATCH')
    cap = cv2.VideoCapture(str(video))
    rows, previous, previous_ms = [], None, None
    camera = np.eye(3)
    try:
        ok, stamp, fallback = seek_with_preroll(cap, ref/1000)
        while ok and stamp*1000 < ref-2:
            ok, stamp, fallback = grab_frame_time_seconds(cap)
        while ok and stamp*1000 <= end+2:
            ms = round(stamp*1000)
            if fallback or time.monotonic() >= deadline:
                raise ValueError('REVIEWED_DIRECTION_TIME_OR_BUDGET')
            ok_pixels, pixels = cap.retrieve()
            if not ok_pixels:
                raise ValueError('REVIEWED_DIRECTION_FRAME_UNAVAILABLE')
            h, w = pixels.shape[:2]
            gray = cv2.cvtColor(cv2.resize(pixels, (480, round(h*480/w))), cv2.COLOR_BGR2GRAY)
            gh, gw = gray.shape
            if previous is None:
                if abs(ms-ref) > 2:
                    raise ValueError('REVIEWED_DIRECTION_REFERENCE_UNAVAILABLE')
                anchors = [np.array([p[0]*gw, p[1]*gh, 1.]) for p in review['direction']]
            else:
                if not 0 < ms-previous_ms <= 75:
                    raise ValueError('REVIEWED_DIRECTION_FRAME_GAP')
                # Exclude the whole player band. Only background may anchor
                # a direction approved on one reference picture.
                matrix, _ = estimate_camera(previous, gray, [(0, gh*.42, gw, gh*.23)])
                if matrix is None:
                    raise ValueError('REVIEWED_DIRECTION_CAMERA_UNAVAILABLE')
                camera = np.vstack([matrix, [0, 0, 1]]) @ camera
            trail = [((camera @ p)[:2]/[gw, gh]).tolist() for p in anchors]
            if animation is not None:
                # Display geometry only: never promote interpolated tips to
                # ball observations, contacts, or event evidence.
                progress = min(1., max(0., (ms-start)/(animation['arrival_ms']-start)))
                trail[1] = (np.asarray(trail[0]) + progress*(np.asarray(trail[1])-trail[0])).tolist()
            if not all(point(p) for p in trail):
                raise ValueError('REVIEWED_DIRECTION_OUT_OF_FRAME')
            if start-2 <= ms <= end+2:
                top = max(0, int((min(p[1] for p in trail)-.25)*h))
                bottom = min(h, int((max(p[1] for p in trail)+.06)*h)+1)
                instances, _ = _instances(pixels[top:bottom])
                polygons = foreground_polygons(instances, w, h, top)
                if not polygons:
                    raise ValueError('REVIEWED_DIRECTION_FOREGROUND_UNAVAILABLE')
                fid = f'reviewed-direction:{ms}'
                rows.append({'media_ms': ms, 'frame_id': fid, 'directionTrail': trail,
                             'foreground': {'method': 'SOURCE_PERSON_MASK', 'media_ms': ms,
                                            'frame_id': fid, 'polygons': polygons}})
            previous, previous_ms = gray, ms
            ok, stamp, fallback = grab_frame_time_seconds(cap)
        if not rows or abs(rows[0]['media_ms']-start) > 2 or abs(rows[-1]['media_ms']-end) > 2:
            raise ValueError('REVIEWED_DIRECTION_INCOMPLETE')
        return {**review, 'method': 'REVIEWED_DIRECTION_BACKGROUND_AFFINE',
                'is_measured_ball_trajectory': False, 'playback_status': 'PENDING', 'samples': rows}
    finally:
        cap.release()
