"""FIX09C statistical-precision regressions for rich football micro-actions."""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import canonical_output_authority as coa  # noqa: E402


def _event(action):
    return {
        "event_id": f"evt_{action.lower()}",
        "canonical_ms": 1000,
        "end_ms": 1100,
        "canonical_event_type": action,
        "canonical_action_type": action,
        "canonical_outcome": "UNKNOWN",
        "causal_verified": False,
        "identity_resolution": "VISIBLE_TARGET_MATCH",
        "details": [f"observed {action.lower()}"],
        "proof": {},
    }


def test_c15_carry_stays_rich_but_is_not_counted_as_a_dribble():
    row = coa.project_event(_event("CARRY"))
    assert row["football_action_type"] == "CARRY"
    assert row["canonical_action_type"] == "OTHER"
    assert row["canonical_event_type"] == "OTHER"


def test_c16_take_on_is_countable_as_dribble_without_losing_rich_type():
    row = coa.project_event(_event("TAKE_ON"))
    assert row["football_action_type"] == "TAKE_ON"
    assert row["canonical_action_type"] == "DRIBBLE"
    assert row["canonical_event_type"] == "DRIBBLE"


def test_c17_receive_does_not_double_count_first_touch():
    row = coa.project_event(_event("RECEIVE"))
    assert row["football_action_type"] == "RECEIVE"
    assert row["canonical_action_type"] == "OTHER"


def test_c18_control_does_not_double_count_first_touch():
    row = coa.project_event(_event("CONTROL"))
    assert row["football_action_type"] == "CONTROL"
    assert row["canonical_action_type"] == "OTHER"
