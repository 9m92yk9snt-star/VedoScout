"""Bounded paired perception probe; no expected action answers enter requests."""
import argparse
import json
import os
from pathlib import Path
import re
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


def run(manifest_path, out, model="gemini-2.5-pro"):
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
    jobs = [{"packet_id": name, "items": items, "reasoning_effort": "low", "image_detail": detail}
            for name, detail in [("detail_default", None), ("detail_high", "high")]]
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="gemini-2.5-pro")
    args = parser.parse_args()
    run(args.prepared, args.output, args.model)
