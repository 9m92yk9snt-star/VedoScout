# Match Room display continuity

The accepted reference uses a continuous green marker, including estimated positioning through short overlaps. A report containing a few visible frames is not sufficient acceptance.

The automatic report now reuses `match_room_display_bridge.display_bridge`, the same camera-space Hermite curve as the approved fall replay. Its 23 reference frames remain numerically unchanged. No hand-written positions or new human taps are supplied to the automatic trial.

## Evidence and presentation

- Dense, bidirectionally agreed instance paths can provide measured lower-body contours. Source body boxes disambiguate nearby opponents' feet. Reversible features may complete a missing optical link, but cannot change an already agreed pixel identity.
- When dense tracking loses a pose, a **presentation-only** bridge can connect independently source-confirmed endpoints. Both endpoint bodies must resolve uniquely, their appearance must pass the existing association threshold, and all intervening source identity observations must remain confirmed. Confirmed source positions inside the interval are retained as camera-stabilized display knots.
- This endpoint mode does **not** claim pixel-tracked identity or newly measured feet in its middle frames. Those rows have `ground: null`, `display_estimated: true` and `source_ground_observation: false`. Their source model observations remain unchanged. The player displays an estimate note.
- Every decoded interval needs valid background camera transforms, fresh foreground masks, no camera cut, frame gaps of at most 75ms and a bridge duration of at most 800ms. Estimated points must remain within the independently observed lower-body region when one is available.
- The renderer checks event/source binding, referenced source positions and fresh frame masks. A measured contour takes precedence over a coarse estimate at the same frame. Conflicting candidates at the same evidence level are suppressed. Uncertain source identity is never bridged.

Closely spaced contact observations are grouped with neighbouring evidence, so a 17ms observation cannot split an otherwise supported sequence into pieces below the minimum frame count. Missing intervals are merged before refinement to avoid decoding overlapping windows repeatedly.

## Observed ball direction

Adjacent direction segments sharing the same observed ball endpoint are one presentation: their arrow no longer disappears and fades in again at every junction. Unrelated or conflicting segments remain rejected. The bounded segment allowance is 16, so a fifth valid observation is not discarded merely because four earlier segments exist. The existing wall-clock budget remains in force. No direction is extended into unobserved or unsupported motion.

## Execution and verification

All original taps and retained paid receipts are reused. Source-position tracking passes are bounded at 35 seconds; legacy tap passes retain their 25-second limit. Up to three targeted medium-model refinements allow 180 seconds each, including when an earlier pass produced only fragmented coverage. Earlier completed paths and ball evidence are retained. The maximum tracking budget is 820 seconds per eight-card report; no additional LLM request is introduced.

Report clips are written to temporary MP4s and decoded at both ends before publication. A failed clip cannot be published as ready.

`frontend/scripts/verify-orman400-matchroom-report.cjs` rejects diagnostic composites and reads the actual encoded frame timestamps. In addition to unchanged ten taps, seventeen events, eight reused receipts, recovery, direction and uncertainty controls, it requires:

- an ellipse on every decoded recovery frame from 11.883 to 12.883 seconds;
- an ellipse on every decoded kick frame from 30.765 to 32.015 seconds;
- a nonzero observed arrow on every decoded frame from 30.949 to 31.249 seconds.

These are regression expectations for the retained source video, never inputs to the tracking algorithm. Actual React playback and visual source comparison are still required before declaring visual acceptance. PR55 remains draft; this work does not establish accuracy on every match or verify the authenticated upload UI.
