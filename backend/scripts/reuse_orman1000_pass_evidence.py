"""Build an offline graphics handoff from accepted action evidence and new positions.

No inference, production writes, cross-run player-ID transfer or playback approval.
The newer localization's unknown contacts do not erase an accepted prior action.
"""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def combine(acceptance, prior, positions, manifest):
    decision = acceptance['decision']
    binding = decision['prior_model_receipt']
    if (decision['status'] != 'ACCEPTED_ASSIST_FROM_PRIOR_MODEL_WITH_EXPLICIT_OWNER_ADJUDICATION'
            or decision['authority'] != 'OWNER_ACCEPTED_PRIOR_MODEL_EVIDENCE'
            or prior['source_video_sha256'] != binding['source_video_sha256']
            or prior['response_sha256'] != binding['response_sha256']
            or hashlib.sha256(prior['raw_response'].encode()).hexdigest() != binding['response_sha256']):
        raise ValueError('ACCEPTED_PRIOR_EVIDENCE_REQUIRED')
    events = prior['result']['target_events']
    if len(events) != 1:
        raise ValueError('UNIQUE_PRIOR_ASSIST_REQUIRED')
    event = events[0]
    accepted = decision['accepted_assertion']
    if (event['approval_status'] != 'APPROVED' or event['event_type'] != 'ASSIST'
            or event['selected_player'] is not True or event['actor'] == event['receiver']
            or event['receiver'] != event['finisher'] or event['one_touch_finish'] is not True
            or event['contact_interval_ms'] != accepted['selected_player_release_interval_ms']
            or event['finishing_contact_interval_ms'] != accepted['distinct_white_teammate_finish_interval_ms']
            or event['receiver_interval_ms'] != event['finishing_contact_interval_ms']
            or event['outcome_ms'] != accepted['goal_outcome_ms']):
        raise ValueError('ACCEPTED_CAUSAL_CHAIN_CHANGED')
    if (positions['source_video_sha256'] != decision['source_video_sha256']
            or manifest['source_video_sha256'] != decision['source_video_sha256']
            or positions['packet_sha256'] != manifest['packet_sha256']
            or len(positions['receipts']) != 1):
        raise ValueError('POSITION_SOURCE_BINDING_CHANGED')
    receipt = positions['receipts'][0]
    if (receipt['status'] != 'COMPLETED'
            or hashlib.sha256(receipt['raw_response'].encode()).hexdigest() != receipt['response_sha256']
            or any(receipt.get(k) != v for k, v in manifest['request'].items())):
        raise ValueError('POSITION_RECEIPT_CHANGED')
    observations = json.loads(receipt['raw_response'])
    if ([r['frame_id'] for r in observations['observations']]
            != [r['frame_id'] for r in manifest['frames'] if 'frame_id' in r]):
        raise ValueError('POSITION_FRAME_ORDER_CHANGED')
    return {
        'event_id': decision['event_id'],
        'source_video_sha256': decision['source_video_sha256'],
        'action_status': 'ACCEPTED_ASSIST',
        'authority': decision['authority'],
        'accepted_sequence': {
            'selected_player_pass_interval_ms': event['contact_interval_ms'],
            'teammate_first_time_receive_and_finish_interval_ms': event['receiver_interval_ms'],
            'goal_outcome_ms': event['outcome_ms'],
            'exact_contact_ms': None,
            'foot_side': accepted['foot_side'],
            'prior_receipt_source_video_sha256': binding['source_video_sha256'],
            'prior_receipt_response_sha256': binding['response_sha256'],
        },
        'position_candidates': {
            'status': 'REQUIRES_SOURCE_PIXEL_REVIEW',
            'source_video_sha256': positions['source_video_sha256'],
            'response_sha256': receipt['response_sha256'],
            'observations': copy.deepcopy(observations['observations']),
            'receiver_role_mapping': None,
        },
        'localization_unknowns_do_not_revoke_accepted_action': True,
        'prior_player_ids_transferred': False,
        'measured_ball_trajectory_approved': False,
        'playback_status': 'PENDING',
        'production_integration': False,
        'new_model_calls': 0,
    }


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    def read(path):
        return json.loads((ROOT / path).read_text())
    result = combine(
        read('testdata/matchroom-completion/orman1000-third-assist-owner-accepted-2026-11-07.json'),
        read('docs/examples/native-third-assist-approval-receipt.json'),
        read('testdata/matchroom-position-llm/result.json'),
        read('testdata/matchroom-position-llm/manifest.json'))
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print('Accepted prior pass/first-time finish reused; geometry remains candidate; zero model calls.')
