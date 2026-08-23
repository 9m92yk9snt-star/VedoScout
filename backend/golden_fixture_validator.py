"""FIX10 real-video Golden Fixture validation.

This module compares a completed FIX10A physical result (and optionally the
normalised FIX09B sequence analysis) with an external fixture manifest.
Fixture truth is NEVER an input to reconstruction.  Validation is deliberately
tri-state:

    PASS        evidence satisfies the assertion
    UNRESOLVED  required evidence is absent/insufficient
    FAIL        available evidence positively contradicts a hard assertion

A fixture can pass globally only when every required assertion is PASS.  This
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
    return rows


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
    return rows


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
    return rows


def _jersey_number(touch: dict) -> str | None:
    posterior = touch.get("jersey_posterior") if isinstance(touch, dict) else None
    if not isinstance(posterior, dict) or posterior.get("status") != "VERIFIED":
        return None
    value = posterior.get("number")
    return str(value) if value is not None else None


def _assert_target_release(strikes: list[dict]) -> dict:
    target = [
        row for row in strikes
        if row.get("status") == "VERIFIED_PHYSICAL_RELEASE"
        and row.get("global_target_id") == "GLOBAL_TARGET"
    ]
    if target:
        return {"status": PASS, "reason": "VERIFIED_TARGET_RELEASE", "count": len(target)}
    if strikes:
        return {"status": FAIL, "reason": "RELEASE_EXISTS_BUT_NOT_BOUND_TO_TARGET", "count": len(strikes)}
    return {"status": UNRESOLVED, "reason": "NO_VERIFIED_PHYSICAL_RELEASE"}


def _assert_player_intervention(outcomes: list[dict]) -> dict:
    verified = [
        row for row in outcomes
        if isinstance(row.get("intervention"), dict)
        and row["intervention"].get("status") == "VERIFIED"
    ]
    if verified:
        return {"status": PASS, "reason": "VERIFIED_POST_STRIKE_PLAYER_INTERVENTION", "count": len(verified)}
    return {"status": UNRESOLVED, "reason": "PLAYER_INTERVENTION_NOT_PHYSICALLY_VERIFIED"}


def _assert_required_outcome(outcomes: list[dict], expected: str) -> dict:
    observed = [str(row.get("physical_outcome") or "") for row in outcomes]
    if expected in observed:
        return {"status": PASS, "reason": f"PHYSICAL_OUTCOME_{expected}_VERIFIED"}
    # A different positively verified terminal outcome is a contradiction.
    positive = [x for x in observed if x and x not in {"UNRESOLVED", "UNRESOLVED_TERMINAL_VISIBILITY"}]
    if positive:
        return {"status": FAIL, "reason": "DIFFERENT_PHYSICAL_OUTCOME_VERIFIED", "observed": positive}
    return {"status": UNRESOLVED, "reason": f"REQUIRED_PHYSICAL_OUTCOME_{expected}_NOT_VERIFIED"}


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


def _assert_forbidden_jersey_touch(touches: list[dict], jersey: str) -> dict:
    target = str(jersey)
    bad = [
        t for t in touches
        if t.get("status") == "VERIFIED"
        and t.get("global_target_id") != "GLOBAL_TARGET"
        and _jersey_number(t) == target
    ]
    if bad:
        return {"status": FAIL, "reason": "FORBIDDEN_VERIFIED_JERSEY_TOUCH", "jersey": target, "count": len(bad)}
    # Absence is enough for this narrow safety assertion: FIX10A did not
    # physically attribute a decisive touch to the forbidden jersey. It does
    # NOT prove the player was absent from the scene.
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
    if gate.get("require_target_release") is True:
        assertions.append({"name": "require_target_release", **_assert_target_release(strikes)})
    if gate.get("require_player_intervention") is True:
        assertions.append({"name": "require_player_intervention", **_assert_player_intervention(outcomes)})
    if gate.get("require_goal_plane_crossing") is True:
        assertions.append({"name": "require_goal_plane_crossing", **_assert_required_outcome(outcomes, "GOAL_PLANE_CROSSING")})
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
    if gate.get("forbid_non_target_verified_jersey_touch") is not None:
        assertions.append({
            "name": "forbid_non_target_verified_jersey_touch",
            **_assert_forbidden_jersey_touch(touches, str(gate["forbid_non_target_verified_jersey_touch"])),
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
    statuses = [case["status"] for case in cases]
    status = FAIL if FAIL in statuses else UNRESOLVED if UNRESOLVED in statuses else PASS
    return {
        "version": VERSION,
        "fixture_id": manifest.get("fixture_id"),
        "status": status,
        "cases": cases,
        "metrics": {
            "cases": len(cases),
            "passed": sum(x == PASS for x in statuses),
            "unresolved": sum(x == UNRESOLVED for x in statuses),
            "failed": sum(x == FAIL for x in statuses),
        },
    }
