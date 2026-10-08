# Guided-only player selection

Base: GitHub main `99b75105fd76f95fedeabf4ea09252c8f79a4f68`, tree
`f0dd5311f6041ca8bf1939af400fbb33cdb55a00`.

## Scope

One player-selection editor, up to ten guided taps, then three extra checks.
The existing minimum of three visible guided taps is preserved. There is no
manual fallback, detector-based auto-enrolment, five-anchor confidence preview,
or green/yellow/red confidence gate. Closing exits the studio.

The old `AnchorPreview.jsx` and its obsolete rendering tests are deleted;
`MarkerStudio.jsx` now owns only source lifetime and the upload contract. These
code removals are recoverable through Git history. No runtime/production data,
environment variables, reports, videos or stored anchors are deleted or changed.

## Findings and fixes

- Parent/manual and guided video elements had separate readiness and event
  lifecycles. The parent listeners were not reattached after conditional video
  remounting. The wrapper no longer owns a video. The inline upload preview is
  unmounted while the guided editor is open: one video decoder at a time.
- Guided marks used cached-frame timestamps while showing the live decoder,
  which could still be at another time. Marking now shows the exact captured
  JPEG, not the live decoder. A draft retains that frame object; confirmation
  and payload construction check the binding. Taps are blocked until the still
  image has loaded, while seeking, and during submission.
- Native mobile-sized Chromium reproduced correct `requestVideoFrameCallback`
  PTS arriving with `seeking=true`, `readyState=1`. The old guard discarded that
  sole paused-frame callback, causing timeouts and missing tap frames. The
  helper now retains matching positive PTS evidence and waits for seek/decode
  readiness and two paint cycles. It never treats timeout, old-frame callbacks,
  or `currentTime` alone as success on browsers with frame callbacks.
- Skip/advance formerly used stale state and added one to the confirmed count
  even for skipped or already-confirmed frames. Progress now uses the updated
  map of unique, valid selections. Two selections plus a skip cannot become
  three. Editing a selection replaces the same slot.
- Three extra checks formerly allowed repeated taps at one time and all started
  at the end of the clip. Suggested checks now start at 20%, 50%, 80%; the user
  can scrub freely. Checks must be at least 0.5 seconds apart. The previous
  frame is blocked immediately when a check is confirmed.
- Histogram distances were divided by 24, limiting the maximum to 0.25 below
  the 0.42 scene threshold. Three-channel distance is now normalised to [0,1].
  Hint allocation also covers the end of clips with more scenes than tap slots.
  These are coarse client-side sampling boundaries, not verified match cuts;
  backend identity/event/cut evidence requirements are unchanged.

## User-facing improvements

- Immediate portrait crop of the selected box, lime outline and surrounding
  dimming. This is a rectangular crop, not generated imagery or segmentation.
- Five-times pinch/button zoom, pan, marker movement and resizing; letterbox
  margins are not selectable. Primary controls and resize hit area are at least
  44px. The dialog focuses Close, traps Tab, restores focus and supports Escape.
- `Hidden?` explains not to mark the player in front. Earlier/later buttons move
  by 0.5 seconds within the current sampled scene. The user must confirm the
  player in the newly captured visible frame; moving does not create an anchor.
  Skipping creates no identity evidence. Fully hidden players are never invented.
- The saved upload card shows the selected crop rather than the whole frame.
  Copy describes saved human reference taps, not guaranteed automatic tracking.
- Read failures show Retry; nearby-frame/save failures retain other selections.

## Payload invariants

Native-normalised box coordinates, actual presented PTS, segment and explicit
`verify:true` remain compatible with `UploadPage` and `serializeMarkerAnchors`.
The first normal anchor and marker JPEG belong to the same earliest selected
frame. Extra checks stay separate; verification is not inferred from position.
No model calls, DB writes, R2 operations, analysis endpoints or canonical event
gates have been added/changed by this patch.

## Verification

```sh
cd frontend
CI=true npm test -- --watchAll=false --runInBand
node scripts/check-scout-tap-policy.cjs
node scripts/check-video-frame-authority.cjs
node scripts/audit-analysis-poll.cjs
node scripts/check-report-coverage.cjs
REACT_APP_BACKEND_URL=http://127.0.0.1:8000 npm run build
```

Focused editor/crop/scene tests and the two policy/frame scripts are included in
the existing GitHub frontend verification job. Existing scene-distribution and
spatio-temporal helper regressions are retained. Production dependencies and
package manifests are unchanged. Local npm installation required a transient
AJV v8 hoisting correction in node_modules; no dependency file was modified.

Local results: 43/43 frontend tests, 16/16 tap-policy cases, 12/12 presented-frame
cases, 5/5 analysis-poll cases and 5/5 report-coverage cases passed. The production
build succeeds; remaining lint warnings are in unchanged components. This does
not represent a new run of the backend/model-analysis test suite.

Native local browser check (Chromium 153.0.8010.0, 390x844 touch viewport):

- Uses the existing evidence ZIP's 76.76s canonical web video, not mock video or
  mock frame callbacks. Test coordinates exercise UI plumbing, not player
  recognition. No analysis is started and no model is called.
- All 22 initial scene/hint seeks succeeded after the callback-order fix.
- Ten normal taps plus three distinct checks produce thirteen anchors whose
  timestamps exactly match the displayed still frames.
- Hidden-player navigation moved from PTS 3.83318 to 4.33316, without creating
  a tap. The saved marker JPEG contained 133,295 bytes.
- One video element, successful submission, clean cancel/reopen with zero old
  selections and no runtime page errors were checked.

This does **not** verify iPhone/Safari, production deployment, player identity,
or recovery of the five missing football actions. Those claims require their
own device/live evidence. Neither merge nor deploy is part of this patch.

## iPhone acceptance before production rollout

Use the same video on Safari: open directly into guided selection; pinch/pan,
mark/resize and inspect the crop; use Hidden and skip when still occluded;
complete the normal taps and three checks; save; reopen and cancel. Confirm no
legacy preview appears, controls remain reachable with browser bars/safe areas,
and upload is still possible. Run the live football-analysis test separately
after deployment and inspect its evidence export; this UI fix cannot prove the
five actions on its own.
