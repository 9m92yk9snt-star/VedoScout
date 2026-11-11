# Exact prediction reuse through final contour output

The optional report-scoped prediction cache previously wrapped only small-model passes. `compute_refinement` now applies that same opt-in wrapper to either small or medium models. `bounded_tracks(..., reuse_predictions=False)` remains the default. No source sampling, graph, engine selection, thresholds, deadlines, or identity decisions change.

New integration coverage checks that separate medium refinement invocations reuse exact pixels, source and model only. Changed pixels, source or model recompute. Returned masks are independent of the persisted copy. Default refinement remains uncached. All 43 prediction-cache and tracking tests passed, including the real ONNX raw-prediction parity test.

## Full contour replay

`backend/scripts/verify_contour_cache_output.py` verifies the exported video's SHA against its report and replays the real 8.750–10.000s source window using the pinned medium model. Each engine is compared against itself: plain, cold cache, then a new cache wrapper reading the populated directory. Every run reaches all endpoint pairs and emits eight segments from 76 detector frames. Complete segment structures, confidence values, foreground polygons, and diagnostic decisions are compared exactly; only measured detector time is excluded. The script fails on any difference or incomplete traversal. Output hashes and timings are retained under `testdata/performance/contour-cache-*-2026-11-09.json`.

One CPU affinity, OpenCV 4.14.0, two OpenCV threads and OPENBLAS_NUM_THREADS=1. The ONNX run uses the pinned runtime 1.31.1. Models are loaded before timing. No provider calls are involved.

The cold run includes cache writes; the warm run includes cache reads and the entire downstream contour pipeline. A warm replay assumes 100% exact input overlap and is therefore an upper bound, not the production hit rate or total-analysis savings. These are single runs, not repeated timing benchmarks. Different engines are not asserted equivalent to each other.

This extends and verifies an opt-in path. Activation in the normal scheduler still needs a realistic mixed-window replay including cache misses, changes of ROI/model, worker restarts and deadline behavior. No synchronization, deployment or default cache activation.

| Engine | Plain | Cold cache | Warm cache | Exact output |
| --- | ---: | ---: | ---: | --- |
| OpenCV | 103.447s | 100.317s | 5.471s | Identical across all three runs |
| ONNX 1.31.1 | 89.985s | 88.326s | 5.726s | Identical across all three runs |

Plain and cold each perform 76 model calls; warm performs zero, with 76 cache hits. Small cold-versus-plain differences should be treated as timing variation, not a demonstrated cache-miss speedup.
