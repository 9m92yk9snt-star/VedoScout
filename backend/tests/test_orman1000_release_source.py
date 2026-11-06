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
    assert discrepancy["exported_report_observed_assists"] == 2
    assert discrepancy["exported_report_observed_goals"] == 2
    assert discrepancy["discrepancy_status"] == "UNRESOLVED_USER_REPORTED_THIRD_ASSIST"
    assert [e["proof_ms"] for e in discrepancy["confirmed_export_assist_events"]] == [44065, 56264]
    candidate = discrepancy["candidate_for_misattribution_review"]
    assert candidate["event_id"] == "47ad617d2ba76a4683cd"
    assert candidate["proof_ms"] == 49881
    assert candidate["currently_exported_as"] == "SHOT_GOAL"
    assert candidate["goal_scoring_actor_verified_by_independent_review"] is False
    assert evidence["current_release_acceptance"] == "BLOCKED_UNRESOLVED_THIRD_ASSIST_AND_EVENT_ATTRIBUTION"
    assert evidence["production_cache_enabled"] is False
