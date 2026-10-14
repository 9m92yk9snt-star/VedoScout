# R6: original marker capture and native timestamp binding

Continuation of `91b03c4` on `codex-r6-native-jersey-20261011`. The same canonical
video and all 12 original user markings are retained. Deployment requires the
strict five-action PASS; no deployment or merge has occurred.

## Source-confirmed defect and repair

The 12 original marking JPEGs and original user marker capture were recovered
by GET from the exact backend-relative media URLs already recorded in the
report. They are original input material, not new uploads or model output.
The two tested original MOV paths returned 404; other storage is not inferred.

`precision_engine.estimate_time_offset` read `CAP_PROP_POS_MSEC` before decoding
the image it scored. OpenCV returns the previous image's PTS at that point.
The unchanged function on the recovered original capture reproduces the
report's exact stored offset, -0.016666 seconds, at score 0.998518168926239.

The repair pairs matching pixels with their own post-decode PTS and uses the
existing adaptive native-time seek. Missing, non-finite, negative, repeated or
decreasing PTS fail calibration; FPS/frame-index values do not supply a match
time. The capture is released on all exits. The existing match-score threshold
and visual scoring remain unchanged.

On the identical capture/video pair the repaired function returns offset 0.0
at the identical score. The actual matched source frame is 3.833180 seconds.
The original report, stored offset, raw anchor times, boxes and masks remain
unchanged. A separate disposable audit document records the source-derived
mapping alongside the old value; action reference labels play no part in it.

Nine masked source photos also register to nearby original video frames using
their unchanged user RLE. Dark green mask fill is excluded from the comparison.
Literal image registration supplies source provenance rather than person or
event authority. Padded context photos never become unmasked identity proof.

## Verification

- All 15 new timestamp regressions pass. Before the repair they produce 14
  failures and one pass on the unchanged production implementation.
- Serial offline regression: 1,373 passed, 19 SDK-dependent cases/modules
  skipped, zero actual SDK, network or native video-decode attempts.
- The three existing native synthetic-video integration tests pass separately
  under OS socket isolation, with SDK construction blocked.
- The initial broad attempt blocked three native integration decodes and
  reported a process-hygiene teardown error. Its failed log is retained. Final
  serial/separate-mode checks pass without changing those assertions.
- Fresh identity timeline: 197 candidate target observations. This count is
  diagnostic; scene 002 remains unresolved across its existing cut barriers.
- Fresh bounded audit re-decodes all 1,922 original actual-PTS frames, matches
  all 1,922 pixel-cache entries, and makes zero new detector or paid calls.
- A fresh jersey replay rebinds all 20 existing blind native responses to the
  exact current body, time, native torso shape and pixel SHA. No original model
  contacts, votes or outcomes enter reconstruction. Both audits remain 0/5.
- The existing qualified body/contact chain at 30.915 seconds is preserved.
  Neither the repaired clock nor jersey identity supplies an outcome verdict.

## Remaining source observations

Searching every actual dense PTS in the first exported window runs 1,882 local
foot-ROI detections across 354 frames. All 193 proposals retain SEARCH_ONLY and
proof_eligible=false. Extra measurements around the shot require independent
active-ball identity; they do not replace the canonical trajectory.

The earlier high-detail local goal review ended with TIMEOUT at 722.705 seconds.
Its incomplete response is not admitted as geometry or crossing evidence.
Native whole-ball continuity, goalkeeper interaction, goal geometry and the
recipient-to-goal chains remain subject to the existing proof gates.

Video SHA256:
`2774978344f9c54e44f81c2328f3165d3aada4f1b95193964bb22b73a9ecf85b`.
Original anchors document SHA256:
`0a49e85e325cbffb36f2296bad75ebf5051a53e5e8442a534fbe18f172da29ed`.
Original marker capture SHA256:
`d6c657e519c29300e49e749fd037fb59c41ecff39ce9c1c3ea78a0618abec8b2`.

No Emergent execution, paid model calls, threshold relaxation, original-marker
retiming, automatic source-proposal promotion, deployment or merge.
