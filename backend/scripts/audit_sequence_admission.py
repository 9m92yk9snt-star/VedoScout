"""Replay exported semantic contracts without models, video decoding or DB writes.

Fallback can erase the historical prepared plan. In that case this audit may
reconstruct its boundaries from the first response only if every echoed window
has the exact deterministic planner ID. This is an admission diagnostic, never
a replacement for pixel/identity/causal verification or a full video replay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import football_sequence_intelligence as sequences
import unified_analysis_engine as unified


def infer_plan(response):
    windows = []
    seen = set()
    for row in response.get("sequences") or []:
        if not isinstance(row, dict):
            raise ValueError("Malformed response window")
        start, end = row.get("start_ms"), row.get("end_ms")
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (start, end)):
            raise ValueError("Unbound response window times")
        scene, sid = row.get("scene_id"), row.get("sequence_id")
        if (not isinstance(scene, str) or not scene or sid in seen or start < 0 or end < start
                or sid != sequences._stable_id("seq", scene, start, end)):
            raise ValueError("Response boundaries do not match the planner ID")
        seen.add(sid)
        windows.append({"sequence_id": sid, "scene_id": scene, "start_ms": start, "end_ms": end})
    if not windows:
        raise ValueError("No bound response windows")
    return {"analysis_windows": windows, "refinement_windows": []}


def audit(archive_path):
    with zipfile.ZipFile(archive_path) as archive:
        report = json.loads(archive.read("report.json"))
        calls = []
        for name in sorted(archive.namelist()):
            if not name.startswith("analysis_model_calls/") or Path(name).stem == "index":
                continue
            call = json.loads(archive.read(name))
            if not str(call.get("session_id") or "").startswith("sequence-"):
                continue
            raw = call.get("raw_response")
            if not isinstance(raw, str) or call.get("raw_response_truncated"):
                raise ValueError("Raw semantic response unavailable")
            if hashlib.sha256(raw.encode()).hexdigest() != call.get("response_sha256"):
                raise ValueError("Raw response checksum mismatch")
            calls.append((call, json.loads(raw[raw.find("{"):raw.rfind("}") + 1])))
    calls.sort(key=lambda pair: str(pair[0].get("started_at") or ""))
    if not calls:
        raise ValueError("No stored semantic model responses")
    plan = infer_plan(calls[0][1])
    merged = unified.merge_model_attempts([response for _, response in calls])
    result = unified.finalise_analysis(merged, {"sequence_plan": plan})
    physical_plan = unified.physical_sequence_plan(result)
    return {"kind": "STORED_SEQUENCE_ADMISSION_AUDIT",
            "plan_source": "ID_VALIDATED_FIRST_RESPONSE_BOUNDARIES",
            "historical_prepared_plan_available": False,
            "planned_windows": len(plan["analysis_windows"]),
            "sequence_contract_metrics": result["sequence_analysis"]["metrics"],
            "incomplete_sequence_ids": result["sequence_analysis"]["incomplete_sequence_ids"],
            "physical_admission": unified.can_run_physical(result),
            "positive_physical_windows": len((physical_plan or {}).get("analysis_windows") or []),
            "unreviewable_windows": (physical_plan or {}).get("unreviewable_windows") or [],
            "semantic_coverage_complete": result["sequence_analysis"]["coverage_complete"],
            "historical_final_stat_line": (report.get("full_report") or {}).get("verified_stat_line"),
            "new_event_approvals": 0, "new_model_calls": 0,
            "video_decodes": 0, "database_writes": 0,
            "limitation": "No historical dense graph/identity is inferred; physical admission is not event verification."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.evidence)
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
