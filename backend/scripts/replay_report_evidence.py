"""Read-only regression replay of saved evidence; never connects to a database.

Runs physical contacts/identity/roles and canonical reconciliation from the
exported observations. Optional --video-detail decodes the same hash-verified
video and adds ground-band ball detections; it does not run a new model service.
Missing saved support observations remain missing, never replaced by stubs.
--support-vision explicitly enables fresh pixel/jersey/role/goal reviews using
EMERGENT_LLM_KEY already in the operator's environment. No credentials are read
from the ZIP and no production report is rewritten. --output-dir checkpoints
the new traces, canonical document, corrected report and a checksummed ZIP.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import zipfile
import os

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ball_trajectory
import ball_contact_engine
import contact_role_resolver
import dense_identity_continuity
import dense_track_refinement
import fix10a_ball_proof_gate
import fix10a_goal_direction
import fix10b_runtime
import goal_review_scheduler
import jersey_consensus
import post_strike_intervention
import report_fact_authority
import shot_outcome_engine
import touch_graph
import unified_identity_authority
import verified_stats
import action_evidence_review
import fix10a_vision_providers
import physical_match_reconstruction as pmr
import video_timebase
from scripts import reference_action_review


def replay(path, video_detail=False, support_vision=False, output_dir=None, reference_cases=None):
    video_path = None
    api_key = os.environ.get("EMERGENT_LLM_KEY", "") if support_vision else ""
    if support_vision and not api_key:
        raise RuntimeError("--support-vision requires EMERGENT_LLM_KEY already in the process environment")
    if support_vision and fix10a_vision_providers.LlmChat is None:
        raise RuntimeError("The supporting vision SDK is unavailable")
    z = zipfile.ZipFile(path)
    for row in z.read("SHA256SUMS").decode().splitlines():
        digest, name = row.split(None, 1)
        if hashlib.sha256(z.read(name.strip().lstrip("*"))).hexdigest() != digest:
            raise ValueError("Evidence checksum mismatch")
    report = json.loads(z.read("report.json"))
    authority = report["unified_identity_authority"]
    traces = [json.loads(z.read(name)) for name in z.namelist() if name.startswith("traces/") and name.endswith(".json")]
    physical, requests = {"traces": [], "status": "ok"}, []
    inspection_plan = action_evidence_review.build_plan([t["window"] for t in traces], report["football_sequence_analysis"])
    if reference_cases is not None:
        reference_cases = reference_action_review.validate_cases(reference_cases)
        inspection_plan = reference_action_review.build_plan(traces, reference_cases)
    reference_sources = {j["dense_window_id"] for j in inspection_plan["jobs"]} if reference_cases is not None else None
    review_analysis = reference_action_review.search_hints(inspection_plan) if reference_cases is not None else report["football_sequence_analysis"]
    bundle = goal_provider = None
    detail_frames = 0
    with tempfile.TemporaryDirectory(prefix="evidence-replay-") as directory:
        cap = detector = None
        if video_detail or support_vision:
            import cv2
            import cv_detect
            cv2.setNumThreads(2)
            video_name = next(name for name in z.namelist() if name.startswith("video/") and name.endswith(".mp4"))
            video_path = Path(directory) / "source.mp4"
            video_path.write_bytes(z.read(video_name))
            expected_hash = (report.get("analysis_run_manifest") or {}).get("source_video_sha256")
            if expected_hash and hashlib.sha256(video_path.read_bytes()).hexdigest() != expected_hash:
                raise ValueError("Exported video does not match the analysis source hash")
            if support_vision:
                bundle = fix10a_vision_providers.build_shadow_providers(api_key, f"readonly-{report['id']}", str(video_path))
                goal_provider = fix10a_goal_direction.wrap_goal_geometry_provider(
                    bundle.goal_geometry_provider, api_key, f"readonly-{report['id']}", str(video_path))
            if video_detail:
                cap = cv2.VideoCapture(str(video_path))
                detector = cv_detect.PersonDetector()
                if not detector.ok:
                    raise RuntimeError("Local person/ball detector unavailable")
        try:
            for original in traces:
                review_this_window = reference_sources is None or original["trace_id"] in reference_sources
                frames = deepcopy(original["decoded_frames"])
                inspections, inspection_requests = [], []
                if bundle is not None:
                    for job in inspection_plan["jobs"]:
                        if job["dense_window_id"] != original["window"]["dense_window_id"] or not job["selected"]:
                            continue
                        observed = bundle.action_evidence_provider(str(video_path), job, frames)
                        applied = action_evidence_review.apply_observations(frames, observed, job["inspection_id"])
                        frames = applied["frames"]
                        inspection_requests.extend(applied["jersey_requests"])
                        inspections.append({**job, **observed, "added_ball_candidates": applied["added_ball_candidates"],
                                            "binding_rejections": applied["binding_rejections"]})
                if cap is not None:
                    for f in frames:
                        if f.get("ball_candidates"):
                            continue
                        ok, image, actual_s = video_timebase.read_frame_at(cap, f["media_ms"] / 1000, fps=cap.get(cv2.CAP_PROP_FPS))
                        if not ok or int(round(actual_s * 1000)) != f["media_ms"]:
                            continue
                        _people, balls = dense_track_refinement._detect_dense_people_and_ball(detector, image)
                        detailed = [b for b in balls if b.get("source") == "NATIVE_GROUND_BAND_DETECTOR"]
                        if detailed:
                            f["ball_candidates"] = detailed
                            detail_frames += 1
                frames = dense_identity_continuity.apply(frames, original["touch_graph"])["frames"]
                trajectory = ball_trajectory.reconstruct_ball_trajectory(frames)
                contacts = ball_contact_engine.resolve_contacts(ball_contact_engine.detect_contact_candidates(frames, trajectory))
                # Preserve separately verified Step-3 observations exported by
                # the live run; its weak support detector input is not in ZIP.
                ids = {c.get("contact_id") for c in contacts.get("contacts") or []}
                for c in original["contacts"].get("accepted") or []:
                    if c.get("contact_id") not in ids and str(c.get("contact_id") or "").startswith("touchcand_step3_"):
                        contacts.setdefault("accepted", []).append(deepcopy(c))
                        contacts.setdefault("contacts", []).append(deepcopy(c))
                graph = touch_graph.build_touch_graph(contacts, authority, frames)
                votes = {tid: row.get("votes") or [] for tid, row in original["jersey_consensus"].items()
                         if isinstance(row, dict)}
                if bundle is not None and inspection_requests:
                    fresh = bundle.jersey_vote_provider(str(video_path), inspection_requests)
                    for track, rows in fresh.items():
                        votes[track] = [*(votes.get(track) or []), *rows]
                jersey = jersey_consensus.apply_jersey_consensus(frames, graph, votes)
                frames, graph = jersey["window_evidence"], jersey["touch_graph"]
                graph = unified_identity_authority.apply_verified_jersey_handoff(authority, frames, graph, jersey["consensus_by_track"])
                shared = dense_identity_continuity.apply(frames, graph)
                frames, graph = shared["frames"], shared["touch_graph"]
                graph = contact_role_resolver.apply_contact_roles(graph, contacts, dense_frames=frames, ball_trajectory=trajectory)
                strikes = [*shot_outcome_engine.find_strike_releases(graph, trajectory),
                           *shot_outcome_engine.find_scoring_control_contacts(graph)]
                tracks = {s["strike_id"]: ball_trajectory.reconstruct_ball_trajectory_from_release_anchor(
                    frames, s.get("active_ball_anchor"), s.get("scene_id")) or trajectory for s in strikes}
                interventions = {s["strike_id"]: post_strike_intervention.detect_post_strike_intervention(
                    s, frames, tracks[s["strike_id"]]) for s in strikes}
                fresh_roles = bundle.role_evidence_provider(str(video_path), original["window"], strikes, graph, frames,
                    list(interventions.values())) if bundle is not None and review_this_window else {}
                outcomes = []
                for strike in strikes:
                    window = original["window"]
                    review = pmr._goal_clarification_eligibility(strike, strikes, graph, window)
                    trajectory_used = tracks[strike["strike_id"]]
                    old = min(original["outcome_evidence"], key=lambda o: abs(o["media_ms"] - strike["media_ms"]), default=None)
                    same_contact = bool(old and abs(old["media_ms"] - strike["media_ms"]) <= 50
                                        and old.get("strike_actor_track_id") == strike.get("player_track_id"))
                    geometry = old.get("goal_geometry_evidence") if same_contact else None
                    roles = {}
                    if same_contact and old.get("intervention_role", {}).get("status") == "VERIFIED":
                        roles[old.get("intervention", {}).get("player_track_id")] = old["intervention_role"]
                    a7 = interventions[strike["strike_id"]]
                    roles.update(fresh_roles)
                    relevant = reference_cases is None or any(j["scene_id"] == strike.get("scene_id")
                        and j["center_ms"] - 750 <= strike["media_ms"] <= j["center_ms"] + pmr.GOAL_REVIEW_CAUSAL_MAX_MS
                        for j in inspection_plan["jobs"])
                    if review.get("eligible") and relevant:
                        requests.append({"window": window, "strike": strike, "review": review, "touch_graph": graph,
                                         "eligibility": pmr._goal_review_eligibility(strike, strikes, graph),
                                         "track": trajectory_used, "roles": roles, "intervention": a7,
                                         "trace_id": original["trace_id"], "outcome_index": len(outcomes)})
                    outcome = shot_outcome_engine.reconstruct_post_strike_outcome(strike, trajectory_used, graph,
                                                                                 goal_geometry=geometry, role_evidence=roles)
                    outcome = post_strike_intervention.apply_intervention_evidence(outcome, a7, roles)
                    outcome = fix10a_goal_direction.apply_direction_gate(outcome, trajectory_used, geometry)
                    outcome = fix10a_ball_proof_gate.apply_ball_proof_gate(outcome, trajectory_used)
                    outcome["goal_review_eligibility"] = pmr._goal_review_eligibility(strike, strikes, graph)
                    outcome["goal_review_decision"] = review
                    outcomes.append(outcome)
                physical["traces"].append({**original, "decoded_frames": frames, "touch_graph": graph,
                                            "contacts": contacts, "ball_trajectory": trajectory,
                                            "action_inspections": inspections,
                                            "jersey_model_audits": jersey.get("model_audits_by_track") or {},
                                            "strike_evidence": strikes, "outcome_evidence": outcomes})
                physical["traces"][-1]["provider_adapter_errors"] = sorted(set(
                    [*(original.get("provider_adapter_errors") or []), *pmr._adapter_diagnostics([inspections, fresh_roles])]))
                if output_dir is not None:
                    checkpoint = Path(output_dir)
                    checkpoint.mkdir(parents=True, exist_ok=True)
                    (checkpoint / "physical_replay.json").write_text(json.dumps(physical, indent=2))
            requests, cross_window_context = pmr._apply_cross_window_review_context(requests, physical["traces"])
            physical["cross_window_evidence"] = cross_window_context
            ordered = goal_review_scheduler.ordered_requests(requests, review_analysis)
            if goal_provider is not None:
                by_id = {t["trace_id"]: t for t in physical["traces"]}
                for rank, job in enumerate(ordered):
                    geometry = goal_provider(job["window"], job["strike"])
                    outcome = shot_outcome_engine.reconstruct_post_strike_outcome(
                        job["strike"], job["track"], job["touch_graph"], goal_geometry=geometry, role_evidence=job["roles"])
                    outcome = post_strike_intervention.apply_intervention_evidence(outcome, job["intervention"], job["roles"])
                    outcome = fix10a_goal_direction.apply_direction_gate(outcome, job["track"], geometry)
                    outcome = fix10a_ball_proof_gate.apply_ball_proof_gate(outcome, job["track"])
                    outcome["goal_review_decision"] = {**job["review"], "report_priority_rank": rank}
                    outcome["goal_review_eligibility"] = pmr._goal_review_eligibility(job["strike"],
                        by_id[job["trace_id"]]["strike_evidence"], job["touch_graph"])
                    by_id[job["trace_id"]]["outcome_evidence"][job["outcome_index"]] = outcome
                    trace = by_id[job["trace_id"]]
                    trace["provider_adapter_errors"] = sorted(set([*trace["provider_adapter_errors"], *pmr._adapter_diagnostics(geometry)]))
                    if output_dir is not None:
                        (Path(output_dir) / "physical_replay.json").write_text(json.dumps(physical, indent=2))
            physical["traces"], _, feedback_plan = pmr.run_feedback_round(
                physical["traces"], str(video_path or ""), {}, review_analysis,
                report["football_scene_graph"], authority,
                action_evidence_provider=bundle.action_evidence_provider if bundle is not None else None,
                jersey_vote_provider=bundle.jersey_vote_provider if bundle is not None else None,
                role_evidence_provider=bundle.role_evidence_provider if bundle is not None else None,
                goal_geometry_provider=goal_provider, review_jobs=[{**j, "shot_track": {
                    "rows": j["track"], "source": "SAVED_REPLAY_TRAJECTORY", "seed_ms": None}} for j in requests],
                feedback_trace_ids=reference_sources)
            physical["evidence_feedback_plan"] = feedback_plan
            _, cross_window_context = pmr._apply_cross_window_review_context([], physical["traces"])
            physical["cross_window_evidence"] = cross_window_context
            if output_dir is not None:
                checkpoint = Path(output_dir)
                checkpoint.mkdir(parents=True, exist_ok=True)
                (checkpoint / "physical_replay.json").write_text(json.dumps(physical, indent=2))
        finally:
            if cap is not None:
                cap.release()
    physical["recall_coverage"] = report["fix10a_physical_summary"]["recall_coverage"]
    source = {"canonical_events": report["canonical_events"], "sequence_analysis": report["football_sequence_analysis"],
              "identity_authority": authority, "scene_graph": report["football_scene_graph"]}
    updated = fix10b_runtime.reconcile_unified_result(source, physical)
    canonical = updated["canonical_events"]
    coverage = deepcopy(updated["scoring_scan"]["physical_evidence_coverage"])
    if not report["football_scene_graph"].get("frames"):
        coverage.update(status="PARTIAL", complete=False)
        coverage["reasons"] = [*coverage["reasons"], "SOURCE_SCENE_GRAPH_FRAMES_NOT_EXPORTED"]
    scan = {**updated["scoring_scan"], "physical_evidence_coverage": coverage,
            "physical_recall_verification_complete": coverage["complete"]}
    report_input = {**report["full_report"], "canonical_events": canonical,
                    "analysis_authority": {"output": "FIX09C"}, "_scoring_scan": scan}
    repaired = verified_stats.apply_verified_stats_authority(report_input)
    unique = set()
    selected_clarifications = []
    for job in ordered:
        key = job["review"]["physical_review_id"]
        if job["review"]["lane"] == "CLARIFICATION" and key not in unique:
            unique.add(key)
            if len(selected_clarifications) < fix10a_goal_direction.MAX_GOAL_CLARIFICATIONS_PER_REPORT:
                selected_clarifications.append(job)
    attempts = {"action_inspections": getattr(bundle, "inspection_calls", 0), "jersey_reads": getattr(bundle, "jersey_calls", 0),
                "role_reads": getattr(bundle, "role_calls", 0), "goal_reads": getattr(bundle, "goal_calls", 0),
                "field_side_reads": getattr(goal_provider, "field_side_calls", 0)}
    result = {"report_id": report["id"], "model_request_attempts": sum(attempts.values()), "db_writes": 0,
            "support_vision_enabled": support_vision, "support_review_attempts": attempts,
            "native_detail_frames_added": detail_frames,
            "native_inspection": {
                "added_ball_proposals": sum(r.get("added_ball_candidates", 0) for t in physical["traces"] for r in t.get("action_inspections") or []),
                "neighbor_frame_observations": sum(len(r.get("native_neighbor_decoded_ms") or []) for t in physical["traces"] for r in t.get("action_inspections") or []),
                "neighbor_roi_attempts": sum(r.get("native_neighbor_roi_attempts", 0) for t in physical["traces"] for r in t.get("action_inspections") or []),
            },
            "before_counts": report["canonical_events"]["counts"], "after_counts": canonical["counts"],
            "identity_feedback": canonical.get("dense_identity_feedback"),
            "verified_frames_before": sum(f.get("global_target", {}).get("proof_eligible") is True for t in traces for f in t["decoded_frames"]),
            "verified_frames_after": sum(f.get("global_target", {}).get("proof_eligible") is True for t in physical["traces"] for f in t["decoded_frames"]),
            "clarifications_selected": [{"scene": j["window"]["scene_id"], "media_ms": j["strike"]["media_ms"]} for j in selected_clarifications],
            "report_fact_authority": repaired["report_fact_authority"],
            "shooting_score_after": repaired.get("technical", {}).get("shooting", {}).get("score"),
            "coverage": coverage,
            "inspection_plan": inspection_plan,
            "cross_window_evidence": cross_window_context,
            "evidence_feedback_plan": feedback_plan,
            "replay_backend_sha256": {
                **{p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(Path(__file__).resolve().parents[1].glob("*.py"))},
                "scripts/replay_report_evidence.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "scripts/reference_action_review.py": hashlib.sha256(Path(reference_action_review.__file__).read_bytes()).hexdigest(),
            },
            "limitation": ("Fresh supporting reviews requested against the exported video; inspect reader statuses and proof before accepting events. "
                           if support_vision else "Saved observations only. Newly scheduled support reviews have not been executed. ")
                          + "Original weak Step-3 detector proposals are absent. Replay does not certify full-video completeness."}
    if reference_cases is not None:
        result["reference_review"] = reference_action_review.assess(reference_cases, canonical, physical, inspection_plan)
    if output_dir is not None:
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        for name, value in [("replay_summary.json", result), ("reviewed_canonical.json", canonical), ("reviewed_full_report.json", repaired)]:
            (directory / name).write_text(json.dumps(value, indent=2))
        payloads = {name: (directory / name).read_bytes() for name in
                    ("physical_replay.json", "replay_summary.json", "reviewed_canonical.json", "reviewed_full_report.json")}
        payloads["source_reference.json"] = json.dumps({"report_id": report["id"],
            "source_zip_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "video_sha256": (report.get("analysis_run_manifest") or {}).get("source_video_sha256"), "db_writes": 0}).encode()
        if reference_cases is not None:
            payloads["reference_review.json"] = json.dumps(result["reference_review"], indent=2).encode()
            payloads["operator_reference_cases.json"] = json.dumps(reference_cases, indent=2).encode()
            (directory / "reference_review.json").write_bytes(payloads["reference_review.json"])
        payloads["manifest.json"] = json.dumps({"kind": "READ_ONLY_EVIDENCE_REPLAY", "report_id": report["id"],
            "db_writes": 0, "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
                                       for name, data in payloads.items()}}).encode()
        checksums = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(payloads.items()))
        with zipfile.ZipFile(directory / "reviewed-evidence.zip", "w", zipfile.ZIP_DEFLATED) as output:
            for name, data in payloads.items():
                output.writestr(name, data)
            output.writestr("SHA256SUMS", checksums)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("--video-detail", action="store_true")
    parser.add_argument("--support-vision", action="store_true", help="Use the operator's environment key for fresh bounded reviews; never writes to a DB")
    parser.add_argument("--output-dir", type=Path, help="Write review checkpoints and a checksummed evidence ZIP to this private directory")
    parser.add_argument("--cases-json", type=Path, help="Offline reference times and acceptance criteria; expected outcomes are never sent to readers")
    args = parser.parse_args()
    cases = json.loads(args.cases_json.read_text()) if args.cases_json else None
    result = replay(args.zip_path, args.video_detail, args.support_vision, args.output_dir, cases)
    print(json.dumps(result, indent=2))
    if cases is not None and not result["reference_review"]["all_verified"]:
        raise SystemExit(2)
