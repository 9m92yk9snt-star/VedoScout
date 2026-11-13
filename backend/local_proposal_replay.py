"""Replay immutable historical proposals, never assert current-model parity."""
import hashlib
import json
from pathlib import Path
from local_track_selection import bind_taps, seed_component, overlap_review_frames, review_windows


def replay(receipt_path, expected_receipt_sha, video_path, selection):
    raw = Path(receipt_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_receipt_sha:
        raise ValueError('PROPOSAL_RECEIPT_CHANGED')
    receipt = json.loads(raw)
    with Path(video_path).open('rb') as stream:
        source = hashlib.file_digest(stream,'sha256').hexdigest()
    if receipt.get('source_video_sha256') != source or selection.get('source_video_sha256') != source:
        raise ValueError('PROPOSAL_SOURCE_MISMATCH')
    if receipt.get('scope') != 'LOCAL_PROPOSALS_ONLY_NOT_PLAYER_IDENTITY_OR_REPORT_PARITY':
        raise ValueError('UNSUPPORTED_PROPOSAL_SCOPE')
    rows=receipt['rows'];lo,hi=receipt['window_ms']
    if not rows or len(rows)!=receipt['frames']:
        raise ValueError('INCOMPLETE_PROPOSAL_RECEIPT')
    stamps=[r['media_ms'] for r in rows]
    if any(type(t) is not int or not lo<=t<=hi for t in stamps) or any(a>=b for a,b in zip(stamps,stamps[1:])):
        raise ValueError('INVALID_PROPOSAL_TIMESTAMPS')
    seeds=bind_taps(rows,selection['taps'],source_sha=source,expected_source_sha=source)
    components=[seed_component(rows,s) for s in seeds]
    flags=[overlap_review_frames(rows,c) for c in components]
    return {'scope':'HISTORICAL_PROPOSAL_REPLAY_ONLY','source_video_sha256':source,
            'receipt_sha256':expected_receipt_sha,'original_model_sha256':receipt.get('model_sha256'),
            'original_versions':receipt.get('versions'),'window_ms':[lo,hi],
            'new_detector_calls':0,'new_llm_calls':0,'proof_eligible':False,
            'tap_candidates':seeds,'seed_components':components,
            'review_windows':[review_windows(f,start_ms=lo,end_ms=hi) for f in flags]}
