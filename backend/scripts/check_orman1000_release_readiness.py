"""Fail-closed, read-only Orman1000 release guard.

Compares a candidate corrected report to the exact latest original Orman1000
source ZIP. It never changes events, receipts, pixels, report statistics or a
database and never uses a model. A regular green CI is not release approval.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from collections import Counter

from orman1000_derived_consistency import check_consistency, FOLLOWUP_RUN

TARGET = "47ad617d2ba76a4683cd"
SOURCE = "fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2"
ARCHIVE = "3b27260511ed965952a497f97d1c6345a0f1b4bef1b89a60912a62e0f6530c0c"
PRIOR_RECEIPT = "c1b78325895885002ccc58f036b0a29824406997108b12648f3805a46e0040ff"
FINISHER_SOURCE_FRAME_HASHES = {
    "s000050331": "4c1daa279d50b4a447c9406e1b25f6ff0f0f34dfbe4880372dfbdf983ddf92b1",
    "s000050648": "ba5d26a54b40fec01d29fa02a53d8ec51c5e5d246ff50c6ade8d33e8953be9f3",
}


def stable(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def judge(original, candidate, role_review=None):
    """Return (ready, blockers); never promote desired counts into evidence."""
    errors = []
    def check(ok, error):
        if not ok:
            errors.append(error)

    prior_bundle = original.get("canonical_events") or {}
    candidate_bundle = candidate.get("canonical_events") or {}
    old, new = prior_bundle.get("events") or [], candidate_bundle.get("events") or []
    check(prior_bundle.get("source_video_sha256") == SOURCE, "ORIGINAL_VIDEO_SHA_MISMATCH")
    check(candidate_bundle.get("source_video_sha256") == SOURCE, "CANDIDATE_VIDEO_SHA_MISMATCH")
    if len(old) != 21 or len(new) != 21:
        errors.append("CANONICAL_21_EVENTS_REQUIRED")
        return False, errors
    old_ids, new_ids = [e.get("event_id") for e in old], [e.get("event_id") for e in new]
    if (len(set(old_ids)) != 21 or len(set(new_ids)) != 21
            or set(old_ids) != set(new_ids)):
        errors.append("CANONICAL_EVENT_IDS_CHANGED")
        return False, errors
    original_by_id = {e["event_id"]: e for e in old}
    candidate_by_id = {e["event_id"]: e for e in new}
    for eid in old_ids:
        if eid not in (TARGET, FOLLOWUP_RUN) and stable(original_by_id[eid]) != stable(candidate_by_id[eid]):
            errors.append("OTHER_CANONICAL_EVENT_CHANGED:" + eid)
    before = original_by_id[TARGET]
    action = candidate_by_id[TARGET]
    check(before.get("canonical_action_type") == "SHOT"
          and before.get("canonical_outcome") == "GOAL", "ORIGINAL_DISPUTED_GOAL_CHANGED")
    check(action.get("source_video_sha256") == SOURCE, "DISPUTED_ACTION_SOURCE_CHANGED")
    original_proof = before.get("proof") or {}
    revised_proof = action.get("proof") or {}
    check(original_proof.get("source_video_sha256") == SOURCE
          and revised_proof.get("source_video_sha256") == SOURCE,
          "DISPUTED_PROOF_VIDEO_SHA_CHANGED")
    check((original_proof.get("frame_id"), original_proof.get("frame_ms")) ==
          (revised_proof.get("frame_id"), revised_proof.get("frame_ms")) ==
          ("s000049881", 49881),
          "DISPUTED_PROOF_ANCHOR_CHANGED")
    required_pts = {"s000050648": 50648, "s000051131": 51131}
    frames = revised_proof.get("cited_frames") or {}
    check(all(frames.get(k) == v for k, v in required_pts.items()),
          "SOURCE_GOAL_OUTCOME_FRAMES_NOT_RETAINED")
    check((action.get("canonical_action_type"), action.get("canonical_event_type"),
           action.get("canonical_outcome")) == ("PASS", "ASSIST", "TEAMMATE_GOAL"),
          "DISPUTED_ACTION_NOT_RECLASSIFIED_AS_ASSIST")
    counts = Counter(e.get("canonical_event_type") for e in new)
    check((counts["GOAL"], counts["ASSIST"]) == (1, 3),
          "CANONICAL_COUNTS_NOT_1_GOAL_3_ASSISTS")
    stats = (candidate.get("full_report") or {}).get("match_stats") or {}
    check((stats.get("observed_goals"), stats.get("observed_assists")) == (1, 3),
          "PUBLISHED_STATS_NOT_1_GOAL_3_ASSISTS")
    chain = action.get("causal_chain") or {}
    finisher, receiver = chain.get("finisher_visual_id"), chain.get("receiver_visual_id")
    selected_actor = before.get("actor_visual_id")
    check((not selected_actor or action.get("actor_visual_id") == selected_actor)
          and (not before.get("global_target_id") or
               action.get("global_target_id") == before.get("global_target_id")),
          "SELECTED_PLAYER_IDENTITY_CHANGED")
    check(bool(receiver) and receiver == finisher
          and receiver not in ("p1", "p3", "prior:p3", selected_actor),
          "SOURCE_SCOPED_WHITE_FINISHER_NOT_BOUND")
    cards = (candidate.get("full_report") or {}).get("video_comments") or []
    affected = [c for c in cards if c.get("event_id") == TARGET]
    check(len(affected) == 1, "SINGLE_REVIEWED_REPORT_CARD_REQUIRED")
    if len(affected) == 1:
        card = affected[0]
        room = card.get("match_room") or {}
        check(card.get("source_video_sha256") == SOURCE
              and room.get("source_video_sha256") == SOURCE,
              "REPORT_CARD_SOURCE_CHANGED")
        check(room.get("action_type") == "PASS"
              and room.get("action_outcome") == "TEAMMATE_GOAL",
              "MATCH_ROOM_STILL_SAYS_OWN_GOAL")
        check(bool(receiver) and room.get("receiver_visual_id") == receiver,
              "MATCH_ROOM_RECIPIENT_NOT_SAME_VERIFIED_PERSON")
        observation = room.get("observation") or ""
        check(bool(observation)
              and "this is a selected-player goal" not in observation.lower()
              and "no teammate receives and shoots" not in observation.lower()
              and "not a direct assist" not in observation.lower(),
              "MATCH_ROOM_CAUSAL_NARRATIVE_STALE")
        check(card.get("comment") == "Verified assist by the selected player.",
              "REPORT_COMMENT_STILL_SAYS_OWN_GOAL")
    review = role_review or {}
    check(review.get("source_video_sha256") == SOURCE
          and review.get("event_id") == TARGET,
          "INDEPENDENT_ROLE_REVIEW_WRONG_SOURCE")
    check(review.get("status") == "VERIFIED_DISTINCT_WHITE_FINISHER",
          "INDEPENDENT_ROLE_REVIEW_PENDING")
    check(review.get("prior_receipt_response_sha256") == PRIOR_RECEIPT,
          "PREVIOUS_APPROVED_ASSIST_NOT_BOUND")
    check(bool(finisher) and review.get("current_source_finisher_visual_id") == finisher,
          "WHITE_FINISHER_ID_NOT_REVIEWED")
    check(review.get("evidence_frames") == ["s000050331", "s000050648"],
          "WHITE_FINISHER_SOURCE_PTS_NOT_REVIEWED")
    check(review.get("source_decoded_bgr_frame_sha256") == FINISHER_SOURCE_FRAME_HASHES,
          "WHITE_FINISHER_SOURCE_FRAME_BYTES_NOT_BOUND")
    errors.extend(check_consistency(original, candidate))
    return not errors, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-zip", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--role-review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output path")
    digest = hashlib.sha256()
    with args.original_zip.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != ARCHIVE:
        raise ValueError("WRONG_ORIGINAL_ARCHIVE")
    with zipfile.ZipFile(args.original_zip) as archive:
        if archive.testzip():
            raise ValueError("CORRUPT_ORIGINAL_ARCHIVE")
        original = json.loads(archive.read("report.json"))
    candidate = json.loads(args.candidate.read_text()) if args.candidate else original
    review = json.loads(args.role_review.read_text()) if args.role_review else None
    approved, reasons = judge(original, candidate, review)
    result = {
        "source_video_sha256": SOURCE, "release_ready": approved,
        "blockers": reasons, "original_canonical_events": 21,
        "model_calls": 0, "original_archive_modified": False,
        "candidate_modified": False, "production_deployed": False,
        "manual_visual_role_review_still_required": not approved,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return 0 if approved else 2


if __name__ == "__main__":
    raise SystemExit(main())
