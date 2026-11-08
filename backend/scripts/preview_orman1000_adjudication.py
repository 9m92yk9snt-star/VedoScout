"""Fail-closed offline adjudication preview for Orman1000's disputed third assist.

Never rewrites the ZIP, canonical event, model receipt, report, statistics, or
database. Produces ONLY a proposed one-event reconciliation and an exact tally
delta, subject to current-source white-finisher actor-role verification.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "testdata/matchroom-completion/orman1000-release-source.json"
APPROVAL_PATH = ROOT / "docs/examples/native-third-assist-approval-receipt.json"
TARGET_EVENT = "47ad617d2ba76a4683cd"


def sha256_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def propose(bundle, previous, manifest, archive_sha):
    primary = manifest["primary_evidence_archive"]
    older = manifest["previously_verified_model_findings"]
    match = manifest["cross_sha_perceptual_source_comparison"]
    conflict = manifest["prior_model_conflict_at_50_seconds"]
    source = primary["original_source_video_sha256_from_latest_archive"]
    if (archive_sha != primary["archive_sha256"]
            or bundle.get("source_video_sha256") != source
            or previous.get("source_video_sha256") != older["original_video_sha256"]
            or previous.get("response_sha256") != older["verified_previous_receipt_response_sha256"]
            or previous.get("source_video_sha256") == source):
        raise ValueError("UNBOUND_SOURCE_OR_PREVIOUS_RECEIPT")
    if (match.get("run_id") != 42315757175
            or match.get("source_sha256") != source
            or match.get("historical_source_sha256") != previous["source_video_sha256"]
            or match.get("visual_near_matches") != 13
            or match.get("total_target_frames") != 13):
        raise ValueError("SAME_SCENE_EVIDENCE_NOT_VERIFIED")
    # Do not confuse "same scene" with an exact source receipt: both remain
    # distinct and the older p3 cannot be the current model's blue p3.
    approved = [
        e for e in (previous.get("result") or {}).get("target_events", [])
        if e.get("event_id") == older["verified_previous_receipt_event_id"]
        and e.get("approval_status") == "APPROVED"
        and e.get("kind") == "PASS"
        and e.get("event_type") == "ASSIST"
        and e.get("outcome") == "TEAMMATE_GOAL"
        and e.get("selected_player") is True
        and e.get("actor") == "p1"
        and e.get("receiver") == e.get("finisher") == "p3"
        and e.get("actor") != e.get("finisher")
        and e.get("contact_interval_ms") == [49715, 50081]
        and e.get("finishing_contact_interval_ms") == [50331, 50648]
        and e.get("outcome_ms") == 51131
    ]
    people = (previous.get("result") or {}).get("raw_observations", {}).get("players", [])
    prior_receiver = next((p for p in people if p.get("person_id") == "p3"), {})
    if (len(approved) != 1 or "white-kit teammate" not in prior_receiver.get("appearance", "")
            or conflict.get("event_id") != TARGET_EVENT
            or conflict.get("stored_export_proof_ms") != 49881):
        raise ValueError("APPROVED_DISTINCT_FINISHER_REQUIRED")
    events = bundle.get("events")
    if not isinstance(events, list) or len(events) != 21:
        raise ValueError("CANONICAL_EVENT_SET_CHANGED")
    unique_ids = [e.get("event_id") for e in events]
    if len(set(unique_ids)) != len(unique_ids) or unique_ids.count(TARGET_EVENT) != 1:
        raise ValueError("TARGET_EVENT_NOT_UNIQUE")
    event = next(e for e in events if e["event_id"] == TARGET_EVENT)
    if (event.get("source_video_sha256") != source
            or event.get("canonical_event_type") != "GOAL"
            or event.get("canonical_action_type") != "SHOT"
            or event.get("canonical_outcome") != "GOAL"
            or event.get("canonical_ms") != 49881
            or event.get("contact_ms") is not None
            or event.get("contact_interval_ms") != [49881, 50648]
            or (event.get("proof") or {}).get("source_video_sha256") != source):
        raise ValueError("DISPUTED_ORMAN1000_EVENT_CHANGED")
    if not all(
        any(r.get("packet_id") == packet["packet_id"]
            and r.get("response_sha256") == packet["response_sha256"]
            for r in (conflict.get("receipts") or []))
        for packet in (event.get("proof") or {}).get("receipts", [])
    ):
        raise ValueError("CURRENT_CONTRADICTORY_RECEIPT_CHANGED")

    counted = Counter(e.get("canonical_event_type") for e in events)
    if counted["GOAL"] != 2 or counted["ASSIST"] != 2:
        raise ValueError("EXPORTED_COUNTS_DIFFER_FROM_REVIEW_BASELINE")
    # The current model's broad 'own-shot' contact bracket overlaps TWO
    # independently differentiated contacts in the earlier approved model:
    # a pass by the selected player, then a separate white teammate's finish.
    # Diagnose collapsed-role risk; source-local player IDs are never copied.
    prior_release = approved[0]["contact_interval_ms"]
    prior_finish = approved[0]["finishing_contact_interval_ms"]
    current_bracket = event["contact_interval_ms"]
    overlap = lambda a,b: max(0, min(a[1],b[1])-max(a[0],b[0]))
    pass_overlap = overlap(current_bracket, prior_release)
    finisher_overlap = overlap(current_bracket, prior_finish)
    if pass_overlap <= 0 or finisher_overlap <= 0 or prior_release[1] >= prior_finish[0]:
        raise ValueError("DISTINCT_PASS_AND_FINISH_SOURCE_INTERVALS_REQUIRED")
    new_goals = counted["GOAL"] - 1
    new_assists = counted["ASSIST"] + 1
    assert (new_goals, new_assists) == (1, 3)
    # All 21 canonical events, including the disputed event, remain byte-for-byte
    # unchanged. Only the safe hypothetical resolution is returned.
    event_fingerprint = hashlib.sha256(
        json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    others_fingerprint = hashlib.sha256(
        json.dumps([e for e in events if e.get("event_id") != TARGET_EVENT],
                   sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "status": "REVIEW_PROPOSAL_NOT_PUBLISHED",
        "source_video_sha256": source,
        "zip_sha256": archive_sha,
        "same_footage_frame_matches": 13,
        "prior_approved_receipt_source": previous["source_video_sha256"],
        "prior_approved_action": "PASS_TO_DISTINCT_WHITE_TEAMMATE_THEN_TEAMMATE_GOAL",
        "contact_role_conflict": {
            "current_reported_own_shot_bracket_ms": current_bracket,
            "prior_selected_player_pass_ms": prior_release,
            "prior_separate_white_teammate_finish_ms": prior_finish,
            "current_bracket_overlap_with_prior_pass_ms": pass_overlap,
            "current_bracket_overlap_with_prior_teammate_finish_ms": finisher_overlap,
            "two_distinct_prior_actor_roles_overlap_current_goal_bracket": True,
            "automatic_cross_source_role_transfer": False,
        },
        "previous_model_local_p3_role": "WHITE_TEAMMATE_FINISHER",
        "orman1000_model_local_p3_role": "BLUE_OPPONENT",
        "actor_ids_transferred_across_model_runs": False,
        "disputed_event_id": TARGET_EVENT,
        "disputed_event_original_sha256": event_fingerprint,
        "all_other_20_events_sha256": others_fingerprint,
        "exported_observed_counts": {"goals": 2, "assists": 2},
        "proposed_observed_counts_if_approved": {"goals": new_goals, "assists": new_assists},
        "suggested_action": {
            "canonical_event_type": "ASSIST",
            "canonical_action_type": "PASS",
            "canonical_outcome": "TEAMMATE_GOAL",
            "prior_contact_interval_ms": [49715, 50081],
            "prior_white_finisher_interval_ms": [50331, 50648],
            "goal_outcome_ms": 51131,
            "current_source_receiver_visual_id": None,
            "current_source_finisher_visual_id": None,
            "proposed_change_auto_approved": False,
        },
        "required_to_publish": [
            "Identify the distinct white finisher using current Orman1000 source frames and original selected-player references",
            "Bind revised action to current event/source without reusing old model-local p3",
            "Recompute and review every derived statistic, timeline, report comment, PDF, and Match Room surface",
            "Pass production CI, exact source report comparison, and user's merge/deploy decision",
        ],
        "canonical_event_overwritten": False,
        "report_or_database_written": False,
        "new_paid_model_calls": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output must be a new path")
    source_hash = sha256_file(args.source_zip)
    with zipfile.ZipFile(args.source_zip) as archive:
        if archive.testzip():
            raise ValueError("CORRUPT_ARCHIVE")
        doc = json.loads(archive.read("canonical.json"))
        bundle = doc["canonical_events"]
    previous = json.loads(APPROVAL_PATH.read_text())
    manifest = json.loads(MANIFEST_PATH.read_text())
    result = propose(bundle, previous, manifest, source_hash)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print("ORMAN1000_ADJUDICATION_PREVIEW=" + json.dumps(result))


if __name__ == "__main__":
    main()
