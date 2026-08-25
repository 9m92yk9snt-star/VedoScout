# FIX10A — bounded occluded-goal verification

Status: source implementation committed on `fix10-match-intelligence`.

Source commit under verification: `cbdffb94bc5fbef48cb6202a7ac7f5f160fd5180` (`FIX10A: prove goal crossing through bounded occlusion`).

The one-shot verification runner applied the exact staged patch, compiled the affected modules and ran the complete FIX10A test family successfully: **219 passed**.

The implementation adds a fail-closed bounded occlusion proof lane for goal-plane crossing. It does not lower global A3/A4/Step-3 detector/contact thresholds, does not let celebration or goalkeeper reaction independently assert a goal, and keeps goal proof linked to the target physical release/strike. Contradictory or insufficient evidence remains `UNRESOLVED`/`FAIL`.

This documentation-only commit exists to trigger the ordinary PR verification workflow from a non-bot commit after the one-shot source publish. The normal FIX10A and historical suites remain the acceptance authority.
