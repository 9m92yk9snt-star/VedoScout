# Isolated reference-streaming measurement

Compared current reference streaming against timeline-only commit `ecbb8fbd8dcf51e1899eecb9306ef625d8e34654`. Both implementations use the same timeline iterator. The baseline module was retrieved verbatim from GitHub; its SHA-256 is recorded in the result.

The original source SHA was verified against the exported report. Six alternating before/after pairs prepared the first real selected event with all ten references uncached on each invocation. The first pair was excluded as warm-up. Full serialized requests and source frame/reference metadata matched for every pair. No provider requests were sent.

Five measured pairs: median preparation 2.520497s before, 2.479206s after (0.041291s / 1.64% lower). One pair was slower after the change. This small difference does not establish a substantial or consistently faster stage; no total-analysis speedup is inferred. References are cached across subsequent events, so this is a once-per-localization cost. All ten reference timestamps are separated by more than one second: source ordering does not remove the iterator's required seeks for this workload. This is not a heavy bottleneck worth further micro-optimization here.

OpenCV 4.14.0; local shared runtime, not production hardware. Twenty localization/timebase tests passed. All three GitHub workflows succeeded for production-code commit `6510416e417038a42ec02ff3b0aa0ba229a07ffb`.

Reproduce with `PYTHONPATH=backend python backend/scripts/benchmark_reference_streaming.py VIDEO EXPORT_ZIP BASELINE_MODULE OUTPUT_JSON`, supplying the baseline module from the commit above. Results: `testdata/performance/reference-streaming-isolated-2026-11-09.json`.

No production code changes, paid model analysis, synchronization or deployment were performed in this measurement.
