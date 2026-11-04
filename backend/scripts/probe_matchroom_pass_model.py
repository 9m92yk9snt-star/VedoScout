"""One fresh, source-only pass-window request through the existing reader.

No reviewed ball positions, historical action results or expected outcome enter
the request. This isolated probe does not write a report or deploy anything.
"""
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sequence_pilot import packet_items, parse_response, resolve_response
from sequence_pilot_transport import run_jobs
from match_room import from_receipts
from sequence_report_adapter import canonical_bundle


def unpack(path):
    envelope = json.loads(Path(path).read_text())
    decode = base64.b64decode
    wrapping_key = hashlib.scrypt(os.environ['EMERGENT_LLM_KEY'].encode(),
        salt=decode(envelope['salt']), n=16384, r=8, p=1, dklen=32)
    pem = AESGCM(wrapping_key).decrypt(decode(envelope['nonce']),
        decode(envelope['wrapped']), b'matchroom-55')
    private = serialization.load_pem_private_key(pem, password=None)
    content_key = private.decrypt(decode(envelope['key']),
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    data = gzip.decompress(AESGCM(content_key).decrypt(decode(envelope['data_nonce']),
        decode(envelope['data']), b'matchroom-frames'))
    if hashlib.sha256(data).hexdigest() != envelope['packet_sha256']:
        raise ValueError('SOURCE_PACKET_CHANGED')
    return json.loads(data), envelope['packet_sha256']


def main():
    source, packet_sha = unpack('testdata/matchroom-pass-auto/packet.enc.json')
    output = {'scope': 'One fresh source-window model request; no full-report run or deployment.',
              'source_video_sha256': source['source_video_sha256'],
              'input_packet_sha256': packet_sha, 'historical_action_results_used': False,
              'reviewed_positions_supplied': False, 'model_calls_requested': 1}
    with tempfile.TemporaryDirectory(prefix='matchroom-pass-auto-') as work:
        manifest = {k: source[k] for k in ('source_video_sha256', 'reference_policy', 'identity_reference_scope')}
        for group in ('references', 'frames'):
            manifest[group] = []
            for index, row in enumerate(source[group]):
                pixels = base64.b64decode(row['jpeg'])
                if hashlib.sha256(pixels).hexdigest() != row['sha256']:
                    raise ValueError('SOURCE_IMAGE_CHANGED')
                path = Path(work) / f'{group}-{index}.jpg'
                path.write_bytes(pixels)
                manifest[group].append({**{k: v for k, v in row.items() if k != 'jpeg'}, 'path': str(path)})
        packet = source['packet']
        items = packet_items(manifest, packet)
        output['manifest'] = {**manifest, **{group: [{k: v for k, v in row.items() if k != 'path'}
            for row in manifest[group]] for group in ('references', 'frames')}}
        output['packet'] = packet
        output['prompt_texts'] = [item['text'] for item in items if item['type'] == 'text']
        job = {'packet_id': packet['packet_id'], 'items': items, 'max_output_tokens': 12000,
               'image_detail': 'high', 'reasoning_effort': 'medium'}
        receipts = run_jobs([job], 'emergent', 'gpt-6-astra', deadline=time.monotonic()+185,
                            per_call_s=180, workers=1)
        output['receipts'] = receipts
        completed = len(receipts) == 1 and receipts[0].get('status') == 'COMPLETED'
        output['status'] = 'MODEL_OBSERVATIONS_RETURNED' if completed else 'MODEL_REQUEST_FAILED'
        if completed:
            receipt = receipts[0]
            try:
                parsed = parse_response(receipt['raw_response'])
                resolved = resolve_response(parsed, manifest, packet, receipt)
                output['resolved'] = resolved
                output['accepted_visual_samples'] = {event['event_id']: from_receipts(event, manifest, receipts)
                    for event in resolved['events'] if event['selected_player'] is True}
                result = {'source_video_sha256': source['source_video_sha256'],
                    'status': 'MODEL_OBSERVATIONS_RETURNED', 'fresh_end_to_end_run': True,
                    'historical_action_results_used': False, 'model_jobs_completed': 1,
                    'target_events': [e for e in resolved['events'] if e['selected_player'] is True],
                    'questions': resolved['questions']}
                try:
                    output['canonical'] = canonical_bundle(result, manifest, receipts)
                except ValueError as exc:
                    output['canonical_error'] = str(exc)
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                output['parse_error_type'] = type(exc).__name__
        destination = Path(os.environ['RUNNER_TEMP']) / 'matchroom-pass-auto-results.json'
        destination.write_text(json.dumps(output, indent=2)+'\n')
        print(json.dumps({'status': output['status'], 'source_frames': len(manifest['frames']),
            'elapsed_seconds': receipts[0].get('elapsed_seconds') if receipts else None,
            'canonical_events': len(output.get('canonical', {}).get('events', [])),
            'sample_counts': {k: len(v) for k, v in output.get('accepted_visual_samples', {}).items()}}))
        return 0 if completed else 3


if __name__ == '__main__':
    raise SystemExit(main())
