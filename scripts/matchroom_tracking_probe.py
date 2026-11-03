"""Replay the actual bounded graphics worker with explicit local source inputs.

No provider call, report write, deployment or runtime model download. The source
hash is required; anchors and observations must belong to that exact source.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from match_room_tracking import bounded_tracks


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('video','source-sha256','anchors','events','output'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    source=Path(args.video)
    if hashlib.sha256(source.read_bytes()).hexdigest()!=args.source_sha256:
        raise ValueError('Source checksum mismatch')
    anchors=json.loads(Path(args.anchors).read_text())
    if isinstance(anchors,dict):anchors=anchors['anchors']
    events=json.loads(Path(args.events).read_text())
    if not isinstance(events,list) or any(e.get('source_video_sha256')!=args.source_sha256 for e in events):
        raise ValueError('Events do not belong to this source')
    start=time.monotonic()
    tracks,status=bounded_tracks(str(source),anchors,events)
    Path(args.output).write_text(json.dumps({'status':status,'elapsed_seconds':time.monotonic()-start,
                                           'source_sha256':args.source_sha256,'tracks':tracks},indent=2)+'\n')


if __name__=='__main__':main()
