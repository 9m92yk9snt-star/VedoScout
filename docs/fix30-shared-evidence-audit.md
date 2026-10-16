# FIX30 — shared evidence processing

Base: main `421525b403c4ca66cedac4c5464c5f4945d68138`.
The saved 76.76-second portrait-video export took 83m13s from creation to readiness; physical reconstruction took about 69 minutes. All changes below were developed from the saved export. No live database or new external model request was used.

## Changes

- The existing action-image reader receives up to three source-bound user-selected crops in the same request. It can compare measured bodies using appearance while the number is hidden. Multiple separated comparisons and a continuous native body track feed the common identity spine and contact graph. Expected shirt numbers and action stories do not establish identity.
- A sparse timeline's cut interval, failed re-identification or target-absence observation can be resolved by fresh measured body evidence. Actual decoded cuts, conflicting selected bodies and user exclusions remain explicit. Unknown legacy barriers remain unresolved.
- Semantic and recall intervals are joined before splitting once. Overlapping grids no longer independently repeat tracking, contact reconstruction and jersey work.
- A single goal-review pool replaces separate identity quotas. Scheduling visits source-time cells across the clip and uses body-bound shot/release search hypotheses. Geometry calls without a usable contact-ball reference are skipped before decoding or spending capacity. Total configured capacity is unchanged.
- Observations sharing a bounded image window share a reader call with each contact focus retained. Changing only an inspection ID does not bypass the input cache. The supporting native detector is reused.
- Rough model ball rectangles select a bounded search area. A uniquely detected smaller ball can be retained without matching the search rectangle's size. Its actual native geometry, contact and temporal evidence still determine the result.
- A later native actor conflict reopens a semantic-only shot attribution instead of preserving a false miss. The original observation remains in the audit. This cannot fabricate an assist or goal.
- Tap suggestions rank clarity in actual source frames within coverage slots. The browser samples more of a short montage and preserves portrait aspect ratio. There is no randomization or previous-video image cache; the same video may still produce the same best frames.
- Deleted decorative PDF/share-image annotation generators. Snapshot labels no longer assign unrelated events to “Hidden Talent” or “Biggest Development Area” by array position. PDF observed goal/assist counts, coverage notes and withheld outlook now match the web report. Score unavailability is explained; page numbering and PDF cache version are corrected.
- Native-cache metrics are persisted. Native preparation and occlusion-search times are recorded, including feedback work.

## Saved-data replay

Run `python backend/scripts/replay_saved_evidence.py /path/to/extracted-evidence`.
It blocks networking and video decoding and does not replay perception. Source SHA-256: `b9e2ba4975ed9dc2497f860a80644711bfd12a2125d9fba6390600b0409ab999`.

| Check | Saved run | Changed plan / reconciliation |
|---|---:|---:|
| Physical windows | 15 | 13 |
| Sum of window durations | 102.531 s | 86.531 s |
| Covered saved actual-PTS timestamps | 4,551 | 4,551 |
| Initial action-image calls / planned packs | 16 | 14 |
| Linked original action observations | 25 | 25 |
| Published semantic miss at 57.2 s | 1 | Reopened actor conflict |

The changed allocation reaches measured contacts at 23.832, 30.915, 42.948, 49.765 and 57.381 seconds using the same total goal-review capacity. The last contact belongs to a downstream finisher. These are inspection opportunities, not five verified target outcomes. Ninety-two saved jobs lack the reference their geometry adapter requires; this is a count of jobs, not avoided paid calls.

A separate bounded local detector comparison used the 16 largest saved model search rectangles in the five relevant windows: the old adapter yielded zero candidates; the changed adapter yielded two, at 27.082 and 27.249 seconds. Both locations were visually checked against the original source. This did not run full video analysis or establish any scoring outcome.

Reconciliation of the unchanged saved traces retains the six other canonical events and reopens the unsupported shot. The saved data still does not prove the requested goal, save and three assists automatically. Changed image packs and appearance comparisons require fresh reader responses before their real-world accuracy can be assessed. Window-work reduction is not a measured wall-clock speedup.

## Validation scope

New regression controls cover appearance without number reads, coarse versus physical cuts, selected-body conflicts, source-bound crops, shared budgets, native search refinement, merged coverage and revisable action attribution. Frontend tests cover source-frame clarity and tap selection.

The controlled offline harness blocks SDK calls, networking and user-video decoding. Server-import cases need the full CI dependencies (local environment lacks bcrypt); synthetic-video cases run separately with decoding restricted to pytest-generated files. The historical API/deployment suite is run in CI with its configured dependencies. PDF QA renders a local copy and checks coverage disclosure, positive observed-count layout, withheld outlook and sequential page numbers; synthetic counts used for layout are not report findings.

Local results: 2,035 core backend cases passed, 28 skipped; the final targeted reconciliation/runtime run passed 84 cases after adding the rebound control. The three generated-video tracking cases passed separately. All 95 frontend tests and the production build passed, along with the polling, coverage, frame-time, tap-policy and bundle checks. Test groups overlap and should not be summed. No external model/network attempt occurred in the controlled suites.

No deployment, new video upload or live report mutation is part of this change.
