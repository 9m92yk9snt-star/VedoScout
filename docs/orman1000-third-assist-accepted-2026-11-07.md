# Orman1000: third assist accepted from existing model evidence

The owner explicitly accepted the correction on 2026-11-07. The action at
approximately 50 seconds is an **assist by the selected player**, followed by
a different white teammate's finish and a goal. The accepted observed tally is
**1 goal and 3 assists**. Do not describe the football action as awaiting its
first model approval: the prior retained model receipt already approved it.

This is an explicit owner adjudication based on existing model evidence. It is
not a new model run or an independently verified current tracking result.
The unmodified newer model responses still disagree and are retained as such.

## Evidence and scope

- The earlier `native-third-assist-approval-receipt.json` has an intact raw
  response hash and an `APPROVED` direct assist. The selected passer releases
  at 49.715–50.081 s; a different white teammate finishes at 50.331–50.648 s;
  the ball is in the goal by 51.131 s.
- Repeating the source comparison found 13/13 perceptual scene matches. These
  are similar image fingerprints, not identical video bytes or person IDs.
  The fingerprints were also reproduced from the actual current MP4.
- Six common human-selection timestamps have compatible selected-player
  regions. This corroborates the owner's same-player acceptance; it is not
  independently sufficient proof of a finisher's identity.
- The earlier model's `p3` remains scoped to that model response. It is never
  assigned to current `p3`, which denotes a blue opponent. The accepted
  passer-to-teammate relationship is retained as scoped role evidence. No
  current finisher tracking ID or unseen bounding box is invented.
- Exact contact time and kicking foot remain unspecified. The previous model
  and owner disagree about the foot; accepting the assist does not resolve it.

## Corrected report copy

The unpublished analysis and publication copies have been built from the
original uploaded ZIP. Validation confirms:

- 21 canonical events; the other 19 events are unchanged.
- Only the disputed action and the directly dependent running description
  change. The running description no longer says the selected player follows
  his own shot.
- Derived action counts, timeline, Match Room action wording and publication
  show one goal and three assists. Partial coverage remains partial.
- Original contradictory model proof remains intact, with a separate decision
  record. The old own-shot ball arrow is not relabelled as an assist arrow.
- The existing publication engine reproduces the original publication and
  passes its validation on the corrected copy.
- Zero new model calls, zero production writes, no merge and no deployment.

The exact evidence and output hashes are recorded in
[`orman1000-third-assist-owner-accepted-2026-11-07.json`](../testdata/matchroom-completion/orman1000-third-assist-owner-accepted-2026-11-07.json).

Acceptance of this action does not approve a precise finisher overlay, resolve
the separate duel-graphics conflict at 9.4 s, bypass the automatic release
checks, or authorize publishing the whole PR. Those are separate questions.
