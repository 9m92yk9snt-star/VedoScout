"""Bind explicit localization to its original selection and finalized event.

This checks provenance and uncertainty, not visual correctness. Observations
remain model observations, never additional human taps or dense tracks.
"""
import hashlib
import json

from sequence_run_checkpoint import reusable_receipt


def selection_digest(selection):
    return hashlib.sha256(json.dumps(selection, sort_keys=True).encode()).hexdigest()


def bound_samples(event, selection, result, validate_response, *, packet='positions_001'):
    """Return ordered evidence including uncertainty barriers, or reject input.

    Caller supplies the strict response validator used by the request producer.
    Keeping empty source rows prevents later motion code from skipping across
    a missing observation to join two otherwise valid endpoints.
    """
    if (result.get('source_video_sha256') != event.get('source_video_sha256')
            or result.get('event_id') != event.get('event_id')
            or result.get('original_selection_values_sha256') != selection_digest(selection)):
        raise ValueError('LOCALIZATION_SOURCE_SELECTION_EVENT_MISMATCH')
    receipt, request = result.get('receipt') or {}, result.get('request') or {}
    digest = request.get('payload_sha256')
    if (not isinstance(digest, str) or len(digest) != 64
            or any(c not in '0123456789abcdef' for c in digest)
            or not reusable_receipt(receipt, request, provider='emergent', model='gpt-6-astra',
                                    packet_id=packet)):
        raise ValueError('LOCALIZATION_RECEIPT_MISMATCH')
    frames = result.get('frames')
    if not isinstance(frames, list) or not frames or len(frames) > 160:
        raise ValueError('LOCALIZATION_FRAME_MANIFEST_REQUIRED')
    image_hashes = {r.get('sha256') for r in receipt.get('images', [])}
    previous = -1
    for frame in frames:
        ms = frame.get('media_ms')
        if (type(ms) is not int or ms <= previous or frame.get('frame_id') != f's{ms:09}'
                or not frame.get('sha256') or frame['sha256'] not in image_hashes):
            raise ValueError('LOCALIZATION_SOURCE_FRAMES_MISMATCH')
        previous = ms
    rows = validate_response(receipt['raw_response'], frames)
    proof = event['proof']
    context = result.get('context_after_ms', 0)
    if context:
        from match_room import position_window
        lo, hi, permitted = position_window(event)
        if context != 750 or permitted != 750 or result.get('window_ms') != [lo, hi]:
            raise ValueError('LOCALIZATION_CONTEXT_NOT_IN_ENCODED_CLIP')
    samples = []
    identified = False
    for row in rows:
        if not proof['proof_start_ms'] <= row['media_ms'] <= proof['proof_end_ms']+context:
            continue
        sample = {'frame_id': row['frame'], 'media_ms': row['media_ms'],
                  'identity_status': row['target_status'],
                  'active_ball_status': row['active_ball_status']}
        if row['target_status'] == 'UNCERTAIN':
            identified = False
        if row['target_status'] == 'CONFIRMED':
            identified = True
            box = row.get('box')
            if row.get('ground') is not None and box is not None and .005 <= box[2] <= .4:
                sample.update(ground=row['ground'], player_width=box[2], player_box=box)
        # A continuously observed kick can leave its player behind. Keep the
        # active ball after ABSENT only following confirmed identity; a cut or
        # unresolved identity resets that authority. Camera continuity is
        # checked again by the motion/arrow layer.
        if identified and row.get('ball') is not None:
            sample['ball'] = row['ball']
        samples.append(sample)
    return samples
