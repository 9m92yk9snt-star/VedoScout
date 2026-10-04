# FIX12 live recall investigation and corrections

The later orchestration/review/coverage changes are documented in
[FIX12_ANALYSIS_PIPELINE_FIXES.md](FIX12_ANALYSIS_PIPELINE_FIXES.md).
Real-video acceptance of all five reference actions remains required.

This change fixes reproducible tracking and review defects. It does **not**
establish that the full video now produces the expected scoring events.

## Source and repeatability

- Base: `f051fa11c6d73eccb0e15a643c57b6d7c5f9fccd` (merged FIX11 / PR #20).
- Live report: `5df7c569-b6af-4f93-8b2a-c8c134baf2a6`.
- Evidence ZIP SHA-256:
  `0b1183544931a17c51bcbe54d599134fd2fa224d45e1c80ab058bd5dbb14119c`.
- Downloaded canonical web video SHA-256:
  `5b75f4523af1afe1f95341ac733c02647c8b8c2b1c3a9b08b99993e144e9b333`.
- All 63 manifest entries verified. The 29 trace files represent 15 trace IDs
  with multiple variants; they are not 29 independent windows. The production
  manifest was not available, so no variant is declared authoritative here.
- Recovered all 11 original user-tap times and boxes from persisted
  `USER_TAP` authority fields. Conflicting copies were checked; no taps were
  guessed or recreated manually. This is trace recovery, not a Mongo export.
- Full production canonical documents were unavailable. No production database
  writes, deployment changes, merge or paid model calls were performed.

## Corrections

1. Dense velocity was calculated from prediction error, subtracting previous
   player velocity again. Constant motion could split a track after a bounded
   sampling gap. Calculate measured displacement after camera compensation.
2. Dense camera compensation applied only the most recent camera step to a
   stale measured box after detector misses. Accumulate camera-transformed
   geometry separately; an unknown camera step breaks continuity.
3. Broad identity tracking sorted negative fallback distances in ascending
   order, choosing a farther body first. Rank the nearest admissible body first.
4. Goal review proposed 14 timestamps but kept their first 12, always dropping
   2.2/2.6-second outcome context at the default budget. Keep release, terminal
   context and early crossing frames within the existing budget and window.
5. A failed pooled kit model suppressed valid local evidence. Fit bounded
   direct-user-tap episodes with the existing separation, sample, confidence and
   consistency gates. Conflicting overlapping models do not publish a label.
   Team labels never create target identity. Derived `FIX04` tap flags cannot
   seed these models; a verified body collapse at a real tap can.
6. Random k-means starts changed team availability for identical live inputs.
   Fit deterministic starts on both chroma axes and the principal axis, choosing
   the lowest compactness. No process-wide random seed is set in production.
7. A fully masked embedding zone fell back to the entire crop, reintroducing
   occluder/background pixels as identity features. Keep explicit zone support;
   unavailable zones contribute no similarity, including pooled/relaxed views.
8. Broad identity tracking discarded camera zoom/rotation and used only the
   frame-centre translation. Compose the full similarity transforms across
   misses and transform the last measured rectangle once. An unavailable or
   malformed camera transform cannot masquerade as a static camera. Composing
   transforms also prevents repeated axis-aligned envelope inflation under
   rotation and its inverse.
9. Geometry association ignored a sustained clean kit conflict and could switch
   onto a nearer opponent. A consistent three-sample kit history spanning at
   least 400 ms can reject a clean opposing-kit candidate. Unknown/overlapped
   readings cannot reject it; same-kit evidence never establishes identity.

No identity, whole-ball crossing, goalkeeper/save or assist proof thresholds
were lowered. Production code has no fixture event times or special video ID.

## Validation and limits

Each tracking/sampling failure was reproduced by a failing test before its
correction. Added coverage for local team conflicts/barriers and repeated kit
clustering with different process RNG seeds. The small kit fixture contains
only anonymous Lab color pairs: no video, user data, tokens or report payload.

Historical regression: `tests/test_fix*.py` plus
`tests/test_unified_analysis_engine.py`: **939 passed**, five existing
deprecation warnings. Tests use the CI no-network Emergent stubs and placeholder
configuration; this is not an LLM validation. Local runtime: Python 3.12.14,
OpenCV 5.0.0, NumPy 2.5.3. CI uses its pinned dependencies independently.
Changed Python files pass critical lint checks; `git diff --check` passes.
The unrelated repository-wide lint cleanup was not included.

On the persisted final-window trace, rerunning team inference and rebuilding
touch team relations makes the teammate release at **56,398 ms** eligible for
goal review after the verified target release at **56,148 ms**:
`VERIFIED_TARGET_TEAM_RELEASE_AFTER_TARGET_PASS`, team confidence **0.9072**.
This demonstrates removal of a review blocker, not an accepted assist. Existing
outcome evidence has not been silently upgraded or rewritten.

The fresh full local identity replay at the unchanged production default of
5 Hz, using the original video and recovered taps, still has `reid_failed` in
the shot scene and `ambiguous_duel` around the goal (29,899–32,932 ms). The
49.44-second assist scene also becomes unresolved; this is a recall limitation.
These are unresolved acceptance
failures. Local tests cannot replace independent identity and goal/save evidence.

An exploratory 10 Hz replay initially produced a falsely reassuring target
point: direct image inspection showed the blue opponent in the goal sequence.
After the kit-conflict association correction, inspection at 30,915 ms showed
the white #15 instead. The shot scene remained unresolved. This is diagnostic
evidence for the association defect, not end-to-end PASS. Production sampling
has not been increased: count-based evidence gates need a separate temporal
independence review before any rate change.

## Remaining end-to-end acceptance

The user's clarification on 2026-10-04 supersedes the earlier negative assist
expectation at 49.44 s. The reference chain there is **#7 -> #15 receives and
turns -> #15 passes to #10 -> #10 scores**. Expected totals are **one target
goal, one saved target shot and three target assists**. The player numbers and
chain are user-supplied reference annotations, not newly verified model outputs.
An assist to #15 must not also be counted as a goal scored by #15.
The synthetic reconciliation regression covers an incoming pass followed by
the target's receive/turn/pass and a verified teammate goal at this reference
time. The no-goal-evidence rejection test remains generic; neither test
establishes the live video's missing proof or changes detection thresholds.

Use the original video and recovered taps on this branch with the project's
actual model integration. No real model credentials were available locally.
Run all readers and canonical reconciliation afresh; replaying old outcomes
cannot test changed frame sampling. Do not mark this draft ready merely because
unit regressions pass.

| Reference time | Required canonical result | Current new full-run verification |
| --- | --- | --- |
| 23.68 s | target shot, saved | Pending; identity replay still unresolved |
| 30.83 s | target goal | Pending; default-rate identity replay remains ambiguous |
| 43.19 s | target assist with proven teammate goal | Pending independent outcome review |
| 49.44 s | target assist: #7 -> #15 -> #10 goal | Pending; identity and complete scoring chain unresolved |
| 56.44 s | target assist with proven teammate goal | Review blocker improved; assist still unverified |

Preserve uncertainty when evidence is insufficient. Further identity recovery
must be based on independent body/jersey evidence rather than expected event
times, spatial proximity or changing another player's identity.

## Production manifest obtained on 2026-10-04

The initial investigation above used historical R2 variants. Read-only MongoView
access now confirms the production manifest's **15 exact trace objects**. Only
**one** of those objects matches an uncompressed trace SHA-256 in the initial
29-file ZIP. The latest private evidence ZIP is
`5df7c569-live-authoritative-traces.zip`, SHA-256
`2f6b7e371ac9eb9a8b30b523b330f4e2708aa988ca756af4c1b8c8625ea2a0f7`.
All 15 original gzip lengths and uncompressed SHA-256 values match the live
manifest. It also includes visible canonical/scoring fields captured through
MongoView, not a complete report JSON export. Raw user artifacts remain private
and are not committed to this repository.

The authoritative traces have 56 physical strikes/outcomes and eight target
strikes. Local reconciliation of these saved outcomes still produces zero
proposals. Live Mongo confirms FIX10B ran in production, `no_change`, with zero
proposals/applied/contradictory proposals. The live canonical bundle has eight
accepted events and eight unresolved observations, including SHOT candidates at
28.132 and 36.132 seconds rather than the reference shot/goal times. It has no
verified goals/assists. Missing event candidates cannot be recovered by a
report-display change alone.

### Execution completion versus evidence completion

Previously `verification_complete` only meant that planned recall windows ran
without reconstruction exceptions. Scoring scan then published
`SEMANTIC_AND_PHYSICAL_COMPLETE`, even with missing target identity and outcomes.
The new side-effect-free coverage assessment exposes missing target-frame
identity, unresolved target/eligible teammate outcomes, downstream team barriers,
and missing target outcomes. Opponent-only unresolved outcomes do not create a
target scoring gap. An assessment without decoded frames is `NOT_ASSESSED`.

`physical_recall_execution_complete` retains the old execution signal.
`physical_recall_verification_complete` additionally requires complete assessed
evidence, and `coverage_status` becomes
`SEMANTIC_COMPLETE_PHYSICAL_EVIDENCE_PARTIAL` when semantic execution completed
but physical proof is incomplete. Canonical counts/proof thresholds do not
change. Consumers of the former verification flag must use the new execution
flag if they only need job completion; unknown evidence must not become a claim
that no goals/assists occurred. A COMPLETE assessment is a diagnostic of the
supplied sampled evidence, not a guarantee of full-video detection recall.

On the exact 15 live traces this assessment reports 5,468 decoded-frame
observations, 4,849 identity-gap observations and 11 unresolved target-chain
outcomes. Windows overlap: these are observations, not unique video frames,
missed-event counts, or a measured recall percentage. No new goals, saves or
assists are inferred from these numbers.

This status correction does **not** fix the five event-detection acceptance
failures. Next work remains bounded identity recovery, temporally supported
occluded contact and complete receiver-to-goal lineage, followed by independent
outcome review on the unchanged original video/taps before any deploy.
