"""Verify prediction cache equality with the real ONNX engine on one exact source.

The previously saved 00:08 localization belongs to a DIFFERENT source SHA
and must not be replayed on this repository's bundled Orman400 source video.
This probe intentionally compares only real source pixels and local raw model
predictions. No receipt, player identity, contour, score, or report is inferred.
No paid model calls, production changes, or permission to enable the cache.
"""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import cv2
from match_room_contours import read_clip
from match_room_prediction_cache import CachedSegmenter
from native_player_segmentation import PersonSegmenter
from scripts.run_matchroom_single_tap_trial import prepare

PINNED_VIDEO_SHA256 = "b9e2ba4975ed9dc2497f860a80644711bfd12a2125d9fba6390600b0409ab999"
FOREIGN_LOCALIZATION_VIDEO_SHA256 = "fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2"


def signatures(rows):
    """Compare every box, score, class and all mask pixels, not a chosen output."""
    return [{"box": list(row["box"]),
             "score": float(row["score"]),
             "class_id": int(row["class_id"]),
             "mask_shape": list(row["mask"].shape),
             "mask_dtype": str(row["mask"].dtype),
             "mask_sha256": hashlib.sha256(row["mask"].tobytes()).hexdigest()}
            for row in rows]


def main():
    os.environ["SCOUTMEPLAY_MATCHROOM_ENGINE"] = "onnxruntime"
    cv2.setNumThreads(2)
    foreign = json.loads((ROOT / "testdata/matchroom-completion/result.json").read_text())
    if foreign["record"]["source_video_sha256"] != FOREIGN_LOCALIZATION_VIDEO_SHA256:
        raise ValueError("SAVED_LOCALIZATION_SOURCE_CHANGED")
    if PINNED_VIDEO_SHA256 == FOREIGN_LOCALIZATION_VIDEO_SHA256:
        raise ValueError("SOURCES_NOT_DISTINGUISHED")

    with tempfile.TemporaryDirectory(prefix="matchroom-onnx-replay-") as temp:
        work = Path(temp)
        video, _ = prepare(ROOT / "testdata/sequence-pilot-orman400", work / "source")
        with video.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != PINNED_VIDEO_SHA256:
            raise ValueError("REAL_VIDEO_SOURCE_SHA_MISMATCH")

        frames = list(read_clip(video, 30500, 31300, sample_step=1/35))
        if not 12 <= len(frames) <= 96:
            raise ValueError("INSUFFICIENT_ACTUAL_SOURCE_FRAMES")
        images = [f["image"] for f in frames]
        model = PersonSegmenter()
        calls = [0]
        original = model.predict

        def counted(image):
            calls[0] += 1
            return original(image)

        model.predict = counted

        def evaluate(predictor):
            started = time.monotonic()
            out = [signatures(predictor.predict(image)) for image in images]
            return out, time.monotonic() - started

        baseline, plain_seconds = evaluate(model)
        plain_calls = calls[0]
        cache_dir = work / "predictions"
        cache_dir.mkdir()
        cache = CachedSegmenter(model, cache_dir, digest)
        cold, cold_seconds = evaluate(cache)
        after_cold = calls[0]
        warm, warm_seconds = evaluate(cache)
        if calls[0] != after_cold:
            raise AssertionError("UNCHANGED_SOURCE_PIXELS_RECOMPUTED")
        if plain_calls != len(images) or cache.misses < 1 or cache.hits < len(images):
            raise AssertionError("ONNX_CACHE_NOT_EXERCISED")
        if not (baseline == cold == warm):
            raise AssertionError("REAL_ONNX_PREDICTION_OR_MASK_CHANGED")
        positive_frames = sum(any(p["class_id"] == 0 for p in rows) for rows in baseline)
        if positive_frames == 0:
            raise AssertionError("REAL_SOURCE_PERSON_DETECTION_NOT_EXERCISED")

        output = {"scope": "ONE_REAL_SOURCE_ONNX_PREDICTION_PARITY_ONLY",
                  "source_video_sha256": digest,
                  "model_sha256": model.sha256,
                  "engine": "onnxruntime",
                  "onnxruntime_version": importlib.metadata.version("onnxruntime"),
                  "opencv_version": cv2.__version__,
                  "actual_frame_timestamps_ms": [f["media_ms"] for f in frames],
                  "source_frames": len(images),
                  "frames_with_person_detections": positive_frames,
                  "baseline_seconds": round(plain_seconds, 3),
                  "cold_seconds": round(cold_seconds, 3),
                  "warm_seconds": round(warm_seconds, 3),
                  "baseline_inference_calls": plain_calls,
                  "cold_inference_calls": after_cold - plain_calls,
                  "warm_inference_calls": calls[0] - after_cold,
                  "cache_hits": cache.hits, "cache_misses": cache.misses,
                  "complete_raw_predictions_identical": True,
                  "foreign_localization_receipts_reused": False,
                  "contour_and_identity_parity_verified": False,
                  "provider_model_calls": 0,
                  "full_report_verified": False,
                  "production_cache_enabled": False}
        print(json.dumps(output, sort_keys=True), flush=True)
        (ROOT / "matchroom-onnx-audit.json").write_text(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
