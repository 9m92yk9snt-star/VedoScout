"""One user-located source packet, fresh originals, one owned model call.

No previous report, model response, inferred profile or expected outcome input.
This validates a short source window, never a complete-report benchmark.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sequence_pilot as p
import sequence_pilot_transport as transport
from scripts.run_sequence_pilot import fresh_original_manifest, original_spatial_items, FRESH_IDENTITY_INSTRUCTION


def run(evidence_dir, output, focus_ms, *, preflight_only=False):
    started = time.monotonic()
    output = Path(output)
    if output.exists():
        raise ValueError("OUTPUT_MUST_BE_NEW")
    manifest = fresh_original_manifest(p.prepare(evidence_dir, output / "prepared", max_edge=1280, scene_packets=True))
    base = next(v for v in manifest["packets"] if v["core_start_ms"] <= focus_ms < v["core_end_ms"])
    packet = {"packet_id": "question_scope_probe", "phase": "FOLLOWUP", "contact_sequence_evidence": True,
              "start_ms": base["core_start_ms"], "end_ms": base["core_end_ms"]-1,
              "core_start_ms": base["core_start_ms"], "core_end_ms": base["core_end_ms"],
              "reference_ids": base["reference_ids"][:],
              "detail_start_ms": max(base["core_start_ms"], focus_ms-100),
              "detail_end_ms": min(base["core_end_ms"]-1, focus_ms+1500),
              "question": {"reason": "CONTACT", "focus_ms": focus_ms,
                           "instruction": "Observe this user-located source window afresh using the full play and original selections. Follow all actors and the active ball through the visible outcome. Use the question scope contract; keep uncertainty where the images are insufficient. No expected result is supplied."}}
    enriched, jobs = p.prepare_contact_reviews(manifest, [packet], output / "native", native_detail_policy="local_half_q50")
    packet = jobs[0]
    items = p.packet_items(enriched, packet)
    items.insert(1, {"type": "text", "text": FRESH_IDENTITY_INSTRUCTION})
    spatial, spatial_audit = original_spatial_items(enriched, packet, output / "spatial")
    prefix = len(p.packet_items(enriched, {**packet, "frame_ids": []}))+1
    items[prefix:prefix] = spatial
    _, _, audit = transport.build_request("emergent", "gpt-6-astra", items,
                                          reasoning_effort="medium", image_detail="high")
    result = {"scope": "SINGLE_USER_LOCATED_SOURCE_PACKET", "fresh_end_to_end_timing": False,
              "expected_answers_used_as_input": False, "historical_action_results_used": False,
              "source_video_sha256": enriched["source_video_sha256"], "packet": packet,
              "request_audit": audit, "spatial_reference_audit": spatial_audit,
              "source_frames": [{"frame_id": f["frame_id"], "media_ms": f["media_ms"]}
                                for f in enriched["frames"] if f["frame_id"] in packet["frame_ids"]],
              "references": [{k: r[k] for k in ("reference_id", "media_ms", "sha256")} for r in enriched["references"]],
              "prompt_sha256": hashlib.sha256(p.PROMPT.encode()).hexdigest(),
              "model_calls": 0, "status": "PREFLIGHT_ONLY"}
    p.write_json(output / "result.json", result)
    if not preflight_only:
        receipt = transport.run_jobs([{"packet_id": packet["packet_id"], "items": items,
            "reasoning_effort": "medium", "image_detail": "high"}], "emergent", "gpt-6-astra",
            deadline=time.monotonic()+125, per_call_s=120, workers=1)[0]
        result.update(receipt=receipt, model_calls=1, status=receipt["status"])
        p.write_json(output / "result.json", result)  # retain paid raw evidence before parsing
        if receipt["status"] == "COMPLETED":
            try:
                resolved = p.resolve_response(p.parse_response(receipt["raw_response"]), enriched, packet,
                    {k: receipt[k] for k in ("packet_id", "payload_sha256", "response_sha256", "origin")})
                result["resolved"] = p.reconcile([resolved])
            except (ValueError, KeyError, TypeError):
                result.update(status="INVALID_OBSERVATION_RESPONSE", error="OBSERVATION_PARSE_FAILED")
    result["total_wall_seconds"] = round(time.monotonic()-started, 3)
    p.write_json(output / "result.json", result)
    print(json.dumps(result), flush=True)
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--evidence-dir", required=True)
    cli.add_argument("--output", required=True)
    cli.add_argument("--focus-ms", type=int, required=True)
    cli.add_argument("--preflight-only", action="store_true")
    args = cli.parse_args()
    result = run(args.evidence_dir, args.output, args.focus_ms, preflight_only=args.preflight_only)
    raise SystemExit(0 if result["status"] in {"COMPLETED", "PREFLIGHT_ONLY"} else 3)
