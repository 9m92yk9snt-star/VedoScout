# Human-assisted player selection in duels

Extends `GUIDED_PLAYER_SELECTION.md`. The guided-only 10 + 3 workflow remains;
there is no second editor or confidence-preview screen. At least three fully
visible normal references are required. Partial taps supplement them.

## User flow

Tap, inspect suggested cutout, confirm. Optional `Adjust selection` opens
`Add player part`, `Not my player`, and `Use box instead`. Positive points can
restore visible body parts that the cutout missed. Red points exclude opponents.
A red point inside the rectangle makes the selection partial, including when
a client incorrectly labels it full. All prompts remain bound to actual pixels.

`Hidden / duel?` offers a partial selection or scene-bounded navigation/skip.
Partial selections can link to human-confirmed clear observations 0.5s before
and after. These remain distinct observations; hidden pixels and ball contact
are not invented. Links never create proof between their timestamps.

Optional `Check tracking` captures up to five actual presented frames over
0.5s forward, stopping at the sampled cut/end. The production optical tracker
returns provisional boxes. Five frames loop slowly; this is not full-frame-rate
video or whole-match accuracy validation. Missing boxes are uncertain and
cannot be approved. Correction requires a new human tap; suggestions never
become human anchors. The first normal marker JPEG is fully visible.

Dense backend cut detection can find boundaries missed by the initial coarse
scene samples. Frames at/after that cut return `scene_cut`, not a lost-player
verdict. The editor keeps the selection and explains the cut when fewer than
three pre-cut frames remain; otherwise it trims the loop, correction choices
and approved interval to the pre-cut frames.

Changing the rectangle invalidates its mask, links and tracking approval.
Request cancellation prevents stale-frame results. Confirmation waits for the
cutout request; failures permit the rectangular fallback. Optional controls
stay collapsed in the normal flow. Partial taps cannot count as full references.

## Processing and identity contract

`/api/player-selection/mask` uses the existing authenticated user dependency
and OpenCV GrabCut on a 96x192 crop with human foreground/background points.
This is pixel separation, **not** SAM, semantic person recognition or recovery
of hidden body parts. Similar kits/blur can defeat it; user approval is needed.
The overlay highlights selected pixels; previews/tight identity crops remove
background. Masks are box-relative binary RLE with at most 8192 runs.

`/api/player-selection/tracking-preview` runs the bounded production optical
tracker on 3–5 stills over at most 0.7s. Authentication, encoded-file/decoded-image
limits, timestamp/shape checks and a shared two-job concurrency limit apply.
Both endpoints are ephemeral: no report/file writes, DB/R2 access or LLM calls.
Existing production dependencies suffice.

Upload, persistence and evidence export retain target/include/exclude points,
visibility, mask, human continuity links and optional short-preview approval.
Links are limited to two fully visible confirmed observations per original tap,
at most 0.7s away in the same supplied scene segment. Original tap budgets stay
unchanged; optical seeds are bounded by 16 originals with at most two links each.

Partial boxes are excluded from full-body optical seeds, appearance profiles,
detector-body pins, fingerprints, full-reference prompts and trusted-time score
inputs. Clear linked observations independently seed/reacquire identity.
Full-body masks supply weighted zero-mean NCC, masked colour histograms and
owned identity embeddings; masked templates are never relearned from unsegmented
frames. Wide crops retain separate scene context.
The colour veto applies the same selected-pixel footprint to the reference and
candidate. This avoids comparing a background-free kit to a grass-heavy whole
candidate box. It is matching assistance, not a new ownership mask or proof.
The existing colour, match, geometry and ambiguity thresholds are unchanged.

When the normal masked match is lost, its existing bounded recovery search can
also test small foreground tilts (-15, -7.5, 7.5, 15 degrees). This requires a
usable torso-colour reference and an approved foreground mask. It does not
retry rejected colour, overlap or ambiguity verdicts with a tilt.
The hypotheses use only original selected pixels; premultiplied warping keeps
unselected background out, and clipped hypotheses must retain 90% of support.
All tilt responses share a maximum response map so rivals at other tilts remain
visible to the existing ambiguity and crowding gates. Accepted recovery points
record `matching_method=masked_pose` and `pose_degrees`. No fresh appearance is
learned and no human tap or action evidence is manufactured.

The unified authority preserves exact partial observations without tap authority
or action proof. Red points reject conflicting boxes within 140ms of that tap;
they never describe stationary opponents throughout a scene. No hidden interval
is interpolated into proof. Legacy anchors without hints retain their old path.

## Verification and known limits

177 backend tests passed (selection/routes, masked pose recovery, tracking, ownership, timeline,
authority/event bridge); all 52 frontend tests passed; 16 tap-policy and 12
frame-authority cases passed. Production build succeeds with warnings in
unchanged components. CI includes the isolated selection suite.

Route tests compile production functions/decorators unchanged with a local auth
fixture, avoiding unrelated Mongo/Stripe/LLM startup dependencies. They verify
binding, dependency use, limits and real processing, not live authentication.
Anchor-builder tests execute actual production function bodies; serializer tests
invoke the actual frontend module. Full application integration was not run.

Native Chromium 153.0.8010.0 at 390x844 touch, existing 76.76s canonical video:
real isolated HTTP routes, GrabCut and optical tracking; cutout/body-point
correction, partial/negative-point/nearby-link flow, tracking correction and
submission retain seven original selections (four normal including one partial,
three checks). Zero page errors/model calls. Generic QA taps test plumbing,
not recognition accuracy.

Follow-up inspection of the actual captured JPEGs and tracker rejection trace
corrects the initial diagnosis of the ~19.18s preview: a montage cut at 19.299s
stopped tracking before any candidate search. It was not an occluded-player
failure. Native Chromium now verifies the cut explanation and preserved tap.

A separate same-scene check at 19.683–20.183s exposed the asymmetric colour
comparison. With identical saved JPEGs/mask, zero of four later frames had a
suggestion before the fix; the colour correction restored two. The two remaining
rigid matches scored 0.416 and 0.394 against the unchanged 0.45 match floor.
Bounded foreground tilt recovery raises them to 0.508 and 0.520 and passes all
other gates. All four subsequent frames now have suggestions. Visual inspection
places all four boxes on the same white #15 player. The actual HTTP/mobile-browser
rerun reproduces four of four, with approval enabled and cut handling preserved.

The ordinary `track_player` path also uses recovery: a 2-second local decode
around the same anchor returned nine points over 19.62–20.15s, including three
annotated pose recoveries, in approximately 1.01s here. This is not a claim of
tracking the entire 2-second window. No server/model services were called.
Eleven synthetic pose tests exercise positive/negative tilts, backward tracking,
selected-pixel invariance, clipping, wrong kit, differently tilted rivals,
disappearance, missing torso reference and scene cuts. This short real sample
is **not** a recall benchmark or whole-match validation.
Some QA cutouts fell back to rectangles.
Crowded-duel accuracy still needs representative annotated-video measurement.
iPhone/Safari and live analysis are untested. No merge/deploy or production-data
change. This does not prove recovery of the five missing football actions.
