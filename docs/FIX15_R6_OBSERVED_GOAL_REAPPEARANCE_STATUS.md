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
