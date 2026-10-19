"""One source-derived unresolved terminal outcome; verify and reuse prior calls.

Prior answers supply navigation and replay only. New request receives original
images and a generic question, never historical action answers or reference cases.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sequence_pilot as p
import sequence_pilot_transport as t
from scripts.run_sequence_pilot import (
    FRESH_IDENTITY_INSTRUCTION, fresh_original_manifest, original_spatial_items,
)


def items_for(manifest, packet, output):
    packet = {**packet, "contact_sequence_evidence": True}
    items = p.packet_items(manifest, packet)
    items.insert(1, {"type": "text", "text": FRESH_IDENTITY_INSTRUCTION})
    spatial, _ = original_spatial_items(manifest, packet, output)
    prefix = len(p.packet_items(manifest, {**packet, "frame_ids": []}))+1
    items[prefix:prefix] = spatial
    return items


def checked_observation(receipt, manifest, packet):
    if (receipt["status"] != "COMPLETED" or receipt["origin"] != "LIVE_MODEL_REQUEST"
            or receipt["requested_model"] != "gpt-6-astra"
            or hashlib.sha256(receipt["raw_response"].encode()).hexdigest() != receipt["response_sha256"]):
        raise ValueError("REVIEW_RECEIPT_MISMATCH")
    observed = p.resolve_response(p.parse_response(receipt["raw_response"]), manifest, packet,
        {k: receipt[k] for k in ("packet_id", "payload_sha256", "response_sha256", "origin")})
    observed["packet_id"] = packet["packet_id"]
    return observed


def outcome_job(manifest, merged, previous_jobs):
    """Unique explicit selected-shot outcome gap; include release and aftermath."""
    explicit = {q.get("source_action_key") for q in merged["questions"]
                if q["reason"] == "OUTCOME" and q.get("explicit_model_question")}
    shots = [e for e in merged["events"] if e["kind"] == "SHOT"
             and e["selected_player"] is True and e["outcome"] == "UNKNOWN"
             and e.get("contact_interval_ms") and explicit.intersection(e["source_action_keys"])]
    if len(shots) != 1:
        raise ValueError("UNIQUE_EXPLICIT_TERMINAL_OUTCOME_REQUIRED")
    event = shots[0]
    parents = [j for j in previous_jobs if j["packet_id"] in event["source_packet_ids"]]
    if len(parents) != 1:
        raise ValueError("UNIQUE_REVIEW_PARENT_REQUIRED")
    parent = parents[0]
    before, after = event["contact_interval_ms"]
    return {"packet_id": "outcome_review_001", "phase": "FOLLOWUP", "round": 2,
        "start_ms": parent["start_ms"], "end_ms": parent["end_ms"],
        "reference_ids": parent["reference_ids"][:], "contact_sequence_evidence": True,
        "replaces_review_packet_id": parent["packet_id"],
        "replaces_initial_packet_id": parent["replaces_initial_packet_id"],
        "detail_start_ms": max(parent["start_ms"], before-100),
        "detail_end_ms": min(parent["end_ms"], after+1500),
        "extra_detail_frame_ids": [v["frame"] for v in event["outcome_evidence"]],
        "question": {"reason": "OUTCOME", "focus_ms": after+750,
            "instruction": "Follow the active ball continuously from the physical striking contact through the terminal outcome. Establish the striker, any intervening touch and the ball's motion before and after it. Distinguish stationary spare balls. Keep specific contact, identity or outcome questions where images are insufficient."}}


def execute(args):
    started, out = time.monotonic(), Path(args.output)
    if out.exists() and any(out.iterdir()):
        raise ValueError("OUTPUT_MUST_BE_NEW_OR_EMPTY")
    manifest = fresh_original_manifest(p.read_json(args.prepared))
    initial, saved = p.read_json(args.initial), p.read_json(args.reviews)
    if saved["source_video_sha256"] != manifest["source_video_sha256"]:
        raise ValueError("SOURCE_INPUT_MISMATCH")
    # Reproduce all ten initial requests without a provider key or model calls.
    specs = [{k: packet[k] for k in ("packet_id", "start_ms", "end_ms", "frame_ids", "reference_ids")}
             for packet in manifest["packets"]]
    fingerprint = hashlib.sha256(json.dumps(specs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    initial_packets = {j["packet_id"]: j for j in manifest["packets"]}
    if (initial["source_video_sha256"] != manifest["source_video_sha256"]
            or initial["original_taps_sha256"] != manifest["original_taps_sha256"]
            or initial["packet_fingerprint"] != fingerprint
            or initial.get("identity_mode") != "FRESH_ORIGINAL_SELECTIONS"
            or set(initial_packets) != {r["packet_id"] for r in initial["receipts"]}
            or len(initial["receipts"]) != len(initial_packets)):
        raise ValueError("INITIAL_REPLAY_FAILED")
    initial_observations = []
    for receipt in initial["receipts"]:
        packet = initial_packets[receipt["packet_id"]]
        items = items_for(manifest, packet, out/"initial-spatial"/packet["packet_id"])
        _, _, audit = t.build_request("emergent", "gpt-6-astra", items,
                                     reasoning_effort="medium", image_detail="high")
        if audit["payload_sha256"] != receipt["payload_sha256"]:
            raise ValueError("INITIAL_REQUEST_MISMATCH")
        initial_observations.append(checked_observation(receipt, manifest, packet))
    base = p.reconcile(initial_observations)
    previous_jobs = p.plan_contact_reviews(manifest, base, limit=6, terminal_only=True)
    review_manifest, previous_jobs = p.prepare_contact_reviews(manifest, previous_jobs,
        out/"review-replay", native_detail_policy="local_half_q50")
    by_id = {j["packet_id"]: j for j in previous_jobs}
    if set(by_id) != {r["packet_id"] for r in saved["receipts"]}:
        raise ValueError("REVIEW_SET_MISMATCH")
    prior = []
    for receipt in saved["receipts"]:
        packet = by_id[receipt["packet_id"]]
        items = items_for(review_manifest, packet, out/"review-spatial"/packet["packet_id"])
        _, _, audit = t.build_request("emergent", "gpt-6-astra", items,
                                     reasoning_effort="medium", image_detail="high")
        if audit["payload_sha256"] != receipt["payload_sha256"]:
            raise ValueError("REVIEW_REQUEST_MISMATCH")
        prior.append(checked_observation(receipt, review_manifest, packet))
    replaced = {j["replaces_initial_packet_id"] for j in previous_jobs}
    prior = [r for r in initial_observations if r["packet_id"] not in replaced]+prior
    merged = p.reconcile(prior)
    for field in ("events", "questions", "conflicts", "counts"):
        if merged[field] != saved["result"][field]:
            raise ValueError("REVIEW_REPLAY_RESULT_MISMATCH")
    job = outcome_job(manifest, merged, previous_jobs)
    enriched, jobs = p.prepare_contact_reviews(manifest, [job], out/"outcome",
                                             native_detail_policy=args.detail_policy)
    packet = jobs[0]
    items = items_for(enriched, packet, out/"outcome-spatial")
    _, _, audit = t.build_request("emergent", "gpt-6-astra", items,
                                 reasoning_effort="medium", image_detail="high")
    # A failed new transport cannot erase the previously verified observations.
    result = {**merged, "status": "PREFLIGHT_ONLY", "source_video_sha256": manifest["source_video_sha256"],
        "fresh_end_to_end_run": False, "initial_requests_sent_in_this_run": 0,
        "previous_review_requests_sent_in_this_run": 0,
        "verified_reused_requests": len(initial["receipts"])+len(saved["receipts"]),
        "expected_answers_used_as_input": False, "production_pipeline_changed": False,
        "independent_visual_correctness_verified": False,
        "navigation_origin_run": saved["origin_run"], "request_audit": audit, "job": packet,
        "source_preparation_seconds": round(time.monotonic()-started, 3)}
    p.write_json(out/"preflight.json", result)
    if args.preflight_only:
        print(result["status"], result["source_preparation_seconds"],
              {k: audit[k] for k in ("payload_sha256", "payload_bytes", "explicit_image_count")}, flush=True)
        return result
    receipt = t.run_jobs([{"packet_id": packet["packet_id"], "items": items,
                          "reasoning_effort": "medium", "image_detail": "high"}],
                         "emergent", "gpt-6-astra", deadline=time.monotonic()+125, per_call_s=120)[0]
    p.write_json(out/"responses"/(packet["packet_id"]+".json"), receipt)
    result.update(status=receipt["status"], model_seconds=receipt.get("elapsed_seconds"))
    p.write_json(out/"result.json", result)
    if receipt["status"] == "COMPLETED":
        observed = checked_observation(receipt, enriched, packet)
        result["previous_terminal_observations"] = [r for r in prior
            if r["packet_id"] == packet["replaces_review_packet_id"]]
        result.update(p.reconcile([r for r in prior
            if r["packet_id"] != packet["replaces_review_packet_id"]]+[observed]))
        result["resolved_observations"] = observed
    result["continuation_seconds"] = round(time.monotonic()-started, 3)
    p.write_json(out/"result.json", result)
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("prepared", "initial", "reviews", "output"):
        cli.add_argument("--"+name, required=True)
    cli.add_argument("--preflight-only", action="store_true")
    cli.add_argument("--detail-policy", choices=("source_union_q50", "local_half_q50"),
                     default="source_union_q50")
    args = cli.parse_args()
    result = execute(args)
    raise SystemExit(0 if args.preflight_only or result["status"] == "COMPLETED" else 3)
