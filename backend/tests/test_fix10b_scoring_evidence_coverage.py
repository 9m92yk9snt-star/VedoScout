"""Successful jobs cannot turn missing target evidence into complete coverage."""
from copy import deepcopy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fix10b_runtime as runtime  # noqa: E402


def physical(target_proof=True, outcome="GOAL_PLANE_CROSSING", target=True):
    return {
        "status": "ok",
        "recall_coverage": {"scan_complete": True, "verification_complete": True},
        "traces": [{
            "trace_id": "test_window",
            "decoded_frames": [{"media_ms": 1000, "global_target": {
                "status": "VERIFIED" if target_proof else "UNRESOLVED",
                "proof_eligible": target_proof,
            }}],
            "strike_evidence": [{"strike_id": "contact", "global_target_id": "GLOBAL_TARGET" if target else None}],
            "outcome_evidence": [{"strike_id": "contact", "physical_outcome": outcome}],
        }],
    }


def scan(p):
    return runtime._scoring_scan({"metrics": {"goals": 0, "assists": 0}}, {"coverage_complete": True}, p)


def test_executed_job_with_identity_gap_has_incomplete_evidence_without_inventing_events():
    s = scan(physical(target_proof=False))
    assert s["physical_recall_execution_complete"] is True
    assert s["physical_recall_verification_complete"] is False
    assert s["coverage_status"] == "SEMANTIC_COMPLETE_PHYSICAL_EVIDENCE_PARTIAL"
    assert s["physical_evidence_coverage"]["identity_gap_observations"] == 1
    assert s["verified_goals"] == s["verified_assists"] == 0


def test_unresolved_target_outcome_is_reported_even_without_semantic_shot_candidate():
    s = scan(physical(outcome="UNRESOLVED_TERMINAL_VISIBILITY"))
    assert s["unresolved_goal_attempts"] == 0
    assert s["physical_evidence_coverage"]["unresolved_target_outcomes"] == 1
    assert s["physical_recall_verification_complete"] is False


def test_opponent_outcome_does_not_create_a_target_scoring_gap():
    s = scan(physical(outcome="UNRESOLVED", target=False))
    assert s["physical_recall_verification_complete"] is True
    assert s["coverage_status"] == "SEMANTIC_AND_PHYSICAL_COMPLETE"


def test_missing_trace_frames_cannot_be_assessed_from_execution_flags():
    s = scan({"recall_coverage": {"verification_complete": True}, "traces": []})
    assert s["physical_evidence_coverage"]["status"] == "NOT_ASSESSED"
    assert s["physical_recall_verification_complete"] is False


def test_missing_target_outcome_is_a_gap():
    p = physical()
    p["traces"][0]["outcome_evidence"] = []
    assert scan(p)["physical_evidence_coverage"]["missing_target_outcomes"] == 1


def test_unverified_downstream_team_is_a_chain_gap_without_counting_an_assist():
    p = physical(target=False, outcome="PLAYER_INTERVENTION")
    p["traces"][0]["outcome_evidence"][0]["goal_review_eligibility"] = {
        "eligible": False, "reason": "DOWNSTREAM_RELEASE_TARGET_TEAM_UNVERIFIED",
    }
    s = scan(p)
    assert s["physical_evidence_coverage"]["unresolved_target_outcomes"] == 1
    assert s["verified_assists"] == 0


def test_coverage_does_not_mutate_any_evidence():
    p = physical(target_proof=False)
    original = deepcopy(p)
    scan(p)
    assert p == original


def test_partial_coverage_preserves_already_verified_canonical_counts():
    s = runtime._scoring_scan(
        {"metrics": {"goals": 1, "assists": 2}},
        {"coverage_complete": True}, physical(target_proof=False),
    )
    assert s["physical_recall_verification_complete"] is False
    assert (s["verified_goals"], s["verified_assists"]) == (1, 2)


def test_complete_evidence_cannot_override_incomplete_execution():
    p = physical()
    p["recall_coverage"]["verification_complete"] = False
    s = scan(p)
    assert s["physical_evidence_coverage"]["complete"] is True
    assert s["physical_recall_verification_complete"] is False
