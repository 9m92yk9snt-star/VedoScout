"""Prepare/run/evaluate a bounded football experiment outside Emergent.

Run --help for commands. Preparation and reference evaluation never call a model.
Only 'run' can send images, and only via an explicitly selected provider with
its normal environment variable. No secrets are accepted as CLI arguments.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sequence_pilot as pilot
import sequence_pilot_transport as transport


def fresh_original_manifest(manifest):
    """No inferred identity description or historical action receipt enters this run."""
    updated = deepcopy(manifest)
    updated.pop("identity_profile", None)
    refs = [r["reference_id"] for r in updated["references"]]
    updated["identity_reference_scope"] = refs[:]
    for packet in updated["packets"]:
        packet.update(reference_ids=refs[:],contact_sequence_evidence=True)
    return updated


def original_spatial_items(manifest, packet, output):
    from scripts.probe_native_play import spatial_reference_items
    lo,hi=packet.get("core_start_ms",packet["start_ms"]),packet.get("core_end_ms",packet["end_ms"]+1)
    local=[r for r in manifest["references"] if lo <= r["media_ms"] < hi]
    return spatial_reference_items(manifest,packet,local,output)


def run(manifest_path, output_dir, *, provider="gemini", model="gemini-2.5-pro", budget_s=300., max_initial=4,
        max_followups=2, per_call_s=90., reasoning_effort=None, identity_profile=False, image_detail=None,
        identity_profile_receipt=None, contact_reviews=False, resume_initial_receipts=None, fresh_originals=False):
    started, out = time.monotonic(), Path(output_dir).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("OUTPUT_MUST_BE_NEW_OR_EMPTY")
    manifest = pilot.read_json(manifest_path)
    if not 1 <= budget_s <= 600 or not 0 <= max_followups <= 6 or not 1 <= max_initial <= 12:
        raise ValueError("INVALID_EXPERIMENT_BUDGET")
    if reasoning_effort not in {None, "low", "medium"}:
        raise ValueError("INVALID_REASONING_EFFORT")
    if fresh_originals and (identity_profile or identity_profile_receipt or resume_initial_receipts):
        raise ValueError("FRESH_ORIGINALS_CANNOT_REPLAY_MODEL_RESULTS")
    if fresh_originals:
        manifest = fresh_original_manifest(manifest)
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
               "identity_mode":"FRESH_ORIGINAL_SELECTIONS" if fresh_originals else "EXISTING_REFERENCE_POLICY",
               "historical_action_results_used":bool(resume_initial_receipts),
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
            if fresh_originals:
                packet["contact_sequence_evidence"] = True
            items = pilot.packet_items(current_manifest, packet)
            spatial_audit=[]
            if fresh_originals:
                items.insert(1,{"type":"text","text":
                    "Read all original selections afresh; no inferred appearance profile or past action answer is supplied. "
                    "A local original point locates the intended physical player at that instant. Connect identity by "
                    "readable numbers and continuous movement, not guessed facial hair or shadow. "
                    "At every candidate release distinguish that person's body/boot movement from nearby players. "
                    "Compare before and after occlusion. A separate teammate can finish first time: the receiving and "
                    "striking contact may be the same action. Do not invent an extra settled touch or conflate "
                    "the releaser with the receiver. Keep opposing brushes distinct from controlled possession. "
                    "If contacts or actors remain ambiguous, retain a specific question. "
                    "Return the actual result, including unsuccessful actions. No expected answers or target count is supplied."})
                spatial,spatial_audit=original_spatial_items(current_manifest,packet,out/"spatial"/packet["packet_id"])
                prefix = len(pilot.packet_items(current_manifest,{**packet,"frame_ids":[]}))+1
                items[prefix:prefix] = spatial
            # Validate the complete wire request before starting any paid job.
            try:
                _url, _payload, request_audit = transport.build_request(provider, model, items,
                    reasoning_effort=reasoning_effort, image_detail=image_detail)
            except ValueError as exc:
                if str(exc) != "REQUEST_IMAGE_BUDGET_EXCEEDED":
                    raise
                skipped = {"packet_id": packet["packet_id"], "status": "NOT_SENT",
                           "error": "REQUEST_IMAGE_BUDGET_EXCEEDED", "origin": "LOCAL_PREFLIGHT"}
                receipts.append(skipped)
                pilot.write_json(out / "responses" / (packet["packet_id"] + ".json"), skipped)
                continue
            pilot.write_json(out / "requests" / (packet["packet_id"] + ".json"),
                {**packet, "image_delivery": request_audit,
                 "spatial_reference_audit":spatial_audit,
                 "prompt_sha256": hashlib.sha256("\n".join(x["text"] for x in items if x["type"] == "text").encode()).hexdigest()})
            jobs.append({"packet_id": packet["packet_id"], "items": items,
                         "reasoning_effort": reasoning_effort, "image_detail": image_detail})
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
                result["packet_id"] = receipt["packet_id"]
                result["replaces_initial_packet_id"] = by_id[receipt["packet_id"]].get("replaces_initial_packet_id")
                resolved_results.append(result)
            except (ValueError, KeyError, TypeError):
                receipts[-1].update(status="INVALID_OBSERVATION_RESPONSE")

    try:
        if identity_profile_receipt:
            saved = pilot.read_json(identity_profile_receipt)
            r = saved["receipt"]
            if (saved["source_video_sha256"] != manifest["source_video_sha256"]
                or r["status"] != "COMPLETED" or r["origin"] != "LIVE_MODEL_REQUEST"
                or hashlib.sha256(r["raw_response"].encode()).hexdigest() != r["response_sha256"]
                or sorted(x["sha256"] for x in r["images"]) != sorted(x["sha256"] for x in manifest["references"])):
                raise ValueError("IDENTITY_PROFILE_UNRESOLVED")
            manifest = pilot.apply_identity_profile(manifest, json.loads(r["raw_response"]))
            owner_manifest = manifest
            summary.update(identity_profile=manifest["identity_profile"], reused_identity_profile_response_sha256=r["response_sha256"])
        elif identity_profile:
            profile_receipt = transport.run_jobs([{"packet_id": "identity_profile",
                "items": pilot.identity_items(manifest), "reasoning_effort": reasoning_effort, "image_detail": image_detail}],
                provider, model, deadline=deadline, per_call_s=per_call_s)[0]
            pilot.write_json(out / "responses" / "identity_profile.json", profile_receipt)
            summary["identity_profile_receipt"] = {k: v for k, v in profile_receipt.items()
                if k not in {"raw_response", "images"}}
            if profile_receipt["status"] != "COMPLETED":
                raise ValueError("IDENTITY_PROFILE_UNRESOLVED")
            manifest = pilot.apply_identity_profile(manifest, json.loads(profile_receipt["raw_response"]))
            owner_manifest = manifest
            summary["identity_profile"] = manifest["identity_profile"]
        if resume_initial_receipts:
            saved = pilot.read_json(resume_initial_receipts)
            specs = [{k: packet[k] for k in ("packet_id", "start_ms", "end_ms", "frame_ids", "reference_ids")} for packet in manifest["packets"]]
            fingerprint = hashlib.sha256(json.dumps(specs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if (saved["source_video_sha256"] != manifest["source_video_sha256"]
                or saved["original_taps_sha256"] != manifest["original_taps_sha256"]
                or saved["packet_fingerprint"] != fingerprint
                or {r["packet_id"] for r in saved["receipts"]} != {p["packet_id"] for p in manifest["packets"]}):
                raise ValueError("INITIAL_RECEIPT_INPUT_MISMATCH")
            by_id = {p["packet_id"]: p for p in manifest["packets"]}
            for r in saved["receipts"]:
                if (r["origin"] != "LIVE_MODEL_REQUEST" or r["status"] != "COMPLETED"
                    or r["requested_model"] != model
                    or hashlib.sha256(r["raw_response"].encode()).hexdigest() != r["response_sha256"]):
                    raise ValueError("INITIAL_RECEIPT_INPUT_MISMATCH")
                pilot.write_json(out / "responses" / (r["packet_id"]+".json"), {**r, "reused_in_this_run": True})
                observed = pilot.resolve_response(pilot.parse_response(r["raw_response"]), manifest, by_id[r["packet_id"]],
                    {k: r[k] for k in ("packet_id", "payload_sha256", "response_sha256", "origin")})
                observed["packet_id"] = r["packet_id"]
                resolved_results.append(observed)
            summary.update(reused_initial_run_id=saved["origin_run"], reused_initial_model_jobs=len(saved["receipts"]),
                           previous_run_analysis_seconds=saved["previous_run_analysis_seconds"], completed_initial_requests_replayed=False)
        else:
            execute(manifest["packets"], manifest)
        merged = pilot.reconcile(resolved_results, sampling_gap_ms=manifest["input_coverage"]["max_sample_gap_ms"])
        summary.update(merged)  # preserve completed observations if later work fails
        access_failed = any(r.get("error") in {"MODEL_ACCESS_DENIED", "MODEL_KEY_NOT_CONFIGURED"} for r in receipts)
        planner = pilot.plan_contact_reviews if contact_reviews else pilot.followup_plan
        followups = [] if access_failed else planner(manifest, merged, limit=max_followups)
        if followups and time.monotonic() + 5 < deadline:
            preparer = pilot.prepare_contact_reviews if contact_reviews else pilot.prepare_followups
            owner_manifest, followups = preparer(manifest, followups, out,
                timeout_s=min(30., max(1., deadline - time.monotonic() - 5)),
                **({"native_detail_policy":"local_half_q50"} if fresh_originals and contact_reviews else {}))
            execute(followups, owner_manifest)
        replaced = {r["replaces_initial_packet_id"] for r in resolved_results
                    if r.get("replaces_initial_packet_id") and r["events"]}
        active = [r for r in resolved_results if r.get("packet_id") not in replaced]
        merged = pilot.reconcile(active, sampling_gap_ms=manifest["input_coverage"]["max_sample_gap_ms"])
        summary["superseded_initial_packet_ids"] = sorted(replaced)
        summary.update(merged)
        initial_count = 0 if resume_initial_receipts else len(manifest["packets"])
        complete = len([r for r in receipts if r.get("status") == "COMPLETED"]) == initial_count + len(followups)
        summary["status"] = "MODEL_OBSERVATIONS_RETURNED" if complete else "PARTIAL_MODEL_RUN"
        if access_failed:
            summary["status"] = "MODEL_ACCESS_DENIED"
    except (ValueError, TimeoutError, OSError) as exc:
        # Exception text is intentionally not persisted: providers may include secrets.
        safe_codes = {"REQUEST_IMAGE_BUDGET_EXCEEDED", "PREPARED_IMAGE_CHANGED", "SOURCE_VIDEO_CHANGED",
                      "DETAIL_PREPARATION_TIME_BUDGET_EXHAUSTED", "INVALID_EXECUTION_BUDGET", "IDENTITY_PROFILE_UNRESOLVED", "INITIAL_RECEIPT_INPUT_MISMATCH"}
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
    model.add_argument("--reasoning-effort", choices=["low","medium"], default=None)
    model.add_argument("--fresh-originals", action="store_true", help="Fresh all-reference identity per play; no historical model reuse")
    model.add_argument("--identity-profile", action="store_true", help="Infer one shared identity from original crops before reading plays")
    model.add_argument("--image-detail", choices=["high"], default=None, help="Request model-side high detail independently of JPEG size")
    model.add_argument("--identity-profile-receipt", type=Path, help="Reuse a source-and-reference-hash-matched identity receipt")
    model.add_argument("--contact-reviews", action="store_true", help="Inspect unresolved target contacts with native source pixels/rate")
    model.add_argument("--resume-initial-receipts", type=Path, help="Reuse verified initial model receipts on identical source/reference/frame inputs")
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
                     reasoning_effort=args.reasoning_effort, identity_profile=args.identity_profile, image_detail=args.image_detail,
                     identity_profile_receipt=args.identity_profile_receipt, contact_reviews=args.contact_reviews,
                     resume_initial_receipts=args.resume_initial_receipts, fresh_originals=args.fresh_originals)
        print(json.dumps({k: result.get(k) for k in ("status", "analysis_seconds", "model_jobs_completed", "counts")}, indent=2))
        return 0 if result["status"] == "MODEL_OBSERVATIONS_RETURNED" else 3
    else:
        print(json.dumps(pilot.assess_reference_cases(pilot.read_json(args.cases), pilot.read_json(args.result)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
