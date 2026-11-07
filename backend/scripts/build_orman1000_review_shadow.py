"""Unpublished, deterministic 1-goal/3-assist REVIEW COPY of Orman1000.

Use only the already verified source archive, same canonical event and previously
approved same-play evidence. Never claim that an independent current-source
finisher identity has been established. The original report/receipts are never
overwritten. Model/provider calls: ZERO.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import zipfile

from verified_stats import build_verified_stats, rebuild_match_stats
from orman1000_derived_consistency import FOLLOWUP_RUN, NEUTRAL_RUN, TARGET

SOURCE = "fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2"
ARCHIVE = "3b27260511ed965952a497f97d1c6345a0f1b4bef1b89a60912a62e0f6530c0c"
PASSED_RECEIPT = "c1b78325895885002ccc58f036b0a29824406997108b12648f3805a46e0040ff"


def review_only(original):
    """Build a fully labelled proposal, never an accepted or published report."""
    if original.get("canonical_events", {}).get("source_video_sha256") != SOURCE:
        raise ValueError("FOREIGN_SOURCE")
    bundle = original["canonical_events"]
    events = bundle["events"]
    if len(events) != 21 or len({e["event_id"] for e in events}) != 21:
        raise ValueError("ORIGINAL_EVENT_COUNT_OR_IDENTITIES_CHANGED")
    disputed = [e for e in events if e["event_id"] == TARGET]
    if (len(disputed) != 1 or disputed[0].get("canonical_action_type") != "SHOT"
            or disputed[0].get("canonical_outcome") != "GOAL"
            or disputed[0].get("canonical_ms") != 49881
            or disputed[0].get("contact_interval_ms") != [49881,50648]
            or (disputed[0].get("proof") or {}).get("source_video_sha256") != SOURCE):
        raise ValueError("ORIGINAL_DISPUTED_EVENT_CHANGED")
    output = deepcopy(original)
    event = next(e for e in output["canonical_events"]["events"]
                 if e["event_id"] == TARGET)
    event.update(
        canonical_action_type="PASS", canonical_event_type="ASSIST",
        canonical_outcome="TEAMMATE_GOAL",
        contact_interval_ms=[49715,50081],
        details=[
            "REVIEW PROPOSAL ONLY: an earlier approved same-play model separates "
            "the selected player's release (49.715–50.081 s) from another white "
            "player's finish (50.331–50.648 s). The source-local identity of the "
            "finisher in Orman1000 is not yet independently verified."
        ],
    )
    # Do not copy prior-model 'p3', which identifies a blue opponent in the
    # current Orman1000 model. Unknown stays unknown, never invented.
    event["causal_chain"].update(
        receiver_visual_id=None, finisher_visual_id=None,
        target_contact_ms=None, goal_outcome_ms=51131
    )
    after_run = next(e for e in output["canonical_events"]["events"]
                     if e["event_id"] == FOLLOWUP_RUN)
    after_run["details"] = [NEUTRAL_RUN]
    full = output["full_report"]
    for row in full["action_timeline"]:
        if row["event_id"] == TARGET:
            row.update(
                action_type="pass", title="Assist", canonical_action_type="PASS",
                canonical_event_type="ASSIST", canonical_result="TEAMMATE_SCORED",
                football_action_type="PASS", football_event_type="ASSIST",
                football_outcome="TEAMMATE_GOAL",
                contact_interval_ms=[49715,50081],
                causal_chain=deepcopy(event["causal_chain"]),
                football_details=deepcopy(event["details"]),
                description=event["details"][0],
            )
        elif row["event_id"] == FOLLOWUP_RUN:
            row["football_details"] = [NEUTRAL_RUN]

    # The *existing product calculation*, not hand-edited observed totals.
    build_verified_stats(full, {
        "performed":True, "coverage_complete":False,
        "coverage_status":"PARTIAL", "authority":"SEQUENCE_V1"
    })
    rebuild_match_stats(full)

    for card in full["video_comments"]:
        if card["event_id"] != TARGET:
            continue
        card.update(
            comment="Proposed assist — independent current-source finisher review pending.",
            contact_interval_ms=[49715,50081],
        )
        room = card.get("match_room") or {}
        room.update(
            action_type="PASS", action_outcome="TEAMMATE_GOAL",
            contact_ms=None, receiver_visual_id=None,
            observation=event["details"][0],
        )
        # Source masks for the selected player remain useful. Never display
        # the old shot-specific ball arrow as if it had become a proven assist.
        if isinstance(room.get("tracking"), dict):
            room["tracking"]["ball_playback"] = []
        card["match_room"] = room
    if isinstance((full.get("parent_value_metrics") or {}).get("top_minutes"), list):
        for row in full["parent_value_metrics"]["top_minutes"]:
            if isinstance(row, dict) and "a second goal" in str(row.get("why","")).lower():
                row["why"] = (
                    "REVIEW PROPOSAL: attacking actions include a goal and three "
                    "assist candidates; the third assist's finisher awaits review."
                )
    output["full_report_status"] = "REVIEW_ONLY_NOT_PUBLISHED"
    output["report_release_allowed"] = False
    output["adjudication_preview"] = {
        "status":"CURRENT_SOURCE_FINISHER_ROLE_UNRESOLVED",
        "source_video_sha256":SOURCE,
        "earlier_approved_response_sha256":PASSED_RECEIPT,
        "disputed_event_id":TARGET,
        "earlier_same_scene_frame_matches":13,
        "original_report_unmodified":True,
        "new_provider_model_calls":0,
        "canonical_model_receipts_not_rewritten":True,
        "source_local_receiver_visual_id":None,
        "published":False,
        "user_confirmation_required_before_release":True,
    }
    return output


def digest(path):
    h = hashlib.sha256()
    with open(path,"rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing overwrite")
    if digest(args.original_zip) != ARCHIVE:
        raise ValueError("WRONG_ORMAN1000_ZIP")
    with zipfile.ZipFile(args.original_zip) as archive:
        if archive.testzip() is not None:
            raise ValueError("CORRUPT_SOURCE_ARCHIVE")
        original = json.loads(archive.read("report.json"))
    shadow = review_only(original)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(shadow, ensure_ascii=False, separators=(",",":")))
    stats = shadow["full_report"]["match_stats"]
    result = {
        "status":"REVIEW_ONLY_NOT_PUBLISHED",
        "source_video_sha256":SOURCE,
        "observed_goals":stats["observed_goals"],
        "observed_assists":stats["observed_assists"],
        "shots":stats["shots"], "passes_completed":stats["passes_completed"],
        "original_video_and_21_events_retained":True,
        "current_source_finisher_verified":False,
        "new_model_calls":0,"production_modified":False,
    }
    print("ORMAN1000_REVIEW_SHADOW="+json.dumps(result))


if __name__ == "__main__":
    main()
