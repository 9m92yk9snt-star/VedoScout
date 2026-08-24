# FIX10A Step 4 checkpoint

Behavior-neutral checkpoint used to obtain standalone verification runs after the Step 4 and subsequent fail-closed Step 3 source changes were committed.

Step 4 adds fail-closed contact-role / possession-continuity evidence before strike extraction. A verified physical contact is no longer automatically a physical release when Step 4 has reviewed it. `RECEIVE_CONTROL` and `UNRESOLVED` cannot be promoted to a strike solely because trajectory change is large; explicit `RELEASE` remains eligible. Legacy touches without Step 4 role evidence retain the prior compatibility path.

A later extended Case-C reconstruction exposed a second general issue: `POST_GAP_MEASURED_REACQUISITION` could bridge from a false measured anchor to the next measured ball even when A3 had explicitly emitted `DISCONTINUITY_REJECTED` evidence between those points. Step 3 now fails closed when such contradictory post-anchor trajectory evidence exists. The gate is restricted to the strict interval between the candidate anchor and its proposed outgoing measured point; pre-anchor discontinuity evidence remains allowed so legitimate dormant reacquisition is not suppressed.

The implementation does not lower A3/A4/Step-3 detector thresholds, does not consume jersey/fixture/canonical-event truth, and remains inside FIX10A shadow evidence.

The Step 4 one-shot verification reported 12 focused Step 4 tests, 173 full FIX10A tests, and 595 historical FIX00–FIX09 + unified tests passing. The post-anchor gate one-shot verification subsequently reported 14 focused short-occlusion tests passing before committing the source and three new regressions. This documentation update intentionally changes no runtime behavior and exists so the normal FIX10A verification workflow can independently validate and package the final committed runtime.
