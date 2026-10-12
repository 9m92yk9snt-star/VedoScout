# R6: inspect the contact-bound ball-path loss

Continuation of `4e200e8` on `codex-r6-native-jersey-20261011`. The original
video and all 12 original markings remain unchanged. Five-action acceptance
is still **0/5**, with no deployment or merge.

## Defect and repair

On the original native video the previous goal reader skipped from 31.115 to
31.565 seconds, across the phase shown in the user's new photograph. Literal
source registration puts the photograph at 31.249 seconds. Its clock and goal
description are evaluation/search context only; neither enters the sampler.

The orchestrator now passes its current contact-bound native shot path to both
normal and feedback goal-provider calls. The adapter validates the exact
contact/anchor binding, measured integer PTS, scene, native dimensions,
confidence, independent time steps and unchanged 80 ms measured-gap bound.
Global paths, rejected seeds, spare balls, search-only/predicted/support rows,
fallback timing and cut/foreign-scene evidence cannot choose a focus.

The bounded 12-image plan retains the contact, exact active-ball reference and
terminal context, then samples six followups every 50 ms after the last native
measurement. Original callers without this validated path retain their prior
sampling. Actual decoded PTS are deduplicated. A separate sampling audit has
no canonical authority; classification and crossing gates are unchanged.

## Tests and actual video

All 32 new cases pass. Against the exact old provider, five focus cases fail
and 27 path-admission controls pass. Initial focused verification passes 50
tests; the expanded serial offline run passes 1,427 with 19 SDK-dependent
skips. The final bounded-terminal edge change and test rename are followed by
34 passing focus/legacy tests. No SDK, network or native decode is attempted
by these pure tests. The new module is compiled by CI and the new test file
belongs to the existing `test_fix10a*.py` CI selection.

Fresh five-window reconstruction rebinds all 20 existing blind local jersey
responses to their current native body/time/pixel hashes. The original report
ZIP is recovered and CRC/hash verified; only its original USER jersey field
is read, with the raw-marker JSON string decoded as 12 entries. Old semantic
observations, contacts and outcomes are excluded.

The first real provider sampling check reads the original pixels at 31.065,
31.115, 31.165, 31.215, 31.265, 31.315 and 31.365 seconds. The closest selected
frame is 16 ms from the registered photograph. Its injected offline recorder
records native source pixels and returns UNRESOLVED, never a synthetic goal
verdict. Socket creation is blocked at OS level and paid SDK entrypoints are
blocked; neither is attempted.

## Fresh native continuation, separate from the sampler repair

A separate local CPU producer re-decodes every original native frame for the
300 ms after the qualified path loss and applies fixed 4/6/12 ball-diameter
search crops. Its centres use the contact-bound camera/motion prediction.
No saved search proposal or expected timestamp/outcome/jersey is supplied.
It performs 54 native detector forwards over 18 source-hash-bound frames.

The unchanged ball selector independently accepts new observations at 31.132
and 31.182 seconds. A second fresh full five-window reconstruction accepts
the six-point path at 30.982, 31.015, 31.032, 31.065, 31.132 and 31.182 seconds.
All original source observations and thresholds remain intact. The resulting
goal-review focus follows the new endpoint: 31.182 through 31.482 every 50 ms.
This native producer is a private reproducible analysis workflow, not a new
automatic production callback in this commit.

The target contact is still classified RECEIVE_CONTROL. No independent
goal-plane geometry or whole-ball crossing is supplied, and the physical
outcome remains PLAYER_INTERVENTION with goal crossing UNRESOLVED. None of the
five expected actions has a qualified canonical event. Keeper reaction and
the human goal description cannot close that gap by themselves.

No Emergent execution, paid model calls, original-marker changes, deployment
or merge. CI success is checked separately on the exact saved commit and is
not five-action video acceptance.
