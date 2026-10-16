# FIX21: foundation audit and identity/claim isolation

The saved Orman100 export, original video, eleven historical selections and
completed native diagnostic were inspected without paid model calls, new taps,
production writes, merge or deployment. This is a review candidate stacked after
PR33, not a complete football-accuracy acceptance.

## Confirmed findings and changes

1. **Late evidence promoted an earlier wrong body.** At 30.832 s the completed
   dense trace's GLOBAL_TARGET rectangle covers the red goalkeeper, confirmed
   against the original video pixels. The underlying identity timeline labels
   track p25 at 30.765 and 30.982 s proof-eligible with enriched similarities
   0.183 and 0.163. Its higher similarities occur later, after a 1.083 s gap.
   Tracks were split using the base identity profile, but not split again when
   the frozen multi-view bank changed the identity evidence. Top-three later
   matches could therefore promote the earlier wrong prefix. Split again using
   the enriched profile before pass-two chaining, and remap taps to their actual
   surviving sample/fragment. Do not copy a tap to every split fragment.
2. **An arbitrarily distant future tap bypassed resume checks.** `_resume_trim`
   used only a lower time bound. Bound the tap exemption to +/-600 ms. This does
   not require a tap at each action or disable other automatic re-identification.
3. **Fusion could cross a cut.** `_nearest` compared timestamps within 140 ms
   without rejecting known different scene IDs. Both fusion directions now
   exclude evidence from a different known scene. Unknown legacy scene metadata
   keeps its existing compatibility behavior; this is not new identity proof.
4. **Dense continuity could override explicit identity conflict.** A neighboring
   exact seed could promote `UNRESOLVED_IDENTITY`/source-conflict frames on the
   same local body track. Explicit conflict/selection/cut barriers now terminate
   propagation. Missing geometry alone remains eligible for bounded recovery.
5. **One supported report clause authorized other unsupported clauses.** The
   report guard returned immediately on an assist or save mention. It now checks
   every recognized outcome in the sentence. Explicit English numeric/one-to-ten
   goal/assist counts, including common adjectives such as “well-taken”, must
   not exceed the relevant verified ledger. This lexical guard is bounded; it
   does not claim to understand every possible paraphrase or language.

## Why the readers disagree

Five historical Gemini responses are present in the export. They are observations,
not five independent physical proofs. They refer to the same source-video hash;
this inspection found no different-source-video hash explaining the discrepancy.
The saved responses classify the approximately 23 s shooting sequence as a goal;
around 57 s one describes a goal and another a save. The exported final report
claims two goals in prose while its verified statistics list zero and COMPLETE
coverage, and it has no `report_fact_authority` metadata. This is a historical
report, not a newly generated report with FIX16-21 applied.

Models must be allowed to disagree as observations. Forcing agreement or taking a
majority would hide errors. They must not independently own target identity or
published totals. Existing unified identity, canonical reconciliation and report
fact authority are the intended shared chain; the leaks above broke that contract.
Role, ball continuity, goal geometry and actor evidence must reference the same
source, actual media time, scene and locally scoped track before reconciliation.

## What still blocks the five actions

The completed native-only diagnostic has no accepted target strike within +/-1 s
of any reference. Around 23.68, 43.19 and 49.44 s, none of the 120 distinct nearby
frames establishes the target. Most reasons are SCENE_CUT. Around 30.83 s, the
apparently verified player was the goalkeeper. Around 56.44 s there is partial
identity coverage, but the nearby scoring-contact candidates belong to other
tracks and are classified RECEIVE_CONTROL, not a verified target release.

All nearby outcomes report GOAL_GEOMETRY_UNAVAILABLE. Semantic action, jersey,
role and goal readers were disabled in this diagnostic. Missing geometry in this
run is therefore an unavailable evidence source, not proof that a goal did not
occur. Without a target release, the bounded goal-review scheduler also reports
NO_PRIOR_TARGET_RELEASE_IN_CAUSAL_HORIZON. Weakening that gate would allow unrelated
players to spend the review budget and inherit the target's actions.

## Measured validation

- A local capture with sockets blocked decoded the existing original video once
  to retain the identity observations/references. Its baseline target points and
  scene list match the previous saved diagnostic exactly (145 points).
- Deterministic replay of those same observations after the identity change
  produces 135 points and removes the erroneous goalkeeper prefix. No point is
  emitted between 30.000 and 31.300 s. Under the shared authority query, 30.982 s
  changes from proof-eligible OK_EXACT to TARGET_GAP. This prevents a false
  attribution; it does not yet find the correct shooter or prove the goal.
- 286 focused regressions pass, including new formerly failing cases for the
  profile-prefix error, future tap exemption, cross-cut fusion, dense conflict
  override, mixed report claims and overcounted goals. Existing identity,
  canonical output, contact/role handoff and reconciliation tests are included.
- The offline harness records zero network, SDK or video-decode attempts in the
  regression suite. The separate identity capture used local video decoding;
  it made no remote call. Existing python_multipart deprecation warning remains.
- Measurements and private-artifact hashes:
  `docs/examples/fix21-foundation-replay.json`. User video, images, full traces,
  raw model responses and captured embeddings are not committed.

## Remaining work and acceptance

This audit has found and repaired specific foundation defects, not established
that every defect is known. No new complete physical reconstruction or complete
online analysis was run. No new five-action acceptance is claimed.

Next: automatically recover the target in each affected scene from the saved
initial references; validate its body through the real contact frames; then
inspect the same active ball, receiver, scorer and post-occlusion goal sequence.
Use existing saved evidence first. If a required observation is absent, record
that exact missing field and window; do not replace it with the expected label.
The five user reference labels remain post-hoc QA, never reconstruction inputs.
Do not ask the user to upload or retap to reproduce these known defects.
