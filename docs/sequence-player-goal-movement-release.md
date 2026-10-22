# Player report, goal attribution and movement observations

This release combines the player-facing report copy from PR46 and independent
anatomical-foot evidence from PR49. Existing web cards, styles, PDF page geometry,
scores and academy coaching ranges are preserved. Academy references are skills
guides, not measured academy percentiles or selection predictions.

## Goal review

Existing automatic terminal contact/outcome review requests receive a neutral
goal-attribution instruction: separate the releasing actor, the same active ball
entering the goal and any opponent intervention. A possible brush is not itself
proof of a different scorer; a hidden intervention is not assumed harmless.
Unknown anatomical foot must not block a known scorer. The existing contact,
identity and outcome gates remain authoritative. No model job is added.

This applies the reasoning demonstrated by the PR51 goal-focused experiment to
automatic terminal reviews, while preserving passes and assists in those plays.
The production instruction is adapted to the existing action schema; it is not
a claim that the experiment's exact input was a complete live run. No player,
video, expected timestamp, goal total or expected foot is embedded in runtime.

## Turns and direction changes

Existing observation calls now inspect protective turns and changes of direction
within carries/dribbles. Only SUPPORTED movement annotations with the same action
actor, valid source frames and a before/during/after sequence can enter canonical
events. Publication revalidates the citations and includes them in the source
proof. The existing shared player copy can describe the turn in web and PDF.

These annotations are parts of their existing action, not extra statistical
events or successful take-ons. A later loss does not erase a locally observed
turn. No deception, named trick, opponent beaten, scan or foot is inferred from
a direction change. Five historical experimental observations pass the offline
annotation contract, but none is replayed into a live report. A fresh video must
be observed again. Recognition with this integrated prompt needs the next live
test; earlier experimental accuracy does not prove it will find every movement.

## Evidence and retry

The helper is included in source exports and runtime fingerprints. Old code
checkpoints cannot silently pass as new observations. The unmodified positive
PR51 goal reply and uncertain PR50 reply are retained in
`examples/sequence-goal-focus-regression.json` for offline regressions only.
They still respectively admit one goal and no goal under the resolver.

No experimental paid workflow, prepared image bundle or manual review runner
is introduced by this release. Existing request limits, retry policy and
watchdog remain in force. The earlier native approach extension adds pixels to
existing requests; added evidence/output can affect duration. No new dependency,
paid call, live database write or deployment is performed during integration.
