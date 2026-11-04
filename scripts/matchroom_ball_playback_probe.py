"""Replay the review-only pass fixture through the real bounded worker.

Requires the checksum-matched original source and its original exported anchors.
Does not update a report, claim automatic extraction, or call a provider.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from match_room_tracking import bounded_tracks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'anchors', 'output'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--require-stance', action='store_true', help='Also require the complete nearby-tap player contour')
    args = parser.parse_args()
    fixture = json.loads((ROOT/'docs/matchroom-ball-playback-validation.json').read_text())
    if hashlib.sha256(Path(args.video).read_bytes()).hexdigest() != fixture['source_sha256']:
        raise ValueError('Source checksum mismatch')
    anchors = json.loads(Path(args.anchors).read_text())
    if isinstance(anchors, dict):
        anchors = anchors['anchors']
    event = fixture['review_fixture']['event']
    started = time.monotonic()
    tracks, status = bounded_tracks(args.video, anchors, [event])
    output = {'status': status, 'elapsed_seconds': time.monotonic()-started, 'tracks': tracks}
    Path(args.output).write_text(json.dumps(output, indent=2)+'\n')
    arrows = tracks.get(event['event_id'], {}).get('ball_playback', [])
    if status != 'COMPLETED' or len(arrows) != 1 or len(arrows[0]['samples']) != 27:
        raise AssertionError('Complete moving pass sequence unavailable; inspect saved diagnostics')
    if args.require_stance:
        player = tracks.get(event['event_id'], {})
        if (player.get('method') != 'TAP_OBSERVATION_BOUND_CONTOUR' or len(player['segments']) != 1
                or len(player['segments'][0]['samples']) != 35):
            raise AssertionError('Complete combined player/ball sequence unavailable')
    print(f"PASS: 27 source frames in {output['elapsed_seconds']:.3f}s")


if __name__ == '__main__':
    main()
