# Orman600: isolated goal review

Run: https://github.com/9m92yk9snt-star/VedoScout/actions/runs/39684310791
Experiment code: `98be6b47d3519bc68976dd309876422942119057`.

One actual `gpt-6-astra` call completed in 121.387 seconds. This is model-call time, not end-to-end production analysis time. The provider reported 69,101 prompt tokens and 5,945 completion tokens (75,046 total). No retry was sent. The trial used 150 verified source images in the user-located interval 11.267–21.900s, original selection references, and native-pixel contact crops at source cadence around 16.5–18.1s. No user annotations, expected outcome, preferred-foot profile or previous action result was supplied. Source SHA256: `db97b9dc0e2cda68f6c4619405270006e7ab31eeb44e73bd7ed432b1a8d0de38`.

## Actual result

- Selected white number 10 is supported as the initial shooter. The model brackets contact at 16.500–16.767s, cites his continuous approach, reaching action, subsequent fall, and ball departure.
- The same active ball ending inside the goal is supported. The model cites 17.500, 17.700 and 18.133s. Local inspection agrees that the sequence ends with the ball in the goal; it does not resolve every intervening touch.
- Anatomical striking foot remains UNKNOWN. The model cannot trace the partly hidden hip/knee/boot chain reliably and does not confirm the user's left-foot hypothesis.
- The initial ball trajectory being goalbound before the later intervention remains uncertain. A later clearance attempt is visible, but actual contact and whether the whole ball crossed earlier are not isolated. This uncertainty matters to scorer attribution; it cannot be silently converted into a confirmed own goal or dismissed.
- A goalkeeper brush remains uncertain. The model does not classify the goalkeeper's spread alone as a save.

## Model output versus system admission

The raw response emits selected-player SHOT/GOAL for action a5 and `contact_actor_unique=true`. The resolver also creates an event with `event_type=GOAL`, but sets `proof_eligible=false`, because an explicit ACTION-level CONTACT question remains on a5: anatomical foot and possible goalkeeper brush. Consequently the final `target_events` contain only one DRIBBLE, and `counts` do not include GOAL.

This is a diagnostic finding, not automatic goal approval. The generic action-level clarification gate does not distinguish foot metadata from shooter/outcome certainty. A future design should scope uncertainty to the individual claim, while preserving blockers for genuine scorer/trajectory ambiguity. Merely removing this question from the saved response would produce misleading approval and was not done. The independent `initial_shot_goalbound=uncertain` finding also remains material.

## Evidence and limits

`docs/examples/orman600-goal-review-receipt.json` preserves the actual raw response, hashes, usage and resolved admission result. The raw response SHA256 is `8126d29e5566e4b602090b4ae23b84c61e2fa71ab97094105ccb7da437b9dd8d`; it was recomputed and verified. The reconstructed request SHA256 is `e3fdbed8e12bf4e94cc3d6ddd36f63cff62d473a292b3092a33dc3f25267f071` and bundle SHA256 is `c64517ebe089a7dab539f006346018c85b9a32b0daf5e87e2a07148a2b22a797`. Frame citations in the response pass the existing resolver contract. Schema/hash checks are not independent visual proof.

This experiment is a positive observation for the selected player's shot and team goal, with unresolved anatomical side and scorer attribution. It does not establish automatic production approval, general accuracy or model learning. No existing report, live statistics, layout, main branch or deployment was changed. Further paid calls require a new reason and explicit scope; do not rerun this workflow to chase a preferred answer.
