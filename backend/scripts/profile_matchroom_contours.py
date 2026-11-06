"""Offline contour profiling from an exported report and its exact source video.

No model-provider calls, report writes or deployment. Uses the repository's
pinned OpenCV segmenter; these timings are not ONNX/live acceptance evidence.
"""
import argparse
import cProfile
import hashlib
import json
import os
from pathlib import Path
import pstats
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--timestamp', required=True)
    parser.add_argument('--model', choices=('small', 'medium'), default='small')
    parser.add_argument('--seconds', type=float, default=90)
    parser.add_argument('--one-cpu', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 5 <= args.seconds <= 420:
        parser.error('--seconds must be between 5 and 420')
    if args.one_cpu:
        if not hasattr(os, 'sched_setaffinity'):
            parser.error('--one-cpu requires CPU affinity support')
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    report = json.loads(args.report.read_text())
    matches = [c for c in report['full_report']['video_comments']
               if c['timestamp'] == args.timestamp]
    if len(matches) != 1:
        parser.error('timestamp must identify exactly one exported clip')
    room = matches[0]['match_room']
    with args.video.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if digest != room['source_video_sha256']:
        parser.error('video does not match the exported source SHA-256')
    if not 0 < room['end_ms']-room['start_ms'] <= 1500:
        parser.error('choose a single contour window of at most 1500ms')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ['SCOUTMEPLAY_MATCHROOM_ENGINE'] = 'opencv'
    import cv2
    from native_player_segmentation import PersonSegmenter
    from match_room_position_contours import contour_segments, refinement_model
    cv2.setNumThreads(2)
    started = time.monotonic()
    model = refinement_model() if args.model == 'medium' else PersonSegmenter()
    load_seconds = time.monotonic()-started
    profile = cProfile.Profile()
    diagnostic = {}
    started = time.monotonic()
    profile.enable()
    segments = contour_segments(args.video, room['samples'], room['start_ms'], room['end_ms'],
                                deadline=started+args.seconds, diagnostics=diagnostic, segmenter=model)
    profile.disable()
    metadata = {'engine': 'opencv', 'opencv_version': cv2.__version__,
                'source_video_sha256': digest, 'event_id': room['event_id'],
                'model': args.model, 'model_sha256': model.sha256,
                'one_cpu': args.one_cpu, 'model_load_seconds': load_seconds,
                'contour_seconds': time.monotonic()-started, 'diagnostic': diagnostic,
                'live_verified': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({**metadata, 'segments': segments}))
    profile.dump_stats(str(args.output)+'.prof')
    print(json.dumps(metadata, indent=2))
    pstats.Stats(profile).sort_stats('cumtime').print_stats(20)


if __name__ == '__main__':
    main()
