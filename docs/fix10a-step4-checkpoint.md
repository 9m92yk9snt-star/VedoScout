# FIX10A Step 4 checkpoint

Behavior-neutral checkpoint used to obtain standalone verification runs after the Step 4 and subsequent fail-closed Step 3 source changes were committed.

Step 4 adds fail-closed contact-role / possession-continuity evidence before strike extraction. A verified physical contact is no longer automatically a physical release when Step 4 has reviewed it. `RECEIVE_CONTROL` and `UNRESOLVED` cannot be promoted to a strike solely because trajectory change is large; explicit `RELEASE` remains eligible. Legacy touches without Step 4 role evidence retain the prior compatibility path.

A later extended reconstruction around 01:10–01:13 exposed a second general issue: `POST_GAP_MEASURED_REACQUISITION` could bridge from a false measured anchor to the next measured ball even when A3 had explicitly emitted `DISCONTINUITY_REJECTED` evidence between those points. Step 3 now fails closed when such contradictory post-anchor trajectory evidence exists. The gate is restricted to the strict interval between the candidate anchor and its proposed outgoing measured point; pre-anchor discontinuity evidence remains allowed so legitimate dormant reacquisition is not suppressed.

Golden-ground-truth correction: this 01:10–01:13 sequence is **not a goal or scorer sequence**. User-confirmed raw-video review establishes it as receive/control followed by a high/long cross-field pass toward a teammate, with no goal in that sequence. The earlier `#15 -> #10 goal, not #12` fixture interpretation is superseded and must not be used as acceptance truth. The only goal Golden case in this video is the 00:27–00:33 receive/feint/acceleration/right-foot-shot sequence. The generic post-anchor discontinuity fix remains valid because it prevents contradictory trajectory evidence from manufacturing a release regardless of event semantics.

The corrected Golden fixture now treats the 01:09.800–01:13.500 window as `RECEIVE` + `PASS_OR_CROSS`, requires a target physical release in the bounded pass-contact reference range, and explicitly forbids `GOAL_PLANE_CROSSING`. Current physical evidence at 01:10.533 is `VERIFIED RECEIVE_CONTROL`, not a release, so the final pass release remains correctly `UNRESOLVED` until independent physical evidence proves it.

The implementation does not lower A3/A4/Step-3 detector thresholds, does not consume jersey/fixture/canonical-event truth, and remains inside FIX10A shadow evidence.

The Step 4 one-shot verification reported 12 focused Step 4 tests, 173 full FIX10A tests, and 595 historical FIX00–FIX09 + unified tests passing. The post-anchor gate one-shot verification subsequently reported 14 focused short-occlusion tests passing before committing the source and three new regressions. After correcting the Golden fixture and validator regressions, GitHub Actions FIX10A verification run #98 passed 176/176 FIX10A tests and 595/595 historical FIX00–FIX09 + unified tests. This documentation update changes no runtime authority.
