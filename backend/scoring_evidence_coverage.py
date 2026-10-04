"""Separate successful execution from observable target/scoring evidence.

These diagnostics never create, reject or upgrade a canonical event. They
describe missing proof, including when a detector never emitted a SHOT/PASS.
Local player IDs from different trace windows are never compared.
"""
from __future__ import annotations
from bisect import bisect_left


def assess(physical_result: dict | None, scene_graph: dict | None = None) -> dict:
    physical = physical_result if isinstance(physical_result, dict) else {}
    traces = [t for t in physical.get("traces") or [] if isinstance(t, dict)]
    frames_seen = 0
    identity_gaps = set()
    target_outcome_gaps = set()
    missing_outcome_traces = set()
    provider_errors = set()
    proof_by_scene = {}
    ball_gaps = set()
    for index, trace in enumerate(traces):
        trace_key = (str(trace.get("trace_id") or index), index)
        provider_errors.update(str(reason) for reason in trace.get("provider_adapter_errors") or [])
        provider_errors.update(str(d.get("provider")) for d in trace.get("provider_diagnostics") or []
                               if isinstance(d, dict) and d.get("status") in {"ERROR", "UNAVAILABLE"})
        frames = [f for f in trace.get("decoded_frames") or [] if isinstance(f, dict)]
        trajectory = {row.get("media_ms"): row for row in trace.get("ball_trajectory") or [] if isinstance(row, dict)}
        frames_seen += len(frames)
        for frame in frames:
            target = frame.get("global_target") or {}
            if not isinstance(target, dict) or target.get("proof_eligible") is not True:
                # A frame missing identity is an observability gap, not proof
                # that the player did not touch the ball or produce a goal.
                identity_gaps.add((trace_key, frame.get("media_ms")))
            elif isinstance(frame.get("media_ms"), (int, float)):
                proof_by_scene.setdefault(frame.get("scene_id"), set()).add(frame["media_ms"])
                if "ball_trajectory" in trace and (trajectory.get(frame["media_ms"]) or {}).get("proof_eligible") is not True:
                    ball_gaps.add((trace_key, frame["media_ms"]))

        strikes = {
            s.get("strike_id"): s for s in trace.get("strike_evidence") or []
            if isinstance(s, dict) and s.get("strike_id")
        }
        outcomes = {
            o.get("strike_id"): o for o in trace.get("outcome_evidence") or []
            if isinstance(o, dict) and o.get("strike_id")
        }
        for strike_id, strike in strikes.items():
            outcome = outcomes.get(strike_id)
            eligibility = (outcome or {}).get("goal_review_eligibility") or {}
            related = (
                strike.get("global_target_id") == "GLOBAL_TARGET"
                or (isinstance(eligibility, dict) and eligibility.get("eligible") is True)
                or (isinstance(eligibility, dict) and eligibility.get("reason")
                    == "DOWNSTREAM_RELEASE_TARGET_TEAM_UNVERIFIED")
            )
            if not related:
                continue
            if not outcome:
                missing_outcome_traces.add((trace_key, strike_id))
            elif str(outcome.get("physical_outcome") or "").startswith("UNRESOLVED"):
                target_outcome_gaps.add((trace_key, strike_id))
            elif isinstance(eligibility, dict) and eligibility.get("reason") == "DOWNSTREAM_RELEASE_TARGET_TEAM_UNVERIFIED":
                target_outcome_gaps.add((trace_key, strike_id))

    # Inspect the full planning substrate too. A successful set of selected
    # windows cannot certify portions omitted because target identity was lost.
    sorted_proof = {scene: sorted(times) for scene, times in proof_by_scene.items()}
    source_gaps = 0
    for frame in (scene_graph or {}).get("frames") or []:
        if not isinstance(frame, dict) or not isinstance(frame.get("media_ms"), (int, float)):
            continue
        target = frame.get("global_target") or {}
        if target.get("proof_eligible") is True:
            continue
        times = sorted_proof.get(frame.get("scene_id"), [])
        index = bisect_left(times, frame["media_ms"])
        neighbors = times[max(0, index - 1):index + 1]
        if not any(abs(ms - frame["media_ms"]) <= 100 for ms in neighbors):
            source_gaps += 1

    reasons = []
    if physical.get("audit_storage_complete") is False:
        reasons.append("TRACE_AUDIT_STORAGE_INCOMPLETE")
    if provider_errors:
        reasons.append("SUPPORTING_REVIEW_UNAVAILABLE_OR_FAILED")
    if not frames_seen:
        reasons.append("TARGET_FRAME_EVIDENCE_UNAVAILABLE")
    if identity_gaps:
        reasons.append("TARGET_IDENTITY_COVERAGE_GAPS")
    if source_gaps:
        reasons.append("SOURCE_TARGET_COVERAGE_GAPS")
    if ball_gaps:
        reasons.append("TARGET_BALL_OBSERVABILITY_GAPS")
    if target_outcome_gaps:
        reasons.append("TARGET_SCORING_CHAIN_UNRESOLVED")
    if missing_outcome_traces:
        reasons.append("TARGET_OUTCOME_EVIDENCE_MISSING")
    return {
        "status": "NOT_ASSESSED" if not frames_seen else "PARTIAL" if reasons else "COMPLETE",
        "complete": bool(frames_seen and not reasons),
        "decoded_frame_observations": frames_seen,
        "identity_gap_observations": len(identity_gaps),
        "source_identity_gap_observations": source_gaps,
        "target_ball_gap_observations": len(ball_gaps),
        "unresolved_target_outcomes": len(target_outcome_gaps),
        "missing_target_outcomes": len(missing_outcome_traces),
        "provider_error_reasons": sorted(provider_errors),
        "reasons": reasons,
    }
