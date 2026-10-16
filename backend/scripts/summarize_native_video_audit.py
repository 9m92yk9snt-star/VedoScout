"""Post-hoc QA of a completed native run; never schedules analysis or readers."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import reference_action_review as review
    receipt = read(args.run / "receipt.json")
    if (receipt.get("status") != "NATIVE_DIAGNOSTIC_COMPLETE_NOT_FULL_ANALYSIS"
            or receipt.get("source_unchanged") is not True
            or receipt.get("counters", {}).get("network") != 0
            or receipt.get("counters", {}).get("remote_sdk") != 0):
        parser.error("A completed, source-stable, isolated native run is required")
    physical = read(args.run / "physical.json")
    canonical = read(args.run / "reconciliation.json")["canonical_events"]
    cases = read(args.cases)
    traces = physical["traces"]
    assessment = review.assess(cases, canonical, physical, review.build_plan(traces, cases))
    rows = []
    for case in assessment["cases"]:
        trace = next((t for t in traces if t["trace_id"] == case["source_trace_id"]), {})
        frames = trace.get("decoded_frames") or []
        nearest = min(frames, key=lambda f: abs(f["media_ms"] - case["reference_ms"]), default={})
        target = nearest.get("global_target") or {}
        nearby = [s for s in trace.get("strike_evidence") or []
                  if abs(s["media_ms"] - case["reference_ms"]) <= 1000]
        rows.append({k: case[k] for k in ("case_id", "reference_ms", "status", "failure_reason",
                                         "source_trace_id", "inspection_status")})
        rows[-1].update(nearest_frame_ms=nearest.get("media_ms"),
                        nearest_target={k: target.get(k) for k in ("status", "reason", "proof_eligible")},
                        nearby_strikes=len(nearby),
                        nearby_target_strikes=sum(s.get("global_target_id") == "GLOBAL_TARGET" for s in nearby),
                        nearby_physical_outcomes=dict(Counter(o.get("physical_outcome")
                            for o in trace.get("outcome_evidence") or []
                            if abs(o["media_ms"] - case["reference_ms"]) <= 1000)))
    frames = [f for t in traces for f in t.get("decoded_frames") or []]
    pts = {f["media_ms"] for f in frames}
    summary = {"scope": "COMPLETED_NATIVE_DIAGNOSTIC_POSTHOC_QA_NOT_FULL_ANALYSIS",
               "source_commit": receipt["source_commit"],
               "source_video_sha256": receipt["source_video_sha256"],
               "original_anchors_sha256": receipt["original_anchors_sha256"],
               "anchor_count": receipt["anchor_count"],
               "declared_number": receipt["declared_number"],
               "original_declared_number": receipt["original_declared_number"],
               "declaration_override_source": receipt["declaration_override_source"],
               "source_unchanged": receipt["source_unchanged"], "stages": receipt["stages"],
               "counters": receipt["counters"],
               "preparation_metrics": receipt["preparation_metrics"],
               "physical_status": physical.get("status"), "physical_metrics": physical.get("metrics"),
               "recall_execution_coverage": physical.get("recall_coverage"),
               "decoded_frame_rows": len(frames), "distinct_media_pts": len(pts),
               "first_media_ms": min(pts, default=None), "last_media_ms": max(pts, default=None),
               "fallback_rows": sum(bool(f.get("used_fallback")) for f in frames),
               "non_actual_pts_rows": sum(f.get("time_authority") != "ACTUAL_MEDIA_PTS" for f in frames),
               "new_remote_model_calls": 0, "database_writes": receipt["database_writes"],
               "qualified_reference_actions": assessment["verified"], "reference_actions": assessment["requested"],
               "reference_labels_used_as_analysis_input": False,
               "reference_cases": rows,
               "limits": ["Remote semantic, jersey, role and goal readers disabled",
                          "Original historical taps are not fresh human acceptance of FIX19 cutouts",
                          "Recall execution coverage is not event recall or verified football truth",
                          "No full online analysis, merge or deployment"],
               "input_artifact_sha256": {name: digest(args.run / name) for name in
                                         ("receipt.json", "physical.json", "reconciliation.json")},
               "qa_cases_sha256": digest(args.cases)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"physical_status": summary["physical_status"], "windows": len(traces),
                      "distinct_media_pts": len(pts), "verified": assessment["verified"],
                      "requested": assessment["requested"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
