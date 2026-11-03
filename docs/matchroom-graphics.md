# Source-bound Match Room

Skill evidence opens MatchRoomPlayer inside the existing assessment card. One
custom transport owns playback, source-time scrubbing, half speed, automatic
pauses and replay. Supported movement facts appear over the video; detailed
assessment copy appears after the sequence. No quiz changes the report score.

New source reads request up to twelve optional full-frame visual samples per
response in the existing model request. This adds response content, not another
model call or tracker. Coordinates are model observations, not independently
validated tracking. The existing two-source probe and visual checks are recorded below; they
cover one shared sequence, not broad model accuracy.

The canonical adapter rebuilds graphics from the hashed source receipts and
exact action/actor scope. It rejects crops, ambiguous samples, missing source
frames, hidden feet, invalid coordinates and unidentified spare balls. The
asset renderer persists a source/event-bound presentation contract alongside
each evidence clip. Event approval, grading and PDF rendering are unchanged.

Times use source milliseconds. Clip playback adds tele_clip_start; fallback
to the original resets that offset. SVG geometry is fitted to the contained
video rectangle including letterboxing and responsive resizing. Position marks
are shown only within 60ms of an observed source frame: no continuous tracking
or invented animation. Ball-direction arrows join two visible active-ball
samples only within 300ms, with either an explicit static-camera observation or
a supported background-affine transform at every intervening source frame.
These are endpoint displacements, not reconstructed paths or predicted targets.

Old reports without visual samples get the same player and a stop at their
existing evidence timestamp. Historical coordinates cannot be recovered from
text; no paid reanalysis or media rewrite is triggered on opening a report.
Reports without verified skill evidence retain their existing locked/text-only
behavior. A future backfill would require explicit source processing, storage
and evaluation before historical reports can show new position graphics.

Validation: MatchRoomContext.test.jsx, matchRoomModel.test.js, publication.test.jsx;
backend/test_match_room.py and sequence report/pilot/only regressions. CI includes
both new frontend suites and a dedicated Match Room contract job. Browser QA was attempted with a local development fixture and real video,
but could not run: the browser executable download was unavailable. No live
authenticated report playback has been verified.



## Bounded optical tracking bridge (draft)

Asset generation now reuses `player_tracking.track_player` and
`motion_compensation.compute_motion_samples` for presentation only. It uses
original selection hints, at most two 3-second seed windows per displayed event,
and at most eight events in one owned subprocess with a 25-second hard timeout.
No legacy reconstruction or new model calls are used. Timeout/error preserves
sparse graphics and never changes event approval, scores or PDF contents.

Each optical segment must agree with an observed ground position from the same
event. A later contradicting observation rejects the segment. Gaps above 120ms
split segments. Independent seed windows stay separate; the frontend hides
conflicting overlaps. Ground positions are calibrated box proxies, not measured
foot landmarks. The old fixed downward marker offset has been removed.
Player arrows show only existing background-affine-compensated displacement;
failed camera estimates do not produce arrows. Ball arrows retain the original
observed-ball contract; player motion is never reused as ball motion.

Real-source validation on the 7–9.3s sequence used existing Orman600/700 videos,
whose hashes match the prior model receipts. The bounded bridge returned no
accepted segment for Orman600 and only three samples (7.37–7.43s) for Orman700.
The longer Orman700 optical track conflicts with the 9.2s model observation and
is rejected. This is NOT validated continuous coverage and is not rollout-ready.
The old tracker is present but cannot simply be enabled and described as solved.
Further work must improve or reacquire body geometry under independent identity
checks; weakening the disagreement gate is not an acceptable fix.


## Observed displacement at a pause

The optional graphics child now also reuses `estimate_camera` on consecutive
source frames between two same-action observed ground positions, at most 1s
apart. Each intermediate frame must support the background affine transform;
cuts, failed transforms or decode gaps suppress the arrow. The actor-endpoint
horizontal band is excluded from background estimation. The earlier ground
point is transformed into the later camera view. The resulting arrow means
observed endpoint displacement, not the hidden path, instantaneous velocity,
future direction or a ball trajectory.

Source endpoints take precedence over optical box proxies. A dribble/carry may
get one additional automatic pause at the last supported endpoint, without
changing its contact/outcome times. At that pause the arrow stays readable.
Existing factual captions are reused. The continuous optical limitations above
remain; this change does not claim to fix body tracking through every turn.

Local existing-receipt replay produced one endpoint arrow for Orman600 and three
for Orman700. These are the same source sequence with different sample spacing,
not four independent football examples. Runtime was approximately 1.4s per
source for the camera-only pass. A rendered preview demonstrates three pauses
for visual inspection; production adds at most one extra pause per action.
No fresh model requests were made. Sparse/continuous ball tracking is unchanged.


## Fresh instance contours and two-tap path fusion (2026-11-03, draft)

The bounded presentation worker now reuses the existing pinned YOLOv8n-seg
asset through `native_player_segmentation.PersonSegmenter`. This performs local
segmentation inference; it makes no LLM/provider request and does not rerun the
football analysis. Each displayed contour is measured anew. Optical flow is
used only to associate detected instances, never to propagate a display mask.

Two original source selection points, 0.15–2.5 seconds apart inside the action,
start forward/backward paths. At least one path must reach both taps; paths
must agree for at least five consecutive shared frames. A disagreement rejects
the contour result. One supported path may complete the other's missing tail.
Missing/partial/overlapping lower contours split graphics, with no generated
positions across the gap. Nearly identical masks (>85% IoU) are deduplicated
before association; distinct overlapping people remain competing candidates.

The mark's height comes from the bottom visible silhouette; its horizontal
centre spans the visible stance near the ground. It is not a pose estimate or
proof of physical foot contact. Source ground observations may refer to either
boot, so validation checks the visible lower body instead of forcing both boots
onto one coordinate. It never shifts the measured mask to fit the observation.
Marker width is bounded by body height, and ellipse aspect ratio respects the
video geometry. Existing source-observed endpoint arrows still take precedence.
No continuous ball tracking is added.

Processing is limited to one <=3-second window and <=96 decoded frames per
eligible action, with streamed decoding and packed masks. The whole graphics
child retains the 25-second hard wall limit and stops new work before that
limit. Completed event output is checkpointed atomically: timeout preserves
completed sparse/contour graphics, never a partially written track. Missing
assets, insufficient taps, no visual observations or failed association retain
the existing fallback. No guarantee of contours for every action/video is made.

Measured bounded runs on existing source-hash-verified files:

| Input | New contour output | Total graphics time |
| --- | --- | --- |
| Orman600, turn | 66/67 frames, 7.000–9.200s; 7.167s omitted | 14.73s |
| Orman700, same turn | 67/67 frames, 7.000–9.200s | 13.86s |
| Separate attack, 24.3–26.9s | No accepted new contour segment; optical fallback only, 24.47–24.67s | 14.87s |

The second action used original human-confirmed mask endpoints as evaluation
references, not newly fabricated LLM observations. This holdout does not pass
continuous-coverage validation. Keep draft: general coverage, occluded feet,
ball arrows and live authenticated report playback remain unverified. The
turn comparison uses the production frontend data adapter on the actual source
video, rendered as an enlarged side-by-side preview; it is not a live-site test.

Local validation: 26 backend test functions and 14 frontend model tests passed
in direct harnesses (pytest is unavailable in the local runtime). CI includes
the new contour suite for full pytest execution. Regression checks cover
conflicting paths, missing contours, source-observation disagreement, visible
boot changes, packed masks, cuts, absent inputs and timeout checkpoint recovery.


## Seed-view recovery and independent ball arrows (2026-11-03, draft)

Before dense inference, both original source taps are checked in the same fixed
view. If full-width inference misses or ambiguously owns either tap, the worker
tries the union of the original boxes, padded by one maximum body width. Both
taps must be uniquely owned in that view. This does not chase a missing player
or change the optical-flow, competing-instance or two-path agreement gates.
Exact-PTS seed detections are reused in the dense pass. Diagnostic statuses and
ownership/path counts are retained in evidence exports.

The 24.633s attack tap has zero owners in the wide view and one in the focused
view; the second tap has one in both. The resulting first path covers only
24.633–24.967s (11 frames), and the second 26.300–26.900s (19 frames), with zero
shared frames. No contour segment is accepted. Visual inspection shows the
model mixing the selected player's body with a defender during overlap; some
other frames miss the white player completely. The original confirmed mask also
contains mixed-player pixels. Resolving point ownership alone is therefore NOT
a solution to this duel. Tight-crop and existing MobileSAM diagnostic probes
also failed to isolate the player consistently; neither is used to relax gates.
No new model asset, dependency or paid model request is introduced.

Ball displacement now has its own source coordinates, maximum 300ms interval,
method and earlier-frame reference. The same measured camera transform may be
used, but player displacement is never copied to the ball. The actor and ball
endpoint bands are excluded from background estimation. A failed intermediate
camera transform, cut, missing ball endpoint or intervening observation without
a ball prevents an arrow. The frontend checks same-event/source binding and
keeps a valid ball arrow independently of player contours or competing player
tracks. The last supported ball endpoint may add one Ball movement pause.

Real-source rerun: Orman600 remains 66/67 contour frames (15.83s); Orman700
remains 67/67 (16.10s). The attack remains unsupported for continuous contours
(15.23s), with the existing five-frame optical fallback only. These are total
graphics-worker times, not full report processing times.

All nine source ball observations were visually checked against the actual
ball. Only the Orman700 8.200–8.400s interval meets the short-gap requirement.
Its six intermediate background transforms all succeed; an aligned-frame
comparison shows the pitch markings coincide and the ball moves slightly up
and right in the current view. The large raw leftward screen shift is primarily
camera motion. One independent ball endpoint arrow is produced at 8.400s;
Orman600 and the separate attack receive none. This verifies one short interval,
not general ball tracking or hidden trajectories.

Local validation: 30 backend functions and 16 frontend model tests pass in
direct harnesses, plus Python compilation and diff checks. New checks cover
fixed-view ownership, ambiguous taps, deadlines, independent ball/player
direction, camera loss, missing ball observations, source binding, conflicting
player tracks and the additional ball pause. PR remains draft; continuous duel
coverage and live authenticated playback are unresolved.


## Display direction clarification

The player is represented only by the green stance glow. Player-displacement
arrows are no longer rendered, and asset generation no longer adds a pause
solely for a player-displacement arrow. Existing analysis/contact/outcome stops
remain. Arrows are reserved for observed ball movement and supported passes.
The validated 200ms ball displacement is not evidence of an entire pass to a
receiver: longer pass arrows still require source-bound release/arrival evidence.
Earlier preview videos showing a dashed player arrow predate this correction.

## Release-to-reception pass direction

Completed PASS events may now add a distinct BACKGROUND_AFFINE_PASS_ENDPOINTS
arrow. It requires exactly one observed RELEASE within 80ms of canonical contact
and one observed RECEIVED point naming the canonical receiver, inside the same
proof window and no more than two seconds later. Every intermediate camera
estimate must succeed. Old short ball arrows are stripped before this check so
camera failure cannot promote a stale arrow into a pass. The arrow is displayed
at reception, with the release location transformed into that camera view; it
represents endpoint direction, not the hidden trajectory or a prediction.

The existing optional visual-sample instruction now requests these phases;
missing observations still produce no pass arrow. No new provider call is added.
The frontend independently checks release time, phase, receiver, source/event
binding and maximum interval. Player display remains the stance glow only.

A local visual-review fixture uses the existing Orman700 PASS at 9.267s and
visible control after reception at 10.000s. The first touch is partly obscured;
the preview does not assign its exact time. Release was manually annotated from the source image;
reception ball position was measured by the existing local segmenter and visually
reviewed. These annotations are NOT model receipts or written to the report.
The selected actor's reception-frame stance was also checked with local
segmentation. The preview exercises the production camera and frontend adapters.
It validates rendering on that fixture, not automatic extraction on future
uploads. Automatic release/reception extraction and the unresolved duel still
require further source-video validation. Local tests: 32 backend functions and
17 frontend model tests pass, plus compilation and diff checks.

### Paused-frame foreground and pass sequence

Optional local person segmentation now supplies normalized foreground polygons
on measured ball-arrow endpoint frames. Geometry is bound to the existing source,
event, sample frame ID and actual PTS. The player validates geometry and only
uses it while paused within 2ms of that frame. The arrow is omitted if no such
mask is available, rather than painting across people. No single-frame mask is
propagated during playback. Inference stays within the existing 25s child budget;
completed sparse output is checkpointed before optional segmentation.

Completed passes pause at the measured release, play forward on Continue, then
pause at visible reception and reveal a restrained warm-yellow direction arrow.
The reception-view arrow is never projected back onto the release frame. This
is endpoint direction, not measured pitch homography, 3D or a ball trajectory.
The player keeps only a soft green stance ellipse; conflicting tracks now take
precedence over sparse motion marks and hide the stance instead of selecting a
person by confidence. Missing tracked positions are not interpolated.

Local validation: 33 backend functions, 20 frontend model tests. The existing
manual Orman700 review fixture produced nine foreground polygons at 10.000s;
visual inspection confirms occlusion behind white 13 and the coach. This is one
frame, not validation of automatic pass extraction, all-person segmentation or
the unresolved 24.63s duel. Existing reports require regenerated graphics to
receive foreground data. No new paid model request, dependency or model asset.


### Visible stance marker
The stance marker now has a brighter green fill and a thin constant-screen-width
rim. Dense accepted tracks render it during playback as well as at pauses.
The five-sample local median of measured body widths stabilizes marker size;
positions are not smoothed or extrapolated, and identity/gap rejection remains.
A separate review preview measures all 38 source frames from 9.000–10.233s in
Orman700, associating fresh person masks backward/forward from the reviewed
10.000s player. It uses current-frame person occlusion, release/reception pauses
and an uncropped horizontal field view. This manually seeded visual fixture is
not automatic report tracking, and does not fix the separate 24.63s duel.

### Offline duel association review (2026-11-03)

`scripts/matchroom_duel_review.py` is an offline experiment, not a report-worker
import. It combines forward/backward-checked image features, appearance against
both original tap masks, and a bounded motion association to a fresh detection.
Missing detections never become display coordinates. The appearance/motion
thresholds were explored on this clip and are not validated for arbitrary games.

On the 79 original Orman600 frames at 24.300–26.900s, cached YOLOv8m-seg masks
and the unchanged original 24.63/26.57s taps yield paths of 70 and 49 frames.
They share 49 frames without an identity conflict; one reaches both original
selections. Eleven deliberately wrong selections (five alternatives at the first
tap and six at the second) are rejected, including the other white teammate.
Each control rebuilds both appearance references from that control's selections.
These are same-clip controls, not independent validation footage.

The separate playback review draws the 64 available lower-contour positions and
hides the marker on the remaining 15 frames. The source-frame review shows white
10 reacquired after the occlusion. This is not a generated report payload: the
existing observation-per-segment gate still admits only two 20-frame segments
(24.367–25.000s and 26.267–26.900s). Middle segments lack a source observation
under that contract. Full report integration and broader validation remain open.

Selective-inference experiments use the existing nano model in the fixed focused
view plus the larger model on failures. Fresh inference and association for the
full window took 35.086s locally (79 nano frames, 13 larger-model frames; 70/51
path frames, 49 shared, no conflict). Restricting work to the original-tap interval
and spacing larger-model retries reduced this to 23.724s (57 nano frames, nine
larger-model frames; 51/41 path frames, 39 shared, no conflict). Source frames were
already decoded, so neither number is complete report-worker latency. Both are
incompatible with the existing 22s internal deadline once other work is included.
A 15fps trial broke continuity and was rejected. No production asset, dependency,
timeout, observation gate, identity method, ball arrow or event score was changed.

Review model SHA256:
`20877569fcfc4744855b1d6d05b0cd7031987ae31894af5c7e1e74328d18e653`.
Original source SHA256:
`db97b9dc0e2cda68f6c4619405270006e7ab31eeb44e73bd7ed432b1a8d0de38`.
Reproduction accepts explicit local paths for the source, the two original
anchors and the checksum-verified model. `--negative-controls` reruns every
uniquely selectable alternative at each tap. No network or provider call occurs.

### Continuous stance presentation

The approved follow-up preview keeps the ellipse visible by visually interpolating
short missing measurements (up to 200ms), with restrained position smoothing.
These display points are not new source observations. That revised preview is
separate from the earlier research ZIP, which retains the unsmoothed experiment.

The report implementation now interpolates position and width between accepted
contour samples instead of jumping to the nearest sample. Backend segments may
explicitly grant a 200ms presentation gap only while player identity remains
supported in every intervening source frame. Lost identity still splits segments;
independent segments are never joined. Old payloads retain the 75ms contour gap
limit. Measured endpoints and stored coordinates remain unchanged; no ball data is
interpolated. Competing tracks still suppress a conflicting marker. This transfers
the continuous movement behavior, not the offline duel model or its missing-identity
bridges. Full automatic duel integration remains pending.

### Adaptive reacquisition integration

The difficult duel now has a runtime path: a failed normal wide-view tap triggers
the checksum-pinned larger segmenter, adaptive sparse inference and bounded
feature/motion association. Both original taps must resolve and agree with their
source observations. Two independently seeded paths must agree on shared source
frames; a path must reach both exact selections. The frontend requires both
identity-reference frame IDs, matched to the original tap times. Middle stance
samples remain fresh lower contours. Only the display bridges short gaps.

A fresh owned-worker run on the original Orman600 duel completed in 19.554s and
returned one 31-sample segment from 24.633–26.567s. The actual returned payload
passed the frontend adapter and supplied continuous marks at 387 checked display
instants. The integrated associator accepted the correct pair and rejected all
11 wrong-player controls on stored source detections. This is still one duel,
not independent match validation or a live-site playback test.

Distinct clips now receive separate sequential children, each hard-limited to
25s. Repeated report cards for the same event share one result. At most eight
unique clips run, so worst-case graphics time is 200s; earlier clips no longer
consume every later clip's budget. This is a deliberate increase from the old
25s aggregate limit. No paid provider request is added. Total upload latency and
behavior on unrelated matches still require live validation.

The pinned 109,312,538-byte public model is bundled in fourteen checksum-verified
parts. Model reconstruction remains local and atomic; serving performs no model
download. The one-shot bundling workflow only copies the previously tested model
artifact into this draft branch and verifies its exact SHA before committing it.

The two-clip replay (turn, duplicate turn card, duel) completed in 34.371s and
returned both tracks; the duplicate card did not cause another run. The original
turn retained its normal contour method. Details, original source checksum,
worker payload and wrong-player results are in `matchroom-duel-validation.json`.
`scripts/matchroom_tracking_probe.py` replays the actual bounded worker with
explicit source-checked local video, anchors and events. The observations in this
review came from the existing review fixture; it does not establish new automatic
provider extraction, unrelated-match accuracy or live-site behavior.

## Moving ball arrows (supersedes paused-only arrow limitation)

`match_room_ball_playback.py` now supplies an atomic source-frame sequence after
saving the completed player track. Each accepted direction keeps its original
ball release/reception references, transforms both endpoints into every decoded
camera view, and measures fresh visible-person polygons on every frame. A cut,
missing camera transform, missing mask, source gap or exhausted deadline rejects
the complete sequence. Sparse paused arrows remain the fallback. The existing
25s per-event hard limit, eight-event cap and player identity rules are unchanged.
Ball-only events do not require an unrelated player anchor to start the worker.

The production player consumes `requestVideoFrameCallback.mediaTime`, including
the source offset of the selected clip. A synchronous React commit avoids the
one-frame-old mask exposed by real browser playback testing. Timeupdate events
do not overwrite the presented frame. Seeking clears that frame until decode;
opacity is a deterministic function of source time, including a short fade within
the proof after reception. There is no wall-clock CSS animation. Green stance
rendering remains separate from moving ball masks. Offscreen endpoints retain
their camera-projected coordinates; the visible line is clipped to the picture
edge with a direction arrowhead. This does not place the receiver at the edge.

The asset encoder aligns clip zero to an actual decoded source frame and uses
FFmpeg passthrough frame timing. New clips declare `SOURCE_PTS_ALIGNED`.
Unaligned older clips cannot use moving masks; their paused fallback is retained.
A generated VFR fixture verifies preserved missing frames and source timestamps.

The Orman700 review fixture yields 27 complete arrow frames (9.267–10.133s) in
8.072s through the actual owned worker. Its encoded H.264 clip maps to those
source PTS within 0.334ms. The production React component passes real local
Chromium playback, seeking/replay and 0.5x checks using a VP9 copy of the same
pictures (this local browser lacks H.264 decoding). Before the synchronous
commit, this check exposed a consistent one-frame lag; after it, every sampled
moving frame agrees within 2ms. Source fixture, timing and browser measurements
are in `matchroom-ball-playback-validation.json`.

This is runtime integration, not a fresh provider extraction or deployment.
The reviewed ball locations are not fabricated receipts or written to the report.
This pass's existing anchors do not yield an accepted production player segment;
the ball validation does not claim to establish one. The independent approved
fall presentation remains research-only. Existing reports need regenerated
assets. No extra paid call, model asset or runtime dependency was added.
