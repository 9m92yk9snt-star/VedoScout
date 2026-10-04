"""Read-only gate audit: actual functions, synthetic controls, optional local traces.

No server startup, video decoding, provider requests, database access or writes.
This documents current behavior; it does not measure real-video precision/recall.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
import fix10a_ball_proof_gate as ball_gate  # noqa: E402
import full_video_event_recall as recall  # noqa: E402
import jersey_consensus as jersey  # noqa: E402
import shot_outcome_engine as outcomes  # noqa: E402
import touch_graph  # noqa: E402
from audit_analysis_control_flow import load_function  # noqa: E402


def function_namespace(filename):
    """Load module functions/constants, excluding imports and other top-level work.

    Vision modules import cv2/SDKs. Their pure gate functions do not need those
    dependencies. Compile their actual AST with original locations/annotations.
    """
    parsed = ast.parse((BACKEND / filename).read_text())
    body = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
    for node in parsed.body:
        if isinstance(node, ast.FunctionDef):
            node.decorator_list = []
            body.append(node)
        elif isinstance(node, ast.Assign) and all(
                isinstance(target, ast.Name) and target.id.isupper() for target in node.targets):
            body.append(node)
    namespace = {"deepcopy": deepcopy, "os": os, "math": math, "json": json,
                 "Path": Path, "__file__": str(BACKEND / filename)}
    exec(compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])),
                 str(BACKEND / filename), "exec"), namespace)
    return namespace


def controls():
    physical = function_namespace("physical_match_reconstruction.py")
    eligible = physical["_goal_review_eligibility"]
    direction = function_namespace("fix10a_goal_direction.py")["apply_direction_gate"]
    ready = load_function("unified_analysis_engine.py", "is_production_ready", {})
    rows = []

    target = {"status": "VERIFIED_PHYSICAL_RELEASE", "proof_eligible": True,
              "player_track_id": "p1", "global_target_id": "GLOBAL_TARGET",
              "media_ms": 1000, "scene_id": "s1", "touch_id": "t1"}
    unknown = {**target, "global_target_id": None}
    a, b = eligible(unknown, [unknown], {}), eligible(target, [target], {})
    assert a["eligible"] is False and b["eligible"] is True
    rows.append({"case": "goal_review_needs_target_ownership", "unknown": a, "verified": b})

    downstream = {**unknown, "media_ms": 2000, "player_track_id": "p2", "touch_id": "t2"}
    touch = {"touch_id": "t2", "status": "VERIFIED", "proof_eligible": True,
             "team_relation": {"status": "SUPPORTING", "team": "target_team", "confidence": .9}}
    a = eligible(downstream, [target, downstream], {"touches": []})
    b = eligible(downstream, [target, downstream], {"touches": [touch]})
    assert a["eligible"] is False and b["eligible"] is True
    rows.append({"case": "downstream_review_needs_team_proof", "unknown": a, "verified": b})

    later = {**downstream, "media_ms": 6201}
    cut = {**downstream, "scene_id": "s2"}
    assert not eligible(later, [target, later], {"touches": [touch]})["eligible"]
    assert not eligible(cut, [target, cut], {"touches": [touch]})["eligible"]
    rows.append({"case": "review_horizon_and_scene_barrier", "blocked": True})

    frame = {"media_ms": 1000, "scene_id": "s1", "global_target": {
        "status": "UNRESOLVED", "candidate_local_track_ids": ["p1"]},
        "possession": {"holder_local_track_id": "p1", "target_relation": "TARGET_LIKELY_POSSESSION"}}
    unresolved = recall._graph_trigger(frame, None)
    hypothesis = recall._graph_trigger({**frame, "global_target": {
        **frame["global_target"], "status": "HYPOTHESES"}}, None)
    assert unresolved[0] is False and hypothesis[0] is True
    rows.append({"case": "recall_graph_lane_is_identity_dependent",
                 "unresolved": unresolved, "hypothesis": hypothesis})

    box = {"x": .1, "y": .2, "w": .1, "h": .3}
    frames = [{"media_ms": ms, "players": [{"local_track_id": "p1", "box": box,
               "association_state": "VERIFIED_LOCAL"}]} for ms in (1000, 1200)]
    graph = {"touches": [{"player_track_id": "p1"}]}
    requests = jersey.select_jersey_review_requests(frames, graph)
    votes = [{"media_ms": r["media_ms"], "readable": True, "number": "15", "confidence": "high"}
             for r in requests]
    result = jersey.aggregate_jersey_votes(votes)
    ambiguous = deepcopy(frames)
    for frame in ambiguous:
        frame["players"][0]["association_state"] = "HYPOTHESES"
    assert len(requests) == 2 and result["status"] == "VERIFIED"
    assert not jersey.select_jersey_review_requests(ambiguous, graph)
    rows.append({"case": "jersey_two_reads_can_verify_but_ambiguous_body_gets_no_request",
                 "selected_frames": len(requests), "consensus": result["status"],
                 "top_posterior": result["top_posterior"]})

    contact = {"media_ms": 1000, "scene_id": "s1", "player_track_id": "p1",
               "player_candidate_track_ids": ["p1"], "status": "VERIFIED", "proof_eligible": True,
               "confidence": .9, "possession_evidence": {"kind": "CONTROL_TOUCH"}}
    good = touch_graph.build_touch_graph({"contacts": [contact]}, {}, [])
    mixed = touch_graph.build_touch_graph({"contacts": [contact, {
        **contact, "media_ms": 1080, "status": "CANDIDATE_OCCLUDED", "proof_eligible": False}]}, {}, [])
    assert good["touches"][0]["status"] == "VERIFIED"
    assert len(mixed["touches"]) == 2
    assert {t["status"] for t in mixed["touches"]} == {"VERIFIED", "CANDIDATE_OCCLUDED"}
    rows.append({"case": "touch_group_separates_quality_and_preserves_verified_member",
                 "single": "VERIFIED", "mixed_groups": 2})

    result = {"status": "ok", "sequence_analysis": {"coverage_complete": True},
              "metrics": {"sequence_windows": 1}, "canonical_events": {"status": "empty"}}
    assert ready(result)
    result["sequence_analysis"]["coverage_complete"] = False
    assert not ready(result)
    runtime = load_function("fix10a_runtime.py", "run", {
        "logger": logging.getLogger("gate-audit"), "VERSION": 2})
    skip = asyncio.run(runtime(report_id="synthetic", video_path="unused", unified_result=result, db=None))
    assert skip["status"] == "skipped"
    rows.append({"case": "partial_sequence_contract_skips_physical_runtime",
                 "empty_complete_can_be_ready": True, "partial_runtime": skip["reason"]})

    # A positive whole-ball control proves these final gates can accept real
    # structured evidence; absence of detector rows is not an absolute veto.
    test_functions = function_namespace("tests/test_fix10a7_structured_goal_proof.py")
    geometry = test_functions["_geometry"]()
    strike = test_functions["_strike"]()
    result = outcomes.reconstruct_post_strike_outcome(
        strike, [], {"touches": []}, goal_geometry=geometry, role_evidence={})
    result = direction(result, [], geometry)
    result = ball_gate.apply_ball_proof_gate(result, [])
    assert result["goal_plane_crossing"]["status"] == "VERIFIED"
    rows.append({"case": "structured_whole_ball_proof_survives_final_gates",
                 "crossing": result["goal_plane_crossing"]["status"]})
    bare = test_functions["_geometry"](audit={"status": "VERIFIED_CROSSING", "confidence": "high"})
    bad = outcomes.reconstruct_post_strike_outcome(
        strike, [], {"touches": []}, goal_geometry=bare, role_evidence={})
    assert bad["goal_plane_crossing"]["status"] == "UNRESOLVED"
    rows.append({"case": "bare_llm_goal_label_is_insufficient", "crossing": "UNRESOLVED"})
    return rows, eligible, direction


def inspect_traces(directory, eligible, direction):
    manifest = json.loads((directory / "mongo-manifest-observed.json").read_text())
    counts, reasons, outcome_types = Counter(), Counter(), Counter()
    near = {23680: [], 30830: []}
    for item in manifest["traces"]:
        payload = (directory / item["file"]).read_bytes()
        decoded = gzip.decompress(payload)
        assert len(payload) == item["bytes_gzip"]
        assert hashlib.sha256(decoded).hexdigest() == item["sha256"]
        trace = json.loads(decoded)
        assert trace["trace_id"] == item["trace_id"]
        counts["verified_manifest_files"] += 1
        strikes = trace.get("strike_evidence") or []
        graph = trace.get("touch_graph") or {}
        by_id = {r["strike_id"]: r for r in strikes}
        for outcome in trace.get("outcome_evidence") or []:
            counts["outcomes"] += 1
            outcome_types[outcome.get("physical_outcome")] += 1
            observed = outcome.get("goal_review_eligibility") or {}
            recomputed = eligible(by_id[outcome["strike_id"]], strikes, graph)
            assert observed == recomputed
            counts["review_eligibility_exact_match"] += 1
            counts["goal_review_eligible"] += int(observed.get("eligible") is True)
            reasons[observed.get("reason")] += 1
            counts["direction_gate_unchanged"] += int(direction(
                outcome, trace.get("ball_trajectory") or [], outcome.get("goal_geometry_evidence")) == outcome)
            counts["ball_gate_unchanged"] += int(ball_gate.apply_ball_proof_gate(
                outcome, trace.get("ball_trajectory") or []) == outcome)
            counts["verified_crossing"] += int((outcome.get("goal_plane_crossing") or {}).get("status") == "VERIFIED")
            counts["goal_budget_exhausted"] += int(
                (outcome.get("goal_geometry_evidence") or {}).get("reason") == "GOAL_REVIEW_BUDGET_EXHAUSTED")
        contacts = trace.get("contacts") or {}
        for category in ("accepted", "rejected", "unresolved"):
            for contact in contacts.get(category) or []:
                for ms, rows in near.items():
                    if abs(contact["media_ms"] - ms) <= 350:
                        ball = contact.get("ball_at_contact") or {}
                        rows.append({"media_ms": contact["media_ms"], "time_authority": contact.get("time_authority"),
                                     "ball_state": ball.get("state"), "ball_proof": ball.get("proof_eligible"),
                                     "reasons": contact.get("rejection_reasons") or []})
    counts["goal_review_skipped"] = counts["outcomes"] - counts["goal_review_eligible"]
    return {"report_id": manifest["report_id"], "counts": dict(counts),
            "eligibility_reasons": dict(reasons), "outcome_types": dict(outcome_types),
            "reference_contacts_within_350ms": near}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-dir", type=Path, help="Private local authoritative traces; never uploaded by this script")
    args = parser.parse_args()
    rows, eligible, direction = controls()
    result = {"synthetic_controls": rows, "control_count": len(rows),
              "limitations": "No new model call or full-video acceptance test; controls run current checkout functions."}
    if args.trace_dir:
        result["authoritative_trace_audit"] = inspect_traces(args.trace_dir, eligible, direction)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
