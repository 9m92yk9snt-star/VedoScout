# Heavy bottlenecks: measured priorities

## 1. Medium segmentation dominates the difficult clip

A new ONNX profile used the exact original video and retained 00:08 source observations, restricted to 8,750–10,000 ms on one CPU. Model SHA-256: `20877569fcfc4744855b1d6d05b0cd7031987ae31894af5c7e1e74328d18e653`. OpenBLAS was limited to one thread; ONNX inference options were unchanged.

- Whole contour window: 82.6714 seconds for 1.25 seconds of video.
- ONNX forward execution: approximately 76.837 seconds, about 93% of the total.
- 76 frames decoded and detected; all nine endpoint pairs reached; eight segments accepted. One source/display conflict was withheld by the existing gate.
- Model initialization: 0.2097 seconds, excluded from the window time.

This is a profile, not an optimization comparison or a claim that it reproduces the historical report's exact outputs. The evidence isolates model execution as the dominant cost. Session-loading improvements cannot remove most of this delay. Earlier complete local eight-card execution separately measured 281.333 seconds in the medium phase out of 491.59 seconds total graphics time; those timings are from a different run and must not be added to this profile.

Evidence: `testdata/performance/heavy-medium-profile-2026-11-08.json`. Reproduction:

```bash
PYTHONPATH=backend OPENBLAS_NUM_THREADS=1 python backend/scripts/profile_matchroom_contours.py --report /path/report.json --video /path/source.mp4 --timestamp 00:08 --window-start-ms 8750 --window-end-ms 10000 --model medium --engine onnxruntime --seconds 180 --one-cpu --output /path/profile.json
```

## 2. Report writing and position localization run serially

The original exported timings are 155.729 seconds for report writing/projection and 259.352 seconds for localization. The current path awaits the writer in `generate`, then starts localization in `persist_assets`. These are separate intervals in the same original report.

Selection is a real dependency: the report has 21 canonical events, but only eight cards are retained. Writer evidence mentions affect ranking within the scoring/non-scoring groups. Therefore pre-localizing all 21 would add unnecessary work and change cost; moving all localization before the writer without preserving selection is not justified.

A specific stable subset exists: this source contains five GOAL/ASSIST/SHOT events. Since scoring events sort ahead of other events and there are at most eight of them, all five are selected regardless of writer mentions. The retained-data regression test covers both no extra mentions and heavy mentions of non-scoring events. Cases with more than eight scoring events do not have this guarantee.

The next substantial scheduling candidate is to prepare/localize only this guaranteed subset while the writer is waiting, then reuse exact request-bound receipts during ordinary localization. Optional cards remain after final selection. This is not enabled yet. Implementation needs:

- A combined provider-call limit: current localization already uses two workers, while the writer uses one. Simply launching them together would increase pressure and could worsen rate limiting.
- One owner for completed paid receipts, including writer failure, cancellation and retry; an async wrapper must not orphan transport threads/processes.
- The same source, selection, request hashes and final event bindings as the existing reuse validation.
- A timing comparison that accounts for all provider latency and preprocessing rather than assuming the whole writer interval is saved.

The 155.729-second writer interval is an overlap ceiling for this historical run, not a predicted saving. No new paid model calls or concurrent writer/localization execution were performed in this investigation.

## Priority

The high-impact targets are medium-model execution and removal of safe serial dependencies between the writer and guaranteed-card localization. Continue against these measured costs; helper-function microbenchmarks do not establish minute-scale gains. No production behavior, image resolution, sampling, model weights, identity thresholds or deployment changed in this profiling follow-up.
