"""Build the real temporal reader inputs from an export, without any model calls.

python scripts/audit_temporal_video_inputs.py EXPORT VIDEO OUTPUT --trace-id TRACE
Reference outcomes/timestamps are deliberately not inputs to this utility.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import tempfile


def audit(export_dir, video_path, output_dir, trace_ids=()):
    import cv2
    import action_evidence_review as inspection
    import fix10a_vision_providers as vision
    import sequence_observation_context as context
    import video_model_input as video

    digest = video.sha256(video_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    results, wanted = [], set(trace_ids)
    for path in sorted((Path(export_dir)/"traces").glob("*.json")):
        trace = json.loads(path.read_text())
        if wanted and trace.get("trace_id") not in wanted:
            continue
        if (trace.get("source_video") or {}).get("sha256") != digest:
            raise ValueError("SOURCE_VIDEO_DOES_NOT_MATCH_TRACE")
        frames, window = trace["decoded_frames"], trace["window"]
        packet = context.build(window, frames, trace=trace, source_video=trace["source_video"])
        sampling = inspection.motion_sampling_plan({**window, "sequence_context": packet}, frames)
        times = sampling["media_ms"]
        by_ms = {f["media_ms"]: f for f in frames}
        labels = context.labels(frames)
        decoded = vision._read_frames(str(video_path), times)
        clock, paths, bodies, views = [], [], [], []
        with tempfile.TemporaryDirectory(prefix="motion_input_audit_") as directory:
            for index, ms in enumerate(times):
                actual_ms, image = decoded[ms]
                if actual_ms != ms:
                    raise ValueError("DECODED_SOURCE_CLOCK_MISMATCH")
                candidates = inspection.motion_body_candidates(by_ms[ms], body_labels=labels)
                view, roi, displayed = vision.motion_search_view(image, by_ms[ms], candidates)
                image_path = Path(directory)/f"{index}.jpg"
                if not vision._write_jpg(image_path, view):
                    raise ValueError("AUDIT_IMAGE_ENCODING_FAILED")
                paths.append(image_path); clock.append(ms); bodies.append(len(displayed)); views.append(roi)
            clip_path = output/f"{trace['trace_id']}.mp4"
            manifest = video.write_motion_clip(paths, clock, clip_path,
                max_dimension=1920 if any(r.get("views") for r in views) else 1280)
            manifest["sampling_plan"] = {k: v for k,v in sampling.items() if k != "media_ms"}
        cap = cv2.VideoCapture(str(clip_path))
        try:
            encoded = {"frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), "playback_fps": cap.get(cv2.CAP_PROP_FPS)}
        finally:
            cap.release()
        if encoded != {"frame_count": len(clock), "playback_fps": 1.}:
            raise ValueError("ENCODED_SOURCE_CLOCK_MISMATCH")
        results.append({"trace_id": trace["trace_id"], "scene_id": window["scene_id"],
            "motion_clip": manifest, "encoded": encoded, "labelled_body_frames": sum(n > 0 for n in bodies),
            "full_scene_frames": sum(any(v.get("view_id") == "OVERVIEW" for v in r.get("views") or []) for r in views),
            "detail_frames": sum(any(v.get("view_id") == "DETAIL" for v in r.get("views") or []) for r in views),
            "all_times_are_actual_source_pts": all(context.actual(by_ms[ms], window["scene_id"]) for ms in clock)})
    if wanted - {r["trace_id"] for r in results}:
        raise ValueError("REQUESTED_TRACE_NOT_FOUND")
    if not results:
        raise ValueError("NO_TRACES_FOUND")
    result = {"mode": "LOCAL_VIDEO_INPUT_AUDIT_ONLY", "source_video_sha256": digest,
        "new_model_calls": 0, "perception_accuracy_established": False, "inputs": results}
    (output/"input_audit.json").write_text(json.dumps(result, indent=2)+"\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_dir", type=Path)
    parser.add_argument("video_path", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--trace-id", action="append", default=[])
    args = parser.parse_args()
    def forbidden(*_args, **_kwargs):
        raise RuntimeError("Input audit cannot access the network or call a model")
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    socket.socket.connect = forbidden
    socket.create_connection = forbidden
    print(json.dumps(audit(args.export_dir, args.video_path, args.output_dir, args.trace_id), indent=2))


if __name__ == "__main__":
    main()
