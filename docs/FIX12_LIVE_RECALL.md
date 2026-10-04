# FIX12 live recall investigation and corrections

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

No identity, whole-ball crossing, goalkeeper/save or assist proof thresholds
were lowered. Production code has no fixture event times or special video ID.

## Validation and limits

Each tracking/sampling failure was reproduced by a failing test before its
correction. Added coverage for local team conflicts/barriers and repeated kit
clustering with different process RNG seeds. The small kit fixture contains
only anonymous Lab color pairs: no video, user data, tokens or report payload.

Historical regression: `tests/test_fix*.py` plus
`tests/test_unified_analysis_engine.py`: **925 passed**, five existing
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

The full local identity replay on the original video and recovered taps still
has `reid_failed` in the shot scene and a target gap in the goal scene. Track
changes also remove an earlier unsupported cut re-identification. These are
unresolved acceptance failures, not completed fixes. Local tests cannot replace
the missing independent identity and goal/save evidence.

## Remaining end-to-end acceptance

Use the original video and recovered taps on this branch with the project's
actual model integration. No real model credentials were available locally.
Run all readers and canonical reconciliation afresh; replaying old outcomes
cannot test changed frame sampling. Do not mark this draft ready merely because
unit regressions pass.

| Reference time | Required canonical result | Current new full-run verification |
| --- | --- | --- |
| 23.68 s | target shot, saved | Pending; identity replay still unresolved |
| 30.83 s | target goal | Pending; identity replay still has a gap |
| 43.19 s | target assist with proven teammate goal | Pending independent outcome review |
| 49.44 s | no target assist | Must remain rejected in the new run |
| 56.44 s | target assist with proven teammate goal | Review blocker improved; assist still unverified |

Preserve uncertainty when evidence is insufficient. Further identity recovery
must be based on independent body/jersey evidence rather than expected event
times, spatial proximity or changing another player's identity.
