# R6: inspect late visibility without attaching a reserve-ball contact

The subsequent user-circle registration and source-pixel motion audit are in
`FIX15_R6_CIRCLED_FEATURE_MOTION_STATUS.md`. The old isolated 31.965 proposal
described below is not the user's circled feature.

Continuation of `bebc6cc` on `codex-r6-native-jersey-20261011`. Original video,
12 original user markings and the six-point contact-bound shot path are
preserved. The strict five-action result remains **0/5**. No deployment/merge.

## New original-pixel evidence

The two new screenshots register to 31.282 and 31.865 seconds, respectively,
using 746/717 static scene inliers and lower-body pixel comparison. Their
displayed clocks are source-search hints, not proof timestamps or goal labels.
No face identity is used. All source pixels match the existing native cache.

A later touch at 31.782 previously supplied PLAYER_INTERVENTION for the
30.915 target contact despite the selected shot path ending at 31.182. Its
contact ball belongs to another image-space object: 39 independent detector
observations at 31.015–31.782 remain within an 8 px background-compensated
matching radius, with 0.91 px median residual. The six shot-ball measurements
are at least 208 px away when transformed to that same background time.
This is a diagnostic motion/separation audit, not a generic reserve-ball
classifier or a new goal verdict.

## Repairs

For an explicit active-ball-anchor contract, an intervention now requires its
measured ball_before, ball_at_contact and ball_after to match three independent
exact native timestamps/boxes on the selected shot-local path. The anchor
must also occur on that path. Rejected/global contacts cannot use a high
trajectory-change score to claim an intervention of another ball. An earlier
unbound touch does not hide a later genuinely bound deflection. Original touch
evidence is untouched; legacy no-anchor callers retain their previous behavior.

The previous 300 ms sampling burst skipped the late visibility phase. The
same bounded 12-image review now allocates its remaining slots across the
existing 900 ms short-occlusion horizon, preserving contact, active-ball
reference, last measurement and terminal context. No photograph timestamp,
expected outcome or jersey label is embedded in that schedule.

On actual native pixels the loss interval is sampled at 31.182, 31.299,
31.415, 31.532, 31.632, 31.749, 31.865, 31.982 and 32.082. The exact frame
matching the second screenshot is now included, and the first is within 17 ms.
Actual PTS remain deduplicated. Neither sampling nor removing an unbound
contact grants goal-plane or same-ball occlusion proof.

## Validation and limit

30 new intervention-binding cases pass. Against exact `bebc6cc`, 28 fail and
two existing-behavior controls pass. The updated 32 focus cases pass; the old
300 ms sampler fails five of them. Combined focused/legacy validation: 84
passed. Final expanded offline regression: 1,457 passed, 19 SDK-dependent
skipped, zero SDK/network/native-decode attempts in the pure-test harness.

The five-window native replay rebinds all 20 cached blind local jersey reads.
The target's six native shot measurements survive. The unrelated 31.782 touch
no longer yields PLAYER_INTERVENTION: outcome and goal crossing remain
UNRESOLVED. Nothing is automatically upgraded to GOAL or SAVED.

A separate source-only native search covers 38 real frames in the late phase,
using 114 free local detector forwards over whole/left/right field-band crops.
It finds one isolated class-32 proposal near the left-post region at 31.965.
All of these outputs remain SEARCH_ONLY/proof_eligible:false. The proposal
does not establish a reappearance of the same shot ball or a whole-ball
crossing. No saved search proposal is relabelled as proof.

An 86-frame, 10 fps slow-motion review uses every real source frame from
30.765 through 32.182, with actual PTS labels and no generated/interpolated
frames. The original video and markings are unchanged. CI is checked on the
exact saved commit separately; it cannot replace five-action video acceptance.

No Emergent execution, paid model calls, gate relaxation, deployment or merge.
