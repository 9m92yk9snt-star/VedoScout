"""Bounded paired perception probe; no expected action answers enter requests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sequence_pilot as pilot
import sequence_pilot_transport as transport


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def catalog():
    """Normal read-only proxy model listing; never export headers/account data."""
    try:
        request = urllib.request.Request("https://integrations.emergentagent.com/llm/models",
            headers={"Authorization": "Bearer " + os.environ["EMERGENT_LLM_KEY"]})
        with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            return {"status": "BYTE_CAP"}
        rows = json.loads(raw).get("data", [])
        return {"status": "RETURNED", "model_ids": sorted({r["id"] for r in rows
            if isinstance(r, dict) and isinstance(r.get("id"), str)
            and re.fullmatch(r"[A-Za-z0-9_./:-]{1,160}", r["id"])})}
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        return {"status": "HTTP_ERROR", "http_status": status}
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "UNAVAILABLE"}


def run(manifest_path, out, model="gemini-2.5-pro", single=False):
    started, out = time.monotonic(), Path(out)
    manifest = pilot.read_json(manifest_path)
    deadline = started + 180
    result = {"status": "FOCUSED_DETAIL_PROBE", "production_pipeline_changed": False,
              "expected_answers_used_as_input": False, "independent_visual_correctness_verified": False,
              "source_video_sha256": manifest["source_video_sha256"],
              "prior_preparation_seconds": manifest["preparation_seconds"], "target_events": [],
              "model_catalog": catalog(), "comparisons": {}, "requested_model": model}
    pilot.write_json(out / "result.json", result)
    if result["model_catalog"].get("http_status") in {401, 403}:
        return
    receipt = transport.run_jobs([{"packet_id": "identity_profile", "items": pilot.identity_items(manifest),
        "reasoning_effort": "low"}], "emergent", "gemini-2.5-pro", deadline=deadline, per_call_s=60)[0]
    pilot.write_json(out / "responses" / "identity_profile.json", receipt)
    if receipt["status"] != "COMPLETED":
        result["status"] = "PROFILE_FAILED"
        pilot.write_json(out / "result.json", result)
        return
    manifest = pilot.apply_identity_profile(manifest, json.loads(receipt["raw_response"]))
    # Most original selections per source second; no reference event times or outcomes.
    def density(packet):
        lo, hi = packet.get("core_start_ms", packet["start_ms"]), packet.get("core_end_ms", packet["end_ms"])
        return sum(lo <= r["media_ms"] < hi for r in manifest["references"]) / max(1, hi - lo)
    packet = max(manifest["packets"], key=density)
    items = pilot.packet_items(manifest, packet)
    result.update(identity_profile=manifest["identity_profile"], selected_packet=packet,
                  selection_strategy="ORIGINAL_TAP_DENSITY_PER_SOURCE_SECOND")
    variants = [("detail_high", "high")] if single else [("detail_default", None), ("detail_high", "high")]
    jobs = [{"packet_id": name, "items": items, "reasoning_effort": "low", "image_detail": detail}
            for name, detail in variants]
    for job in jobs:
        transport.build_request("emergent", model, items,
                                reasoning_effort="low", image_detail=job["image_detail"])
    for receipt in transport.run_jobs(jobs, "emergent", model, deadline=deadline, per_call_s=90):
        pilot.write_json(out / "responses" / (receipt["packet_id"] + ".json"), receipt)
        if receipt["status"] == "COMPLETED":
            observed = pilot.resolve_response(pilot.parse_response(receipt["raw_response"]), manifest, packet,
                {k: receipt[k] for k in ("packet_id", "payload_sha256", "response_sha256", "origin")})
            result["comparisons"][receipt["packet_id"]] = pilot.reconcile([observed])
    result["analysis_seconds"] = round(time.monotonic() - started, 3)
    pilot.write_json(out / "result.json", result)


def run_native(manifest_path, out, model):
    """Compare normal-duration video sampling, retaining raw observations only."""
    started, out = time.monotonic(), Path(out)
    manifest = pilot.read_json(manifest_path)
    if pilot.digest(manifest["source_video"]) != manifest["source_video_sha256"]:
        raise ValueError("SOURCE_VIDEO_CHANGED")
    out.mkdir(parents=True, exist_ok=False)
    video = out / "normal_source_8fps.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", manifest["source_video"],
        "-map", "0:v:0", "-vf", "fps=8,scale=720:1280", "-an", "-c:v", "libx264",
        "-preset", "fast", "-crf", "29", "-movflags", "+faststart", str(video)],
        check=True, timeout=60, capture_output=True)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=width,height,r_frame_rate,nb_frames", "-of", "json", str(video)],
        check=True, timeout=10, capture_output=True).stdout)
    deadline = started + 240
    result = {"status": "NATIVE_VIDEO_SAMPLING_PROBE", "production_pipeline_changed": False,
        "expected_answers_used_as_input": False, "independent_visual_correctness_verified": False,
        "target_events": [], "source_video_sha256": manifest["source_video_sha256"],
        "prior_preparation_seconds": manifest["preparation_seconds"], "encoded_video": probe,
        "encoded_video_sha256": pilot.digest(video), "requested_model": model,
        "encoding": {"width": 720, "height": 1280, "fps": 8, "codec": "libx264", "crf": 29, "audio": False},
        "native_observations": {}, "timestamp_policy": "MODEL_VIDEO_TIMES_APPROXIMATE; NOT_EXACT_FRAME_PROOF"}
    pilot.write_json(out / "result.json", result)
    receipt = transport.run_jobs([{"packet_id": "identity_profile", "items": pilot.identity_items(manifest),
        "reasoning_effort": "low"}], "emergent", model, deadline=deadline, per_call_s=60)[0]
    pilot.write_json(out / "responses" / "identity_profile.json", receipt)
    if receipt["status"] != "COMPLETED":
        return
    manifest = pilot.apply_identity_profile(manifest, json.loads(receipt["raw_response"]))
    result["identity_profile"] = manifest["identity_profile"]
    refs = {r["reference_id"]: r for r in manifest["references"]}
    items = [{"type": "text", "text": "Read this normal-speed football video from beginning to end. "
        "Video time zero is original source time zero. Reference pictures are identity examples only, not plays. "
        "Observe the active ball and keep passer, recipient and finisher as different physical people. "
        "A pass directly to the teammate who scores is an assist for the passer; never give the passer the teammate's goal. "
        "Track the same person across the camera pan. Do not guess hidden numbers. "
        "A stationary spare ball inside a goal is not the active shot ball. Follow the active ball after keeper contact; "
        "a dive alone is not a save, and a stationary spare ball is not goal evidence. "
        "Ignore music and audio. Include selected-player attempts, saved shots, goals, passes leading to teammates' "
        "finishes and other clear ball actions. Identify actual release, reception, finish and outcome, not preparation touches. "
        "No expected event counts, times or outcomes are given. When unseen, say uncertain. "
        'Return JSON {"events":[{"type":"SHOT|GOAL|ASSIST|PASS|OTHER",'
        '"selected_actor":true,"actor_description":"visible identity",'
        '"start_s":0,"contact_s":0,"receiver_description":null,"receive_s":null,'
        '"finisher_description":null,"shot_s":null,"outcome_s":0,'
        '"outcome":"SAVED|GOAL|TEAMMATE_GOAL|COMPLETED|UNKNOWN|OTHER",'
        '"evidence":"concrete visible before/after ball and identity evidence",'
        '"uncertainty":"unseen connection or empty"}]} . '
        "Shared identity profile: " + json.dumps(manifest["identity_profile"])}]
    for ref_id in manifest["identity_profile"]["canonical_reference_ids"]:
        r = refs[ref_id]
        items.extend([{"type": "text", "text": "Identity reference " + ref_id},
                      {"type": "image", "path": r["path"], "sha256": r["sha256"]}])
    jobs = []
    for fps in (1, 8):
        media = items + [{"type": "text", "text": "Original action video follows; it is not slowed or held."},
            {"type": "video", "path": str(video), "sha256": pilot.digest(video), "fps": fps}]
        transport.build_request("emergent", model, media, reasoning_effort="low", image_detail="high")
        jobs.append({"packet_id": f"native_{fps}fps", "items": media, "reasoning_effort": "low", "image_detail": "high"})
    for receipt in transport.run_jobs(jobs, "emergent", model, deadline=deadline, per_call_s=120):
        pilot.write_json(out / "responses" / (receipt["packet_id"] + ".json"), receipt)
        if receipt["status"] == "COMPLETED":
            result["native_observations"][receipt["packet_id"]] = json.loads(receipt["raw_response"])
    result["analysis_seconds"] = round(time.monotonic() - started, 3)
    pilot.write_json(out / "result.json", result)


def run_followup(manifest_path, out, model, action_path, profile_path):
    """Resume this experiment's real missing link; never replay completed calls."""
    started, out = time.monotonic(), Path(out)
    manifest = pilot.read_json(manifest_path)
    def receipt(path):
        saved = pilot.read_json(path)
        r = saved["receipt"]
        assert saved["source_video_sha256"] == manifest["source_video_sha256"]
        assert r["origin"] == "LIVE_MODEL_REQUEST" and r["status"] == "COMPLETED"
        assert hashlib.sha256(r["raw_response"].encode()).hexdigest() == r["response_sha256"]
        return r
    initial_receipt, profile_receipt = receipt(action_path), receipt(profile_path)
    manifest = pilot.apply_identity_profile(manifest, json.loads(profile_receipt["raw_response"]))
    def density(packet):
        lo, hi = packet["core_start_ms"], packet["core_end_ms"]
        return sum(lo <= r["media_ms"] < hi for r in manifest["references"]) / max(1, hi-lo)
    packet = max(manifest["packets"], key=density)
    initial = pilot.resolve_response(pilot.parse_response(initial_receipt["raw_response"]), manifest, packet,
        {k: initial_receipt[k] for k in ("packet_id", "payload_sha256", "response_sha256", "origin")})
    lo, hi = packet["core_start_ms"], packet["core_end_ms"]
    questions = [q for q in initial["questions"] if isinstance(q.get("focus_ms"), (int, float))
                 and lo <= q["focus_ms"] < hi]
    if not questions:
        raise ValueError("NO_FOCUSED_MISSING_LINK")
    q = questions[0]
    ids = list(dict.fromkeys(packet["reference_ids"] + [r["reference_id"] for r in manifest["references"]
                                                        if lo <= r["media_ms"] < hi]))
    job = {"packet_id": "missing_link", "phase": "FOLLOWUP", "round": 1,
           "start_ms": lo, "end_ms": hi-1, "reference_ids": ids,
           "question": {**q, "also_inspect": "Resolve the actor identity and actual last ball contact before the observed outcome. "
                        "Distinguish a pass to another finisher from an uninterrupted shot. Use the original in-play selections "
                        "as local identity evidence; they are not outcome answers."}}
    enriched, jobs = pilot.prepare_followups(manifest, [job], out, timeout_s=30)
    items = pilot.packet_items(enriched, jobs[0])
    transport.build_request("emergent", model, items, reasoning_effort="low", image_detail="high")
    result = {"status": "TARGETED_LINK_PROBE", "source_video_sha256": manifest["source_video_sha256"],
        "expected_answers_used_as_input": False, "production_pipeline_changed": False,
        "independent_visual_correctness_verified": False, "prior_preparation_seconds": manifest["preparation_seconds"],
        "completed_requests_replayed": False, "resumed_response_sha256": initial_receipt["response_sha256"],
        "question": job["question"], "reference_ids": ids, "initial": pilot.reconcile([initial]), "target_events": []}
    pilot.write_json(out / "result.json", result)
    r = transport.run_jobs([{"packet_id": "missing_link", "items": items, "reasoning_effort": "low", "image_detail": "high"}],
        "emergent", model, deadline=started+180, per_call_s=120)[0]
    pilot.write_json(out / "responses" / "missing_link.json", r)
    if r["status"] == "COMPLETED":
        followup = pilot.resolve_response(pilot.parse_response(r["raw_response"]), enriched, jobs[0],
            {k: r[k] for k in ("packet_id", "payload_sha256", "response_sha256", "origin")})
        # Keep conflicting initial and follow-up readings separately for inspection.
        result["followup"] = pilot.reconcile([followup])
        result["target_events"] = result["followup"]["target_events"]
    result["analysis_seconds"] = round(time.monotonic()-started, 3)
    pilot.write_json(out / "result.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="gemini-2.5-pro")
    parser.add_argument("--native-video", action="store_true")
    parser.add_argument("--single", action="store_true")
    parser.add_argument("--resume-action")
    parser.add_argument("--resume-profile")
    args = parser.parse_args()
    if args.resume_action and args.resume_profile:
        run_followup(args.prepared, args.output, args.model, args.resume_action, args.resume_profile)
    elif args.native_video:
        run_native(args.prepared, args.output, args.model)
    else:
        run(args.prepared, args.output, args.model, args.single)
