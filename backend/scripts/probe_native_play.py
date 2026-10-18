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


def run(manifest_path, output, profile_path):
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
        items.extend([{"type": "text", "text": "Identity reference "+ref_id+" (not action evidence)"},
                      {"type": "image", "path": r["path"], "sha256": r["sha256"]}])
    for view in views:
        items.extend([{"type": "text", "text": view["name"]+"; same clip-relative time zero"},
            {"type": "video", "path": view["path"], "sha256": view["sha256"], "fps": view["fps"]}])
    model = "gemini-3.1-pro-preview"
    _, _, audit = transport.build_request("emergent", model, items, reasoning_effort="low", image_detail="high")
    result = {"status": "SHORT_SYNCHRONIZED_NATIVE_VIDEO_PROBE", "target_events": [],
        "production_pipeline_changed": False, "expected_answers_used_as_input": False,
        "independent_visual_correctness_verified": False,
        "source_video_sha256": manifest["source_video_sha256"],
        "selected_packet": packet["packet_id"], "selection_strategy": "ORIGINAL_TAP_DENSITY_PER_SOURCE_SECOND",
        "source_start_ms": packet["core_start_ms"], "source_end_ms": packet["core_end_ms"],
        "timestamp_policy": "APPROXIMATE_CLIP_RELATIVE_TIMES_NOT_EXACT_SOURCE_PROOF",
        "detail_source_crop_box": box, "reference_ids": ids, "request_audit": audit,
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--resume-profile", required=True)
    args = parser.parse_args()
    run(args.prepared, args.output, args.resume_profile)
