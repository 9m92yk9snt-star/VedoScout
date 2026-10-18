"""Read all source-derived plays with bounded native-video jobs; no answer input."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.probe_native_play import prepare_request
import sequence_pilot as pilot
import sequence_pilot_transport as transport


def run(manifest_path, output, profile_path, known_receipt, baseline_receipt, known_videos):
    started, output = time.monotonic(), Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("OUTPUT_MUST_BE_NEW_OR_EMPTY")
    manifest = pilot.read_json(manifest_path)
    if len(manifest["packets"]) > 12:
        raise ValueError("SOURCE_PLAY_BUDGET_EXCEEDED")
    known = pilot.read_json(known_receipt); cached = known["receipt"]
    if known["selected_packet"] not in {p["packet_id"] for p in manifest["packets"]}:
        raise ValueError("CACHED_NATIVE_PLAY_MISSING_FROM_PLAN")
    if (known["source_video_sha256"] != manifest["source_video_sha256"]
            or cached["status"] != "COMPLETED" or cached["origin"] != "LIVE_MODEL_REQUEST"
            or cached["requested_model"] != "gemini-3.8-flash"
            or hashlib.sha256(cached["raw_response"].encode()).hexdigest() != cached["response_sha256"]):
        raise ValueError("CACHED_NATIVE_RESULT_INVALID")
    summary = {"status": "PREPARING_NATIVE_SOURCE_PLAYS", "target_events": [],
        "production_pipeline_changed": False, "expected_answers_used_as_input": False,
        "independent_visual_correctness_verified": False,
        "source_video_sha256": manifest["source_video_sha256"], "source_end_ms": manifest["source_end_ms"],
        "source_preparation_seconds": manifest["preparation_seconds"], "wall_budget_seconds": 300,
        "timestamp_policy": "APPROXIMATE_NATIVE_VIDEO_OBSERVATIONS_NOT_EXACT_SOURCE_PROOF",
        "planned_plays": len(manifest["packets"]), "new_model_calls": 0, "reused_model_calls": 0,
        "plays": [], "failed_preparations": []}
    pilot.write_json(output/"result.json", summary)
    jobs, prepared = [], {}
    for packet in manifest["packets"]:
        pid = packet["packet_id"]
        if time.monotonic() > started+210:
            summary["failed_preparations"].append({"packet_id": pid, "error": "PREPARATION_BUDGET_EXHAUSTED"})
            continue
        options = {"spatial_references": True, "model": "gemini-3.8-flash", "packet_id": pid}
        if pid == known["selected_packet"]:
            options.update(comparison_receipt=baseline_receipt, reuse_encoded_videos=known_videos)
        try:
            result, job, _ = prepare_request(manifest_path, output/"plays"/pid, profile_path, **options)
        except (ValueError, OSError, TimeoutError, subprocess.SubprocessError) as exc:
            safe = str(exc) if str(exc) in {"REQUEST_IMAGE_BUDGET_EXCEEDED", "COMPARISON_INPUT_NOT_IDENTICAL"} else type(exc).__name__
            summary["failed_preparations"].append({"packet_id": pid, "error": safe})
            continue
        prepared[pid] = result
        if pid == known["selected_packet"]:
            if result["request_audit"]["payload_sha256"] != cached["payload_sha256"]:
                raise ValueError("CACHED_NATIVE_REQUEST_NOT_IDENTICAL")
            result.update(model_status="COMPLETED_REUSED", raw_native_observations=json.loads(cached["raw_response"]),
                          reused_origin_run=known["origin_run"])
            summary["reused_model_calls"] += 1
            pilot.write_json(output/"responses"/(pid+".json"), {**cached, "reused_in_this_run": True})
        else:
            job["packet_id"] = pid
            jobs.append(job)
        print(json.dumps({"packet_id": pid, "payload_bytes": result["request_audit"]["payload_bytes"],
                          "prepared_seconds": round(time.monotonic()-started, 3)}), flush=True)
    summary["request_preparation_seconds"] = round(time.monotonic()-started, 3)
    summary["status"] = "RUNNING_NATIVE_SOURCE_PLAYS"
    pilot.write_json(output/"result.json", summary)
    for response in transport.run_jobs(jobs, "emergent", "gemini-3.8-flash", deadline=started+300, per_call_s=90):
        pid = response["packet_id"]
        pilot.write_json(output/"responses"/(pid+".json"), response)
        result = prepared[pid]
        result["model_status"] = response["status"]
        if response["status"] == "COMPLETED":
            result["raw_native_observations"] = json.loads(response["raw_response"])
            summary["new_model_calls"] += 1
        print(json.dumps({"packet_id": pid, "status": response["status"],
                          "model_seconds": response.get("elapsed_seconds")}), flush=True)
    summary["plays"] = [prepared[p["packet_id"]] for p in manifest["packets"] if p["packet_id"] in prepared]
    summary["analysis_seconds"] = round(time.monotonic()-started, 3)
    summary["status"] = "ALL_NATIVE_PLAY_RESPONSES_RETURNED" if (
        summary["new_model_calls"]+summary["reused_model_calls"] == summary["planned_plays"]
        and not summary["failed_preparations"]) else "PARTIAL_NATIVE_PLAY_EXPERIMENT"
    pilot.write_json(output/"result.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--resume-profile", required=True)
    parser.add_argument("--known-receipt", required=True)
    parser.add_argument("--baseline-receipt", required=True)
    parser.add_argument("--known-videos", required=True)
    args = parser.parse_args()
    result = run(args.prepared, args.output, args.resume_profile, args.known_receipt, args.baseline_receipt, args.known_videos)
    raise SystemExit(0 if result["status"] == "ALL_NATIVE_PLAY_RESPONSES_RETURNED" else 3)
