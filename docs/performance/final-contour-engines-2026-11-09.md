# Source-bound final contour comparison

Both engines processed the exact exported 8.75–10.00s window, pinned medium model, 76 frames and all nine source endpoint pairs on one CPU. Both accepted eight segments and rejected the same source-conflicting interval. All diagnostic decision fields matched after excluding elapsed detector time.

Exact emitted output did not match: 93 confidence fields and 34 geometry/structure entries differ. The geometry differences include the foreground polygon at segment 7, sample 14 (polygon 5: 123 versus 126 vertices). Indexed vertex differences must not be interpreted as physical displacement, because the vertex counts differ. No claim is made about which contour is more accurate. This prevents an exact-equivalence approval for switching the recovery engine.

Single-run profiled elapsed times were OpenCV 110.543407s and ONNX 88.030928s. These are bounded offline measurements with a generous 420s deadline, not live latency or timeout guarantees. OpenCV version was 5.0.0; deployment-version equivalence is not established. This exercises the source-position contour pipeline, not every recovery branch.

Reproduce each input using profile_matchroom_contours.py with --timestamp 00:08 --window-start-ms 8750 --window-end-ms 10000 --model medium --seconds 420 --one-cpu --audit-pairs and the respective --engine. Compare with compare_contour_outputs.py. Complete outputs are retained as xz/base64 files; the comparison includes raw-output hashes. No production engine switch, paid provider call, synchronization or deployment.
