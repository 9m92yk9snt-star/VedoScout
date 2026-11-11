# Medium engine adaptive-decision replay

The full AdaptiveAssociator.review decision path was replayed with OpenCV and ONNX medium detections on 13 identical decoded source frames (49.448–49.648s). Small-model detections and endpoint points were identical between engines. All 24 unique visible endpoint combinations were compared, including rejected cases: 3 accepted and 21 rejected, identically. Both full reviews (paths, conflicts, events, samples and accept/reject) and the sets of requested small/medium detections matched exactly.

Endpoint combinations are computational test cases, not independently confirmed player identities. This is a short offline decision replay with precomputed detections; it does not verify production timeouts, source-observation binding, final emitted graphics/confidence values, or other video sequences. The earlier tiny confidence differences are not erased. No engine switch is enabled and no overall speed gain is claimed.

Source/model hashes, all per-case reviews and requests are stored in testdata/performance/recovery-paths-2026-11-09.json. Reproduce with backend/scripts/compare_recovery_paths.py. No paid provider call, synchronization or deployment.
