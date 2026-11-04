"""A localization response cannot silently fill missing identity evidence."""
import json
import pytest
from scripts.probe_report_positions import validate


def row():
    return dict(frame='s1', target_status='UNCERTAIN', identity_evidence='Two competing players',
                feet_visible=False, ground=None, box=None, active_ball_status='UNCERTAIN', ball=None)


def test_uncertainty_survives_without_coordinates():
    result = validate(json.dumps({'frames': [row()]}), [{'frame_id': 's1', 'media_ms': 100}])
    assert result == [{**row(), 'media_ms': 100}]


@pytest.mark.parametrize('changes,error', [
    ({'ground': [.2, .3]}, 'UNCONFIRMED_PLAYER_COORDINATES'),
    ({'box': [.1, .2, .1, .2]}, 'UNCONFIRMED_PLAYER_COORDINATES'),
    ({'target_status': 'CONFIRMED', 'ground': [.2, .3]}, 'UNOBSERVED_GROUND'),
    ({'ball': [.2, .3]}, 'UNOBSERVED_BALL'),
    ({'identity_evidence': ''}, 'IDENTITY_EVIDENCE_REQUIRED'),
])
def test_unsupported_measurements_are_rejected(changes, error):
    with pytest.raises(ValueError, match=error):
        validate(json.dumps({'frames': [{**row(), **changes}]}), [{'frame_id': 's1', 'media_ms': 100}])


def test_missing_source_frame_is_rejected():
    with pytest.raises(ValueError, match='COMPLETE_ORDERED_FRAME_COVERAGE_REQUIRED'):
        validate(json.dumps({'frames': [row()]}), [{'frame_id': 's1'}, {'frame_id': 's2'}])
