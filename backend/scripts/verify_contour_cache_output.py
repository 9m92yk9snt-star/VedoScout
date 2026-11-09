"""Offline full-contour parity with cold/warm exact prediction reuse."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import tempfile
import time
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('export_zip', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--engine', choices=('opencv', 'onnxruntime'), default='opencv')
    args = parser.parse_args()
    os.environ['SCOUTMEPLAY_MATCHROOM_ENGINE'] = args.engine
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    import cv2
    from match_room_position_contours import contour_segments, refinement_model
    from match_room_prediction_cache import CachedSegmenter
    cv2.setNumThreads(2)
    with zipfile.ZipFile(args.export_zip) as archive:
        report = json.loads(archive.read('report.json'))
    room, = [r['match_room'] for r in report['full_report']['video_comments'] if r['timestamp'] == '00:08']
    with args.video.open('rb') as source:
        sha = hashlib.file_digest(source, 'sha256').hexdigest()
    assert sha == room['source_video_sha256']
    start, end = 8750, 10000
    assert room['start_ms'] <= start < end <= room['end_ms']
    model = refinement_model()
    calls = [0]
    predict = model.predict
    def counted(image):
        calls[0] += 1
        return predict(image)
    model.predict = counted
    runs = []
    reference = None
    with tempfile.TemporaryDirectory(prefix='contour-parity-') as tmp:
        for name in ('plain', 'cold', 'warm'):
            # New wrapper simulates separate workers, with disk data shared.
            predictor = model if name == 'plain' else CachedSegmenter(model, tmp, sha)
            before = calls[0]
            cv2.setRNGSeed(0)
            diagnostics = {}
            started = time.monotonic()
            segments = contour_segments(args.video, room['samples'], start, end,
                deadline=started+420, diagnostics=diagnostics, segmenter=predictor, audit_pairs=True)
            elapsed = time.monotonic()-started
            detector_seconds = diagnostics.pop('detector_seconds')
            assert diagnostics['status'] == 'SUPPORTED_SOURCE_OBSERVATIONS'
            assert diagnostics['source_pairs_unreached'] == 0
            assert segments, 'Must exercise actual emitted graphics'
            output = {'segments': segments, 'diagnostics': diagnostics}
            if reference is None:
                reference = output
            assert output == reference, 'FINAL_GRAPHICS_OR_DECISIONS_CHANGED'
            runs.append({'mode': name, 'seconds': elapsed, 'detector_seconds': detector_seconds,
                'inference_calls': calls[0]-before, 'cache_hits': getattr(predictor, 'hits', 0),
                'cache_misses': getattr(predictor, 'misses', 0), 'segments': len(segments),
                'output_sha256': hashlib.sha256(json.dumps(output, sort_keys=True).encode()).hexdigest()})
            print(json.dumps(runs[-1]), flush=True)
        assert runs[0]['inference_calls'] == runs[1]['inference_calls'] == diagnostics['detector_frames']
        assert runs[2]['inference_calls'] == 0
        assert runs[2]['cache_hits'] == diagnostics['detector_frames']
        result = {'source_sha256': sha, 'model_sha256': model.sha256, 'engine': args.engine,
            'opencv_version': cv2.__version__,
            'onnxruntime_version': importlib.metadata.version('onnxruntime') if args.engine == 'onnxruntime' else None, 'window_ms': [start, end], 'one_cpu': True,
            'runs': runs, 'exact_complete_output_equal': True, 'output': reference,
            'scope': 'One real medium-model contour window. Warm replay is an upper bound for exact overlap, not measured production cache hit rate. Includes cache read/write cost; excludes model loading. No provider calls, deployment or production cache activation.'}
        args.output.write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
