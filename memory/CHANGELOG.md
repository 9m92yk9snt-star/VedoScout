
## 2026-06 — FIX09A.1 (branch fix-09a1-tap-independent-global-profile, commit 9b8ddf3)
- Tap-independent GLOBAL_TARGET profile: bounded multi-view prototype bank (A1), two-pass offline re-id (A2), affirmative-positive acceptance with thin negative gallery (A3), top-2 multi-prototype scoring (A4), flip-guard (bank may raise recall, never override tap-profile ordering between concurrent bodies).
- Tests: 50 FIX09A (incl. P01-P09) + 232 FIX00A-06 + 148 FIX07/08 green.
- Real video b1c74fdb: coverage 21.0s->24.8s, 104/104 same-body agreement vs stored run, 0 switches/substitutions. scene_007 remains correctly unresolved: tap-verified body ranks 6th under appearance — acceptance would mis-credit p34.

## 2026-06 — FIX09A.2 (branch fix-09a1-tap-independent-global-profile, commit 6de36ba)
- Decisive-action identity recovery: A2.1 tap-instant local recovery (relaxed nearest-body binding + tap-authority elimination + tap veto), A2.2 physical-exclusion rival pools + labeled predicted continuity fill (proof_eligible=false), A2.3 shape/motion same-kit tiebreak, A2.4 kinematic path hypotheses with edge-safe scale references.
- Safety hardening found during work: _affirmative neg-separation now always full margin; _resume_trim requires per-sample neg-relative separation on non-pinned post-gap resumes (S02 walk-in protection).
- Tests: 70 FIX09A (R01-R10 added) + 232 + 148 green. Real video: coverage 24.8->28.6s (37.3%), 105/105 same-body agreement, 0 switches/substitutions. GT02 63%, GT05 77% (pass contact covered, tap-rooted), GT01 unresolved (genuine ambiguity), GT04 unchanged (target offscreen).
- Known contested: 32.7-34.0s diverges from independent run-1 acceptance (outside GT02 decisive area except 1 point).
