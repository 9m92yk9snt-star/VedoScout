"""Prepare/run/evaluate a bounded football experiment outside Emergent.

Run --help for commands. Preparation and reference evaluation never call a model.
Only 'run' can send images, and only via an explicitly selected provider with
its normal environment variable. No secrets are accepted as CLI arguments.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sequence_pilot as pilot
import sequence_pilot_transport as transport


def run(manifest_path, output_dir, *, provider="gemini", model="gemini-2.5-pro", budget_s=300., max_initial=4,
        max_followups=2, per_call_s=90., reasoning_effort=None):
    started, out = time.monotonic(), Path(output_dir).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("OUTPUT_MUST_BE_NEW_OR_EMPTY")
    manifest = pilot.read_json(manifest_path)
    if not 1 <= budget_s <= 600 or not 0 <= max_followups <= 2 or not 1 <= max_initial <= 12:
        raise ValueError("INVALID_EXPERIMENT_BUDGET")
    if reasoning_effort not in {None, "low"}:
        raise ValueError("INVALID_REASONING_EFFORT")
    if provider not in transport.KEY_ENV:
        raise ValueError("INVALID_MODEL_PROVIDER")
    summary = {"version": pilot.VERSION, "status": "NOT_STARTED", "provider": provider, "model": model,
               "code_sha256": {p.name: pilot.digest(p) for p in (
                   Path(pilot.__file__), Path(transport.__file__), Path(__file__),
                   Path(pilot.__file__).with_name("player_selection.py"))},
               "source_video_sha256": manifest["source_video_sha256"], "preparation_reused": True,
               "prior_preparation_seconds": manifest["preparation_seconds"], "wall_budget_seconds": budget_s,
               "production_pipeline_changed": False, "expected_answers_used_as_input": False,
               "model_jobs_completed": 0, "independent_visual_correctness_verified": False,
               "requested_reasoning_effort": reasoning_effort,
               "reference_policy": manifest.get("reference_policy"),
               "visual_packet_plan": manifest.get("visual_packet_plan"),
               "model_jobs": [], "events": [], "target_events": [], "counts": {}, "questions": [], "conflicts": []}
    if not os.environ.get(transport.KEY_ENV[provider]):
        summary["status"] = "MODEL_KEY_NOT_CONFIGURED"
        pilot.write_json(out / "result.json", summary)
        return summary
    if len(manifest["packets"]) > max_initial:
        raise ValueError("INITIAL_WORKLOAD_EXCEEDS_CALL_BUDGET")
    if pilot.digest(manifest["source_video"]) != manifest["source_video_sha256"]:
        raise ValueError("SOURCE_VIDEO_CHANGED")
    deadline, resolved_results, receipts = started + budget_s, [], []
    owner_manifest = manifest

    def execute(packets, current_manifest):
        jobs = []
        for packet in packets:
            items = pilot.packet_items(current_manifest, packet)
            # Validate the complete wire request before starting any paid job.
            _url, _payload, request_audit = transport.build_request(provider, model, items,
                reasoning_effort=reasoning_effort)
            pilot.write_json(out / "requests" / (packet["packet_id"] + ".json"),
                {**packet, "image_delivery": request_audit,
                 "prompt_sha256": hashlib.sha256("\n".join(x["text"] for x in items if x["type"] == "text").encode()).hexdigest()})
            jobs.append({"packet_id": packet["packet_id"], "items": items, "reasoning_effort": reasoning_effort})
        print(json.dumps({"phase": packets[0]["phase"] if packets else "NONE", "jobs": len(jobs),
                          "remaining_seconds": round(max(0, deadline - time.monotonic()), 1)}), flush=True)
        responses = transport.run_jobs(jobs, provider, model, deadline=deadline, per_call_s=per_call_s)
        by_id = {p["packet_id"]: p for p in packets}
        for receipt in responses:
            pilot.write_json(out / "responses" / (receipt["packet_id"] + ".json"), receipt)
            receipts.append({k: v for k, v in receipt.items() if k not in {"raw_response", "images"}})
            print(json.dumps({k: receipt.get(k) for k in ("packet_id", "status", "error", "elapsed_seconds")}), flush=True)
            if receipt["status"] != "COMPLETED":
                continue
            try:
                raw = pilot.parse_response(receipt["raw_response"])
                result = pilot.resolve_response(raw, current_manifest, by_id[receipt["packet_id"]],
                    {k: receipt[k] for k in ("packet_id", "payload_sha256", "response_sha256", "origin")})
                resolved_results.append(result)
            except (ValueError, KeyError, TypeError):
                receipts[-1].update(status="INVALID_OBSERVATION_RESPONSE")

    try:
        execute(manifest["packets"], manifest)
        merged = pilot.reconcile(resolved_results, sampling_gap_ms=manifest["input_coverage"]["max_sample_gap_ms"])
        summary.update(merged)  # preserve completed observations if later work fails
        access_failed = any(r.get("error") in {"MODEL_ACCESS_DENIED", "MODEL_KEY_NOT_CONFIGURED"} for r in receipts)
        followups = [] if access_failed else pilot.followup_plan(manifest, merged, limit=max_followups)
        if followups and time.monotonic() + 5 < deadline:
            owner_manifest, followups = pilot.prepare_followups(manifest, followups, out,
                timeout_s=min(30., max(1., deadline - time.monotonic() - 5)))
            execute(followups, owner_manifest)
        merged = pilot.reconcile(resolved_results, sampling_gap_ms=manifest["input_coverage"]["max_sample_gap_ms"])
        summary.update(merged)
        complete = len([r for r in receipts if r.get("status") == "COMPLETED"]) == len(manifest["packets"]) + len(followups)
        summary["status"] = "MODEL_OBSERVATIONS_RETURNED" if complete else "PARTIAL_MODEL_RUN"
        if access_failed:
            summary["status"] = "MODEL_ACCESS_DENIED"
    except (ValueError, TimeoutError, OSError) as exc:
        # Exception text is intentionally not persisted: providers may include secrets.
        safe_codes = {"REQUEST_IMAGE_BUDGET_EXCEEDED", "PREPARED_IMAGE_CHANGED", "SOURCE_VIDEO_CHANGED",
                      "DETAIL_PREPARATION_TIME_BUDGET_EXHAUSTED", "INVALID_EXECUTION_BUDGET"}
        summary.update(status="EXPERIMENT_STOPPED", error_type=type(exc).__name__,
                       error_code=str(exc) if str(exc) in safe_codes else "EXPERIMENT_PROCESSING_FAILED")
    finally:
        summary.update(model_jobs=receipts, analysis_seconds=round(time.monotonic() - started, 3),
                       model_jobs_completed=sum(r.get("status") == "COMPLETED" for r in receipts),
                       independent_visual_correctness_verified=False)
        pilot.write_json(out / "result.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Offline: verify source/taps and sample original images once")
    prepare.add_argument("--evidence-dir", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--fps", type=float, default=8.)
    prepare.add_argument("--max-edge", type=int, default=768)
    prepare.add_argument("--chunk-ms", type=int, default=30000)
    prepare.add_argument("--overlap-ms", type=int, default=6000)
    prepare.add_argument("--scene-packets", action="store_true", help="Split using measured source-image changes; raw reference consensus")
    model = commands.add_parser("run", help="Paid model experiment; requires configured environment key")
    model.add_argument("--prepared", type=Path, required=True)
    model.add_argument("--output", type=Path, required=True)
    model.add_argument("--provider", choices=sorted(transport.KEY_ENV), default="gemini")
    model.add_argument("--model", default="gemini-2.5-pro")
    model.add_argument("--budget-s", type=float, default=300.)
    model.add_argument("--per-call-s", type=float, default=90.)
    model.add_argument("--max-followups", type=int, default=2)
    model.add_argument("--max-initial", type=int, default=4)
    model.add_argument("--reasoning-effort", choices=["low"], default=None)
    evaluate = commands.add_parser("evaluate", help="Offline matching; never passes expected answers to a model")
    evaluate.add_argument("--result", type=Path, required=True)
    evaluate.add_argument("--cases", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        import cv2
        cv2.setNumThreads(2)
        manifest = pilot.prepare(args.evidence_dir, args.output, fps=args.fps, max_edge=args.max_edge,
                                 chunk_ms=args.chunk_ms, overlap_ms=args.overlap_ms, scene_packets=args.scene_packets)
        print(json.dumps({k: manifest[k] for k in ("status", "preparation_seconds", "input_coverage", "model_calls", "detector_forwards")}, indent=2))
    elif args.command == "run":
        result = run(args.prepared, args.output, provider=args.provider, model=args.model, budget_s=args.budget_s,
                     per_call_s=args.per_call_s, max_followups=args.max_followups, max_initial=args.max_initial,
                     reasoning_effort=args.reasoning_effort)
        print(json.dumps({k: result.get(k) for k in ("status", "analysis_seconds", "model_jobs_completed", "counts")}, indent=2))
        return 0 if result["status"] == "MODEL_OBSERVATIONS_RETURNED" else 3
    else:
        print(json.dumps(pilot.assess_reference_cases(pilot.read_json(args.cases), pilot.read_json(args.result)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
