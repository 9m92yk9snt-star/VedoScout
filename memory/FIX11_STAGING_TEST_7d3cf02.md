# FIX11 Staging Test — commit 7d3cf02 (read-only, 2026-06)

ISOLATED staging test ONLY. No production DB/report/code/deploy/merge/publish touched.

## Run parameters
- Branch: `fix11-full-video-event-recall`, commit `7d3cf02571aec3f0bbe1e942e4853028361aa32e`
- Source tree: `/root/fix11b/VedoScout-7d3cf02.../backend`
- Staging DB: `fix11b_staging_db`  | Staging report id: `fix11bstg-6be4ba33056d`
- Input reused (read-only) from prod report `9ba44ac0-90da-4321-9015-a90aab15b64e`:
  raw video `tmp/9ba44ac0...mov` (217,604,700 B), marker t=3.84, raw box
  {x:0.3867,y:0.5096,w:0.0826,h:0.116}, 11 raw_marker_anchors + 11 processed anchors, player Orman09 #15.
- Resources confirmed = deployed: 2 vCPU (cpu.max 200000/100000), 8 GB (memory.max 8589934592).
- NOTE: launch command ran twice (timeout retry) → 2 concurrent runs. Killed duplicate
  (pid 561 / report `fix11bstg-87457d0576d7`), kept monitored run `fix11bstg-6be4ba33056d`.

## Headline result vs commit 0274f074 (run #1)
- IndexError FIXED: FIX10A status=`ok`, 15 traces, 10/10 recall windows OK, 0 failed
  (run #1 was `partial` with 3 IndexError in dense_track_refinement). Guard `hypotheses and (...)` works.
- False GOAL @49.2s from run #1 is GONE — now correctly TACKLE WON @48.6 + PASS COMPLETED @49.1.
- Team authority improved but still fails: labeled_detections 0 → 361, but target_median_spread
  still 10.05 → status `partial` reason `UNSTABLE_TARGET_KIT_ANCHOR`.
- Final canonical scoring: 0 goals / 0 assists / 0 shots (8 non-scoring events). staging_validation = FAIL.

## FIX10A physical metrics
traces=15, accepted_contacts=459, touches=482, physical_strikes=54, physical_release_strikes=49,
scoring_control_contacts=5, goal_reviews_requested=10, a7_verified_interventions=44.
FIX10B: no_change, 0 proposals (fail-closed, correct).

## Per-timestamp: PHYSICAL (FIX10A) vs CANONICAL (final)
- ~23.68s SHOT/SAVED: PHYSICAL = target #15 release @23.62s; ball visual crossing VERIFIED (medium conf)
  but whole-ball crossing NOT PROVEN (keeper occlusion) → outcome UNRESOLVED_TERMINAL_VISIBILITY.
  CANONICAL = withheld (INSUFFICIENT_PHYSICAL_IDENTITY_EVIDENCE). Correctly fail-closed, under-detected.
- ~30.83s GOAL: PHYSICAL = releases by NON-target p045@29.27, p069@30.83, p070@32.31; no target in
  causal horizon; no goal-plane crossing. CANONICAL = no goal (target not physically bound here).
- ~43.19s ASSIST: PHYSICAL = target scoring contacts @41.63/43.13, releases @42.41/43.88, AND
  teammate release after target pass VERIFIED @42.88 (VERIFIED_TARGET_TEAM_RELEASE_AFTER_TARGET_PASS)
  = assist chain partially proven; but goal-plane crossing UNRESOLVED (ball stays field-side) → no goal.
  CANONICAL = OFF_BALL_RUN@42.4 + RECEIVE@43.3 accepted; pass unresolved; NO assist.
- ~49.44s (NO assist expected): PHYSICAL = only non-target releases p030@48.41, p046@50.63; target not
  involved. CANONICAL = TACKLE WON + PASS COMPLETED, no scoring. CORRECT (no false positive).
- ~56.44s ASSIST: PHYSICAL = target scoring contacts @55.86/56.40 + release @55.93, crossing VERIFIED
  @55.86 (not proof-ready); downstream teammate releases DOWNSTREAM_RELEASE_TARGET_TEAM_UNVERIFIED.
  CANONICAL = withheld (INSUFFICIENT_PHYSICAL_IDENTITY_EVIDENCE). Under-detected.

## Root blockers (not fabrication — correct fail-closed, but under-recall)
1. Goal-plane whole-ball crossing never PROVEN (proof_ready=False everywhere;
   STRUCTURED_WHOLE_BALL_CROSSING_NOT_PROVEN / ball field-side / keeper occlusion),
   even when visual_audit reports VERIFIED_CROSSING at medium confidence @23.62 and @55.86.
2. UNSTABLE_TARGET_KIT_ANCHOR (spread 10.05) blocks teammate team-verification → assists cannot close.
3. @30.83 goal: target not physically bound to the action (releases attributed to other tracks).

## Handoff artifacts (run #1, still valid for Codex)
- Report-only ZIP: tmp/exports/fix11stg-36e38f07e872-6339daa3.zip
- Canonical web video: tmp/exports/fix11stg-36e38f07e872-canonical-ae88f6f6.web.mp4
