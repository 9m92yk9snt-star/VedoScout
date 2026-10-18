"""One automatically chosen play as synchronized native overview/detail videos.

No historical action observations or evaluation answers are read by this probe.
Native-video observations remain raw; they are not exact-frame event proof.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sequence_pilot as pilot
import sequence_pilot_transport as transport


def select_play(manifest):
    def density(packet):
        lo, hi = packet["core_start_ms"], packet["core_end_ms"]
        return sum(lo <= r["media_ms"] < hi for r in manifest["references"]) / max(1, hi-lo)
    packet = max(manifest["packets"], key=density)
    lo, hi = packet["core_start_ms"], packet["core_end_ms"]
    local = [r for r in manifest["references"] if lo <= r["media_ms"] < hi]
    if not local:
        raise ValueError("LOCAL_SELECTION_REQUIRED")
    top = max(0, min(r["box"]["y"]-r["box"]["h"] for r in local))
    bottom = min(1, max(r["box"]["y"]+2*r["box"]["h"] for r in local))
    return packet, local, top, bottom


def prepare_videos(manifest, output):
    if pilot.digest(manifest["source_video"]) != manifest["source_video_sha256"]:
        raise ValueError("SOURCE_VIDEO_CHANGED")
    packet, local, top, bottom = select_play(manifest)
    metadata = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", manifest["source_video"]],
        check=True, capture_output=True, timeout=10).stdout)["streams"][0]
    width, height = metadata["width"], metadata["height"]
    # Even crop bounds for yuv420p H.264; retain the full source width.
    y = int(top*height)//2*2
    crop_height = (min(height, int(bottom*height))-y)//2*2
    start = packet["core_start_ms"]/1000
    duration = (packet["core_end_ms"]-packet["core_start_ms"])/1000
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    views = []
    for name, fps, filters in (("overview", 8, "scale=720:1280"),
            ("native_detail", 24, f"crop={width}:{crop_height}:0:{y}")):
        path = output/(name+".mp4")
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", str(start),
            "-i", manifest["source_video"], "-t", str(duration), "-map", "0:v:0", "-an",
            "-vf", filters+f",fps={fps}", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)],
            check=True, capture_output=True, timeout=30)
        probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
            "format=duration,size:stream=width,height,r_frame_rate,nb_frames", "-of", "json", str(path)],
            check=True, capture_output=True, timeout=10).stdout)
        if abs(float(probe["format"]["duration"])-duration) > .15:
            raise ValueError("ENCODED_CLIP_DURATION_CHANGED")
        views.append({"name": name, "fps": fps, "path": str(path.resolve()),
            "sha256": pilot.digest(path), "metadata": probe})
    return packet, local, views, [0, y, width, y+crop_height]


def spatial_reference_items(manifest, packet, local, output):
    """Original human geometry in its full source frame, never an inferred track."""
    import cv2
    output = Path(output)
    cap = cv2.VideoCapture(manifest["source_video"])
    items, audit = [], []
    try:
        for ref in local:
            cap.set(cv2.CAP_PROP_POS_MSEC, ref["media_ms"])
            ok, pixels = cap.read()
            actual_ms = round(cap.get(cv2.CAP_PROP_POS_MSEC))
            if not ok or abs(actual_ms-ref["media_ms"]) > 18:
                raise ValueError("ORIGINAL_SELECTION_SOURCE_FRAME_UNAVAILABLE")
            height, width = pixels.shape[:2]
            b, point = ref["box"], ref["target_point"]
            x, y = round(b["x"]*width), round(b["y"]*height)
            right, bottom = round((b["x"]+b["w"])*width), round((b["y"]+b["h"])*height)
            px, py = round(point["x"]*width), round(point["y"]*height)
            cv2.rectangle(pixels, (x, y), (right, bottom), (255, 255, 0), 3)
            cv2.drawMarker(pixels, (px, py), (255, 255, 0), cv2.MARKER_CROSS, 22, 3)
            image = pilot._save_image(output/(ref["reference_id"]+"-source-selection.jpg"), pixels, 1280, 90)
            description = {"original_selection": ref["reference_id"], "source_ms": actual_ms,
                "approximate_clip_s": (actual_ms-packet["core_start_ms"])/1000,
                "original_source_box": b, "original_positive_point": point,
                "annotation_policy": "ORIGINAL_HUMAN_SELECTION_ONLY_AT_THIS_SOURCE_INSTANT_NOT_A_PREDICTED_TRACK"}
            items.extend([{"type": "text", "text":
                "IDENTITY ONLY: cyan box and cross place the ORIGINAL human selection in its full source frame. "
                "The cross marks the intended player, not the ball. A broad box may contain a neighbour. "
                "This label applies only at the displayed instant; infer later identity from video motion. "
                "No event or result is annotated. "+json.dumps(description)},
                {"type": "image", "path": image["path"], "sha256": image["sha256"]}])
            audit.append({**description, "annotated_image_sha256": image["sha256"]})
    finally:
        cap.release()
    return items, audit


def run(manifest_path, output, profile_path, *, spatial_references=False, model="gemini-3.1-pro-preview", comparison_receipt=None):
    if model not in {"gemini-3.1-pro-preview", "gemini-3.8-flash"}:
        raise ValueError("UNREVIEWED_NATIVE_MODEL")
    started = time.monotonic(); output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("OUTPUT_MUST_BE_NEW_OR_EMPTY")
    manifest = pilot.read_json(manifest_path)
    saved = pilot.read_json(profile_path); receipt = saved["receipt"]
    if (saved["source_video_sha256"] != manifest["source_video_sha256"]
            or receipt["status"] != "COMPLETED" or receipt["origin"] != "LIVE_MODEL_REQUEST"
            or hashlib.sha256(receipt["raw_response"].encode()).hexdigest() != receipt["response_sha256"]
            or sorted(i["sha256"] for i in receipt["images"]) != sorted(r["sha256"] for r in manifest["references"])):
        raise ValueError("IDENTITY_PROFILE_UNRESOLVED")
    manifest = pilot.apply_identity_profile(manifest, json.loads(receipt["raw_response"]))
    packet, local, views, box = prepare_videos(manifest, output/"videos")
    refs = {r["reference_id"]: r for r in manifest["references"]}
    ids = list(dict.fromkeys(manifest["identity_profile"]["canonical_reference_ids"]+
                             [r["reference_id"] for r in local]))
    items = [{"type": "text", "text":
        "Read this short football play. Two synchronized videos show EXACTLY THE SAME interval, "
        "not two plays: a full-frame overview and a native-pixel detail band. Both play at normal "
        "speed with no audio. Time 0 is the first instant of this clip in both views. "
        "Describe the active ball's possession and changes of motion from beginning to end. "
        "Keep each physical player separate, using readable numbers only. Identify the selected "
        "player using the original identity references, then follow who actually plays the ball, "
        "who receives it and who has the last touch. Examine before and after any short occlusion. "
        "Distinguish controlled possession from a deflection or mere proximity. Stationary spare "
        "balls are not the active ball. A goalkeeper dive alone does not determine the outcome. "
        "Do not assume a nearby player touched the ball or that nobody else touched it. "
        "Return uncertainty when the responsible player or final touch remains unseen. "
        "No expected action count, times or outcomes are provided. Use clip-relative approximate "
        "seconds; exact simultaneous foot/ball frames are not required. "
        'Return JSON {"players":[{"id":"p1","kit":"visible kit","visible_number":null,'
        '"selected":null}],"ball_sequence":[{"clip_s":0,"actor":"p1",'
        '"action":"observed ball action","recipient":null,"visible_evidence":"what changes",'
        '"uncertainty":"remaining alternatives or empty"}],'
        '"outcome":{"kind":"observed result or UNKNOWN","last_touch_player":null,'
        '"visible_evidence":"active ball before and after","uncertainty":"remaining alternatives or empty"},'
        '"selected_player_summary":"actions and outcomes attributable to this person"}. '
        "Identity-only profile: "+json.dumps(manifest["identity_profile"])}]
    for ref_id in ids:
        r = refs[ref_id]
        inside = packet["core_start_ms"] <= r["media_ms"] < packet["core_end_ms"]
        location = {"reference_id": ref_id, "source_ms": r["media_ms"],
            "in_this_play": inside, "original_full_frame_box_xywh": r["box"],
            "original_user_point": r.get("target_point")}
        if inside:
            location["clip_s"] = round((r["media_ms"]-packet["core_start_ms"])/1000, 3)
        items.extend([{"type": "text", "text": "Identity reference, not action evidence: "
            +json.dumps(location)+". Box and user point use normalized full overview coordinates, "
            "not the cropped detail video's coordinates. For an in-play reference, match the "
            "pictured person at that clip time before following them through the play. A crop "
            "can contain nearby players; do not transfer identity to the eventual recipient "
            "merely because their number is easier to read. Preserve uncertainty if the "
            "reference is ambiguous."},
                      {"type": "image", "path": r["path"], "sha256": r["sha256"]}])
    spatial_audit = []
    if spatial_references:
        additional, spatial_audit = spatial_reference_items(manifest, packet, local, output/"spatial-references")
        items.extend(additional)
    for view in views:
        items.extend([{"type": "text", "text": view["name"]+"; same clip-relative time zero"},
            {"type": "video", "path": view["path"], "sha256": view["sha256"], "fps": view["fps"]}])
    _, _, audit = transport.build_request("emergent", model, items, reasoning_effort="low", image_detail="high")
    comparison = None
    if comparison_receipt:
        baseline = pilot.read_json(comparison_receipt); old = baseline["receipt"]
        if (baseline["source_video_sha256"] != manifest["source_video_sha256"]
                or old["status"] != "COMPLETED" or old["origin"] != "LIVE_MODEL_REQUEST"
                or old["requested_model"] != "gemini-3.1-pro-preview"
                or hashlib.sha256(old["raw_response"].encode()).hexdigest() != old["response_sha256"]):
            raise ValueError("COMPARISON_RECEIPT_INVALID")
        _, original_body, original_audit = transport.build_request("emergent", old["requested_model"], items,
            reasoning_effort="low", image_detail="high")
        if original_audit["payload_sha256"] != old["payload_sha256"]:
            raise ValueError("COMPARISON_INPUT_NOT_IDENTICAL")
        before = json.loads(original_body)
        after = json.loads(transport.build_request("emergent", model, items,
            reasoning_effort="low", image_detail="high")[1])
        before.pop("model"); after.pop("model")
        if before != after:
            raise ValueError("COMPARISON_CHANGED_MORE_THAN_MODEL")
        comparison = {"origin_run": baseline["origin_run"], "baseline_model": old["requested_model"],
            "baseline_payload_sha256": old["payload_sha256"], "only_model_changed": True}
    result = {"status": "SHORT_SYNCHRONIZED_NATIVE_VIDEO_PROBE", "target_events": [],
        "production_pipeline_changed": False, "expected_answers_used_as_input": False,
        "independent_visual_correctness_verified": False,
        "source_video_sha256": manifest["source_video_sha256"],
        "selected_packet": packet["packet_id"], "selection_strategy": "ORIGINAL_TAP_DENSITY_PER_SOURCE_SECOND",
        "source_start_ms": packet["core_start_ms"], "source_end_ms": packet["core_end_ms"],
        "timestamp_policy": "APPROXIMATE_CLIP_RELATIVE_TIMES_NOT_EXACT_SOURCE_PROOF",
        "detail_source_crop_box": box, "reference_ids": ids, "request_audit": audit,
        "spatial_reference_audit": spatial_audit,
        "model_comparison": comparison,
        "encoded_views": [{k:v for k,v in view.items() if k != "path"} for view in views]}
    pilot.write_json(output/"result.json", result)
    response = transport.run_jobs([{"packet_id": "native_short_play", "items": items,
        "reasoning_effort": "low", "image_detail": "high"}], "emergent", model,
        deadline=started+150, per_call_s=120)[0]
    pilot.write_json(output/"responses"/"native_short_play.json", response)
    if response["status"] == "COMPLETED":
        result["raw_native_observations"] = json.loads(response["raw_response"])
    result.update(analysis_seconds=round(time.monotonic()-started, 3), model_status=response["status"])
    pilot.write_json(output/"result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--resume-profile", required=True)
    parser.add_argument("--spatial-references", action="store_true")
    parser.add_argument("--model", choices=["gemini-3.1-pro-preview", "gemini-3.8-flash"], default="gemini-3.1-pro-preview")
    parser.add_argument("--comparison-receipt")
    args = parser.parse_args()
    result = run(args.prepared, args.output, args.resume_profile,
                 spatial_references=args.spatial_references, model=args.model, comparison_receipt=args.comparison_receipt)
    raise SystemExit(0 if result["model_status"] == "COMPLETED" else 3)
