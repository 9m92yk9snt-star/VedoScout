# Recovery engine comparison

Five full source frames at 8.75, 23.68, 30.83, 49.44 and 56.44 seconds were compared using the pinned medium model, unchanged preprocessing and mask decoding, one CPU affinity, two OpenCV threads and one BLAS thread.

All 29 detections have identical masks, boxes and classes. Confidence scores differ for 22 detections; the maximum absolute difference is 1.9073486328125e-06. Exact metadata parity therefore fails. This does not establish worse accuracy, but downstream threshold and association decisions have not been compared.

Total prediction time across the five frames: OpenCV 6.897011s; ONNX Runtime 5.336872s. These are single-sweep timings including cold effects, not a robust speed benchmark or a total-analysis improvement.

Production engine selection is unchanged. Next required validation is full recovery replay with both engines, comparing decisions, emitted segments and rejected cases. No paid provider calls or deployment. Reproduce with backend/scripts/compare_recovery_engines.py; raw evidence in testdata/performance/recovery-engines-2026-11-09.json.
