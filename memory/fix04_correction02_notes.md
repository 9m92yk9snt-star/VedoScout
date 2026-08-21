# FIX04 CORRECTION 02 — learnings (commit bb1f693)

## What was built
- Dual-hypothesis arbitration in `_run_direction` (player_tracking.py ~L330-404):
  - primary accept with stale-velocity risk (prov alive OR displacement > plausible bound)
    is arbitrated vs bounded recovery; two distinct safe candidates => ambiguous (record/learn neither).
  - `jump` now triggers pass-2 recovery (lost/colour/jump); ambiguous/contaminated NEVER recover.
- `_distinct(b1,b2,bw,bh)` + `_provisional_from(...)` helpers in player_tracking.py.
- `SCALE_HYST = 0.02` in tracking_geometry.py: non-unit scale must beat unit scale by margin
  (fixes cumulative noise-driven bbox shrink 36→28.6 that falsely shrank the far-allowance).
- Template learning floor: accepts with mx < CONTAM_MIN (0.55) are recorded but NOT learned
  (prevents blend-poisoned templates during partial occlusion — root cause of G28 regression).
- solid2 floor: recovery verdicts only count as credible hypotheses when best2 mx >= CONTAM_MIN
  (junk background ambiguity must not veto a safe primary — root cause of G12 regression).

## Judgment call (flag for reviewer)
- G13 (symmetric identical-twin crossover): under C02 the honest outcome is fail-closed
  with ambiguity doubt — C01's "resume" was exactly the stale-velocity preference C02 forbids.
  G13 asserts strict no-switch, then accepts EITHER resume OR fail-closed doubt (G31 contract).
- G28 conf>=0.6 template-purity assert scoped to post-separation frames (i>=13); the weak
  blend frame i11 (mx 0.51) is legitimately recorded but never learned.
- _escort_frames shortened to range(15): i15 pushed the target to x=468 (clipped at frame edge).

## Test counts (all green)
FIX04 38 (G1–G32) / FIX03 26 / FIX02 29 / FIX01 29 (pinned call counts) / FIX00B 31 / FIX00A 16 = 169.

## Known pre-existing offline failures (untouched, byte-identical to base)
test_precision_engine.py (2 audio), test_iter94_tele_clips.py (2 media), test_iter95_cv_shadow.py (1 stale summary).
