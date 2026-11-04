# ONNX Runtime full report replay — 2026-11-04

Experimental only; no production runtime/dependency changes. Same pinned model weights, one CPU affinity, original ten taps, all eight clips, retained exact model receipts, normal report asset flow, unchanged per-event deadlines. Preparation batching from PR56 was enabled. No new paid requests.

Total 607.578s versus earlier 862.631s baseline (29.6% faster). Preparation/receipt validation 31.400s; tracking 539.162s; rendering including tracking 573.587s. This is retained report-graphics replay, not complete new upload/analysis latency.

Production playback gates: whole duel ellipse 175/249 (baseline 93/249); post-duel recovery 61/61; kick ellipse 76/76 (baseline 61/76); observed arrow 13/19 (baseline 8/19). Missing arrow frames: 31165, 31182, 31199, 31215, 31232, 31249 ms. Acceptance failed: ellipse absent at 9016 ms. Full continuous visual acceptance is NOT achieved. Runtime switch remains unapproved for deployment.

RAM monitor failed (psutil NoSuchProcess); no memory claim and no 4GB limit enforced. Earlier short runtime comparison showed one-pixel mask changes, so no bitwise equivalence claim. Baseline and experiment are single runs, not repeated production benchmarks.

Complete report, encoded clips, experiment adapter, logs and measurements retained as ScoutMePlay_hastighedsproeve_ONNX.zip, Library file libfile_0995463a3400819184a241cb73d683c1. PR56 remains draft. Next work: determine why remaining duel intervals and final ball-direction frames exceed or fail the supported evidence path; preserve uncertainty gates.
