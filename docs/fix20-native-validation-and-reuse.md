# FIX20 — native video validation and bounded proposal reuse

This review candidate follows FIX19 in PR32. It does not merge, sync to
Emergent or deploy the changes. The original video and private evidence remain
outside the repository.

## Concrete changes

Overlapping dense replay windows currently request the same native detector
work repeatedly. A run-local session now reuses only stateless person/ball
proposals for identical pixels, dimensions, dtype, loaded model SHA and detector
settings. Every window still reconstructs its own camera motion, tracks,
GLOBAL_TARGET binding, contacts, ball trajectories and outcomes. Native
selected-body refinement remains available. No semantic response or event
decision is cached; identical frames do not become independent evidence.

The cache holds at most 768 entries and 16 MiB of serialized proposal payload,
retains no images, and gives callers independent mutable results. Failed calls,
unknown models and oversized payloads are not reused. Its lifetime is one
physical reconstruction; it cannot carry one player's selection into another
report. The physical output records actual hit/miss/payload metrics.

The old `original_taps_sha256` only covered t/box/segment/verify. A different
target point, mask or behind selection therefore had the same legacy hash.
Keep that field for historical export compatibility and add versioned
`selection_inputs_sha256` over consumed human selection metadata and the anchor
time offset. Record a separate player-details hash and ONNX Runtime/Pillow
versions. This is provenance; no checkpoint or semantic-response cache is
enabled by this patch. It is not a complete key for all analysis assets.

## Measured validation

- 1,343 relevant offline regression tests pass, including physical evidence,
  reconciliation, native selected-body refinement, selection UI contracts and
  job fencing. Zero network, remote SDK or video-decode attempts in this suite.
- 77 focused tests also pass; this set overlaps the larger suite.
- A bounded benchmark uses original-video windows 0–600 and 300–900 ms, with
  actual decoded PTS, the same fresh scene graph and identity authority, and
  both native and physical/reconciliation stages. It does not receive expected
  football-event labels. Both passes produce 74 frame rows.
- Control: 148 native forwards, 24.509 seconds. Reuse: 110 forwards, 18.219
  seconds, 19 hits / 55 misses, 97,447 bytes of cached proposal payload. This is
  25.7% fewer forwards on these overlapping windows, not a whole-report claim.
- The entire serialized physical traces and canonical evidence are identical:
  SHA256 `d05d232878c04fa2f4780fe7add8a1f6789e2f41e7bc05d7a53b4f5357fe2642`.
  Network attempts: 0. Audited backend sources remained unchanged.
- All five GitHub jobs pass on code head `93eeb33297f8ddff5a487d021e38250c269853ac`:
  backend regression 1,736 passed / 19 skipped; selection 346 passed; FIX10
  778 passed; export 35 passed; frontend 91 passed and production build PASS.
  These suites overlap. Existing dependency/hook/build warnings remain.

## Completed original-video baseline

The separate native diagnostic completed on unchanged FIX19 commit
`f6bbd6a0525020dc13b255a6206e9671a657cea7`, not on a deployed FIX20 build.
It used the complete checksum-verified source video and original eleven
selections. All 15 planned windows completed, producing 6,165 frame rows at
4,551 distinct media timestamps from 0 through 76,664 ms. Overlap repeats rows;
cut gaps and the final source tail mean this is not all 4,606 source frames.
Zero fallback rows and zero non-actual-PTS rows were observed. Physical execution
took 1,238.576 seconds; tracking 14.084, identity 43.619, preparation 55.791 and
reconciliation 3.683 seconds. There were 13,024 detector forwards across stages,
zero network/remote-SDK attempts, zero new online model calls and zero database
writes. Audited backend sources remained unchanged.

**Post-hoc reference acceptance is 0/5.** This does not assert that the player
had zero actions. All five reference times have actual native frames, but no
qualified canonical event was established. At 23.68, 43.19 and 49.44 seconds,
the nearest frame lacks target identity across a scene cut. At 30.83 and 56.44,
nearest-frame target continuity exists, but there is no qualified target strike
or scoring chain. Nearby native outcomes remain unresolved. The remote action,
jersey, role and goal readers were disabled, so this is not a new complete
ScoutMePlay analysis or a measure of the full online system's recall.

The next accuracy work must examine automatic re-identification after cuts and
the target/contact/active-ball binding before outcomes, using actual reader
responses and exported traces. Do not require extra manual player checks or
loosen identity/goal proof gates to make the five references pass.

Machine-readable measurements are in
`docs/examples/fix20-native-validation-summary.json` and
`docs/examples/fix20-native-reuse-benchmark.json`. The former is generated only
after reconstruction has completed; expected labels are read only for QA.

Commands, in an isolated checkout without backend/.env:

```bash
python backend/scripts/audit_current_video_pipeline.py \
  --evidence /private/original-evidence.zip --output /private/new-native-run \
  --threads 4 --declared-number 15 --physical

python backend/scripts/benchmark_native_proposal_reuse.py \
  --video /private/new-native-run/source.mp4 \
  --prepared /private/new-native-run/unified_without_semantic_reader.json \
  --output /private/new-reuse-benchmark --threads 2

python backend/scripts/summarize_native_video_audit.py \
  --run /private/new-native-run \
  --cases docs/examples/five_action_reference_cases.json \
  --output /private/new-native-summary.json
```

The diagnostic and benchmark disable external model readers. The original
export contains eleven historical selections and an old declared number 5;
the diagnostic records the user's explicit declaration 15 separately, not as
OCR evidence. Old selections do not demonstrate acceptance of fresh FIX19
cutouts. No expected action labels enter tracking or reconstruction.

## Remaining acceptance boundary

Native-only evidence cannot replace unavailable jersey, action-role and goal
readers. A new complete ScoutMePlay analysis with reviewed FIX19 code, correct
number 15 and fresh initial taps is still required. Compare its exported PDF
and evidence against the five cases afterwards. Do not hardcode their counts,
convert uncertainty into proof, or claim five accepted actions from this
benchmark. Emergent initially timed out, then loaded its sign-in page on one
recovery navigation. Login is now the observed access boundary. No new online
model call, Emergent code sync or deployment has been verified.
