# Local tracking feasibility — 13 November 2026

Goal: reduce paid perception work and latency while retaining player identity,
action coverage and uncertainty. This experiment does not change production.

## Measured result

The uploaded diagnostic video (source SHA in local-bytetrack-summary.json)
was processed from 15,000 to 18,000 ms: all 180 source frames, original decoded
resolution, existing YOLOv8n weights and preprocessing, one CPU affinity core,
one OpenCV thread. The detector input remains 640, as in the existing detector.
The newly added ByteTrack path retains person candidates above 0.1 for its
second association; this differs from the old detector's 0.25 candidate floor
and is experimental, not an equivalent replacement for existing evidence.

Second measured pass: 32.52 seconds total; 30.42 detection, 1.71 decoding,
0.26 tracking. Zero LLM calls. Tracks were returned on 180/180 frames, with
20 distinct track IDs. These are all-player proposals, NOT a demonstrated
continuous track of the selected player. Identity switches are unmeasured.
The first pass took 31.71 seconds. Neither is a full report benchmark or a
measurement on the deployed server. CPU architecture also affects timings.

An ONNX Runtime comparison was blocked by automatic review after an attempted
telemetry connection despite disabling telemetry. There is no validated ONNX
result; do not retry it indirectly or infer a speedup from it.

## Architecture to validate next

1. Decode once with actual media timestamps; attach source and model hashes.
2. Reuse one person/ball detector pass across consumers. Track people with
   ByteTrack; retain ball measurements separately. Never equate a person track
   ID with the selected player or a ball detection with the active match ball.
3. Bind original tap points to an unambiguous visible person. Multiple boxes,
   missing detections, occlusions, cuts and discontinuities require explicit
   uncertainty. Re-identification requires evidence beyond ByteTrack ID reuse.
4. Persist source-bound observations and uncertainty intervals for both report
   analysis and graphics. Consumers must not repeat identical pixel inference.
5. Evaluate which currently paid localization windows are fully covered by
   verified local observations. Only those windows may become eligible to skip
   LLM localization after comparison against annotated video. Football action
   interpretation retains its own evidence requirements.

Do not enable automatic LLM suppression based merely on detector confidence,
smooth paths or the presence of a track. No FPS, resolution or model reduction
is part of this experiment. Camera-cut reset is a heuristic, not proof that all
cuts or identity switches have been detected. Feet/ball coordinates and masks
are not supplied by this player-box benchmark.

## Required comparison

Use the actual target player and labelled occlusion/cut boundaries. Record
identity switches, missed target frames, wrong-player frames, ball coverage,
action outcomes and report evidence. Compare end-to-end time and paid tokens
against the current sequence pipeline, including fallback calls and retries.
Unknown identity remains unknown. A faster proposal generator alone cannot
establish report-quality parity or justify a claimed cost reduction.

## Reproduction

Use an isolated environment with backend/requirements-local-tracking-test.txt.
Run backend/scripts/benchmark_local_bytetrack.py with --video, --start-ms,
--end-ms and a new --output path. The engine is OpenCV. The benchmark
blocks socket connections and writes proposal rows plus timings. Supervision
0.26.1 is pinned to its documented ByteTrack API; production dependencies are
unchanged. Run backend/tests/test_local_bytetrack_proposals.py with pytest.
