# ScoutMePlay project state and remaining work — 13 October 2026

The product's missing five scoring actions are not yet recovered automatically.
The last strict acceptance remains **0/5**. Local regression success is not
original-video action acceptance. The required result is **1 goal, 1 saved shot
and 3 assists**, using the existing original video and existing player selections.
User observations guide automatic inspection; the user does not approve goals.

## Verified source state

| Area | Verified state | Remaining validation |
| --- | --- | --- |
| Guided taps and masked/tilted player recovery | PR #25 merged into main | Representative crowded duels and iPhone/Safari |
| One analysis waiting room, remaining-time calibration and background/profile handoff | PR #26 and #27 merged into main | End-to-end live timing and mobile flow |
| Scoring coverage and jersey binding | PR #28 draft | Fresh complete original-video five-action acceptance |
| Native jersey/body work | `codex-r6-native-jersey-20261011` at `4224e75` | Included in PR #29's base, not merged into main |
| Dense goal reappearance, temporal/context continuation and image selection correction | PR #29 draft | Classified after-ball identity, independent goal geometry and correct scoring-contact attribution |

Verified main: `4b89e714e365f4ecd1af7f7247cf7059959446d5`. PR #29 is stacked
on the native-jersey branch rather than directly on main. Its continuation builds
on `1990b43ec5293579f1f69021a7104ca22adb7627`; subsequent exact source is the PR
head. Source merged into main is not evidence of a live deployment.

## Work completed in this continuation

- Recover the unfinished local temporal search, projected frame inspection,
  literal head/glove/foot/outside/possession context, and audited airborne
  before-position handling. All search/context data retain their limited authority.
- Fix refocusing so the three last measured before images cannot be dropped.
  Reserve baseline temporal coverage when six unclassified suggestions compete
  for the same twelve-image reader budget. The original 31,857 ms reappearance
  observation and all three before observations are retained.
- Verify 215 focused cases and the 1,539-case offline selection; 28 SDK-dependent
  cases are skipped locally. No SDK/network/decode calls occur in the regression
  process. The earlier lifecycle teardown error is documented in the receipt;
  unchanged lifecycle checks and full reruns pass.
- Freshly check 55 original-video images, with 55 exact RGB matches and all
  seven images of the short after interval. Original goal identity, geometry
  and crossing remain unresolved. No canonical events, database writes, user
  marking changes, paid model calls, Emergent execution or deployment occurred.

## Next work, in order

1. **Goal around 30.83 seconds:** identify the released ball after occlusion
   from original pixels. Current class-32 detection and appearance proposals
   do not establish that the documented moving feature is the active football.
   Measure goal plane/field orientation and bind the before/after positions to
   goal volume. The saved 30,915 ms physical contact is still labeled
   `RECEIVE_CONTROL`; verify the actual right-foot strike and attribution to
   selected #15. Do not use keeper reaction or absence of an outside ball as
   a substitute for ball identity or goal position. Direct visibility of the
   hidden crossing itself is not required by the before/after lane.
2. **Saved shot around 23.68 seconds:** verify #15 across the montage boundary,
   native release/ball path and measured keeper intervention. A shot hint alone
   cannot establish a saved shot.
3. **Assists around 43.19, 49.44 and 56.44 seconds:** follow each passing contact,
   recipient, subsequent shot and certified goal. The 49.44-second reference
   is an assist target; preserve the #7 → #15 → scoring teammate chain. These
   are inspection references, not hard-coded event outputs.
4. **Full acceptance on the same video:** run the entire production path against
   all five reference cases and ensure ordinary negative/competing-ball cases
   still reject. Full five-action acceptance requires 5/5, not the number of
   passed unit tests. Preserve selections and avoid a new upload.
5. **Release validation:** consolidate the draft stack with main, verify current
   CI, measure end-to-end behavior/latency, and test the upload/background/profile/
   complete report flow on iPhone/Safari. Publish/deploy only after original-video
   acceptance and the release checks pass.

No defensible overall completion percentage or completion date follows from
the present evidence. The current bottleneck is physical event verification.
Detailed validation: `docs/evidence/FIX15_R6_TEMPORAL_GOAL_VALIDATION.json`.
