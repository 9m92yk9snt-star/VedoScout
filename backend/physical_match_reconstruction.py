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
import traceback
import time

import ball_contact_engine
import ball_trajectory
import contact_role_resolver
import dense_replay
import dense_track_refinement
import event_trace
import fix10a_ball_proof_gate
import fix10a_goal_direction
import full_video_event_recall
import jersey_consensus
import post_strike_intervention
import shot_outcome_engine
import short_occlusion_contact_recovery
import touch_graph
import unified_identity_authority
import dense_identity_continuity
import goal_review_scheduler
import action_evidence_review

VERSION = 1
SOURCE_ROLE = "CANONICAL_WEB_VIDEO"
MAX_ERROR_MESSAGE_CHARS = 400
MAX_TRACEBACK_CHARS = 5000
GLOBAL_TARGET_ID = "GLOBAL_TARGET"
GOAL_REVIEW_CAUSAL_MAX_MS = 5200
GOAL_REVIEW_TEAM_CONFIDENCE_MIN = 0.70


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _strike_is_verified_release(strike):
    return bool(
        isinstance(strike, dict)
        and strike.get("status") == "VERIFIED_PHYSICAL_RELEASE"
        and strike.get("proof_eligible") is True
        and isinstance(strike.get("player_track_id"), str)
        and _num(strike.get("media_ms"))
    )


def _strike_is_goal_review_contact(strike):
    return bool(
        isinstance(strike, dict)
        and strike.get("status") in {
            "VERIFIED_PHYSICAL_RELEASE",
            "VERIFIED_PHYSICAL_SCORING_CONTACT",
        }
        and strike.get("proof_eligible") is True
        and isinstance(strike.get("player_track_id"), str)
        and _num(strike.get("media_ms"))
    )


def _touch_for_strike(strike, touch_graph):
    touch_id = strike.get("touch_id") if isinstance(strike, dict) else None
    if not isinstance(touch_id, str):
        return None
    graph = touch_graph if isinstance(touch_graph, dict) else {}
    return next(
        (
            touch for touch in graph.get("touches") or []
            if isinstance(touch, dict) and touch.get("touch_id") == touch_id
        ),
        None,
    )


def _verified_target_team_touch(touch):
    relation = (
        touch.get("team_relation")
        if isinstance(touch, dict) and isinstance(touch.get("team_relation"), dict)
        else {}
    )
    confidence = relation.get("confidence")
    return bool(
        isinstance(touch, dict)
        and touch.get("status") == "VERIFIED"
        and touch.get("proof_eligible") is True
        and relation.get("status") == "SUPPORTING"
        and relation.get("team") == "target_team"
        and _num(confidence)
        and float(confidence) >= GOAL_REVIEW_TEAM_CONFIDENCE_MIN
    )


def _goal_review_eligibility(strike, strikes, touch_graph):
    """Bound expensive goal review to a target-owned scoring chain.

    The goal provider is supporting vision, not a full-video event detector.
    Reviewing every physical contact both wastes its report budget and lets an
    unrelated opponent action starve later target evidence. A review is
    therefore allowed only for a verified target scoring contact, or for a verified
    target-team release within the direct-assist horizon of a prior verified
    target release in the same scene. Missing team/identity proof fails closed.
    """
    if not _strike_is_goal_review_contact(strike):
        return {
            "eligible": False,
            "reason": "CONTACT_NOT_VERIFIED_PROOF_ELIGIBLE_FOR_GOAL_REVIEW",
        }
    strike_ms = int(strike["media_ms"])
    scene = strike.get("scene_id")
    if strike.get("global_target_id") == GLOBAL_TARGET_ID:
        contact_kind = (
            "SCORING_CONTACT"
            if strike.get("status") == "VERIFIED_PHYSICAL_SCORING_CONTACT"
            else "RELEASE"
        )
        return {
            "eligible": True,
            "reason": f"VERIFIED_GLOBAL_TARGET_{contact_kind}",
            "target_release_ms": strike_ms,
        }

    prior_target_releases = [
        row for row in strikes or []
        if _strike_is_verified_release(row)
        and row.get("global_target_id") == GLOBAL_TARGET_ID
        and row.get("scene_id") == scene
        and int(row["media_ms"]) < strike_ms
        and strike_ms - int(row["media_ms"]) <= GOAL_REVIEW_CAUSAL_MAX_MS
    ]
    if not prior_target_releases:
        return {
            "eligible": False,
            "reason": "NO_PRIOR_TARGET_RELEASE_IN_CAUSAL_HORIZON",
        }
    scoring_touch = _touch_for_strike(strike, touch_graph)
    if not _verified_target_team_touch(scoring_touch):
        relation = (
            scoring_touch.get("team_relation")
            if isinstance(scoring_touch, dict)
            and isinstance(scoring_touch.get("team_relation"), dict)
            else {}
        )
        return {
            "eligible": False,
            "reason": "DOWNSTREAM_RELEASE_TARGET_TEAM_UNVERIFIED",
            "team_status": relation.get("status"),
            "team": relation.get("team"),
            "team_confidence": relation.get("confidence"),
        }
    target_release = max(prior_target_releases, key=lambda row: int(row["media_ms"]))
    relation = scoring_touch.get("team_relation") or {}
    return {
        "eligible": True,
        "reason": "VERIFIED_TARGET_TEAM_RELEASE_AFTER_TARGET_PASS",
        "target_release_ms": int(target_release["media_ms"]),
        "elapsed_ms": strike_ms - int(target_release["media_ms"]),
        "team_confidence": float(relation["confidence"]),
    }


def _skipped_goal_review(eligibility):
    return {
        "status": "UNRESOLVED",
        "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
        "line_by_ms": [],
        "field_side_status": "UNRESOLVED",
        "field_side_by_ms": [],
        "reason": "GOAL_REVIEW_NOT_CAUSALLY_ELIGIBLE",
        "eligibility": deepcopy(eligibility) if isinstance(eligibility, dict) else {},
        "visual_crossing_audit": {
            "status": "UNRESOLVED",
            "confidence": "low",
            "reason": "GOAL_REVIEW_NOT_CAUSALLY_ELIGIBLE",
        },
    }


def _goal_clarification_eligibility(strike, strikes, touch_graph, window):
    """Review physical outcomes before uncertain target/team attribution.

    This is permission to inspect pixels, never permission to register a target
    event. Verified opponents are excluded; publication still uses FIX10B.
    """
    ownership = _goal_review_eligibility(strike, strikes, touch_graph)
    if ownership.get("eligible") is True:
        return {**ownership, "lane": "VERIFIED_CHAIN"}
    if not _strike_is_goal_review_contact(strike):
        return {**ownership, "lane": "NONE"}
    touch = _touch_for_strike(strike, touch_graph) or {}
    relation = touch.get("team_relation") or {}
    confidence = relation.get("confidence")
    if (relation.get("team") == "opponent" and _num(confidence)
            and float(confidence) >= GOAL_REVIEW_TEAM_CONFIDENCE_MIN):
        return {"eligible": False, "lane": "NONE", "reason": "VERIFIED_OPPONENT_REVIEW_EXCLUDED"}
    if ownership.get("reason") == "DOWNSTREAM_RELEASE_TARGET_TEAM_UNVERIFIED":
        return {"eligible": True, "lane": "CLARIFICATION", "reason": "TARGET_PASS_DOWNSTREAM_TEAM_UNRESOLVED"}
    # Both window sources are target-relevant, constructed before outcome
    # classification. No expected goal/assist label is sent to the reader.
    if window.get("recall_window") or window.get("source_sequence_ids") or window.get("source_action_ids"):
        return {"eligible": True, "lane": "CLARIFICATION", "reason": "TARGET_WINDOW_OWNER_UNRESOLVED"}
    return {**ownership, "lane": "NONE"}


def _safe_provider(provider, *args, default=None, diagnostics=None, name="provider"):
    started = time.monotonic()
    record = {"provider": name}
    if provider is None:
        record.update(status="UNAVAILABLE", reason="PROVIDER_NOT_CONFIGURED")
        value = default
    else:
        try:
            value = provider(*args)
            record.update(status="NO_EVIDENCE" if value is None else "COMPLETED")
        except Exception as exc:
            value = default
            # Exception text may contain credentials/transport URLs. Preserve
            # operational error type without copying that text to the report.
            record.update(status="ERROR", reason="PROVIDER_EXCEPTION", error_type=type(exc).__name__)
    record["elapsed_seconds"] = round(max(0.0, time.monotonic() - started), 3)
    if diagnostics is not None:
        diagnostics.append(record)
    return value


def _adapter_diagnostics(value):
    """Readers can catch SDK failures themselves; keep those outcomes explicit."""
    if isinstance(value, dict):
        errors = [str(value.get(key) or "").lower() for key in ("reason", "field_side_reason", "proof_reason")]
        errors = [reason for reason in errors if "reader_error" in reason or "reader_unavailable" in reason or "reader_invalid" in reason]
        if errors:
            return errors
        return [reason for item in value.values() for reason in _adapter_diagnostics(item)]
    if isinstance(value, list):
        return [reason for item in value for reason in _adapter_diagnostics(item)]
    return []


def _safe_role_provider(provider, video_path, window, strikes, touch_graph,
                        window_evidence, interventions, default=None, diagnostics=None):
    """Call new six-argument role providers without breaking old injections."""
    if provider is None:
        return _safe_provider(None, default=default, diagnostics=diagnostics, name="intervention_role")
    args5 = (video_path, window, strikes, touch_graph, window_evidence)

    def call():
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
    return _safe_provider(call, default=default, diagnostics=diagnostics, name="intervention_role")


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


def _window_error(exc: Exception, stage: str) -> dict:
    """Return bounded, persistence-safe diagnostics for one failed shadow window."""
    message = str(exc or "")[:MAX_ERROR_MESSAGE_CHARS]
    try:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    except Exception:
        tb = ""
    if len(tb) > MAX_TRACEBACK_CHARS:
        tb = tb[-MAX_TRACEBACK_CHARS:]
    return {
        "error_stage": str(stage or "unknown")[:120],
        "error_type": type(exc).__name__,
        "error_message": message,
        "error_traceback": tb,
    }


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
    action_evidence_provider=None,
    detector_fn=None,
    camera_estimator=None,
    dense_frame_provider=None,
    trace_callback=None,
) -> dict:
    """Build bounded physical evidence without changing canonical truth."""
    plan = deepcopy(sequence_plan) if isinstance(sequence_plan, dict) else {}
    analysis = deepcopy(sequence_analysis) if isinstance(sequence_analysis, dict) else {}
    graph = deepcopy(scene_graph) if isinstance(scene_graph, dict) else {}
    authority = deepcopy(identity_authority) if isinstance(identity_authority, dict) else {}
    semantic_windows = dense_replay.select_critical_windows(plan, analysis)
    recall_plan = full_video_event_recall.build_physical_recall_windows(plan, graph)
    recall_windows = recall_plan.get("windows") or []
    windows = full_video_event_recall.union_dense_windows(
        semantic_windows,
        recall_windows,
    )
    inspection_plan = action_evidence_review.build_plan(windows, analysis)
    source = _source_meta(source_video, video_path)
    traces = []
    summaries = []
    window_rows = []
    unresolved_all = []
    review_jobs = []

    for window in windows:
        stage = "window_setup"
        try:
            provider_diagnostics = []
            stage = "dense_replay"
            if dense_frame_provider is None:
                dense_iter = dense_replay.iter_dense_frames(
                    str(video_path), int(window["start_ms"]), int(window["end_ms"])
                )
            else:
                dense_iter = dense_frame_provider(
                    str(video_path), int(window["start_ms"]), int(window["end_ms"])
                )

            stage = "dense_track_refinement"
            refined = dense_track_refinement.refine_window(
                dense_iter, graph, authority, str(window.get("scene_id") or ""),
                detector_fn=detector_fn, camera_estimator=camera_estimator,
            )
            dense_frames = list(refined.get("frames") or []) if isinstance(refined, dict) else []
            dense_frames = dense_identity_continuity.apply(dense_frames)["frames"]

            # Inspection admission precedes physical/identity proof. Pixel
            # proposals do not become contacts or target identity directly:
            # ball locations need a fresh native detector match, and jersey
            # crops still use the separate multi-frame number authority.
            stage = "action_pixel_inspection"
            inspection_rows, inspection_requests = [], []
            for job in inspection_plan["jobs"]:
                if job["dense_window_id"] != window["dense_window_id"]:
                    continue
                if not job["selected"]:
                    inspection_rows.append({**job, "status": "DEFERRED", "reason": "ACTION_INSPECTION_BUDGET_EXHAUSTED"})
                    continue
                if action_evidence_provider is None:
                    inspection_rows.append({**job, "status": "NOT_CONFIGURED"})
                    continue
                observation = _safe_provider(
                    action_evidence_provider, str(video_path), deepcopy(job), deepcopy(dense_frames),
                    default={"status": "ERROR", "reason": "action_pixel_reader_error", "frames": []},
                    diagnostics=provider_diagnostics, name="action_pixels")
                observation = observation if isinstance(observation, dict) else {"status": "NO_EVIDENCE", "frames": []}
                applied = action_evidence_review.apply_observations(dense_frames, observation, job["inspection_id"])
                dense_frames = applied["frames"]
                inspection_requests.extend(applied["jersey_requests"])
                inspection_rows.append({**job, **observation, "added_ball_candidates": applied["added_ball_candidates"],
                                        "binding_rejections": applied["binding_rejections"],
                                        "independent_jersey_crops": len(applied["jersey_requests"])})

            stage = "ball_trajectory"
            trajectory = ball_trajectory.reconstruct_ball_trajectory(dense_frames)

            stage = "ball_contact_candidates"
            candidates = ball_contact_engine.detect_contact_candidates(dense_frames, trajectory)

            stage = "ball_contact_resolution"
            contact_result = ball_contact_engine.resolve_contacts(candidates)

            stage = "short_occlusion_recovery"
            step3_recovery = short_occlusion_contact_recovery.recover_short_occlusion_contacts(
                dense_frames, trajectory, contact_result, video_path=str(video_path)
            )

            stage = "short_occlusion_apply"
            contact_result = short_occlusion_contact_recovery.apply_recovered_contacts(
                contact_result, step3_recovery
            )

            stage = "touch_graph"
            touches = touch_graph.build_touch_graph(contact_result, authority, dense_frames)

            stage = "contact_role_resolution"
            touches = contact_role_resolver.apply_contact_roles(
                touches, contact_result,
                dense_frames=dense_frames, ball_trajectory=trajectory,
            )

            stage = "jersey_request_selection"
            requests = inspection_requests + jersey_consensus.select_jersey_review_requests(dense_frames, touches)

            stage = "jersey_provider"
            votes_by_track = _safe_provider(
                jersey_vote_provider, str(video_path), deepcopy(requests), default={},
                diagnostics=provider_diagnostics, name="jersey",
            )
            if not isinstance(votes_by_track, dict):
                votes_by_track = {}

            stage = "jersey_consensus"
            jersey_result = jersey_consensus.apply_jersey_consensus(dense_frames, touches, votes_by_track)
            dense_with_jersey = jersey_result.get("window_evidence") or dense_frames
            touch_with_jersey = jersey_result.get("touch_graph") or touches

            stage = "verified_jersey_identity_handoff"
            touch_with_jersey = unified_identity_authority.apply_verified_jersey_handoff(
                authority,
                dense_with_jersey,
                touch_with_jersey,
                jersey_result.get("consensus_by_track") or {},
            )
            shared_identity = dense_identity_continuity.apply(dense_with_jersey, touch_with_jersey)
            dense_with_jersey = shared_identity["frames"]
            touch_with_jersey = shared_identity["touch_graph"]
            # Re-evaluate delayed release roles after a safe local-track re-ID;
            # physical role truth itself remains independent of jersey evidence.
            touch_with_jersey = contact_role_resolver.apply_contact_roles(
                touch_with_jersey, contact_result,
                dense_frames=dense_with_jersey, ball_trajectory=trajectory,
            )
            jersey_result["touch_graph"] = deepcopy(touch_with_jersey)
            jersey_result["identity_handoff"] = deepcopy(
                touch_with_jersey.get("jersey_identity_handoff") or {}
            )

            stage = "strike_detection"
            release_strikes = shot_outcome_engine.find_strike_releases(
                touch_with_jersey, trajectory
            )
            scoring_contacts = shot_outcome_engine.find_scoring_control_contacts(
                touch_with_jersey
            )
            all_goal_contacts = sorted(
                [*release_strikes, *scoring_contacts],
                key=lambda row: (int(row.get("media_ms") or 0), str(row.get("strike_id") or "")),
            )
            # Control contacts are admitted only when the same causal gate that
            # protects the goal-review budget can already bind them to the
            # analysed player's scoring chain. Releases remain available for
            # physical non-goal outcomes such as saves.
            scoring_contacts = [
                row for row in scoring_contacts
                if _goal_clarification_eligibility(
                    row, all_goal_contacts, touch_with_jersey, window
                ).get("eligible") is True
            ]
            strikes = sorted(
                [*release_strikes, *scoring_contacts],
                key=lambda row: (int(row.get("media_ms") or 0), str(row.get("strike_id") or "")),
            )

            # A verified ball-after-contact anchor is the identity seed for
            # this strike. Reconstruct one bounded path from it and pass that
            # same path through intervention, outcome, direction, and proof
            # gates. Falling back to the window-global path after a valid seed
            # would silently reattach this strike to a competing ball.
            shot_trajectories = []
            for strike in strikes:
                anchor = strike.get("active_ball_anchor") if isinstance(strike, dict) else None
                anchored_path = ball_trajectory.reconstruct_ball_trajectory_from_release_anchor(
                    dense_with_jersey, anchor, strike.get("scene_id")
                )
                uses_anchor = bool(anchored_path)
                selected_path = anchored_path if uses_anchor else trajectory
                shot_trajectories.append({
                    "rows": selected_path,
                    "source": "VERIFIED_RELEASE_ANCHOR" if uses_anchor else "WINDOW_GLOBAL_TRAJECTORY",
                    "seed_ms": int(anchor["media_ms"]) if uses_anchor else None,
                })

            stage = "intervention_detection"
            a7_interventions = [
                post_strike_intervention.detect_post_strike_intervention(
                    strike, dense_with_jersey, shot_track["rows"]
                )
                for strike, shot_track in zip(strikes, shot_trajectories)
            ]
            a7_verified = sum(
                isinstance(row, dict) and row.get("status") == "VERIFIED"
                for row in a7_interventions
            )

            stage = "role_provider"
            provider_roles = _safe_role_provider(
                role_evidence_provider, str(video_path), deepcopy(window), deepcopy(strikes),
                deepcopy(touch_with_jersey), deepcopy(dense_with_jersey),
                deepcopy(a7_interventions), default={},
                diagnostics=provider_diagnostics,
            )
            window_roles = deepcopy(provider_roles) if isinstance(provider_roles, dict) else {}
            if isinstance(role_evidence, dict):
                window_roles.update(deepcopy(role_evidence))

            outcomes = []
            goal_reviews_requested = 0
            goal_reviews_skipped = 0
            goal_clarifications_requested = 0
            for strike, a7, shot_track in zip(strikes, a7_interventions, shot_trajectories):
                stage = "goal_review_eligibility"
                eligibility = _goal_review_eligibility(
                    strike, strikes, touch_with_jersey
                )
                review = _goal_clarification_eligibility(strike, strikes, touch_with_jersey, window)
                if review.get("eligible") is True:
                    stage = "goal_review_scheduling"
                    request_strike = deepcopy(strike)
                    request_strike["_review_lane"] = review["lane"]
                    # All physical windows are inspected before the bounded
                    # provider budget is spent. Preliminary traces remain
                    # durable while the later global review phase is running.
                    goal_geometry = {"status": "UNRESOLVED", "reason": "GOAL_REVIEW_PENDING"}
                    review_jobs.append({
                        "window": window, "strike": request_strike, "review": review,
                        "eligibility": eligibility, "shot_track": shot_track,
                        "touch_graph": touch_with_jersey, "roles": window_roles,
                        "intervention": a7, "outcome_index": len(outcomes),
                        "diagnostics": provider_diagnostics,
                    })
                    goal_reviews_requested += 1
                    goal_clarifications_requested += int(review["lane"] == "CLARIFICATION")
                else:
                    goal_geometry = _skipped_goal_review(eligibility)
                    goal_reviews_skipped += 1

                stage = "shot_outcome_reconstruction"
                outcome = shot_outcome_engine.reconstruct_post_strike_outcome(
                    strike, shot_track["rows"], touch_with_jersey,
                    goal_geometry=goal_geometry, role_evidence=window_roles,
                )
                outcome["goal_review_decision"] = review
                outcome["ball_trajectory_source"] = shot_track["source"]
                outcome["ball_trajectory_seed_ms"] = shot_track["seed_ms"]
                outcome["ball_trajectory_points"] = [
                    {
                        "media_ms": int(row["media_ms"]),
                        "state": row.get("state"),
                        "box": deepcopy(row.get("box")),
                        "proof_eligible": row.get("proof_eligible") is True,
                        "provenance": row.get("provenance"),
                    }
                    for row in shot_track["rows"]
                    if isinstance(row, dict) and row.get("state") == "MEASURED"
                ]

                stage = "intervention_apply"
                outcome = post_strike_intervention.apply_intervention_evidence(
                    outcome, a7, window_roles
                )

                stage = "goal_direction_gate"
                outcome = fix10a_goal_direction.apply_direction_gate(
                    outcome, shot_track["rows"], goal_geometry
                )

                stage = "ball_proof_gate"
                outcome = fix10a_ball_proof_gate.apply_ball_proof_gate(
                    outcome, shot_track["rows"]
                )
                outcome["goal_review_eligibility"] = deepcopy(eligibility)
                outcomes.append(outcome)

            stage = "window_unresolved_summary"
            unresolved = _window_unresolved_reasons(contact_result, jersey_result, outcomes)
            unresolved_all.extend(unresolved)
            trace_id = str(window.get("dense_window_id") or "dense_unknown")

            stage = "event_trace"
            trace = event_trace.build_event_trace(
                trace_id=trace_id, source_video=source, window=window,
                dense_frames=dense_with_jersey, ball_trajectory=trajectory,
                contact_result=contact_result, touch_graph=touch_with_jersey,
                jersey_consensus=jersey_result, strike_evidence=strikes,
                outcome_evidence=outcomes, sequence_analysis=analysis,
                contradictions=[], unresolved_reasons=unresolved,
            )
            adapter_errors = _adapter_diagnostics([votes_by_track, window_roles,
                                                  [o.get("goal_geometry_evidence") for o in outcomes]])
            trace["provider_diagnostics"] = provider_diagnostics
            trace["action_inspections"] = inspection_rows
            trace["jersey_model_audits"] = jersey_result.get("model_audits_by_track") or {}
            trace["provider_adapter_errors"] = sorted(set(adapter_errors + _adapter_diagnostics(inspection_rows)))
            trace["goal_review_phase"] = "pending" if any(
                o.get("goal_geometry_evidence", {}).get("reason") == "GOAL_REVIEW_PENDING"
                for o in outcomes) else "complete"

            stage = "trace_summary"
            summary = event_trace.compact_trace_summary(trace)
            traces.append(trace)
            summaries.append(summary)
            if trace_callback is not None:
                try:
                    trace_callback(trace)
                except Exception as exc:
                    # An audit delivery problem cannot invalidate physical
                    # evidence that has already been reconstructed.
                    trace["incremental_storage_error_type"] = type(exc).__name__
            window_rows.append({
                "dense_window_id": trace_id,
                "scene_id": window.get("scene_id"),
                "start_ms": window.get("start_ms"),
                "end_ms": window.get("end_ms"),
                "status": "ok",
                "recall_window": bool(window.get("recall_window")),
                "window_reasons": list(window.get("reasons") or []),
                "refined_frames": len(dense_frames),
                "ball_rows": len(trajectory),
                "accepted_contacts": len(contact_result.get("accepted") or []),
                "unresolved_contacts": len(contact_result.get("unresolved") or []),
                "step3_recovered_contacts": int(
                    ((step3_recovery.get("metrics") or {}).get("verified") or 0)
                ),
                "touches": len(touch_with_jersey.get("touches") or []),
                "jersey_requests": len(requests),
                "action_inspections": len(inspection_rows),
                "inspection_ball_candidates": sum(r.get("added_ball_candidates", 0) for r in inspection_rows),
                "inspection_native_neighbor_frames": sum(len(r.get("native_neighbor_decoded_ms") or []) for r in inspection_rows),
                "inspection_native_roi_attempts": sum(r.get("native_neighbor_roi_attempts", 0) for r in inspection_rows),
                "role_evidence_tracks": len(window_roles),
                "strikes": len(strikes),
                "release_strikes": len(release_strikes),
                "scoring_control_contacts": len(scoring_contacts),
                "a7_verified_interventions": a7_verified,
                "outcomes": len(outcomes),
                "goal_reviews_requested": goal_reviews_requested,
                "goal_reviews_skipped": goal_reviews_skipped,
                "goal_clarifications_requested": goal_clarifications_requested,
                "provider_diagnostics": provider_diagnostics,
                "provider_adapter_errors": sorted(set(adapter_errors)),
                "unresolved_reasons": unresolved,
            })
        except Exception as exc:
            reason = f"WINDOW_RECONSTRUCTION_ERROR:{type(exc).__name__}"
            unresolved_all.append(reason)
            diagnostic = _window_error(exc, stage)
            window_rows.append({
                "dense_window_id": window.get("dense_window_id"),
                "scene_id": window.get("scene_id"),
                "start_ms": window.get("start_ms"),
                "end_ms": window.get("end_ms"),
                "status": "error",
                "recall_window": bool(window.get("recall_window")),
                "window_reasons": list(window.get("reasons") or []),
                "reason": reason,
                **diagnostic,
            })

    traces_by_window = {t["trace_id"]: t for t in traces}
    review_jobs = [job for job in review_jobs
                   if job["window"].get("dense_window_id") in traces_by_window]
    scheduled_jobs = goal_review_scheduler.ordered_requests(review_jobs, analysis)
    for rank, job in enumerate(scheduled_jobs):
        trace = traces_by_window[job["window"]["dense_window_id"]]
        try:
            geometry = _safe_provider(
                goal_geometry_provider, deepcopy(job["window"]), deepcopy(job["strike"]),
                default=None, diagnostics=trace["provider_diagnostics"], name="goal_geometry")
            track = job["shot_track"]
            outcome = shot_outcome_engine.reconstruct_post_strike_outcome(
                job["strike"], track["rows"], job["touch_graph"],
                goal_geometry=geometry, role_evidence=job["roles"])
            outcome["goal_review_decision"] = {**job["review"], "report_priority_rank": rank}
            outcome["ball_trajectory_source"] = track["source"]
            outcome["ball_trajectory_seed_ms"] = track["seed_ms"]
            previous = trace["outcome_evidence"][job["outcome_index"]]
            outcome["ball_trajectory_points"] = previous.get("ball_trajectory_points") or []
            outcome = post_strike_intervention.apply_intervention_evidence(
                outcome, job["intervention"], job["roles"])
            outcome = fix10a_goal_direction.apply_direction_gate(outcome, track["rows"], geometry)
            outcome = fix10a_ball_proof_gate.apply_ball_proof_gate(outcome, track["rows"])
            outcome["goal_review_eligibility"] = deepcopy(job["eligibility"])
            trace["outcome_evidence"][job["outcome_index"]] = outcome
        except Exception as exc:
            # One malformed review must not discard unrelated windows. Keep
            # its pending, unresolved outcome and expose the exact audit gap.
            trace["provider_diagnostics"].append({
                "provider": "goal_geometry", "status": "ERROR",
                "error_type": type(exc).__name__, "report_priority_rank": rank,
                "media_ms": job["strike"].get("media_ms"),
            })
            trace["unresolved_reasons"].append("GOAL_REVIEW_EXECUTION_ERROR")
    # Replace pending diagnostics and publish the final version of each trace.
    # The runtime upserts by trace ID so the manifest has one authoritative row.
    for trace in traces:
        if trace.get("goal_review_phase") != "pending":
            continue
        trace["goal_review_phase"] = "complete"
        trace["provider_adapter_errors"] = sorted(set(
            (trace.get("provider_adapter_errors") or []) + _adapter_diagnostics(
                [trace.get("action_inspections"),
                 [o.get("goal_geometry_evidence") for o in trace["outcome_evidence"]]])))
        trace["unresolved_reasons"] = [reason for reason in trace["unresolved_reasons"]
                                       if reason not in {"GOAL_PLANE_CROSSING_UNRESOLVED", "POST_STRIKE_OUTCOME_UNRESOLVED"}]
        trace["unresolved_reasons"].extend(reason for reason in _window_unresolved_reasons(
            {}, {}, trace["outcome_evidence"]) if reason in {
                "GOAL_PLANE_CROSSING_UNRESOLVED", "POST_STRIKE_OUTCOME_UNRESOLVED"})
        if trace_callback is not None:
            try:
                trace_callback(trace)
            except Exception as exc:
                trace["incremental_storage_error_type"] = type(exc).__name__
    summaries = [event_trace.compact_trace_summary(trace) for trace in traces]
    for row in window_rows:
        trace = traces_by_window.get(row.get("dense_window_id"))
        if trace:
            row["provider_diagnostics"] = deepcopy(trace["provider_diagnostics"])
            row["provider_adapter_errors"] = deepcopy(trace["provider_adapter_errors"])
            row["unresolved_reasons"] = deepcopy(trace["unresolved_reasons"])
    unresolved_all = [reason for row in window_rows for reason in row.get("unresolved_reasons") or []]
    ok_windows = sum(row.get("status") == "ok" for row in window_rows)
    status = (
        "no_critical_windows" if not windows
        else "ok" if ok_windows == len(windows)
        else "partial" if ok_windows else "error"
    )
    recall_rows = [row for row in window_rows if row.get("recall_window") is True]
    recall_ok = sum(row.get("status") == "ok" for row in recall_rows)
    recall_failed = len(recall_rows) - recall_ok
    recall_scan_complete = recall_plan.get("scan_complete") is True
    recall_verification_complete = bool(recall_scan_complete and recall_failed == 0)

    failed_by_stage = {}
    for row in window_rows:
        if row.get("status") != "error":
            continue
        failed_stage = str(row.get("error_stage") or "unknown")
        failed_by_stage[failed_stage] = failed_by_stage.get(failed_stage, 0) + 1
    return {
        "version": VERSION,
        "status": status,
        "timebase": "canonical_media_ms",
        "source_role": SOURCE_ROLE,
        "source_video": source,
        "windows": window_rows,
        "trace_summaries": summaries,
        "traces": traces,
        "action_inspection_plan": inspection_plan,
        "goal_review_plan": {
            "requests": len(scheduled_jobs),
            "unique_contacts": len({j["review"]["physical_review_id"] for j in scheduled_jobs}),
            "review_budget": getattr(goal_geometry_provider, "max_reviews", None),
            "clarification_budget": getattr(goal_geometry_provider, "max_clarifications", None),
            "reviews_executed": getattr(goal_geometry_provider, "calls", None),
            "clarifications_executed": getattr(goal_geometry_provider, "clarification_calls", None),
        },
        "unresolved_reasons": list(dict.fromkeys(unresolved_all)),
        "recall_coverage": {
            "version": full_video_event_recall.VERSION,
            "scan_complete": recall_scan_complete,
            "verification_complete": recall_verification_complete,
            "status": (
                "verified_complete"
                if recall_verification_complete
                else "partial" if recall_scan_complete else "unavailable"
            ),
            "planned_windows": len(recall_windows),
            "executed_windows": len(recall_rows),
            "windows_ok": recall_ok,
            "windows_failed": recall_failed,
            "planner_metrics": deepcopy(recall_plan.get("metrics") or {}),
        },
        "metrics": {
            "critical_windows": len(windows),
            "semantic_critical_windows": len(semantic_windows),
            "physical_recall_windows": len(recall_windows),
            "physical_recall_windows_ok": recall_ok,
            "physical_recall_windows_failed": recall_failed,
            "windows_ok": ok_windows,
            "windows_failed": len(windows) - ok_windows,
            "windows_failed_by_stage": failed_by_stage,
            "traces": len(traces),
            "accepted_contacts": sum(int(x.get("accepted_contacts") or 0) for x in window_rows),
            "inspection_ball_candidates": sum(int(x.get("inspection_ball_candidates") or 0) for x in window_rows),
            "inspection_native_neighbor_frames": sum(int(x.get("inspection_native_neighbor_frames") or 0) for x in window_rows),
            "inspection_native_roi_attempts": sum(int(x.get("inspection_native_roi_attempts") or 0) for x in window_rows),
            "step3_recovered_contacts": sum(
                int(x.get("step3_recovered_contacts") or 0) for x in window_rows
            ),
            "touches": sum(int(x.get("touches") or 0) for x in window_rows),
            "physical_strikes": sum(int(x.get("strikes") or 0) for x in window_rows),
            "physical_release_strikes": sum(
                int(x.get("release_strikes") or 0) for x in window_rows
            ),
            "scoring_control_contacts": sum(
                int(x.get("scoring_control_contacts") or 0) for x in window_rows
            ),
            "goal_reviews_requested": sum(
                int(x.get("goal_reviews_requested") or 0) for x in window_rows
            ),
            "goal_reviews_skipped": sum(
                int(x.get("goal_reviews_skipped") or 0) for x in window_rows
            ),
            "a7_verified_interventions": sum(int(x.get("a7_verified_interventions") or 0) for x in window_rows),
        },
        # Explicitly absent by contract: canonical_events, event_ledger,
        # verified_stats, goals, assists, scorer or report mutation.
    }
