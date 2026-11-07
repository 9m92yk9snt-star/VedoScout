"""Test ONLY an unpublished deterministic review candidate; never publication."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from scripts.build_orman1000_review_shadow import review_only, SOURCE, TARGET
from orman1000_derived_consistency import FOLLOWUP_RUN, NEUTRAL_RUN

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
    return {
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
                              }},
            }],
            "parent_value_metrics":{"top_minutes":[{
                "why":"He scores a goal and a second goal."
            }]},
            "match_stats":{"observed_goals":2,"observed_assists":2},
        },
        "full_report_status":"ready",
    }


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
