# R6: source-bound motion in the user's circled region

The later selected-mask identity repair and earlier optical search audit are
documented in `FIX15_R6_SELECTED_MASK_BINDING_STATUS.md`.

Continuation of `5d76a82` on `codex-r6-native-jersey-20261011`. This is an
evidence checkpoint, not a detector, identity, or goal-gate change. Strict
five-action acceptance remains **0/5**. No deployment or merge.

## Original source and annotation

The original video has SHA-256
`2774978344f9c54e44f81c2328f3165d3aada4f1b95193964bb22b73a9ecf85b`.
All 12 original USER markings are unchanged. The recovered private source
checkpoint passed ZIP CRC and all 296 member hashes. The Git checkout is the
exact saved `5d76a82499e6f738960b5664284521a7a3887a69` source.

`IMG_9598.jpeg` registers to actual original PTS 31.865 seconds using static
scene pixels, excluding heads and the drawn circle. Static-scene NCC is
0.9900. The circle narrows a search region near native pixel (908.34, 1340.32),
not an event label. The separate reserve object is about 79 native pixels
away. The older isolated proposal at 31.965, normalized x=0.768, is not this
circled feature.

## What the new native-pixel audit measures

The native background affines from the source-bound physical trace align 38
original late-phase frames to a common scene reference. All affine chains
require exact actual PTS, one scene, and no cut or fallback. Original crop
BGR pixel hashes are checked before sampling; no generated details are used.

A fixed grayscale template and a foreground-contrast check yield six local
matches in the circle's anchor segment: 31.849, 31.865, 31.882, 31.899,
31.915, and 31.949 seconds. In this 100 ms interval the feature moves 32
pixels right and 10 down after camera compensation: 33.53 pixels in total.
The fitted median residual is 0.74 pixels. The ambiguous 31.932 match is
not accepted, and the dark background match after 31.949 fails the
foreground-contrast check. Other frame-local matches before the visible
segment are separate hypotheses and cannot bridge the hidden interval.

Sensitivity checks at template radii 8–11 pixels retain the right/down
motion; radius 7 supplies only two matches and is insufficient. A separate
contrast-component centroid calculation at four thresholds also retains
the right/down direction. The two lowest centroid thresholds measure
33.62–34.23 pixels of displacement over the full 100 ms span. The separate
reserve object has 31 local class-32 source observations within the
diagnostic control radius, with median background residual 1.70 pixels.

These are measurements of an image feature, not automatic football or
same-shot identification. Every diagnostic output remains
`SEARCH_ONLY` / `proof_eligible:false`.

## Fresh free native detector check and remaining gap

The unchanged local YOLOv8n ONNX sports-ball detector runs 60 fresh native
forwards on 20 source frames, using 4/6/12-diameter search windows. Model
SHA-256 remains
`013a98f3bc0264a3d793ef29ccbd178ceb0bbb86bc12ff3510273ce85b1c4526`.
Inference runs under the process-level seccomp network guard.

The early probe corroborates the already known 31.182 ball location but
does not extend the verified path. The late probe finds only the separate
reserve object, 78–86 pixels from its search centre; it supplies no class-32
observation on the circled moving feature. Saved search proposals are not
relabelled as proof. No paid model calls or Emergent execution occur.

There are 667 ms between the last verified shot measurement at 31.182 and
the first local moving-feature match at 31.849. The unchanged native
association limit is 80 ms. Being within the separate 900 ms occlusion
review horizon does not certify identity or crossing. A linear continuation
of the pre-segment also does not explain the late position; unseen post/net
deflection or acceleration must not be entered as measured evidence.

Same-shot identity across the hidden interval, independent goal-plane
geometry, and whole-ball crossing remain UNRESOLVED. The new audit
strengthens the search region and rules out treating the moving feature as
the stationary reserve object; it does not change canonical actions.

Private source pixels, six diagnostic scripts, receipts, sensitivity results,
and a source-frame review clip are preserved in
`ScoutMePlay-cirklet-bevaegelsesspor.zip`. Git-backed code is kept only in Git.
No backend files or acceptance gates change in this checkpoint, so the
previous 1,457 offline test passes and 19 SDK-dependent skips remain the
backend baseline rather than a new five-action PASS.
