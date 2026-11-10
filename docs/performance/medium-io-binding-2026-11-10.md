# Medium ONNX output-buffer probe

Four alternating pairs over three source-derived crops at 8.5, 9.0 and 9.5 seconds compared session.run with CPU IO binding and reusable output buffers. Same medium graph, runtime 1.31.1, one CPU affinity, OPENBLAS_NUM_THREADS=1, two OpenCV threads. All raw arrays matched exactly. Median per three frames: 3.081071s versus 3.050732s (~0.98% lower). One pair was slower. This small probe does not demonstrate a material or robust speedup; production code is unchanged. No whole-contour or total-analysis equivalence is claimed.

Source was canonical_web-dd5a84b1-3dc9-40b0-80c4-89232903774f.web.mp4, previously verified SHA fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2. Crops are probe inputs, not reconstructed production requests. Reproduce using OPENBLAS_NUM_THREADS=1 python backend/scripts/benchmark_medium_io_binding.py VIDEO OUTPUT_JSON. No provider calls or deployment.
