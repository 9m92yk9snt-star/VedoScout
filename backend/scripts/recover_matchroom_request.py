"""One isolated exact-request diagnostic at the existing 210-second maximum.

This does not change production deadlines or bypass checkpoint validation.
Completed responses must reproduce their original wire hashes before paid work.
"""
import hashlib
from pathlib import Path
import time

import sequence_pilot as pilot
import sequence_pilot_transport as transport
import sequence_report_runtime as runtime
from sequence_run_checkpoint import reusable_receipt
from scripts.run_sequence_pilot import fresh_original_manifest, original_spatial_items, FRESH_IDENTITY_INSTRUCTION


def request_items(manifest, packet, output):
    packet['contact_sequence_evidence'] = True
    items = pilot.packet_items(manifest, packet)
    items.insert(1, {'type': 'text', 'text': FRESH_IDENTITY_INSTRUCTION})
    spatial, _ = original_spatial_items(manifest, packet, output / packet['packet_id'])
    prefix = len(pilot.packet_items(manifest, {**packet, 'frame_ids': []})) + 1
    items[prefix:prefix] = spatial
    return items


def recover(video, selection, prior_path, work):
    import json
    prior = pilot.read_json(prior_path)
    selection_sha = hashlib.sha256(json.dumps(selection, sort_keys=True).encode()).hexdigest()
    source = pilot.digest(video)
    checkpoint = runtime.retained_retry(prior, source, selection_sha)
    if (prior.get('full_report_status') != 'failed' or not checkpoint
            or prior.get('raw_marker_anchors') != selection['raw_marker_anchors']):
        raise ValueError('EXACT_RETRY_INPUTS_CHANGED')
    inputs = work / 'recovery-input'
    (inputs / 'video').mkdir(parents=True, exist_ok=False)
    (inputs / 'video/source.mp4').symlink_to(video.resolve())
    pilot.write_json(inputs / 'anchors.json', selection)
    (inputs / 'SHA256SUMS').write_text(''.join(
        f'{pilot.digest(inputs / name)}  {name}\n' for name in ('video/source.mp4', 'anchors.json')))
    manifest = fresh_original_manifest(pilot.prepare(inputs, work / 'recovery-prepared',
        scene_packets=True, max_edge=1280))
    if manifest['original_taps_sha256'] != checkpoint['original_taps_sha256']:
        raise ValueError('ORIGINAL_SELECTION_FILE_CHANGED')
    saved = {r['packet_id']: r for r in checkpoint['receipts']}
    pending, validated = [], []
    for packet in manifest['packets']:
        items = request_items(manifest, packet, work / 'recovery-spatial')
        _, _, request = transport.build_request('emergent', 'gpt-6-astra', items,
            reasoning_effort='medium', image_detail='high')
        old = saved.get(packet['packet_id'], {})
        if old.get('status') == 'COMPLETED':
            if not reusable_receipt(old, request, provider='emergent', model='gpt-6-astra', packet_id=packet['packet_id']):
                raise ValueError('COMPLETED_REQUEST_CHANGED')
            pilot.resolve_response(pilot.parse_response(old['raw_response']), manifest, packet, old)
            validated.append(packet['packet_id'])
        else:
            pending.append((packet, items, request))
    if len(pending) != 1 or len(validated) != len(manifest['packets']) - 1:
        raise ValueError('ONE_MISSING_REQUEST_REQUIRED')
    packet, items, request = pending[0]
    summary = {'scope': 'Isolated exact request with the existing maximum call duration; production defaults unchanged',
        'packet_id': packet['packet_id'], 'source_video_sha256': source,
        'request_sha256': request['payload_sha256'], 'payload_bytes': request['payload_bytes'],
        'source_frames': len(packet['frame_ids']), 'validated_completed_packet_ids': validated,
        'per_call_seconds': transport.MAX_CALL_SECONDS, 'expected_actions_supplied': False}
    pilot.write_json(work / 'recovery-diagnostic.json', summary)
    print(json.dumps(summary), flush=True)
    receipts = transport.run_jobs([{'packet_id': packet['packet_id'], 'items': items,
        'reasoning_effort': 'medium', 'image_detail': 'high'}], 'emergent', 'gpt-6-astra',
        deadline=time.monotonic() + transport.MAX_CALL_SECONDS + 2,
        per_call_s=transport.MAX_CALL_SECONDS, workers=1)
    receipt = receipts[0]
    pilot.write_json(work / 'recovery-receipt.json', receipt)
    if receipt.get('status') != 'COMPLETED':
        raise RuntimeError('ISOLATED_REQUEST_FAILED')
    pilot.resolve_response(pilot.parse_response(receipt['raw_response']), manifest, packet, receipt)
    summary.update(status='COMPLETED_AND_REBOUND', elapsed_seconds=receipt.get('elapsed_seconds'))
    pilot.write_json(work / 'recovery-diagnostic.json', summary)
    checkpoint['receipts'] = [receipt if r['packet_id'] == packet['packet_id'] else r for r in checkpoint['receipts']]
    prior['sequence_retry'] = checkpoint
    destination = work / 'recovery-report-document.json'
    pilot.write_json(destination, prior)
    return destination
