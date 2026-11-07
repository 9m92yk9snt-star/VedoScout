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

FIXTURE = (Path(__file__).resolve().parents[2] /
           "testdata/matchroom-completion/orman1000-real-21-event-review-fixture.json")


def real_source_derived_baseline():
    raw = json.loads(FIXTURE.read_text())
    assert raw["video_source_sha256"] == SOURCE
    action = deepcopy(raw["disputed_original"])
    actions = [*deepcopy(raw["other_20_events"]), action]
    report = {
        "canonical_events": {"source_video_sha256": SOURCE, "events": actions},
        "full_report": {
            "match_stats": {"observed_goals": 2, "observed_assists": 2},
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
    # Synthetic role proof ONLY; this is not a real source identity assigned.
    tested_role = "synthetic-current-source-white-finisher"
    action["causal_chain"].update(
        receiver_visual_id=tested_role, finisher_visual_id=tested_role
    )
    candidate["full_report"]["match_stats"].update(
        observed_goals=1, observed_assists=3
    )
    card = candidate["full_report"]["video_comments"][0]
    card["comment"] = "Synthetic reviewed assist, not a live report."
    card["match_room"].update(action_type="PASS", action_outcome="TEAMMATE_GOAL")
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
    assert all(a == b for a, b in zip(
        original["canonical_events"]["events"][:-1],
        candidate["canonical_events"]["events"][:-1]
    ))


def test_any_stale_field_foreign_source_or_unreviewed_white_finisher_blocks_release():
    original, perfect, role = hypothetical_review_only()
    candidates = []
    bad = deepcopy(perfect)
    bad["canonical_events"]["events"][0]["canonical_event_type"] = "GOAL"
    candidates.append((bad, role, "OTHER_CANONICAL_EVENT_CHANGED:"))
    bad = deepcopy(perfect)
    bad["full_report"]["match_stats"]["observed_assists"] = 2
    candidates.append((bad, role, "PUBLISHED_STATS_NOT_1_GOAL_3_ASSISTS"))
    bad = deepcopy(perfect)
    bad["full_report"]["video_comments"][0]["match_room"]["action_type"] = "SHOT"
    candidates.append((bad, role, "MATCH_ROOM_STILL_SAYS_OWN_GOAL"))
    bad = deepcopy(perfect)
    bad["canonical_events"]["source_video_sha256"] = "foreign"
    candidates.append((bad, role, "CANDIDATE_VIDEO_SHA_MISMATCH"))
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
