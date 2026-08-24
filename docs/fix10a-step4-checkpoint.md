# FIX10A Step 4 checkpoint

Behavior-neutral checkpoint used to obtain a standalone verification run after the one-shot Step 4 workflow committed its tested source tree.

Step 4 adds fail-closed contact-role / possession-continuity evidence before strike extraction. A verified physical contact is no longer automatically a physical release when Step 4 has reviewed it. `RECEIVE_CONTROL` and `UNRESOLVED` cannot be promoted to a strike solely because trajectory change is large; explicit `RELEASE` remains eligible. Legacy touches without Step 4 role evidence retain the prior compatibility path.

The implementation does not lower A3/A4/Step-3 detector thresholds, does not consume jersey/fixture/canonical-event truth, and remains inside FIX10A shadow evidence.

The one-shot verification immediately before commit reported 12 focused Step 4 tests, 173 full FIX10A tests, and 595 historical FIX00–FIX09 + unified tests passing. This documentation commit intentionally changes no runtime behavior and exists so the normal FIX10A verification workflow can validate and package the committed Step 4 runtime independently.
