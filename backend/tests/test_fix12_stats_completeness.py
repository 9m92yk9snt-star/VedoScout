"""Unknown totals stay unknown; accepted events and legacy contracts survive."""
from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verified_stats as stats  # noqa: E402


def goal():
    return {"event_id": "g", "timestamp": "00:30", "cross_verified": True,
            "canonical_event_type": "GOAL", "canonical_action_type": "SHOT",
            "canonical_result": "SCORED", "outcome_visible": True}


def test_partial_scan_preserves_observed_goal_without_publishing_total():
    full = {"action_timeline": [goal()]}
    before = deepcopy(full["action_timeline"])
    result = stats.build_verified_stats(full, {"performed": True, "physical_recall_verification_complete": False})
    stats.rebuild_match_stats(full)
    assert result["goals"] is None and result["assists"] is None
    assert result["observed_counts"]["goals"] == 1
    assert result["coverage_status"] == "PARTIAL"
    assert full["match_stats"]["observed_goals"] == 1 and "goals" not in full["match_stats"]
    assert "verified_stat_line" not in full and full["action_timeline"] == before


def test_partial_empty_scan_never_proves_zero():
    full = {"action_timeline": [], "verified_stat_line": "old zero line"}
    result = stats.build_verified_stats(full, {"performed": True, "coverage_status": "PARTIAL"})
    assert not result["goals_assists_available"] and result["goals"] is None
    assert result["observed_counts"]["goals"] == 0
    assert "verified_stat_line" not in full


def test_complete_empty_legacy_scan_can_still_publish_zero():
    full = {"action_timeline": []}
    result = stats.build_verified_stats(full, {"performed": True})
    assert result["goals_assists_available"] and result["goals"] == 0
    assert full["verified_stat_line"] == "0 goals · 0 assists · 0 shots"


def test_explicit_partial_contract_overrides_performed_and_summary_status():
    assert not stats.scoring_totals_available({"performed": True, "physical_recall_verification_complete": False,
                                              "coverage_status": "SEMANTIC_AND_PHYSICAL_COMPLETE"})
    assert not stats.scoring_totals_available({"performed": True, "incomplete_scoring_coverage": True})
    assert stats.scoring_totals_available({"performed": True, "physical_recall_verification_complete": True})
