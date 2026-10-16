"""A one-frame scene must not disable physical review of the other scenes."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import football_sequence_intelligence as sequences
import unified_analysis_engine as unified
import fix10a_runtime as runtime
import verified_stats as stats


def window(scene, start, end):
    return {"sequence_id": sequences._stable_id("seq", scene, start, end),
            "scene_id": scene, "start_ms": start, "end_ms": end}


def partial_result():
    windows = [window("before", 0, 19199), window("flash", 19333, 19333),
               window("after", 19466, 25466)]
    return {"status": "partial_coverage",
            "sequence_plan": {"analysis_windows": windows,
                              "refinement_windows": deepcopy(windows)},
            "sequence_analysis": {"coverage_complete": False, "sequences": []},
            "canonical_events": {"status": "empty", "events": [], "counts": {},
                                 "unresolved": [], "rejected": [], "metrics": {}},
            "identity_authority": {}, "scene_graph": {},
            "metrics": {"sequence_windows": 3}}


def test_planner_omits_single_frame_scene_without_crossing_its_cuts():
    rows = [("before", 0), ("before", 19199), ("flash", 19333),
            ("after", 19466), ("after", 25466)]
    graph = {"frames": [{"media_ms": ms, "scene_id": scene,
                         "global_target": {"status": "VERIFIED", "local_track_id": "p1"}}
                        for scene, ms in rows],
             "scenes": [{"scene_id": scene, "start_ms": start, "end_ms": end}
                        for scene, start, end in [("before", 0, 19199),
                                                  ("flash", 19333, 19333),
                                                  ("after", 19466, 25466)]]}
    plan = sequences.build_sequence_plan(graph)
    assert plan["analysis_windows"]
    assert all(w["end_ms"] > w["start_ms"] for key in ("analysis_windows", "refinement_windows")
               for w in plan[key])
    assert {w["scene_id"] for w in plan["analysis_windows"]} == {"before", "after"}
    assert plan["unreviewable_windows"] == [{"scene_id": "flash", "start_ms": 19333,
                                             "end_ms": 19333, "reason": "ZERO_DURATION_SCENE"}]
    assert not any(w["start_ms"] <= 19333 <= w["end_ms"] for w in plan["analysis_windows"])


def test_omitted_scene_does_not_turn_reviewed_remainder_into_complete_coverage():
    plan = {"analysis_windows": [window("after", 19466, 25466)],
            "unreviewable_windows": [{"scene_id": "flash", "start_ms": 19333,
                                       "end_ms": 19333, "reason": "ZERO_DURATION_SCENE"}]}
    w = plan["analysis_windows"][0]
    response = {"sequences": [{**w, "actions": []}],
                "coverage": [{"sequence_id": w["sequence_id"], "reviewed": True,
                              "target_seen": False, "actions_found": 0}]}
    result = unified.finalise_analysis(response, {"sequence_plan": plan})
    assert result["status"] == "partial_coverage"
    assert not result["sequence_analysis"]["coverage_complete"]
    assert unified.can_run_physical(result)
    assert result["canonical_events"]["events"] == []


def test_old_plan_keeps_safe_windows_and_does_not_promote_observations():
    result = partial_result()
    before = deepcopy(result)
    assert unified.can_run_physical(result)
    plan = unified.physical_sequence_plan(result)
    assert {w["scene_id"] for w in plan["analysis_windows"]} == {"before", "after"}
    assert {w["scene_id"] for w in plan["refinement_windows"]} == {"before", "after"}
    assert plan["unreviewable_windows"]
    assert result == before
    assert not unified.is_production_ready(result)
    assert result["canonical_events"]["events"] == []


@pytest.mark.parametrize("change", [{"end_ms": float("nan")}, {"start_ms": -1},
                                  {"end_ms": -1}, {"scene_id": ""}, {"start_ms": True}])
def test_other_malformed_windows_remain_rejected(change):
    result = partial_result()
    result["sequence_plan"]["analysis_windows"][1].update(change)
    assert not unified.can_run_physical(result)


def test_only_single_frame_windows_do_not_admit_physical_work():
    result = partial_result()
    result["sequence_plan"]["analysis_windows"] = [window("flash", 19333, 19333)]
    assert not unified.can_run_physical(result)


async def test_runtime_reaches_physical_work_with_only_positive_windows(monkeypatch):
    monkeypatch.setattr(runtime, "support_vision_enabled", lambda: False)
    calls = []
    def reconstruct(video, plan, *args, **kwargs):
        calls.append(plan)
        return {"status": "ok", "traces": [], "windows": [], "metrics": {},
                "recall_coverage": {"complete": True, "status": "COMPLETE",
                                    "scan_complete": True, "verification_complete": True}}
    monkeypatch.setattr(runtime.physical_match_reconstruction, "reconstruct_physical_match", reconstruct)
    output = await runtime.run(report_id="test", video_path="unused", unified_result=partial_result(), db=None)
    assert len(calls) == 1
    assert all(w["end_ms"] > w["start_ms"] for w in calls[0]["analysis_windows"])
    assert output["_fix10b_candidate"]["enabled"] is True
    candidate = output["_fix10b_candidate"]["unified_result"]
    assert candidate["canonical_events"]["events"] == []
    assert not candidate["scoring_scan"]["physical_recall_verification_complete"]
    assert "SOURCE_SEQUENCE_WINDOWS_UNREVIEWABLE" in candidate["scoring_scan"]["physical_evidence_coverage"]["reasons"]


def test_fallback_report_with_empty_ledger_cannot_publish_model_goals():
    full = {"action_timeline": [{"timestamp": "00:24", "title": "Goal"}],
            "executive_summary": "He scored a fantastic goal.",
            "snapshot_moments": [{"timestamp": "00:24", "title": "Goal",
                                  "desc": "His shot goes into the net."}],
            "cross_verification": {"status": "verified"},
            "_scoring_scan": {"performed": True, "unresolved_goal_attempts": 1}}
    ledger = {"events": [], "candidates_total": 25, "candidates_verified": 0,
              "status": "ok", "discovery_complete": True, "track_usable": True}
    full = unified.apply_legacy_result_to_report(full, ledger)
    result = stats.apply_verified_stats_authority(full)
    assert result["action_timeline"] == []
    assert result["verified_stats"]["coverage_status"] == "PARTIAL"
    assert not result["verified_stats"]["goals_assists_available"]
    assert result["match_stats"].get("goals") is None
    assert "fantastic goal" not in result["executive_summary"]
    assert result["report_fact_authority"]["unsupported_claim_paths"]
    assert result["snapshot_moments"][0]["title"] != "Goal"


def test_compact_plan_retains_omitted_window_diagnostic():
    result = partial_result()
    result["sequence_plan"] = unified.physical_sequence_plan(result)
    payload = unified.persistence_payload(result)
    assert payload["football_sequence_plan"]["unreviewable_windows"]


def test_diagnostic_plan_reconstruction_rejects_changed_response_boundaries():
    import importlib.util
    path = Path(__file__).resolve().parents[1] / "scripts/audit_sequence_admission.py"
    spec = importlib.util.spec_from_file_location("sequence_admission_audit", path)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    original = window("flash", 19333, 19333)
    assert audit.infer_plan({"sequences": [original]})["analysis_windows"] == [original]
    with pytest.raises(ValueError, match="planner ID"):
        audit.infer_plan({"sequences": [{**original, "end_ms": 19466}]})


@pytest.mark.parametrize("number,text,conflict", [
    ("5", "I am in white jersey number 15", {"field_number": "5", "description_number": "15"}),
    ("15", "I am number 15 in white", None),
    ("015", "My shirt number is not included. Jersey 15", None),
    ("5", "I am 11 and we won 15-5", None),
    (None, "Jeg har trøje nummer 15", None),
    ("5", "Jeg har trøje nr. 15", {"field_number": "5", "description_number": "15"}),
    ("15", "I am number 15, opponent number 5", None),
])
def test_number_declarations_do_not_truncate_or_guess(number, text, conflict):
    from player_identity_declaration import jersey_declaration_conflict
    assert jersey_declaration_conflict(number, text) == conflict


async def test_upload_checks_conflicting_identity_before_billing_or_background_work():
    import ast
    from fastapi import HTTPException
    source = ast.parse((Path(__file__).resolve().parents[1] / "server.py").read_text())
    upload = next(n for n in source.body if isinstance(n, ast.AsyncFunctionDef)
                  and n.name == "upload_video_and_create_preview")
    # Execute the real production prefix up to the first billing/access gate.
    gate = next(i for i, n in enumerate(upload.body) if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "is_admin" for t in n.targets))
    upload.body = upload.body[:gate]
    upload.decorator_list = []
    upload.args = ast.arguments(posonlyargs=[], args=[ast.arg(arg="jersey_number"),
                                 ast.arg(arg="description")], kwonlyargs=[], kw_defaults=[], defaults=[])
    upload.returns = None
    namespace = {"HTTPException": HTTPException}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[upload], type_ignores=[])),
                 "production-upload-identity-preflight", "exec"), namespace)
    with pytest.raises(HTTPException) as error:
        await namespace[upload.name]("5", "I am in white jersey number 15")
    assert error.value.status_code == 422
    assert "5" in error.value.detail and "15" in error.value.detail
    await namespace[upload.name]("15", "I am in white jersey number 15")
