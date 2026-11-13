"""Diagnostic tap-to-detection binding. Never grants identity or skips LLM work."""
import math


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def bind_taps(rows, taps, *, source_sha, expected_source_sha):
    if not source_sha or source_sha != expected_source_sha:
        raise ValueError('SELECTION_SOURCE_MISMATCH')
    results = []
    for index, tap in enumerate(taps):
        result = {'tap_index': index, 'status': 'UNRESOLVED', 'track_id': None,
                  'proof_eligible': False, 'reason': 'INVALID_TAP'}
        results.append(result)
        point, seconds = tap.get('target_point'), tap.get('t')
        if (not number(seconds) or seconds < 0 or not isinstance(point, dict)
                or not all(number(point.get(k)) and 0 <= point[k] <= 1 for k in ('x', 'y'))):
            continue
        stamp = seconds * 1000
        nearby = [r for r in rows if number(r.get('media_ms')) and abs(r['media_ms']-stamp) <= 25]
        if not nearby:
            result['reason'] = 'NO_NEARBY_SOURCE_FRAME'
            continue
        row = min(nearby, key=lambda r: abs(r['media_ms']-stamp))
        result['media_ms'] = row['media_ms']
        if row.get('barrier'):
            result['reason'] = 'CUT_OR_TIME_GAP'
            continue
        width, height = row.get('width'), row.get('height')
        if not all(number(v) and v > 0 for v in (width, height)):
            result['reason'] = 'MISSING_IMAGE_DIMENSIONS'
            continue
        x, y = point['x']*width, point['y']*height
        matches = []
        for box in row.get('detection_boxes', []):
            if (len(box) == 4 and all(number(v) for v in box)
                    and box[0] <= x <= box[2] and box[1] <= y <= box[3]):
                matches.append(box)
        if len(matches) != 1:
            result['reason'] = 'AMBIGUOUS_OVERLAP' if matches else 'NO_PERSON_AT_TAP'
            continue
        # Require a visible detection, not a predicted tracker position. The
        # benchmark's ByteTrack output retains the original detection box.
        tracks = [t for t in row.get('tracks', []) if t.get('box') == matches[0]
                  and isinstance(t.get('id'), str) and t['id']]
        if len(tracks) != 1:
            result['reason'] = 'NO_UNIQUE_OBSERVED_TRACK'
            continue
        result.update(status='CANDIDATE_SEED', reason='UNIQUE_VISIBLE_DETECTION',
                      track_id=tracks[0]['id'])
    return results


def seed_component(rows, seed):
    """Restrict a candidate seed to consecutive observed frames, never bridge.

    Availability only: even a continuous component can contain identity swaps.
    Missing detections, duplicate IDs, cuts and time gaps split components.
    """
    if seed.get('status') != 'CANDIDATE_SEED':
        return None
    groups, current, previous = [], [], None
    for row in rows:
        stamp = row.get('media_ms')
        if not number(stamp) or (previous is not None and stamp <= previous):
            raise ValueError('NON_INCREASING_SOURCE_TIMESTAMPS')
        tracks = [t for t in row.get('tracks', []) if t.get('id') == seed.get('track_id')
                  and t.get('box') in row.get('detection_boxes', [])]
        split = row.get('barrier') or (previous is not None and stamp-previous > 120)
        if split or len(tracks) != 1:
            if current: groups.append(current)
            current = []
        if len(tracks) == 1 and not row.get('barrier'):
            current.append(stamp)
        previous = stamp
    if current: groups.append(current)
    matches = [g for g in groups if seed.get('media_ms') in g]
    if len(matches) != 1:
        return None
    group = matches[0]
    return {'track_id': seed['track_id'], 'start_ms':group[0], 'end_ms':group[-1],
            'observed_frames':len(group), 'proof_eligible':False,
            'status':'OBSERVED_CANDIDATE_COMPONENT', 'identity_verified':False}
