# Observed whole-ball reappearance after a short body occlusion

The previous goal lane needed a visible crossing or a short extrapolated
trajectory plus celebration. A ball that disappears behind bodies and later
reappears wholly inside the goal needs a separate physical-evidence lane.
This change implements that lane and wires local measurement into the goal
provider. It does not certify the user's original goal or complete the five
reference actions. Keep this change draft; do not deploy or merge on unit-test
success alone.

Base: `4224e75cced3367eff93ee17870372880a78f94e` on
`codex-r6-native-jersey-20261011`, including the earlier native mask/body
corrections. The earlier `ade1880` circle-motion checkpoint is an ancestor of
this base. Existing contact/release/jersey gates and original user selections
are retained.

## Implemented behavior

- Three contact-bound native before observations, completed independent image
  review, literal body occlusion and time-aligned goal/field geometry remain
  required. The bounded gap is at most 900 ms.
- The provider re-detects the reviewed after ball in original pixels and
  measures background camera alignment locally. The detector's loaded weights
  and source video are fingerprinted. No reader JSON can supply native identity.
- Three independently classified after observations over at least 80 ms must
  match the contact-bound ball's interior appearance. A competing moving ball,
  missing alternative path or unmeasured camera alignment keeps the result
  unresolved. An already-present stationary ball is a separate negative control;
  stillness alone cannot classify a stopped active ball as a reserve.
- The whole ball must be field-side before and goal-side inside the mouth after.
  Goalkeeper reaction, no visible outside ball and user observations alone do
  not certify the event. Verified conflicting contact or no-crossing evidence
  blocks this narrow unopposed lane.
- Crossing time is the first observed whole-ball goal-side position, accompanied
  by the explicit last-before/first-after interval. It is not a fabricated exact
  hidden crossing instant. Direction and final ball-proof gates recheck the
  packet independently.
- Video rebinding invalidates the goal cache. The contact-bound native path is
  part of its cache key. New modules are included in evidence fingerprints and
  the production CI test selection.

`parse_goal_scene_response` continues to parse geometry/visible observations
without SDK transport. Native identity is attached only after local pixel
measurement, outside that reader boundary. The normal goal reader is unchanged;
this work adds no extra remote model calls. All validation in this session ran
without Emergent execution, paid model calls, database writes or deployment.

## Validation on 13 October 2026

- Focused rule/provider/parser/sampling tests: **151 passed**.
- Archived 122-file regression selection plus both new test files:
  **1,487 passed, 28 skipped**, 46.33 seconds. Offline skips include SDK-dependent
  cases. Zero attempted SDK/network/video-decode calls in that
  test run; Internet sockets were additionally blocked at the process level.
- The checked-in native ONNX bytes load and pass the shared parser smoke test.
  Model fingerprint:
  `013a98f3bc0264a3d793ef29ccbd178ceb0bbb86bc12ff3510273ce85b1c4526`.
- Synthetic 667 ms occlusion plus measured after positions passes the complete
  outcome, field-to-goal and ball-proof chain without a celebration. This is a
  fixture test, not evidence that the original football action passed.

## Fresh original-video check: still unresolved

Source video SHA-256:
`2774978344f9c54e44f81c2328f3165d3aada4f1b95193964bb22b73a9ecf85b`.

Seven original frames were freshly decoded at actual PTS 31,182 / 31,849 /
31,865 / 31,882 / 31,899 / 31,915 / 31,949 ms. All seven decoded goal-region RGB
hashes match the saved original PNG pixels exactly. Full-image and local ROI
class-32 detection were rerun. The circle's prior measured feature positions
were search hints only; no feature was relabelled as a classified football.
There are zero independently qualifying detections at the circled moving
feature in all six after frames. Other candidates remain separate objects.

The original contact at 30,915 ms was also re-evaluated with its six unchanged
contact-bound before positions, original touch graph and original unresolved
goal geometry. Current gates return `UNRESOLVED`, with no canonical goal.
The original automated goal is therefore **not PASS**. This check is not a fresh
five-action reconstruction; the last strict five-action acceptance remains
**0/5**.

Remaining work is independent recognition/identity of the moving after ball,
goal-plane and field-side geometry, and correct scoring-contact attribution.
The user's right-foot, post/occlusion and after-goal observations remain
documented separately; they have not been substituted for automatic measurements.
Original video, markings and production report counts are unchanged.

## Follow-up: dense native inspection of the documented reappearance

The three newly supplied screenshots (IMG_9600/9601/9602) show earlier chat
instructions, not additional football frames. They were read successfully.
The original documented right-foot strike, post direction/occlusion,
goalkeeper response, separate reserve ball and after-goal ball observation
remain the basis of the investigation; they are not relabelled as automatic
measurements.

A concrete coverage defect was found. For the original contact-bound path
ending at 31,182 ms, the twelve-image scene-reader plan samples only 31,857 ms
inside the measured 31,849–31,949 ms reappearance interval. A three-observation
native reappearance rule could not use that single scene-reader after row.

The provider now opens a separate bounded local scan when a completed review
contains literal body occlusion and a verified contact-bound native path.
It decodes the following 900 ms at approximately 60 fps (at most 56 requested
images, clipped to the original window). The remote scene-reader image budget
and number of remote calls stay unchanged. Native detector boxes, pixel hashes,
measured camera affines and competing candidate segments are retained.

After an independently verified goal line AND field side exist, classified
native after positions can supply the additional after observations. Static
geometry is transferred with measured background affines over at most 100 ms;
it is not copied unchanged through camera motion. Source mismatches, conflicting
duplicate identities, competing balls, missing geometry, unclassified features
and visible outside-mouth positions keep the lane unresolved. The ordinary
outcome, direction and final ball-proof checks still run.

Original-video check: **55 frames**, all 55 goal-region RGB hashes matching the
saved original pixels exactly. The dense plan captures 31,849 / 31,865 / 31,882 /
31,899 / 31,915 / 31,932 / 31,949 ms: all seven frames of the short reappearance.
Five other frames in the gap contain detector-qualified ball proposals; the
moving circled feature is still not linked as the released football. The native
identity result and original goal crossing remain **UNRESOLVED**. There is no
new automatic GOAL, canonical event write, five-action PASS or deployment.

Validation after the follow-up: **158 focused tests passed**; the full archived
selection plus new tests passed **1,507 tests, 28 skipped** in 46.44 seconds when
run without concurrent pixel inference. Zero attempted network/SDK/video-decode
calls in that regression run. The separate original-pixel experiment uses only
local decoding and inference under the network guard.

The export-limit fixture now leaves space for the expanded mandatory source
provenance while keeping its test video above the per-file cap. The export
production size limit and fail-closed behavior are unchanged. Source fingerprints
now also include the native sampling module.
