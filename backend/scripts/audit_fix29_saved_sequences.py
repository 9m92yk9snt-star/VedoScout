"""Replay saved native observations and compare exact decoder pixels locally.

No external readers, expected event labels, database, new upload or new taps.
Use --backend for a separate unmodified baseline source tree.
"""
import argparse
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--backend", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--decode-check", action="store_true")
    parser.add_argument("--decode-only", action="store_true")
    args = parser.parse_args()
    backend = args.backend.resolve()
    if (backend/".env").exists():
        raise RuntimeError("ENVIRONMENT_FILE_NOT_ALLOWED")
    sys.path.insert(0, str(backend))
    counters = {"network": 0, "sdk": 0, "video_opens": 0, "detector_forwards": 0}
    def forbidden(kind):
        def block(*_a, **_k):
            counters[kind] += 1
            raise RuntimeError("OFFLINE_AUDIT_FORBIDDEN_"+kind)
        return block
    socket.socket.connect = forbidden("network")
    socket.socket.connect_ex = forbidden("network")
    socket.create_connection = forbidden("network")
    import cv2
    import numpy as np
    cv2.setNumThreads(2)
    actual_capture = cv2.VideoCapture
    def capture(*a, **k):
        counters["video_opens"] += 1
        return actual_capture(*a, **k)
    cv2.VideoCapture = capture
    actual_net = cv2.dnn.readNetFromONNX
    class Net:
        def __init__(self, net): self.net = net
        def __getattr__(self, key): return getattr(self.net, key)
        def forward(self, *a, **k):
            counters["detector_forwards"] += 1
            return self.net.forward(*a, **k)
    cv2.dnn.readNetFromONNX = lambda *a, **k: Net(actual_net(*a, **k))
    import action_evidence_review as inspection
    import fix10a_vision_providers as vision
    import fix10a_goal_direction as direction
    import physical_match_reconstruction as physical
    import fix10b_reconciliation as reconciliation
    import evidence_feedback
    import video_timebase
    vision.LlmChat = direction.LlmChat = forbidden("sdk")
    sources = {p.name: digest(p) for p in backend.glob("*.py")}
    started = time.perf_counter()
    saved_path = args.run/"physical.json"
    saved = json.loads(saved_path.read_text())
    prepared = json.loads((args.run/"unified_without_semantic_reader.json").read_text())
    video = args.run/"source.mp4"
    assert digest(video) == saved["source_video"]["sha256"]
    windows = [t["window"] for t in saved["traces"]]
    plan = inspection.build_plan(windows, prepared.get("sequence_analysis") or {})
    receipt = {"scope": "SAVED_NATIVE_OBSERVATIONS_NO_EXTERNAL_READERS", "source_sha256": sources,
        "source_video_sha256": digest(video), "input_physical_sha256": digest(saved_path),
        "reference_labels_used_as_input": False, "new_uploads": 0, "new_taps": 0, "database_writes": 0,
        "limits": ["Saved native detections and identity observations are reused", "No external image or jersey reader was run",
                   "No full production analysis, push or deployment", "Timing is local and sensitive to load"]}
    if args.decode_check:
        raw = subprocess.check_output(["git", "show", "3a6b50f:backend/fix10a_vision_providers.py"],
                                      cwd=backend.parent, text=True)
        node = next(n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == "_read_frames")
        namespace = {"cv2": cv2, "video_timebase": video_timebase, "_num": vision._num}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "FIX22_read_frames", "exec"), namespace)
        legacy = namespace["_read_frames"]
        by_id = {t["trace_id"]: t for t in saved["traces"]}
        groups = [inspection.frame_times(j, by_id[j["dense_window_id"]]["decoded_frames"])
                  for j in plan["jobs"] if j["selected"]]
        base_s = new_s = 0.; images = 0
        for times in groups:
            clock = time.perf_counter(); old = legacy(str(video), times); base_s += time.perf_counter()-clock
            clock = time.perf_counter(); new = vision._read_frames(str(video), times); new_s += time.perf_counter()-clock
            assert set(new) == set(old)
            for ms in old:
                assert old[ms][0] == new[ms][0] and np.array_equal(old[ms][1], new[ms][1])
            images += len(new)
        receipt["decoder"] = {"jobs": len(groups), "requested_images": images, "actual_pts_and_pixels_identical": True,
            "baseline_seconds": round(base_s, 3), "batched_seconds": round(new_s, 3)}
        print(json.dumps({"stage": "decoder_complete", **receipt["decoder"]}), flush=True)
    if not args.decode_only:
        phase = time.perf_counter()
        def progress(trace):
            print(json.dumps({"stage": "physical", "trace_id": trace.get("trace_id"),
                              "seconds": round(time.perf_counter()-phase, 1)}), flush=True)
        replay = physical.reconstruct_physical_match(str(video), prepared["sequence_plan"],
            prepared.get("sequence_analysis") or {}, prepared["scene_graph"], prepared["identity_authority"],
            source_video=saved["source_video"], trace_callback=progress,
            _feedback_context={"traces": {t["trace_id"]: t for t in saved["traces"]}, "jobs": plan["jobs"], "support_traces": []})
        physical_s = time.perf_counter()-phase
        canonical = reconciliation.reconcile_canonical_events(deepcopy(prepared["canonical_events"]), replay)
        followup = evidence_feedback.build_plan(replay["traces"])
        args.output.mkdir(parents=True, exist_ok=True)
        for name, data in (("physical.json", replay), ("canonical.json", canonical), ("feedback.json", followup)):
            (args.output/name).write_text(json.dumps(data, separators=(",", ":")))
        receipt["physical_seconds"] = round(physical_s, 3)
        receipt["physical_metrics"] = replay["metrics"]
        receipt["canonical_counts"] = canonical.get("counts") or {}
        receipt["feedback_centers_ms"] = [j["center_ms"] for j in followup["jobs"] if j["selected"]]
        receipt["proof_identity_frames"] = sum((f.get("global_target") or {}).get("proof_eligible") is True
            for t in replay["traces"] for f in t.get("decoded_frames") or [])
        receipt["physical_sha256"] = digest(args.output/"physical.json")
    args.output.mkdir(parents=True, exist_ok=True)
    receipt.update(source_unchanged=sources == {p.name: digest(p) for p in backend.glob("*.py")},
                   counters=counters, elapsed_seconds=round(time.perf_counter()-started, 3))
    assert receipt["source_unchanged"] and counters["network"] == counters["sdk"] == 0
    (args.output/"receipt.json").write_text(json.dumps(receipt, indent=2)+"\n")
    print(json.dumps({k: v for k, v in receipt.items() if k != "source_sha256"}), flush=True)


if __name__ == "__main__":
    main()
