"""Prepare encrypted source-only inputs for the authorized pass-window probe."""
import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

import cv2
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from video_timebase import read_frame_at, grab_frame_time_seconds


def encoded(image):
    ok, pixels = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise ValueError('JPEG_FAILED')
    data = pixels.tobytes()
    return {'jpeg': base64.b64encode(data).decode(), 'sha256': hashlib.sha256(data).hexdigest(),
            'width': image.shape[1], 'height': image.shape[0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'anchors', 'wrapping-envelope', 'output', 'manifest'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    source_hash = hashlib.sha256(Path(args.video).read_bytes()).hexdigest()
    if source_hash != 'a659197551270a396fa5754239066c176fbacf2d5af400e63eea876ebfe06082':
        raise ValueError('SOURCE_MISMATCH')
    anchors = json.loads(Path(args.anchors).read_text())['anchors']
    references, frames = [], []
    cap = cv2.VideoCapture(args.video)
    try:
        for index in (1, 4, 5):
            anchor = next(a for a in anchors if a['i'] == index)
            ok, image, pts = read_frame_at(cap, anchor['t'])
            if not ok or abs(pts-anchor['t']) > .025:
                raise ValueError('ORIGINAL_SELECTION_FRAME_MISSING')
            h, w = image.shape[:2]
            b = anchor['box']
            crop = image[max(0, int(b['y']*h)):min(h, int((b['y']+b['h'])*h)+1),
                         max(0, int(b['x']*w)):min(w, int((b['x']+b['w'])*w)+1)]
            references.append({'reference_id': f'r{index}', 'media_ms': round(pts*1000),
                'box': b, 'target_point': anchor['target_point'], **encoded(crop)})
        ok, image, pts = read_frame_at(cap, 9.)
        while ok and pts <= 10.301:
            ms = round(pts*1000)
            frames.append({'frame_id': f's{ms:09d}', 'media_ms': ms, **encoded(image)})
            ok, pts, fallback = grab_frame_time_seconds(cap)
            if fallback:
                raise ValueError('SOURCE_TIMEBASE_MISSING')
            if ok:
                ok, image = cap.retrieve()
    finally:
        cap.release()
    if len(frames) != 40 or frames[0]['media_ms'] != 9000 or frames[-1]['media_ms'] != 10300:
        raise ValueError('SOURCE_WINDOW_INCOMPLETE')
    packet = {'packet_id': 'matchroom_pass_auto_20261103', 'phase': 'INITIAL',
        'start_ms': frames[0]['media_ms'], 'end_ms': frames[-1]['media_ms'],
        'core_start_ms': frames[0]['media_ms'], 'core_end_ms': frames[-1]['media_ms'],
        'reference_ids': [r['reference_id'] for r in references],
        'frame_ids': [f['frame_id'] for f in frames]}
    source = {'source_video_sha256': source_hash, 'reference_policy': 'CONSENSUS_RAW',
        'identity_reference_scope': packet['reference_ids'], 'references': references,
        'frames': frames, 'packet': packet}
    if sum(len(row['jpeg']) for group in ('references', 'frames') for row in source[group]) > 19_400_000:
        raise ValueError('REQUEST_IMAGE_BUDGET_EXCEEDED')
    data = json.dumps(source, separators=(',', ':')).encode()
    envelope = json.loads(Path(args.wrapping_envelope).read_text())
    public = serialization.load_pem_public_key(envelope['public'].encode())
    key, nonce = os.urandom(32), os.urandom(12)
    encode = lambda v: base64.b64encode(v).decode()
    envelope.update(key=encode(public.encrypt(key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
        algorithm=hashes.SHA256(), label=None))), data_nonce=encode(nonce),
        data=encode(AESGCM(key).encrypt(nonce, gzip.compress(data), b'matchroom-frames')),
        packet_sha256=hashlib.sha256(data).hexdigest())
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(envelope)+'\n')
    clean = {**source, **{group: [{k: v for k, v in row.items() if k != 'jpeg'} for row in source[group]]
        for group in ('references', 'frames')}}
    clean['packet_sha256'] = envelope['packet_sha256']
    clean['historical_action_results_used'] = False
    clean['reviewed_positions_supplied'] = False
    Path(args.manifest).write_text(json.dumps(clean, indent=2)+'\n')
    print(json.dumps({'frames': len(frames), 'references': len(references),
        'encrypted_bytes': output.stat().st_size, 'packet_sha256': envelope['packet_sha256']}))


if __name__ == '__main__':
    main()
