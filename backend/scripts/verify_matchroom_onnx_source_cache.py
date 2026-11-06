"""Verify exact prediction reuse on recorded source pixels with the serving ONNX engine.

Offline only: no provider requests, report mutations, new player inference authority,
or modification of the normal bounded scheduler. A single previously approved source
window is replayed with the same model: baseline, cold cache, then warm cache.
This is a local graphics-layer experiment, not full-report/live acceptance.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import cv2
from match_room_localization import validate
from match_room_position_evidence import bound_samples
from match_room_position_contours import contour_segments, observation_windows
from match_room_prediction_cache import CachedSegmenter
from native_player_segmentation import PersonSegmenter
from scripts.run_matchroom_single_tap_trial import prepare


def main():
    os.environ["SCOUTMEPLAY_MATCHROOM_ENGINE"] = "onnxruntime"
    cv2.setNumThreads(2)
    retained = json.loads((ROOT / "testdata/matchroom-completion/result.json").read_text())
    if retained.get("status") != "OBSERVATIONS_RETURNED":
        raise ValueError("SAVED_OBSERVATIONS_NOT_VALIDATED")
    record = retained["record"]
    source = ROOT / "testdata/sequence-pilot-orman400"
    anchors = json.loads((source / "anchors.json").read_text())
    raw = anchors["raw_marker_anchors"]
    while isinstance(raw, str):
        raw = json.loads(raw)
    selection = {"raw_marker_anchors": raw}
    frames = record["frames"]
    proof = {"proof_start_ms": frames[0]["media_ms"],
             "proof_end_ms": frames[-1]["media_ms"]}
    event = {"source_video_sha256": record["source_video_sha256"],
             "event_id": record["event_id"], "proof": proof}
    observed = bound_samples(event, selection, record, validate,
                             packet=record["packet_id"])
    if observed != retained["samples"]:
        raise ValueError("RECORDED_SOURCE_OBSERVATIONS_CHANGED")
    windows = observation_windows(observed, proof["proof_start_ms"],
                                  proof["proof_end_ms"])
    if not windows:
        raise ValueError("NO_SOURCE_CONFIRMED_CONTOUR_WINDOW")
    start, end = windows[0]
    if not 0 < end - start <= 1500:
        raise ValueError("CONTOUR_WINDOW_OUT_OF_BOUNDS")

    with tempfile.TemporaryDirectory(prefix="matchroom-onnx-replay-") as temp:
        work = Path(temp)
        video, _ = prepare(source, work / "source")
        with video.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != record["source_video_sha256"]:
            raise ValueError("REAL_SOURCE_VIDEO_SHA_MISMATCH")
        model = PersonSegmenter()
        prediction_calls = [0]
        original = model.predict

        def counted_predict(image):
            prediction_calls[0] += 1
            return original(image)
        model.predict = counted_predict

        def contour_pass(segmenter):
            diagnostic = {}
            started = time.monotonic()
            segments = contour_segments(video, observed, start, end,
                deadline=started + 150, diagnostics=diagnostic, segmenter=segmenter)
            if diagnostic["status"] == "TIME_BUDGET":
                raise RuntimeError("ONNX_CONTOUR_WINDOW_TIMED_OUT")
            if diagnostic["detector_frames"] < 3:
                raise ValueError("REAL_FRAMES_NOT_PROCESSED")
            return segments, time.monotonic() - started, diagnostic

        plain, plain_s, plain_diag = contour_pass(model)
        baseline_calls = prediction_calls[0]
        cache_dir = work / "predictions"
        cache_dir.mkdir()
        cache = CachedSegmenter(model, cache_dir, digest)
        cold, cold_s, cold_diag = contour_pass(cache)
        calls_after_cold = prediction_calls[0]
        warm, warm_s, warm_diag = contour_pass(cache)
        if prediction_calls[0] != calls_after_cold:
            raise AssertionError("EXACT_CACHE_RECOMPUTED_IDENTICAL_REAL_PIXELS")
        if baseline_calls < 3 or cache.misses < 3 or cache.hits < 3:
            raise AssertionError("INSUFFICIENT_SOURCE_MODEL_CACHE_EVIDENCE")
        if not (plain == cold == warm):
            raise AssertionError("ONNX_SOURCE_CONTOUR_OUTPUT_CHANGED")
        for d in (cold_diag, warm_diag):
            if (d["decoded_frames"] != plain_diag["decoded_frames"]
                    or d["agreed_intervals"] != plain_diag["agreed_intervals"]
                    or d["status"] != plain_diag["status"]):
                raise AssertionError("ONNX_CONTOUR_DECISION_CHANGED")

        output = {"scope": "REAL_SOURCE_ONNX_CONTOUR_WINDOW_ONLY",
                  "source_video_sha256": digest,
                  "model_sha256": model.sha256,
                  "engine": "onnxruntime",
                  "packet_id": record["packet_id"],
                  "window_ms": [start, end],
                  "baseline_seconds": round(plain_s, 3),
                  "cold_cache_seconds": round(cold_s, 3),
                  "warm_cache_seconds": round(warm_s, 3),
                  "baseline_inference_calls": baseline_calls,
                  "cold_inference_calls": calls_after_cold - baseline_calls,
                  "warm_inference_calls": prediction_calls[0] - calls_after_cold,
                  "cache_hits": cache.hits, "cache_misses": cache.misses,
                  "segment_count": len(plain),
                  "decoded_frames": plain_diag["decoded_frames"],
                  "segments_identical": True,
                  "provider_model_calls": 0,
                  "full_report_verified": False,
                  "production_cache_enabled": False}
        print(json.dumps(output, sort_keys=True), flush=True)
        (ROOT / "matchroom-onnx-audit.json").write_text(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
