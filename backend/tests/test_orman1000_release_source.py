"""Orman1000 release-source integrity contract (no video/model/provider calls).

The actual latest uploaded ZIP was inspected offline before these SHA and frame
facts were recorded. This test checks that subsequent PR changes cannot
silently substitute an Orman400 fixture, call incomplete coverage 'ready',
or reactivate unverified cache. It does NOT replace a live Orman1000 replay.
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[2] / "testdata/matchroom-completion"
SOURCE = "fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2"
ARCHIVE = "3b27260511ed965952a497f97d1c6345a0f1b4bef1b89a60912a62e0f6530c0c"
SELECTION = "ca4bc63080b8de6b986c370f809c89ad1050b5d1c883fe7e748da0ab8400d016"
DUEL_ID = "966c91c7243829d6fab0"


def load(filename):
    return json.loads((BASE / filename).read_text())


def test_primary_orman1000_release_evidence_is_byte_verified_and_not_orman400():
    evidence = load("orman1000-release-source.json")
    primary = evidence["primary_evidence_archive"]
    assert evidence["analysis_name"] == "Orman1000"
    assert primary["archive_bytes_directly_verified_in_current_runtime"] is True
    assert primary["archive_sha256"] == ARCHIVE
    assert primary["original_source_video_sha256_from_latest_archive"] == SOURCE
    assert primary["original_selection_digest"] == SELECTION
    assert primary["verified_payload_files"] == 118
    assert primary["checksum_mismatches"] == 0
    assert primary["zip_integrity_test"] == "PASS"
    assert primary["original_human_selections"] == 10
    assert primary["canonical_event_count"] == 21
    assert primary["match_room_card_count"] == 8
    assert primary["canonical_event_coverage_complete"] is False
    assert primary["export_manifest_complete"] is False
    assert evidence["excluded_release_evidence"]["other_video_sha256"] != SOURCE
    assert evidence["production_cache_enabled"] is False
    assert evidence["current_release_acceptance"] != "READY"


def test_orman1000_masked_vs_visible_candidate_frame_coverage_not_conflated():
    evidence = load("orman1000-release-source.json")
    metrics = evidence["actual_latest_zip_source_pts_audit"]
    passed = metrics["00:44"]
    assert passed["frames"] == 136
    assert passed["stored_mask_covered"] == 69
    assert passed["independent_confirmed_ground_supported"] == 91
    assert passed["supported_but_unmasked"] == 22
    assert passed["no_confirmed_ground_support_and_unmasked"] == 45
    assert passed["stored_mask_covered"] + passed["supported_but_unmasked"] + passed["no_confirmed_ground_support_and_unmasked"] == passed["frames"]
    assert passed["last_confirmed_ground_ms"] == 45382
    assert passed["first_absent_ms"] == 45632
    shot = metrics["00:31"]
    assert shot["frames"] == 83
    assert shot["stored_mask_covered"] + shot["supported_but_unmasked"] == 83
    assert shot["independent_confirmed_ground_supported"] == 83
    # Documented support is NOT an identity-tracked mask or authorized interpolation.
    assert "does NOT authorize" in metrics["caveat"]


def test_completed_orman1000_duel_tail_receipt_same_source_and_selection():
    evidence = load("orman1000-release-source.json")
    completion = load("result.json")
    assert completion["status"] == "OBSERVATIONS_RETURNED"
    assert completion["scope"] == "ONE_MISSING_CLIP_EDGE_ONLY"
    record = completion["record"]
    assert record["source_video_sha256"] == SOURCE
    assert record["original_selection_values_sha256"] == SELECTION
    assert record["event_id"] == DUEL_ID
    assert record["window_ms"] == [10125, 12133]
    assert record["receipt"]["status"] == "COMPLETED"
    rows = completion["samples"]
    assert len(rows) == 17
    assert rows[0]["media_ms"] == 10133
    assert rows[-1]["media_ms"] == 12133
    assert evidence["actual_latest_zip_source_pts_audit"]["00:08"]["stored_localization_ends_ms"] == 10000
    assert evidence["actual_latest_zip_source_pts_audit"]["00:08"]["reported_clip_ends_ms"] == 12133


def test_prior_orman1000_cache_timing_is_not_release_or_full_coverage_proof():
    evidence = load("orman1000-release-source.json")
    old = load("prediction-scheduler-verification.json")
    assert old["source_video_sha256"] == SOURCE
    by_clip = {x["clip"]: x for x in old["results"]}
    assert by_clip["00:44"]["frames"] == 136
    assert by_clip["00:44"]["baselineVisible"] == 91
    assert by_clip["00:44"]["cachedVisible"] == 91
    assert old["production_enabled"] is False
    assert old["live_verified"] is False
    assert evidence["previous_source_bound_orman1000_diagnostics"]["stored_diagnostic_is_a_separate_experiment"] is True


def test_third_assist_is_explicit_release_block_not_unverified_score_rewrite():
    evidence = load("orman1000-release-source.json")
    discrepancy = evidence["user_reported_goal_assist_discrepancy"]
    assert discrepancy["user_reported_assists_in_video"] == 3
    assert discrepancy["user_reported_goals_in_video"] == 1
    assert discrepancy["user_expected_action_tally"] == {"goals": 1, "assists": 3}
    assert discrepancy["exported_report_action_tally"] == {"goals": 2, "assists": 2}
    assert discrepancy["exported_report_observed_assists"] == 2
    assert discrepancy["exported_report_observed_goals"] == 2
    assert discrepancy["discrepancy_status"] == "UNRESOLVED_ORIGINAL_REPORT_2_GOALS_2_ASSISTS_VERSUS_USER_1_GOAL_3_ASSISTS"
    assert [e["proof_ms"] for e in discrepancy["confirmed_export_assist_events"]] == [44065, 56264]
    candidate = discrepancy["candidate_for_misattribution_review"]
    assert candidate["event_id"] == "47ad617d2ba76a4683cd"
    assert candidate["proof_ms"] == 49881
    assert candidate["currently_exported_as"] == "SHOT_GOAL"
    assert candidate["goal_scoring_actor_verified_by_independent_review"] is False
    assert evidence["current_release_acceptance"] == "RELEASE_BLOCKED_PENDING_SOURCE_BOUND_PERSON_ROLE_RECONCILIATION_DESPITE_SAME_VIDEO_PLAY_CONFIRMED"
    assert evidence["production_cache_enabled"] is False


def test_latest_source_receipts_explicitly_conflict_with_previously_verified_assist():
    evidence = load("orman1000-release-source.json")
    previous = evidence["previously_verified_model_findings"]
    assert previous["total_goals"] == 1
    assert previous["total_assists"] == 3
    assert previous["original_video_sha256"] == "b9e2ba4975ed9dc2497f860a80644711bfd12a2125d9fba6390600b0409ab999"
    assert [row["type"] for row in previous["chronological_actions"]] == [
        "GOAL", "ASSIST", "ASSIST", "ASSIST"
    ]
    conflict = evidence["prior_model_conflict_at_50_seconds"]
    assert conflict["orman1000_source_sha256"] == SOURCE
    assert conflict["stored_export_proof_ms"] == 49881
    assert conflict["regression_classification"] == "MODEL_TO_MODEL_ACTION_ATTRIBUTION_DISAGREEMENT"
    assert [r["packet_id"] for r in conflict["receipts"]] == [
        "sequence_006", "contact_review_006"
    ]
    assert all((r["model_decision"], r["model_outcome"], r["finisher"]) ==
               ("SHOT", "GOAL", "p1") for r in conflict["receipts"])
    assert conflict["historical_reference"]["evidence_ms_range"] == [49848, 50065]
    assert conflict["cause_not_yet_proven"] is True
    assert conflict["production_fix_implemented"] is False


def test_older_approved_assist_and_current_orman1000_are_same_video_play_not_same_local_ids():
    evidence = load("orman1000-release-source.json")
    linked = evidence["cross_sha_perceptual_source_comparison"]
    assert linked["source_sha256"] == SOURCE
    assert linked["historical_source_sha256"] != SOURCE
    assert linked["run_id"] == 42315757175
    assert linked["total_target_frames"] == linked["match_count"] == 13
    assert linked["exact_decoded_pts_matches"] == 12
    assert linked["one_matched_pts_difference_ms"] == 16
    assert linked["same_underlying_play_supported"] is True
    assert linked["original_human_anchor_sets_byte_identical"] is False
    assert len(linked["older_source_tap_times_seconds"]) == 10
    assert len(linked["latest_orman1000_tap_times_seconds"]) == 10
    assert linked["older_source_tap_times_seconds"][7] != linked["latest_orman1000_tap_times_seconds"][7]
    assert linked["direct_receipt_transfer_approved"] is False
    assert linked["canonical_stats_mutated"] is False
    assert linked["provider_model_calls"] == 0
    historical = evidence["previously_verified_model_findings"]
    assert historical["verified_previous_receipt_response_sha256"] == (
        "c1b78325895885002ccc58f036b0a29824406997108b12648f3805a46e0040ff"
    )
    assert historical["verified_previous_contact_interval_ms"] == [49715,50081]
    assert historical["verified_previous_receiver_finish_interval_ms"] == [50331,50648]
    assert "white teammate" in historical["verified_previous_receiver"]
    conflict = evidence["prior_model_conflict_at_50_seconds"]
    assert conflict["historical_reference"]["same_underlying_play_verified_by_perceptual_frame_matching"] is True
    assert conflict["historical_reference"]["independent_player_role_reconciliation_automatically_applied"] is False
    assert "Orman1000-local p3, a blue opponent" in historical["verified_previous_receiver"]
    assert evidence["current_release_acceptance"].startswith("RELEASE_BLOCKED_")


def test_prior_approved_assist_receipt_actor_and_finisher_are_two_distinct_people():
    evidence = load("orman1000-release-source.json")
    previous = evidence["previously_verified_model_findings"]
    prior = json.loads((BASE.parents[1] / "docs/examples/native-third-assist-approval-receipt.json").read_text())
    assert prior["source_video_sha256"] == previous["original_video_sha256"]
    assert prior["response_sha256"] == previous["verified_previous_receipt_response_sha256"]
    approved = prior["result"]["target_events"]
    matches = [e for e in approved if e.get("event_type") == "ASSIST"
               and e.get("approval_status") == "APPROVED"]
    assert len(matches) == 1
    row = matches[0]
    assert row["actor"] == "p1"
    assert row["receiver"] == row["finisher"] == "p3"
    assert row["actor"] != row["finisher"]
    assert row["contact_interval_ms"] == [49715,50081]
    assert row["receiver_interval_ms"] == [50331,50648]
    assert row["finishing_contact_interval_ms"] == [50331,50648]
    assert row["outcome_ms"] == 51131
    # Previous local p3 is a white finisher. New model local p3 is BLUE.
    assert "white-kit teammate" in next(p["appearance"] for p in
            prior["result"]["raw_observations"]["players"] if p["person_id"] == "p3")


def test_current_50s_goal_bracket_cannot_prove_single_player_contact():
    evidence = load("orman1000-release-source.json")
    conflict = evidence["current_50s_contact_role_bracket_conflict"]
    assert conflict["current_source_video_sha256"] == SOURCE
    assert conflict["current_source_event_id"] == "47ad617d2ba76a4683cd"
    a = conflict["current_model_goal_contact_bracket_ms"]
    b = conflict["prior_approved_selected_player_pass_ms"]
    c = conflict["prior_approved_separate_white_teammate_finishing_contact_ms"]
    assert (a, b, c) == ([49881, 50648], [49715, 50081], [50331, 50648])
    overlap = lambda x, y: max(0, min(x[1],y[1]) - max(x[0],y[0]))
    assert overlap(a, b) == conflict["current_contact_bracket_overlap_with_prior_selected_pass_ms"] == 200
    assert overlap(a, c) == conflict["current_contact_bracket_overlap_with_prior_distinct_finish_ms"] == 317
    assert conflict["underlying_play_verified_13_of_13_frames"] is True
    assert conflict["old_p3_role"] == "WHITE_TEAMMATE_FINISHER"
    assert conflict["orman1000_p3_role"] == "BLUE_OPPONENT"
    assert conflict["copied_actor_ids_across_runs"] is False
    assert conflict["live_canonical_event_modified"] is False
    assert conflict["role_mapping_status"].startswith("BLOCKED_")


def test_two_new_model_player_censuses_omit_old_approved_white_finisher():
    evidence = load("orman1000-release-source.json")
    census = evidence["source_player_census_at_50s"]
    assert census["same_underlying_play_confirmed_by_13_visual_frame_fingerprints"] is True
    assert [p["packet_id"] for p in census["orman1000_model_packets"]] == [
        "sequence_006", "contact_review_006"
    ]
    assert [p["explicit_image_count"] for p in census["orman1000_model_packets"]] == [67,189]
    assert all(p["people_in_play"] == 7
               and p["selected_local_person"] == "p1"
               and p["separate_white_finisher_registered"] is False
               and p["local_p3_kit"] == "BLUE"
               for p in census["orman1000_model_packets"])
    prior = census["previously_approved_model"]
    assert prior["explicit_image_count"] == 255
    assert prior["special_limb_comparison_panels_added"] == 5
    assert prior["distinct_white_finisher_recorded"] is True
    assert prior["people_in_approved_source_response"] == 9
    assert census["confirmed_systematic_cause"] is False
    assert census["production_automatic_correction_enabled"] is False
