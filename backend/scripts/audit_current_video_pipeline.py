"""Fresh native diagnostic using the production spine and original tap pixels.

This is not a new multimodal/full-report run: all remote readers are disabled.
It measures tracking, scene/identity preparation and physical reconstruction
from the complete original video. Expected action labels never enter a stage.
No database, payment, notification, deployment or report mutation is possible.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import zipfile


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--threads', type=int, default=4, choices=range(1, 5))
    parser.add_argument('--declared-number', type=int, required=True)
    parser.add_argument('--physical', action='store_true')
    args = parser.parse_args()
    backend = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend))
    if (backend / '.env').exists():
        parser.error('Run from an isolated checkout without backend/.env')
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('Use a new empty output directory')
    for key in list(os.environ):
        if any(word in key.upper() for word in ('API_KEY', 'EMERGENT_LLM_KEY', 'OPENAI_KEY')):
            os.environ.pop(key, None)
    args.output.mkdir(parents=True, exist_ok=True)
    source_hashes = {p.name: digest(p) for p in backend.glob('*.py')}
    counters = {'network': 0, 'remote_sdk': 0, 'video_open': 0, 'detector_forward': 0}
    phase = {'name': 'input', 'started': time.monotonic()}
    stages = []
    finished = threading.Event()

    def forbidden(kind):
        def blocked(*_a, **_k):
            counters[kind] += 1
            raise RuntimeError('NATIVE_AUDIT_FORBIDDEN_' + kind.upper())
        return blocked

    socket.socket.connect = socket.socket.connect_ex = socket.create_connection = forbidden('network')
    import cv2
    import cv_detect
    import fix10a_vision_providers as vision
    import fix10b_runtime
    import identity_verify
    import physical_match_reconstruction as physical
    import player_identity_timeline
    import player_tracking
    import unified_analysis_engine as unified

    vision.LlmChat = identity_verify.LlmChat = forbidden('remote_sdk')
    cv2.setNumThreads(args.threads)
    cv2.setRNGSeed(0)
    original_capture = cv2.VideoCapture

    def capture(*a, **k):
        counters['video_open'] += 1
        return original_capture(*a, **k)

    cv2.VideoCapture = capture
    original_detector_init = cv_detect.PersonDetector.__init__

    class CountedNet:
        def __init__(self, net):
            self.net = net
        def __getattr__(self, name):
            return getattr(self.net, name)
        def forward(self, *a, **k):
            counters['detector_forward'] += 1
            return self.net.forward(*a, **k)

    def detector_init(instance, *a, **k):
        original_detector_init(instance, *a, **k)
        if instance.net is not None:
            instance.net = CountedNet(instance.net)

    cv_detect.PersonDetector.__init__ = detector_init
    with zipfile.ZipFile(args.evidence) as archive:
        if 'SHA256SUMS' not in archive.namelist():
            raise ValueError('Checksummed evidence required')
        for row in archive.read('SHA256SUMS').decode().splitlines():
            expected, name = row.split(None, 1)
            if hashlib.sha256(archive.read(name.strip().lstrip('*'))).hexdigest() != expected:
                raise ValueError('Evidence checksum mismatch')
        report = json.loads(archive.read('report.json'))
        anchor_doc = json.loads(archive.read('anchors.json'))
        video_names = [name for name in archive.namelist() if name.startswith('video/') and name.endswith('.mp4')]
        if len(video_names) != 1:
            raise ValueError('Exactly one original canonical video required')
        video = args.output / 'source.mp4'
        video.write_bytes(archive.read(video_names[0]))
    video_sha = digest(video)
    if video_sha != report.get('analysis_run_manifest', {}).get('source_video_sha256'):
        raise ValueError('Canonical source video mismatch')
    anchors = deepcopy(anchor_doc.get('anchors') or [])
    t_off = float(anchor_doc.get('anchor_time_offset') or report.get('anchor_time_offset') or 0)
    if not anchors:
        raise ValueError('Original anchors required')
    context = {'scope': 'FRESH_NATIVE_DIAGNOSTIC_REMOTE_READERS_DISABLED',
               'source_video_sha256': video_sha, 'original_anchors_sha256': hashlib.sha256(json.dumps(anchor_doc, sort_keys=True).encode()).hexdigest(),
               'anchor_count': len(anchors), 'declared_number': args.declared_number,
               'original_declared_number': (report.get('player_details') or {}).get('jersey_number'),
               'declaration_override_source': 'USER_DECLARED_NUMBER_NOT_OCR',
               'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=backend, text=True).strip(),
               'source_sha256': source_hashes, 'script_sha256': digest(__file__),
               'model_sha256': digest(backend / 'models/yolov8n.onnx'),
               'semantic_model_calls': 0, 'supporting_model_calls': 0, 'database_writes': 0,
               'expected_reference_labels_used_as_input': False, 'stages': stages, 'counters': counters}
    save(args.output / 'receipt.json', context)

    def heartbeat():
        while not finished.wait(10):
            print(json.dumps({'heartbeat': phase['name'], 'elapsed_s': round(time.monotonic() - phase['started'], 1), **counters}), flush=True)

    threading.Thread(target=heartbeat, daemon=True).start()

    def run_stage(name, function):
        phase.update(name=name, started=time.monotonic())
        before = dict(counters)
        print(json.dumps({'stage': name, 'status': 'START'}), flush=True)
        result = function()
        row = {'name': name, 'elapsed_s': round(time.monotonic() - phase['started'], 3),
               'counters': {k: counters[k] - before[k] for k in counters}}
        stages.append(row)
        save(args.output / (name + '.json'), result)
        save(args.output / 'receipt.json', context)
        print(json.dumps({'stage': name, 'status': 'COMPLETE', **row}), flush=True)
        return result

    try:
        track = run_stage('tracking', lambda: player_tracking.track_player(str(video), anchors, t_off=t_off))
        timeline = run_stage('identity', lambda: player_identity_timeline.build_identity_timeline(str(video), {'anchors': anchors, 'anchor_time_offset': t_off}))
        prepared = run_stage('preparation', lambda: unified.prepare_analysis(
            video_path=str(video), fix04_track=track, identity_timeline=timeline, anchors=anchors,
            anchor_time_offset=t_off, player_details={'jersey_number': args.declared_number}))
        result = unified.finalise_analysis({}, prepared)
        save(args.output / 'unified_without_semantic_reader.json', result)
        context['preparation_metrics'] = prepared.get('metrics')
        context['physical_admitted'] = unified.can_run_physical(result)
        context['identity_statuses'] = dict(Counter(p.get('status') for p in prepared.get('authority', {}).get('target_points') or []))
        if args.physical and context['physical_admitted']:
            def trace_callback(trace):
                key = hashlib.sha256(str(trace.get('trace_id')).encode()).hexdigest()[:20]
                path = args.output / 'traces' / (key + '.json.gz')
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(gzip.compress(json.dumps(trace).encode()))
                print(json.dumps({'trace': trace.get('trace_id'), 'frames': len(trace.get('decoded_frames') or []),
                                  'contacts': len((trace.get('contacts') or {}).get('accepted') or []),
                                  'strikes': len(trace.get('strike_evidence') or [])}), flush=True)
            physical_result = run_stage('physical', lambda: physical.reconstruct_physical_match(
                str(video), unified.physical_sequence_plan(result), result['sequence_analysis'],
                result['scene_graph'], result['identity_authority'],
                source_video={'sha256': video_sha}, trace_callback=trace_callback))
            reconciled = run_stage('reconciliation', lambda: fix10b_runtime.reconcile_unified_result(result, physical_result))
            context['physical_metrics'] = physical_result.get('metrics')
            context['physical_coverage'] = physical_result.get('recall_coverage')
            context['canonical_counts'] = (reconciled.get('canonical_events') or {}).get('counts')
        context['status'] = 'NATIVE_DIAGNOSTIC_COMPLETE_NOT_FULL_ANALYSIS'
    except BaseException as exc:
        context.update(status='NATIVE_DIAGNOSTIC_FAILED', error_type=type(exc).__name__)
        raise
    finally:
        finished.set()
        context['source_unchanged'] = source_hashes == {p.name: digest(p) for p in backend.glob('*.py')}
        save(args.output / 'receipt.json', context)
    if counters['network'] or counters['remote_sdk'] or not context['source_unchanged']:
        context['status'] = 'NATIVE_DIAGNOSTIC_ISOLATION_FAILED'
        save(args.output / 'receipt.json', context)
        raise RuntimeError('Native audit isolation failed')
    print(json.dumps({'status': context['status'], 'output': str(args.output), 'canonical_counts': context.get('canonical_counts')}), flush=True)


if __name__ == '__main__':
    main()
