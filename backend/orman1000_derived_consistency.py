"""Pure, read-only consistency checks for one reviewed Orman1000 assist correction.

Other event findings retain their provenance; only the disputed own-goal and
its directly dependent follow-up running description may change. Do not use
this module to infer who kicked a hidden ball or to auto-approve an assist.
"""

import copy
import re

TARGET = "47ad617d2ba76a4683cd"
FOLLOWUP_RUN = "baa4a5cfb76333175f55"
NEUTRAL_RUN = (
    "P1 continues his run toward goal. "
    "No additional p1 ball contact is visible before the camera pans away."
)
STAT_DELTAS = {
    "goals": -1,
    "assists": 1,
    "shots": -1,
    "shots_on_target": -1,
    "passes_attempted": 1,
    "passes_completed": 1,
    "key_passes": 1,
}
REMOVE_IDS = ("goals", "shots", "shots_on_target")
ADD_IDS = ("assists", "passes_attempted", "passes_completed", "key_passes")


def _stable(v):
    import json
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def check_consistency(original, candidate):
    """Return list of precise fail-closed blockers. Neither input is modified."""
    errors = []
    old_bundle = original.get("canonical_events") or {}
    new_bundle = candidate.get("canonical_events") or {}
    old_events = old_bundle.get("events") or []
    new_events = new_bundle.get("events") or []
    old_by_id = {e.get("event_id"): e for e in old_events}
    new_by_id = {e.get("event_id"): e for e in new_events}
    if (len(old_events) != len(new_events) or
            [e.get("event_id") for e in old_events] !=
            [e.get("event_id") for e in new_events] or
            len(old_by_id) != len(old_events)):
        return ["SOURCE_CANONICAL_EVENT_ORDER_OR_ID_CHANGED"]
    for eid, earlier in old_by_id.items():
        if eid in (TARGET, FOLLOWUP_RUN):
            continue
        if _stable(earlier) != _stable(new_by_id[eid]):
            errors.append("UNRELATED_CANONICAL_EVENT_CHANGED:" + str(eid))

    # The run is the SAME event and the SAME source, not an extra goal.
    run_old, run_new = old_by_id.get(FOLLOWUP_RUN), new_by_id.get(FOLLOWUP_RUN)
    if not isinstance(run_old, dict) or not isinstance(run_new, dict):
        errors.append("DEPENDENT_RUN_EVENT_MISSING")
    elif _stable(run_old) != _stable(run_new):
        preserved = copy.deepcopy(run_new)
        preserved["details"] = copy.deepcopy(run_old.get("details"))
        if _stable(preserved) != _stable(run_old):
            errors.append("DEPENDENT_RUN_FACTS_CHANGED")
        if (run_old.get("details") != [
                "P1 follows his shot toward goal. No additional p1 ball contact "
                "is visible before the camera pans away."
            ] or run_new.get("details") != [NEUTRAL_RUN]):
            errors.append("DEPENDENT_RUN_DESCRIPTION_NOT_SOURCE_NEUTRAL")
    elif "his shot" in _stable(run_new.get("details", [])).lower():
        errors.append("DEPENDENT_RUN_STILL_SAYS_OWN_SHOT")

    old_full = original.get("full_report") or {}
    new_full = candidate.get("full_report") or {}
    old_stats = old_full.get("match_stats") or {}
    new_stats = new_full.get("match_stats") or {}
    old_verified = old_full.get("verified_stats") or {}
    new_verified = new_full.get("verified_stats") or {}
    old_counts = old_verified.get("observed_counts") or {}
    new_counts = new_verified.get("observed_counts") or {}

    # Observed count and total availability are different concepts; retain
    # the original partial-coverage status and null season-level totals.
    for k, delta in STAT_DELTAS.items():
        expected = old_counts.get(k)
        if type(expected) is not int or new_counts.get(k) != expected + delta:
            errors.append("VERIFIED_OBSERVED_COUNT_NOT_RECOMPUTED:" + k)
        expected_match = old_stats.get(
            "observed_goals" if k == "goals" else
            "observed_assists" if k == "assists" else k
        )
        actual_match = new_stats.get(
            "observed_goals" if k == "goals" else
            "observed_assists" if k == "assists" else k
        )
        if type(expected_match) is not int or actual_match != expected_match + delta:
            errors.append("MATCH_STATS_COUNT_NOT_RECOMPUTED:" + k)
    for field in ("coverage_status", "goals_assists_available",
                  "goals", "assists", "available"):
        if new_verified.get(field) != old_verified.get(field):
            errors.append("UNVERIFIED_TOTAL_OR_COVERAGE_CHANGED:" + field)
    if new_stats.get("coverage_status") != old_stats.get("coverage_status"):
        errors.append("MATCH_STATS_COVERAGE_CHANGED")

    counted_old = old_verified.get("counted_event_ids") or {}
    counted_new = new_verified.get("counted_event_ids") or {}
    for field in (*REMOVE_IDS, *ADD_IDS):
        before = counted_old.get(field)
        after = counted_new.get(field)
        if not isinstance(before, list) or not isinstance(after, list):
            errors.append("MISSING_EVENT_COUNT_PROVENANCE:" + field)
            continue
        expected = [eid for eid in before if eid != TARGET]
        if field in ADD_IDS:
            if TARGET in before:
                errors.append("PREVIOUS_EVENT_ALREADY_COUNTED:" + field)
            expected.append(TARGET)
        else:
            if before.count(TARGET) != 1:
                errors.append("DISPUTED_SHOT_NOT_IN_ORIGINAL_COUNTED_EVENTS:" + field)
        if len(set(after)) != len(after) or set(after) != set(expected):
            errors.append("VERIFIED_EVENT_ID_COUNTS_MISMATCH:" + field)
    for key, before in counted_old.items():
        if key not in (*REMOVE_IDS, *ADD_IDS) and _stable(counted_new.get(key)) != _stable(before):
            errors.append("UNRELATED_VERIFIED_EVENT_LIST_CHANGED:" + key)
    if new_verified.get("scoring_scan") != old_verified.get("scoring_scan"):
        errors.append("UNVERIFIED_SCORING_SCAN_MODIFIED")

    old_timeline = old_full.get("action_timeline")
    new_timeline = new_full.get("action_timeline")
    if not isinstance(old_timeline, list) or not isinstance(new_timeline, list):
        errors.append("ACTION_TIMELINE_REQUIRED")
    elif ([r.get("event_id") for r in old_timeline] !=
          [r.get("event_id") for r in new_timeline]):
        errors.append("ACTION_TIMELINE_EVENT_ORDER_CHANGED")
    else:
        old_timeline_by_id = {r.get("event_id"):r for r in old_timeline}
        new_timeline_by_id = {r.get("event_id"):r for r in new_timeline}
        for eid, before in old_timeline_by_id.items():
            after = new_timeline_by_id[eid]
            if eid in (TARGET, FOLLOWUP_RUN):
                continue
            if _stable(before) != _stable(after):
                errors.append("UNRELATED_ACTION_TIMELINE_CHANGED:" + str(eid))
        affected = new_timeline_by_id.get(TARGET) or {}
        if (affected.get("canonical_action_type"),
                affected.get("canonical_event_type"),
                affected.get("football_action_type"),
                affected.get("football_event_type"),
                affected.get("football_outcome"),
                affected.get("canonical_result"),
                affected.get("title"),
                affected.get("action_type")) != (
                "PASS", "ASSIST", "PASS", "ASSIST",
                "TEAMMATE_GOAL", "TEAMMATE_SCORED", "Assist", "pass"):
            errors.append("ACTION_TIMELINE_STILL_SHOWS_GOAL")
        if affected.get("causal_chain") != (new_by_id.get(TARGET) or {}).get("causal_chain"):
            errors.append("ACTION_TIMELINE_CAUSAL_CHAIN_STALE")
        if not isinstance(affected.get("football_details"), list) or not affected["football_details"]:
            errors.append("ACTION_TIMELINE_ASSIST_EVIDENCE_TEXT_MISSING")
        if any(word in _stable(affected).lower() for word in (
                "not a direct assist", "no teammate receives and shoots",
                "this is a selected-player goal")):
            errors.append("ACTION_TIMELINE_OWN_GOAL_NARRATIVE_STALE")
        followup = new_timeline_by_id.get(FOLLOWUP_RUN) or {}
        old_followup = old_timeline_by_id.get(FOLLOWUP_RUN) or {}
        original_neutral = copy.deepcopy(followup)
        original_neutral["football_details"] = copy.deepcopy(old_followup.get("football_details"))
        if _stable(original_neutral) != _stable(old_followup):
            errors.append("DEPENDENT_RUN_TIMELINE_FACTS_CHANGED")
        if followup.get("football_details") != [NEUTRAL_RUN]:
            errors.append("DEPENDENT_RUN_TIMELINE_STILL_OWN_SHOT")

    new_metrics = new_full.get("parent_value_metrics") or {}
    top = new_metrics.get("top_minutes") or []
    if any(re.search(r"\b(second goal|two goals|2 goals)\b", str(row.get("why","")), re.I)
           for row in top if isinstance(row, dict)):
        errors.append("PARENT_REPORT_STILL_CLAIMS_SECOND_GOAL")
    return errors
