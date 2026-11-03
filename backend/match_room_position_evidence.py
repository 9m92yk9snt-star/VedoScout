"""Bind explicit localization to its original selection and finalized event.

This checks provenance and uncertainty, not visual correctness. Observations
remain model observations, never additional human taps or dense tracks.
"""
import hashlib
import json

from sequence_run_checkpoint import reusable_receipt


def selection_digest(selection):
    return hashlib.sha256(json.dumps(selection, sort_keys=True).encode()).hexdigest()


def bound_samples(event, selection, result, validate_response):
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
                                    packet_id='positions_001')):
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
    samples = []
    for row in rows:
        if not proof['proof_start_ms'] <= row['media_ms'] <= proof['proof_end_ms']:
            continue
        sample = {'frame_id': row['frame'], 'media_ms': row['media_ms'],
                  'identity_status': row['target_status'],
                  'active_ball_status': row['active_ball_status']}
        if row['target_status'] == 'CONFIRMED':
            box = row.get('box')
            if row.get('ground') is not None and box is not None and .005 <= box[2] <= .4:
                sample.update(ground=row['ground'], player_width=box[2], player_box=box)
            if row.get('ball') is not None:
                sample['ball'] = row['ball']
        samples.append(sample)
    return samples
