"""Compare exact native reader outputs on a bounded original-video window.

Runs identity person detection, scene person/ball detection, dense detection
and a sparse native revisit. This is a measured reader pattern, not a replay
of historical LLM choices, full tracking/reconstruction or full-report latency.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(root, name):
    spec = importlib.util.spec_from_file_location('before_' + name, root / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', required=True, type=Path)
    parser.add_argument('--start-ms', required=True, type=int)
    parser.add_argument('--end-ms', required=True, type=int)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--baseline-backend', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new output directory')
    backend = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend))
    network = []
    def offline(event, _args):
        if event == 'socket.connect':
            network.append(event)
            raise RuntimeError('NATIVE_BENCHMARK_NETWORK_FORBIDDEN')
    sys.addaudithook(offline)
    import cv2
    import cv_detect as cv
    import dense_replay
    import dense_track_refinement as dense
    import football_scene_graph as graph
    import player_identity_timeline as identity

    sources = {name: sha(backend / (name+'.py')) for name in
               ('cv_detect', 'dense_track_refinement', 'football_scene_graph')}
    frames = list(dense_replay.iter_dense_frames(str(args.video), args.start_ms, args.end_ms))
    if not frames or len(frames) > 480 or any(f['used_fallback'] or f['time_authority'] != 'ACTUAL_MEDIA_PTS' for f in frames):
        raise RuntimeError('Require 1–480 actual-PTS frames; shorten the diagnostic window if necessary')
    def sample(hz):
        rows, previous = [], None
        for row in frames:
            seconds = row['media_ms'] / 1000
            if previous is None or seconds - previous >= 1 / hz - .0005:
                rows.append(row)
                previous = seconds
        return rows
    selections = [sample(identity.HZ), sample(graph.HZ), frames, frames[::30]]
    before = None
    if args.baseline_backend:
        before = {name: load(args.baseline_backend, name) for name in sources}
    results, receipts = [], []
    args.output.mkdir(parents=True)
    for enabled in (False, True):
        modules = before if before and not enabled else {'cv_detect': cv, 'football_scene_graph': graph,
                                                        'dense_track_refinement': dense}
        functions = [modules['cv_detect'].PersonDetector.detect,
                     modules['football_scene_graph']._detect_people_and_ball,
                     lambda d, image: modules['dense_track_refinement']._detect_dense_people_and_ball(d, image, include_a7_support=True)]
        functions.append(functions[-1])
        forwards = [0]
        class Counted:
            def __init__(self, net): self.net = net
            def setInput(self, value): self.net.setInput(value)
            def forward(self):
                forwards[0] += 1
                return self.net.forward()
        detectors = [cv.PersonDetector(enabled=True) for _ in functions]
        if any(not d.ok for d in detectors): raise RuntimeError('Original detector unavailable')
        for d, function in zip(detectors, functions):
            d.net = Counted(d.net)
            function(d, frames[0]['frame_bgr'])
        forwards[0] = 0
        cache = cv.PredictionCache() if enabled else None
        token = cv.CURRENT_PREDICTIONS.set(cache)
        started = time.monotonic()
        outputs, stages = [], []
        try:
            for name, d, function, selected in zip(('identity_reader', 'scene_reader', 'dense_reader', 'native_revisit'),
                                                   detectors, functions, selections):
                first, stage_started = forwards[0], time.monotonic()
                outputs.append([{'media_ms': f['media_ms'], 'proposals': function(d, f['frame_bgr'])} for f in selected])
                stages.append({'stage': name, 'input_frames': len(selected), 'forwards': forwards[0]-first,
                               'seconds': round(time.monotonic()-stage_started, 6)})
                print(json.dumps({'cache': enabled, **stages[-1]}), flush=True)
        finally:
            cv.CURRENT_PREDICTIONS.reset(token)
        seconds = time.monotonic() - started
        payload = json.dumps(outputs, sort_keys=True, separators=(',', ':'), allow_nan=False)
        results.append(payload)
        (args.output / ('candidate-evidence.json' if enabled else 'baseline-evidence.json')).write_text(payload+'\n')
        receipts.append({'cache_enabled': enabled, 'seconds': round(seconds, 6), 'forwards': forwards[0],
                         'stages': stages, 'evidence_sha256': hashlib.sha256(payload.encode()).hexdigest(),
                         'cache': cache.metrics() if cache else None})
    receipt = {'scope': 'BOUNDED_NATIVE_READER_PATTERN_NOT_FULL_ANALYSIS_OR_LLM_RECOGNITION',
               'source_video_sha256': sha(args.video), 'model_sha256': detectors[0].model_sha256,
               'source_span_ms': [frames[0]['media_ms'], frames[-1]['media_ms']],
               'source_frames': len(frames), 'reader_input_frames': sum(map(len, selections)),
               'opencv_threads': cv2.getNumThreads(), 'backend_source_sha256': sources,
               'baseline_source_sha256': {name: sha(args.baseline_backend/(name+'.py')) for name in sources} if before else sources,
               'script_sha256': sha(__file__), 'runs': receipts, 'evidence_identical': results[0] == results[1],
               'new_llm_calls': 0, 'network_attempts': len(network), 'expected_event_labels_used': False}
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({k: receipt[k] for k in ('source_frames', 'evidence_identical', 'new_llm_calls', 'network_attempts')}))
    if not receipt['evidence_identical'] or network:
        raise RuntimeError('Reader outputs changed or isolation failed')


if __name__ == '__main__':
    main()
