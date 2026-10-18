"""One source-derived outcome gap, continuous native images, existing resolver.

The previous native response supplies navigation only. Its claimed outcome and
the evaluator's expected events never enter the new request.
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
from scripts.probe_native_gaps import plan
from scripts.probe_native_play import spatial_reference_items


def outcome_gap(manifest, native):
    if native["source_video_sha256"] != manifest["source_video_sha256"]:
        raise ValueError("SOURCE_INPUT_MISMATCH")
    candidates = [j for j in plan(manifest, native)
                  if j["reason"] == "ACTIVE_BALL_OUTCOME_AFTER_ATTEMPT"]
    if len(candidates) != 1:
        raise ValueError("UNIQUE_OUTCOME_GAP_REQUIRED")
    return candidates[0]


def prepare(manifest_path, native_path, profile_path, output):
    import cv2
    started, output = time.monotonic(), Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("OUTPUT_MUST_BE_NEW_OR_EMPTY")
    manifest, native, profile = map(p.read_json, (manifest_path, native_path, profile_path))
    if (p.digest(manifest["source_video"]) != manifest["source_video_sha256"]
            or profile["source_video_sha256"] != manifest["source_video_sha256"]):
        raise ValueError("SOURCE_INPUT_MISMATCH")
    receipt = profile["receipt"]
    if (receipt["status"] != "COMPLETED" or receipt["origin"] != "LIVE_MODEL_REQUEST"
            or hashlib.sha256(receipt["raw_response"].encode()).hexdigest() != receipt["response_sha256"]
            or sorted(i["sha256"] for i in receipt["images"]) != sorted(r["sha256"] for r in manifest["references"])):
        raise ValueError("IDENTITY_PROFILE_UNRESOLVED")
    question = outcome_gap(manifest, native)
    manifest = p.apply_identity_profile(manifest, json.loads(receipt["raw_response"]))
    local = [r for r in manifest["references"] if question["start_ms"] <= r["media_ms"] <= question["end_ms"]]
    ids = list(dict.fromkeys(manifest["identity_profile"]["canonical_reference_ids"] +
                             [r["reference_id"] for r in local]))
    cap = cv2.VideoCapture(manifest["source_video"])
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    # Same original-selection union as the gap reader; keep the full pitch width.
    top = max(0, min(r["box"]["y"]-r["box"]["h"] for r in manifest["references"]))
    bottom = min(1, max(r["box"]["y"]+2*r["box"]["h"] for r in manifest["references"]))
    box = [0, int(top*height), width, int(bottom*height)]
    detail = []
    try:
        while True:
            if time.monotonic()-started > 45:
                raise TimeoutError("SOURCE_IMAGE_PREPARATION_BUDGET")
            ok, pixels = cap.read()
            if not ok:
                break
            ms = round(cap.get(cv2.CAP_PROP_POS_MSEC))
            if ms > question["detail_end_ms"]:
                break
            if question["detail_start_ms"] <= ms:
                image = p._save_image(output/"detail"/f"s{ms:09}.jpg", pixels[box[1]:box[3]], 1280, 50)
                detail.append({"frame_id": f"s{ms:09}", "media_ms": ms, "source_crop_box": box, **image})
    finally:
        cap.release()
    if len(detail) < 2 or any(not 0 < b["media_ms"]-a["media_ms"] <= 18 for a,b in zip(detail, detail[1:])):
        raise ValueError("CONTINUOUS_NATIVE_COVERAGE_REQUIRED")
    overview = []
    for frame in manifest["frames"]:
        if question["start_ms"] <= frame["media_ms"] <= question["end_ms"]:
            image = p._save_image(output/"overview"/(frame["frame_id"]+".jpg"), cv2.imread(frame["path"]), 768, 70)
            overview.append({**frame, **image})
    # The resolver receives the union of actually delivered source instants.
    rows = {f["frame_id"]: f for f in overview + detail}
    enriched = {**manifest, "frames": sorted(rows.values(), key=lambda f:f["media_ms"])}
    packet = {"packet_id": question["packet_id"], "start_ms": question["start_ms"],
              "end_ms": question["end_ms"], "core_start_ms": question["start_ms"],
              "core_end_ms": question["end_ms"]+1, "reference_ids": ids,
              "frame_ids": list(rows), "question": question["question"], "contact_sequence_evidence": True}
    # packet_items supplies the existing action/contact-bracket schema unchanged.
    items = p.packet_items(enriched, {**packet, "frame_ids": []})
    spatial, spatial_audit = spatial_reference_items(manifest, packet, local, output/"identity")
    items.extend(spatial)
    for frame, kind in sorted([(f,"overview") for f in overview]+[(f,"native detail") for f in detail],
                              key=lambda row:(row[0]["media_ms"], row[1])):
        items.extend([{"type":"text", "text":f"Source frame {frame['frame_id']}, {kind}, source_ms={frame['media_ms']}"+
                       (", original source crop="+json.dumps(box) if kind == "native detail" else "")},
                      {"type":"image", "path":frame["path"], "sha256":frame["sha256"]}])
    _, _, audit = t.build_request("emergent", "gpt-6-astra", items, reasoning_effort="medium", image_detail="high")
    result = {"status":"PREFLIGHT_ONLY", "source_video_sha256":manifest["source_video_sha256"],
              "native_navigation_sha256":p.digest(native_path), "question":question,
              "expected_answers_used_as_input":False, "production_pipeline_changed":False,
              "independent_visual_correctness_verified":False, "target_events":[],
              "overview_instants":len(overview), "native_instants":len(detail),
              "native_first_ms":detail[0]["media_ms"], "native_last_ms":detail[-1]["media_ms"],
              "source_crop_box":box, "spatial_reference_audit":spatial_audit,
              "detail_jpeg_quality":50, "overview_jpeg_quality":70,
              "source_preparation_seconds":round(time.monotonic()-started,3), "request_audit":audit}
    p.write_json(output/"preflight.json", result)
    return result, enriched, packet, items


def run(args):
    started = time.monotonic()
    result, manifest, packet, items = prepare(args.prepared, args.native_result, args.resume_profile, args.output)
    if args.preflight_only:
        return result
    receipt = t.run_jobs([{"packet_id":packet["packet_id"], "items":items,
                           "reasoning_effort":"medium", "image_detail":"high"}],
                         "emergent", "gpt-6-astra", deadline=time.monotonic()+125, per_call_s=120)[0]
    p.write_json(Path(args.output)/"responses"/(packet["packet_id"]+".json"), receipt)
    result.update(status=receipt["status"], model_seconds=receipt.get("elapsed_seconds"))
    if receipt["status"] == "COMPLETED":
        observed = p.resolve_response(p.parse_response(receipt["raw_response"]), manifest, packet,
            {k:receipt[k] for k in ("packet_id","payload_sha256","response_sha256","origin")})
        result.update(p.reconcile([observed]))
        result["resolved_observations"] = observed
    result["probe_seconds"] = round(time.monotonic()-started,3)
    p.write_json(Path(args.output)/"result.json", result)
    print(json.dumps(result), flush=True)
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("prepared", "native-result", "resume-profile", "output"):
        cli.add_argument("--"+name, required=True)
    cli.add_argument("--preflight-only", action="store_true")
    args = cli.parse_args()
    result = run(args)
    raise SystemExit(0 if args.preflight_only or result["status"] == "COMPLETED" else 3)
