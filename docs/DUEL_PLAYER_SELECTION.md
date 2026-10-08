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

The unified authority preserves exact partial observations without tap authority
or action proof. Red points reject conflicting boxes within 140ms of that tap;
they never describe stationary opponents throughout a scene. No hidden interval
is interpolated into proof. Legacy anchors without hints retain their old path.

## Verification and known limits

163 backend tests passed (selection/routes, tracking, ownership, timeline,
authority/event bridge); all 50 frontend tests passed; 16 tap-policy and 12
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

In the tested ~19.18s sequence, the optical preview remained uncertain on four
subsequent frames. Human correction worked; this is **not** evidence of improved
automatic tracking on those frames. Some QA cutouts fell back to rectangles.
Crowded-duel accuracy still needs representative annotated-video measurement.
iPhone/Safari and live analysis are untested. No merge/deploy or production-data
change. This does not prove recovery of the five missing football actions.
