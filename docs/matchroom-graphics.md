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
samples only within 300ms and with an explicit static-camera observation. Camera
pans, zooms, cuts and unseen paths do not receive extrapolated arrows.

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
