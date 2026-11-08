# CPU scaling benchmark setup

The latest production-code commit `f29a1aae3b06d15e5066ac9af26fe9d2ea1d1f51` passed both Production verification and Sequence full-report integration.

`backend/scripts/benchmark_cpu_scaling.py` prepares a controlled comparison of the current ONNX graphics worker under CPU affinity limits of one, two and four logical CPUs. Each trial starts a fresh process before importing NumPy/ONNX, so thread affinity is inherited consistently. It preserves the production settings: ONNX intra/inter-op threads 1, OpenCV threads 2, OpenBLAS threads 1. Three rotated rounds compare output hashes and require every source endpoint pair to be reached.

The test host exposes nine affinity CPUs and a cgroup quota of eight CPU equivalents. Restricting affinity is not a simulation of Emergent's hardware, quotas or contention. The test measures one original small-model contour window; model startup, medium refinement, provider latency, report writing and upload are excluded.

## Execution status

The attempted execution was blocked by automatic approval review because of an attempted external Microsoft telemetry connection whose payload and disclosure scope were unknown. This occurred despite the earlier user instruction to run ONNX. No workaround or repeat attempt followed this rejection. No completed one/two/four CPU comparison is available, and no speedup or purchase recommendation can be inferred from this setup.

No production code or server configuration changed. The benchmark should only be run when the applicable telemetry authorization is resolved.
