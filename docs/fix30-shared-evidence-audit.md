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
- The production goal-image call reads goalposts and a literal playable-pitch point together. The direction adapter retains that shared coordinate evidence instead of decoding the same frames and making a second model call. Missing pitch visibility stays explicit. Legacy/injected providers retain their previous adapter. The old export contains 27 field-side audit rows with 25 distinct inputs; those extra production reads are no longer needed by the shared reader.
- Contact candidate generation calculates each frame/ball holder once rather than repeating the same whole-player search for every candidate body. Exact source-time frame lookup avoids repeated full-window scans. The cache exists only inside one unchanged calculation.
- Goal-gap search and reappearance validation reuse raw native detector proposals for identical pixels/settings. Proposal-specific ball regions, actor bindings, source PTS and outcome decisions are still evaluated independently. Video changes also clear jersey/role caches.
- Report writing has its own progress stage. The old export spent about 173 seconds there while the UI still said it was reconciling actions.

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

A paired local comparison of contact generation across all 15 saved windows used unchanged JSON, with networking and video decoding blocked. All 35,563 candidate dictionaries were identical and neither input was mutated. This phase took 21.0928 seconds with commit `d3a9ecc` and 8.3971 seconds with the shared holder/frame work (about 60% less time in this phase). This is one local paired measurement, not a production end-to-end benchmark or a new event-accuracy result.

## Validation scope

New regression controls cover appearance without number reads, coarse versus physical cuts, selected-body conflicts, source-bound crops, shared budgets, native search refinement, merged coverage and revisable action attribution. Frontend tests cover source-frame clarity and tap selection.

The controlled offline harness blocks SDK calls, networking and user-video decoding. Server-import cases need the full CI dependencies (local environment lacks bcrypt); synthetic-video cases run separately with decoding restricted to pytest-generated files. The historical API/deployment suite is run in CI with its configured dependencies. PDF QA renders a local copy and checks coverage disclosure, positive observed-count layout, withheld outlook and sequential page numbers; synthetic counts used for layout are not report findings.

Local results: 2,035 core backend cases passed, 28 skipped; the final targeted reconciliation/runtime run passed 84 cases after adding the rebound control. The three generated-video tracking cases passed separately. All 95 frontend tests and the production build passed, along with the polling, coverage, frame-time, tap-policy and bundle checks. Test groups overlap and should not be summed. No external model/network attempt occurred in the controlled suites.

After the shared geometry, native proposal and holder-work follow-up, 393 affected backend cases passed with zero model/network/video-decode attempts. The integration control carries a synthetic complete goal transition from one image-reader response through outcome reconstruction, direction and ball certification without a second geometry reader; it is not a user-video result.

## Continued receiver/scorer and native-work cleanup

- Direct assists and receiver-to-finisher track stitching now use the same event-local team evidence already used by scoring/deflection ownership. An unresolved broad team vote no longer discards the existing body-bound local observation. Repeated copies of a source timestamp do not count as separate observations; explicitly fallback, cut or requested-time rows cannot supply this native evidence.
- Cross-window ball binding accepts the existing verified scoring-control anchor as well as the release anchor, with each source matched to its producer status. A controlled finish can therefore complete the same assist chain on either side of a processing-window boundary. Source, measured-ball and overlap checks remain unchanged.
- Three positive regression cases reproduced the previous rejection: a locally identified teammate, the same teammate after a measured ID split, and a cross-window controlled finish. All three now produce an assist from a complete synthetic scoring chain. Opponents, wrong bodies, missing goal proof and unbound balls do not.
- The saved-JSON replay now reports eight target-team contacts whose broad vote is unresolved but whose event-local body samples are usable (seven broad-label conflicts and one unspecified gap). This supplies team evidence, not missing goal outcomes. The unchanged export still yields no new verified goal/assist.
- Temporal pixel search no longer repeats identical rounded sizes, identical correlation templates or the same crop descriptor. Bidirectional candidate assignment computes its nearest choices once rather than rescanning its sorted pair list. Native descriptor variance is calculated once.
- A paired local comparison used six existing source PNGs with one reference input and with three repeated reference inputs: all 612 proposals across the 12 bounded searches were identical, with unchanged source pixels. The measured phase took 3.4634 seconds before and 2.7618 seconds after. The repeated-input cases deliberately exercise reuse; these figures do not predict full-run savings.
- The existing requirement for a later native detector endpoint is checked before optical-flow decoding, where it already made the resulting flow unusable. Measured release alternatives share successful body/ball flow from the same seed. Failed reads can still retry; no global frame cache or additional image retention is introduced.

The final continued backend sweep passed 1,445 cases with zero SDK, network or video-decode attempts. It covers physical contacts, identity, cross-window evidence, goal/assist reconciliation and native reappearance. Actual decoded cuts also prevent receiver-to-finisher ID stitching, even if a coarse scene label remains the same. These tests include generated pixel arrays; no new external reader response or full video analysis is part of this result.

No deployment, new video upload or live report mutation is part of this change.
