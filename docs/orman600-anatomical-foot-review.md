# Orman600: anatomical foot follow-up

Actual run: https://github.com/9m92yk9snt-star/VedoScout/actions/runs/39698985235
Experiment code: `9401b1a4206f4cf34e9e786a9bfce4051ee8d3db`.

## Result

The independent model response returns `striking_foot=LEFT` and `assessment=probable`. This supports the user's anatomical explanation, but does not establish an unoccluded boot-ball touch.

The model follows the player's rear-oblique approach using readable white number 10 and no observed half-turn. At 15.767–16.100s it identifies the right leg trailing outward while the left advances toward the ball. At 16.267–16.333s the numbered back remains visible, the left leg occupies the ball-side space, and the other leg is outside the challenge. At 16.633s the outside white-socked leg and bright boot remain down as a probable right bracing leg. The model regards the visible leg continuity, rather than boot colour or image-left alone, as the reason to favor LEFT. Local review of the newly extracted approach frames is compatible with this interpretation; it does not independently resolve the hidden contact.

The tentative late contact window is 16.567–16.700s. This is not an exactly observed boot-ball instant. The strongest alternative remains a defender/goalkeeper touch or deflection in the partly hidden cluster. A right-foot touch by number 10 is less consistent with the outside leg's bracing trajectory but cannot be completely excluded because the hips and ankles overlap late. The evidence must therefore remain probable, not confirmed LEFT. Goal outcome and final scorer attribution were outside this follow-up's scope and are not upgraded by the foot finding.

## New evidence and bounded execution

This was a single additional request authorized by the user's request to continue anatomical clarification. It added genuinely new visual information relative to the previous probe: all 49 original frames from 15.400–17.000s in native 1080x540 full-body bands, including the approach before 16.500s where the previous model saw sparse downscaled overview images. Ten original identity references were included, for 59 images total. The expected left foot, preferred-foot profile, user arrows and previous model conclusion were excluded. The prompt explicitly permitted either side or UNKNOWN and asked for counterevidence.

One actual gpt-6-astra request completed in 81.870 seconds, with no retry. The provider reported 37,380 prompt tokens, 2,532 completion tokens and 39,912 total tokens. It reported 37,248 cached prompt tokens. These are provider-reported usage and model-call duration, not total production analysis time.

Source SHA256: `db97b9dc0e2cda68f6c4619405270006e7ab31eeb44e73bd7ed432b1a8d0de38`.
Bundle SHA256: `186aa35944fb121fa1b3bbc670c2677d517d7f75f6beeed5b1715426bb35523e`.
Request SHA256: `e910872c727434d905205c108e610468d16453c90cd13d2193b6c5c40b1bd9e5`.
Response SHA256: `8d8c6715803903ab26d66a7467162421ea760fb941e0e908b267d07cd9205a98`.

The exact local/CI request audit and image hashes match. The response hash was recomputed and every cited native frame ID exists in the 49-frame input. These checks verify provenance, not anatomical accuracy. The complete raw receipt and response are retained in `docs/examples/orman600-anatomical-foot-receipt.json`.

No live report, statistics, publication logic, layout or model weights changed. No merge or deploy. Do not repeat paid calls merely to obtain a stronger label from these same images.

## Event-parser limitation

The shared runner recorded `validation_error=OBSERVATION_CONTRACT_FAILED` after retaining the completed raw response. This probe deliberately requested `plays=[]` because it asks only for anatomical side, whereas the existing football event parser expects event plays. Therefore no automatic football-event admission was obtained. The foot object was separately parsed as JSON, its LEFT/probable vocabulary checked, and its twelve cited source frame IDs validated against the supplied 49 native frames. This preserves the raw model finding for manual review without relabelling the generic event-parser failure as a passed event contract.
