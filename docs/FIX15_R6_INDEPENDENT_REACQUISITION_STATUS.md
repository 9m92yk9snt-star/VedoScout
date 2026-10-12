# R6: independent optical support and same-ball A3 reacquisition

Continuation of `267fc54` on `codex-r6-native-jersey-20261011`. The same
canonical video and 12 original user markings remain unchanged. This is a
fail-closed evidence repair, not a five-action PASS or a deployment.

## Source-confirmed defect

The old flow matcher counted each later optical sample independently even
when both samples matched the same weak detector observation. Neither tap
recovery producer required the chosen strong A3 reacquisition to match that
optical path. A path containing a nearby weak observation and a different
strong ball could therefore create a verified aggregate release.

The source-bound replay contains that exact failure at 42.415 seconds:
optical samples at 42.432 and 42.448 both match the weak observation at 42.448.
The selected strong ball at 42.432 matches neither optical sample. The existing
downstream contact-to-release gate independently rejects its anchor as
`CONTACT_BALL_NOT_PROOF_ELIGIBLE`; there is no valid release-to-goal chain.

## Repair

- Count a maximum one-to-one matching using independent actual integer media
  timestamps. Repeated rows or multiple same-frame proposals do not add proof.
- Require that matching to include the exact chosen strong reacquisition,
  rather than a weak object sharing its timestamp or another nearby endpoint.
- Apply the same rule in both `EXACT_TARGET_SUPPORT_PATH` and
  `TAP_CONTINUITY_SUPPORT_RELEASE` before constructing a verified contact.
- Keep the existing 25 ms / 0.05 flow gates, two-later-observation requirement,
  actor continuity, contact geometry and separation gates unchanged.
- Optical support remains support-only; no predicted/search-only observation
  becomes measured proof, and no reference action label is consumed.

## Verification

All 22 new regression cases fail against the exact local Git baseline.
Six expose failures of the existing matcher/producers; the others exercise
the new explicit endpoint-binding contract. The repaired implementation
passes all 22 and the 44 existing recovery/contact-role control tests.

Expanded serial offline regression: 1,395 passed, 19 SDK-dependent skipped;
zero SDK, network or native video-decode attempts. Three existing native
synthetic-video integration tests pass separately with OS socket isolation
and SDK constructors blocked. Missing test dependencies were restored from
local cached wheels only. The task-local runtime uses cached AnyIO 4.15.1;
repository requirements remain unchanged at 4.13.0. The resulting existing
Starlette deprecation warning is retained in the test log.

A fresh five-window reconstruction starts with empty old contacts and semantic
votes/outcomes. All 20 existing blind local jersey responses are re-bound to
their exact current body/time/native pixel hashes. The original user field
15 is retained as explicitly identified continuation metadata because the
original report ZIP was not preserved locally; it is not inferred from model
results and is never supplied to blind readers. All raw anchor times, boxes,
masks and original video bytes remain unchanged.

The suspect 42.415-second release is no longer verified. The measured contact
at 30.915 seconds is preserved; its measured ball path still ends at 31.065.
New short optical continuation searches match 17 original pixel-cache frames
and remain SEARCH_ONLY. They do not close the outcome chain.

The strict result remains **0/5**, with all five cases NOT_VERIFIED. Goal-line
crossing, goalkeeper intervention and recipient-to-goal chains still need
independent same-ball proof. CI results are checked separately on the exact
saved commit and do not replace this video-based acceptance gate.

No Emergent execution, paid model calls, gate relaxation, original marking
retiming, deployment or merge.
