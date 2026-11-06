"""Offline full scheduler comparison on retained SAME-SOURCE Match Room evidence.

Requires a prior retained report with source- and selection-bound paid receipts.
All source/model/identity settings stay unchanged. No provider calls are allowed.
Runs both scheduler paths, including initial, small and medium child work.
A mismatch FAILS the experiment and leaves cache disabled in production.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

import sequence_pilot as pilot
from match_room_localization import packet_id, validate
from match_room_position_evidence import bound_samples, selection_digest
from match_room_tracking import bounded_tracks
from scripts.run_matchroom_single_tap_trial import prepare

TARGET_EVENT_IDS = ('a512ae64e102f24b3383', 'ec74209ace700fa49d2e')
PINNED_SOURCE = 'b9e2ba4975ed9dc2497f860a80644711bfd12a2125d9fba6390600b0409ab999'


def observations_from_retained(event, selection, record):
    if record.get('event_id') != event['event_id'] or record.get('status') != 'OBSERVATIONS_RETURNED':
        raise ValueError('RETAINED_EVENT_NOT_SOURCE_BOUND')
    if record.get('source_video_sha256') != PINNED_SOURCE:
        raise ValueError('FOREIGN_LOCALIZATION_SOURCE')
    rows = bound_samples(event, selection, record, validate, packet=packet_id(event))
    by_time = {r['media_ms']: r for r in rows}
    for pid, extra in (record.get('completion') or {}).items():
        if extra.get('status') != 'OBSERVATIONS_RETURNED':
            continue
        if pid != extra.get('packet_id'):
            raise ValueError('SUPPLEMENT_PACKET_CHANGED')
        supplemental = bound_samples(event, selection, extra, validate, packet=pid)
        for row in supplemental:
            previous = by_time.get(row['media_ms'])
            if previous is not None and previous != row:
                raise ValueError('CONFLICTING_SOURCE_OBSERVATIONS')
            by_time[row['media_ms']] = row
    result = sorted(by_time.values(), key=lambda r: r['media_ms'])
    if len(result) < 3 or sum(r.get('identity_status') == 'CONFIRMED' and r.get('ground') is not None
                              for r in result) < 2:
        raise ValueError('INSUFFICIENT_VERIFIED_SOURCE_POSITIONS')
    return result


def tracked_fields(snapshot, eid):
    row = snapshot.get(eid) or {}
    if row.get('event_id') != eid or row.get('source_video_sha256') != PINNED_SOURCE:
        raise ValueError('TRACK_OUTPUT_SOURCE_MISMATCH')
    return {key: row.get(key) for key in ('method', 'segments', 'observed_samples', 'ball_playback')}



def first_differences(a, b, limit=12):
    """Bounded diff paths and numeric discrepancies; never raw masks or receipts."""
    rows = []
    def walk(x, y, path):
        if len(rows) >= limit or x == y:
            return
        if isinstance(x, dict) and isinstance(y, dict):
            for key in sorted(set(x) | set(y), key=str):
                sub = path + '.' + str(key)[:80]
                if key not in x or key not in y:
                    rows.append({'path': sub, 'reason': 'FIELD_MISSING'})
                else:
                    walk(x[key], y[key], sub)
                if len(rows) >= limit:
                    return
        elif isinstance(x, list) and isinstance(y, list):
            if len(x) != len(y):
                rows.append({'path': path, 'reason': 'LENGTH_CHANGED',
                             'before_length': len(x), 'after_length': len(y)})
            for i, (before, after) in enumerate(zip(x, y)):
                walk(before, after, path + '[' + str(i) + ']')
                if len(rows) >= limit:
                    return
        elif type(x) in (int, float) and type(y) in (int, float):
            rows.append({'path': path, 'reason': 'NUMERIC_DIFFERENCE',
                         'before': x, 'after': y,
                         'absolute_difference': abs(float(x)-float(y))})
        else:
            rows.append({'path': path, 'reason': 'VALUE_OR_TYPE_CHANGED'})
    walk(a, b, 'root')
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report', type=Path, required=True)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists() or args.work.exists():
        ap.error('fresh work and output paths required')
    doc = json.loads(args.report.read_text())
    bundle = doc['canonical_events']
    if bundle['source_video_sha256'] != PINNED_SOURCE:
        raise ValueError('RETAINED_REPORT_SOURCE_MISMATCH')
    raw = doc['raw_marker_anchors']
    while isinstance(raw, str):
        raw = json.loads(raw)
    selection = {'raw_marker_anchors': raw}
    taps = pilot.original_taps(selection)
    fixture = json.loads((ROOT / 'testdata/sequence-pilot-orman400/anchors.json').read_text())
    original = fixture['raw_marker_anchors']
    while isinstance(original, str):
        original = json.loads(original)
    if raw != original or len(taps) != 10:
        raise ValueError('ORIGINAL_HUMAN_TAPS_CHANGED')
    audit = doc.get('match_room_localization') or {}
    if (audit.get('source_video_sha256') != PINNED_SOURCE or
            audit.get('original_selection_values_sha256') != selection_digest(selection)):
        raise ValueError('LOCALIZATION_AUDIT_SOURCE_OR_SELECTION_CHANGED')
    video, _ = prepare(ROOT / 'testdata/sequence-pilot-orman400', args.work)
    with video.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != PINNED_SOURCE:
            raise ValueError('ACTUAL_VIDEO_BYTES_CHANGED')
    events_by_id = {e['event_id']: e for e in bundle['events']}
    report_ids = {row['event_id'] for row in doc['full_report']['video_comments']}
    selected = []
    for eid in TARGET_EVENT_IDS:
        if eid not in report_ids or eid not in events_by_id:
            raise ValueError('TARGET_EVENT_NOT_IN_RETAINED_REPORT')
        event = deepcopy(events_by_id[eid])
        record = (audit.get('events') or {}).get(eid)
        if not isinstance(record, dict):
            raise ValueError('VERIFIED_LOCALIZATION_RECEIPT_MISSING')
        event['visual_samples'] = observations_from_retained(event, selection, record)
        event['localization_method'] = 'EXPLICIT_SOURCE_POSITIONS'
        if record.get('context_after_ms') == 750:
            event['graphics_context_ms'] = 750
        selected.append(event)
    anchors = [{'t': t['requested_ms'] / 1000, 'box': t['box'],
                'target_point': t['target_point'], **t['selection_hints']}
               for t in taps]

    start = time.monotonic()
    baseline, base_status = bounded_tracks(video, anchors, selected, reuse_predictions=False)
    base_seconds = time.monotonic() - start
    start = time.monotonic()
    # Unchanged-code control distinguishes intrinsic ONNX variability
    # from any difference caused by the cache.
    control, control_status = bounded_tracks(video, anchors, selected, reuse_predictions=False)
    control_seconds = time.monotonic() - start
    start = time.monotonic()
    cached, cache_status = bounded_tracks(video, anchors, selected, reuse_predictions=True)
    cache_seconds = time.monotonic() - start
    comparison = []
    for eid in TARGET_EVENT_IDS:
        original_fields = tracked_fields(baseline, eid)
        control_fields = tracked_fields(control, eid)
        cache_fields = tracked_fields(cached, eid)
        equality = {key: original_fields[key] == cache_fields[key]
                    for key in original_fields}
        control_equality = {key: original_fields[key] == control_fields[key]
                            for key in original_fields}
        comparison.append({'event_id': eid, 'parity': equality,
                           'control_parity': control_equality,
                           'cache_differences': first_differences(original_fields, cache_fields),
                           'control_differences': first_differences(original_fields, control_fields),
                           'baseline_segments': len(original_fields['segments'] or []),
                           'control_segments': len(control_fields['segments'] or []),
                           'cached_segments': len(cache_fields['segments'] or []),
                           'source_observations': len(next(e['visual_samples'] for e in selected
                                                           if e['event_id'] == eid))})
    output = {
        'scope': 'TWO_SAME_SOURCE_REAL_REPORT_CLIPS_COMPLETE_ONNX_SCHEDULER',
        'source_video_sha256': PINNED_SOURCE, 'original_human_taps': len(taps),
        'events': comparison, 'engine': 'onnxruntime', 'new_provider_model_requests': 0,
        'baseline_status': base_status, 'control_status': control_status,
        'cached_status': cache_status,
        'baseline_seconds': round(base_seconds, 3),
        'control_seconds': round(control_seconds, 3),
        'cached_seconds': round(cache_seconds, 3),
        'no_cache_control_identical':
            all(all(row['control_parity'].values()) for row in comparison),
        'all_segments_and_ball_evidence_identical':
            all(all(row['parity'].values()) for row in comparison),
        'full_report_verified': False, 'production_cache_enabled': False,
        'live_deployment_verified': False,
    }
    args.output.write_text(json.dumps(output, indent=2))
    print('MATCHROOM_ONNX_SCHEDULER_RESULT=' + json.dumps(output), flush=True)
    if any(v != 'COMPLETED' for v in (base_status, control_status, cache_status)):
        raise RuntimeError('ONNX_SCHEDULER_INCOMPLETE')
    if not output['no_cache_control_identical']:
        raise RuntimeError('ONNX_SCHEDULER_BASELINE_NOT_DETERMINISTIC')
    if not output['all_segments_and_ball_evidence_identical']:
        raise RuntimeError('ONNX_SCHEDULER_PARITY_CHANGED')


if __name__ == '__main__':
    main()
