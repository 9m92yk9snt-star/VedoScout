
## 2026-06 — FIX09A.1 (branch fix-09a1-tap-independent-global-profile, commit 9b8ddf3)
- Tap-independent GLOBAL_TARGET profile: bounded multi-view prototype bank (A1), two-pass offline re-id (A2), affirmative-positive acceptance with thin negative gallery (A3), top-2 multi-prototype scoring (A4), flip-guard (bank may raise recall, never override tap-profile ordering between concurrent bodies).
- Tests: 50 FIX09A (incl. P01-P09) + 232 FIX00A-06 + 148 FIX07/08 green.
- Real video b1c74fdb: coverage 21.0s->24.8s, 104/104 same-body agreement vs stored run, 0 switches/substitutions. scene_007 remains correctly unresolved: tap-verified body ranks 6th under appearance — acceptance would mis-credit p34.
