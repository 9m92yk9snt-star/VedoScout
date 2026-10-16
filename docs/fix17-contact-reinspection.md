# Contact and identity reinspection before a new video analysis

The prior run was blocked before physical verification by a zero-duration scene.
FIX16 removes that scheduling failure while preserving incomplete coverage.
The physical diagnostics also exposed selection gaps: an unassigned native
release had no dedicated identity search, ordinary control gaps could outrank
contacts, and repeated windows from one scene could consume the feedback budget.

## Changes

- A proof-qualified native physical release can request an independent pixel and
  identity inspection before the analysed player's identity has been resolved.
  The request does not declare a shot, goal, assist or shirt number.
- An unresolved contact involving a body already followed by native target
  evidence receives a focused search. The ambiguous contact remains unverified.
- A generic control/ball gap cannot outrank a measured release or a specific
  target-contact gap merely because it already has a target tag.
- The feedback planner visits distinct scenes before revisiting one scene, and
  deduplicates identical actual-PTS frame requests from overlapping windows.
- The default feedback allocation is eight inspections instead of four, with
  the existing hard maximum of eight and one feedback round retained. Explicit
  `FIX13_MAX_FEEDBACK_REVIEWS` settings remain respected. This can increase the
  number of model reads and processing time; the initial inspection budget is
  unchanged.
- Independent shirt-number crops for an involved, measured target body lead
  the queue even when its physical touch is occluded. Native quality, isolation,
  timing, two-frame agreement and number-consensus gates remain unchanged.

Physical contact, ball identity, goal-plane direction, goalkeeper role and the
pass/receiver/scorer chain still decide canonical acceptance. No expected action
count, event outcome or expected shirt number enters the inspection reader.

## Validation and next run

Regression cases cover unknown-actor releases, unqualified releases, target-body
contact ambiguity, ordinary controls, scene fairness, overlap deduplication,
hard budgets, crop priority, malformed target hints and unchanged proof state.
Offline tests make no new model calls. Replaying the planner on stored physical
observations checks selection changes; it does not certify new scoring events.

For the next ScoutMePlay analysis:

1. Merge the tested changes and synchronise that source into the analysis
   environment before the user deploys.
2. Keep the player's explicit shirt number consistent between its field and the
   description. Do not silently rewrite the original export.
3. Confirm supporting vision is enabled and the existing model access is
   configured in that environment; local credentials are not required for the
   user's deployed ScoutMePlay run.
4. Run the video with the user's player taps. Retain physical window traces,
   inspection responses, shirt-number audits, goal/save evidence and final
   canonical events in the export.
5. Evaluate reference actions after the run. A newly selected inspection or a
   model-authored event is not an automatically approved scoring action.

No five-action acceptance PASS or live deployment is claimed by this change.
