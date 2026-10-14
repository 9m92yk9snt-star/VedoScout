# R6: bounded ball search and camera-relative association

Continuation of `9a1b05a`, using the unchanged canonical video and all 12
existing user markings. No deployment or merge is authorized by this checkpoint.

## Implemented

`ball_trajectory.py` now retains a separate, bounded search channel alongside
the authoritative trajectory. A linked reserve no longer hides every newly
appearing detector proposal from subsequent search. There are at most three
established and three new search objects. Missing observations are kept only
internally for the existing 180 ms bound, never exported as fresh measurements.

Search associations require unique, reciprocal measured-motion support. Neither
detector confidence nor a nearby player resolves equal competing objects.
Stable search IDs and actual observation counts are diagnostic only: every
search row has `state=SEARCH_ONLY` and `proof_eligible=false`. Search rows cannot
be recycled into a release anchor or promoted automatically into a contact.

Native A3 association now composes the exact measured background transforms.
Camera pan, acceleration, rotation and zoom are removed from association
velocity/acceleration; horizontal and vertical distances use decoded pixel
geometry. Short-gap predictions follow the measured camera. Invalid native
camera chains stay missing, with no screen-coordinate fallback. Legacy traces
without the native camera contract retain their previous selected-path behavior.

Explicit non-proof proposals, synthetic timing and malformed/non-finite
confidence values are rejected. The detector floor, contact thresholds, original
markings, reference labels, event gates and deployment gate are unchanged.

## Verification

- 914 selected local tests in 56 files pass, retaining all previous 879 tests.
- The new synthetic test file has 35 tests. Against unchanged `9a1b05a`, 31 fail
  and four pass. Eighteen failures demonstrate behavior through the unchanged
  public API; thirteen concern the newly added search metadata contract.
- Network, actual SDK and video decode attempts in the unit-test harness: zero.
- The complete bounded native audit re-decoded 1,922 original actual-PTS frames;
  all 1,922 matched the pixel-bound detector cache, with zero new forwards.
- OS-level socket isolation self-test passed; Python network/SDK attempts and
  paid model calls were zero. Audited backend source hashes matched afterward.

| Reference window | Frames | Accepted physical contacts | Search observations | Search tracks |
|---|---:|---:|---:|---:|
| 1 | 354 | 27 | 564 | 193 |
| 2 | 481 | 25 | 806 | 186 |
| 3 | 402 | 23 | 578 | 153 |
| 4 | 333 | 19 | 240 | 55 |
| 5 | 352 | 34 | 547 | 153 |

These counts are not accuracy measurements. A track is a bounded detector-object
search, not a verified match ball. Camera correction changes selected paths;
the new search channel itself cannot change contact authority.

## Remaining work

The strict canonical result remains **0/5 NOT_VERIFIED**. Keeping an alternative
does not yet establish the active ball, target identity, goalkeeper role or
whole-ball goal-plane crossing. No expected label is fed into reconstruction.

Original frames at 19.049238 s and 19.165900 s confirm that the two existing
near-cut markings are before the shot scene, which starts at 19.282562 s.
Their boxes and times were not moved. Any cross-cut identity needs new independent
pixel evidence, not a timestamp adjustment.

Additional free CPU-only checks use local Qwen3-VL weights under the same
OS-level network guard. At this checkpoint, two blind full-width torso reads
independently identify number 15 at 30.865 s and 31.115 s on the same local body.
The unchanged consensus and identity-handoff gates accept that diagnostic
pair with the pre-existing user-stated number. These reads are **not yet applied
to the saved canonical report**, and prove neither a release nor an outcome.
The rest of the bounded reader queue and outcome verification remain work in
progress. No Emergent request or paid model API is used.
