"""Compare unchanged native evidence on two overlapping original-video windows.

No event labels, semantic readers, database or deployed report are used.
This bounded benchmark is not a full-video accuracy or latency measurement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=2, choices=range(1, 5))
    args = parser.parse_args()
    backend = Path(__file__).resolve().parents[1]
    if (backend / ".env").exists():
        parser.error("Run in an isolated checkout without backend/.env")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Use a new empty output directory")
    for name in list(os.environ):
        if any(token in name.upper() for token in ("API_KEY", "EMERGENT_LLM_KEY", "OPENAI_KEY")):
            os.environ.pop(name, None)
    counters = {"network": 0, "detector_forward": 0}
    def blocked(*_a, **_k):
        counters["network"] += 1
        raise RuntimeError("NATIVE_BENCHMARK_NETWORK_FORBIDDEN")
    socket.socket.connect = socket.socket.connect_ex = socket.create_connection = blocked
    sys.path.insert(0, str(backend))
    import cv2
    import cv_detect
    import dense_replay
    import dense_track_refinement as dense
    import dense_identity_continuity
    import physical_match_reconstruction as physical
    import fix10b_runtime

    cv2.setNumThreads(args.threads)
    args.output.mkdir(parents=True, exist_ok=True)
    sources = {p.name: digest(p) for p in backend.glob("*.py")}
    original_init = cv_detect.PersonDetector.__init__
    def counted_init(instance, *a, **k):
        original_init(instance, *a, **k)
        if instance.net is None:
            raise RuntimeError("Native detector unavailable")
        net = instance.net
        class Net:
            def __getattr__(self, name):
                return getattr(net, name)
            def forward(self, *a, **k):
                counters["detector_forward"] += 1
                return net.forward(*a, **k)
        instance.net = Net()
    cv_detect.PersonDetector.__init__ = counted_init
    prepared = json.loads(args.prepared.read_text())
    graph, authority = prepared["scene_graph"], prepared["identity_authority"]
    windows = [(0, 600), (300, 900)]
    scene = next(s["scene_id"] for s in graph["scenes"] if s["start_ms"] <= 0 and s["end_ms"] >= 900)
    receipts, outputs = [], []
    for enabled in (False, True):
        cv2.setRNGSeed(0)
        session = dense.NativeDetectionSession() if enabled else None
        forward_start = counters["detector_forward"]
        started = time.monotonic()
        traces = {}
        for index, (start, end) in enumerate(windows):
            result = dense.refine_window(dense_replay.iter_dense_frames(str(args.video), start, end),
                                         graph, authority, scene, native_session=session)
            if result.get("status") != "ok":
                raise RuntimeError("Native refinement did not complete")
            frames = dense_identity_continuity.apply(result["frames"])["frames"]
            if any(f.get("used_fallback") or f.get("time_authority") != "ACTUAL_MEDIA_PTS" for f in frames):
                raise RuntimeError("Actual native media PTS required")
            traces[str(index)] = {"window": {"scene_id": scene, "start_ms": start, "end_ms": end,
                                           "dense_window_id": str(index)}, "decoded_frames": frames,
                                  "source_video": {"sha256": digest(args.video)}}
        physical_result = physical.reconstruct_physical_match(str(args.video), {}, {"sequences": []},
                            graph, authority, _feedback_context={"traces": traces, "jobs": []})
        if physical_result.get("status") != "ok" or any(w.get("status") != "ok" for w in physical_result["windows"]):
            raise RuntimeError("Physical reconstruction did not complete")
        canonical = fix10b_runtime.reconcile_unified_result(prepared, physical_result)["canonical_events"]
        evidence = {"traces": physical_result["traces"], "canonical": canonical}
        serialized = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
        outputs.append(serialized)
        row = {"cache_enabled": enabled, "elapsed_s": round(time.monotonic() - started, 3),
               "detector_forwards": counters["detector_forward"] - forward_start,
               "evidence_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
               "frames": sum(len(t["decoded_frames"]) for t in traces.values()),
               "cache": session.metrics() if session else None}
        receipts.append(row)
        print(json.dumps(row), flush=True)
    source_unchanged = sources == {p.name: digest(p) for p in backend.glob("*.py")}
    receipt = {"scope": "BOUNDED_NATIVE_OVERLAP_BENCHMARK_NOT_FULL_ANALYSIS", "windows_ms": windows,
               "source_video_sha256": digest(args.video), "prepared_sha256": digest(args.prepared),
               "script_sha256": digest(__file__), "backend_source_sha256": sources,
               "threads": args.threads, "runs": receipts, "evidence_equal": outputs[0] == outputs[1],
               "source_unchanged": source_unchanged, "network_attempts": counters["network"],
               "expected_reference_labels_used_as_input": False}
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if not receipt["evidence_equal"] or not source_unchanged or counters["network"]:
        raise RuntimeError("Native reuse changed evidence or violated isolation")


if __name__ == "__main__":
    main()
