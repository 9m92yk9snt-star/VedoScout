"""Lossless external storage for large presentation data; never truncate graphics."""
import hashlib
import json
from pathlib import Path

INLINE_BYTES = 128_000

async def publish_graphics(row, directory, publish):
    room = row.get('match_room')
    if not isinstance(room, dict):
        return
    payload = json.dumps(room, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    if len(payload) <= INLINE_BYTES:
        return
    digest = hashlib.sha256(payload).hexdigest()
    path = Path(directory) / ('graphics-' + digest + '.json')
    path.write_bytes(payload)
    url = await publish(path, 'application/json')
    if not isinstance(url, str) or not url:
        raise RuntimeError('SEQUENCE_GRAPHICS_PUBLISH_FAILED')
    row['match_room'] = {k: room[k] for k in (
        'version', 'event_id', 'source_video_sha256', 'coordinate_space',
        'start_ms', 'end_ms', 'contact_ms', 'observation') if k in room}
    row['match_room']['graphics_asset'] = {'url': url, 'sha256': digest, 'bytes': len(payload)}
