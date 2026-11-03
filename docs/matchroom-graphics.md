# Source-bound Match Room

Skill evidence opens MatchRoomPlayer inside the existing assessment card. One
custom transport owns playback, source-time scrubbing, half speed, automatic
pauses and replay. Supported movement facts appear over the video; detailed
assessment copy appears after the sequence. No quiz changes the report score.

New source reads request up to twelve optional full-frame visual samples per
response in the existing model request. This adds response content, not another
model call or tracker. Coordinates are model observations, not independently
validated tracking. No real model evaluation of their visual accuracy has yet
been performed for this feature.

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
