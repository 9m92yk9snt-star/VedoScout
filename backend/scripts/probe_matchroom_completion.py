"""One encrypted source-only completion probe; no report writes or deployment."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import base64
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.probe_matchroom_pass_model import unpack
from match_room_localization import validate
from match_room_position_evidence import bound_samples
from sequence_pilot_transport import build_request, run_jobs


def restore_packet(root, destination):
    manifest = json.loads((root/'manifest.json').read_text())
    parts = manifest['parts']
    if not parts or [p['name'] for p in parts] != [f'{i:03}.bin' for i in range(len(parts))]:
        raise ValueError('ENCRYPTED_PARTS_CHANGED')
    payload = bytearray()
    for part in parts:
        data = (root/part['name']).read_bytes()
        if hashlib.sha256(data).hexdigest() != part['sha256']:
            raise ValueError('ENCRYPTED_PART_CHANGED')
        payload.extend(data)
    if hashlib.sha256(payload).hexdigest() != manifest['sha256']:
        raise ValueError('ENCRYPTED_PACKET_CHANGED')
    destination.write_bytes(payload)
    source, digest = unpack(destination)
    if digest != manifest['packet_sha256']:
        raise ValueError('SOURCE_PACKET_CHANGED')
    return source, digest


def prepare_job(source, work):
    job = source['job']
    for item in job['items']:
        if item['type'] != 'image':
            continue
        sha = item['sha256']
        data = base64.b64decode(source['images'][sha], validate=True)
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError('SOURCE_IMAGE_CHANGED')
        path = work/(sha+'.jpg')
        path.write_bytes(data)
        item['path'] = str(path)
    _, _, rebuilt = build_request('emergent', 'gpt-6-astra', job['items'],
        reasoning_effort=job['reasoning_effort'], image_detail=job['image_detail'],
        max_output_tokens=job['max_output_tokens'])
    if rebuilt != source['record']['request']:
        raise ValueError('PREPARED_REQUEST_CHANGED')
    return job


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--packet', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--run-model', action='store_true')
    args = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='matchroom-completion-') as directory:
        work = Path(directory)
        source, digest = restore_packet(args.packet, work/'packet.json')
        job = prepare_job(source, work)
        record = source['record']
        output = {'scope': 'ONE_MISSING_CLIP_EDGE_ONLY', 'packet_sha256': digest,
                  'record': record, 'model_calls_requested': int(args.run_model),
                  'report_written': False, 'deployed': False, 'status': 'PREFLIGHT_ONLY'}
        if args.run_model:
            # The total deadline equals per-call time: the transport's 429
            # retry predicate cannot reserve a second full call plus its wait.
            receipts = run_jobs([job], 'emergent', 'gpt-6-astra',
                                deadline=time.monotonic()+150, per_call_s=150, workers=1)
            if len(receipts) != 1:
                raise ValueError('EXACTLY_ONE_RECEIPT_REQUIRED')
            record['receipt'] = receipts[0]
            output['status'] = 'MODEL_REQUEST_FAILED'
            if receipts[0].get('status') == 'COMPLETED':
                try:
                    output['samples'] = bound_samples(source['event'], source['selection'], record,
                                                      validate, packet=job['packet_id'])
                    output['status'] = 'OBSERVATIONS_RETURNED'
                except ValueError as exc:
                    output['status'] = 'OBSERVATIONS_REJECTED'
                    output['error'] = str(exc)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output))
        # Source-bound receipt only; never images, request bodies or secrets.
        print('MATCHROOM_COMPLETION_RESULT='+json.dumps(output), flush=True)
        return 0 if output['status'] in ('PREFLIGHT_ONLY', 'OBSERVATIONS_RETURNED') else 3


if __name__ == '__main__':
    raise SystemExit(main())
