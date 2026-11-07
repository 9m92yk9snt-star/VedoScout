"""Prepare a single UNPUBLISHED Orman1000 fully reconciled report candidate.

This routine runs only after explicit independent review of the current
source's WHITE finisher. It is NOT used by live analysis or any database job.
The old 21 events / source receipts are preserved as input; the revised output
is always a new file, no original bytes are ever changed. The final checker
runs over every derived report surface and original source-player locations.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import zipfile

from scripts.build_orman1000_review_shadow import review_only, SOURCE, ARCHIVE
from scripts.check_orman1000_release_readiness import judge
from orman1000_derived_consistency import TARGET
from orman1000_review_provenance import make_resolution

def reviewed_candidate(original, verified_role_review):
    # The role review is external evidence of a current-video separate white
    # player. This code can NEVER infer such a player from previous local IDs.
    role = deepcopy(verified_role_review)
    if (role.get("source_video_sha256") != SOURCE or
            role.get("event_id") != TARGET or
            role.get("status") != "VERIFIED_DISTINCT_WHITE_FINISHER"):
        raise ValueError("SOURCE_BOUND_INDEPENDENT_FINISHER_REVIEW_REQUIRED")
    finisher=role.get("current_source_finisher_visual_id")
    if (not isinstance(finisher,str) or not finisher
            or finisher in ("p1","p3","prior:p3")):
        raise ValueError("INVALID_ORMAN1000_FINISHER_ID")
    candidate=review_only(original)
    actions=candidate["canonical_events"]["events"]
    revised=next(e for e in actions if e["event_id"]==TARGET)
    original_disputed=next(e for e in original["canonical_events"]["events"]
                           if e["event_id"]==TARGET)
    # Do NOT replace a contradictory source-model receipt. Append a separate,
    # source-scoped adjudication trail identifying exactly what overrode it.
    revised["review_resolution"]=make_resolution(original_disputed, role)
    revised["causal_chain"].update(
        receiver_visual_id=finisher, finisher_visual_id=finisher,
        target_contact_ms=None, goal_outcome_ms=51131,
    )
    description=(
        "Source-reviewed direct assist: the selected player's release precedes "
        "a separate white teammate's finish toward goal. The two distinct "
        "bodies are tied to the original Orman1000 frames at 50.331 and "
        "50.648 seconds. Exact foot-ball contact is partly occluded and "
        "must not be represented as measured at a single instant."
    )
    revised["details"]=[description]
    for event in candidate["full_report"]["action_timeline"]:
        if event["event_id"]!=TARGET:continue
        event["causal_chain"]=deepcopy(revised["causal_chain"])
        event["football_details"]=[description]
        event["description"]=description
    for card in candidate["full_report"]["video_comments"]:
        if card["event_id"]!=TARGET:continue
        card["comment"]="Verified assist by the selected player."
        room=card.get("match_room") or {}
        room.update(
            action_type="PASS",action_outcome="TEAMMATE_GOAL",
            receiver_visual_id=finisher, observation=description,
            contact_ms=None,
        )
        # The real source-bound player outline remains unchanged. Old
        # outgoing own-goal arrow was removed by review_only(), and there is
        # no permission to invent a new assist arrow.
        if isinstance(room.get("tracking"),dict):
            room["tracking"]["ball_playback"]=[]
        card["match_room"]=room
    parent=(candidate["full_report"].get("parent_value_metrics") or {})
    for row in parent.get("top_minutes") or []:
        if isinstance(row,dict) and "review proposal" in str(row.get("why","")).lower():
            row["why"]="The selected player contributed one goal and a source-reviewed direct assist."
    # Separate review provenance from raw model receipts, preserving the
    # difference between original model assertion and independent adjudication.
    candidate["full_report"]["independent_action_review_trails"] = [
        deepcopy(revised["review_resolution"])
    ]
    ready, blockers=judge(original,candidate,role)
    if not ready:
        raise ValueError("UNPUBLISHED_ORMAN1000_CANDIDATE_NOT_READY:"+",".join(blockers))
    candidate["full_report_status"]="SOURCE_REVIEWED_CANDIDATE_NOT_PUBLISHED"
    candidate["report_release_allowed"]=False
    candidate["adjudication_preview"]={
        "status":"REVIEWED_CANDIDATE_ONLY",
        "source_video_sha256":SOURCE, "disputed_event_id":TARGET,
        "reviewed_current_source_finisher_visual_id":finisher,
        "review_source_frame_ids":list(role["evidence_frames"]),
        "source_frame_hashes":deepcopy(role["source_decoded_bgr_frame_sha256"]),
        "canonical_other_19_events_unchanged":True,
        "new_provider_calls":0,
        "published":False, "merged":False,
        "requires_user_approval_before_publication":True,
    }
    return candidate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-zip",type=Path,required=True)
    parser.add_argument("--verified-finisher-role",type=Path,required=True)
    parser.add_argument("--new-output",type=Path,required=True)
    args=parser.parse_args()
    if args.new_output.exists():
        parser.error("Refusing overwrite of candidate or original")
    h=hashlib.sha256()
    with args.original_zip.open("rb") as stream:
        for part in iter(lambda:stream.read(1024*1024),b""):
            h.update(part)
    if h.hexdigest()!=ARCHIVE:
        raise ValueError("NOT_THE_LATEST_ORMAN1000_SOURCE")
    with zipfile.ZipFile(args.original_zip) as archive:
        if archive.testzip() is not None:
            raise ValueError("CORRUPTED_SOURCE_ARCHIVE")
        original=json.loads(archive.read("report.json"))
    verified=json.loads(args.verified_finisher_role.read_text())
    output=reviewed_candidate(original,verified)
    args.new_output.parent.mkdir(parents=True,exist_ok=True)
    args.new_output.write_text(json.dumps(output,ensure_ascii=False,separators=(",",":")))
    print(json.dumps({
        "status":"UNPUBLISHED_REVIEWED_CANDIDATE",
        "original_bytes_changed":False,
        "production_published":False,
        "source_video_sha256":SOURCE,
        "new_paid_model_calls":0,
        "counts":{"goals":1,"assists":3},
    }))


if __name__=="__main__":
    main()
