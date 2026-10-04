"""Separate successful execution from observable target/scoring evidence.

These diagnostics never create, reject or upgrade a canonical event. They
describe missing proof, including when a detector never emitted a SHOT/PASS.
Local player IDs from different trace windows are never compared.
"""
from __future__ import annotations


def assess(physical_result: dict | None) -> dict:
    physical = physical_result if isinstance(physical_result, dict) else {}
    traces = [t for t in physical.get("traces") or [] if isinstance(t, dict)]
    frames_seen = 0
    identity_gaps = set()
    target_outcome_gaps = set()
    missing_outcome_traces = set()
    for index, trace in enumerate(traces):
        trace_key = (str(trace.get("trace_id") or index), index)
        frames = [f for f in trace.get("decoded_frames") or [] if isinstance(f, dict)]
        frames_seen += len(frames)
        for frame in frames:
            target = frame.get("global_target") or {}
            if not isinstance(target, dict) or target.get("proof_eligible") is not True:
                # A frame missing identity is an observability gap, not proof
                # that the player did not touch the ball or produce a goal.
                identity_gaps.add((trace_key, frame.get("media_ms")))

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

    reasons = []
    if not frames_seen:
        reasons.append("TARGET_FRAME_EVIDENCE_UNAVAILABLE")
    if identity_gaps:
        reasons.append("TARGET_IDENTITY_COVERAGE_GAPS")
    if target_outcome_gaps:
        reasons.append("TARGET_SCORING_CHAIN_UNRESOLVED")
    if missing_outcome_traces:
        reasons.append("TARGET_OUTCOME_EVIDENCE_MISSING")
    return {
        "status": "NOT_ASSESSED" if not frames_seen else "PARTIAL" if reasons else "COMPLETE",
        "complete": bool(frames_seen and not reasons),
        "decoded_frame_observations": frames_seen,
        "identity_gap_observations": len(identity_gaps),
        "unresolved_target_outcomes": len(target_outcome_gaps),
        "missing_target_outcomes": len(missing_outcome_traces),
        "reasons": reasons,
    }
