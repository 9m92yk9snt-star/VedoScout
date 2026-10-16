"""Audit saved evidence plans and reconciliation without video/SDK/network use.

Usage: python scripts/replay_saved_evidence.py /path/to/extracted-evidence
This does not rerun perception or predict the accuracy of future model replies.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def replay(root):
    import action_evidence_review as inspection
    import fix10b_reconciliation as reconciliation
    import full_video_event_recall as recall
    import goal_review_scheduler as scheduler
    import goal_review_sampling as sampling
    import fix10a_goal_direction as direction
    import sequence_observation_context as context

    report = json.loads((root / "report.json").read_text())
    traces = [json.loads(p.read_text()) for p in sorted((root / "traces").glob("*.json"))]
    old_windows = [t["window"] for t in traces]
    windows = recall.union_dense_windows(old_windows, [])
    sequence = report.get("football_sequence_analysis") or {}
    new_inspection = inspection.build_plan(windows, sequence)
    before = report.get("canonical_events") or {}
    if not isinstance(before, dict):
        before = json.loads((root / "canonical.json").read_text())["canonical_events"]
    role_conflicts = reconciliation._shot_role_conflicts(before.get("events") or [], {"traces": traces})
    reconciled = reconciliation.reconcile_canonical_events(before, {"status": "ok", "traces": traces})
    # Re-use the saved jobs, not fabricated model answers or expected actions.
    jobs = []
    for trace in traces:
        outcomes = {o["strike_id"]: o for o in trace.get("outcome_evidence") or []}
        for strike in trace.get("strike_evidence") or []:
            outcome = outcomes.get(strike.get("strike_id"), {})
            review = outcome.get("goal_review_decision") or {}
            if review.get("eligible") is True:
                jobs.append({"strike": strike, "window": trace["window"], "touch_graph": trace.get("touch_graph") or {},
                             "inspection_search_hints": context.review_search_hints(trace.get("action_inspections"), trace.get("decoded_frames") or []),
                             "review": review})
    seen = []
    provider = direction.GoalDirectionProvider(
        lambda w, s: seen.append(s["media_ms"]) or {"status": "UNRESOLVED", "line_by_ms": []},
        "", "saved-evidence", "unused")
    ordered = scheduler.ordered_requests(jobs, sequence)
    for job in ordered:
        provider(job["window"], sampling.provider_strike(job))
    saved_goal_reviews = []
    for trace in traces:
        for outcome in trace.get("outcome_evidence") or []:
            geometry = outcome.get("goal_geometry_evidence") or {}
            if (geometry.get("sampling_audit") or {}).get("actual_ms"):
                saved_goal_reviews.append(outcome["media_ms"])
    actual = {f["media_ms"] for t in traces for f in t.get("decoded_frames") or []}
    covered = {ms for ms in actual if any(w["start_ms"] <= ms <= w["end_ms"] for w in windows)}
    return {"source_video_sha256": (traces[0].get("source_video") or {}).get("sha256") if traces else None,
        "mode": "SAVED_JSON_ONLY_NO_PERCEPTION_REPLAY", "new_model_calls": 0, "decoded_video_frames": 0,
        "windows": {"saved": len(old_windows), "planned": len(windows),
            "saved_interval_ms": sum(w["end_ms"]-w["start_ms"] for w in old_windows),
            "planned_interval_ms": sum(w["end_ms"]-w["start_ms"] for w in windows),
            "saved_actual_pts": len(actual), "covered_actual_pts": len(covered)},
        "action_reads": {"saved_first_pass": sum(j.get("selected") is True and j.get("phase") != "FEEDBACK"
                                                for t in traces for j in t.get("action_inspections") or []),
                         "new_plan_selected": new_inspection["selected"],
                         "new_plan_observation_links": sum(len(j.get("source_action_ids") or []) for j in new_inspection["jobs"])},
        "goal_reviews": {"saved_review_audit_rows_media_ms": saved_goal_reviews,
            "dead_end_jobs_skipped": sum(not sampling.has_contact_reference(j["strike"], j["window"]) for j in jobs),
            "new_budget_allocation_media_ms": seen, "review_calls": provider.calls,
            "clarification_calls": provider.clarification_calls},
        "reopened_shot_role_conflicts": list(role_conflicts.values()),
        "saved_canonical_counts": before.get("counts"),
        "reconciled_saved_counts": reconciled.get("counts"),
        "warning": "New image packs and appearance comparisons have no saved model responses; five-event accuracy is not established."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_dir", type=Path)
    args = parser.parse_args()
    def forbidden(*_args, **_kwargs):
        raise RuntimeError("Saved-evidence replay cannot use the network or decode video")
    socket.socket.connect = forbidden
    socket.create_connection = forbidden
    import cv2
    cv2.VideoCapture = forbidden
    print(json.dumps(replay(args.evidence_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
