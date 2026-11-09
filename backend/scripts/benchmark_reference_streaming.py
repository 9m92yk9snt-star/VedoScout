"""Paired offline reference-streaming preparation benchmark against a supplied baseline module."""
import argparse
import hashlib
import importlib.util
import json
import statistics
import tempfile
import time
import zipfile
from pathlib import Path
import cv2
import match_room_localization as current
import sequence_pilot_transport as transport


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('video', type=Path)
    p.add_argument('export_zip', type=Path)
    p.add_argument('baseline_module', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    spec = importlib.util.spec_from_file_location('reference_before', args.baseline_module)
    before = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(before)
    with zipfile.ZipFile(args.export_zip) as archive:
        report = json.loads(archive.read('report.json'))
        audit = json.loads(archive.read('sequence/match-room-localization.json'))
    with args.video.open('rb') as source:
        sha = hashlib.file_digest(source, 'sha256').hexdigest()
    assert sha == report['canonical_events']['source_video_sha256']
    event = next(e for e in report['canonical_events']['events'] if e['event_id'] in audit['events'])
    selection = {'raw_marker_anchors': report['raw_marker_anchors']}
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for round_index in range(6):
            elapsed, outputs = {}, {}
            order = ('before', 'after') if round_index % 2 == 0 else ('after', 'before')
            for name in order:
                module = before if name == 'before' else current
                started = time.perf_counter()
                record, job = module.prepare(args.video, selection, event, Path(tmp)/str(round_index)/name)
                elapsed[name] = time.perf_counter()-started
                wire = transport.build_request('emergent', 'gpt-6-astra', job['items'], reasoning_effort=job['reasoning_effort'], image_detail=job['image_detail'], max_output_tokens=job['max_output_tokens'])
                outputs[name] = (wire, {key: [{k:v for k,v in f.items() if k != 'path'} for f in record[key]] for key in ('references', 'frames')})
            assert outputs['before'] == outputs['after'], 'Request bytes or source metadata changed'
            rows.append({'round': round_index, 'order': order, 'seconds': elapsed, 'equal': True})
    measured = rows[1:]  # Discard one warm-up pair.
    medians = {name: statistics.median(r['seconds'][name] for r in measured) for name in ('before', 'after')}
    result = {'baseline_commit': 'ecbb8fbd8dcf51e1899eecb9306ef625d8e34654', 'baseline_module_sha256': hashlib.sha256(args.baseline_module.read_bytes()).hexdigest(), 'source_sha256': sha, 'opencv': cv2.__version__, 'event_id': event['event_id'], 'reference_times_ms': [t['requested_ms'] for t in current.pilot.original_taps(selection)], 'rounds': rows, 'median_seconds': medians, 'relative_change_percent': 100*(medians['after']/medians['before']-1), 'scope': 'First request preparation with uncached references; timeline streaming enabled in both versions. Alternating order, one warm-up pair excluded, five measured pairs. No provider calls or total-analysis timing.'}
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
