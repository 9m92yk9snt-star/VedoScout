# Pass-position probe: retained result and next decision — 2026-11-08

## Completed work
GitHub run https://github.com/9m92yk9snt-star/VedoScout/actions/runs/42435432564 completed one real model request on source commit 99259caf3c45875f7e9809a7a344cad04281c9a4. Existing Actions secret was used. Result is retained in result.json; do not repeat this request to recover its output.

Elapsed provider-call time: 89.552 seconds. Input: 26 chronological source frames plus two original selection references (28 images). Usage: 23,864 prompt tokens and 6,330 completion tokens; no dollar cost returned.

Local integrity checks passed: source video SHA, packet SHA, all request-audit fields including image hashes/order, raw-response SHA, and all 26 ordered observation frame IDs. These checks establish provenance, not geometric accuracy.

## What the candidate response adds
10 selected-player ground coordinates, 21 candidate-player ground coordinates, and eight visible-ball coordinates. Two pre-occlusion selected-player anchors: 49.315 and 49.415 seconds. All coordinates remain unverified model candidates.

The distinct background white-player track is called receiver_01 only within this response. The model explicitly does not establish that this person receives the pass. Do not transfer this ID into canonical current or prior player IDs.

## What it does not resolve
Pass release interval: null. Reception interval: null. RECEIVER_AT_CONTACT anchors: zero. The tentative 50.615–50.665 shot interval is not reception evidence and has obscured striker attribution. Never connect the pre-occlusion player position to that outgoing shot as a measured pass.

The accepted third assist and 1-goal/3-assist decision remain unchanged. Geometry uncertainty does not reopen the owner-accepted football classification.

## Next work, without repeating failed trials
Compare the new position candidates against exact source pixels and the retained localization at overlapping times, accounting for their different timestamps. In particular, inspect the model's receiver-side track before and after the overlap at 49.615–49.765; screen movement or a visible boot does not alone establish person continuity.

Resolve the receiver endpoint using visible source evidence and temporal context, separately from subsequent shot motion. A reconstructed illustration must remain explicitly distinct from measured ball trajectory; existing manually estimated preview is not automatic approval. Do not silently merge these candidates into production localization or raise certainty thresholds to force a result.

Do not repeat generic YOLO, football-ONNX, old forward/backward LK seeds, or this identical model packet without new evidence. No new provider call, production modification, merge or deployment was made during retrieval and integrity validation.
