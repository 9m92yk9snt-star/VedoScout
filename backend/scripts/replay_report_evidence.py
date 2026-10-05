"""Offline regression replay of saved evidence. No DB, storage writes or models.

Runs physical contacts/identity/roles and canonical reconciliation from the
exported observations. Optional --video-detail decodes the same hash-verified
video and adds ground-band ball detections; it does not run a new model service.
Missing saved support observations remain missing, never replaced by stubs.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import zipfile

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


def replay(path, video_detail=False):
    z = zipfile.ZipFile(path)
    for row in z.read("SHA256SUMS").decode().splitlines():
        digest, name = row.split(None, 1)
        if hashlib.sha256(z.read(name.strip().lstrip("*"))).hexdigest() != digest:
            raise ValueError("Evidence checksum mismatch")
    report = json.loads(z.read("report.json"))
    authority = report["unified_identity_authority"]
    traces = [json.loads(z.read(name)) for name in z.namelist() if name.startswith("traces/") and name.endswith(".json")]
    physical, requests = {"traces": [], "status": "ok"}, []
    detail_frames = 0
    with tempfile.TemporaryDirectory(prefix="evidence-replay-") as directory:
        cap = detector = None
        if video_detail:
            import cv2
            import cv_detect
            cv2.setNumThreads(2)
            video_name = next(name for name in z.namelist() if name.startswith("video/") and name.endswith(".mp4"))
            video_path = Path(directory) / "source.mp4"
            video_path.write_bytes(z.read(video_name))
            cap = cv2.VideoCapture(str(video_path))
            detector = cv_detect.PersonDetector()
            if not detector.ok:
                raise RuntimeError("Local person/ball detector unavailable")
        try:
            for original in traces:
                frames = deepcopy(original["decoded_frames"])
                if cap is not None:
                    for f in frames:
                        if f.get("ball_candidates"):
                            continue
                        cap.set(cv2.CAP_PROP_POS_MSEC, f["media_ms"])
                        ok, image = cap.read()
                        if not ok:
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
                jersey = jersey_consensus.apply_jersey_consensus(frames, graph, votes)
                frames, graph = jersey["window_evidence"], jersey["touch_graph"]
                graph = unified_identity_authority.apply_verified_jersey_handoff(authority, frames, graph, jersey["consensus_by_track"])
                shared = dense_identity_continuity.apply(frames, graph)
                frames, graph = shared["frames"], shared["touch_graph"]
                graph = contact_role_resolver.apply_contact_roles(graph, contacts, dense_frames=frames, ball_trajectory=trajectory)
                strikes = [*shot_outcome_engine.find_strike_releases(graph, trajectory),
                           *shot_outcome_engine.find_scoring_control_contacts(graph)]
                outcomes = []
                for strike in strikes:
                    window = original["window"]
                    import physical_match_reconstruction as pmr
                    review = pmr._goal_clarification_eligibility(strike, strikes, graph, window)
                    if review.get("eligible"):
                        requests.append({"window": window, "strike": strike, "review": review})
                    anchored = ball_trajectory.reconstruct_ball_trajectory_from_release_anchor(
                        frames, strike.get("active_ball_anchor"), strike.get("scene_id"))
                    trajectory_used = anchored or trajectory
                    old = min(original["outcome_evidence"], key=lambda o: abs(o["media_ms"] - strike["media_ms"]), default=None)
                    same_contact = bool(old and abs(old["media_ms"] - strike["media_ms"]) <= 50
                                        and old.get("strike_actor_track_id") == strike.get("player_track_id"))
                    geometry = old.get("goal_geometry_evidence") if same_contact else None
                    roles = {}
                    if same_contact and old.get("intervention_role", {}).get("status") == "VERIFIED":
                        roles[old.get("intervention", {}).get("player_track_id")] = old["intervention_role"]
                    a7 = post_strike_intervention.detect_post_strike_intervention(strike, frames, trajectory_used)
                    outcome = shot_outcome_engine.reconstruct_post_strike_outcome(strike, trajectory_used, graph,
                                                                                 goal_geometry=geometry, role_evidence=roles)
                    outcome = post_strike_intervention.apply_intervention_evidence(outcome, a7, roles)
                    outcome = fix10a_goal_direction.apply_direction_gate(outcome, trajectory_used, geometry)
                    outcome = fix10a_ball_proof_gate.apply_ball_proof_gate(outcome, trajectory_used)
                    outcome["goal_review_eligibility"] = pmr._goal_review_eligibility(strike, strikes, graph)
                    outcomes.append(outcome)
                physical["traces"].append({**original, "decoded_frames": frames, "touch_graph": graph,
                                            "contacts": contacts, "ball_trajectory": trajectory,
                                            "strike_evidence": strikes, "outcome_evidence": outcomes})
        finally:
            if cap is not None:
                cap.release()
    physical["recall_coverage"] = report["fix10a_physical_summary"]["recall_coverage"]
    source = {"canonical_events": report["canonical_events"], "sequence_analysis": report["football_sequence_analysis"],
              "identity_authority": authority, "scene_graph": report["football_scene_graph"]}
    updated = fix10b_runtime.reconcile_unified_result(source, physical)
    canonical = updated["canonical_events"]
    repaired = report_fact_authority.apply(report["full_report"], canonical)
    ordered = goal_review_scheduler.ordered_requests(requests, source["sequence_analysis"])
    selected_clarifications = [j for j in ordered if j["review"]["lane"] == "CLARIFICATION"][:4]
    return {"report_id": report["id"], "model_service_calls": 0, "db_writes": 0,
            "native_detail_frames_added": detail_frames,
            "before_counts": report["canonical_events"]["counts"], "after_counts": canonical["counts"],
            "identity_feedback": canonical.get("dense_identity_feedback"),
            "verified_frames_before": sum(f.get("global_target", {}).get("proof_eligible") is True for t in traces for f in t["decoded_frames"]),
            "verified_frames_after": sum(f.get("global_target", {}).get("proof_eligible") is True for t in physical["traces"] for f in t["decoded_frames"]),
            "clarifications_selected": [{"scene": j["window"]["scene_id"], "media_ms": j["strike"]["media_ms"]} for j in selected_clarifications],
            "report_fact_authority": repaired["report_fact_authority"],
            "shooting_score_after": repaired.get("technical", {}).get("shooting", {}).get("score"),
            "coverage": updated["scoring_scan"]["physical_evidence_coverage"],
            "limitation": "Saved observations only. Newly scheduled support reviews have not been executed. Original weak Step-3 detector proposals are absent."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("--video-detail", action="store_true")
    args = parser.parse_args()
    print(json.dumps(replay(args.zip_path, args.video_detail), indent=2))
