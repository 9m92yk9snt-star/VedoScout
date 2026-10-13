from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fix10b_runtime
import reviewed_goal


def approval():
    return {"review_id": "r1", "reviewer": "video_owner", "reviewed_at": "2026-10-13",
            "scene_id": "scene_003", "actor_id": "GLOBAL_TARGET", "contact_ms": 30915,
            "source_video_sha256": "a" * 64, "decision": "APPROVE_GOAL",
            "source": "EXPLICIT_USER_REVIEW", "statement": "I confirm this goal",
            "observations": ["Ball reappears inside goal after body occlusion"]}


def test_review_is_separate_from_automatic_proof_and_does_not_mutate():
    row = approval()
    before = deepcopy(row)
    result = fix10b_runtime.reconcile_unified_result(
        {}, {}, trusted_goal_approvals=[row], source_video_sha256="a" * 64)
    assert row == before
    assert result["metrics"]["verified_goals"] == 0
    assert result["metrics"]["confirmed_goals_including_user_review"] == 1
    assert result["reviewed_scoring"]["events"][0]["automatic_proof_eligible"] is False
    assert not result["canonical_events"]["events"]


def test_untrusted_embedded_approval_is_not_consumed():
    result = fix10b_runtime.reconcile_unified_result(
        {"trusted_goal_approvals": [approval()], "reviewed_scoring": {"events": [approval()]}}, {})
    assert result["reviewed_scoring"]["events"] == []


def test_source_binding_and_explicit_decision_required():
    for field, value in [("source_video_sha256", "b" * 64), ("decision", "SUGGEST_GOAL"),
                         ("source", "MODEL_RESPONSE"), ("reviewer", ""), ("contact_ms", True),
                         ("observations", [])]:
        row = approval()
        row[field] = value
        result = reviewed_goal.project([row], source_video_sha256="a" * 64)
        assert result["user_confirmed_goals"] == 0
        assert result["rejected"]


def test_no_double_count_when_automatic_goal_exists():
    event = {"canonical_event_type": "GOAL", "scene_id": "scene_003",
             "global_target_id": "GLOBAL_TARGET", "canonical_ms": 30915,
             "reconciliation_authority": "FIX10B_PHYSICAL_RECONCILIATION"}
    result = reviewed_goal.project([approval(), approval()], source_video_sha256="a" * 64,
                                  automatic_events=[event])
    assert result["user_confirmed_goals"] == 1
    assert result["additional_user_confirmed_goals"] == 0


def test_original_confirmation_remains_human_sourced():
    path = Path(__file__).resolve().parents[2] / "docs" / "original-goal-user-review.json"
    row = json.loads(path.read_text())
    result = reviewed_goal.project([row], source_video_sha256=row["source_video_sha256"])
    assert result["user_confirmed_goals"] == 1
    assert result["events"][0]["observation_authority"] == "HUMAN_REVIEW_NOT_MACHINE_MEASUREMENT"
