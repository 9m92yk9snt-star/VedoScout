# FIX19 — initial player cutout and behind-mode review candidate

This change continues the saved FIX19 checkpoint on top of tested FIX16–18
without moving PR31 or main. It is not a production deployment or a new
complete match-analysis result.

## Editor and analysis contract

An initial tap requests a local per-person outline automatically. The masked
preview is shown beside the complete selected area. A human reviews the head,
shirt/body, arms and legs before confirming the initial selection. Outline
failure retains the exact frame, box and human point, provides retry, and may
fall back to the full box for a clear view. Legacy colour masks are not accepted
as a new native person-outline response.

`Player is behind` preserves the box, requires an actual visible target point,
and supports marking the foreground first. Hidden anatomy is not generated.
Behind Confirm is disabled until a cutout is available, and the saved anchor
remains partial. Returning to a visible player clears the occlusion hints.
Moving/resizing a box never clamps the human point to a fabricated pixel; a
point outside the new area must be explicitly reselected. Stale replies from
another frame or another tap cannot replace the active selection. Pending
outlines disable Confirm, including during the initial debounce interval.

The existing FIX18 worker continues automatically after initial selection.
There is no new mandatory three-tap page, owner wait, automatic guessed seed or
change to event/identity proof gates. Three clear initial references are still
required; partial/hidden views cannot replace them.

## Segmentation and model package

The CPU instance model proposes a measured person outline rather than just
shirt pixels. Detected sports-ball pixels are removed from body suggestions.
The prompt model requires measured person support and groups red points on the
same measured foreground person. Full-frame foreground prompting was a real
failure mode: the model could prefer grass/background at a high score. Prompts
now use measured person bounds, and the union of supported foreground masks is
removed, including disconnected alternatives. Conflicting points are rejected.

All three checksum-pinned ONNX graphs are included as ordinary binary Git parts
with a manifest. This avoids the connector's 16 MiB request limit. The service
assembles missing graphs locally and atomically and verifies both part and
full-file checksums. There are no runtime downloads or Torch dependencies.
`backend/scripts/package_player_selection_models.py` reproduces the parts from
the verified exports. Source licenses and both model cards are included.

## Validation

- Actual React/Cra selection/waiting tests: **91 passed**, including **34**
  ScoutMode tests for automatic masks, retry, stale replies, manual geometry,
  behind foreground-first selection, returning to visible, and single-flow save.
- Focused backend/real model asset checks: **60 passed**, two dependency
  deprecation warnings. Real CPU sessions load; decoder prompt shapes and
  exact local reconstruction are exercised. Network, remote SDK and video
  decode guards record zero attempts in this focused run.
- Production frontend build: PASS, with six existing unrelated React-hook
  warnings and the existing bundle-size warning. No new ScoutMode lint warning.
- Polling 13, report coverage 5, frame ownership 12 and tap policy 20 scenarios:
  PASS. Browser CommonJS packaging guard: PASS.
- Wider selection suite initially reported 385 passed / 3 blocked: those three
  geometry tests intentionally decode generated local pytest videos, which the
  strict no-video harness forbids. Their fixture-only rerun is recorded in the
  final GitHub review status; do not represent that initial run as 388 passed.

Read-only checks used the existing canonical Orman video and historical taps.
One crowded 15.35-second frame demonstrated the old merged foreground issue.
Explicit visible-part and foreground-part refinements produced a partial
white-player cutout after removal of foreground arms/boots. One point can omit
visible parts; more precise initial hints or a clearer frame may be needed.
High scores and successful unit tests are not proof of perfect separation.
Private user frames and the video are not published in this repository.

## Release boundary

Keep the review draft until GitHub CI passes for the complete package. No merge
or Emergent/live deploy has been performed by this change. After code review,
sync the exact reviewed head to Emergent and let the user deploy through the
established flow. A fresh ScoutMePlay upload with correct number 15 and fresh
initial taps is still needed for complete analysis acceptance. Inspect its PDF
and evidence export against the five reference cases without using those
labels as analysis input. This work has not established five accepted actions.
