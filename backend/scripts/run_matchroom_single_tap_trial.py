"""Fresh independent-source diagnostic using one original tap and server report flow.

The current upload UI requires three taps. This exercises the real report backend,
not a claimed browser end-to-end pass. No historical model receipts are supplied.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_sequence_report_trial import trial
from sequence_pilot import original_taps


def prepare(source, work):
    work.mkdir(parents=True, exist_ok=False)
    (work / 'video').mkdir()
    parts = sorted((source / 'video-parts').glob('*.bin'))
    if [p.name for p in parts] != [f'{i:03}.bin' for i in range(43)]:
        raise ValueError('SOURCE_PARTS_INCOMPLETE')
    video = work / 'video/source.mp4'
    with video.open('wb') as output:
        for part in parts:
            with part.open('rb') as stream:
                shutil.copyfileobj(stream, output)
    shutil.copyfile(source / 'anchors.json', work / 'anchors.json')
    for line in (source / 'SHA256SUMS').read_text().splitlines():
        expected, name = line.split(None, 1)
        with (work / name).open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise ValueError('SOURCE_CHECKSUM_MISMATCH')
    raw = json.loads((work / 'anchors.json').read_text())['raw_marker_anchors']
    while isinstance(raw, str):
        raw = json.loads(raw)
    # First original selection only, without using action times or expected answers.
    selection = {'raw_marker_anchors': [raw[0]]}
    if len(original_taps(selection)) != 1:
        raise ValueError('EXACTLY_ONE_ORIGINAL_TAP_REQUIRED')
    (work / 'single-tap.json').write_text(json.dumps(selection, indent=2))
    return video, selection


def inspect_report(output, selection):
    path = output / 'report-document.json'
    doc = json.loads(path.read_text()) if path.exists() else {}
    audit = doc.get('sequence_audit') or {}
    retry = doc.get('sequence_retry') or {}
    receipts = audit.get('receipts') or retry.get('receipts') or []
    full = doc.get('full_report') or {}
    rows = []
    for row in full.get('video_comments') or []:
        room = row.get('match_room') or {}
        tracking = room.get('tracking') or {}
        samples = room.get('samples') or []
        rows.append({'event_id': row.get('event_id'), 'evidence_time_ms': row.get('evidence_time_ms'),
            'clip': row.get('tele_clip_url'), 'tracking_status': room.get('tracking_status'),
            'tracking_keys': sorted(tracking), 'observed_samples': len(samples),
            'arrow_endpoints': sum(s.get('ball_motion_method') in {
                'BACKGROUND_AFFINE_BALL_ENDPOINTS', 'BACKGROUND_AFFINE_PASS_ENDPOINTS'} for s in samples)})
    policy = Path(__file__).resolve().parents[2] / 'frontend/src/components/marker-studio/scoutTapPolicy.cjs'
    match = re.search(r'const MIN_TAPS = (\d+)', policy.read_text())
    summary = {'scope': 'Real fresh server report orchestration in isolated storage; upload UI not executed',
        'human_tap_count': len(original_taps(selection)), 'tap_time_seconds': selection['raw_marker_anchors'][0]['t'],
        'ui_minimum_taps': int(match.group(1)) if match else None,
        'one_tap_upload_ui_pass': False, 'report_status': doc.get('full_report_status'),
        'report_error': doc.get('full_report_error'),
        'source_video_sha256': audit.get('source_video_sha256') or retry.get('source_video_sha256'),
        'source_checkpoint_reused': audit.get('source_checkpoint_reused'),
        'completed_source_receipts': sum(r.get('origin') == 'LIVE_MODEL_REQUEST' and r.get('status') == 'COMPLETED' for r in receipts),
        'validated_reused_receipts': sum(r.get('retry_payload_verified') is True for r in receipts),
        'source_progress': doc.get('sequence_progress'), 'failures': doc.get('sequence_failures'),
        'source_references': audit.get('references'), 'evidence': rows,
        'visual_correctness_verified': False, 'production_database_used': False,
        'notifications_sent': 0, 'deployment_performed': False}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'single-tap-verification.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--retry-document', type=Path)
    parser.add_argument('--recover-missing', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    video, selection = prepare(root / 'testdata/sequence-pilot-orman400', args.work)
    print(json.dumps({'phase': 'verified_source_ready', 'human_taps': 1,
        'source_bytes': video.stat().st_size, 'historical_results_used': False}), flush=True)
    if not os.environ.get('EMERGENT_LLM_KEY'):
        raise RuntimeError('MODEL_KEY_NOT_CONFIGURED')
    try:
        if args.recover_missing:
            if not args.retry_document:
                raise ValueError('RETRY_DOCUMENT_REQUIRED')
            from scripts.recover_matchroom_request import recover
            args.retry_document = recover(video, selection, args.retry_document, args.work)
        asyncio.run(trial(video, selection, args.output, retry_document=args.retry_document))
    finally:
        inspect_report(args.output, selection)


if __name__ == '__main__':
    main()
