# Exact mask decoding optimization

Full-frame thresholding generated boolean and uint8 arrays for every retained person/ball, although the decoder copies only the detection box to the returned mask. Keep full-frame interpolation unchanged, then threshold only that box into the same full-size uint8 output. A small named helper isolates this operation for parity tests. Models, class/score thresholds, NMS, selected instance order, mask dimensions, source sampling, identity gates and budgets are unchanged. No cache activation or model-call reduction.

Validation: 88 focused tests passed (21 new threshold-parity cases, existing selection/proposal tests, cache and source-contour tests). Tests include exactly 0.5, adjacent float32 values, NaN/infinities, empty/full boxes, portrait/landscape, noncontiguous arrays and mutation isolation. The new tests are included in the normal player-selection CI job.

Real-source benchmark: 12 original source times, each as a 720×1280 full view and a 720×400 field detail; 24 cases, 126 retained person/ball instances. Run the pinned small ONNX model once per case, then compare legacy and optimized decoding with those identical inference outputs and assert equal preprocessing blobs, metadata and every mask pixel. Zero differences. Source/model SHA and measurements are retained under testdata/performance.

Seven alternating timing rounds: median preprocessing+decode 0.210876s → 0.203672s, a 3.42% reduction in that measured stage. This excludes model inference from the paired timing and is NOT a 3.42% full-analysis speedup. The current production environment and full-report latency have not been benchmarked. The change is deliberately small; the much larger inference bottleneck remains a separate optimization task.

Benchmark is offline, no paid LLM calls, one CPU/BLAS thread for both variants. No deployment or synchronization. New branch starts from merged PR #59 at 3f13f63f7c13e51cf159a82ccf7793d116f70362.
