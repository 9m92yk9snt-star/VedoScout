"""Source-frame graphics, independent of score and event approval.

No coordinates are inferred from kit, profile, timestamps or another video.
Missing/cropped/ambiguous observations fail closed, without failing a report.
"""
import math
import json

INSTRUCTION = """
For Match Room presentation, optionally add visual_samples to selected-player
actions only, at most 12 samples TOTAL across this response. Prioritise supplied
contact and outcome frames; do not expand the response with dense tracks:
[{"frame":"supplied source frame ID","actor":"this action actor",
"plane":"FULL_FRAME","confidence":"HIGH","visible":true,
"ground":[x,y],"player_width":0.06,"ball":[x,y],
"active_ball_verified":true,"camera_static_from_previous":false}].
Coordinates are normalized 0..1 in the FULL uncropped source image. ground is
the visible player's contact with the pitch; player_width is the visible body
width relative to image width. Include only clearly visible, confidently located
points. Omit ball unless the active ball is distinguishable from spare balls.
Omit ground if feet are occluded. Do not estimate hidden positions or destinations.
Never use reference crops or detail crops as the FULL_FRAME coordinate plane.
camera_static_from_previous=true ONLY when consecutive samples show the same
continuous camera view without pan, zoom or cut. Omit uncertain samples entirely.
These optional observations must never change event identity, outcome or scores.
"""


def number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def point(v):
    return (isinstance(v, list) and len(v) == 2
            and all(number(x) and 0 <= x <= 1 for x in v))


def samples(rows, *, actor, frames, start, end, allowed=None):
    """Only full-frame observations of this actor in this action's source span."""
    result = {}
    for row in rows[:12] if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        fid = row.get('frame')
        f = frames.get(fid) if isinstance(fid, str) else None
        if not isinstance(f, dict) or f.get('source_crop_box') or (allowed is not None and fid not in allowed):
            continue
        ms = f.get('media_ms')
        if (not number(ms) or not start <= ms <= end or row.get('actor') != actor
                or row.get('plane') != 'FULL_FRAME' or row.get('confidence') != 'HIGH'
                or row.get('visible') is not True):
            continue
        item = {'frame_id': fid, 'media_ms': ms}
        width = row.get('player_width')
        if point(row.get('ground')) and number(width) and .005 <= width <= .4:
            item.update(ground=row['ground'], player_width=width)
        if point(row.get('ball')) and row.get('active_ball_verified') is True:
            item['ball'] = row['ball']
        if len(item) > 2:
            item['camera_static_from_previous'] = row.get('camera_static_from_previous') is True
            result[ms] = item
    return sorted(result.values(), key=lambda r: r['media_ms'])


def presentation(event, samples_=None):
    proof = event['proof']
    start, end = proof['proof_start_ms'], proof['proof_end_ms']
    contact = event.get('contact_ms')
    if contact is None:
        contact = proof['frame_ms']
    outcome = proof.get('outcome_ms')
    kind = event.get('canonical_action_type', 'Action').title()
    stops = [{'media_ms': contact, 'label': kind, 'phase': 'action'}]
    for movement in event.get('movement_observations') or []:
        cited = proof.get('cited_frames') or {}
        middle = movement.get('movement_frames') or []
        ms = cited.get(middle[0]) if middle else None
        if number(ms) and start <= ms <= end:
            stops.append({'media_ms': ms, 'label': movement['type'].replace('_', ' ').title(),
                          'phase': 'action', 'caption': movement['visible_movement'][:240]})
    if number(outcome) and contact < outcome <= end:
        stops.append({'media_ms': outcome, 'label': str(event.get('canonical_outcome', 'Result')).replace('_', ' ').title(), 'phase': 'result'})
    return {'version': 1, 'event_id': event['event_id'],
            'source_video_sha256': event['source_video_sha256'],
            'coordinate_space': 'FULL_FRAME_NORMALIZED',
            'start_ms': start, 'end_ms': end, 'stops': sorted(stops, key=lambda s:s['media_ms']),
            'samples': samples_ if isinstance(samples_, list) else [],
            'observation': ' '.join(event.get('details') or [])[:1000]}


def from_receipts(event, manifest, receipts):
    """Rebuild graphics from checked model receipts, not intermediate coordinates."""
    frames = {f['frame_id']: f for f in manifest['frames']}
    for receipt in receipts:
        prefix = str(receipt.get('packet_id')) + ':'
        scope = event.get('actor_scope', '')
        if not scope.startswith(prefix):
            continue
        try:
            text = receipt['raw_response'].strip()
            if text.startswith('```'):
                text = '\n'.join(text.splitlines()[1:-1])
            plays = json.loads(text).get('plays', [])
            index = int(scope[len(prefix):])
            play = plays[index]
            for action in play.get('actions', []):
                key = scope + ':' + str(action.get('action_id'))
                if key not in event.get('source_action_keys', []) or action.get('actor') != event.get('actor'):
                    continue
                return samples(action.get('visual_samples'), actor=event['actor'], frames=frames,
                               start=event['start_ms'], end=event['end_ms'])
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            continue
    return []
