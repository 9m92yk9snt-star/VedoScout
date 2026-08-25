"""FIX10A — physical match reconstruction orchestration.

Runs the bounded dense evidence stack A1→A8 over critical FIX09B windows.
This module is intentionally NOT a canonical event authority.  It may emit
physical contacts, touches, jersey evidence, interventions and goal-plane
crossing evidence, but it never promotes GOAL/ASSIST/scorer/stat truth.  That
reconciliation belongs to FIX10B and the existing B3 authority.
"""
from __future__ import annotations

from copy import deepcopy
import inspect

import ball_contact_engine
import ball_trajectory
import contact_role_resolver
import dense_replay
import dense_track_refinement
import event_trace
import fix10a_ball_proof_gate
import fix10a_goal_direction
import jersey_consensus
import post_strike_intervention
import shot_outcome_engine
import short_occlusion_contact_recovery
import touch_graph

VERSION = 1
SOURCE_ROLE = "CANONICAL_WEB_VIDEO"


def _safe_provider(provider, *args, default=None):
    if provider is None:
        return default
    try:
        return provider(*args)
    except Exception:
        return default


def _safe_role_provider(provider, video_path, window, strikes, touch_graph,
                        window_evidence, interventions, default=None):
    """Call new six-argument role providers without breaking old injections."""
    if provider is None:
        return default
    args5 = (video_path, window, strikes, touch_graph, window_evidence)
    try:
        signature = inspect.signature(provider)
        parameters = list(signature.parameters.values())
        accepts_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in parameters)
        positional = [
            p for p in parameters
            if p.kind in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
        ]
        if accepts_varargs or len(positional) >= 6:
            return provider(*args5, interventions)
        return provider(*args5)
    except Exception:
        return default


def _window_unresolved_reasons(contact_result, jersey_result, outcomes):
    reasons = []
    contact = contact_result if isinstance(contact_result, dict) else {}
    if contact.get("unresolved"):
        reasons.append("PHYSICAL_CONTACT_UNRESOLVED")
    if not contact.get("accepted"):
        reasons.append("NO_VERIFIED_PHYSICAL_CONTACT")
    jerseys = jersey_result if isinstance(jersey_result, dict) else {}
    for row in (jerseys.get("consensus_by_track") or {}).values():
        if isinstance(row, dict) and row.get("status") in {"UNRESOLVED", "UNKNOWN"}:
            reasons.append("JERSEY_IDENTITY_UNRESOLVED")
            break
    for out in outcomes or []:
        if not isinstance(out, dict):
            continue
        if out.get("physical_outcome") in {"UNRESOLVED", "UNRESOLVED_TERMINAL_VISIBILITY"}:
            reasons.append("POST_STRIKE_OUTCOME_UNRESOLVED")
        crossing = out.get("goal_plane_crossing") if isinstance(out.get("goal_plane_crossing"), dict) else {}
        if crossing.get("status") == "UNRESOLVED":
            reasons.append("GOAL_PLANE_CROSSING_UNRESOLVED")
    return list(dict.fromkeys(reasons))


def _source_meta(source_video, video_path):
    src = deepcopy(source_video) if isinstance(source_video, dict) else {}
    src.setdefault("role", SOURCE_ROLE)
    src.setdefault("path_role", "canonical_web")
    src.setdefault("video_path_supplied", bool(video_path))
    return src


def reconstruct_physical_match(
    video_path: str,
    sequence_plan: dict | None,
    sequence_analysis: dict | None,
    scene_graph: dict | None,
    identity_authority: dict | None,
    jersey_vote_provider=None,
    *,
    source_video: dict | None = None,
    goal_geometry_provider=None,
    role_evidence: dict | None = None,
    role_evidence_provider=None,
    detector_fn=None,
    camera_estimator=None,
    dense_frame_provider=None,
) -> dict:
    """Build bounded physical evidence without changing canonical truth."""
    plan = deepcopy(sequence_plan) if isinstance(sequence_plan, dict) else {}
    analysis = deepcopy(sequence_analysis) if isinstance(sequence_analysis, dict) else {}
    graph = deepcopy(scene_graph) if isinstance(scene_graph, dict) else {}
    authority = deepcopy(identity_authority) if isinstance(identity_authority, dict) else {}
    windows = dense_replay.select_critical_windows(plan, analysis)
    source = _source_meta(source_video, video_path)
    traces = []
    summaries = []
    window_rows = []
    unresolved_all = []

    for window in windows:
        try:
            if dense_frame_provider is None:
                dense_iter = dense_replay.iter_dense_frames(
                    str(video_path), int(window["start_ms"]), int(window["end_ms"])
                )
            else:
                dense_iter = dense_frame_provider(
                    str(video_path), int(window["start_ms"]), int(window["end_ms"])
                )

            refined = dense_track_refinement.refine_window(
                dense_iter, graph, authority, str(window.get("scene_id") or ""),
                detector_fn=detector_fn, camera_estimator=camera_estimator,
            )
            dense_frames = list(refined.get("frames") or []) if isinstance(refined, dict) else []
            trajectory = ball_trajectory.reconstruct_ball_trajectory(dense_frames)
            candidates = ball_contact_engine.detect_contact_candidates(dense_frames, trajectory)
            contact_result = ball_contact_engine.resolve_contacts(candidates)

            # FIX10A Step 3 is a separate, fail-closed recovery layer.  It does
            # not relax ordinary A4 gates or feed weak detector proposals into
            # A3.  Only an independently VERIFIED aggregate short-occlusion
            # recovery may be appended to the copied A4 result before A5.
            step3_recovery = short_occlusion_contact_recovery.recover_short_occlusion_contacts(
                dense_frames, trajectory, contact_result, video_path=str(video_path)
            )
            contact_result = short_occlusion_contact_recovery.apply_recovered_contacts(
                contact_result, step3_recovery
            )
            touches = touch_graph.build_touch_graph(contact_result, authority, dense_frames)
            touches = contact_role_resolver.apply_contact_roles(touches, contact_result)

            requests = jersey_consensus.select_jersey_review_requests(dense_frames, touches)
            votes_by_track = _safe_provider(
                jersey_vote_provider, str(video_path), deepcopy(requests), default={}
            )
            if not isinstance(votes_by_track, dict):
                votes_by_track = {}
            jersey_result = jersey_consensus.apply_jersey_consensus(dense_frames, touches, votes_by_track)
            dense_with_jersey = jersey_result.get("window_evidence") or dense_frames
            touch_with_jersey = jersey_result.get("touch_graph") or touches

            strikes = shot_outcome_engine.find_strike_releases(touch_with_jersey, trajectory)

            # Detect independent A7 intervention actors before role review. A7
            # intentionally bypasses A4/A5 Touch Graph truth, so waiting until
            # after role-provider selection would make hand/arm interventions
            # invisible to goalkeeper/outfield verification.
            a7_interventions = [
                post_strike_intervention.detect_post_strike_intervention(
                    strike, dense_with_jersey, trajectory
                )
                for strike in strikes
            ]
            a7_verified = sum(
                isinstance(row, dict) and row.get("status") == "VERIFIED"
                for row in a7_interventions
            )
            provider_roles = _safe_role_provider(
                role_evidence_provider, str(video_path), deepcopy(window), deepcopy(strikes),
                deepcopy(touch_with_jersey), deepcopy(dense_with_jersey),
                deepcopy(a7_interventions), default={},
            )
            window_roles = deepcopy(provider_roles) if isinstance(provider_roles, dict) else {}
            if isinstance(role_evidence, dict):
                window_roles.update(deepcopy(role_evidence))

            outcomes = []
            for strike, a7 in zip(strikes, a7_interventions):
                goal_geometry = _safe_provider(
                    goal_geometry_provider, deepcopy(window), deepcopy(strike), default=None
                )
                outcome = shot_outcome_engine.reconstruct_post_strike_outcome(
                    strike, trajectory, touch_with_jersey,
                    goal_geometry=goal_geometry, role_evidence=window_roles,
                )
                outcome = post_strike_intervention.apply_intervention_evidence(
                    outcome, a7, window_roles
                )
                outcome = fix10a_goal_direction.apply_direction_gate(outcome, trajectory, goal_geometry)
                outcome = fix10a_ball_proof_gate.apply_ball_proof_gate(outcome, trajectory)
                outcomes.append(outcome)

            unresolved = _window_unresolved_reasons(contact_result, jersey_result, outcomes)
            unresolved_all.extend(unresolved)
            trace_id = str(window.get("dense_window_id") or "dense_unknown")
            trace = event_trace.build_event_trace(
                trace_id=trace_id, source_video=source, window=window,
                dense_frames=dense_with_jersey, ball_trajectory=trajectory,
                contact_result=contact_result, touch_graph=touch_with_jersey,
                jersey_consensus=jersey_result, strike_evidence=strikes,
                outcome_evidence=outcomes, sequence_analysis=analysis,
                contradictions=[], unresolved_reasons=unresolved,
            )
            summary = event_trace.compact_trace_summary(trace)
            traces.append(trace)
            summaries.append(summary)
            window_rows.append({
                "dense_window_id": trace_id,
                "scene_id": window.get("scene_id"),
                "start_ms": window.get("start_ms"),
                "end_ms": window.get("end_ms"),
                "status": "ok",
                "refined_frames": len(dense_frames),
                "ball_rows": len(trajectory),
                "accepted_contacts": len(contact_result.get("accepted") or []),
                "unresolved_contacts": len(contact_result.get("unresolved") or []),
                "step3_recovered_contacts": int(
                    ((step3_recovery.get("metrics") or {}).get("verified") or 0)
                ),
                "touches": len(touch_with_jersey.get("touches") or []),
                "jersey_requests": len(requests),
                "role_evidence_tracks": len(window_roles),
                "strikes": len(strikes),
                "a7_verified_interventions": a7_verified,
                "outcomes": len(outcomes),
                "unresolved_reasons": unresolved,
            })
        except Exception as exc:
            reason = f"WINDOW_RECONSTRUCTION_ERROR:{type(exc).__name__}"
            unresolved_all.append(reason)
            window_rows.append({
                "dense_window_id": window.get("dense_window_id"),
                "scene_id": window.get("scene_id"),
                "start_ms": window.get("start_ms"),
                "end_ms": window.get("end_ms"),
                "status": "error", "reason": reason,
            })

    ok_windows = sum(row.get("status") == "ok" for row in window_rows)
    status = (
        "no_critical_windows" if not windows
        else "ok" if ok_windows == len(windows)
        else "partial" if ok_windows else "error"
    )
    return {
        "version": VERSION,
        "status": status,
        "timebase": "canonical_media_ms",
        "source_role": SOURCE_ROLE,
        "source_video": source,
        "windows": window_rows,
        "trace_summaries": summaries,
        "traces": traces,
        "unresolved_reasons": list(dict.fromkeys(unresolved_all)),
        "metrics": {
            "critical_windows": len(windows),
            "windows_ok": ok_windows,
            "windows_failed": len(windows) - ok_windows,
            "traces": len(traces),
            "accepted_contacts": sum(int(x.get("accepted_contacts") or 0) for x in window_rows),
            "step3_recovered_contacts": sum(
                int(x.get("step3_recovered_contacts") or 0) for x in window_rows
            ),
            "touches": sum(int(x.get("touches") or 0) for x in window_rows),
            "physical_strikes": sum(int(x.get("strikes") or 0) for x in window_rows),
            "a7_verified_interventions": sum(int(x.get("a7_verified_interventions") or 0) for x in window_rows),
        },
        # Explicitly absent by contract: canonical_events, event_ledger,
        # verified_stats, goals, assists, scorer or report mutation.
    }
