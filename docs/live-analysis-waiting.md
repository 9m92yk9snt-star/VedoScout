# Live finish estimates and compact waiting room

This change builds on the exact-request retry/failure work in PR #41. It does
not change perception, scoring, PDF layout or model concurrency.

## Finish estimate

Previously, the ETA required five recent matching legacy manifests and an
exact matching pipeline stage. New Sequence runs generally had no eligible
manifest, so the page displayed “Estimate not available yet”.

An active upload now gets an explicitly provisional workload window even
before comparable history exists. Calibration comes from the retained 77s
Orman500 export: approximately 187s initial preparation, 605s source analysis,
178s writing/projection and 39s asset preparation. This is one observed run,
not measured population percentiles or a guaranteed deadline. Video duration
scales the starting workload with a deliberately broad range. The initial
preview is included when the target is a full report.

Sequence runtime persists a small live phase/work summary alongside its
private retry receipts: preparation, source request count/mean observed request
duration, writer, then assets. The status endpoint returns that small summary
and source duration. ETA adjusts after real work returns or a phase changes.
Eligible comparable history remains preferred when available. It is cached,
bounded and optional; database history failure does not block a starting ETA.

The client counts down between polls, shows a local 24-hour finish window and
elapsed time, and uses the same starting calibration before the first status
response. Stale estimates are labelled as the last estimate. An expired window
states that the analysis is taking longer; it does not create a fake five-second
floor, imply completion or keep promising a new deadline without evidence.
No model call is needed to calculate these estimates.

## Tips

Forty short general coaching tips form four sets of ten. Consecutive new
analysis IDs receive different sets, retained in session storage when returning
to a report. Storage denial falls back to page memory. Each set advances every
five seconds with pause and previous/next controls. Hidden tabs do not advance;
reduced-motion users start paused and can explicitly play.

The existing green/lime card gets brighter text, theme-dependent accents,
gentle fades and different schematic football routes. These diagrams illustrate
the general advice and are never presented as findings about the uploaded
player. No player photo is generated or altered.

## Mobile

The existing navigation, video/status card and tips card are retained. The
waiting wrapper uses the dynamic viewport and measures the navigation and
bottom-tab border boxes, including safe-area padding. Compact spacing removes
repeated explanatory lines; a smaller available room also removes the repeated
page heading. No viewport overflow is hidden to pretend that content fits.
An on-demand native video dialog preserves a usable replay despite the smaller
cover. Very short/landscape viewports and accessibility enlargement may scroll
so content and controls remain available.

Local Chromium review uses the real Navigation, MobileBottomTabs and
PremiumBuildingDashboard components with isolated data/auth/API boundaries.
All 40 tips pass bounds checks on 390×664 (with 0/34px bottom safe padding),
375×667 (34px), 390×844 (34px) and 430×932 (34px): no page or horizontal
overflow, no status/tip overlap, and the tip controls stay above the tabs and
inside the card. Rotation was checked at five seconds. This is not an actual
Safari/device or deployed backend/media-delivery test.

Offline tests cover starting estimates, workload updates, expiry, failure,
cache behavior, numeric start clocks, live countdown, distinct tip decks,
rotation/pause, background navigation, video replay/close and readiness gates.
No live analysis/model call, merge or deployment is performed for this review.
