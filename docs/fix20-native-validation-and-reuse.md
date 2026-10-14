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
- The baseline full native diagnostic on the 76.764-second original video is
  running separately on unchanged FIX19 sources. Its final results will be
  added here before this work is described as complete.

Commands, in an isolated checkout without backend/.env:

```bash
python backend/scripts/audit_current_video_pipeline.py \
  --evidence /private/original-evidence.zip --output /private/new-native-run \
  --threads 4 --declared-number 15 --physical

python backend/scripts/benchmark_native_proposal_reuse.py \
  --video /private/new-native-run/source.mp4 \
  --prepared /private/new-native-run/unified_without_semantic_reader.json \
  --output /private/new-reuse-benchmark --threads 2
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
benchmark. Emergent navigation failed to complete in this session, and no new
online model call or Emergent deployment has been verified.
