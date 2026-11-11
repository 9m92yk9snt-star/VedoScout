# Bound OpenBLAS threads in owned graphics workers

The isolated Match Room child already uses one ONNX intra-op thread and two OpenCV threads. NumPy's OpenBLAS pool was not bounded before import. In the local environment it initialized nine BLAS threads even when the worker was restricted to one available CPU. Earlier single-thread benchmark commands therefore did not measure that inherited production-launch behavior.

The worker launch now sets `OPENBLAS_NUM_THREADS=1` in the child environment before any NumPy imports. The parent environment is unchanged. No model, provider, input, precision, sample rate, confidence threshold, identity gate, timeout or checkpoint behavior changes. No runtime dependency is added; threadpoolctl is used only by offline measurement scripts. Environments already using one OpenBLAS thread should not expect a new benefit from this setting. The actual live environment's thread count has not been measured.

## Exact-source comparison

`benchmark_worker_threads.py` runs the same current code with inherited nine-thread BLAS versus one-thread BLAS, on the original report's 00:31 window (30,765–32,132 ms). Both variants use ONNX Runtime, one CPU affinity, two OpenCV threads, a warmed model and the identical source observations.

Three alternating paired rounds produced medians 15.947803 s versus 15.582921 s, a 2.29% reduction for the complete small-model contour window. Each run decoded 83 frames, reached all 16 endpoint pairs and returned the same nine segments and diagnostics. All output hashes matched. This is a narrow local CPU result, not an end-to-end live-analysis claim; it does not measure medium-refinement latency.

Medium-model verification compared nine versus one BLAS thread on five real source frames in full and detail views: ten views, 61 masks, zero changed mask pixels or metadata. A fresh Python child confirmed that the environment setting initializes the actual local OpenBLAS pool with one thread. The 89 focused tracking, reacquisition, contour and ball-playback tests passed, including all four worker modes and preservation of the parent environment.

Artifacts:
- `testdata/performance/worker-threads-2026-11-08.json`
- `testdata/performance/medium-thread-parity-2026-11-08.json`
- `backend/scripts/benchmark_worker_threads.py`
- `backend/scripts/verify_segmentation_thread_parity.py`

Example commands (leave OPENBLAS_NUM_THREADS unset when comparing the inherited baseline):

```bash
PYTHONPATH=backend python backend/scripts/benchmark_worker_threads.py --engine onnxruntime --report /path/report.json --video /path/source.mp4 --output /path/result.json
PYTHONPATH=backend python backend/scripts/verify_segmentation_thread_parity.py /path/source.mp4 /path/medium-parity.json
```

An independent read-only check of the retained 00:08 medium-refinement windows found 167 decoder inputs and zero identical input hashes: the two windows have different detector ROIs. Exact prediction caching was therefore not activated or retried as an optimization.

No synchronization, deployment or publication was performed.
