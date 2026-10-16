"""One physical episode, monotone outcome evidence, revisitable identity."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import canonical_event_resolver as resolver
import cross_window_evidence as overlap
import dense_event_reconciliation as feedback
import fix10b_reconciliation as recon
import test_fix09b3_canonical_event_resolver as actor_fixture
import test_fix10b_reconciliation as fixture
import test_fix13_cross_window_evidence as window_fixture


def pending_shot():
    bundle = fixture.canonical([])
    bundle["unresolved"] = [{"action_id": "shot", "sequence_id": "seq",
        "scene_id": "scene_007", "kind": "SHOT", "start_ms": 23067,
        "contact_ms": 23133, "end_ms": 24500,
        "actor_resolution": {"status": "UNRESOLVED",
                             "reason": "INSUFFICIENT_PHYSICAL_IDENTITY_EVIDENCE"}}]
    return bundle


def release_window(name, *, goal=False, sid=None, track="p083"):
    strike = fixture.strike(23616, track, target=True, sid=sid)
    trace = fixture.trace([fixture.touch(23616, track, target=True)], [strike],
                          [fixture.outcome(strike, goal=goal, crossing_ms=24000)])
    trace["trace_id"] = name
    trace["window"].update(dense_window_id=name, start_ms=23000, end_ms=25000)
    trace["decoded_frames"] = [{"media_ms": ms, "scene_id": "scene_007",
        "time_authority": "ACTUAL_MEDIA_PTS", "players": [{"local_track_id": track,
            "association_state": "VERIFIED_LOCAL", "box": deepcopy(window_fixture.BOX)}]}
        for ms in range(23000, 25001, 50)]
    trace["ball_trajectory"] = [window_fixture.measured(ms) for ms in range(23000, 25001, 50)]
    trace["touch_graph"]["touches"][0]["ball_at_contact"] = window_fixture.measured(23616)
    return trace


def test_unknown_overlap_does_not_cancel_verified_goal():
    good = release_window("goal", goal=True)
    unknown = release_window("unknown", sid="second-window")
    out = recon.reconcile_canonical_events(pending_shot(), {"traces": [good, unknown]})
    assert out["metrics"]["goals"] == 1
    assert out["reconciliation"]["proposals_contradictory"] == 0
    assert out["metrics"]["shots"] == 1
    assert not out["unresolved"]
    assert out["events"][0]["source_action_ids"] == ["shot"]
    assert out["reconciliation"]["shot_observations_linked_to_proved_outcome"] == 1


def test_unknown_unjoined_window_is_not_a_counterproof_to_a_verified_goal():
    good = release_window("goal", goal=True)
    unknown = release_window("unknown", sid="second-window")
    unknown["decoded_frames"] = []
    out = recon.reconcile_canonical_events(pending_shot(), {"traces": [good, unknown]})
    assert out["metrics"]["goals"] == 1


def test_unknown_overlap_cannot_downgrade_verified_save():
    good = release_window("saved")
    result = good["outcome_evidence"][0]
    result.update(physical_outcome="GOALKEEPER_SAVE_EVIDENCE",
                  save_evidence={"status": "VERIFIED"},
                  intervention={"status": "VERIFIED", "media_ms": 24000},
                  intervention_role={"status": "VERIFIED", "role": "GOALKEEPER"})
    unknown = release_window("unknown", sid="second-window")
    unknown["decoded_frames"] = []
    out = recon.reconcile_canonical_events(pending_shot(), {"traces": [good, unknown]})
    assert len(out["events"]) == 1
    assert out["events"][0]["canonical_outcome"] == "SAVED"
    assert out["metrics"]["shots"] == 1


@pytest.mark.parametrize("reverse", [False, True])
def test_proven_same_release_in_two_windows_is_one_candidate(reverse):
    traces = [release_window("a"), release_window("b", sid="b-strike", track="other-local-id")]
    assert overlap.build({"traces": traces})["links"]
    if reverse:
        traces.reverse()
    out = recon.reconcile_canonical_events(pending_shot(), {"traces": traces})
    assert out["metrics"]["shots"] == 1
    assert out["events"][0]["canonical_outcome"] == "UNKNOWN"
    assert not out["unresolved"]


def test_same_time_without_measured_overlap_remains_ambiguous():
    traces = [release_window("a"), release_window("b", sid="b-strike")]
    traces[1]["ball_trajectory"] = []
    assert not overlap.build({"traces": traces})["links"]
    out = recon.reconcile_canonical_events(pending_shot(), {"traces": traces})
    assert out["metrics"]["shots"] == 0


def test_distinct_same_window_strikes_are_not_deduplicated_by_actor_and_time():
    trace = release_window("a")
    other = deepcopy(trace["strike_evidence"][0])
    other["strike_id"] = "another-contact-hypothesis"
    trace["strike_evidence"].append(other)
    out = recon.reconcile_canonical_events(pending_shot(), {"traces": [trace]})
    assert out["metrics"]["shots"] == 0


def test_overlap_without_same_measured_contact_ball_does_not_merge_contacts():
    traces = [release_window("a"), release_window("b", sid="b-strike")]
    traces[1]["touch_graph"]["touches"][0]["ball_at_contact"]["box"]["x"] = .8
    assert overlap.build({"traces": traces})["links"]
    assert recon.reconcile_canonical_events(pending_shot(), {"traces": traces})["metrics"]["shots"] == 0


def test_shot_recovery_does_not_clear_another_scenes_same_action_id():
    bundle = pending_shot()
    other = {**deepcopy(bundle["unresolved"][0]), "scene_id": "other", "sequence_id": "other_seq"}
    bundle["unresolved"].append(other)
    out = recon.reconcile_canonical_events(bundle, {"traces": [release_window("a")]})
    assert out["unresolved"] == [other]


def corrected_identity_case(kind="CARRY"):
    action = actor_fixture.action(kind=kind, outcome="UNKNOWN")
    sequence = actor_fixture.analysis([action])
    old = actor_fixture.graph([actor_fixture.frame(1000, target="p002")])
    canonical = resolver.resolve_canonical_events(sequence, old, {})
    assert canonical["rejected"], "the old wrong-target decision is reproduced"
    frame = actor_fixture.frame(1000)
    frame.update(time_authority="ACTUAL_MEDIA_PTS", used_fallback=False)
    for body in frame["players"]:
        body["association_state"] = "VERIFIED_LOCAL"
    physical = {"traces": [{"trace_id": "corrected", "decoded_frames": [frame],
                            "strike_evidence": []}]}
    return canonical, sequence, physical


def test_corrected_identity_reopens_old_wrong_player_rejection():
    canonical, sequence, physical = corrected_identity_case()
    source = deepcopy(canonical)
    out = feedback.recover(canonical, sequence, physical, {})
    assert len(out["events"]) == 1
    assert out["events"][0]["canonical_action_type"] == "CARRY"
    assert not out["rejected"]
    assert canonical == source


def test_still_wrong_player_is_not_recovered():
    canonical, sequence, physical = corrected_identity_case()
    physical["traces"][0]["decoded_frames"][0]["global_target"]["local_track_id"] = "p002"
    out = feedback.recover(canonical, sequence, physical, {})
    assert not out["events"]
    assert out["rejected"]


def test_recovered_identity_alone_does_not_prove_a_goal_or_pass_release():
    for kind in ["SHOT", "PASS"]:
        canonical, sequence, physical = corrected_identity_case(kind)
        out = feedback.recover(canonical, sequence, physical, {})
        assert not out["events"]


def test_explicit_duplicate_is_not_reopened_by_new_identity():
    canonical, sequence, physical = corrected_identity_case()
    canonical["rejected"][0]["reason"] = "EXPLICIT_REPLAY_OR_DUPLICATE"
    out = feedback.recover(canonical, sequence, physical, {})
    assert not out["events"]


@pytest.mark.parametrize("reason", ["INSUFFICIENT_PHYSICAL_IDENTITY_EVIDENCE",
    "INCONSISTENT_VISIBLE_ACTOR_TRACK", "INCONSISTENT_ACTOR_EVIDENCE",
    "OTHER_PLAYER_VISIBLE_AT_ACTION", "UNIFIED_TARGET_GEOMETRY_MISMATCH"])
def test_all_identity_decisions_can_be_revisited_but_not_blindly_accepted(reason):
    canonical, sequence, physical = corrected_identity_case()
    canonical["rejected"][0]["reason"] = reason
    out = feedback.recover(canonical, sequence, physical, {})
    assert len(out["events"]) == 1
    assert out["dense_identity_feedback"]["previous_decisions"][0]["reason"] == reason
    physical["traces"][0]["decoded_frames"][0]["global_target"]["local_track_id"] = "p002"
    assert not feedback.recover(canonical, sequence, physical, {})["events"]


@pytest.mark.parametrize("kind", ["PASS", "SHOT"])
def test_fresh_identity_and_release_recover_action_without_inventing_outcome(kind):
    canonical, sequence, physical = corrected_identity_case(kind)
    strike = fixture.strike(1000, "p001", target=True)
    strike["scene_id"] = "scene_001"
    physical["traces"][0]["strike_evidence"] = [strike]
    out = feedback.recover(canonical, sequence, physical, {})
    assert len(out["events"]) == 1
    assert out["events"][0]["canonical_event_type"] == kind
    assert out["events"][0]["canonical_outcome"] == "UNKNOWN"
    assert out["events"][0]["causal_verified"] is False


def test_recovery_does_not_clear_another_scenes_same_local_action_id():
    canonical, sequence, physical = corrected_identity_case()
    other = {**deepcopy(canonical["rejected"][0]), "scene_id": "other", "sequence_id": "other_seq"}
    canonical["rejected"].append(other)
    sequence["sequences"].append({**deepcopy(sequence["sequences"][0]),
                                  "scene_id": "other", "sequence_id": "other_seq"})
    out = feedback.recover(canonical, sequence, physical, {})
    assert len(out["events"]) == 1
    assert out["rejected"] == [other]


@pytest.mark.parametrize("change", [{"used_fallback": True}, {"time_authority": "REQUESTED_TIME"}])
def test_non_actual_dense_geometry_cannot_reopen_a_rejection(change):
    canonical, sequence, physical = corrected_identity_case()
    physical["traces"][0]["decoded_frames"][0].update(change)
    assert not feedback.recover(canonical, sequence, physical, {})["events"]


def test_conflicting_fresh_target_bodies_are_not_hidden_by_a_nearby_good_frame():
    canonical, sequence, physical = corrected_identity_case()
    good = physical["traces"][0]["decoded_frames"][0]
    conflict = deepcopy(good)
    conflict["global_target"]["local_track_id"] = "p002"
    near = deepcopy(good)
    near["media_ms"] = 950
    physical["traces"][0]["decoded_frames"].append(near)
    physical["traces"].append({"trace_id": "conflict", "decoded_frames": [conflict]})
    assert not feedback.recover(canonical, sequence, physical, {})["events"]


def test_same_local_track_name_cannot_borrow_a_release_from_an_unlinked_window():
    canonical, sequence, physical = corrected_identity_case("PASS")
    strike = fixture.strike(1000, "p001", target=True)
    strike["scene_id"] = "scene_001"
    physical["traces"].append({"trace_id": "other", "strike_evidence": [strike]})
    assert not feedback.recover(canonical, sequence, physical, {})["events"]


def test_shot_feedback_uses_shared_release_interval_and_actual_contact_time():
    canonical, sequence, physical = corrected_identity_case("SHOT")
    canonical["rejected"][0]["end_ms"] = 1800
    sequence["sequences"][0]["actions"][0]["end_ms"] = 1800
    strike = fixture.strike(1483, "p001", target=True)
    strike["scene_id"] = "scene_001"
    physical["traces"][0]["strike_evidence"] = [strike]
    out = feedback.recover(canonical, sequence, physical, {})
    assert len(out["events"]) == 1
    assert out["events"][0]["canonical_ms"] == 1483
    assert out["events"][0]["canonical_outcome"] == "UNKNOWN"
    assert out["events"][0]["proof"]["contact_geometry"] is None


def test_identity_feedback_is_idempotent_with_other_pending_observations():
    canonical, sequence, physical = corrected_identity_case()
    other = {**deepcopy(canonical["rejected"][0]), "scene_id": "other", "sequence_id": "other_seq"}
    canonical["rejected"].append(other)
    first = feedback.recover(canonical, sequence, physical, {})
    second = feedback.recover(first, sequence, physical, {})
    assert second == first
