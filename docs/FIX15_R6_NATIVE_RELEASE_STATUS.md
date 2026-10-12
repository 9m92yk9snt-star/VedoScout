# R6: native contact-to-ball binding and transport-free goal parsing

Continuation of `2195247`, with the same canonical video, all 12 original
markings and unchanged reference/event gates. No deployment or merge.

## Implemented

Native release-local tracking now uses the exact measured background camera
chain and decoded pixel geometry. Camera pan, acceleration, zoom and rotation
cannot become ball acceleration. An unknown native transform ends the identity;
there is no screen-coordinate or player-proximity fallback. The existing speed,
acceleration, measured-gap, size and motion-support limits are unchanged.

A fresh touch can carry an A3 observation below the release tracker's existing
0.04 confidence floor. The producer now qualifies a later measured seed before
binding: it must be on a unique camera-corrected path from the verified contact,
inside the unchanged 300 ms horizon. The original weak proposal must also match
the raw native pixels/proposal and uniquely agree with the measured endpoints.
That interpolation is supporting-only, never an extra proof point. Original
touches remain unchanged and the strike retains the old seed and qualification
audit. Rejected, external, predicted, search-only or already eligible required
anchors cannot be substituted, and cannot fall back to the global/reserve ball.

`parse_goal_scene_response` exposes the existing goal response gates without an
SDK transport, API key or paid-provider impersonation. The legacy reader calls
the same parser. Coverage, geometry, whole-ball continuity, occlusion and reaction
requirements were moved unchanged; the 61 moved gate statements have AST SHA256
`d7836c86f9f6c9629b45a182083a13157a3f1cc86d4322aac6cb2124305a465c`.
Native timestamp input is strict, and the actual local model audit is retained.

## Verification

- 1,017 offline tests pass; 19 SDK-dependent cases/modules are skipped.
- 93 new tests: 25 camera/release, 49 seed-selection and 19 native-parser tests.
- The 74 camera/seed tests against unchanged `2195247` produce 60 failures and
  14 passes. Sixteen failures exercise existing public behavior; 44 concern the
  new qualification API. No baseline source was edited.
- Overlapping broad test runs had three process-hygiene teardown errors. The
  final complete, non-overlapping run passes without changing those tests or
  their assertions. Failed-run receipts are retained, not reported as PASS.
- Actual SDK, network and native video-decode attempts in unit tests: zero.
- Fresh bounded native audit: 1,922 original actual-PTS frames re-decoded,
  1,922 pixel-cache matches, zero new detector forwards or paid calls.
- All audited backend source hashes match afterward. OS socket-isolation
  self-check passes; Python network/SDK attempts remain zero.
- Fresh blind jersey replay binds all 20 raw local observations to the exact
  requested body rectangle, actual PTS and re-decoded torso pixel SHA.
  No old model contacts, votes or outcomes enter reconstruction.

## Actual contact chain, not an outcome verdict

Two temporally independent native crops on local body `p036` read number 15
without an expected number in the reader prompt. The unchanged identity gates
bind one physical contact at 30.915 s using the existing user-stated jersey.
Conflicting number reads on another body remain supporting/unresolved.

The original after-contact observation at 30.965 s has confidence 0.0389 and
cannot pass the existing 0.04 release floor. The producer now selects the
uniquely measured same-ball observation at 30.982 s, confidence 0.22787295.
The verified prefix is 30.915 → 30.982 s. The actual measured outgoing path is
30.982, 31.015, 31.032 and 31.065 s; it stops before the reserve-ball proposal.
The weak original remains in the audit and never becomes a measured proof row.
Neither a release role nor a goal is inferred from this repair.

## Still unresolved

The strict canonical result is **0/5 NOT_VERIFIED**, not five-action PASS.
The first free native goal review has complete row coverage but unresolved
geometry/whole-ball crossing. A later, higher-detail review with the newly
qualified reference is separate ongoing work, not part of that old receipt.
Additional original-marking shirt crops produce no usable enrollment so far;
missing original masks are recorded explicitly, never invented. No cross-cut
identity rule, jersey threshold, reference time or outcome label was relaxed.

Video SHA256:
`2774978344f9c54e44f81c2328f3165d3aada4f1b95193964bb22b73a9ecf85b`.
Original marking SHA256:
`0a49e85e325cbffb36f2296bad75ebf5051a53e5e8442a534fbe18f172da29ed`.
Five-action PASS remains the deployment prerequisite.
