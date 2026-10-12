# R6: preserve selected visible pixels through identity binding

The next source-bound repair finds the missed white body without inheriting
the foreground player's local ID. See
[`FIX15_R6_NATIVE_SELECTED_BODY_STATUS.md`](FIX15_R6_NATIVE_SELECTED_BODY_STATUS.md).

Continuation of `ade1880` on `codex-r6-native-jersey-20261011`. Original video
and all 12 original markings remain unchanged. Five-action video acceptance
is still **0/5**. No deployment, merge, Emergent execution or paid model calls.

## Source-reproduced identity error

At original PTS 50.398 s, the original 50.4 s USER rectangle/point selects the
white player partly hidden behind a blue player. The broad full-frame person
detection is track `p018`, visually belonging to the blue foreground player.
It contains the selected point, but covers only **78.7493%** of the selected
foreground mask. Exact `ade1880` nevertheless returns VERIFIED/p018.

The stored mask was validated in selection metadata but dropped by
`unified_identity_authority._tap_rows` and the USER_TAP canonical row. Dense
and scene-graph consumers therefore treated one containing rectangle as
unambiguous body ownership. The same hazard exists in coarse tap pinning.

## Repair and boundaries

Valid masks now survive on their original USER_TAP authority rows. Body
selection first respects the original point and exclusions, then requires
at least 90% of the mask's actual foreground pixel centres to lie inside a
compatible measured body. Coverage ignores the selection rectangle's
background. The calculation works in normalized or decoded-pixel units.

The shared constraint is used by dense target resolution, scene-graph
target candidates and coarse tap pinning. An incompatible sole body returns
UNRESOLVED/TAP_POINT_BODY_MASK_CONFLICT; two compatible bodies remain
ambiguous. The mask cannot create a detection, invent a local track, defeat
an exclusion, identify a jersey, or grant temporal interpolation authority.
Point-only legacy callers are unchanged. Original masks/points/boxes are not
modified, inferred larger, or transferred to a new selected body.

The source audit reuses exact original physical frame metadata and compares
the actual baseline source with the repaired consumers. The incorrect p018
binding is rejected; the four other available original direct-tap frame
bindings are unchanged, including one legacy maskless tap. The original
anchor-file hash remains
`0a49e85e325cbffb36f2296bad75ebf5051a53e5e8442a534fbe18f172da29ed`.

Four fresh free local person-detector views around the unchanged USER box
find smaller white-player candidates. The two narrow views agree on geometry
covering 100% of selected foreground, with detector confidence 0.345/0.351.
Wider views expose competing bodies. These are SEARCH_ONLY proposals, not
new established local-track continuity or an automatically verified assist.
No detector boxes or events are manually relabelled as proof.

## Earlier shot pixels and validation

A separate fixed native template plus forward/backward optical-flow check
finds a source-aligned search point at 31.199 s, NCC 0.759, with five surviving
features and 0.657 px method disagreement. At 31.215 s the disagreement
exceeds the predeclared 4 px limit and tracking stops. Ten fresh native ball
ROI forwards supply no class-32 corroboration. The six verified shot points
therefore remain unchanged; this is not a seventh proof-eligible measurement.

29 new mask cases are included in the expanded selection CI job. Combined
focused/legacy validation: **63 passed**. Expanded offline regression:
**1,486 passed, 19 SDK-dependent skipped**, one existing Starlette/AnyIO
deprecation warning. Network, actual SDK and video-decode attempts in the
pure harness are all zero. Native source experiments use the existing local
YOLOv8n ONNX model and unchanged confidence thresholds.

Cold process-hygiene runs initially reported lazy child-baseline differences.
The offline harness now initializes Python's standard parent-owned resource
tracker before fixture baselines. No worker lifecycle checks or network/SDK
guards are disabled, and no supporting-vision production code is changed.
The full suite passes through the ordinary harness with that startup fix.

Private source images, ROI receipts, before/after audit and test logs are
preserved in `ScoutMePlay-maskebinding-og-assistkontrol.zip`. Git-backed
code is preserved only in Git. Whole-ball goal crossing and the full
same-player/pass/teammate-goal assist chains remain unverified; this repair
removes a demonstrably wrong body binding rather than claiming event PASS.
