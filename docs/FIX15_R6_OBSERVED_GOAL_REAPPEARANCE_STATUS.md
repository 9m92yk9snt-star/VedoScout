# Observed whole-ball reappearance after a short body occlusion

The user's observations are search/evaluation context, not a human goal
approval. The briefly added human-review interface and review record were
removed after the user clarified this requirement. Automated scoring remains
the sole event authority. The hidden crossing need not be directly visible;
the implemented post-occlusion lane instead requires a measured, consistent
before/after sequence. Observations guide where to inspect without supplying
the expected answer to the pixel detector.

## Automatic search correction after the clarification

The dense native gap inspection no longer waits for `VERIFIED_OCCLUSION`.
That verdict required independent goal geometry and pre-occlusion visual
observations, making evidence collection wait for the conclusion it should
help investigate. A completed scene response plus an independently qualified,
contact-bound native path can now open the bounded local search. The resulting
packet remains `SEARCH_ONLY`; incomplete responses, unbound paths and fake PTS
remain ineligible. All downstream physical/identity/direction gates are intact.

The scene-reader prompt explicitly continues inspection after body occlusion
for ball reappearance, spare balls, outside-post observations and possession.
It separates the directly visible crossing verdict from the runtime's
before/after occluded-goal inference. Neither a hidden interval nor absent
celebration is, by itself, a reason to reject a measured post-occlusion goal.
No invisible crossing timestamp is supplied by the user's description.

A further original-pixel check used the shared YOLOv8n and an already cached
YOLOv8m, five native crop sizes per frame, the original last-before image and
six documented after images: 70 forwards / 14 model-frame pairs. Exact RGB
hashes were checked against the original PNG receipt. At the documented after
feature there are still no qualifying class-32 detections from either model.
This is not a new automatic goal acceptance. The feature hints only select
inspection regions; they never supply ball class or event outcome.

Focused native/reappearance/occlusion/runtime tests: **176 passed**. No paid
model calls, production report writes or deployment were performed.
The full offline regression selection passed **1,510 tests, 28 skipped** in
47.30 seconds, with zero attempted SDK, network or video-decode calls in the
regression process. Pixel inference was a separate offline diagnostic, not
silently substituted for a completed automatic goal verification.

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

## Continuation: temporal candidates, literal context and retained before images

The unfinished local continuation was recovered and checked against PR #29
head `1990b43`. It adds original-pixel appearance proposals, post/crossbar image
candidates, and literal per-image right/left release-foot, same-keeper head,
glove, outside-ball and possession observations. These are search/support
data, not canonical ball identity, goal depth or a goal approval. A projected
goal rectangle alone cannot establish that a ball is inside the goal volume.

Native search runs before the one existing independent reader call so candidate
times can improve that call's image coverage. Reader refocusing preserves the
last three measured before positions, contact/seed and terminal context, and
three remaining baseline slots when available. Unclassified candidates cannot consume
the entire after interval. There are still at most twelve reader images and no
additional remote reader calls. Source provenance includes all three modules.

The saved original contact-bound path has last-before times 31,065 / 31,132 /
31,182 ms. The prior reader plan omitted the first two. The revised original
plan preserves all three and the original 31,857 ms image inside the documented
short reappearance. Six before boxes were matched to their exact independently
measured native detector candidates; the global spare-ball trajectory was not
substituted. This schedule check uses saved measurements, not a new goal verdict.

An airborne ball's screen position relative to a ground line cannot by itself
establish its position in field space. A narrow airborne-before lane requires
three high-confidence before relations and all after relations from a complete,
hashed independent image response, each bound to the native ball boxes. Native
same-ball identity, time-aligned geometry, whole-ball after position, field
direction, contradictions and final proof checks remain mandatory. Contextual
head/glove/foot observations cannot open this lane.

Validation: **215 focused checks**, and **1,539 full offline regressions passed,
28 skipped** in 47.15 seconds. All recorded SDK/network/video-decode attempts in
the regression process were zero. The lifecycle suite and a full rerun passed
after one earlier teardown process-hygiene error; the runner was not modified.

A separate fresh original-video probe decoded **55 images**, verified all 55
goal-region RGB hashes, and retained all seven 31,849–31,949 ms reappearance
images. Five gap images contained detector-qualified proposals; the native
moving-ball identity remained unresolved. Appearance search returned 129
unclassified tracks, not a recovered football. Goal geometry and crossing both
remain **UNRESOLVED**, with no canonical goal and no report count writes.
This was not a fresh full five-action run; its last strict acceptance is **0/5**.

The reproducible test target list and compact original-pixel/sampling receipt
are in `docs/evidence/FIX15_R6_TEMPORAL_GOAL_VALIDATION.json`. Next work and the
main/draft distinction are in `docs/SCOUTMEPLAY_PROJECT_STATUS_20261013.md`.
Keep draft until original-video acceptance; no deployment occurred.
