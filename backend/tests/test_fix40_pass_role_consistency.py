"""One video observation owns its receiver/finisher roles and pass outcome.

Replies below are test doubles. Actual report-300 component replay is recorded
separately; these tests make no claim about fresh model perception.
"""
from copy import deepcopy

import pytest

import dense_event_reconciliation as reconciliation
from test_fix31_temporal_video import motion_trace


def role_trace(outcome="COMPLETED", team="OPPONENT", same_finisher=True):
    trace = motion_trace("PASS", outcome)
    action = trace["action_inspections"][0]["video_actions"][0]
    action.update(receiver_team=team, receiver_finisher_same_player=same_finisher)
    return trace


@pytest.mark.parametrize("outcome", ["COMPLETED", "TEAMMATE_SHOT", "TEAMMATE_GOAL"])
def test_observed_opponent_receipt_is_incomplete_pass_not_a_teammate_success(outcome):
    trace = role_trace(outcome)
    before = deepcopy(trace)
    event, = reconciliation.resolve_motion_observations(trace)["events"]
    assert event["canonical_event_type"] == "PASS"
    assert event["canonical_outcome"] == "INCOMPLETE"
    assert event["causal_verified"]
    assert event["resolution_reason"] == "VISIBLE_PASS_INTERCEPTED"
    assert event["proof"]["video_observation"]["assist_roles"]["receiver_team"] == "OPPONENT"
    assert trace == before


def test_report_stats_do_not_count_an_intercepted_pass_as_completed_or_key_pass():
    import fix10b_runtime as runtime
    import verified_stats
    result = runtime.reconcile_unified_result({}, {"traces": [role_trace("TEAMMATE_SHOT")]})
    counts = verified_stats.build_verified_stats(result, result["scoring_scan"])["observed_counts"]
    assert counts["passes_attempted"] == 1
    assert counts["passes_completed"] == counts["key_passes"] == counts["assists"] == 0


@pytest.mark.parametrize("outcome", ["TEAMMATE_SHOT", "TEAMMATE_GOAL"])
def test_different_finisher_preserves_completed_pass_without_inventing_direct_assist(outcome):
    trace = role_trace(outcome, "TEAMMATE", False)
    event, = reconciliation.resolve_motion_observations(trace)["events"]
    assert event["canonical_event_type"] == "PASS"
    assert event["canonical_outcome"] == "COMPLETED"
    assert event["causal_verified"]
    assert event["resolution_reason"] == "VISIBLE_PASS_DIFFERENT_FINISHER"


@pytest.mark.parametrize("missing", ["receipt", "contact", "visibility", "same_actor"])
def test_incomplete_role_evidence_never_invents_a_failed_or_completed_transfer(missing):
    trace = role_trace()
    raw = trace["action_inspections"][0]["video_actions"][0]
    if missing == "receipt": raw["receiver_idx"] = None
    elif missing == "contact": raw["contact_idx"] = None
    elif missing == "visibility": raw["outcome_visible"] = False
    else: raw["receiver_body_id"] = raw["actor_body_id"]
    event, = reconciliation.resolve_motion_observations(trace)["events"]
    assert event["canonical_outcome"] == "UNKNOWN"
    assert not event["causal_verified"]


def test_observed_receipt_role_does_not_require_an_extra_native_receiver_identity():
    trace = role_trace()
    trace["action_inspections"][0]["video_actions"][0]["receiver_body_id"] = None
    event, = reconciliation.resolve_motion_observations(trace)["events"]
    assert event["canonical_outcome"] == "INCOMPLETE" and event["causal_verified"]


@pytest.mark.parametrize("kind", ["CROSS", "KEY_PASS"])
def test_opponent_receipt_also_prevents_success_for_crosses_and_key_pass_labels(kind):
    trace = role_trace("TEAMMATE_SHOT")
    trace["action_inspections"][0]["video_actions"][0]["kind"] = kind
    event, = reconciliation.resolve_motion_observations(trace)["events"]
    assert event["canonical_event_type"] == kind and event["canonical_outcome"] == "INCOMPLETE"


@pytest.mark.parametrize("team,same_finisher,expected", [
    ("OPPONENT", True, "INCOMPLETE"), ("TEAMMATE", False, "COMPLETED")])
def test_first_whole_video_read_uses_the_same_role_resolution(team, same_finisher, expected):
    from test_fix38_sequence_observation_reuse import response, finalise
    raw = response("PASS", "TEAMMATE_GOAL")
    raw["sequences"][0]["actions"][0]["causal_chain"].update(
        receiver_team=team, receiver_finisher_same_player=same_finisher)
    event, = finalise(raw)["canonical_events"]["events"]
    assert event["canonical_event_type"] == "PASS" and event["canonical_outcome"] == expected


def test_unspecified_legacy_roles_keep_the_original_observed_completed_pass():
    trace = motion_trace("PASS", "COMPLETED")
    event, = reconciliation.resolve_motion_observations(trace)["events"]
    assert event["canonical_event_type"] == "PASS" and event["canonical_outcome"] == "COMPLETED"


def test_already_observed_incomplete_pass_does_not_need_another_receipt_approval():
    trace = role_trace("INCOMPLETE")
    trace["action_inspections"][0]["video_actions"][0].update(receiver_idx=None, receiver_body_id=None)
    event, = reconciliation.resolve_motion_observations(trace)["events"]
    assert event["canonical_outcome"] == "INCOMPLETE" and event["causal_verified"]


def test_normal_direct_teammate_assist_is_preserved():
    event, = reconciliation.resolve_motion_observations(role_trace("TEAMMATE_GOAL", "TEAMMATE"))["events"]
    assert event["canonical_event_type"] == "ASSIST"
    assert event["canonical_outcome"] == "TEAMMATE_GOAL"
