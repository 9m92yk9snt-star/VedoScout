"""No-model release gate tests: real Orman1000 IDs, simulated review candidates.

A synthetic passing example is NOT an approved real-world scorer identification.
The actual uploaded 2+2 report must fail; all 20 unrelated events are immutable.
"""
from copy import deepcopy
import json
from pathlib import Path

from scripts.check_orman1000_release_readiness import (
    SOURCE, TARGET, PRIOR_RECEIPT, judge
)
from orman1000_derived_consistency import (
    FOLLOWUP_RUN, NEUTRAL_RUN, STAT_DELTAS, REMOVE_IDS, ADD_IDS
)

FIXTURE = (Path(__file__).resolve().parents[2] /
           "testdata/matchroom-completion/orman1000-real-21-event-review-fixture.json")


def real_source_derived_baseline():
    raw = json.loads(FIXTURE.read_text())
    assert raw["video_source_sha256"] == SOURCE
    action = deepcopy(raw["disputed_original"])
    actions = [*deepcopy(raw["other_20_events"]), action]
    old_run = next(e for e in actions if e["event_id"] == FOLLOWUP_RUN)
    old_run["details"] = [
        "P1 follows his shot toward goal. No additional p1 ball contact "
        "is visible before the camera pans away."
    ]
    counted = {
        "goals": ["d1a34d11944defe8c2ce", TARGET],
        "assists": ["006dbd71ed71d464f19d", "16b70d6326506d906e7d"],
        "shots": ["9a392fb19c052dfe6719", "d1a34d11944defe8c2ce", TARGET],
        "shots_on_target": ["9a392fb19c052dfe6719", "d1a34d11944defe8c2ce", TARGET],
        "passes_attempted": ["3662fe46e2175be7f823", "006dbd71ed71d464f19d",
                             "16b70d6326506d906e7d", "aa72fc7d4774da486be7"],
        "passes_completed": ["3662fe46e2175be7f823", "006dbd71ed71d464f19d",
                             "16b70d6326506d906e7d", "aa72fc7d4774da486be7"],
        "key_passes": ["006dbd71ed71d464f19d", "16b70d6326506d906e7d"],
        "runs": [FOLLOWUP_RUN],
    }
    counts = {key:len(value) for key,value in counted.items()}
    timeline = []
    for event in actions:
        row = {"event_id":event["event_id"],"source_video_sha256":SOURCE}
        if event["event_id"] == TARGET:
            row.update(action_type="shot", canonical_action_type="SHOT",
                       canonical_event_type="GOAL", football_action_type="SHOT",
                       football_event_type="GOAL", football_outcome="GOAL",
                       title="Goal", causal_chain=deepcopy(event["causal_chain"]),
                       football_details=["This is a selected-player goal, not a direct assist."])
        if event["event_id"] == FOLLOWUP_RUN:
            row["football_details"] = deepcopy(event["details"])
        timeline.append(row)
    report = {
        "canonical_events": {"source_video_sha256": SOURCE, "events": actions},
        "full_report": {
            "match_stats": {"observed_goals": 2, "observed_assists": 2,
                            "shots":3, "shots_on_target":3, "passes_attempted":4,
                            "passes_completed":4, "key_passes":2,
                            "coverage_status":"PARTIAL"},
            "verified_stats": {
                "observed_counts": {"goals":2, "assists":2, **counts},
                "counted_event_ids":counted,
                "coverage_status":"PARTIAL",
                "goals_assists_available":False,
                "goals":None,"assists":None,"available":True,
                "scoring_scan":{"coverage_status":"PARTIAL","complete":False}
            },
            "action_timeline":timeline,
            "parent_value_metrics":{"top_minutes":[
                {"why":"He delivered a dribble, a goal and a second goal."}
            ]},
            "video_comments": [{
                "event_id": TARGET, "source_video_sha256": SOURCE,
                "comment": "Verified goal by the selected player.",
                "match_room": {
                    "source_video_sha256": SOURCE,
                    "action_type": "SHOT", "action_outcome": "GOAL",
                },
            }],
        },
    }
    return report


def hypothetical_review_only():
    original = real_source_derived_baseline()
    candidate = deepcopy(original)
    action = candidate["canonical_events"]["events"][-1]
    action.update(canonical_event_type="ASSIST", canonical_action_type="PASS",
                  canonical_outcome="TEAMMATE_GOAL")
    next(e for e in candidate["canonical_events"]["events"]
         if e["event_id"] == FOLLOWUP_RUN)["details"] = [NEUTRAL_RUN]
    # Synthetic role proof ONLY; this is not a real source identity assigned.
    tested_role = "synthetic-current-source-white-finisher"
    action["causal_chain"].update(
        receiver_visual_id=tested_role, finisher_visual_id=tested_role
    )
    ms = candidate["full_report"]["match_stats"]
    ms.update(observed_goals=1, observed_assists=3)
    for key, change in STAT_DELTAS.items():
        if key not in ("goals", "assists"):
            ms[key] += change
    verified = candidate["full_report"]["verified_stats"]
    for key, change in STAT_DELTAS.items():
        verified["observed_counts"][key] += change
    for key in REMOVE_IDS:
        verified["counted_event_ids"][key].remove(TARGET)
    for key in ADD_IDS:
        verified["counted_event_ids"][key].append(TARGET)
    for row in candidate["full_report"]["action_timeline"]:
        if row["event_id"] == TARGET:
            row.update(action_type="pass", canonical_action_type="PASS",
                       canonical_event_type="ASSIST", football_action_type="PASS",
                       football_event_type="ASSIST", football_outcome="TEAMMATE_GOAL",
                       canonical_result="TEAMMATE_SCORED",
                       title="Assist", causal_chain=deepcopy(action["causal_chain"]),
                       football_details=["Synthetic reviewed assist to a distinct player."])
        elif row["event_id"] == FOLLOWUP_RUN:
            row["football_details"] = [NEUTRAL_RUN]
    candidate["full_report"]["parent_value_metrics"]["top_minutes"][0]["why"] = (
        "He delivered a dribble, a goal and a direct assist."
    )
    card = candidate["full_report"]["video_comments"][0]
    card["comment"] = "Verified assist by the selected player."
    card["match_room"].update(
        action_type="PASS", action_outcome="TEAMMATE_GOAL",
        receiver_visual_id=tested_role,
        observation="Synthetic distinct white teammate receives and finishes; source review not real.",
    )
    review = {
        "source_video_sha256": SOURCE, "event_id": TARGET,
        "prior_receipt_response_sha256": PRIOR_RECEIPT,
        "status": "VERIFIED_DISTINCT_WHITE_FINISHER",
        "current_source_finisher_visual_id": tested_role,
        "evidence_frames": ["s000050331", "s000050648"],
    }
    return original, candidate, review


def test_actual_orman1000_2_goals_2_assists_fails_release_without_mutation():
    original = real_source_derived_baseline()
    before = deepcopy(original)
    ready, reasons = judge(original, original)
    assert ready is False
    for problem in (
        "DISPUTED_ACTION_NOT_RECLASSIFIED_AS_ASSIST",
        "CANONICAL_COUNTS_NOT_1_GOAL_3_ASSISTS",
        "PUBLISHED_STATS_NOT_1_GOAL_3_ASSISTS",
        "SOURCE_SCOPED_WHITE_FINISHER_NOT_BOUND",
        "MATCH_ROOM_STILL_SAYS_OWN_GOAL",
        "REPORT_COMMENT_STILL_SAYS_OWN_GOAL",
        "INDEPENDENT_ROLE_REVIEW_PENDING",
    ):
        assert problem in reasons
    assert original == before


def test_explicit_synthetic_reviewer_path_demonstrates_full_atomic_consistency():
    original, candidate, review = hypothetical_review_only()
    original_copy = deepcopy(original)
    candidate_copy = deepcopy(candidate)
    assert judge(original, candidate, review) == (True, [])
    assert original == original_copy and candidate == candidate_copy
    assert [e["event_id"] for e in candidate["canonical_events"]["events"]] == [
        e["event_id"] for e in original["canonical_events"]["events"]
    ]
    assert all(a == b for a,b in zip(
        original["canonical_events"]["events"][:-1],
        candidate["canonical_events"]["events"][:-1]
    ) if a["event_id"] != FOLLOWUP_RUN)


def test_any_stale_field_foreign_source_or_unreviewed_white_finisher_blocks_release():
    original, perfect, role = hypothetical_review_only()
    candidates = []
    bad = deepcopy(perfect)
    bad["canonical_events"]["events"][0]["canonical_event_type"] = "GOAL"
    candidates.append((bad, role, "OTHER_CANONICAL_EVENT_CHANGED:"))
    bad = deepcopy(perfect)
    bad["full_report"]["verified_stats"]["counted_event_ids"]["goals"].append(TARGET)
    candidates.append((bad, role, "VERIFIED_EVENT_ID_COUNTS_MISMATCH:goals"))
    bad = deepcopy(perfect)
    bad["full_report"]["verified_stats"]["observed_counts"]["shots"] = 3
    candidates.append((bad, role, "VERIFIED_OBSERVED_COUNT_NOT_RECOMPUTED:shots"))
    bad = deepcopy(perfect)
    bad["full_report"]["action_timeline"][-1]["title"] = "Goal"
    candidates.append((bad, role, "ACTION_TIMELINE_STILL_SHOWS_GOAL"))
    bad = deepcopy(perfect)
    dep = next(e for e in bad["canonical_events"]["events"]
               if e["event_id"] == FOLLOWUP_RUN)
    dep["details"][0] = "P1 follows his shot toward goal."
    candidates.append((bad, role, "DEPENDENT_RUN_DESCRIPTION_NOT_SOURCE_NEUTRAL"))
    bad = deepcopy(perfect)
    bad["full_report"]["parent_value_metrics"]["top_minutes"][0]["why"] = "A second goal"
    candidates.append((bad, role, "PARENT_REPORT_STILL_CLAIMS_SECOND_GOAL"))
    bad = deepcopy(perfect)
    bad["full_report"]["match_stats"]["observed_assists"] = 2
    candidates.append((bad, role, "PUBLISHED_STATS_NOT_1_GOAL_3_ASSISTS"))
    bad = deepcopy(perfect)
    bad["full_report"]["action_timeline"][-1]["canonical_result"] = "SCORED"
    candidates.append((bad, role, "ACTION_TIMELINE_STILL_SHOWS_GOAL"))
    bad = deepcopy(perfect)
    bad["full_report"]["video_comments"][0]["match_room"]["receiver_visual_id"] = "p1"
    candidates.append((bad, role, "MATCH_ROOM_RECIPIENT_NOT_SAME_VERIFIED_PERSON"))
    bad = deepcopy(perfect)
    bad["full_report"]["video_comments"][0]["match_room"]["observation"] = "This is a selected-player goal"
    candidates.append((bad, role, "MATCH_ROOM_CAUSAL_NARRATIVE_STALE"))
    bad = deepcopy(perfect)
    bad["full_report"]["video_comments"][0]["match_room"]["action_type"] = "SHOT"
    candidates.append((bad, role, "MATCH_ROOM_STILL_SAYS_OWN_GOAL"))
    bad = deepcopy(perfect)
    bad["canonical_events"]["events"][-1]["proof"]["cited_frames"]["s000050648"] = 50647
    candidates.append((bad, role, "SOURCE_GOAL_OUTCOME_FRAMES_NOT_RETAINED"))
    bad = deepcopy(perfect)
    bad["canonical_events"]["events"][-1]["proof"]["source_video_sha256"] = "foreign"
    candidates.append((bad, role, "DISPUTED_PROOF_VIDEO_SHA_CHANGED"))
    bad = deepcopy(perfect)
    bad["canonical_events"]["source_video_sha256"] = "foreign"
    candidates.append((bad, role, "CANDIDATE_VIDEO_SHA_MISMATCH"))
    bad = deepcopy(perfect)
    selected = bad["canonical_events"]["events"][-1]["actor_visual_id"]
    bad["canonical_events"]["events"][-1]["causal_chain"].update(
        receiver_visual_id=selected, finisher_visual_id=selected
    )
    candidates.append((bad, role, "SOURCE_SCOPED_WHITE_FINISHER_NOT_BOUND"))
    bad = deepcopy(perfect)
    bad["canonical_events"]["events"][-1]["actor_visual_id"] = "foreign:selected:p2"
    candidates.append((bad, role, "SELECTED_PLAYER_IDENTITY_CHANGED"))
    bad = deepcopy(perfect)
    bad["canonical_events"]["events"][-1]["causal_chain"]["finisher_visual_id"] = "p3"
    candidates.append((bad, role, "SOURCE_SCOPED_WHITE_FINISHER_NOT_BOUND"))
    review = deepcopy(role)
    review["status"] = "PENDING"
    candidates.append((deepcopy(perfect), review, "INDEPENDENT_ROLE_REVIEW_PENDING"))
    for candidate, reviewed, required in candidates:
        ok, reasons = judge(original, candidate, reviewed)
        assert ok is False
        assert any(required in reason for reason in reasons), reasons
