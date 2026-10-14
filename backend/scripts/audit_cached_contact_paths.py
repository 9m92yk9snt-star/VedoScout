"""Offline contact-path audit of a hash-bound native evidence cache.

Re-enters the production physical gates using the existing measured frames.
No network, SDK, video decode, detector, or saved goal outcome is permitted.
Reference labels, when supplied, are used only in the final diagnostic output.
This is not fresh video acceptance, deployment, or full-video completeness.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import socket
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    parser.add_argument("--cases-json", type=Path)
    args = parser.parse_args()
    for name in list(os.environ):
        if any(token in name.upper() for token in ("API_KEY", "EMERGENT_LLM_KEY", "OPENAI_KEY")):
            os.environ.pop(name, None)
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    attempts = {"network": 0, "sdk": 0, "video_decode": 0, "native_detector": 0}

    def block(kind):
        def forbidden(*_args, **_kwargs):
            attempts[kind] += 1
            raise RuntimeError("CACHE_AUDIT_FORBIDDEN_" + kind.upper())
        return forbidden

    socket.socket.connect = block("network")
    socket.socket.connect_ex = block("network")
    socket.create_connection = block("network")
    import cv2
    cv2.VideoCapture = block("video_decode")
    import dense_track_refinement
    dense_track_refinement.refine_window = block("native_detector")
    dense_track_refinement.detect_ball_candidates = block("native_detector")
    import fix10a_vision_providers
    import identity_verify
    fix10a_vision_providers.LlmChat = identity_verify.LlmChat = block("sdk")
    import physical_match_reconstruction as pmr
    from scripts import reference_action_review

    backend = Path(__file__).resolve().parents[1]

    def source_hashes():
        return {name: hashlib.sha256((backend / name).read_bytes()).hexdigest() for name in (
            "ball_trajectory.py", "contact_role_resolver.py", "fix10a_vision_providers.py",
            "physical_match_reconstruction.py", "scripts/audit_cached_contact_paths.py",
            "support_vision_runner.py", "fix10b_reconciliation.py")}

    initial_sources = source_hashes()
    cache = args.cache.resolve()
    manifest_path = cache / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    for name, expected in manifest["files"].items():
        path = (cache / name).resolve()
        if not path.is_relative_to(cache) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("Frozen cache checksum mismatch")

    def load(name):
        if name not in manifest["files"]:
            raise RuntimeError("Required evidence is not covered by the cache manifest: " + name)
        return json.loads((cache / name).read_bytes())

    traces = [load(name) for name in manifest["traces"]]
    originals = deepcopy(traces)
    source_paths = []
    for trace in traces:
        strikes = deepcopy(trace.get("strike_evidence") or [])
        paths = pmr._strike_ball_paths(strikes, trace.get("touch_graph") or {},
                                       trace["decoded_frames"], trace.get("ball_trajectory") or [])
        source_paths.extend(paths)
    physical = pmr.reconstruct_physical_match(
        "", load("sequence_plan.json"), load("sequence_analysis.json"),
        load("scene_graph.json"), load("authority.json"),
        _feedback_context={"traces": {t["trace_id"]: t for t in traces}, "jobs": []})
    if physical.get("status") != "ok" or any(w.get("status") == "error" for w in physical["windows"]):
        raise RuntimeError("Cached production reconstruction failed")
    if traces != originals:
        raise RuntimeError("Cached source observations were mutated")
    for name, expected in manifest["files"].items():
        if hashlib.sha256((cache / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("Cached evidence changed during audit")

    outcomes = [o for t in physical["traces"] for o in t.get("outcome_evidence") or []]
    cases = []
    if args.cases_json:
        references = reference_action_review.validate_cases(json.loads(args.cases_json.read_bytes()))
        plan = reference_action_review.build_plan(physical["traces"], references)
        for case in references:
            job = next((j for j in plan["jobs"] if j["center_ms"] == case["reference_ms"]), None)
            trace = next((t for t in physical["traces"]
                          if job and t["trace_id"] == job["dense_window_id"]), {})
            near = lambda row: case["reference_ms"] - 1000 <= row.get("media_ms", -1) <= case["reference_ms"] + 1600
            cases.append({**case, "fresh_video_qualification": "NOT_PERFORMED",
                "frame_coverage": job is not None,
                "nearby_contacts": len([c for c in (trace.get("contacts") or {}).get("accepted") or [] if near(c)]),
                "nearby_target_touches": len([t for t in (trace.get("touch_graph") or {}).get("touches") or []
                    if near(t) and t.get("global_target_id") == "GLOBAL_TARGET" and t.get("proof_eligible") is True]),
                "nearby_outcomes": [{k: o.get(k) for k in (
                    "media_ms", "physical_outcome", "ball_trajectory_source", "release_ball_binding",
                    "goal_plane_crossing", "save_evidence", "intervention_role")}
                    for o in trace.get("outcome_evidence") or [] if near(o)]})
    source_bindings = [p.get("contact_binding") or {} for p in source_paths]
    if source_hashes() != initial_sources:
        raise RuntimeError("Backend source changed during the audit")
    result = {"kind": "OFFLINE_CONTACT_BOUND_CACHE_AUDIT",
        "source_sha256": initial_sources,
        "cache_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "windows": len(traces), "source_frames": sum(len(t["decoded_frames"]) for t in traces),
        "source_strike_paths": len(source_paths),
        "source_binding_statuses": dict(Counter(b.get("status", "LEGACY_NO_CONTACT_CONTRACT") for b in source_bindings)),
        "source_binding_rejection_reasons": dict(Counter(b["reason"] for b in source_bindings if b.get("status") == "REJECTED")),
        "reconstructed_strikes": sum(len(t.get("strike_evidence") or []) for t in physical["traces"]),
        "reconstructed_outcome_types": dict(Counter(o.get("physical_outcome") for o in outcomes)),
        "reconstructed_binding_statuses": dict(Counter((o.get("release_ball_binding") or {}).get("status", "LEGACY_NO_CONTACT_CONTRACT") for o in outcomes)),
        "forbidden_attempts": attempts, "new_model_calls": 0,
        "source_observations_unchanged": True, "saved_goal_outcomes_reused": False,
        "fresh_video_qualification_performed": False, "cases": cases,
        "limitations": ["Earlier native cache, not the later complete supporting-review run",
                        "No new camera transforms, role/jersey votes, or whole-ball goal-crossing proof",
                        "The initial contact object's match-ball identity is not independently certified",
                        "No canonical event acceptance or full-video completeness certification"]}
    print(json.dumps(result, sort_keys=True))
    return 90 if any(attempts.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
