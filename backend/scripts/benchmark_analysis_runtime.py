"""Offline detector/pixel reuse comparison on an existing source/evidence export.

No database, remote model or expected event labels are used. This is a component
benchmark, never a claim of full-report latency or automatic event accuracy.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
import cv_detect
import dense_track_refinement as dense
from scripts import detector_runtime_probe as detector_runtime
import fix10a_vision_providers as vision
from source_frame_cache import SourceFrameCache


def compare(first, second):
    same_counts, max_box_delta, max_conf_delta = True, 0., 0.
    for a, b in zip(first, second):
        if len(a) != len(b):
            same_counts = False
            continue
        order = lambda row: (row["box"]["x"], row["box"]["y"])
        for x, y in zip(sorted(a, key=order), sorted(b, key=order)):
            max_box_delta = max(max_box_delta, *(abs(x["box"][k]-y["box"][k]) for k in ("x", "y", "w", "h")))
            max_conf_delta = max(max_conf_delta, abs(x["confidence"]-y["confidence"]))
            if x.get("top_class_id") != y.get("top_class_id"):
                same_counts = False
    return same_counts, max_box_delta, max_conf_delta


def benchmark(video, trace_dir, samples_per_window=8):
    times = set()
    windows = []
    for path in sorted(Path(trace_dir).glob("*.json")):
        trace = json.loads(path.read_text())
        native = [f["media_ms"] for f in trace.get("decoded_frames") or []
                  if f.get("time_authority") == "ACTUAL_MEDIA_PTS" and not f.get("used_fallback")]
        if not native:
            continue
        picks = [native[int(round(i*(len(native)-1)/max(1, samples_per_window-1)))]
                 for i in range(samples_per_window)]
        times.update(picks)
        windows.append(trace["trace_id"])
    if not times:
        raise ValueError("No measured source timestamps in the supplied traces")
    with Path(video).open("rb") as stream:
        source_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    threads = detector_runtime.cpu_threads()
    cv2.setNumThreads(threads)
    baseline = SimpleNamespace(ok=True, net=cv2.dnn.readNetFromONNX(str(cv_detect.MODEL_PATH)))
    accelerated = SimpleNamespace(ok=True, net=detector_runtime.OnnxDetector(cv_detect.MODEL_PATH))
    stats = {"opencv_seconds": 0., "onnxruntime_seconds": 0., "frames": 0,
             "same_candidate_counts_and_classes": True, "max_normalized_box_delta": 0., "max_confidence_delta": 0.,
             "baseline_people": 0, "baseline_ball_proposals": 0}
    # Decode in small batches; never retain a full video's uncompressed pixels.
    ordered = sorted(times)
    warmed = False
    for start in range(0, len(ordered), 8):
        images = vision._read_frames_uncached(str(video), ordered[start:start+8])
        for requested in sorted(images):
            actual, image = images[requested]
            if actual != requested:
                raise ValueError("Benchmark source PTS differs from saved evidence")
            height, width = image.shape[:2]
            if width > 960:
                image = cv2.resize(image, (960, max(2, int(round(height*960/width)))), interpolation=cv2.INTER_AREA)
            if not warmed:
                for net in (baseline, accelerated):
                    dense._detect_dense_people_and_ball(net, image, include_a7_support=True)
                warmed = True
            outputs = []
            # Alternate execution order to reduce a systematic warm-cache bias.
            nets = [("opencv_seconds", baseline), ("onnxruntime_seconds", accelerated)]
            if stats["frames"] % 2:
                nets.reverse()
            for name, net in nets:
                began = time.perf_counter()
                result = dense._detect_dense_people_and_ball(net, image, include_a7_support=True)
                stats[name] += time.perf_counter()-began
                outputs.append((name, result))
            results = dict(outputs)
            stats["baseline_people"] += len(results["opencv_seconds"][0])
            stats["baseline_ball_proposals"] += len(results["opencv_seconds"][1])
            same, box_delta, conf_delta = compare(results["opencv_seconds"], results["onnxruntime_seconds"])
            stats["same_candidate_counts_and_classes"] &= same
            stats["max_normalized_box_delta"] = max(stats["max_normalized_box_delta"], box_delta)
            stats["max_confidence_delta"] = max(stats["max_confidence_delta"], conf_delta)
            stats["frames"] += 1
        print(json.dumps({"progress_frames": stats["frames"], "planned_frames": len(ordered)}), flush=True)

    if stats["baseline_people"] == 0:
        raise ValueError("Benchmark did not detect any players; no performance/quality claim is valid")
    cache = SourceFrameCache()
    cache_times = ordered[:12]
    began = time.perf_counter()
    first = cache.read(video, cache_times, vision._read_frames_uncached)
    first_seconds = time.perf_counter()-began
    began = time.perf_counter()
    second = cache.read(video, cache_times, vision._read_frames_uncached)
    reused_seconds = time.perf_counter()-began
    pixel_equal = (first.keys() == second.keys() and all(
        first[ms][0] == second[ms][0] and np.array_equal(first[ms][1], second[ms][1]) for ms in first))
    return {"source_video_sha256": source_sha, "model_sha256": hashlib.sha256(cv_detect.MODEL_PATH.read_bytes()).hexdigest(),
            "threads_per_backend": threads, "source_windows": windows, **stats,
            "component_time_reduction_pct": round((1-stats["onnxruntime_seconds"]/stats["opencv_seconds"])*100, 2),
            "original_rounding_fallbacks": accelerated.net.rounding_fallbacks,
            "pixel_reuse": {"first_seconds": first_seconds, "reused_seconds": reused_seconds,
                            "byte_identical_and_same_pts": pixel_equal, **cache.metrics()},
            "remote_model_calls": 0, "full_report_latency_measured": False, "automatic_five_action_accuracy_measured": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("trace_dir", type=Path)
    parser.add_argument("--samples-per-window", type=int, default=8)
    args = parser.parse_args()
    if not 2 <= args.samples_per_window <= 64:
        parser.error("--samples-per-window must be between 2 and 64")
    print(json.dumps(benchmark(args.video, args.trace_dir, args.samples_per_window), indent=2))
