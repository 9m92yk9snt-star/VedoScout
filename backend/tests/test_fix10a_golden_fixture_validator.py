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


def _strike(ms, *, touch_id=None, target=False, suffix=""):
    return {
        "strike_id": f"strike-{ms}{suffix}",
        "touch_id": touch_id,
        "media_ms": ms,
        "status": "VERIFIED_PHYSICAL_RELEASE",
        "global_target_id": "GLOBAL_TARGET" if target else None,
    }


def _trace(start, end, *, touches=None, strikes=None, outcomes=None):
    return {
        "trace_id": f"trace-{start}",
        "window": {"start_ms": start, "end_ms": end},
        "touch_graph": {"touches": touches or []},
        "strike_evidence": strikes or [],
        "outcome_evidence": outcomes or [],
    }


def _pass_analysis(*, include_pass=True):
    actions = [{"kind": "RECEIVE", "start_ms": 70400, "end_ms": 70650}]
    if include_pass:
        actions.append({"kind": "PASS", "start_ms": 70800, "end_ms": 71300})
    return {"sequences": [{"actions": actions}]}


def test_golden01_manifest_is_locked_and_has_three_cases():
    manifest = _manifest()
    assert manifest["source"]["sha256"] == "8e9f04b4f70cb3174a204ec37ce957ee4ff0f3506a0d1815ef0e86e19b17df34"
    assert manifest["source"]["frame_count"] == 2303
    assert [c["case_id"] for c in manifest["cases"]] == [
        "saved_shot_23s",
        "receive_feint_accel_right_foot_goal_27s",
        "receive_cross_field_pass_no_goal_70s",
    ]
    corrected = manifest["cases"][2]
    assert corrected["expected_semantics"] == ["RECEIVE", "PASS"]
    assert corrected["perception_gate"]["require_kinds"] == ["RECEIVE", "PASS"]
    assert corrected["canonical_later"]["expected_target_event"] == "PASS"


def test_golden02_saved_shot_requires_verified_keeper_save_and_no_goal():
    case = _manifest()["cases"][0]
    strike = _strike(23800, target=True)
    outcome = {
        "strike_id": strike["strike_id"], "media_ms": 23800,
        "physical_outcome": "GOALKEEPER_SAVE_EVIDENCE",
        "intervention": {"status": "VERIFIED", "media_ms": 24500},
    }
    result = {"traces": [_trace(23550, 25150, strikes=[strike], outcomes=[outcome])]}
    verdict = gfv.validate_case(case, result)
    assert verdict["status"] == gfv.PASS
    assert all(a["status"] == gfv.PASS for a in verdict["assertions"])


def test_golden03_intervention_without_keeper_save_is_not_enough():
    case = _manifest()["cases"][0]
    strike = _strike(23800, target=True)
    outcome = {
        "strike_id": strike["strike_id"], "media_ms": 23800,
        "physical_outcome": "PLAYER_INTERVENTION",
        "intervention": {"status": "VERIFIED", "media_ms": 24500},
    }
    verdict = gfv.validate_case(case, {"traces": [_trace(23550, 25150, strikes=[strike], outcomes=[outcome])]})
    assert verdict["status"] == gfv.FAIL
    required = next(a for a in verdict["assertions"] if a["name"] == "require_physical_outcome")
    assert required["status"] == gfv.FAIL


def test_golden04_saved_shot_fails_if_physical_layer_asserts_goal():
    case = _manifest()["cases"][0]
    strike = _strike(23800, target=True)
    outcome = {
        "strike_id": strike["strike_id"], "media_ms": 23800,
        "physical_outcome": "GOAL_PLANE_CROSSING",
        "intervention": {"status": "VERIFIED", "media_ms": 24500},
    }
    result = {"traces": [_trace(23550, 25150, strikes=[strike], outcomes=[outcome])]}
    verdict = gfv.validate_case(case, result)
    assert verdict["status"] == gfv.FAIL
    assert any(a["name"] == "must_not_assert_physical_outcome" and a["status"] == gfv.FAIL
               for a in verdict["assertions"])


def test_golden05_goal_case_is_unresolved_without_goal_geometry_evidence():
    case = _manifest()["cases"][1]
    strike = _strike(31050, target=True)
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


def test_golden06_cross_field_pass_case_passes_with_release_no_goal_and_pass_semantics():
    case = _manifest()["cases"][2]
    release = _strike(71000, target=True)
    result = {"traces": [_trace(69800, 73500, strikes=[release], outcomes=[])]}
    verdict = gfv.validate_case(case, result, _pass_analysis())
    assert verdict["status"] == gfv.PASS
    required = next(a for a in verdict["assertions"] if a["name"] == "require_target_release")
    forbidden = next(a for a in verdict["assertions"] if a["name"] == "must_not_assert_physical_outcome")
    semantics = next(a for a in verdict["assertions"] if a["name"] == "require_perception_kinds")
    assert required["status"] == gfv.PASS
    assert forbidden["status"] == gfv.PASS
    assert semantics["status"] == gfv.PASS


def test_golden07_cross_field_pass_case_fails_if_goal_is_asserted():
    case = _manifest()["cases"][2]
    release = _strike(71000, target=True)
    goal = {
        "strike_id": release["strike_id"],
        "media_ms": 71200,
        "physical_outcome": "GOAL_PLANE_CROSSING",
    }
    result = {"traces": [_trace(69800, 73500, strikes=[release], outcomes=[goal])]}
    verdict = gfv.validate_case(case, result, _pass_analysis())
    assert verdict["status"] == gfv.FAIL
    forbidden = next(a for a in verdict["assertions"] if a["name"] == "must_not_assert_physical_outcome")
    assert forbidden["status"] == gfv.FAIL


def test_golden08_cross_field_pass_case_is_unresolved_without_target_release():
    case = _manifest()["cases"][2]
    result = {"traces": [_trace(69800, 73500, strikes=[], outcomes=[])]}
    verdict = gfv.validate_case(case, result, _pass_analysis())
    assert verdict["status"] == gfv.UNRESOLVED
    required = next(a for a in verdict["assertions"] if a["name"] == "require_target_release")
    assert required["status"] == gfv.UNRESOLVED


def test_golden09_cross_field_pass_case_rejects_wrong_actor_release_in_reference_range():
    case = _manifest()["cases"][2]
    wrong_actor_release = _strike(71000, target=False)
    result = {"traces": [_trace(69800, 73500, strikes=[wrong_actor_release], outcomes=[])]}
    verdict = gfv.validate_case(case, result, _pass_analysis())
    assert verdict["status"] == gfv.FAIL
    required = next(a for a in verdict["assertions"] if a["name"] == "require_target_release")
    assert required["status"] == gfv.FAIL


def test_golden10_cross_field_pass_case_cannot_pass_without_pass_semantics():
    case = _manifest()["cases"][2]
    release = _strike(71000, target=True)
    result = {"traces": [_trace(69800, 73500, strikes=[release], outcomes=[])]}
    verdict = gfv.validate_case(case, result, _pass_analysis(include_pass=False))
    assert verdict["status"] == gfv.UNRESOLVED
    semantics = next(a for a in verdict["assertions"] if a["name"] == "require_perception_kinds")
    assert semantics["status"] == gfv.UNRESOLVED
    assert semantics["missing"] == ["PASS"]


def test_golden11_fixture_never_false_passes_when_no_traces_exist():
    verdict = gfv.validate_fixture(_manifest(), {"traces": []}, {})
    assert verdict["status"] == gfv.UNRESOLVED
    assert verdict["metrics"]["passed"] == 0
    assert verdict["metrics"]["unresolved"] == 3
