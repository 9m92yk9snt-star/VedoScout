import copy
import json
from pathlib import Path

import pytest
from scripts.reuse_orman1000_pass_evidence import combine

ROOT = Path(__file__).resolve().parents[2]


def inputs():
    return [json.loads((ROOT / p).read_text()) for p in (
        'testdata/matchroom-completion/orman1000-third-assist-owner-accepted-2026-11-07.json',
        'docs/examples/native-third-assist-approval-receipt.json',
        'testdata/matchroom-position-llm/result.json',
        'testdata/matchroom-position-llm/manifest.json')]


def test_real_prior_first_time_reception_survives_new_localization_unknowns():
    values = inputs()
    before = copy.deepcopy(values)
    result = combine(*values)
    assert values == before
    assert result['action_status'] == 'ACCEPTED_ASSIST'
    assert result['accepted_sequence']['selected_player_pass_interval_ms'] == [49715, 50081]
    assert result['accepted_sequence']['teammate_first_time_receive_and_finish_interval_ms'] == [50331, 50648]
    assert result['position_candidates']['receiver_role_mapping'] is None
    assert result['playback_status'] == 'PENDING'
    assert result['measured_ball_trajectory_approved'] is False


@pytest.mark.parametrize('kind', ['foreign_source', 'rewritten_prior', 'rewritten_position', 'changed_interval', 'changed_request'])
def test_incompatible_evidence_is_not_reused(kind):
    values = inputs()
    if kind == 'foreign_source':
        values[2]['source_video_sha256'] = 'other'
    elif kind == 'rewritten_prior':
        values[1]['raw_response'] += ' '
    elif kind == 'rewritten_position':
        values[2]['receipts'][0]['raw_response'] += ' '
    elif kind == 'changed_interval':
        values[1]['result']['target_events'][0]['receiver_interval_ms'] = [50615, 50665]
    else:
        values[2]['receipts'][0]['payload_sha256'] = 'other'
    with pytest.raises(ValueError):
        combine(*values)
