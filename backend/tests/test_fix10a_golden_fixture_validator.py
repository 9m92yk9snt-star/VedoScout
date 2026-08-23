"""FIX10A real-video Golden Fixture validator regression tests."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import golden_fixture_validator as gfv  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "real_video" / "almin_test07_v1.json"


def _manifest():
    return gfv.load_manifest(FIXTURE)


def _touch(ms, jersey=None, *, target=False):
    posterior = None
    if jersey is not None:
        posterior = {"status": "VERIFIED", "number": str(jersey)}
    return {
        "touch_id": f"t{ms}-{jersey}",
        "media_ms": ms,
        "status": "VERIFIED",
        "player_track_id": f"p{jersey or 15}",
        "global_target_id": "GLOBAL_TARGET" if target else None,
        "jersey_posterior": posterior,
    }


def _trace(start, end, *, touches=None, strikes=None, outcomes=None):
    return {
        "trace_id": f"trace-{start}",
        "window": {"start_ms": start, "end_ms": end},
        "touch_graph": {"touches": touches or []},
        "strike_evidence": strikes or [],
        "outcome_evidence": outcomes or [],
    }


def test_golden01_manifest_is_locked_and_has_three_cases():
    manifest = _manifest()
    assert manifest["source"]["sha256"] == "8e9f04b4f70cb3174a204ec37ce957ee4ff0f3506a0d1815ef0e86e19b17df34"
    assert manifest["source"]["frame_count"] == 2303
    assert [c["case_id"] for c in manifest["cases"]] == [
        "saved_shot_23s",
        "receive_feint_accel_right_foot_goal_27s",
        "assist_15_to_scorer_10_not_12",
    ]


def test_golden02_saved_shot_passes_without_any_goal_assertion():
    case = _manifest()["cases"][0]
    strike = {
        "strike_id": "s1", "media_ms": 23800,
        "status": "VERIFIED_PHYSICAL_RELEASE", "global_target_id": "GLOBAL_TARGET",
    }
    outcome = {
        "strike_id": "s1", "media_ms": 23800,
        "physical_outcome": "PLAYER_INTERVENTION",
        "intervention": {"status": "VERIFIED", "media_ms": 24500},
    }
    result = {"traces": [_trace(23550, 25150, strikes=[strike], outcomes=[outcome])]}
    verdict = gfv.validate_case(case, result)
    assert verdict["status"] == gfv.PASS
    assert all(a["status"] == gfv.PASS for a in verdict["assertions"])


def test_golden03_saved_shot_fails_if_physical_layer_asserts_goal():
    case = _manifest()["cases"][0]
    strike = {
        "strike_id": "s1", "media_ms": 23800,
        "status": "VERIFIED_PHYSICAL_RELEASE", "global_target_id": "GLOBAL_TARGET",
    }
    outcome = {
        "strike_id": "s1", "media_ms": 23800,
        "physical_outcome": "GOAL_PLANE_CROSSING",
        "intervention": {"status": "VERIFIED", "media_ms": 24500},
    }
    result = {"traces": [_trace(23550, 25150, strikes=[strike], outcomes=[outcome])]}
    verdict = gfv.validate_case(case, result)
    assert verdict["status"] == gfv.FAIL
    assert any(a["name"] == "must_not_assert_physical_outcome" and a["status"] == gfv.FAIL
               for a in verdict["assertions"])


def test_golden04_goal_case_is_unresolved_without_goal_geometry_evidence():
    case = _manifest()["cases"][1]
    strike = {
        "strike_id": "s2", "media_ms": 31050,
        "status": "VERIFIED_PHYSICAL_RELEASE", "global_target_id": "GLOBAL_TARGET",
    }
    result = {"traces": [_trace(27200, 34000, strikes=[strike], outcomes=[])]}
    analysis = {"sequences": [{"actions": [
        {"kind": "RECEIVE", "start_ms": 27800, "end_ms": 28100},
        {"kind": "FEINT", "start_ms": 28800, "end_ms": 29200},
        {"kind": "ACCELERATION", "start_ms": 29400, "end_ms": 30100},
        {"kind": "SHOT", "start_ms": 30900, "end_ms": 31200, "foot": "RIGHT"},
    ]}]}
    verdict = gfv.validate_case(case, result, analysis)
    assert verdict["status"] == gfv.UNRESOLVED
    assert any(a["name"] == "require_goal_plane_crossing" and a["status"] == gfv.UNRESOLVED
               for a in verdict["assertions"])
    assert any(a["name"] == "require_perception_kinds" and a["status"] == gfv.PASS
               for a in verdict["assertions"])
    assert any(a["name"] == "require_shot_foot" and a["status"] == gfv.PASS
               for a in verdict["assertions"])


def test_golden05_number10_touch_after_target_release_passes_and_number12_fails():
    case = _manifest()["cases"][2]
    target_strike = {
        "strike_id": "s3", "media_ms": 69000,
        "status": "VERIFIED_PHYSICAL_RELEASE", "global_target_id": "GLOBAL_TARGET",
    }
    good = {"traces": [_trace(
        65500, 72500,
        touches=[_touch(70300, "10")],
        strikes=[target_strike],
    )]}
    verdict = gfv.validate_case(case, good)
    assert verdict["status"] == gfv.PASS
    ordered = next(a for a in verdict["assertions"]
                   if a["name"] == "require_non_target_verified_jersey_touch_after_target_release")
    assert ordered["status"] == gfv.PASS
    assert ordered["target_release_ms"] == 69000
    assert ordered["touch_ms"] == [70300]

    bad = {"traces": [_trace(
        65500, 72500,
        touches=[_touch(70300, "12")],
        strikes=[target_strike],
    )]}
    verdict_bad = gfv.validate_case(case, bad)
    assert verdict_bad["status"] == gfv.FAIL


def test_golden06_number10_touch_before_target_release_cannot_pass_chain():
    case = _manifest()["cases"][2]
    late_target_release = {
        "strike_id": "s4", "media_ms": 70500,
        "status": "VERIFIED_PHYSICAL_RELEASE", "global_target_id": "GLOBAL_TARGET",
    }
    result = {"traces": [_trace(
        65500, 72500,
        touches=[_touch(70300, "10")],
        strikes=[late_target_release],
    )]}
    verdict = gfv.validate_case(case, result)
    assert verdict["status"] == gfv.UNRESOLVED
    ordered = next(a for a in verdict["assertions"]
                   if a["name"] == "require_non_target_verified_jersey_touch_after_target_release")
    assert ordered["status"] == gfv.UNRESOLVED


def test_golden07_fixture_never_false_passes_when_no_traces_exist():
    verdict = gfv.validate_fixture(_manifest(), {"traces": []}, {})
    assert verdict["status"] == gfv.UNRESOLVED
    assert verdict["metrics"]["passed"] == 0
    assert verdict["metrics"]["unresolved"] == 3
