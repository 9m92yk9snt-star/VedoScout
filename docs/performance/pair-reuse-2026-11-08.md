# Preserve unaffected optical-flow pairs during adaptive recovery

Each new or upgraded detection previously cleared the entire adaptive association cache. A pair result depends on its source and destination masks, the fixed decoded grayscale frames, and the chosen source instance. It does not depend on a third frame's detections or appearance histograms. Appearance checks still run separately on every feature-link evaluation.

Invalidate both directions involving the changed frame and preserve other pairs. No model inference, frame selection, target, threshold, deadline or identity rule changes. The cache is scoped to one bounded adaptive recovery instance; nothing is shared across reports or different source pixels.

90 recovery, contour, tracking, inference and source-position contour tests pass. Added tests verify real optical-flow values on textured inputs, unchanged pairs requiring no feature extraction after another frame is filled, invalidation of both directions on upgrade, agreement with a fresh recomputation after changed masks, and exact full bidirectional-review equality with the former full-clear behavior.

`backend/scripts/benchmark_pair_reuse.py` measures this stage using fixed detections from original source pixels. All visible endpoint-instance combinations are workload cases, not assertions that those endpoints depict the same player. Five alternating paired rounds compare full review results and count feature extractions. Inference preparation is excluded from timings. This is not a full-analysis speed or player-identity validation.

## Measured replay

Source SHA-256 `fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2`; 13 decoded frames, 49.448–49.648s; 16 endpoint combinations per round. Across all five paired rounds, feature extractions fell from 505 to 396 (109 avoided). Median stage time fell from 8.592503s to 7.053321s (~17.9%). Every complete review output matched exactly. Raw rounds and source/model hashes are in `testdata/performance/pair-reuse-2026-11-08.json`. This bounded stage improvement must not be added to other optimization percentages or described as total live-analysis savings. No synchronization, deployment or paid model call.
