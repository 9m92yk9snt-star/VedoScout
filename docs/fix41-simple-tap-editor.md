# Simple player-selection editor

## User flow

The default mobile view prioritizes the video, a single selected-player crop,
and Save player. Adjust opens four independently draggable corner handles,
centres/enlarges the existing selected region, and exposes optional precise
tools. Picking a different player is explicit; background taps cannot replace a
draft. Opening visibility help no longer discards that draft.

One help panel replaces the overlapping behind/duel controls. A fully hidden
player is skipped, never inferred. A partially visible player keeps the existing
positive/exclusion hints, native cutout requirements and optional nearby human
reference tools. At least three clear references and the ten-reference limit
remain unchanged; the early finish action is prominent once available.

Find moment decodes at most four neighboring source frames on demand and reuses
the displayed frame in a swipeable filmstrip. Each chosen frame uses its actual
presented timestamp; requested or cross-scene timestamps cannot become anchors.
Browsing/cancelling keeps the draft; selecting a different frame requires a new
human tap. No new LLM call, detector pass or automatic identity claim is added.

## Interaction safety

- Locked default box; explicit edit mode, visible target point and four 44px
  corner targets, also adjustable with arrow keys (Shift for larger steps).
- Resizing preserves the opposite edges and clamps to source bounds.
- Moving the box never invents or translates the original positive pixel. If
  that pixel is outside the box, a new visible-body tap is required before save.
- Two-finger zoom/pan and marker gestures cannot turn into accidental taps.
- Native outline requests pause during box dragging and resume after release,
  rather than repeatedly processing intermediate drag positions.
- Existing stale-frame/stale-mask rejection, single-flight submit, partial-player
  rules and final payload format are preserved.

## Verification

All eight frontend test suites pass: 120 tests, including 49 editor controls.
These exercise both original frame/identity safeguards and the new default,
corner, keyboard, accidental-tap, help-preservation and filmstrip behavior.
The existing policy script passes 20 cases; presented-frame authority passes 12;
the production CommonJS bundle check passes. These totals are separate checks,
not a sum of independent football-perception results.

The local optimized production build passes with source maps and the ESLint
webpack plugin disabled in the isolated dependency environment. Browser rendering
was attempted but blocked by the environment's socket permission during Chromium
startup. No mobile screenshot, visual approval or actual iPhone/Safari behavior is
claimed. A real-device visual pass remains outstanding. No merge, deployment,
production analysis or new five-action model verification is performed here.
