# FIX32: Edited portrait football footage

The source is a 1080×1920, approximately 60 FPS, 76.76-second highlight montage.
The user reports that playback has been sped up; the editing factor is unknown.
This change uses the existing upload, selected-player taps, temporal reader and
canonical resolver. It does not install SoccerNet/FOOTPASS models or create a
second event authority.

## Changes

1. **Contact details without losing the play.** Keep the existing approximately
   eight source views per second over each bounded window. Add at most 32 actual
   decoded frames around up to four search focuses, targeting 25 FPS locally.
   The total is at most 97 frames. Measured contact proposals are distributed
   over time instead of allowing early list entries to consume the allocation.
   The real source-index map, minimum/maximum gaps and effective sampling rate
   replace the old hard-coded claim that all views are 125 ms apart.
2. **Synchronized portrait views.** A single video contains the entire original
   scene and a letterboxed measured-player detail pane. A detail choice is not
   a target-identity assertion. Both panels have exact native/source-to-canvas
   maps. Ball boxes spanning panels or black letterboxing cannot become source
   measurements. A portrait canvas may encode at up to 1920 pixels per side to
   preserve the original overview resolution. Wide video retains its old view.
3. **References across cuts.** The selected-person gallery remains bound to the
   source video and existing user taps. A nearby usable reference is combined
   with source sharpness, native crop size and visual variation for up to three
   references. No front/back classifier or learned ReID model is claimed. The
   private selection descriptors are not sent to the reader or serialized as
   proof; only the selected actual crops and their hashes supply evidence.
4. **Edited time and scene boundaries.** Native ball search can retain a unique
   sequence despite acceleration in uploaded-media time exceeding the ordinary
   prior. It still requires native camera geometry, bounded displacement/size
   and an unambiguous match. These alternatives remain `SEARCH_ONLY`; fixed
   authoritative ball speed/acceleration limits are unchanged. A scene-ID
   change resets both tracks even when an upstream cut flag is absent. Exported
   motion values explicitly use uploaded-media seconds and do not claim a
   calibrated real-time playing speed. No editing factor is guessed.
5. **A specific missing connection.** Temporal actions supply bounded search
   requests for a missing identity, receiver, shot or outcome. A chain search
   keeps the original contact and later aftermath in the existing decoded
   scene, up to eight seconds, instead of the old fixed 700 ms aftermath. One
   round is retained. A new focused question may reuse the same context frames
   once; the identical completed request cannot open another round. Previously
   observed source clips remain available during feedback resolution and
   resolved full clips do not cause generic identity-only re-reads.

## Offline checks on the actual saved video

The production view/encoding utility was run with network access blocked and
zero model calls. All source timestamps are actual exported PTS. Reference
results and expected jersey numbers are not perception inputs.

| Saved window | Source views | Full-scene views | Player-detail views | Maximum source gap |
| --- | ---: | ---: | ---: | ---: |
| 19.466–25.466 s | 81 | 81 | 62 | 133 ms |
| 25.599–33.599 s | 97 | 97 | 78 | 133 ms |
| 40.332–47.198 s | 88 | 88 | 72 | 134 ms |
| 47.331–52.931 s | 78 | 78 | 49 | 134 ms |
| 53.065–58.931 s | 80 | 80 | 67 | 133 ms |

There are 424 source views, versus 264 in the previous input audit. Detail
sampling can use adjacent original frames (16–17 ms apart); that is not a claim
that the whole window or every contact was sampled at 25 FPS. The encoded
49.448 s frame was visually inspected for full-scene retention, player detail
and source-clock labeling. These are input checks, not fresh action recognition.

## Validation and limits

Regression coverage includes source-clock sampling, both-panel coordinate
round trips, preservation of distant goal pixels, source-reference diversity,
native search without physical-proof promotion, implicit scene changes,
receiver/shot/outcome requests, cut-bounded aftermath and one-round feedback.
The production CI includes the new regressions.

Fresh automatic recognition/approval of the five real actions has not been
established: the configured Emergent SDK/model credentials are unavailable in
this workspace. The existing read-only `--motion-only` review can test that in
the configured project without new uploads/taps or a full physical rerun.

No new full-run latency or provider image-resolution behavior is measured. The
number of initial reader calls is unchanged, but a difficult window has more
frames and portrait inputs have more pixels. Quality and model latency must be
measured together. Actual real-time speed calibration needs a known editing
factor; slowing this rendition cannot recover frames removed by editing.

See [FIX31](fix31-temporal-video-plan.md) for the bounded review command and
the distinction between actual-video recognition and synthetic chain tests.
