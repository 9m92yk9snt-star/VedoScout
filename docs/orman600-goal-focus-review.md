# Orman600 goal-focus model evaluation

## Outcome

In this experiment the model and the unchanged PR49 observation resolver **admit one selected-player GOAL** for white #10. The raw answer identifies p1 as the releasing actor and finisher, returns GOAL and contact_actor_unique=true, and asks no unresolved questions. The resolver returns VISIBLE_SHOT_OUTCOME, proof_eligible=true and model_requested_clarification=false. The contact interval is 16.533–16.767 seconds; an exact contact instant is not fabricated.

This is a positive automatic packet-level result. **It is not a production deployment, a saved-report correction or evidence of consistent accuracy across runs.** PR50 with the same images returned uncertainty; the base production prompt alone has not demonstrated stable approval. This experiment adds the explicitly recorded goal-focus instruction and is not an unchanged-production end-to-end run.

## Model's evidence

The source-referenced model explanation attributes the reaching finish to white #10, follows the same moving ball past the goalkeeper, and interprets the later red defender's movement as an unsuccessful clearance after the ball entered the goal. It cites 16.300, 16.533 and 16.767s for identity/release continuity; 16.800, 16.900, 17.000, 17.467 and 18.633s for ball progression; and 16.600, 16.833, 17.000, 17.333 and 17.633s for intervention assessment.

The model specifically asserts that the ball is beyond the goal-line plane by 17.000s. That is a model interpretation of the source perspective, **not a separately calibrated or measured line crossing**. The experiment preserves this assertion unchanged; validation of frame IDs does not independently prove its visual interpretation. Celebration is explicitly excluded as goal proof.

Anatomical striking foot is deferred and is not established by this result.

## Controlled inputs

All 183 images, their bytes and order, and the base PR49 prompt are identical to PR50. A single neutral goal-attribution instruction was appended; its exact text is included in the receipt. No earlier response, expected scorer, preferred foot or user annotation was supplied. The instruction requests separate release, goal-outcome and intervention evidence and permits uncertainty.

The images come from the user-located 11.267–21.899s packet, with native detail 15.400–18.100s. Source video SHA256: db97b9dc0e2cda68f6c4619405270006e7ab31eeb44e73bd7ed432b1a8d0de38.

## Execution and checks

- One actual gpt-6-astra request, medium reasoning, high image detail; no retry or writer request.
- Model request duration: **121.532 seconds**. This excludes queue/setup, source preparation, artifact transfer and review; it is not total full-video analysis time.
- 86,799 prompt tokens; 6,416 completion tokens; 93,215 total tokens.
- API request completed and observation parsing passed.
- Offline replay with the unchanged PR49 resolver reproduced the stored resolved events exactly.
- All supplementary goal-review evidence frame IDs exist in the supplied source manifest.
- Raw-response SHA256 matches the immutable receipt.
- Admitted packet counts: DUEL 2, DRIBBLE 1, GOAL 1. These do not replace whole-video statistics.

Workflow run: https://github.com/9m92yk9snt-star/VedoScout/actions/runs/39707357153
Artifact ID: 12395384211
Experiment commit: 9da8fc3d79a5d0674eda3950b051015c8efdc0e0
Production implementation evaluated: 715e6605348c2ffcc6b490c8c7f28e068c5eb2cf
Bundle SHA256: 8d6d84ebf5636095eb9f0c55654dbd2971cf8437b03c5ea162a0ba2253231905
Focused request SHA256: 22ce92c67e98e99724ce43634dd509bb5ad18548562457c74265ec6049038da6
Raw response SHA256: 67a65ac8d847e32dd4920fb65d8cca20c833d78bb8bb282f3b61913b2e02abc5

The [complete receipt](examples/orman600-goal-focus-receipt.json) preserves the exact focus instruction, raw answer, source metadata, transport details and resolved events. No main-branch code, layout, live statistics or saved report was changed.
