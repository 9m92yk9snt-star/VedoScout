# Orman600 PR49 model evaluation

One actual model request evaluated the unchanged prompt and resolver from PR #49, implementation commit `715e6605348c2ffcc6b490c8c7f28e068c5eb2cf`. This experiment is not merged, does not modify a saved report and is not a full-video benchmark.

## Result

The request completed successfully in **83.753 seconds**. Parsing and the production observation contract passed. Offline replay with the same implementation reproduced the stored resolved result exactly. This establishes request/contract completion, not visual truth or end-to-end production reliability.

The model identifies selected white #10 receiving from white #6, turning and advancing, and attempting a close-range finish while falling. It observes the active ball subsequently in the goal, but leaves the releasing actor and effect of a later opponent clearance attempt unresolved. The shot has `contact_actor_unique=false` and `outcome=UNKNOWN`; the resolver admits no goal and marks the shot ineligible pending contact/outcome clarification.

The model **omits anatomical_foot entirely** on every action. It does not return SUPPORTED LEFT, PROBABLE LEFT or RIGHT in this run. Consequently PR49's anatomical-foot validation yields UNKNOWN. The new supported-foot pathway has therefore **not been positively demonstrated on this real example**. The previous anatomical-only trial's probable LEFT is a separate result and was neither supplied as input nor promoted.

Admitted selected-player packet counts are DRIBBLE 1 and DUEL 1. These are short-window experimental counts, not replacement whole-video statistics.

## Evidence and limitations

- User-located play: 11.267–21.899 seconds, original video SHA256 `db97b9dc0e2cda68f6c4619405270006e7ab31eeb44e73bd7ed432b1a8d0de38`.
- 183 images: original identity references, original spatial context and timeline images; 82 native detail frames over 15.400–18.100 seconds. Preparation uses production `local_half_q50`, crop [0,877,1080,1257].
- The native approach context is 1.2 seconds before the user-located focus. The prompt, observation resolver and source data are from PR49; the window location is supplied manually, so automatic discovery and the complete production follow-up loop are not tested.
- No expected foot, scorer label, user annotation, preferred-foot profile or previous model conclusions were input.
- One request only, no model retry and no report-writer call. 84 seconds is the successful request duration, excluding image preparation, Actions queue/setup, artifact download and review.
- No conclusion here establishes that the user's interpretation is wrong. It establishes that this model run did not automatically substantiate it.
- Next work should inspect why the action-level evidence is absent and whether the delivered crops retain the needed limb continuity. Do not hardcode LEFT or weaken actor/outcome evidence requirements. No further paid calls were made.

## Receipt

- Workflow: https://github.com/9m92yk9snt-star/VedoScout/actions/runs/39703921174
- Experiment commit: `c29193dc5817a5ef3647925b7c46e43017cd5f6b`
- Artifact ID: 12393534402
- Model: gpt-6-astra, medium reasoning, high image detail
- Prompt tokens: 86,449; completion tokens: 5,491; total: 91,940
- Bundle SHA256: `8d6d84ebf5636095eb9f0c55654dbd2971cf8437b03c5ea162a0ba2253231905`
- Request SHA256: `a4dd4603cb1138e24f5b8d21658f42a8a78e4d3978fde4670733954e7f84183f`
- Response SHA256: `a136527a9aa4384b077078df129e52bec84fe630f82de2fcb99734d50e541e02`
- Exact PR49 prompt SHA256: `e402cdf929e30fb66c800d2eb3c4c7795ca15b4f0cbb1700facea5ec371cc3cd`

The complete immutable raw response, resolved events, frame metadata and transport receipt are preserved in [the receipt](examples/orman600-foot-v2-receipt.json). Model assertions remain model observations, not independent confirmation.
