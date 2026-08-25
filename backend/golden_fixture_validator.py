"""FIX10 real-video Golden Fixture validation.

This module compares a completed FIX10A physical result (and optionally the
normalised FIX09B sequence analysis) with an external fixture manifest.
Fixture truth is NEVER an input to reconstruction. Validation is deliberately
tri-state:

    PASS        evidence satisfies the assertion
    UNRESOLVED  required evidence is absent/insufficient
    FAIL        available evidence positively contradicts a hard assertion

A fixture can pass globally only when every required assertion is PASS. This
prevents missing goal geometry, jersey reads or contacts from producing a false
green acceptance result.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

VERSION = 1
PASS = "PASS"
UNRESOLVED = "UNRESOLVED"
FAIL = "FAIL"


def load_manifest(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != "FIX10_REAL_VIDEO_GOLDEN_V1":
        raise ValueError("INVALID_GOLDEN_FIXTURE_SCHEMA")
    if not isinstance(data.get("cases"), list) or not data["cases"]:
        raise ValueError("GOLDEN_FIXTURE_HAS_NO_CASES")
    return data


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_source_fingerprint(video_path: str | Path, manifest: dict) -> dict:
    expected = str(((manifest or {}).get("source") or {}).get("sha256") or "").lower()
    if not expected:
        return {"status": UNRESOLVED, "reason": "FIXTURE_SHA256_MISSING"}
    path = Path(video_path)
    if not path.exists() or not path.is_file():
        return {"status": UNRESOLVED, "reason": "REFERENCE_VIDEO_UNAVAILABLE"}
    actual = sha256_file(path).lower()
    return {
        "status": PASS if actual == expected else FAIL,
        "reason": "SOURCE_FINGERPRINT_MATCH" if actual == expected else "SOURCE_FINGERPRINT_MISMATCH",
        "expected_sha256": expected,
        "actual_sha256": actual,
    }


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _window(case: dict) -> tuple[int, int]:
    row = case.get("window_ms") if isinstance(case, dict) else None
    if not (isinstance(row, list) and len(row) == 2 and all(_num(x) for x in row)):
        raise ValueError("INVALID_CASE_WINDOW")
    a, b = int(row[0]), int(row[1])
    return min(a, b), max(a, b)


def _reference_range(case: dict, key: str, fallback: tuple[int, int]) -> tuple[int, int]:
    ranges = case.get("reference_ranges_ms") if isinstance(case, dict) else None
    row = ranges.get(key) if isinstance(ranges, dict) else None
    if isinstance(row, list) and len(row) == 2 and all(_num(x) for x in row):
        a, b = int(row[0]), int(row[1])
        return min(a, b), max(a, b)
    return fallback


def _trace_overlaps(trace: dict, start_ms: int, end_ms: int) -> bool:
    window = trace.get("window") if isinstance(trace, dict) else None
    if not isinstance(window, dict):
        return False
    a, b = window.get("start_ms"), window.get("end_ms")
    if not (_num(a) and _num(b)):
        return False
    lo, hi = sorted((int(a), int(b)))
    return not (hi < start_ms or lo > end_ms)


def _case_traces(physical_result: dict | None, case: dict) -> list[dict]:
    result = physical_result if isinstance(physical_result, dict) else {}
    start, end = _window(case)
    return [
        trace for trace in (result.get("traces") or [])
        if isinstance(trace, dict) and _trace_overlaps(trace, start, end)
    ]


def _all_touches(traces: list[dict], start_ms: int, end_ms: int) -> list[dict]:
    rows = []
    seen = set()
    for trace in traces:
        graph = trace.get("touch_graph") if isinstance(trace.get("touch_graph"), dict) else {}
        for touch in graph.get("touches") or []:
            if not isinstance(touch, dict) or not _num(touch.get("media_ms")):
                continue
            ms = int(touch["media_ms"])
            if not start_ms <= ms <= end_ms:
                continue
            key = touch.get("touch_id") or (ms, touch.get("player_track_id"))
            if key in seen:
                continue
            seen.add(key)
            rows.append(touch)
    return sorted(rows, key=lambda row: int(row["media_ms"]))


def _all_strikes(traces: list[dict], start_ms: int, end_ms: int) -> list[dict]:
    rows = []
    seen = set()
    for trace in traces:
        for strike in trace.get("strike_evidence") or []:
            if not isinstance(strike, dict) or not _num(strike.get("media_ms")):
                continue
            ms = int(strike["media_ms"])
            if not start_ms <= ms <= end_ms:
                continue
            key = strike.get("strike_id") or (ms, strike.get("player_track_id"))
            if key in seen:
                continue
            seen.add(key)
            rows.append(strike)
    return sorted(rows, key=lambda row: int(row["media_ms"]))


def _all_outcomes(traces: list[dict], start_ms: int, end_ms: int) -> list[dict]:
    rows = []
    seen = set()
    for trace in traces:
        for outcome in trace.get("outcome_evidence") or []:
            if not isinstance(outcome, dict) or not _num(outcome.get("media_ms")):
                continue
            ms = int(outcome["media_ms"])
            if not start_ms <= ms <= end_ms:
                continue
            key = outcome.get("strike_id") or (ms, outcome.get("physical_outcome"))
            if key in seen:
                continue
            seen.add(key)
            rows.append(outcome)
    return sorted(rows, key=lambda row: int(row["media_ms"]))


def _jersey_number(touch: dict) -> str | None:
    posterior = touch.get("jersey_posterior") if isinstance(touch, dict) else None
    if not isinstance(posterior, dict) or posterior.get("status") != "VERIFIED":
        return None
    value = posterior.get("number")
    return str(value) if value is not None else None


def _target_releases(strikes: list[dict], start_ms: int, end_ms: int) -> list[dict]:
    return [
        row for row in strikes
        if _num(row.get("media_ms"))
        and start_ms <= int(row["media_ms"]) <= end_ms
        and row.get("status") == "VERIFIED_PHYSICAL_RELEASE"
        and row.get("global_target_id") == "GLOBAL_TARGET"
    ]


def _assert_target_release(strikes: list[dict], start_ms: int, end_ms: int) -> dict:
    target = _target_releases(strikes, start_ms, end_ms)
    if target:
        return {
            "status": PASS,
            "reason": "VERIFIED_TARGET_RELEASE",
            "count": len(target),
            "media_ms": [int(x["media_ms"]) for x in target],
        }
    in_range = [
        row for row in strikes
        if _num(row.get("media_ms")) and start_ms <= int(row["media_ms"]) <= end_ms
    ]
    if in_range:
        return {"status": FAIL, "reason": "RELEASE_EXISTS_IN_REFERENCE_RANGE_BUT_NOT_BOUND_TO_TARGET", "count": len(in_range)}
    return {"status": UNRESOLVED, "reason": "NO_VERIFIED_TARGET_RELEASE_IN_REFERENCE_RANGE"}


def _assert_player_intervention(outcomes: list[dict], start_ms: int, end_ms: int) -> dict:
    verified = []
    for row in outcomes:
        intervention = row.get("intervention") if isinstance(row.get("intervention"), dict) else {}
        ms = intervention.get("media_ms")
        if intervention.get("status") == "VERIFIED" and _num(ms) and start_ms <= int(ms) <= end_ms:
            verified.append(row)
    if verified:
        return {"status": PASS, "reason": "VERIFIED_POST_STRIKE_PLAYER_INTERVENTION", "count": len(verified)}
    return {"status": UNRESOLVED, "reason": "PLAYER_INTERVENTION_NOT_PHYSICALLY_VERIFIED_IN_REFERENCE_RANGE"}


def _assert_required_outcome(outcomes: list[dict], expected: str) -> dict:
    observed = [str(row.get("physical_outcome") or "") for row in outcomes]
    if expected in observed:
        return {"status": PASS, "reason": f"PHYSICAL_OUTCOME_{expected}_VERIFIED"}
    positive = [x for x in observed if x and x not in {"UNRESOLVED", "UNRESOLVED_TERMINAL_VISIBILITY"}]
    if positive:
        return {"status": FAIL, "reason": "DIFFERENT_PHYSICAL_OUTCOME_VERIFIED", "observed": positive}
    return {"status": UNRESOLVED, "reason": f"REQUIRED_PHYSICAL_OUTCOME_{expected}_NOT_VERIFIED"}


def _assert_target_goal_plane_crossing(strikes: list[dict], outcomes: list[dict],
                                       start_ms: int, end_ms: int) -> dict:
    """Bind the goal-plane crossing to the target player's verified release.

    A goal crossing elsewhere in the same case window must never satisfy the
    target scorer assertion.  The physical chain is linked only through the
    immutable ``strike_id`` emitted from the target release.
    """
    target = _target_releases(strikes, start_ms, end_ms)
    target_ids = {
        row.get("strike_id") for row in target
        if isinstance(row.get("strike_id"), str) and row.get("strike_id")
    }
    goals = [
        row for row in outcomes
        if str(row.get("physical_outcome") or "") == "GOAL_PLANE_CROSSING"
    ]
    if not target:
        if goals:
            return {
                "status": FAIL,
                "reason": "GOAL_PLANE_CROSSING_EXISTS_WITHOUT_TARGET_RELEASE",
                "goal_strike_ids": [row.get("strike_id") for row in goals],
            }
        return {"status": UNRESOLVED, "reason": "TARGET_RELEASE_NOT_VERIFIED_FOR_GOAL_LINK"}
    if not target_ids:
        return {"status": UNRESOLVED, "reason": "TARGET_RELEASE_STRIKE_ID_MISSING"}

    linked = [row for row in goals if row.get("strike_id") in target_ids]
    foreign = [row for row in goals if row.get("strike_id") not in target_ids]
    if linked and foreign:
        return {
            "status": FAIL,
            "reason": "ADDITIONAL_GOAL_PLANE_CROSSING_LINKED_TO_DIFFERENT_STRIKE",
            "target_strike_ids": sorted(target_ids),
            "foreign_strike_ids": [row.get("strike_id") for row in foreign],
        }
    if linked:
        return {
            "status": PASS,
            "reason": "TARGET_RELEASE_LINKED_TO_GOAL_PLANE_CROSSING",
            "target_strike_ids": sorted(target_ids),
            "crossing_ms": [int(row["media_ms"]) for row in linked if _num(row.get("media_ms"))],
        }
    if goals:
        return {
            "status": FAIL,
            "reason": "GOAL_PLANE_CROSSING_LINKED_TO_DIFFERENT_STRIKE",
            "target_strike_ids": sorted(target_ids),
            "goal_strike_ids": [row.get("strike_id") for row in goals],
        }
    return {
        "status": UNRESOLVED,
        "reason": "TARGET_GOAL_PLANE_CROSSING_NOT_VERIFIED",
        "target_strike_ids": sorted(target_ids),
    }


def _fixture_goal_crossings(physical_result: dict | None) -> list[dict]:
    """Collect unique verified physical goal crossings across the whole video."""
    result = physical_result if isinstance(physical_result, dict) else {}
    goals, seen = [], set()
    for trace in result.get("traces") or []:
        if not isinstance(trace, dict):
            continue
        for outcome in trace.get("outcome_evidence") or []:
            if not isinstance(outcome, dict):
                continue
            if str(outcome.get("physical_outcome") or "") != "GOAL_PLANE_CROSSING":
                continue
            key = outcome.get("strike_id")
            if not isinstance(key, str) or not key:
                key = (outcome.get("media_ms"), "GOAL_PLANE_CROSSING")
            if key in seen:
                continue
            seen.add(key)
            goals.append(outcome)
    return goals


def _assert_exact_physical_goal_count(physical_result: dict | None, expected: int) -> dict:
    goals = _fixture_goal_crossings(physical_result)
    observed = len(goals)
    details = {
        "expected": int(expected),
        "observed": observed,
        "strike_ids": [row.get("strike_id") for row in goals],
        "media_ms": [int(row["media_ms"]) for row in goals if _num(row.get("media_ms"))],
    }
    if observed == int(expected):
        return {"status": PASS, "reason": "EXACT_PHYSICAL_GOAL_COUNT_VERIFIED", **details}
    if observed > int(expected):
        return {"status": FAIL, "reason": "EXTRA_PHYSICAL_GOAL_CROSSING_ASSERTED", **details}
    return {"status": UNRESOLVED, "reason": "REQUIRED_PHYSICAL_GOAL_COUNT_NOT_YET_VERIFIED", **details}


def _assert_forbidden_outcomes(outcomes: list[dict], forbidden) -> dict:
    blocked = {str(x) for x in (forbidden or []) if str(x)}
    observed = [str(row.get("physical_outcome") or "") for row in outcomes]
    bad = sorted(blocked.intersection(observed))
    return {
        "status": FAIL if bad else PASS,
        "reason": "FORBIDDEN_PHYSICAL_OUTCOME_ASSERTED" if bad else "NO_FORBIDDEN_PHYSICAL_OUTCOME_ASSERTED",
        "forbidden_seen": bad,
    }


def _assert_required_jersey_touch(touches: list[dict], jersey: str) -> dict:
    target = str(jersey)
    verified = [t for t in touches if t.get("status") == "VERIFIED"]
    matches = [t for t in verified if _jersey_number(t) == target and t.get("global_target_id") != "GLOBAL_TARGET"]
    if matches:
        return {"status": PASS, "reason": "VERIFIED_NON_TARGET_JERSEY_TOUCH", "jersey": target, "count": len(matches)}
    any_verified_jersey = [(_jersey_number(t), t) for t in verified if _jersey_number(t) is not None]
    if any_verified_jersey:
        return {
            "status": FAIL,
            "reason": "VERIFIED_JERSEY_TOUCHES_EXIST_BUT_REQUIRED_JERSEY_ABSENT",
            "jersey": target,
            "observed_jerseys": sorted({j for j, _ in any_verified_jersey}),
        }
    return {"status": UNRESOLVED, "reason": "NON_TARGET_JERSEY_TOUCH_NOT_RESOLVED", "jersey": target}


def _assert_ordered_jersey_touch(touches: list[dict], strikes: list[dict], jersey: str,
                                 decisive_start_ms: int, decisive_end_ms: int,
                                 case_start_ms: int, case_end_ms: int) -> dict:
    releases = _target_releases(strikes, case_start_ms, case_end_ms)
    if not releases:
        return {"status": UNRESOLVED, "reason": "TARGET_RELEASE_NOT_VERIFIED_FOR_ORDERED_CHAIN", "jersey": str(jersey)}
    first_release_ms = min(int(row["media_ms"]) for row in releases)
    verified = [
        touch for touch in touches
        if touch.get("status") == "VERIFIED"
        and _num(touch.get("media_ms"))
        and max(first_release_ms + 1, decisive_start_ms) <= int(touch["media_ms"]) <= decisive_end_ms
        and touch.get("global_target_id") != "GLOBAL_TARGET"
    ]
    matches = [touch for touch in verified if _jersey_number(touch) == str(jersey)]
    if matches:
        return {
            "status": PASS,
            "reason": "ORDERED_TARGET_RELEASE_TO_VERIFIED_JERSEY_TOUCH",
            "jersey": str(jersey),
            "target_release_ms": first_release_ms,
            "touch_ms": [int(t["media_ms"]) for t in matches],
        }
    resolved = [(_jersey_number(t), int(t["media_ms"])) for t in verified if _jersey_number(t) is not None]
    if resolved:
        return {
            "status": FAIL,
            "reason": "ORDERED_DECISIVE_TOUCH_RESOLVED_TO_DIFFERENT_JERSEY",
            "jersey": str(jersey),
            "target_release_ms": first_release_ms,
            "observed": resolved,
        }
    return {
        "status": UNRESOLVED,
        "reason": "ORDERED_DECISIVE_JERSEY_TOUCH_NOT_RESOLVED",
        "jersey": str(jersey),
        "target_release_ms": first_release_ms,
    }


def _assert_ordered_jersey_strike(touches: list[dict], strikes: list[dict], jersey: str,
                                  decisive_start_ms: int, decisive_end_ms: int,
                                  case_start_ms: int, case_end_ms: int) -> dict:
    """Require the required jersey touch itself to own a later physical strike."""
    releases = _target_releases(strikes, case_start_ms, case_end_ms)
    if not releases:
        return {"status": UNRESOLVED, "reason": "TARGET_RELEASE_NOT_VERIFIED_FOR_SCORER_CHAIN", "jersey": str(jersey)}
    first_release_ms = min(int(row["media_ms"]) for row in releases)
    touch_by_id = {
        t.get("touch_id"): t for t in touches
        if isinstance(t.get("touch_id"), str) and t.get("status") == "VERIFIED"
    }
    candidate_strikes = []
    for strike in strikes:
        if strike.get("status") != "VERIFIED_PHYSICAL_RELEASE" or strike.get("global_target_id") == "GLOBAL_TARGET":
            continue
        if not _num(strike.get("media_ms")):
            continue
        ms = int(strike["media_ms"])
        if not max(first_release_ms + 1, decisive_start_ms) <= ms <= decisive_end_ms:
            continue
        touch = touch_by_id.get(strike.get("touch_id"))
        if not isinstance(touch, dict) or touch.get("global_target_id") == "GLOBAL_TARGET":
            continue
        candidate_strikes.append((strike, touch))
    matches = [
        (strike, touch) for strike, touch in candidate_strikes
        if _jersey_number(touch) == str(jersey)
    ]
    if matches:
        return {
            "status": PASS,
            "reason": "ORDERED_TARGET_RELEASE_TO_VERIFIED_JERSEY_STRIKE",
            "jersey": str(jersey),
            "target_release_ms": first_release_ms,
            "strike_ms": [int(strike["media_ms"]) for strike, _ in matches],
            "touch_ids": [touch.get("touch_id") for _, touch in matches],
        }
    resolved = [
        (_jersey_number(touch), int(strike["media_ms"]))
        for strike, touch in candidate_strikes if _jersey_number(touch) is not None
    ]
    if resolved:
        return {
            "status": FAIL,
            "reason": "DECISIVE_PHYSICAL_STRIKE_RESOLVED_TO_DIFFERENT_JERSEY",
            "jersey": str(jersey),
            "target_release_ms": first_release_ms,
            "observed": resolved,
        }
    return {
        "status": UNRESOLVED,
        "reason": "DECISIVE_JERSEY_STRIKE_NOT_RESOLVED",
        "jersey": str(jersey),
        "target_release_ms": first_release_ms,
    }


def _assert_forbidden_jersey_touch(touches: list[dict], jersey: str,
                                   start_ms: int, end_ms: int) -> dict:
    target = str(jersey)
    bad = [
        t for t in touches
        if t.get("status") == "VERIFIED"
        and _num(t.get("media_ms")) and start_ms <= int(t["media_ms"]) <= end_ms
        and t.get("global_target_id") != "GLOBAL_TARGET"
        and _jersey_number(t) == target
    ]
    if bad:
        return {"status": FAIL, "reason": "FORBIDDEN_VERIFIED_JERSEY_TOUCH", "jersey": target, "count": len(bad)}
    return {"status": PASS, "reason": "NO_FORBIDDEN_VERIFIED_JERSEY_TOUCH", "jersey": target}


def _primary_actions(sequence_analysis: dict | None, start_ms: int, end_ms: int) -> list[dict]:
    analysis = sequence_analysis if isinstance(sequence_analysis, dict) else {}
    rows = []
    for seq in analysis.get("sequences") or []:
        if not isinstance(seq, dict):
            continue
        for action in seq.get("actions") or []:
            if not isinstance(action, dict) or not _num(action.get("start_ms")):
                continue
            a0 = int(action["start_ms"])
            a1 = int(action.get("end_ms") or a0)
            if a1 < start_ms or a0 > end_ms:
                continue
            rows.append(action)
    return rows


def _assert_perception_kinds(actions: list[dict], kinds) -> dict:
    expected = {str(x).upper() for x in (kinds or []) if str(x)}
    observed = {str(a.get("kind") or "").upper() for a in actions}
    missing = sorted(expected - observed)
    return {
        "status": PASS if not missing else UNRESOLVED,
        "reason": "REQUIRED_PERCEPTION_KINDS_PRESENT" if not missing else "REQUIRED_PERCEPTION_KINDS_MISSING",
        "missing": missing,
        "observed": sorted(x for x in observed if x),
    }


def _assert_shot_foot(actions: list[dict], foot: str) -> dict:
    shots = [a for a in actions if str(a.get("kind") or "").upper() == "SHOT"]
    if any(str(a.get("foot") or "").upper() == str(foot).upper() for a in shots):
        return {"status": PASS, "reason": "SHOT_FOOT_MATCH", "foot": str(foot).upper()}
    visible_other = [
        str(a.get("foot") or "").upper() for a in shots
        if str(a.get("foot") or "").upper() in {"LEFT", "RIGHT", "BOTH"}
    ]
    if visible_other:
        return {"status": FAIL, "reason": "SHOT_FOOT_CONTRADICTION", "expected": str(foot).upper(), "observed": visible_other}
    return {"status": UNRESOLVED, "reason": "SHOT_FOOT_NOT_RESOLVED", "expected": str(foot).upper()}


def validate_case(case: dict, physical_result: dict | None,
                  sequence_analysis: dict | None = None) -> dict:
    start, end = _window(case)
    traces = _case_traces(physical_result, case)
    if not traces:
        return {
            "case_id": case.get("case_id"),
            "status": UNRESOLVED,
            "reason": "NO_PHYSICAL_TRACE_OVERLAPS_CASE",
            "assertions": [],
        }
    touches = _all_touches(traces, start, end)
    strikes = _all_strikes(traces, start, end)
    outcomes = _all_outcomes(traces, start, end)
    assertions = []
    gate = case.get("physical_gate") if isinstance(case.get("physical_gate"), dict) else {}

    strike_start, strike_end = _reference_range(case, "target_strike", (start, end))
    intervention_start, intervention_end = _reference_range(case, "intervention", (start, end))
    decisive_start, decisive_end = _reference_range(case, "decisive_teammate_touch", (start, end))

    if gate.get("require_target_release") is True:
        assertions.append({
            "name": "require_target_release",
            **_assert_target_release(strikes, strike_start, strike_end),
        })
    if gate.get("require_player_intervention") is True:
        assertions.append({
            "name": "require_player_intervention",
            **_assert_player_intervention(outcomes, intervention_start, intervention_end),
        })
    if gate.get("require_physical_outcome"):
        assertions.append({
            "name": "require_physical_outcome",
            **_assert_required_outcome(outcomes, str(gate["require_physical_outcome"])),
        })
    if gate.get("require_goal_plane_crossing") is True:
        assertions.append({"name": "require_goal_plane_crossing", **_assert_required_outcome(outcomes, "GOAL_PLANE_CROSSING")})
    if gate.get("require_target_goal_plane_crossing") is True:
        assertions.append({
            "name": "require_target_goal_plane_crossing",
            **_assert_target_goal_plane_crossing(strikes, outcomes, strike_start, strike_end),
        })
    if gate.get("must_not_assert_physical_outcome"):
        assertions.append({
            "name": "must_not_assert_physical_outcome",
            **_assert_forbidden_outcomes(outcomes, gate.get("must_not_assert_physical_outcome")),
        })
    if gate.get("require_non_target_verified_jersey_touch") is not None:
        assertions.append({
            "name": "require_non_target_verified_jersey_touch",
            **_assert_required_jersey_touch(touches, str(gate["require_non_target_verified_jersey_touch"])),
        })
    if gate.get("require_non_target_verified_jersey_touch_after_target_release") is not None:
        assertions.append({
            "name": "require_non_target_verified_jersey_touch_after_target_release",
            **_assert_ordered_jersey_touch(
                touches,
                strikes,
                str(gate["require_non_target_verified_jersey_touch_after_target_release"]),
                decisive_start,
                decisive_end,
                start,
                end,
            ),
        })
    if gate.get("require_non_target_verified_jersey_strike_after_target_release") is not None:
        assertions.append({
            "name": "require_non_target_verified_jersey_strike_after_target_release",
            **_assert_ordered_jersey_strike(
                touches,
                strikes,
                str(gate["require_non_target_verified_jersey_strike_after_target_release"]),
                decisive_start,
                decisive_end,
                start,
                end,
            ),
        })
    if gate.get("forbid_non_target_verified_jersey_touch") is not None:
        assertions.append({
            "name": "forbid_non_target_verified_jersey_touch",
            **_assert_forbidden_jersey_touch(
                touches,
                str(gate["forbid_non_target_verified_jersey_touch"]),
                decisive_start,
                decisive_end,
            ),
        })

    perception = case.get("perception_gate") if isinstance(case.get("perception_gate"), dict) else {}
    actions = _primary_actions(sequence_analysis, start, end)
    if perception.get("require_kinds"):
        assertions.append({"name": "require_perception_kinds", **_assert_perception_kinds(actions, perception["require_kinds"])})
    if perception.get("require_shot_foot"):
        assertions.append({"name": "require_shot_foot", **_assert_shot_foot(actions, perception["require_shot_foot"])})

    statuses = [a["status"] for a in assertions]
    status = FAIL if FAIL in statuses else UNRESOLVED if UNRESOLVED in statuses else PASS
    return {
        "case_id": case.get("case_id"),
        "status": status,
        "reason": "ASSERTION_FAILURE" if status == FAIL else "INSUFFICIENT_EVIDENCE" if status == UNRESOLVED else "ALL_REQUIRED_ASSERTIONS_PASS",
        "assertions": assertions,
        "trace_count": len(traces),
        "touch_count": len(touches),
        "strike_count": len(strikes),
        "outcome_count": len(outcomes),
    }


def validate_fixture(manifest: dict, physical_result: dict | None,
                     sequence_analysis: dict | None = None) -> dict:
    cases = [
        validate_case(case, physical_result, sequence_analysis)
        for case in (manifest.get("cases") or []) if isinstance(case, dict)
    ]
    case_statuses = [case["status"] for case in cases]
    fixture_assertions = []
    video_gate = manifest.get("video_gate") if isinstance(manifest.get("video_gate"), dict) else {}
    expected_goals = video_gate.get("require_exact_physical_goal_count")
    if isinstance(expected_goals, int) and not isinstance(expected_goals, bool) and expected_goals >= 0:
        fixture_assertions.append({
            "name": "require_exact_physical_goal_count",
            **_assert_exact_physical_goal_count(physical_result, expected_goals),
        })
    statuses = case_statuses + [row["status"] for row in fixture_assertions]
    status = FAIL if FAIL in statuses else UNRESOLVED if UNRESOLVED in statuses else PASS
    return {
        "version": VERSION,
        "fixture_id": manifest.get("fixture_id"),
        "status": status,
        "cases": cases,
        "fixture_assertions": fixture_assertions,
        "metrics": {
            "cases": len(cases),
            "passed": sum(x == PASS for x in case_statuses),
            "unresolved": sum(x == UNRESOLVED for x in case_statuses),
            "failed": sum(x == FAIL for x in case_statuses),
        },
    }

# FIX10A_TARGET_GOAL_LINK_V2
# Final fail-closed Golden enforcement. Physical reconstruction remains
# non-canonical; this only validates that a goal crossing belongs to the
# target player's own verified release and that the fixture contains the
# exact number of physically verified goals declared by its hard gates.
_validate_case_before_target_goal_link = validate_case


def _target_goal_link_v2(case: dict, physical_result: dict | None) -> dict:
    start, end = _window(case)
    traces = _case_traces(physical_result, case)
    strikes = _all_strikes(traces, start, end)
    outcomes = _all_outcomes(traces, start, end)
    strike_start, strike_end = _reference_range(case, "target_strike", (start, end))
    target_releases = _target_releases(strikes, strike_start, strike_end)
    if not target_releases:
        return {"status": UNRESOLVED, "reason": "TARGET_RELEASE_NOT_VERIFIED_FOR_GOAL_CHAIN"}
    target_ids = {
        str(row.get("strike_id")) for row in target_releases
        if isinstance(row.get("strike_id"), str) and row.get("strike_id")
    }
    goals = [row for row in outcomes if row.get("physical_outcome") == "GOAL_PLANE_CROSSING"]
    linked = [row for row in goals if str(row.get("strike_id") or "") in target_ids]
    if linked:
        return {
            "status": PASS,
            "reason": "TARGET_RELEASE_LINKED_TO_GOAL_PLANE_CROSSING",
            "target_strike_ids": sorted(target_ids),
            "crossing_ms": [int(row["media_ms"]) for row in linked if _num(row.get("media_ms"))],
        }
    if goals:
        return {
            "status": FAIL,
            "reason": "GOAL_PLANE_CROSSING_LINKED_TO_DIFFERENT_STRIKE",
            "target_strike_ids": sorted(target_ids),
            "observed_strike_ids": sorted({str(row.get("strike_id") or "") for row in goals}),
        }
    return {
        "status": UNRESOLVED,
        "reason": "TARGET_GOAL_PLANE_CROSSING_NOT_VERIFIED",
        "target_strike_ids": sorted(target_ids),
    }


def validate_case(case: dict, physical_result: dict | None,
                  sequence_analysis: dict | None = None) -> dict:
    result = _validate_case_before_target_goal_link(case, physical_result, sequence_analysis)
    gate = case.get("physical_gate") if isinstance(case.get("physical_gate"), dict) else {}
    if gate.get("require_goal_plane_crossing") is not True:
        return result
    assertions = [
        row for row in (result.get("assertions") or [])
        if isinstance(row, dict)
        and row.get("name") not in {"require_goal_plane_crossing", "require_target_goal_plane_crossing"}
    ]
    assertions.append({
        "name": "require_target_goal_plane_crossing",
        **_target_goal_link_v2(case, physical_result),
    })
    statuses = [row.get("status") for row in assertions]
    status = FAIL if FAIL in statuses else UNRESOLVED if UNRESOLVED in statuses else PASS
    result["assertions"] = assertions
    result["status"] = status
    result["reason"] = (
        "ASSERTION_FAILURE" if status == FAIL
        else "INSUFFICIENT_EVIDENCE" if status == UNRESOLVED
        else "ALL_REQUIRED_ASSERTIONS_PASS"
    )
    return result


_validate_fixture_before_exact_goal_count = validate_fixture


def _exact_physical_goal_count_v2(manifest: dict, physical_result: dict | None) -> dict:
    expected = sum(
        1 for case in (manifest.get("cases") or [])
        if isinstance(case, dict)
        and isinstance(case.get("physical_gate"), dict)
        and case["physical_gate"].get("require_goal_plane_crossing") is True
    )
    result = physical_result if isinstance(physical_result, dict) else {}
    seen = set()
    goals = []
    for trace in result.get("traces") or []:
        if not isinstance(trace, dict):
            continue
        for outcome in trace.get("outcome_evidence") or []:
            if not isinstance(outcome, dict) or outcome.get("physical_outcome") != "GOAL_PLANE_CROSSING":
                continue
            key = (
                str(outcome.get("strike_id") or ""),
                int(outcome["media_ms"]) if _num(outcome.get("media_ms")) else None,
            )
            if key in seen:
                continue
            seen.add(key)
            goals.append(outcome)
    observed = len(goals)
    if observed > expected:
        status, reason = FAIL, "EXTRA_PHYSICAL_GOAL_CROSSING_ASSERTED"
    elif observed < expected:
        status, reason = UNRESOLVED, "REQUIRED_PHYSICAL_GOAL_CROSSING_NOT_VERIFIED"
    else:
        status, reason = PASS, "EXACT_PHYSICAL_GOAL_COUNT_MATCH"
    return {
        "status": status,
        "reason": reason,
        "expected": expected,
        "observed": observed,
        "strike_ids": [str(row.get("strike_id") or "") for row in goals],
    }


def validate_fixture(manifest: dict, physical_result: dict | None,
                     sequence_analysis: dict | None = None) -> dict:
    result = _validate_fixture_before_exact_goal_count(manifest, physical_result, sequence_analysis)
    fixture_assertions = [{
        "name": "require_exact_physical_goal_count",
        **_exact_physical_goal_count_v2(manifest, physical_result),
    }]
    result["fixture_assertions"] = fixture_assertions
    statuses = [row.get("status") for row in (result.get("cases") or [])] + [
        row.get("status") for row in fixture_assertions
    ]
    result["status"] = FAIL if FAIL in statuses else UNRESOLVED if UNRESOLVED in statuses else PASS
    return result

# FIX10A_GOAL_STABILIZATION_LEGACY_ASSERTION_ALIAS
# Compatibility only: when the goal case has no physical outcomes at all,
# preserve the historical missing-crossing assertion name as an exact alias
# of the stricter target-linked verdict. Once any outcome exists, the
# target-linked assertion is the sole goal-crossing authority so an
# unrelated PLAYER_INTERVENTION cannot recreate the old unlinked failure.
_validate_case_before_strict_goal_alias = validate_case

def _case_has_any_physical_outcome(case: dict, physical_result: dict | None) -> bool:
    window = case.get("window_ms") if isinstance(case.get("window_ms"), list) else None
    start = int(window[0]) if window and len(window) == 2 else None
    end = int(window[1]) if window and len(window) == 2 else None
    for trace in ((physical_result or {}).get("traces") or []):
        if not isinstance(trace, dict):
            continue
        tw = trace.get("window") if isinstance(trace.get("window"), dict) else {}
        ts, te = tw.get("start_ms"), tw.get("end_ms")
        if start is not None and end is not None and isinstance(ts, (int, float)) and isinstance(te, (int, float)):
            if int(te) < start or int(ts) > end:
                continue
        if any(isinstance(row, dict) for row in (trace.get("outcome_evidence") or [])):
            return True
    return False

def validate_case(case: dict, physical_result: dict | None,
                  sequence_analysis: dict | None = None) -> dict:
    result = _validate_case_before_strict_goal_alias(case, physical_result, sequence_analysis)
    gate = case.get("physical_gate") if isinstance(case.get("physical_gate"), dict) else {}
    if gate.get("require_goal_plane_crossing") is not True:
        return result
    assertions = [row for row in (result.get("assertions") or []) if isinstance(row, dict)]
    strict = next((row for row in assertions if row.get("name") == "require_target_goal_plane_crossing"), None)
    if strict is None:
        return result
    assertions = [row for row in assertions if row.get("name") != "require_goal_plane_crossing"]
    if not _case_has_any_physical_outcome(case, physical_result):
        alias = dict(strict)
        alias["name"] = "require_goal_plane_crossing"
        assertions.append(alias)
    statuses = [row.get("status") for row in assertions]
    status = FAIL if FAIL in statuses else UNRESOLVED if UNRESOLVED in statuses else PASS
    result["assertions"] = assertions
    result["status"] = status
    result["reason"] = (
        "ASSERTION_FAILURE" if status == FAIL
        else "INSUFFICIENT_EVIDENCE" if status == UNRESOLVED
        else "ALL_REQUIRED_ASSERTIONS_PASS"
    )
    return result
