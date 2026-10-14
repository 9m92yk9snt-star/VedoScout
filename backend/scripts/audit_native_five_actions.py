"""Repeatable local benchmark on original pixels and existing user markings.

Reference cases select bounded exported windows and evaluate the final result;
their labels never enter reconstruction. This is not a full-video recall audit.
The optional cache contains only native detector proposals keyed by pixel hash.
Old contacts, jersey votes, outcomes and canonical events are never supplied.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import inspect
import json
import os
from pathlib import Path
import socket
import sys
import time
import zipfile


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--anchors", required=True, type=Path)
    parser.add_argument("--identity-timeline", required=True, type=Path)
    parser.add_argument("--evidence-export", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    if args.cache_only and (args.cache is None or not args.cache.is_file()):
        parser.error("--cache-only requires an existing --cache")
    if not 1 <= args.threads <= 8:
        parser.error("--threads must be between 1 and 8")
    backend = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend))
    if (backend / ".env").exists():
        parser.error("Run the audit from a checkout without backend/.env")
    for name in list(os.environ):
        if any(token in name.upper() for token in ("API_KEY", "EMERGENT_LLM_KEY", "OPENAI_KEY")):
            os.environ.pop(name, None)
    attempts = {"network": 0, "sdk": 0}

    def block(kind):
        def forbidden(*_a, **_k):
            attempts[kind] += 1
            raise RuntimeError("NATIVE_ACTION_AUDIT_FORBIDDEN_" + kind)
        return forbidden

    socket.socket.connect = socket.socket.connect_ex = socket.create_connection = block("network")
    import cv2
    import cv_detect
    import dense_replay
    import dense_track_refinement as dense
    import fix10a_vision_providers as vision
    import fix10b_runtime
    import identity_verify
    import physical_match_reconstruction as physical_engine
    import unified_identity_authority as identity
    import reference_action_review as review

    vision.LlmChat = identity_verify.LlmChat = block("sdk")
    cv2.setNumThreads(args.threads)
    cv2.setRNGSeed(0)
    args.output.mkdir(parents=True, exist_ok=True)
    model = backend / "models/yolov8n.onnx"
    if not model.is_file():
        parser.error("The local ONNX detector is missing; the audit will not download it")
    source_hashes = {p.name: sha(p) for p in backend.glob("*.py")}
    metadata = {"version": 1, "video_sha256": sha(args.video), "detector_sha256": sha(model),
                "detector_source_sha256": hashlib.sha256(inspect.getsource(
                    dense._detect_dense_people_and_ball).encode()).hexdigest()}
    cache = {**metadata, "entries": {}}
    if args.cache and args.cache.is_file():
        cache = json.loads(args.cache.read_text())
        if any(cache.get(k) != v for k, v in metadata.items()) or not isinstance(cache.get("entries"), dict):
            raise ValueError("NATIVE_DETECTOR_CACHE_SOURCE_MISMATCH")
    inputs = json.loads(args.anchors.read_text())
    anchors = inputs.get("anchors") or inputs.get("player_anchors") or []
    timeline = json.loads(args.identity_timeline.read_text())
    authority = identity.build_unified_identity_authority(
        identity_timeline=timeline, anchors=anchors,
        anchor_time_offset=float(inputs.get("anchor_time_offset") or 0))
    cases = json.loads(args.cases.read_text())
    with zipfile.ZipFile(args.evidence_export) as archive:
        windows = [json.loads(archive.read(n))["window"] for n in archive.namelist()
                   if n.startswith("traces/") and n.endswith(".json")]
    selected = {}
    for case in cases:
        ms = case["reference_ms"]
        window = deepcopy(max((w for w in windows if w["start_ms"] <= ms <= w["end_ms"]),
                              key=lambda w: w["end_ms"] - ms))
        scene = next(s for s in authority["scenes"] if s["start_ms"] <= ms <= s["end_ms"])
        window.update(scene_id=scene["scene_id"], start_ms=max(window["start_ms"], scene["start_ms"]),
                      end_ms=min(window["end_ms"], scene["end_ms"]))
        selected[window["dense_window_id"]] = window
    counters = {"decoded_frames": 0, "cache_hits": 0, "native_forwards": 0}
    detector = None

    def detect(image):
        nonlocal detector
        pixel_key = hashlib.sha256(str(image.shape).encode() + image.tobytes()).hexdigest()
        counters["decoded_frames"] += 1
        if pixel_key in cache["entries"]:
            counters["cache_hits"] += 1
            return deepcopy(cache["entries"][pixel_key])
        if args.cache_only:
            raise ValueError("NATIVE_DETECTOR_CACHE_PIXEL_MISSING")
        if detector is None:
            detector = cv_detect.PersonDetector(enabled=True)
            if not detector.ok:
                raise ValueError("NATIVE_DETECTOR_UNAVAILABLE")
            net = detector.net

            class CountedNet:
                def setInput(self, *a, **k):
                    return net.setInput(*a, **k)

                def forward(self, *a, **k):
                    counters["native_forwards"] += 1
                    return net.forward(*a, **k)

            detector.net = CountedNet()
        result = dense._detect_dense_people_and_ball(detector, image, include_a7_support=True)
        cache["entries"][pixel_key] = deepcopy(result)
        return result

    started = time.monotonic()
    traces, stats = [], []
    for window in selected.values():
        refined = dense.refine_window(dense_replay.iter_dense_frames(
            str(args.video), window["start_ms"], window["end_ms"]), {}, authority,
            window["scene_id"], detector_fn=detect)
        if refined.get("status") != "ok":
            raise ValueError("NATIVE_REFINEMENT_NOT_OK")
        frames = refined["frames"]
        if not frames or any(f.get("used_fallback") or f.get("time_authority") != "ACTUAL_MEDIA_PTS" for f in frames):
            raise ValueError("NATIVE_ACTUAL_PTS_REQUIRED")
        previous = {"window": window, "decoded_frames": frames,
                    "source_video": {"sha256": metadata["video_sha256"]},
                    "contacts": {"accepted": []}, "jersey_consensus": {}}
        result = physical_engine.reconstruct_physical_match(
            str(args.video), {}, {"sequences": []}, {}, authority,
            _feedback_context={"traces": {window["dense_window_id"]: previous}, "jobs": []})
        if result.get("status") != "ok" or any(w.get("status") != "ok" for w in result.get("windows") or []):
            raise ValueError("NATIVE_PHYSICAL_RECONSTRUCTION_NOT_OK")
        trace = result["traces"][0]
        traces.append(trace)
        (args.output / (trace["trace_id"] + "-physical.json")).write_text(json.dumps(result))
        stat = {"trace_id": trace["trace_id"], "frames": len(frames),
                "contacts": len(trace["contacts"]["accepted"]), "strikes": len(trace["strike_evidence"]),
                "outcomes": dict(Counter(o["physical_outcome"] for o in trace["outcome_evidence"]))}
        stats.append(stat)
        print(json.dumps({"stage": "window", **stat}), flush=True)
    physical = {"status": "ok", "traces": traces, "windows": [],
                "recall_coverage": {"complete": False, "status": "PARTIAL"}}
    canonical = fix10b_runtime.reconcile_unified_result(
        {"identity_authority": authority, "scene_graph": {}, "sequence_analysis": {"sequences": []},
         "canonical_events": {"events": [], "counts": {}}}, physical)["canonical_events"]
    assessment = review.assess(cases, canonical, physical, review.build_plan(traces, cases))
    if source_hashes != {p.name: sha(p) for p in backend.glob("*.py")}:
        raise ValueError("AUDITED_SOURCE_CHANGED_DURING_RUN")
    receipt = {"kind": "LOCAL_NATIVE_FIVE_ACTION_BOUNDED_AUDIT", **metadata, **counters,
               "anchors_sha256": sha(args.anchors), "identity_timeline_sha256": sha(args.identity_timeline),
               "cases_sha256": sha(args.cases), "source_hashes": source_hashes,
               "stats": stats, "canonical_counts": canonical["counts"],
               "forbidden_attempts": attempts, "new_paid_model_calls": 0,
               "old_contacts_votes_or_outcomes_supplied": False, "full_recall_audit": False,
               "elapsed_s": round(time.monotonic() - started, 3)}
    for name, value in (("receipt.json", receipt), ("assessment.json", assessment), ("canonical.json", canonical)):
        (args.output / name).write_text(json.dumps(value, indent=2))
    if args.cache and not args.cache_only:
        args.cache.parent.mkdir(parents=True, exist_ok=True)
        args.cache.write_text(json.dumps(cache))
    print(json.dumps({"stage": "finished", "verified": assessment["verified"], "requested": assessment["requested"],
                      **counters, "forbidden_attempts": attempts}), flush=True)
    return 90 if any(attempts.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
