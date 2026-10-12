"""Offline original-video A/B for body-crop isolation; no event certification.

Each lane decodes the hash-verified video with unchanged user selections.
One local native detector supplies both lanes via a pixel-keyed memo. Only
the crop function changes; no saved identity, contacts, votes or outcomes are
input. Network calls are forbidden. Output contains aggregate evidence only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def equal_embedding(a, b):
    import numpy as np
    if a is None or b is None:
        return a is b
    return (all(a[k] == b[k] for k in a if k != "zones")
            and len(a["zones"]) == len(b["zones"])
            and all(np.array_equal(x, y) for x, y in zip(a["zones"], b["zones"])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--anchors", type=Path, required=True)
    parser.add_argument("--video-sha256", required=True)
    parser.add_argument("--anchors-sha256", required=True)
    parser.add_argument("--baseline-source", type=Path, required=True)
    parser.add_argument("--baseline-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-timelines", type=Path,
                        help="Optional local diagnostics with player geometry; keep out of Git")
    args = parser.parse_args()
    for path, expected in ((args.video, args.video_sha256),
                           (args.anchors, args.anchors_sha256),
                           (args.baseline_source, args.baseline_sha256)):
        if digest(path) != expected:
            raise SystemExit("Input checksum mismatch")
    document = json.loads(args.anchors.read_text())
    if not isinstance(document.get("anchors"), list) or not document["anchors"]:
        raise SystemExit("Existing anchor document required")
    for key in list(os.environ):
        if any(token in key.upper() for token in ("API_KEY", "EMERGENT_LLM_KEY", "OPENAI_KEY")):
            os.environ.pop(key, None)
    attempts = {"network": 0}

    def no_network(*_a, **_k):
        attempts["network"] += 1
        raise RuntimeError("OFFLINE_CROP_AUDIT_NETWORK_FORBIDDEN")

    socket.socket.connect = socket.socket.connect_ex = no_network
    socket.create_connection = no_network
    import cv2
    import numpy as np
    import cv_detect
    import cv_shadow
    import player_identity_timeline as timeline

    cv2.setNumThreads(2)
    baseline_spec = importlib.util.spec_from_file_location("crop_baseline", args.baseline_source)
    baseline = importlib.util.module_from_spec(baseline_spec)
    baseline_spec.loader.exec_module(baseline)
    candidate_crop = cv_shadow._comp_mask_crop
    original_zone = cv_shadow._zone_embedding
    original_assemble = timeline.assemble_timeline
    native = cv_detect.PersonDetector(enabled=True)
    if not native.ok:
        raise SystemExit("Local native detector unavailable; refusing a substitute")
    detector_hash = digest(cv_detect.MODEL_PATH)
    memo = {}
    forwards = 0

    class SharedDetector:
        ok = True

        def detect(self, frame):
            nonlocal forwards
            key = hashlib.sha256(frame.tobytes()).hexdigest()
            if key not in memo:
                memo[key] = tuple(native.detect(frame))
                forwards += 1
            return list(memo[key])

    cv_detect.PersonDetector = lambda **_k: SharedDetector()
    lanes = {}
    started = time.monotonic()
    for name, crop_fn in (("before", baseline._comp_mask_crop), ("after", candidate_crop)):
        cv_shadow._comp_mask_crop = crop_fn
        cv2.setRNGSeed(0)
        metrics = {"embedding_calls": 0, "valid_embeddings": 0,
                   "supported_pixels_outside_body": 0, "crops_with_outside_support": 0,
                   "outside_perturbations": 0, "outside_perturbation_mismatches": 0}
        observation_digest = hashlib.sha256()
        inputs = {}

        def inspect_embedding(image, box, pitch_l, **kwargs):
            result = original_zone(image, box, pitch_l, **kwargs)
            metrics["embedding_calls"] += 1
            metrics["valid_embeddings"] += int(result is not None)
            crop, mask, _merged, (gx, gy) = crop_fn(image, box)
            ys, xs = np.nonzero(mask)
            x, y, w, h = box
            outside = int(((xs + gx < x) | (xs + gx >= x + w)
                           | (ys + gy < y) | (ys + gy >= y + h)).sum())
            metrics["supported_pixels_outside_body"] += outside
            metrics["crops_with_outside_support"] += int(outside > 0)
            if name == "after":
                ih, iw = image.shape[:2]
                x0, y0 = min(iw, max(0, x)), min(ih, max(0, y))
                x1, y1 = max(x0, min(iw, x + w)), max(y0, min(ih, y + h))
                for colour in ((240, 240, 240), (255, 0, 0)):
                    modified = np.full_like(image, colour)
                    modified[y0:y1, x0:x1] = image[y0:y1, x0:x1]
                    other = original_zone(modified, box, pitch_l, **kwargs)
                    metrics["outside_perturbations"] += 1
                    if not equal_embedding(result, other):
                        metrics["outside_perturbation_mismatches"] += 1
            return result

        def assemble(observations, taps, *a, **kw):
            # Prove the lanes use the same detected bodies, actual PTS and
            # camera inputs; appearance vectors are the intentional difference.
            for row in observations:
                comparable = {k: v for k, v in row.items() if k != "detections"}
                comparable["detections"] = [{k: v for k, v in d.items() if k != "emb"}
                                             for d in row["detections"]]
                observation_digest.update(json.dumps(comparable, sort_keys=True).encode())
            inputs["actual_pts_frames"] = sum(not r["used_fallback"] for r in observations)
            inputs["fallback_frames"] = sum(r["used_fallback"] for r in observations)
            inputs["detected_bodies"] = sum(len(r["detections"]) for r in observations)
            return original_assemble(observations, taps, *a, **kw)

        cv_shadow._zone_embedding = inspect_embedding
        timeline.assemble_timeline = assemble
        lane_start = time.monotonic()
        result = timeline.build_identity_timeline(str(args.video), document)
        if result.get("status") != "ok":
            raise SystemExit("Identity lane failed: " + str(result.get("reason")))
        if args.private_timelines is not None:
            args.private_timelines.mkdir(parents=True, exist_ok=True)
            (args.private_timelines / (name + ".json")).write_text(json.dumps(result) + "\n")
        lanes[name] = {**metrics, **inputs, "input_sha256": observation_digest.hexdigest(),
                       "elapsed_s": round(time.monotonic() - lane_start, 3),
                       "samples": result["samples"], "tap_references": result["tap_references"],
                       "negative_gallery": result["negative_gallery"], "counts": result["counts"],
                       "measured_target_points": sum(not p.get("predicted") for p in result["target_points"]),
                       "proof_eligible_target_points": sum(bool(p.get("proof_eligible")) for p in result["target_points"]),
                       "scenes": [{"scene_id": s["scene_id"], "start_ms": s["start_ms"],
                                   "end_ms": s["end_ms"], "reid_state": s["reid_state"]}
                                  for s in result["scenes"]],
                       "identity_counts_by_scene": dict(Counter(p["scene_id"] for p in result["target_points"]
                                                                if p.get("proof_eligible")))}
        print(json.dumps({"lane": name, "result": lanes[name]}, sort_keys=True), flush=True)
    after = lanes["after"]
    passed = (not attempts["network"] and after["supported_pixels_outside_body"] == 0
              and after["outside_perturbations"] > 0 and after["outside_perturbation_mismatches"] == 0
              and lanes["before"]["input_sha256"] == after["input_sha256"]
              and not after["fallback_frames"] and not lanes["before"]["fallback_frames"])
    receipt = {"kind": "R6_ORIGINAL_BODY_CROP_AB", "crop_isolation_pass": passed,
               "video_sha256": args.video_sha256, "anchors_sha256": args.anchors_sha256,
               "original_anchor_count": len(document["anchors"]),
               "baseline_source_sha256": args.baseline_sha256,
               "candidate_source_sha256": digest(cv_shadow.__file__),
               "local_detector_sha256": detector_hash, "native_detector_forwards": forwards,
               "pixel_keyed_detector_entries": len(memo), "lanes": lanes,
               "elapsed_s": round(time.monotonic() - started, 3), "forbidden_attempts": attempts,
               "audit_source_sha256": digest(__file__), "python_version": sys.version.split()[0],
               "opencv_version": cv2.__version__, "numpy_version": np.__version__,
               "paid_model_calls": 0, "saved_identity_votes_contacts_or_outcomes_supplied": False,
               "strict_five_event_assessment_performed": False,
               "pitch_l_held_fixed_during_outside_perturbations": True,
               "merge_or_deployment": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"crop_isolation_pass": passed, "elapsed_s": receipt["elapsed_s"]}), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
