"""Meaningful failure cases; all responses here are synthetic, not model proof."""
from copy import deepcopy
import hashlib
import json
import multiprocessing
from pathlib import Path
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sequence_pilot as p
import sequence_pilot_transport as t
from scripts.run_sequence_pilot import run
from scripts.run_sequence_pilot import fresh_original_manifest


def fixture():
    frames = [{"frame_id": f"s{i:09}", "media_ms": i} for i in (0, 125, 250, 500, 750, 1000, 1250, 1500, 1750, 2000, 2500, 3000, 4000, 5000, 6000, 8000)]
    packet = {"packet_id": "first", "phase": "INITIAL", "start_ms": 0, "end_ms": 8000,
              "frame_ids": [f["frame_id"] for f in frames], "reference_ids": ["r1"]}
    manifest = {"source_video_sha256": "source", "source_end_ms": 8000, "frames": frames,
                "references": [], "packets": [packet], "preparation_seconds": 0,
                "input_coverage": {"max_sample_gap_ms": 125}}
    people = [{"person_id": "passer", "selected": True, "kit_consistent": True, "reference_ids": ["r1"],
               "evidence_frames": ["s000000500"]},
              {"person_id": "finisher", "selected": False, "kit_consistent": True, "reference_ids": [],
               "evidence_frames": ["s000001250", "s000001500"]}]
    action = {"action_id": "a1", "kind": "PASS", "actor": "passer", "start_frame": "s000000500",
        "contact_frame": "s000001000", "end_frame": "s000001250", "actor_evidence_frames": ["s000000500", "s000001000"],
        "ball_id": "active", "outcome": "TEAMMATE_GOAL", "receiver": "finisher", "receiver_frame": "s000001250",
        "receiver_is_teammate": True, "finisher": "finisher", "shot_frame": "s000001500", "outcome_frame": "s000002000",
        "same_active_ball": True, "continuous_play": True,
        "outcome_evidence": [{"frame": "s000002000", "fact": "The moving ball is inside the goal."}]}
    play = {"start_frame": "s000000000", "end_frame": "s000003000", "people": people, "actions": [action], "questions": []}
    return manifest, packet, {"plays": [play]}


def test_shared_profile_cannot_invent_references_or_change_source_frames():
    manifest, _, _ = fixture()
    manifest["references"] = [{"reference_id": "r1"}]
    profile = {"identity_clear": True, "appearance": "Visible white kit and light hair",
               "canonical_reference_ids": ["r1"]}
    reused = p.apply_identity_profile(manifest, profile)
    assert p.apply_identity_profile(manifest, [profile]) == reused
    assert reused["frames"] == manifest["frames"]
    assert reused["packets"][0]["frame_ids"] == manifest["packets"][0]["frame_ids"]
    assert "identity_profile" not in manifest
    profile["canonical_reference_ids"] = ["invented"]
    with pytest.raises(ValueError, match="IDENTITY_PROFILE_UNRESOLVED"):
        p.apply_identity_profile(manifest, profile)
    with pytest.raises(ValueError, match="IDENTITY_PROFILE_UNRESOLVED"):
        p.apply_identity_profile(manifest, [profile, profile])


def test_fresh_whole_source_input_removes_inferred_profile_without_dropping_source_or_originals():
    manifest,packet,_=fixture()
    manifest["references"]=[{"reference_id":"r1"},{"reference_id":"r2"}]
    manifest["identity_profile"]={"appearance":"old disputed appearance","canonical_reference_ids":["r1"]}
    fresh=fresh_original_manifest(manifest)
    assert "identity_profile" not in fresh and "identity_profile" in manifest
    assert fresh["frames"] == manifest["frames"] and fresh["references"] == manifest["references"]
    assert fresh["packets"][0]["frame_ids"] == packet["frame_ids"]
    assert fresh["packets"][0]["reference_ids"] == ["r1","r2"]
    assert fresh["packets"][0]["contact_sequence_evidence"] is True


def test_fresh_original_reference_scope_does_not_allow_two_physical_selected_people():
    manifest,_,data=fixture()
    manifest["references"]=[{"reference_id":"r1"},{"reference_id":"r2"}]
    fresh=fresh_original_manifest(manifest)
    data["plays"][0]["people"][1].update(selected=True,reference_ids=["r2"])
    resolved=p.resolve_response(data,fresh,fresh["packets"][0],{})
    assert any(q["reason"] == "IDENTITY_CONFLICT" for q in resolved["questions"])
    assert p.reconcile([resolved])["target_events"] == []


@pytest.mark.parametrize("reuse", [{"identity_profile":True},{"identity_profile_receipt":"old.json"},
                                   {"resume_initial_receipts":"old.json"}])
def test_fresh_full_source_mode_cannot_replay_old_model_answers(tmp_path,reuse):
    manifest,_,_=fixture();p.write_json(tmp_path/"manifest.json",manifest)
    with pytest.raises(ValueError,match="FRESH_ORIGINALS_CANNOT_REPLAY_MODEL_RESULTS"):
        run(tmp_path/"manifest.json",tmp_path/"result",fresh_originals=True,**reuse)


def test_unclear_identity_profile_does_not_silently_choose_a_player():
    manifest, _, _ = fixture()
    manifest["references"] = [{"reference_id": "r1"}]
    with pytest.raises(ValueError, match="IDENTITY_PROFILE_UNRESOLVED"):
        p.apply_identity_profile(manifest, {"identity_clear": False, "appearance": "Two different players",
                                          "canonical_reference_ids": ["r1"]})


def test_shared_profile_preserves_original_in_play_identity_examples():
    manifest, _, _ = fixture()
    manifest["references"] = [{"reference_id": "r1", "media_ms": 9000}, {"reference_id": "r2", "media_ms": 1500}]
    profile = {"identity_clear": True, "appearance": "white player", "canonical_reference_ids": ["r1"]}
    assert p.apply_identity_profile(manifest, profile)["packets"][0]["reference_ids"] == ["r1", "r2"]


def test_estimated_finishing_contact_does_not_answer_its_own_model_question():
    manifest, packet, data = fixture()
    data["plays"][0]["actions"].append({"action_id": "finish", "kind": "SHOT", "actor": "finisher",
        "start_frame": "s000001250", "contact_frame": "s000001500", "end_frame": "s000002000",
        "actor_evidence_frames": ["s000001250", "s000001500"], "outcome": "GOAL", "outcome_frame": "s000002000",
        "same_active_ball": True, "continuous_play": True,
        "outcome_evidence": [{"frame": "s000002000", "fact": "The active ball enters the goal."}]})
    data["plays"][0]["questions"] = [{"reason": "CONTACT", "action_id": "finish"}]
    initial = p.resolve_response(data, manifest, packet, {"origin": "SYNTHETIC_TEST_ONLY"})
    merged = p.reconcile([initial])
    assert "ASSIST" not in merged["counts"]
    q = next(q for q in merged["questions"] if q.get("explicit_model_question"))
    assert q["focus_ms"] == 1500 and q["target_related"] is True
    jobs = p.plan_contact_reviews(manifest, merged)
    assert len(jobs) == 1 and jobs[0]["question"]["source_action_key"] == q["source_action_key"]
    # Only a genuinely clarified later reading can resolve the question.
    data["plays"][0]["questions"] = []
    review = {**packet, "packet_id": "review", "phase": "FOLLOWUP", "question": q}
    clarified = p.resolve_response(data, manifest, review, {"origin": "SYNTHETIC_TEST_ONLY"})
    final = p.reconcile([initial, clarified])
    assert final["counts"].get("ASSIST") == 1
    assert not any(q.get("explicit_model_question") for q in final["questions"])


def cold_saved_shot_question_fixture():
    # Actual raw model response, offline resolver test only. The original
    # unscoped question is not retrospectively changed in the retained run.
    root = Path(__file__).resolve().parents[2]
    retained = p.read_json(root / "docs/examples/sequence-report-cold-failed.json")
    audit = retained["report_document"]["sequence_audit"]
    receipt = next(r for r in audit["receipts"] if r["packet_id"] == "contact_review_002")
    raw = __import__('json').loads(receipt["raw_response"])
    manifest = {"source_video_sha256": audit["source_video_sha256"],
                "frames": audit["source_frames"], "references": audit["references"],
                "source_end_ms": max(f["media_ms"] for f in audit["source_frames"])}
    packet = {"packet_id": receipt["packet_id"], "phase": "FOLLOWUP",
              "frame_ids": [f["frame_id"] for f in audit["source_frames"]],
              "reference_ids": [r["reference_id"] for r in audit["references"]]}
    question = next(q for q in raw["plays"][0]["questions"] if q["action_id"] == "a4")
    return manifest, packet, raw, receipt, question


def test_actual_unscoped_rebound_question_remains_blocking_and_keeps_its_text():
    manifest, packet, raw, receipt, question = cold_saved_shot_question_fixture()
    resolved = p.resolve_response(raw, manifest, packet, receipt)
    shot = next(e for e in resolved["events"] if e["kind"] == "SHOT")
    assert shot["selected_player"] is True and shot["outcome"] == "SAVED"
    assert shot["proof_eligible"] is False
    q = next(q for q in resolved["questions"] if q["action_id"] == "a4")
    assert q["scope"] == "ACTION" and q["question"] == question["question"]


def actual_validated_shot():
    saved = p.read_json(Path(__file__).resolve().parents[2] / "docs/examples/sequence-shot-filter-validation.json")
    r = saved["result"]
    receipt = r["receipt"]
    assert receipt["origin"] == "LIVE_MODEL_REQUEST" and receipt["status"] == "COMPLETED"
    assert hashlib.sha256(receipt["raw_response"].encode()).hexdigest() == receipt["response_sha256"]
    assert receipt["payload_sha256"] == r["request_audit"]["payload_sha256"]
    manifest = {"source_video_sha256": r["source_video_sha256"], "frames": r["source_frames"],
                "references": r["references"]}
    return r, manifest, p.parse_response(receipt["raw_response"])


def test_actual_live_aftermath_question_preserves_selected_saved_shot():
    r, manifest, raw = actual_validated_shot()
    resolved = p.reconcile([p.resolve_response(raw, manifest, r["packet"],
        {k: r["receipt"][k] for k in ("packet_id", "payload_sha256", "response_sha256", "origin")})])
    assert resolved == r["resolved"]
    shot = next(e for e in resolved["target_events"] if e["kind"] == "SHOT")
    assert shot["selected_player"] is True and shot["outcome"] == "SAVED"
    assert shot["contact_interval_ms"] == [23682, 23749]
    assert shot["reference_ids"] == ["r5", "r6"]
    assert shot["proof_eligible"] is True and shot["model_requested_clarification"] is False
    assert len(resolved["questions"]) == 1 and resolved["questions"][0]["scope"] == "AFTERMATH"
    assert r["model_calls"] == 1 and r["fresh_end_to_end_timing"] is False
    assert r["expected_answers_used_as_input"] is False


@pytest.mark.parametrize("change", [
    lambda q, a: q.update(scope="ACTION"),
    lambda q, a: q.update(after_frame="s000023682"),
    lambda q, a: a.update(contact_actor_unique=False),
    lambda q, a: a.update(same_active_ball=False),
])
def test_actual_live_shot_does_not_bypass_new_action_uncertainty(change):
    r, manifest, raw = actual_validated_shot()
    q = raw["plays"][0]["questions"][0]
    action = next(a for a in raw["plays"][0]["actions"] if a["kind"] == "SHOT")
    change(q, action)
    resolved = p.resolve_response(raw, manifest, r["packet"], r["receipt"])
    shot = next(e for e in resolved["events"] if e["kind"] == "SHOT")
    assert shot["proof_eligible"] is False and shot["model_requested_clarification"] is True


def test_structured_later_possession_question_keeps_saved_shot_and_unknown_aftermath():
    manifest, packet, raw, receipt, question = cold_saved_shot_question_fixture()
    question.update(scope="AFTERMATH", after_frame="s000025516")
    resolved = p.reconcile([p.resolve_response(raw, manifest, packet, receipt)])
    shot = next(e for e in resolved["target_events"] if e["kind"] == "SHOT")
    assert shot["outcome"] == "SAVED" and shot["contact_interval_ms"] == [23666, 23749]
    assert shot["model_requested_clarification"] is False
    q = next(q for q in resolved["questions"] if q["action_id"] == "a4")
    assert q["scope"] == "AFTERMATH" and q["after_ms"] == 25516
    assert any(q["action_id"] == "a2" and q["scope"] == "ACTION" for q in resolved["questions"])
    aftermath_only = {**resolved, "questions": [q]}
    assert p.plan_contact_reviews(manifest, aftermath_only) == []
    assert p.followup_plan(manifest, aftermath_only) == []


@pytest.mark.parametrize("change", [
    lambda q, a: q.update(scope="ACTION"),
    lambda q, a: q.update(scope="unrecognised"),
    lambda q, a: q.update(reason="CONTACT"),
    lambda q, a: q.update(reason="IDENTITY"),
    lambda q, a: q.update(after_frame=None),
    lambda q, a: q.update(after_frame="s000023666"),
    lambda q, a: a.update(outcome="UNKNOWN"),
    lambda q, a: a.update(same_active_ball=False),
    lambda q, a: a.update(contact_actor_unique=False),
])
def test_aftermath_scope_cannot_bypass_missing_or_uncertain_action_proof(change):
    manifest, packet, raw, receipt, question = cold_saved_shot_question_fixture()
    question.update(scope="AFTERMATH", after_frame="s000025516")
    action = next(a for a in raw["plays"][0]["actions"] if a["action_id"] == "a4")
    change(question, action)
    resolved = p.resolve_response(raw, manifest, packet, receipt)
    shot = next(e for e in resolved["events"] if e["kind"] == "SHOT")
    assert shot["proof_eligible"] is False
    assert shot["model_requested_clarification"] is True


def test_contact_question_is_not_filtered_out_by_coarse_run_label():
    manifest, packet, data = fixture()
    a = data["plays"][0]["actions"][0]
    a.update(kind="RUN", contact_frame=None, outcome="UNKNOWN", receiver=None, finisher=None)
    data["plays"][0]["questions"] = [{"reason": "CONTACT", "action_id": "a1"}]
    jobs = p.plan_contact_reviews(manifest, p.reconcile([p.resolve_response(data, manifest, packet, {})]))
    assert len(jobs) == 1 and jobs[0]["question"]["reason"] == "CONTACT"


def test_apparent_selected_control_loss_does_not_hide_later_chance():
    manifest, packet, data = fixture()
    a = data["plays"][0]["actions"][0]
    a.update(kind="DRIBBLE", contact_frame=None, end_frame="s000001000", outcome="INCOMPLETE", receiver=None, finisher=None)
    data["plays"][0]["actions"].append({"action_id": "finish", "kind": "SHOT", "actor": "finisher",
        "start_frame": "s000001250", "contact_frame": None, "end_frame": "s000002000",
        "actor_evidence_frames": ["s000001250", "s000001500"], "outcome": "UNKNOWN", "outcome_frame": "s000002000",
        "same_active_ball": True, "continuous_play": True,
        "outcome_evidence": [{"frame": "s000002000", "fact": "A chance develops near the goal."}]})
    jobs = p.plan_contact_reviews(manifest, p.reconcile([p.resolve_response(data, manifest, packet, {})]))
    assert len(jobs) == 1
    assert jobs[0]["detail_start_ms"] < 1000 < 1250 < jobs[0]["detail_end_ms"]


def resolved(data=None):
    manifest, packet, original = fixture()
    return p.resolve_response(data or original, manifest, packet, {"origin": "SYNTHETIC_TEST_ONLY"})


def test_direct_assist_credits_passer_not_receivers_goal():
    r = p.reconcile([resolved()])
    assert r["counts"] == {"ASSIST": 1}
    assert r["target_events"][0]["actor"] == "passer"


def bracketed_shot():
    data = shot()
    a = data["plays"][0]["actions"][0]
    a.update(contact_frame=None, contact_before_frame="s000000750", contact_after_frame="s000001000",
             contact_actor_unique=True, contact_evidence=[
                 {"frame": "s000000750", "fact": "Only the actor swings toward the incoming ball."},
                 {"frame": "s000001000", "fact": "The ball leaves along the direction of that foot swing."}])
    return data


def test_contact_bracket_preserves_interval_without_inventing_exact_touch():
    e = p.reconcile([resolved(bracketed_shot())])["target_events"][0]
    assert e["event_type"] == "GOAL"
    assert e["contact_ms"] is None
    assert e["contact_interval_ms"] == [750, 1000]
    assert e["contact_basis"] == "BRACKETED_VISUAL_SEQUENCE"


@pytest.mark.parametrize("field,value", [
    ("contact_actor_unique", False), ("contact_actor_unique", "true"),
    ("contact_after_frame", "not_supplied"), ("contact_after_frame", "s000000500"),
    ("contact_after_frame", "s000002000"), ("contact_evidence", []),
    ("contact_before_frame", "s000000000")])
def test_unproven_or_invalid_contact_bracket_cannot_approve_goal(field, value):
    data = bracketed_shot(); data["plays"][0]["actions"][0][field] = value
    assert p.reconcile([resolved(data)])["counts"] == {}


def test_contact_bracket_cannot_override_explicit_uncertainty_or_spare_ball():
    data = bracketed_shot(); data["plays"][0]["questions"] = [{"reason": "CONTACT", "action_id": "a1"}]
    assert p.reconcile([resolved(data)])["counts"] == {}
    data["plays"][0]["questions"] = []
    data["plays"][0]["actions"][0]["same_active_ball"] = False
    assert p.reconcile([resolved(data)])["counts"] == {}


@pytest.mark.parametrize("field,value", [("same_active_ball", False), ("continuous_play", False),
    ("receiver_is_teammate", None), ("receiver_frame", "not_supplied"), ("shot_frame", None), ("finisher", "another_person")])
def test_missing_causal_link_does_not_become_assist(field, value):
    _, _, data = fixture(); data["plays"][0]["actions"][0][field] = value
    r = p.reconcile([resolved(data)])
    assert "ASSIST" not in r["counts"]
    assert any(q["reason"] == "RECEIVER" for q in r["questions"])


def test_both_participants_cannot_be_selected_person():
    _, _, data = fixture(); data["plays"][0]["people"][1].update(selected=True, reference_ids=["r1"])
    r = p.reconcile([resolved(data)])
    assert r["target_events"] == []
    assert any(q["reason"] == "IDENTITY_CONFLICT" for q in r["questions"])
    assert len(r["events"]) == 1  # retain the visible play for targeted attribution


def test_kit_contradiction_overrides_positive_target_label():
    _, _, data = fixture(); data["plays"][0]["people"][0]["kit_consistent"] = False
    assert p.reconcile([resolved(data)])["target_events"] == []


def test_opponent_receipt_preserves_incomplete_pass():
    _, _, data = fixture(); data["plays"][0]["actions"][0]["receiver_is_teammate"] = False
    e = p.reconcile([resolved(data)])["target_events"][0]
    assert (e["event_type"], e["outcome"]) == ("PASS", "INCOMPLETE")


def shot(outcome="GOAL"):
    _, _, data = fixture(); a = data["plays"][0]["actions"][0]
    a.update(kind="SHOT", outcome=outcome, end_frame="s000003000")
    return data


def test_spare_ball_without_active_ball_continuity_is_not_goal():
    data = shot(); data["plays"][0]["actions"][0]["same_active_ball"] = None
    assert p.reconcile([resolved(data)])["target_events"] == []


def test_keeper_dive_without_outcome_evidence_does_not_verify_save():
    data = shot("SAVED"); data["plays"][0]["actions"][0]["outcome_evidence"] = []
    assert p.reconcile([resolved(data)])["target_events"] == []


def test_save_does_not_need_separate_native_ball_or_keeper_boxes():
    e = p.reconcile([resolved(shot("SAVED"))])["target_events"][0]
    assert (e["event_type"], e["outcome"]) == ("SHOT", "SAVED")


def test_outcome_after_contact_must_be_chronological():
    data = shot(); data["plays"][0]["actions"][0]["outcome_frame"] = "s000000750"
    assert p.reconcile([resolved(data)])["target_events"] == []


def test_source_frame_outside_packet_does_not_become_evidence():
    _, _, data = fixture(); data["plays"][0]["actions"][0]["actor_evidence_frames"] = ["s000999999"]
    r = resolved(data)
    assert not r["events"] and r["invalid_rows"]


def test_two_observations_of_terminal_goal_merge_despite_contact_disagreement():
    a, b = resolved(shot()), resolved(shot())
    b["events"][0].update(event_id="different", contact_ms=1500, source_packet_ids=["second"])
    r = p.reconcile([a, b])
    assert r["counts"] == {"GOAL": 1}
    assert r["target_events"][0]["contact_interval_ms"] == [1000, 1500]
    assert len(r["target_events"][0]["receipts"]) == 2


def test_different_rebound_shots_are_retained():
    a, b = resolved(shot("SAVED")), resolved(shot("GOAL"))
    b["events"][0].update(event_id="rebound", start_ms=2500, contact_ms=3000, outcome_ms=4000, end_ms=5000)
    assert p.reconcile([a, b])["counts"] == {"SHOT": 1, "GOAL": 1}


def test_fast_rebound_is_not_a_conflict_just_because_outcomes_are_close():
    a, b = resolved(shot("SAVED")), resolved(shot("GOAL"))
    b["events"][0].update(event_id="rebound", contact_ms=1500, outcome_ms=2125)
    assert p.reconcile([a, b])["counts"] == {"SHOT": 1, "GOAL": 1}


def test_conflict_cannot_be_settled_by_third_initial_opinion():
    r = p.reconcile([resolved(shot("SAVED")), resolved(shot("GOAL")), resolved(shot("GOAL"))])
    assert r["counts"] == {} and r["conflicts"]


def test_specific_followup_can_settle_conflict_and_keep_provenance():
    followup = resolved(shot("SAVED")); followup["events"][0]["review_phase"] = "FOLLOWUP"
    r = p.reconcile([resolved(shot("SAVED")), resolved(shot("GOAL")), followup])
    assert r["counts"] == {"SHOT": 1} and not r["conflicts"]
    assert r["target_events"][0]["superseded_observations"]


def test_packets_cover_entire_source_and_keep_context_overlap():
    jobs = p.plan_packets(76748)
    assert [(j["start_ms"], j["end_ms"]) for j in jobs] == [(0, 30000), (24000, 54000), (48000, 76748)]
    assert all(a["end_ms"] - b["start_ms"] == 6000 for a, b in zip(jobs, jobs[1:]))


def test_missing_link_review_keeps_full_play_and_aftermath():
    manifest, _, _ = fixture()
    r = p.reconcile([resolved(shot("UNKNOWN"))])
    jobs = p.followup_plan(manifest, r)
    assert len(jobs) == 1 and jobs[0]["start_ms"] == 0 and jobs[0]["end_ms"] == 8000
    assert jobs[0]["question"]["reason"] == "OUTCOME"


def test_no_generic_second_read_for_complete_assist():
    manifest, _, _ = fixture()
    assert p.followup_plan(manifest, p.reconcile([resolved()])) == []


def test_wider_packet_already_answered_outcome_does_not_trigger_another_call():
    manifest, _, _ = fixture()
    initial = resolved(shot("UNKNOWN")); later = resolved(shot("SAVED"))
    later["events"][0].update(source_packet_ids=["wider"], source_action_keys=["wider:0:a1"])
    merged = p.reconcile([initial, later])
    assert merged["counts"] == {"SHOT": 1}
    assert p.followup_plan(manifest, merged) == []


def test_original_taps_drop_derived_colours_and_legacy_target_labels():
    row = {"t": 2., "box": {"x": .2, "y": .3, "w": .1, "h": .2}, "target_point": {"x": .25, "y": .4},
           "jersey_name": "navy blue", "global_target_id": "wrong"}
    taps = p.original_taps({"raw_marker_anchors": json.dumps(json.dumps([row]))})
    assert "jersey_name" not in taps[0] and "global_target_id" not in taps[0]


def test_positive_reference_match_cannot_silently_deny_identity_in_consensus_mode():
    manifest, packet, _ = fixture()
    manifest["reference_policy"] = "CONSENSUS_RAW"
    observation = shot("GOAL")
    observation["plays"][0]["people"][0]["selected"] = False
    result = p.resolve_response(observation, manifest, packet, {"origin": "SYNTHETIC_TEST_ONLY"})
    assert result["events"][0]["selected_player"] is None
    assert any(q["reason"] == "IDENTITY" for q in result["questions"])
    assert not p.reconcile([result])["target_events"]


def test_consensus_delivery_excludes_automatic_mask_images_but_keeps_original_crop():
    manifest, packet, _ = fixture()
    manifest["reference_policy"] = "CONSENSUS_RAW"
    reference = {"reference_id": "r1", "media_ms": 0, "path": "original-human-crop.jpg", "sha256": "original",
                 "box": {"x": .2, "y": .3, "w": .1, "h": .2}, "target_point": {"x": .25, "y": .4}}
    manifest["references"] = [reference]
    packet["frame_ids"] = []
    reference["masked_view"] = {"path": "wrong-neighbour-mask.jpg", "sha256": "untrusted"}
    items = p.packet_items(manifest, packet)
    assert any(i.get("path") == reference["path"] for i in items)
    assert not any(i.get("path") == "wrong-neighbour-mask.jpg" for i in items)


def test_visual_packet_boundaries_follow_changed_pixels_and_cover_every_frame(tmp_path):
    import cv2
    import numpy as np
    frames = []
    for index in range(29):
        path = tmp_path / f"{index}.jpg"
        colour = (0, 0, 220) if index < 8 else (220, 0, 0) if index < 18 else (0, 220, 0)
        assert cv2.imwrite(str(path), np.full((80, 60, 3), colour, dtype=np.uint8))
        frames.append({"frame_id": f"f{index}", "media_ms": index * 500, "path": str(path)})
    packets, audit = p.plan_visual_packets(frames, frames[-1]["media_ms"])
    assert [c["media_ms"] for c in audit["changes"]] == [4000, 9000]
    assert all(any(j["start_ms"] <= f["media_ms"] <= j["end_ms"] for j in packets) for f in frames)
    for f in frames:
        f["media_ms"] += 1000
    _packets, shifted = p.plan_visual_packets(frames, frames[-1]["media_ms"])
    assert [c["media_ms"] for c in shifted["changes"]] == [5000, 10000]


def test_reference_matching_uses_buildup_without_changing_contact_time():
    r = p.reconcile([resolved()])
    case = {"case_id": "held_out", "reference_ms": 600, "expected_type": "ASSIST", "expected_outcome": "TEAMMATE_GOAL", "tolerance_ms": 0}
    result = p.assess_reference_cases([case], r)
    assert result["all_reference_cases_matched"]
    assert result["cases"][0]["observed_contact_ms"] == 1000


def test_expected_reference_file_never_enters_preparation_or_request_code():
    import inspect
    assert "assess_reference_cases" not in inspect.getsource(p.prepare)
    assert "reference_ms" not in p.PROMPT and "23680" not in p.PROMPT
    assert "reference_ms" not in inspect.getsource(p.packet_items)


def image_item(tmp_path):
    image = tmp_path / "frame.jpg"; image.write_bytes(b"test-jpeg")
    return {"type": "image", "path": str(image), "sha256": hashlib.sha256(b"test-jpeg").hexdigest()}


@pytest.mark.parametrize("effort", ["low", "medium"])
def test_openai_reasoning_model_uses_completion_budget_without_sampling_override(effort):
    _, body, _ = t.build_request("emergent", "gpt-6-sol", [{"type": "text", "text": "observe"}], reasoning_effort=effort)
    body = json.loads(body)
    assert body["max_completion_tokens"] == 16384
    assert "max_tokens" not in body and "temperature" not in body
    assert body["reasoning_effort"] == effort


@pytest.mark.parametrize("provider", ["gemini", "emergent"])
def test_native_video_keeps_exact_bytes_and_explicit_fps(tmp_path, provider):
    video = tmp_path / "source.mp4"; video.write_bytes(b"synthetic-video")
    item = {"type": "video", "path": str(video), "sha256": p.digest(video), "fps": 8}
    _, body, audit = t.build_request(provider, "gemini-3.1-pro-preview", [item], image_detail="high")
    body = json.loads(body)
    assert audit["explicit_image_count"] == 0
    assert audit["videos"] == [{"sha256": p.digest(video), "bytes": 15, "requested_fps": 8}]
    if provider == "gemini":
        part = body["contents"][0]["parts"][0]
        assert part["inlineData"]["mimeType"] == "video/mp4"
        assert part["videoMetadata"]["fps"] == 8
    else:
        part = body["messages"][0]["content"][0]
        assert part["type"] == "file"
        assert part["file"]["file_data"].startswith("data:video/mp4;base64,")
        assert part["file"]["video_metadata"] == {"fps": 8}


@pytest.mark.parametrize("fps", [25, 30, 60, float("nan"), True])
def test_native_video_rejects_unsupported_sampling_before_request(tmp_path, fps):
    video = tmp_path / "source.mp4"; video.write_bytes(b"synthetic-video")
    item = {"type": "video", "path": str(video), "sha256": p.digest(video), "fps": fps}
    with pytest.raises(ValueError, match="INVALID_VIDEO_FPS"):
        t.build_request("emergent", "gemini-3.1-pro-preview", [item])


@pytest.mark.parametrize("provider", ["gemini", "emergent"])
def test_gemini3_uses_its_supported_reasoning_and_temperature_defaults(provider):
    _, body, _ = t.build_request(provider, "gemini-3.1-pro-preview", [{"type": "text", "text": "observe"}], reasoning_effort="low")
    body = json.loads(body)
    config = body["generationConfig"] if provider == "gemini" else body
    assert "temperature" not in config
    if provider == "gemini":
        assert config["thinkingConfig"] == {"thinkingLevel": "LOW"}
    else:
        assert body["model"] == "gemini/gemini-3.1-pro-preview"
        assert body["reasoning_effort"] == "low"


@pytest.mark.parametrize("provider", ["gemini", "emergent"])
def test_model_detail_setting_is_distinct_from_source_image_bytes(tmp_path, provider):
    item = image_item(tmp_path)
    _, standard, a = t.build_request(provider, "gemini-2.5-pro", [item])
    _, detailed, b = t.build_request(provider, "gemini-2.5-pro", [item], image_detail="high")
    assert a["images"] == b["images"]
    assert a["requested_image_detail"] is None and b["requested_image_detail"] == "high"
    body = json.loads(detailed)
    if provider == "gemini":
        assert body["generationConfig"]["mediaResolution"] == "MEDIA_RESOLUTION_HIGH"
        assert "mediaResolution" not in json.loads(standard)["generationConfig"]
    else:
        assert body["messages"][0]["content"][0]["image_url"]["detail"] == "high"
        assert "detail" not in json.loads(standard)["messages"][0]["content"][0]["image_url"]


@pytest.mark.parametrize("provider", ["gemini", "emergent"])
def test_both_adapters_deliver_all_images_as_explicit_ordered_parts(tmp_path, provider):
    item = image_item(tmp_path)
    _url, body, audit = t.build_request(provider, "gemini-2.5-pro", [{"type": "text", "text": "source time 125ms"}, item])
    wire = json.loads(body)
    assert audit["explicit_image_count"] == 1
    assert "videoMetadata" not in body.decode() and "video_url" not in body.decode()
    parts = wire["contents"][0]["parts"] if provider == "gemini" else wire["messages"][0]["content"]
    assert len(parts) == 2


def test_modified_prepared_image_stops_before_network(tmp_path):
    item = image_item(tmp_path); Path(item["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="PREPARED_IMAGE_CHANGED"):
        t.build_request("gemini", "gemini-2.5-pro", [item])


def test_oversized_request_is_rejected_without_silently_dropping_frames(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "MAX_REQUEST_BYTES", 10)
    with pytest.raises(ValueError, match="REQUEST_IMAGE_BUDGET_EXCEEDED"):
        t.build_request("gemini", "gemini-2.5-pro", [image_item(tmp_path)])


def test_truncated_model_reply_is_not_accepted():
    with pytest.raises(ValueError, match="INCOMPLETE_MODEL_RESPONSE"):
        t.extract_reply("gemini", {"candidates": [{"finishReason": "MAX_TOKENS"}]})


def stall_worker(connection, job, provider, model, timeout_s):
    time.sleep(30)


def denied_worker(connection, job, provider, model, timeout_s):
    connection.send({"packet_id": job["packet_id"], "status": "ERROR", "error": "MODEL_ACCESS_DENIED"})
    connection.close()


def test_access_denied_stops_queued_work_without_alternate_route():
    result = t.run_jobs([{"packet_id": "first"}, {"packet_id": "second"}], "gemini", "gemini-2.5-pro",
                       deadline=time.monotonic() + 5, workers=1, worker=denied_worker)
    assert result[0]["error"] == "MODEL_ACCESS_DENIED"
    assert result[1]["status"] == "NOT_SENT"


def quota_worker(connection, job, provider, model, timeout_s):
    connection.send({"packet_id": job["packet_id"], "status": "ERROR", "http_status": 429,
                     "error": "MODEL_QUOTA_OR_RATE_LIMIT", "limit_kind": "QUOTA_EXHAUSTED"})
    connection.close()


def test_quota_failure_stops_every_queued_request_without_retry():
    result = t.run_jobs([{"packet_id": str(i)} for i in range(4)], "emergent", "gpt-6-astra",
                       deadline=time.monotonic()+5, workers=1, worker=quota_worker)
    assert result[0]["http_status"] == 429
    assert all(r["status"] == "NOT_SENT" for r in result[1:])
    assert all(r["error"] == "MODEL_ACCESS_STOPPED" for r in result[1:])


def test_transport_persists_result_before_returning_the_batch():
    saved = []
    result = t.run_jobs([{"packet_id": "first"}], "emergent", "gpt-6-astra",
                        deadline=time.monotonic()+5, workers=1, worker=quota_worker,
                        on_result=lambda row: saved.append(deepcopy(row)))
    assert saved == result and saved[0]["http_status"] == 429


@pytest.mark.parametrize("change,expected_sent", [
    (None, ["second"]), ("request", ["first", "second"]),
    ("response", ["first", "second"]), ("model", ["first", "second"]),
    ("status", ["first", "second"]), ("invalid_json", ["first", "second"]),
])
def test_retry_only_sends_unfinished_or_changed_exact_requests(tmp_path, monkeypatch, change, expected_sent):
    from scripts import run_sequence_pilot as runner
    from sequence_run_checkpoint import code_fingerprint
    manifest, packet, data = fixture()
    source = tmp_path / "source.bin"; source.write_bytes(b"synthetic source")
    manifest.update(source_video=str(source), source_video_sha256=p.digest(source), original_taps_sha256="selections",
                    references=[{"reference_id": "r1"}])
    manifest["packets"].append({**packet, "packet_id": "second"})
    path = tmp_path / "manifest.json"; p.write_json(path, manifest)
    items = lambda m, j: [{"type": "text", "text": j["packet_id"]}]
    monkeypatch.setattr(p, "packet_items", items)
    monkeypatch.setattr(runner, "original_spatial_items", lambda *a: ([], []))
    monkeypatch.setattr(p, "plan_contact_reviews", lambda *a, **kw: [])
    monkeypatch.setattr(p, "plan_outcome_reviews", lambda *a, **kw: [])
    monkeypatch.setenv("EMERGENT_LLM_KEY", "SYNTHETIC_NO_NETWORK_TEST")
    def receipt(job):
        audit = t.build_request("emergent", "gpt-6-astra", job["items"], reasoning_effort="medium", image_detail="high")[2]
        raw = json.dumps(data)
        return {**audit, "packet_id": job["packet_id"], "provider": "emergent", "requested_model": "gpt-6-astra",
                "origin": "LIVE_MODEL_REQUEST", "status": "COMPLETED", "raw_response": raw,
                "response_sha256": hashlib.sha256(raw.encode()).hexdigest()}
    # Reconstruct exactly what the runner inserts; only the first job finished previously.
    first = receipt({"packet_id": "first", "items": [items(None, packet)[0],
                     {"type": "text", "text": runner.FRESH_IDENTITY_INSTRUCTION}]})
    if change == "request": first["payload_sha256"] = "changed"
    if change == "response": first["raw_response"] += "corrupted"
    if change == "model": first["requested_model"] = "other-model"
    if change == "status": first["status"] = "ERROR"
    if change == "invalid_json":
        first["raw_response"] = "not JSON"
        first["response_sha256"] = hashlib.sha256(b"not JSON").hexdigest()
    retry = {"code_sha256": code_fingerprint(), "source_video_sha256": manifest["source_video_sha256"],
             "original_taps_sha256": "selections", "receipts": [first]}
    retry_path = tmp_path / "retry.json"; p.write_json(retry_path, retry)
    sent = []
    def send(jobs, *a, on_result, **kw):
        sent.extend(j["packet_id"] for j in jobs)
        rows = [receipt(j) for j in jobs]
        for row in rows: on_result(row)
        return rows
    monkeypatch.setattr(t, "run_jobs", send)
    result = run(path, tmp_path / "result", provider="emergent", model="gpt-6-astra", fresh_originals=True,
                 contact_reviews=True, automatic_outcomes=True, reasoning_effort="medium", image_detail="high",
                 retry_receipts=retry_path)
    assert sent == expected_sent
    assert result["status"] == "MODEL_OBSERVATIONS_RETURNED"
    assert result["retry_reused_packet_ids"] == (["first"] if change is None else [])
    assert result["fresh_end_to_end_run"] is (change is not None)
    for name in ("first", "second"):
        assert p.read_json(tmp_path / "result/responses" / (name + ".json"))["status"] == "COMPLETED"


@pytest.mark.parametrize("payload,header,kind", [
    ({"error": {"code": "insufficient_quota", "message": "secret-token-do-not-save"}}, "30", "QUOTA_EXHAUSTED"),
    ({"error": {"type": "rate_limit_error", "message": "secret-token-do-not-save"}}, "1.5", "RATE_LIMITED"),
    ({"error": {"code": "unknown-private-code", "message": "secret-token-do-not-save"}}, "bad-private-header", "UNSPECIFIED"),
    ({"error": {"code": ["rate_limit_error"]}}, "99999", "UNSPECIFIED"),
])
def test_limit_diagnostics_only_keeps_allowlisted_categories(payload, header, kind):
    import io
    import urllib.error
    body = io.BytesIO(json.dumps(payload).encode())
    error = urllib.error.HTTPError("https://synthetic.invalid", 429, "synthetic", {"Retry-After": header,
                                  "Authorization": "secret-token-do-not-save"}, body)
    result = t.limit_diagnostics(error)
    assert result["limit_kind"] == kind
    assert "secret-token" not in json.dumps(result) and "unknown-private-code" not in json.dumps(result)
    if header in {"30", "1.5"}:
        assert result["retry_after_seconds"] == float(header)
    else:
        assert "retry_after_seconds" not in result


def test_oversized_error_body_stays_unknown_without_retaining_it():
    import io
    import urllib.error
    stream = io.BytesIO(b'x'*10000)
    error = urllib.error.HTTPError("https://synthetic.invalid", 429, "synthetic", {}, stream)
    assert t.limit_diagnostics(error) == {"limit_kind": "UNSPECIFIED"}
    assert stream.tell() == 4097


def test_http_date_retry_after_is_respected_and_unusable_header_is_not_ignored():
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime
    import io
    import urllib.error
    until = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=60), usegmt=True)
    error = urllib.error.HTTPError("https://synthetic.invalid", 429, "synthetic",
                                  {"Retry-After": until}, io.BytesIO(b'{}'))
    assert 58 <= t.limit_diagnostics(error)["retry_after_seconds"] <= 60
    for header in ("99999", "unknown-provider-header"):
        error = urllib.error.HTTPError("https://synthetic.invalid", 429, "synthetic",
                                      {"Retry-After": header}, io.BytesIO(b'{}'))
        diagnostic = t.limit_diagnostics(error)
        assert diagnostic == {"limit_kind": "UNSPECIFIED", "retry_after_unusable": True}


def test_wall_deadline_kills_real_worker_process():
    before = {c.pid for c in multiprocessing.active_children()}
    started = time.monotonic()
    result = t.run_jobs([{"packet_id": "timeout"}], "gemini", "gemini-2.5-pro",
                       deadline=started + .4, per_call_s=.3, worker=stall_worker)
    assert time.monotonic() - started < 3
    assert result[0]["error"] == "MODEL_WALL_DEADLINE_EXCEEDED"
    assert {c.pid for c in multiprocessing.active_children()} == before


def crash_worker(connection, job, provider, model, timeout_s):
    import os
    os._exit(7)


def test_crashed_worker_is_not_reported_as_a_timeout():
    before = {c.pid for c in multiprocessing.active_children()}
    result = t.run_jobs([{"packet_id": "crash"}], "emergent", "gpt-6-astra",
                        deadline=time.monotonic()+5, worker=crash_worker)
    assert result[0]["error"] == "MODEL_CHILD_EXITED"
    assert {c.pid for c in multiprocessing.active_children()} == before


def test_socket_timeout_has_its_own_receipt_without_exposing_connection_details(monkeypatch):
    class Connection:
        def send(self, row):
            self.row = row
        def close(self):
            pass
    def timeout(*a, **kw):
        raise TimeoutError("private-provider-details")
    monkeypatch.setenv("EMERGENT_LLM_KEY", "SYNTHETIC_NO_NETWORK_TEST")
    monkeypatch.setattr(t.urllib.request, "urlopen", timeout)
    connection = Connection()
    t._worker(connection, {"packet_id": "timeout", "items": [{"type": "text", "text": "synthetic"}]},
              "emergent", "gpt-6-astra", 1)
    assert connection.row["error"] == "MODEL_CALL_TIMEOUT"
    assert "private-provider-details" not in json.dumps(connection.row)


def rate_limit_worker(connection, job, provider, model, timeout_s):
    marker = Path(job["marker"])
    if job.get("always_limited") or not marker.exists():
        marker.write_text("limited")
        row = {"status": "ERROR", "error": "MODEL_QUOTA_OR_RATE_LIMIT", "http_status": 429,
               "limit_kind": job.get("limit_kind", "RATE_LIMITED"),
               "retry_after_seconds": job.get("delay", 0)}
    else:
        row = {"status": "COMPLETED"}
    connection.send({"packet_id": job["packet_id"], "sent_at": time.monotonic(), **row})
    connection.close()


def sibling_rate_limit_worker(connection, job, provider, model, timeout_s):
    if job["packet_id"] == "sibling":
        time.sleep(1.5)
        connection.send({"packet_id": "sibling", "status": "COMPLETED"})
        connection.close()
    else:
        rate_limit_worker(connection, job, provider, model, timeout_s)


def test_transient_429_does_not_kill_a_running_sibling(tmp_path):
    result = t.run_jobs([{"packet_id": "limited", "marker": str(tmp_path / "limited")},
                         {"packet_id": "sibling"}], "emergent", "gpt-6-astra",
                        deadline=time.monotonic()+10, per_call_s=3, worker=sibling_rate_limit_worker)
    assert [r["status"] for r in result] == ["COMPLETED", "COMPLETED"]
    assert result[0]["rate_limit_retry_count"] == 1


@pytest.mark.parametrize("kind", ["RATE_LIMITED", "UNSPECIFIED"])
def test_transient_429_retries_once_and_pauses_queued_requests(tmp_path, kind):
    saved = []
    jobs = [{"packet_id": name, "marker": str(tmp_path / name), "limit_kind": kind}
            for name in ("first", "second")]
    # The queued request will succeed immediately, but may not jump the cooldown.
    (tmp_path / "second").write_text("ready")
    before = {c.pid for c in multiprocessing.active_children()}
    result = t.run_jobs(jobs, "emergent", "gpt-6-astra", deadline=time.monotonic()+10,
                        per_call_s=2, workers=1, worker=rate_limit_worker,
                        on_result=lambda row: saved.append(deepcopy(row)))
    assert [r["status"] for r in result] == ["COMPLETED", "COMPLETED"]
    assert result[0]["rate_limit_retry_count"] == 1
    assert result[0]["prior_rate_limit"]["http_status"] == 429
    assert saved[0]["rate_limit_retry_scheduled"] is True
    assert result[0]["sent_at"] - saved[0]["sent_at"] >= 1
    assert result[1]["sent_at"] >= result[0]["sent_at"]
    assert {c.pid for c in multiprocessing.active_children()} == before


def test_repeated_429_stops_after_one_retry_and_keeps_both_failures(tmp_path):
    result = t.run_jobs([{"packet_id": "limited", "marker": str(tmp_path / "limited"),
                          "always_limited": True},
                         {"packet_id": "queued", "marker": str(tmp_path / "queued")}],
                        "emergent", "gpt-6-astra", deadline=time.monotonic()+10,
                        per_call_s=2, workers=1, worker=rate_limit_worker)
    assert result[0]["error"] == "MODEL_QUOTA_OR_RATE_LIMIT"
    assert result[0]["rate_limit_retry_count"] == 1
    assert result[0]["prior_rate_limit"]["error"] == "MODEL_QUOTA_OR_RATE_LIMIT"
    assert result[1]["status"] == "NOT_SENT"
    assert not (tmp_path / "queued").exists()


@pytest.mark.parametrize("delay,budget", [(31, 10), (86400, 10), (2, 2)])
def test_429_never_retries_earlier_than_retry_after_or_beyond_budget(tmp_path, delay, budget):
    saved = []
    result = t.run_jobs([{"packet_id": "limited", "marker": str(tmp_path / "limited"), "delay": delay}],
                        "emergent", "gpt-6-astra", deadline=time.monotonic()+budget,
                        per_call_s=2, workers=1, worker=rate_limit_worker, on_result=saved.append)
    assert len(saved) == 1 and result[0]["http_status"] == 429
    assert "rate_limit_retry_count" not in result[0]


@pytest.mark.parametrize("recovers", [False, True])
def test_missing_initial_is_retried_before_optional_work_without_repeating_completed_packets(
        tmp_path, monkeypatch, recovers):
    from scripts import run_sequence_pilot as runner
    manifest, packet, data = fixture()
    source = tmp_path / "source.bin"; source.write_bytes(b"synthetic")
    manifest.update(source_video=str(source), source_video_sha256=p.digest(source),
                    references=[{"reference_id": "r1"}])
    manifest["packets"].append({**packet, "packet_id": "second"})
    path = tmp_path / "manifest.json"; p.write_json(path, manifest)
    monkeypatch.setenv("EMERGENT_LLM_KEY", "SYNTHETIC_NO_NETWORK_TEST")
    monkeypatch.setattr(p, "packet_items", lambda m, j: [{"type": "text", "text": j["packet_id"]}])
    monkeypatch.setattr(runner, "original_spatial_items", lambda *a: ([], []))
    calls, planners = [], []
    def send(jobs, *a, on_result, deadline, per_call_s):
        calls.append(([j["packet_id"] for j in jobs], deadline, per_call_s))
        rows = []
        for job in jobs:
            row = {"packet_id": job["packet_id"], "status": "COMPLETED",
                   "raw_response": json.dumps(data), "origin": "SYNTHETIC_TEST_ONLY",
                   "payload_sha256": "request", "response_sha256": "response"}
            if job["packet_id"] == "first" and (len(calls) == 1 or not recovers):
                row.update(status="ERROR", error="MODEL_WALL_DEADLINE_EXCEEDED")
            on_result(row); rows.append(row)
        return rows
    monkeypatch.setattr(t, "run_jobs", send)
    def plan(*a, **kw):
        planners.append(len(calls))
        return []
    monkeypatch.setattr(p, "plan_contact_reviews", plan)
    monkeypatch.setattr(p, "plan_outcome_reviews", plan)
    result = run(path, tmp_path / "run", provider="emergent", model="gpt-6-astra",
                 fresh_originals=True, contact_reviews=True, automatic_outcomes=True,
                 budget_s=600, per_call_s=120)
    assert [c[0] for c in calls] == [["first", "second"], ["first"]]
    assert calls[0][1] == calls[1][1] and calls[1][2] == 180
    assert planners == ([2, 2] if recovers else [])
    assert result["status"] == ("MODEL_OBSERVATIONS_RETURNED" if recovers else "PARTIAL_MODEL_RUN")
    assert len(result["model_jobs"]) == 2
    saved = p.read_json(tmp_path / "run/responses/first.json")
    assert saved["initial_recovery_count"] == 1
    assert saved["prior_initial_error"] == "MODEL_WALL_DEADLINE_EXCEEDED"


def test_no_model_key_does_not_fake_success_or_use_historical_answers(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    manifest, _, _ = fixture(); path = tmp_path / "manifest.json"; p.write_json(path, manifest)
    result = run(path, tmp_path / "run")
    assert result["status"] == "MODEL_KEY_NOT_CONFIGURED"
    assert result["model_jobs"] == [] and result["target_events"] == []


def source_export(tmp_path):
    """Small actual CFR file to exercise decoder PTS, crops and checksums."""
    import cv2
    import numpy as np
    root = tmp_path / "export"; (root / "video").mkdir(parents=True)
    video = root / "video" / "source.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 20., (96, 160))
    assert writer.isOpened()
    for i in range(16):
        frame = np.zeros((160, 96, 3), dtype=np.uint8)
        frame[:, :, 1] = 90
        frame[50:100, 20+i:40+i] = 240
        writer.write(frame)
    writer.release()
    tap = {"t": .15, "box": {"x": .2, "y": .3, "w": .3, "h": .4},
           "target_point": {"x": .3, "y": .4}, "player_behind": True,
           "exclude_points": [{"x": .45, "y": .5}],
           "visible_mask": {"width": 96, "height": 192, "runs": [0, 96*192]}}
    p.write_json(root / "anchors.json", {"raw_marker_anchors": json.dumps([tap])})
    (root / "SHA256SUMS").write_text("\n".join(f"{p.digest(file)}  {file.relative_to(root).as_posix()}"
        for file in (video, root / "anchors.json")) + "\n")
    return root


def test_actual_decoder_preparation_retains_taps_masks_and_source_clock(tmp_path):
    root = source_export(tmp_path)
    manifest = p.prepare(root, tmp_path / "prepared", fps=8, max_edge=768)
    assert manifest["input_coverage"]["decoded_source_frames"] == 16
    assert manifest["input_coverage"]["complete"]
    assert manifest["input_coverage"]["max_sample_gap_ms"] <= 150
    assert manifest["model_calls"] == manifest["detector_forwards"] == 0
    ref = manifest["references"][0]
    assert ref["media_ms"] == 150 and ref["target_point"] == {"x": .3, "y": .4}
    assert ref["masked_view"] and ref["selection_hints"]["player_behind"]
    assert ref["selection_hints"]["exclude_points"] == [{"x": .45, "y": .5}]


def test_initial_receipt_resume_never_repeats_paid_calls_and_rejects_changed_inputs(tmp_path, monkeypatch):
    manifest = p.prepare(source_export(tmp_path), tmp_path / "prepared")
    specs = [{k: packet[k] for k in ("packet_id", "start_ms", "end_ms", "frame_ids", "reference_ids")} for packet in manifest["packets"]]
    raw = '{"plays":[]}'
    cache = {"source_video_sha256": manifest["source_video_sha256"], "original_taps_sha256": manifest["original_taps_sha256"],
        "packet_fingerprint": hashlib.sha256(json.dumps(specs, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "origin_run": "SYNTHETIC_TEST_ONLY", "previous_run_analysis_seconds": 1,
        "receipts": [{"packet_id": manifest["packets"][0]["packet_id"], "origin": "LIVE_MODEL_REQUEST", "status": "COMPLETED",
            "requested_model": "gemini-2.5-pro", "raw_response": raw, "response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "payload_sha256": "SYNTHETIC_TEST_ONLY"}]}
    path = tmp_path / "cache.json"; p.write_json(path, cache)
    monkeypatch.setenv("GEMINI_API_KEY", "SYNTHETIC_TEST_ONLY")
    def no_calls(*args, **kwargs):
        raise AssertionError("A completed initial request must not be replayed")
    monkeypatch.setattr(t, "run_jobs", no_calls)
    result = run(tmp_path / "prepared" / "manifest.json", tmp_path / "resumed", max_followups=0, resume_initial_receipts=path)
    assert result["status"] == "MODEL_OBSERVATIONS_RETURNED" and result["model_jobs_completed"] == 0
    assert result["reused_initial_model_jobs"] == 1
    cache["packet_fingerprint"] = "CHANGED"; p.write_json(path, cache)
    rejected = run(tmp_path / "prepared" / "manifest.json", tmp_path / "rejected", max_followups=0, resume_initial_receipts=path)
    assert rejected["error_code"] == "INITIAL_RECEIPT_INPUT_MISMATCH"


def test_changed_source_checksum_stops_before_sampling(tmp_path):
    root = source_export(tmp_path)
    (root / "anchors.json").write_text("{}")
    with pytest.raises(ValueError, match="SOURCE_INPUT_CHECKSUM_MISMATCH"):
        p.prepare(root, tmp_path / "prepared")


def test_oversized_packet_does_not_prevent_other_packet_from_running(tmp_path, monkeypatch):
    root = source_export(tmp_path)
    manifest = p.prepare(root, tmp_path / "prepared")
    second = deepcopy(manifest["packets"][0]); second["packet_id"] = "second"
    manifest["packets"].append(second)
    p.write_json(tmp_path / "prepared" / "manifest.json", manifest)
    original, attempts, executed = t.build_request, [], []
    def preflight(*args, **kwargs):
        attempts.append(True)
        if len(attempts) == 1:
            raise ValueError("REQUEST_IMAGE_BUDGET_EXCEEDED")
        return original(*args, **kwargs)
    def jobs(rows, *args, **kwargs):
        executed.extend(r["packet_id"] for r in rows)
        return [{"packet_id": r["packet_id"], "status": "COMPLETED", "raw_response": '{"plays":[]}',
                 "payload_sha256": "synthetic", "response_sha256": "synthetic",
                 "origin": "SYNTHETIC_TEST_ONLY"} for r in rows]
    monkeypatch.setenv("GEMINI_API_KEY", "SYNTHETIC_TEST_ONLY")
    monkeypatch.setattr(t, "build_request", preflight)
    monkeypatch.setattr(t, "run_jobs", jobs)
    result = run(tmp_path / "prepared" / "manifest.json", tmp_path / "result", max_followups=0)
    assert executed == ["second"]
    assert result["status"] == "PARTIAL_MODEL_RUN"
    assert result["model_jobs_completed"] == 1
    assert result["model_jobs"][0]["error"] == "REQUEST_IMAGE_BUDGET_EXCEEDED"


def test_targeted_detail_adds_real_frames_without_rebuilding_identity(tmp_path):
    root = source_export(tmp_path)
    manifest = p.prepare(root, tmp_path / "prepared", fps=4)
    question = {"reason": "OUTCOME", "start_ms": 0, "end_ms": 750, "focus_ms": 350, "source_packet_id": "sequence_001"}
    jobs = p.followup_plan(manifest, {"questions": [question]})
    enriched, jobs = p.prepare_followups(manifest, jobs, tmp_path / "detail")
    assert len(enriched["frames"]) > len(manifest["frames"])
    assert all(f["media_ms"] % 50 == 0 for f in enriched["frames"])
    assert enriched["references"] == manifest["references"]
    assert len(jobs) == 1 and jobs[0]["round"] == 1


def test_contact_review_keeps_overview_and_uses_actual_native_source_clock(tmp_path):
    root = source_export(tmp_path)
    manifest = p.prepare(root, tmp_path / "prepared", fps=8)
    job = {"packet_id": "review", "phase": "FOLLOWUP", "start_ms": 0, "end_ms": 750,
           "reference_ids": ["r1"], "question": {"focus_ms": 350}}
    enriched, jobs = p.prepare_contact_reviews(manifest, [job], tmp_path / "review")
    assert {f["frame_id"] for f in manifest["frames"]} <= {f["frame_id"] for f in enriched["frames"]}
    assert jobs[0]["native_crop_count"] == 16
    assert all(f["media_ms"] % 50 == 0 for f in enriched["frames"])
    assert any(f.get("zoom_view") for f in enriched["frames"])
    assert any(f.get("source_crop_box") for f in enriched["frames"])


def test_restored_native_detail_changes_only_crop_delivery_not_timestamps_or_overview(tmp_path):
    manifest = p.prepare(source_export(tmp_path), tmp_path / "prepared", fps=8)
    original = {"packet_id": "review", "phase": "FOLLOWUP", "start_ms": 0, "end_ms": 750,
                "reference_ids": ["r1"], "question": {"focus_ms": 350}}
    low, low_jobs = p.prepare_contact_reviews(manifest, [deepcopy(original)], tmp_path / "low")
    restored, restored_jobs = p.prepare_contact_reviews(manifest, [deepcopy(original)], tmp_path / "restored",
                                                       native_detail_policy="local_span_q80")
    assert low_jobs[0]["frame_ids"] == restored_jobs[0]["frame_ids"]
    assert low_jobs[0]["question"] == restored_jobs[0]["question"]
    assert restored_jobs[0]["source_crop_box"] == [0, 0, 96, 160]
    assert restored_jobs[0]["native_crop_count"] == low_jobs[0]["native_crop_count"]
    assert restored["contact_review_delivery"]["native_crop_jpeg_quality"] == 80
    assert restored["references"] == low["references"] == manifest["references"]
    initial = {f["frame_id"] for f in manifest["frames"]}
    assert [f["sha256"] for f in low["frames"] if f["frame_id"] in initial] == [
        f["sha256"] for f in restored["frames"] if f["frame_id"] in initial]


def test_half_player_review_crop_preserves_instants_and_uses_original_geometry(tmp_path):
    manifest=p.prepare(source_export(tmp_path),tmp_path/"prepared",fps=8)
    job={"packet_id":"review","phase":"FOLLOWUP","start_ms":0,"end_ms":750,
         "reference_ids":["r1"],"question":{"focus_ms":350}}
    before=deepcopy(manifest)
    enriched,jobs=p.prepare_contact_reviews(manifest,[job],tmp_path/"review",native_detail_policy="local_half_q50")
    assert manifest == before
    assert jobs[0]["native_crop_count"] == 16
    assert {f["frame_id"] for f in manifest["frames"]} <= set(jobs[0]["frame_ids"])
    assert jobs[0]["source_crop_box"][::2] == [0,96]
    assert enriched["contact_review_delivery"]["native_crop_jpeg_quality"] == 50
    assert enriched["contact_review_delivery"]["source_instants_removed"] == 0


def test_followup_spatial_reference_without_core_fields_uses_actual_packet_bounds(tmp_path):
    from scripts.run_sequence_pilot import original_spatial_items
    manifest=p.prepare(source_export(tmp_path),tmp_path/"prepared",fps=8)
    packet={"packet_id":"review","start_ms":0,"end_ms":750}
    items,audit=original_spatial_items(manifest,packet,tmp_path/"spatial")
    assert items and audit
    assert all(0 <= a["source_ms"] <= 750 for a in audit)


def test_identity_context_citations_do_not_replace_in_action_evidence_or_shift_contact():
    manifest,packet,data=fixture()
    action=data["plays"][0]["actions"][0]
    action["actor_evidence_frames"]=["s000000000","s000000500","s000001000"]
    result=p.reconcile([p.resolve_response(data,manifest,packet,{})])
    event=result["target_events"][0]
    assert event["contact_ms"] == 1000 and event["actor_context_frames"] == ["s000000000"]
    assert event["actor_evidence_frames"] == ["s000000500","s000001000"]
    action["actor_evidence_frames"]=["s000000000"]
    assert p.resolve_response(data,manifest,packet,{})["events"] == []
    action["actor_evidence_frames"]=["s000000500","s000006000"]
    assert p.resolve_response(data,manifest,packet,{})["events"] == []


def test_actual_fresh_initial_replay_preserves_saved_shot_and_plans_full_control_handoff_review():
    saved=p.read_json(Path(__file__).resolve().parents[2]/"docs/examples/fresh-whole-source-initial-receipts.json")
    manifest=saved["replay_manifest"];packets={v["packet_id"]:v for v in manifest["packets"]}
    results=[p.resolve_response(p.parse_response(r["raw_response"]),manifest,packets[r["packet_id"]],
             {k:r[k] for k in ("packet_id","payload_sha256","response_sha256","origin")}) for r in saved["receipts"]]
    merged=p.reconcile(results)
    shots=[e for e in merged["target_events"] if e["event_type"] == "SHOT" and e["outcome"] == "SAVED"]
    assert len(shots) == 1 and shots[0]["actor_context_frames"] == ["s000022016"]
    jobs=p.plan_contact_reviews(manifest,merged,limit=6,terminal_only=True)
    assert {j["replaces_initial_packet_id"] for j in jobs} == {"sequence_003","sequence_004","sequence_007"}
    middle=next(j for j in jobs if j["replaces_initial_packet_id"] == "sequence_007")
    control=next(e for e in merged["events"] if e["source_action_keys"] == [middle["question"]["source_action_key"]])
    assert middle["detail_start_ms"] <= control["start_ms"] < control["end_ms"] <= middle["detail_end_ms"]
    goal=next(j for j in jobs if j["replaces_initial_packet_id"] == "sequence_004")
    assert (goal["detail_start_ms"],goal["detail_end_ms"]) == (31015,32515)
    assert not any(j["replaces_initial_packet_id"] in {"sequence_006","sequence_008"} for j in jobs)


def test_fresh_resume_reproduces_request_hash_and_never_repeats_initial_calls(tmp_path,monkeypatch):
    from scripts.run_sequence_pilot import original_spatial_items,FRESH_IDENTITY_INSTRUCTION
    original=p.prepare(source_export(tmp_path),tmp_path/"prepared",fps=8)
    manifest=fresh_original_manifest(original);packet=manifest["packets"][0]
    items=p.packet_items(manifest,packet);items.insert(1,{"type":"text","text":FRESH_IDENTITY_INSTRUCTION})
    spatial,_=original_spatial_items(manifest,packet,tmp_path/"spatial")
    prefix=len(p.packet_items(manifest,{**packet,"frame_ids":[]}))+1;items[prefix:prefix]=spatial
    _,_,audit=t.build_request("emergent","gpt-6-astra",items,reasoning_effort="medium",image_detail="high")
    raw='{"plays":[]}'
    receipt={"packet_id":packet["packet_id"],"origin":"LIVE_MODEL_REQUEST","status":"COMPLETED",
             "requested_model":"gpt-6-astra","raw_response":raw,"response_sha256":hashlib.sha256(raw.encode()).hexdigest(),
             "payload_sha256":audit["payload_sha256"],"fixture_origin":"SYNTHETIC_TEST_ONLY"}
    specs=[{k:v[k] for k in ("packet_id","start_ms","end_ms","frame_ids","reference_ids")} for v in manifest["packets"]]
    saved={"identity_mode":"FRESH_ORIGINAL_SELECTIONS","source_video_sha256":manifest["source_video_sha256"],
           "original_taps_sha256":manifest["original_taps_sha256"],"origin_run":1,"previous_run_analysis_seconds":1,
           "packet_fingerprint":hashlib.sha256(json.dumps(specs,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
           "receipts":[receipt]}
    path=tmp_path/"resume.json";p.write_json(path,saved)
    def no_calls(*args,**kwargs): raise AssertionError("INITIAL_MODEL_CALL_REPEATED")
    monkeypatch.setattr(t,"run_jobs",no_calls);monkeypatch.setenv("EMERGENT_LLM_KEY","SYNTHETIC_NO_NETWORK_TEST")
    options=dict(provider="emergent",model="gpt-6-astra",reasoning_effort="medium",image_detail="high",
                 fresh_originals=True,resume_fresh_initial=path,max_followups=0)
    result=run(tmp_path/"prepared/manifest.json",tmp_path/"result",**options)
    assert result["status"] == "MODEL_OBSERVATIONS_RETURNED" and result["reused_initial_model_jobs"] == 1
    assert result["initial_requests_sent_in_this_run"] == 0 and result["fresh_end_to_end_run"] is False
    receipt["payload_sha256"]="0"*64;p.write_json(path,saved)
    result=run(tmp_path/"prepared/manifest.json",tmp_path/"bad-result",**options)
    assert result["status"] == "EXPERIMENT_STOPPED" and result["error_code"] == "INITIAL_RECEIPT_INPUT_MISMATCH"


def test_cold_terminal_planner_keeps_actor_review_and_continuous_keeper_outcome_together():
    saved=p.read_json(Path(__file__).resolve().parents[2]/"docs/examples/fresh-whole-source-initial-receipts.json")
    manifest=saved["replay_manifest"];packets={v["packet_id"]:v for v in manifest["packets"]}
    observed=[p.resolve_response(p.parse_response(r["raw_response"]),manifest,packets[r["packet_id"]],
                                {"origin":"RETAINED_ACTUAL_REPLY_REPLAY"}) for r in saved["receipts"]]
    merged=p.reconcile(observed)
    jobs=p.plan_contact_reviews(manifest,merged,terminal_only=True,complete_terminal_context=True)
    assert {j["replaces_initial_packet_id"] for j in jobs} == {"sequence_003","sequence_004","sequence_007"}
    review=next(j for j in jobs if j["replaces_initial_packet_id"] == "sequence_003")
    shot=next(e for e in merged["events"] if e["selected_player"] is True and e["kind"] == "SHOT"
              and e["outcome"] == "SAVED")
    assert review["detail_start_ms"] < shot["contact_interval_ms"][0]
    assert review["detail_end_ms"] >= shot["contact_interval_ms"][1]+1500
    # Explicit uncertainty still demands a review even when the outcome said SAVED.
    shot.update(proof_eligible=False,model_requested_clarification=True)
    merged["questions"].append({"reason":"CONTACT","source_action_key":shot["source_action_keys"][0],
        "source_packet_id":shot["source_packet_ids"][0],"explicit_model_question":True,"target_related":True})
    jobs=p.plan_contact_reviews(manifest,merged,terminal_only=True,complete_terminal_context=True)
    review=next(j for j in jobs if j["replaces_initial_packet_id"] == "sequence_003")
    assert review["detail_start_ms"] <= shot["contact_interval_ms"][0]-100
    assert review["detail_end_ms"] >= shot["contact_interval_ms"][1]+1500


@pytest.mark.parametrize("max_followups,failure_call,expected_calls",[(2,0,3),(2,3,3),(1,0,2),(2,2,2),(2,1,1)])
def test_cold_automatic_outcome_round_shares_budget_and_preserves_uncertainty_on_failure(
        tmp_path,monkeypatch,max_followups,failure_call,expected_calls):
    """Synthetic transport/control-flow test, never a perception trial."""
    from scripts import run_sequence_pilot as runner
    manifest,packet,data=fixture()
    source=tmp_path/"source.bin";source.write_bytes(b"synthetic source checksum")
    manifest.update(source_video=str(source),source_video_sha256=p.digest(source),references=[{"reference_id":"r1"}])
    action=data["plays"][0]["actions"][0]
    action.update(kind="SHOT",contact_frame=None,contact_before_frame="s000000750",contact_after_frame="s000001000",
        contact_actor_unique=True,contact_evidence=[{"frame":"s000000750","fact":"before"},
                                                  {"frame":"s000001000","fact":"departure"}],
        end_frame="s000002500",outcome="UNKNOWN",receiver=None,receiver_frame=None,
        receiver_is_teammate=None,finisher="passer",shot_frame=None)
    data["plays"][0]["questions"]=[{"reason":"OUTCOME","action_id":"a1"}]
    path=tmp_path/"manifest.json";p.write_json(path,manifest)
    monkeypatch.setenv("EMERGENT_LLM_KEY","SYNTHETIC_NO_NETWORK_TEST")
    monkeypatch.setattr(p,"packet_items",lambda m,j:[{"type":"text","text":json.dumps({
        "packet_id":j["packet_id"],"question":j.get("question")})}])
    monkeypatch.setattr(runner,"original_spatial_items",lambda *a:([],[]))
    def prepare(m,jobs,*args,**kwargs):
        return m,[{**j,"frame_ids":packet["frame_ids"]} for j in jobs]
    monkeypatch.setattr(p,"prepare_contact_reviews",prepare)
    calls=[]
    def transport(jobs,provider,model,*,deadline,per_call_s,on_result):
        calls.append((deepcopy(jobs),deadline))
        assert len(jobs)==1 and "SAVED" not in json.dumps(jobs)
        j=jobs[0]
        receipt={"packet_id":j["packet_id"],"origin":"SYNTHETIC_TEST_ONLY","status":"COMPLETED",
                 "payload_sha256":"synthetic-request","response_sha256":"synthetic-response"}
        if len(calls)==failure_call:
            return [{**receipt,"status":"ERROR","error":"MODEL_QUOTA_OR_RATE_LIMIT"}]
        reply=deepcopy(data)
        if len(calls)==3:
            reply["plays"][0]["actions"][0]["outcome"]="SAVED"
            reply["plays"][0]["questions"]=[]
        return [{**receipt,"raw_response":json.dumps(reply)}]
    monkeypatch.setattr(t,"run_jobs",transport)
    result=run(path,tmp_path/"result",provider="emergent",model="gpt-6-astra",fresh_originals=True,
               contact_reviews=True,automatic_outcomes=True,max_followups=max_followups)
    assert len(calls)==expected_calls and len({deadline for _,deadline in calls})==1
    assert result["historical_action_results_used"] is False and result["fresh_end_to_end_run"] is True
    if expected_calls==3 and not failure_call:
        assert result["counts"]["SHOT"]==1 and result["questions"]==[]
        assert result["superseded_review_packet_ids"]==["contact_review_001"]
    else:
        assert result["counts"].get("SHOT",0)==0
        if failure_call != 1:
            assert result["questions"]
    assert result["status"] == ("PARTIAL_MODEL_RUN" if failure_call else "MODEL_OBSERVATIONS_RETURNED")
    if failure_call:
        assert result["error_code"] == "MODEL_QUOTA_OR_RATE_LIMIT"


def test_automatic_outcomes_rejects_resume_or_nonfresh_mode_before_any_call(tmp_path):
    manifest,_,_=fixture();path=tmp_path/"manifest.json";p.write_json(path,manifest)
    for options in ({}, {"fresh_originals":True},
                    {"fresh_originals":True,"contact_reviews":True,"resume_fresh_initial":"old.json"}):
        with pytest.raises(ValueError,match="AUTOMATIC_OUTCOMES_REQUIRE_COLD_FRESH_CONTACT_RUN"):
            run(path,tmp_path/"result",automatic_outcomes=True,**options)


def test_actor_continuity_band_keeps_all_people_and_does_not_select_an_identity():
    from scripts.probe_actor_continuity import viewing_band
    box = viewing_band([[(.1, .4, .1, .1, .8)], [(.7, .45, .08, .2, .7)]], 1000, 2000)
    assert box == [0, 700, 1000, 1500]
    assert viewing_band([[(.1, 0, .1, .2, .8), (.7, .9, .1, .2, .8)]], 1000, 2000) == [0, 0, 1000, 2000]


def test_actor_continuity_band_rejects_missing_or_invalid_geometry():
    from scripts.probe_actor_continuity import viewing_band
    for boxes in ([], [[(.1, float('nan'), .1, .2, .8)]], [[(.1, .5, .1, -.2, .8)]]):
        with pytest.raises(ValueError):
            viewing_band(boxes, 1000, 2000)


def test_actor_review_requires_integrity_checked_explicit_unresolved_actor():
    from scripts.probe_actor_continuity import unresolved_gap
    raw = json.dumps({'outcome': {'last_touch_player': 'Unknown', 'uncertainty': 'Two players overlap'}})
    saved = {'question': {'packet_id':'p','start_ms':100,'end_ms':900,
                         'detail_start_ms':200,'detail_end_ms':800},
             'receipt': {'status':'COMPLETED','origin':'LIVE_MODEL_REQUEST','packet_id':'p',
                         'raw_response':raw,'response_sha256':hashlib.sha256(raw.encode()).hexdigest()}}
    assert unresolved_gap(saved) == saved['question']
    for changed in ({'response_sha256':'bad'}, {'status':'ERROR'}, {'packet_id':'different'}):
        with pytest.raises(ValueError):
            unresolved_gap({**saved, 'receipt':{**saved['receipt'], **changed}})
    settled = json.dumps({'outcome':{'last_touch_player':'p1','uncertainty':''}})
    with pytest.raises(ValueError, match='NO_UNRESOLVED_FINISHING_ACTOR'):
        unresolved_gap({**saved,'receipt':{**saved['receipt'],'raw_response':settled,
            'response_sha256':hashlib.sha256(settled.encode()).hexdigest()}})


def test_native_play_views_keep_normal_duration_and_source_geometry(tmp_path):
    from scripts.probe_native_play import prepare_videos
    manifest = p.prepare(source_export(tmp_path), tmp_path / "prepared", fps=8, scene_packets=True)
    packet, local, views, box = prepare_videos(manifest, tmp_path / "native")
    assert (packet["core_start_ms"], packet["core_end_ms"]) == (0, 750)
    assert local == manifest["references"]
    assert box == [0, 0, 96, 160]
    assert len(views) == 2
    for view in views:
        meta = view["metadata"]
        assert .65 <= float(meta["format"]["duration"]) <= .90
        assert view["sha256"] == p.digest(view["path"])
    detail = views[1]["metadata"]["streams"][0]
    assert (detail["width"], detail["height"], detail["r_frame_rate"]) == (96, 160, "24/1")


def test_video_comparison_reuses_exact_encoded_bytes_without_encoder_work(tmp_path, monkeypatch):
    import subprocess
    from scripts.probe_native_play import prepare_videos
    manifest = p.prepare(source_export(tmp_path), tmp_path / "prepared", scene_packets=True)
    _, _, initial, _ = prepare_videos(manifest, tmp_path / "baseline")
    original = subprocess.run
    def no_encode(command, **kwargs):
        assert command[0] != "ffmpeg", "A comparison must not re-encode its baseline videos"
        return original(command, **kwargs)
    monkeypatch.setattr(subprocess, "run", no_encode)
    _, _, reused, _ = prepare_videos(manifest, tmp_path / "reused", replay_dir=tmp_path / "baseline")
    assert [v["sha256"] for v in initial] == [v["sha256"] for v in reused]


def test_full_source_play_without_local_tap_does_not_invent_a_local_marker(tmp_path):
    from scripts.probe_native_play import select_play, spatial_reference_items
    manifest = p.prepare(source_export(tmp_path), tmp_path / "prepared", scene_packets=True)
    packet = {**manifest["packets"][0], "packet_id": "untapped", "core_start_ms": 500}
    manifest["packets"].append(packet)
    selected, local, top, bottom = select_play(manifest, "untapped")
    assert selected == packet and local == [] and 0 <= top < bottom <= 1
    assert spatial_reference_items(manifest, packet, local, tmp_path / "spatial") == ([], [])


def test_native_gap_plan_uses_observed_scoring_uncertainty_not_contested_tackles():
    from scripts.probe_native_gaps import plan
    manifest = {"references": []}
    def observed(pid, kind, action, uncertainty, start):
        return {"selected_packet":pid,"source_start_ms":start,"source_end_ms":start+4000,
            "raw_native_observations":{"players":[{"id":"p","selected":True}],
                "ball_sequence":[{"actor":"p","action":action,"uncertainty":uncertainty,"clip_s":2}],
                "outcome":{"kind":kind}}}
    source = {"plays":[observed("tackle","tackle","tackled","contested",0),
        observed("miss","miss","shot","",10000), observed("link","goal","pass","deflection or control",20000),
        observed("identity","goal","shot","",30000)]}
    jobs = plan(manifest, source)
    assert [j["packet_id"] for j in jobs] == ["miss","link","identity"]
    assert jobs[0]["focus_ms"] == 12700
    assert jobs[1]["focus_ms"] == 22000
    assert jobs[2]["reason"] == "FINAL_TOUCH_ACTOR_WITHOUT_LOCAL_IDENTITY_MARK"


def test_native_play_cli_reports_failed_model_access_as_failed_process(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
    manifest = p.prepare(source_export(tmp_path), tmp_path / "prepared", scene_packets=True)
    raw = json.dumps({"identity_clear": True, "appearance": "Synthetic green video fixture",
                      "canonical_reference_ids": ["r1"]})
    p.write_json(tmp_path / "profile.json", {"source_video_sha256": manifest["source_video_sha256"],
        "receipt": {"status": "COMPLETED", "origin": "LIVE_MODEL_REQUEST",
                    "raw_response": raw, "response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                    "images": [{"sha256": r["sha256"]} for r in manifest["references"]]}})
    cli = Path(__file__).resolve().parents[1] / "scripts/probe_native_play.py"
    result = subprocess.run([sys.executable, str(cli), "--prepared", str(tmp_path / "prepared/manifest.json"),
        "--output", str(tmp_path / "result"), "--resume-profile", str(tmp_path / "profile.json")],
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 3, result.stderr
    assert p.read_json(tmp_path / "result/result.json")["model_status"] == "ERROR"
    assert p.read_json(tmp_path / "result/responses/native_short_play.json")["error"] == "MODEL_KEY_NOT_CONFIGURED"


def test_spatial_reference_uses_original_full_frame_coordinates_and_preserves_source(tmp_path):
    import cv2
    from scripts.probe_native_play import spatial_reference_items
    manifest = p.prepare(source_export(tmp_path), tmp_path / "prepared", scene_packets=True)
    before = p.digest(manifest["source_video"])
    packet = manifest["packets"][0]
    items, audit = spatial_reference_items(manifest, packet, manifest["references"], tmp_path / "spatial")
    picture = cv2.imread(items[1]["path"])
    assert picture.shape[:2] == (160, 96)
    b, g, r = map(int, picture[64, 29])
    assert b > 180 and g > 180 and r < 100
    assert audit[0]["original_positive_point"] == {"x": .3, "y": .4}
    assert audit[0]["source_ms"] == 150
    assert audit[0]["approximate_clip_s"] == .15
    assert p.digest(manifest["source_video"]) == before


def test_runner_preserves_initial_observations_if_targeted_preparation_fails(tmp_path, monkeypatch):
    root = source_export(tmp_path)
    manifest = p.prepare(root, tmp_path / "prepared")
    ids = [f["frame_id"] for f in manifest["frames"]]
    raw = {"plays": [{"start_frame": ids[0], "end_frame": ids[-1],
        "people": [{"person_id": "one", "selected": True, "kit_consistent": True,
                    "reference_ids": ["r1"], "evidence_frames": [ids[0]]}],
        "actions": [{"action_id": "shot", "kind": "SHOT", "actor": "one", "start_frame": ids[0],
                     "contact_frame": ids[1], "end_frame": ids[-1], "actor_evidence_frames": [ids[0]], "outcome": "UNKNOWN"}]}]}
    def synthetic_jobs(jobs, *args, **kwargs):
        return [{"packet_id": j["packet_id"], "status": "COMPLETED", "raw_response": json.dumps(raw),
                 "origin": "SYNTHETIC_TEST_ONLY", "payload_sha256": "a"*64, "response_sha256": "b"*64} for j in jobs]
    def fail_detail(*args, **kwargs):
        raise TimeoutError("DETAIL_PREPARATION_TIME_BUDGET_EXHAUSTED")
    monkeypatch.setenv("GEMINI_API_KEY", "SYNTHETIC_TEST_ONLY")
    monkeypatch.setattr(t, "run_jobs", synthetic_jobs)
    monkeypatch.setattr(p, "prepare_followups", fail_detail)
    result = run(tmp_path / "prepared" / "manifest.json", tmp_path / "result")
    assert result["status"] == "EXPERIMENT_STOPPED"
    assert result["error_code"] == "DETAIL_PREPARATION_TIME_BUDGET_EXHAUSTED"
    assert len(result["events"]) == 1 and result["counts"] == {}
    assert result["independent_visual_correctness_verified"] is False
