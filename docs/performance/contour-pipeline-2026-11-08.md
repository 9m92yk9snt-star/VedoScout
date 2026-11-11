# Combined contour replay

This probe compares the accumulated exact-pixel optimizations against the decoder from main commit `3f13f63f7c13e51cf159a82ccf7793d116f70362`, the original overlap calculation, and scalar feature votes. It runs the complete `contour_segments` function, including source decoding, inference, association and display geometry. It does not rerun paid event analysis or publish a report.

The source is the original exported video (SHA-256 `fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2`). The selected event is the report's 00:31 card, with its retained observations and 30,765–32,132 ms source window. The benchmark checks every segment and all diagnostic counters for exact equality, excluding only elapsed detector time. All source endpoint pairs must be reached; incomplete timing-budget runs fail the benchmark.

The benchmark supports OpenCV (default) and ONNX Runtime (--engine onnxruntime), one available CPU via affinity, two OpenCV threads (as in the workers), the existing small segmentation model, three alternating paired rounds and a shared warmed model. Model initialization is excluded. Its results cannot be projected directly onto production ONNX, medium-model refinement, or total analysis latency.

The initial ONNX comparison was blocked by automatic approval review because of an attempted external Microsoft telemetry connection with unknown payload. After the user explicitly requested the ONNX run following that disclosure, the ordinary execution completed. No sandbox or telemetry-control bypass was introduced. Both engine results are recorded separately.

To reproduce, export `backend/native_player_segmentation.py` from the baseline commit into a separate file and supply it with `--baseline-segmenter`:

```bash
PYTHONPATH=backend OPENBLAS_NUM_THREADS=1 python backend/scripts/benchmark_contour_pipeline.py \
  --report /path/to/exported/report.json \
  --video /path/to/exact/source.mp4 \
  --baseline-segmenter /path/to/baseline/native_player_segmentation.py \
  --output /path/to/result.json
```

The output records the source/model/baseline checksums, per-round times, output checksum and diagnostic counts. See `testdata/performance/contour-pipeline-opencv-2026-11-08.json` for measurements.

## Results

Three paired rounds produced median 22.8241 seconds for the baseline and 22.4547 seconds for the candidate (1.62% lower). Individual rounds overlap: this is a small observed local difference, not a statistically established production speedup. Every run decoded 83 frames, reached all 16 endpoint pairs, and returned the same nine segments and diagnostic counters. Zero output differences were observed.

A separate profiled OpenCV run spent 17.135 of 22.538 seconds in the segmentation forward call (about 76%). That supports prioritizing the model-execution cost for larger gains; it does not establish the corresponding ONNX or medium-model breakdown. The profile metadata is saved separately in `testdata/performance/contour-profile-opencv-2026-11-08.json`.

All six Production verification jobs and the Sequence full-report integration workflow passed for production-code commit `24efdeba7d5e2697cfddd9c91f2d0b029310d63d`. This follow-up adds only the offline benchmark and its evidence; it does not alter production inference, quality gates or deployment.

## Authorized ONNX replay

The same exact source window was replayed with `--engine onnxruntime` in three alternating paired rounds. Median baseline: 15.740725 s; median candidate: 15.744659 s (0.003934 s higher, about 0.025%). The candidate range was 15.402178–15.857496 s and overlaps the baseline range. **No overall ONNX contour speed improvement is demonstrated by this probe.** The isolated helper benchmarks must not be described as an equivalent overall production gain.

All six runs produced exactly the same output within the ONNX comparison: 83 decoded/detected frames, all 16 endpoint pairs reached, nine accepted segments and unchanged diagnostic counters. The ONNX output checksum differs from the separately recorded OpenCV checksum, so these runs do not establish cross-engine pixel equivalence. No engine substitution is proposed.

Results: `testdata/performance/contour-pipeline-onnx-2026-11-08.json`. This remains a local small-model graphics-window probe, not a complete live analysis or deployment. Production code is unchanged by this follow-up.
