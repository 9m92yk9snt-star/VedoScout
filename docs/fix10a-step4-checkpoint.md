# FIX10A Step 4 checkpoint

Behavior-neutral checkpoint used to obtain standalone verification runs after the Step 4 and subsequent fail-closed Step 3 source changes were committed.

Step 4 adds fail-closed contact-role / possession-continuity evidence before strike extraction. A verified physical contact is no longer automatically a physical release when Step 4 has reviewed it. `RECEIVE_CONTROL` and `UNRESOLVED` cannot be promoted to a strike solely because trajectory change is large; explicit `RELEASE` remains eligible. Legacy touches without Step 4 role evidence retain the prior compatibility path.

A later extended reconstruction around 01:10–01:13 exposed a second general issue: `POST_GAP_MEASURED_REACQUISITION` could bridge from a false measured anchor to the next measured ball even when A3 had explicitly emitted `DISCONTINUITY_REJECTED` evidence between those points. Step 3 now fails closed when such contradictory post-anchor trajectory evidence exists. The gate is restricted to the strict interval between the candidate anchor and its proposed outgoing measured point; pre-anchor discontinuity evidence remains allowed so legitimate dormant reacquisition is not suppressed.

## Corrected Golden timeline — authoritative

- **00:23.550–00:25.150:** shot followed by goalkeeper intervention/save evidence; no goal.
- **00:27.200–00:34.000:** the video's only goal sequence: receive → feint → acceleration/separation → right-foot shot → goal. The verified physical final-shot release remains at **00:30.900**.
- **01:09.800–01:13.500:** receive/control followed by a high/long cross-field pass toward a teammate; **not a shot, not an assist-to-goal sequence, and not a goal**. The earlier `#15 -> #10 goal, not #12` fixture interpretation is superseded and must not be used as acceptance truth.

The generic post-anchor discontinuity fix discovered in the last window remains valid because it prevents contradictory trajectory evidence from manufacturing a release regardless of event semantics.

The corrected Golden fixture now treats the 01:09.800–01:13.500 window as `RECEIVE` + `PASS_OR_CROSS`, requires a target physical release in the bounded pass-contact reference range, and explicitly forbids `GOAL_PLANE_CROSSING`. Current physical evidence at 01:10.533 is `VERIFIED RECEIVE_CONTROL`, not a release, so the final pass release remains correctly `UNRESOLVED` until independent physical evidence proves it.

The implementation does not lower A3/A4/Step-3 detector thresholds, does not consume jersey/fixture/canonical-event truth, and remains inside FIX10A shadow evidence.

After correcting the Golden fixture and validator regressions, GitHub Actions FIX10A verification run #98 passed **176/176 FIX10A tests** and **595/595 historical FIX00–FIX09 + unified tests**. The correction changes acceptance truth/tests only; it does not promote FIX10A into canonical authority.
