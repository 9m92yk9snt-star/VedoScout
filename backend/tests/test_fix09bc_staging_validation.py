"""FIX09B/C final staging acceptance contract tests."""
import copy
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import staging_validation as sv  # noqa: E402


def _canonical_event(event_id, event_type, action_type, ms):
    row = {
        "event_id": event_id,
        "global_target_id": "GLOBAL_TARGET",
        "canonical_event_type": event_type,
        "canonical_action_type": action_type,
        "canonical_outcome": "UNKNOWN",
        "canonical_ms": ms,
        "causal_verified": event_type in {"GOAL", "ASSIST"},
    }
    if event_type == "GOAL":
        row["canonical_outcome"] = "GOAL"
    if event_type == "ASSIST":
        row["canonical_outcome"] = "TEAMMATE_GOAL"
        row["receiver_team_resolution"] = {
            "status": "VERIFIED",
            "reason": "RECEIVER_TEAM_AND_BALL_TRANSFER_VERIFIED",
            "sample_counts": {"target_team": 3, "opponent": 0, "other": 0},
            "actor_ball_relation": {"status": "VERIFIED", "likely_holder_samples": 1},
            "receiver_ball_relation": {"status": "VERIFIED", "likely_holder_samples": 1},
        }
    return row


def valid_reference_doc():
    events = [
        _canonical_event("goal", "GOAL", "SHOT", 10_000),
        _canonical_event("assist1", "ASSIST", "PASS", 20_000),
        _canonical_event("assist2", "ASSIST", "PASS", 30_000),
        _canonical_event("assist3", "ASSIST", "CROSS", 40_000),
        _canonical_event("shot2", "SHOT", "SHOT", 50_000),
    ]
    timeline = []
    comments = []
    for i, e in enumerate(events):
        timeline.append({
            "event_id": e["event_id"],
            "event_source": "fix09b_canonical",
            "cross_verified": True,
            "event_start_ms": e["canonical_ms"],
            "canonical_event_type": e["canonical_event_type"],
            "canonical_action_type": e["canonical_action_type"],
        })
        comments.append({
            "event_id": e["event_id"],
            "canonical_event_native": True,
            "event_source": "fix09b_canonical",
            "event_track_locked": True,
            "canonical_event_ms": e["canonical_ms"],
            "evidence_time_ms": e["canonical_ms"],
            "frame_time_ms": e["canonical_ms"],
            "frame_time_authority": "ACTUAL_MEDIA_PTS",
            "frame_url": f"https://example.test/{e['event_id']}.jpg",
            "proof_frame_verified": True,
        })
    for i, c in enumerate(comments[:3]):
        event_ms = events[i]["canonical_ms"]
        c.update({
            "tele_clip_url": f"https://example.test/{c['event_id']}.mp4",
            "clip_id": f"clip_{i}",
            "clip_start_ms": event_ms - 2000,
            "clip_end_ms": event_ms + 3000,
            "moment_local_ms": 2000,
            "telestrated": True,
            "tele_ring": True,
            "tele_authority": "FIX09B_CANONICAL_GEOMETRY",
        })
    scoring = events[:4]
    snapshots = [{
        "event_id": e["event_id"], "proof_verified": True,
        "frame_url": f"https://example.test/{e['event_id']}.jpg",
    } for e in scoring]
    return {
        "full_report_status": "ready",
        "unified_analysis_status": "ok",
        "unified_event_track_source": "UNIFIED_IDENTITY",
        "movement_track_source": "UNIFIED_GLOBAL_TARGET",
        "unified_identity_authority": {"global_target_id": "GLOBAL_TARGET"},
        "football_scene_graph": {
            "status": "ok",
            "team_authority": {"status": "ok", "reason": None},
        },
        "football_sequence_analysis": {
            "coverage_complete": True, "incomplete_sequence_ids": [],
        },
        "canonical_events": {
            "status": "ok", "global_target_id": "GLOBAL_TARGET", "events": events,
        },
        "event_ledger": {
            "authority": "FIX09B_CANONICAL_EVENTS", "discovery_complete": True,
        },
        "unified_scoring_scan": {
            "performed": True, "authority": "FIX09B_CANONICAL_EVENTS",
            "verified_goals": 1, "verified_assists": 3,
        },
        "unified_event_barriers": {"unsafe_intervals": []},
        "full_report": {
            "action_timeline": timeline,
            "video_comments": comments,
            "snapshot_moments": snapshots,
            "snapshot_moments_authority": True,
            "event_discovery": {
                "authority": "FIX09B_CANONICAL_EVENTS",
                "event_discovery_complete": True,
            },
            "verified_stats": {
                "available": True, "goals_assists_available": True,
                "goals": 1, "assists": 3, "shots": 2,
            },
        },
    }


def test_staging_validator_accepts_complete_reference_contract():
    result = sv.validate_report_document(valid_reference_doc())
    assert result["status"] == "pass"
    assert result["failures"] == []
    assert result["metrics"]["goals"] == 1
    assert result["metrics"]["assists"] == 3
    assert result["metrics"]["extra_shots"] == 1


def test_staging_validator_rejects_unverified_assist_receiver():
    doc = valid_reference_doc()
    doc["canonical_events"]["events"][1]["receiver_team_resolution"]["status"] = "UNRESOLVED"
    result = sv.validate_report_document(doc)
    assert result["status"] == "fail"
    assert "assists.teammate_verified" in result["failures"]


def test_staging_validator_rejects_parallel_timeline_time():
    doc = valid_reference_doc()
    doc["full_report"]["action_timeline"][0]["event_start_ms"] += 500
    result = sv.validate_report_document(doc)
    assert "timeline.canonical_time_and_source" in result["failures"]


def test_staging_validator_rejects_scoring_event_inside_identity_barrier():
    doc = valid_reference_doc()
    doc["unified_event_barriers"]["unsafe_intervals"] = [[9.8, 10.2]]
    result = sv.validate_report_document(doc)
    assert "proof.outside_identity_barriers" in result["failures"]


def test_staging_validator_rejects_legacy_fallback_even_if_counts_look_right():
    doc = copy.deepcopy(valid_reference_doc())
    doc["unified_analysis_status"] = "legacy_fallback"
    doc["unified_event_track_source"] = "FIX04_FALLBACK"
    result = sv.validate_report_document(doc)
    assert "engine.unified_status" in result["failures"]
    assert "engine.event_track" in result["failures"]


def test_staging_validator_rejects_noncanonical_scoring_frame_impersonation():
    doc = valid_reference_doc()
    row = doc["full_report"]["video_comments"][0]
    row["canonical_event_native"] = False
    result = sv.validate_report_document(doc)
    assert "proof.scoring_frames" in result["failures"]


def test_staging_validator_rejects_clip_without_canonical_geometry_authority():
    doc = valid_reference_doc()
    doc["full_report"]["video_comments"][0].pop("tele_authority")
    result = sv.validate_report_document(doc)
    assert "proof.clips_and_ellipse" in result["failures"]


def test_staging_validator_rejects_unproven_canonical_frame_pts():
    doc = valid_reference_doc()
    doc["full_report"]["video_comments"][0].pop("frame_time_authority")
    result = sv.validate_report_document(doc)
    assert "proof.scoring_frames" in result["failures"]


def test_staging_validator_rejects_canonical_frame_inside_identity_barrier():
    doc = valid_reference_doc()
    row = doc["full_report"]["video_comments"][0]
    row["evidence_time_ms"] = 10_050
    row["frame_time_ms"] = 10_050
    doc["unified_event_barriers"]["unsafe_intervals"] = [[10.04, 10.06]]
    result = sv.validate_report_document(doc)
    assert "proof.scoring_frames" in result["failures"]
