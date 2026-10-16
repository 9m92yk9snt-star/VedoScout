# FIX22: coordinated evidence rather than contradictory partial decisions

Local review candidate after FIX21 commit `0681fa7`. No merge, deployment,
GitHub upload, paid reader call, new user upload or new tap is part of this work.

## Reproduced failures

Before the changes, the new regression controls reproduced five failing cases
across three mechanisms:

1. A verified physical goal passed alone, but adding an overlapping release
   with UNKNOWN outcome caused both proposals to be marked contradictory.
2. Two windows with measured body/active-ball overlap recorded the same target
   release under different native strike IDs. Unknown-shot recovery counted
   two candidates and recovered neither. The final positive control also
   explicitly binds both contacts to the same measured contact ball.
3. A previous wrong-player rejection was never reconsidered after fresh dense
   evidence correctly identified the observed actor.

These are controlled data/production-function reproductions, not newly proved
goals or assists from the user's video.

## One contact and outcome authority

`reconcile_canonical_events` builds measured overlap contexts once and passes
them to both full physical proposals and partial-shot recovery. Shared release
episodes retain their source context, scene, actual time and body mapping.

Deduplication across windows requires existing measured body AND active-ball
overlap plus matching measured contact balls at the same media timestamp.
Different hypotheses in one native window, unlinked windows, conflicting
contact balls and unrelated scenes remain distinct. Local ID spelling does not
establish correspondence.

UNKNOWN is missing knowledge, not a competing goal/save/assist verdict. It no
longer vetoes a proved outcome. Where a partial observation maps to the exact
proved release, it adds its observation/sequence provenance to that event and
clears its own pending row without downgrading the outcome or adding a count.
Actual contradictory proved ownership/outcomes remain unresolved.

Pending observations are cleared by scene + sequence + action, not a bare local
action ID. A shot recovered in one scene cannot silently clear another a1.

## Revisit decisions when their evidence changes

The canonical resolver declares which identity-dependent decisions are
revisitable. Dense feedback considers those decisions in both unresolved and
rejected rows. Duplicate/replay and non-identity rejections are not reopened.

Feedback reruns the original normalized observations through the actual actor
resolver. Only fresh actual-PTS, non-fallback dense target evidence participates;
the stale coarse identity is not reused as an independent proof source.
Unlinked contexts are evaluated separately so a p001 in one window cannot
borrow a p001 release from another. Conflicting fresh target bodies still block
recovery. Existing decisions, source identifiers and recovery history remain
auditable; repeated processing does not duplicate events or erase history.

A recovered pass or shot still needs the target's verified physical release.
Shot matching shares the existing unique-release interval rather than adding
a narrower, contradictory tolerance. Its timestamp becomes the actual measured
release time; an old model rectangle is not relabeled as a new contact frame.
Recovered outcomes remain UNKNOWN. Only the existing full physical
reconciliation may upgrade them to saved shot, goal or assist.

## Validation and remaining boundary

`backend/tests/test_fix22_evidence_coordination.py` tests the three fixes and
their counterexamples: wrong player/source, duplicate hypotheses, different
contact balls, non-actual frames, real conflicting identities, source-ID reuse,
repeat processing and preservation of proved outcomes. Existing complete
goal/assist/save and true contradiction tests are unchanged.

All 27 new controls pass on the patched implementation. Running the same
controls against the unchanged three production modules from `0681fa7` yields
16 failures and 11 passes. No baseline repository source was edited. The broad
offline selection passes 1,660 tests, with 28 skipped and one existing
python_multipart warning. It records zero attempted network, real SDK or video
decode calls. The new test parameter order was then made explicit to allow
baseline loading without depending on a newly introduced production constant;
all 27 patched controls pass again, with unchanged production code.

A read-only reconciliation replay of all 15 saved native traces makes no
new model or video-decode calls. The saved native-only run still has zero
complete canonical events; the new code does not invent the missing identity,
ball contact, role or goal geometry. The five reference actions remain unproved
by that saved run. It is not a new full online ScoutMePlay analysis.

Receipt: `docs/examples/fix22-saved-reconciliation.json`.
No user footage, raw model responses or private physical traces are committed.
The separate HTTP-server claim test could not collect in this environment
because bcrypt is missing; its assertions and dependencies were not weakened.
