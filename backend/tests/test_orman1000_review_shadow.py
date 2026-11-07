"""Test ONLY an unpublished deterministic review candidate; never publication."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from scripts.build_orman1000_review_shadow import review_only, SOURCE, TARGET
from orman1000_derived_consistency import FOLLOWUP_RUN, NEUTRAL_RUN
from scripts.finalize_orman1000_review_candidate import reviewed_candidate
from scripts.check_orman1000_release_readiness import FINISHER_SOURCE_FRAME_HASHES
from verified_stats import build_verified_stats, rebuild_match_stats

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "testdata/matchroom-completion/"
                      "orman1000-real-21-event-review-fixture.json").read_text())


def minimum_original():
    source = FIXTURE["video_source_sha256"]
    assert source == SOURCE
    original_events = deepcopy(FIXTURE["other_20_events"])
    selected = deepcopy(FIXTURE["disputed_original"])
    event_types = {e["event_id"]:e["canonical_event_type"] for e in original_events}
    old_run = next(e for e in original_events if e["event_id"] == FOLLOWUP_RUN)
    old_run["details"] = [
        "P1 follows his shot toward goal. No additional p1 ball contact "
        "is visible before the camera pans away."
    ]
    events = original_events + [selected]
    timelines = []
    for e in events:
        eid = e["event_id"]
        kind = e["canonical_event_type"]
        act = ("SHOT" if kind == "GOAL" else "PASS" if kind in ("ASSIST","PASS") else kind)
        outcome = ("SCORED" if kind == "GOAL" else
                   "TEAMMATE_SCORED" if kind == "ASSIST" else
                   "SAVED" if kind == "SHOT" else "COMPLETED")
        row = {
            "event_id":eid,
            "canonical_event_type":kind, "canonical_action_type":act,
            "canonical_result":outcome, "cross_verified":True,
            "outcome_visible":True,"football_event_type":kind,
            "football_action_type":act,"football_outcome":outcome,
            "action_type":act.lower(),
            "title":kind.title(),
            "causal_chain":deepcopy(e.get("causal_chain") or {}),
            "football_details":deepcopy(e.get("details") or []),
        }
        timelines.append(row)
    # The original 50-second event was misclassified as own goal.
    last = timelines[-1]
    last.update(action_type="shot",canonical_action_type="SHOT",
                canonical_event_type="GOAL",canonical_result="SCORED",
                football_action_type="SHOT",football_event_type="GOAL",
                football_outcome="GOAL",title="Goal")
    owner_taps=[{"t":float(i+1),"box":{"x":.1,"y":.5,"w":.1,"h":.1},
                 "target_point":{"x":.15,"y":.55}} for i in range(9)]
    owner_taps.append({"t":51.18,
                       "box":{"x":0.1102,"y":0.4724,"w":0.0759,"h":0.0969},
                       "target_point":{"x":0.16192537621109052,
                                       "y":0.5216450216450216}})
    baseline = {
        "raw_marker_anchors":owner_taps,
        "canonical_events":{"source_video_sha256":SOURCE,"events":events},
        "full_report":{
            "action_timeline":timelines,
            "video_comments":[{
                "event_id":TARGET,"source_video_sha256":SOURCE,
                "comment":"Verified goal by the selected player.",
                "match_room":{"event_id":TARGET,"source_video_sha256":SOURCE,
                              "action_type":"SHOT","action_outcome":"GOAL",
                              "receiver_visual_id":None, "tracking":{
                                  "ball_playback":[{"id":"old-incorrect-shot-trail"}]
                              }, "samples":[{
                                  "frame_id":"s000050648",
                                  "media_ms":50648,
                                  "identity_status":"CONFIRMED",
                                  "ground":[0.257,0.564],
                                  "player_box":[0.177,0.485,0.103,0.081],
                                  "ball":[0.363,0.539],
                              },{
                                  "frame_id":"s000051181","media_ms":51181,
                                  "identity_status":"CONFIRMED",
                                  "player_box":[0.1102,0.4724,0.0759,0.0969],
                                  "ground":[0.17,0.567],
                                  "ball":[0.964,0.541],
                              }]},
            }],
            "parent_value_metrics":{"top_minutes":[{
                "why":"He scores a goal and a second goal."
            }]},
            "match_stats":{"observed_goals":2,"observed_assists":2},
        },
        "full_report_status":"ready",
    }
    build_verified_stats(baseline["full_report"],{
        "performed":True,"coverage_complete":False,
        "coverage_status":"PARTIAL","authority":"SEQUENCE_V1"
    })
    rebuild_match_stats(baseline["full_report"])
    return baseline


def test_unpublished_shadow_changes_only_disputed_event_and_followup_description():
    before = minimum_original()
    original_copy = deepcopy(before)
    result = review_only(before)
    assert before == original_copy
    assert result["report_release_allowed"] is False
    assert result["full_report_status"] == "REVIEW_ONLY_NOT_PUBLISHED"
    meta = result["adjudication_preview"]
    assert meta["source_video_sha256"] == SOURCE
    assert meta["source_local_receiver_visual_id"] is None
    assert meta["published"] is False
    assert meta["new_provider_model_calls"] == 0
    events = result["canonical_events"]["events"]
    assert len(events) == 21
    for old, new in zip(before["canonical_events"]["events"], events):
        if old["event_id"] not in (TARGET, FOLLOWUP_RUN):
            assert old == new
    target = next(e for e in events if e["event_id"] == TARGET)
    assert (target["canonical_event_type"],target["canonical_action_type"],
            target["canonical_outcome"]) == ("ASSIST","PASS","TEAMMATE_GOAL")
    assert target["causal_chain"]["receiver_visual_id"] is None
    assert target["causal_chain"]["finisher_visual_id"] is None
    assert next(e for e in events if e["event_id"] == FOLLOWUP_RUN)["details"] == [NEUTRAL_RUN]
    stats = result["full_report"]["match_stats"]
    assert (stats["observed_goals"],stats["observed_assists"]) == (1,3)
    assert result["full_report"]["video_comments"][0]["match_room"]["tracking"]["ball_playback"] == []
    assert result["full_report"]["verified_stats"]["goals_assists_available"] is False
    assert result["full_report"]["verified_stats"]["coverage_status"] == "PARTIAL"


@pytest.mark.parametrize("change",["source", "event", "contact", "count"])
def test_shadow_cannot_process_wrong_video_or_modified_original_action(change):
    old = minimum_original()
    if change=="source":
        old["canonical_events"]["source_video_sha256"] = "another-source"
    elif change=="event":
        old["canonical_events"]["events"][-1]["canonical_action_type"] = "PASS"
    elif change=="contact":
        old["canonical_events"]["events"][-1]["contact_interval_ms"] = [49715,50081]
    elif change=="count":
        old["canonical_events"]["events"].append(deepcopy(old["canonical_events"]["events"][-1]))
    with pytest.raises(ValueError):
        review_only(old)


def synthetic_role_not_real_video_approval():
    """The scenario tests software logic, not whether the real child scored."""
    return {
        "source_video_sha256":SOURCE,
        "event_id":TARGET,
        "status":"VERIFIED_DISTINCT_WHITE_FINISHER",
        "prior_receipt_response_sha256":"c1b78325895885002ccc58f036b0a29824406997108b12648f3805a46e0040ff",
        "current_source_finisher_visual_id":"SYNTHETIC_ORMAN1000_WHITE_PERSON",
        "evidence_frames":["s000050331","s000050648"],
        "source_decoded_bgr_frame_sha256":deepcopy(FINISHER_SOURCE_FRAME_HASHES),
        "identity_review_method":"SOURCE_FRAME_PERSON_SEPARATION",
        "finisher_kit_observed":"WHITE",
        "finishing_contact_evidence":"OCCLUDED_BRACKETED",
        "source_selected_player_frame_id":"s000050648",
        "source_selected_player_box":[0.177,0.485,0.103,0.081],
        "source_selected_player_ground":[0.257,0.564],
        "source_finisher_boxes":{
            "s000050331":[0.32,0.46,0.09,0.10],
            "s000050648":[0.335,0.47,0.08,0.095],
        },
    }


def test_full_synthetic_role_review_produces_atomically_consistent_unpublished_candidate():
    original=minimum_original()
    before=deepcopy(original)
    candidate=reviewed_candidate(original,synthetic_role_not_real_video_approval())
    assert original == before
    assert candidate["report_release_allowed"] is False
    assert candidate["full_report_status"] == "SOURCE_REVIEWED_CANDIDATE_NOT_PUBLISHED"
    assert candidate["adjudication_preview"]["published"] is False
    assert candidate["adjudication_preview"]["new_provider_calls"] == 0
    events=candidate["canonical_events"]["events"]
    assert len(events)==21
    assert all(e==o for e,o in zip(events,before["canonical_events"]["events"])
               if e["event_id"] not in (TARGET,FOLLOWUP_RUN))
    revised=next(e for e in events if e["event_id"]==TARGET)
    assert (revised["canonical_event_type"],revised["canonical_action_type"],
            revised["canonical_outcome"])==("ASSIST","PASS","TEAMMATE_GOAL")
    assert revised["causal_chain"]["finisher_visual_id"] == "SYNTHETIC_ORMAN1000_WHITE_PERSON"
    assert candidate["full_report"]["match_stats"]["observed_goals"] == 1
    assert candidate["full_report"]["match_stats"]["observed_assists"] == 3
    assert candidate["full_report"]["video_comments"][0]["match_room"]["tracking"]["ball_playback"] == []


@pytest.mark.parametrize("tamper",[
    "unverified", "prior_id", "wrong_video", "wrong_white_kit", "falsified_player",
    "wrong_finisher_frame",
])
def test_unverified_or_wrong_source_role_refuses_even_shadow_finalization(tamper):
    orig=minimum_original()
    role=synthetic_role_not_real_video_approval()
    if tamper=="unverified":role["status"]="PENDING"
    elif tamper=="prior_id":role["current_source_finisher_visual_id"]="p3"
    elif tamper=="wrong_video":role["source_video_sha256"]="foreign"
    elif tamper=="wrong_white_kit":role["finisher_kit_observed"]="BLUE"
    elif tamper=="falsified_player":role["source_selected_player_box"]=[0.1,0.1,0.1,0.1]
    elif tamper=="wrong_finisher_frame":role["source_decoded_bgr_frame_sha256"]["s000050331"]="wrong"
    with pytest.raises(ValueError):
        reviewed_candidate(orig,role)
