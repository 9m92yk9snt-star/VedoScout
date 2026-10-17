# Reconcile the selected body once

## Observed failure

The report-300 export contains a 76.763596-second video with source SHA-256
`3d4ac55aaef424a7f90012681e408e6f9e9850a388eb2009b4aef8d24c4d7b7a`.
All exported checksums and 13 trace checksums verified. Its 68 exported Python
files match PR #36; the deployment commit field itself is unavailable.

The completed run took 5,585.031 seconds. Physical reconstruction used
4,851.849 seconds (86.9%). It published four goals and zero assists. Those
counts do not establish recognition of the five reference actions.

At actual source PTS 21,482 ms, the original full-body rectangle contains the
white player. Its point grazes a mostly-outside blue player's detection. The
old point-only binding collapses that detection to `p052`. Later the dense
graph incorrectly verifies a blue opponent as GLOBAL_TARGET, and the motion
reader's goal claim is accepted as the selected player's goal.

## Change

The existing selection helper reconciles a conflicting boundary hit with the
same-frame rectangle. The original hit must lie mostly outside that rectangle;
the point must graze both boundaries. A replacement must be an already measured,
nearly enclosed, substantial body immediately adjacent to that point. It never
uses crop-centre proximity alone. Multiple replacements remain ambiguous, and
no replacement leaves the contradictory hit unverified. Visible masks retain
ownership; exclusions and ordinary off-centre point matches are preserved.

The same helper is used by coarse tap pinning, native reference refinement,
the scene graph and dense identity binding. The input rectangle, point, clock,
detector model, thresholds and source-image coverage are unchanged.

The existing motion-video call can now pass its explicit positive or negative
selected-reference comparison to the same canonical resolver used by the first
whole-video read. Actual source/reference metadata binds that comparison to the
supplied actor frames. Explicit other-player or incompatible-kit observations
cannot bootstrap a positive dense identity. No additional model call, approval
stage, video pass or production module is introduced.

## Verification and limits

Replaying the actual stored source frame's measured bodies through dense target
binding now selects `p053`, the enclosed white body, instead of `p052`. Original
tap and frame observations remain unchanged. Using the actual video frame and
the stored detections through the production reference-refinement function
produces one reference at native reduced-frame box `[212, 271, 21, 51]` in a
360-by-640 image, corresponding to that same white body. These are bounded
selection/component replays with zero new model calls, not fresh detector or
event-perception results.

The tests distinguish measured selection geometry from synthetic model replies.
Model-reply controls exercise explicit negative identity, valid positive identity
without another native approval, source/reference binding, masks, exclusions,
ambiguous candidates and unchanged ordinary point selections.

Local validation: 653 passed and one optional LiteLLM conversion test skipped
across 20 relevant modules in 4.50 seconds. Plugin autoload and ONNX Runtime
were disabled and Python socket connections blocked. All 384 backend Python
files parse, and the whitespace check passes. Test runtime is not video runtime.

No new full-video model run or end-to-end speed measurement has been performed.
This change does not retroactively repair the old model's event labels or prove
the saved shot, goal and three assists. The old observations replayed through
PR #37's resolver still accept the wrong goals; first-read reuse by itself was
not a fix for that failure. PDF benchmark/text consistency and the profile's
stored `preferred_foot=right` are separate remaining issues.
