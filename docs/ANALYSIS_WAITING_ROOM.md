# Analysis waiting room and completion contract

## Problem and resulting behaviour

An uploaded paid video has two separate results: an initial preview and the
full report. Previously the upload overlay treated `analysis_status=ready`
(preview readiness) as full completion. The report page then showed another
waiting screen. Both screens advanced percentages and remaining-time estimates
from local clocks, including a recurring “5 sec left” estimate. The old report
waiting screen also displayed invented ratings and human scout activity.

Upload now shows measured byte progress, then saving. Once the server accepts
the upload and returns a report ID, the user moves directly to that report's
single waiting room. It follows preparation, analysis, and final checks. The
full report opens only when the server marks it ready and confirms a stored
body. Preview readiness does not complete a paid report.

The waiting room uses the selected player's details and video frame, offers
optional playback of that uploaded video, and rotates general football tips.
Tips have previous, next, and pause controls; reduced-motion preference pauses
automatic rotation. They are labelled separately from the video analysis.

## Server contract

`backend/analysis_progress.py` is a pure, read-only projection of the stored
report. Both `/api/reports/{id}/status` and normal report serialization expose
its fields. Existing owner/admin access checks remain in place.

| Field | Meaning |
| --- | --- |
| `status` / `analysis_status` | Existing preview lifecycle; not full completion |
| `analysis_target` | `full` for a paid/manually unlocked report; otherwise `preview` |
| `preview_ready` | Preview lifecycle ready with a stored preview |
| `analysis_phase` | Actual stored preview/full lifecycle, with bounded fallback for preparation steps |
| `analysis_complete` | Completion for this report's target |
| `full_report_ready` | Stored full body and full lifecycle ready |
| `has_full_report` | Whether a full body exists, including a body still under verification |
| `analysis_started_at` | Stored report creation time, with full start time as fallback |
| `last_progress_at` | Server heartbeat; missing or stale values do not establish activity |
| `full_pipeline_stage` | Existing worker subtask, translated to user-facing descriptions |
| `taps_received` | Number of supplied player marks; not a claim that identity is verified |

An explicit `full_report_status=ready` without a body remains incomplete.
`generating`, `awaiting_confirmation`, `verifying`, `finalizing`, and `failed`
remain incomplete even if a partial body exists. Legacy full bodies without an
explicit lifecycle remain readable. The lightweight status endpoint does not
return the full report body.

## Client contract

`analysisProgress.mjs` supplies one view model for the waiting room, background
tracker, and dashboard report cards. `pollAnalysis.mjs` follows the same
readiness helpers. Elapsed time updates a timer only: it cannot advance a stage,
mark a check complete, invent a percentage, or publish a report.

Only upload byte progress is expressed as a percentage. There is no remaining
time estimate: the current pipeline does not provide a calibrated completion
estimate. The screen explains that duration depends on the video and checks.

Status polling uses a 15-second request timeout and a 4.5-second interval.
Transient network failures retain the current phase and show connection
uncertainty. A fresh changed heartbeat permits runs longer than 20 minutes;
20 minutes without reported progress and the existing two-hour polling ceiling
offer a read-only status check. They do not restart the job. Explicit full-job
failure/start failure is the condition for a retry action. Access failures are
shown separately.

The background tracker skips duplicate requests while its report page is open.
It polls sequentially elsewhere, keeps following a paid report after preview
readiness, and announces full readiness only under the full readiness contract.
Reloading or returning from the dashboard resumes status observation without
starting a second active analysis. The initial upload's backend task continues
to own preview-to-full handoff after identity-profile persistence.

## Production build correction

Browser testing of the actual CRA build exposed a separate failure on opening
the report: `selectionHints.cjs`, `scoutTapPolicy.cjs`, and
`videoFrameAuthority.cjs` had been emitted as media assets. Their imports became
URL strings, causing `validMask is not a function` despite passing Jest tests.

`craco.config.js` now compiles application `.cjs` files as JavaScript and excludes
them from CRA's asset fallback. `scripts/check-browser-cjs.cjs` rejects a built
asset manifest containing `.cjs` assets. This check runs after the CI production
build. Module source and tracking thresholds are unchanged.

## Verification

Local verification on this change:

- 203 backend cases: 26 progress/status cases plus existing selection, masked
  recovery, identity, geometry, and event-bridge regressions.
- 69 frontend cases across six suites, including waiting states, background
  tracking, guided tapping, frame authority, and marked player crops.
- 13 simulated polling scenarios, including a fresh-heartbeat run exceeding
  54 minutes, stale/future heartbeats, network recovery, cancellation, access
  failures, free preview, paid preview, and body withheld until ready.
- Existing frontend report-coverage, presented-frame, and tap-policy checks.
- Production build and the CommonJS asset-manifest guard.
- Real built-app browser flow at 390px mobile and 1280px desktop: guided tap
  modules execute, accepted upload hands off to one waiting room, elapsed time
  does not advance phases, tips/video controls work, reload does not restart,
  disconnection recovers, dashboard navigation resumes observation, partial
  report remains withheld, and ready report opens without uncaught errors.

The browser script intercepts API requests with synthetic fixtures and blocks
external traffic. It does not use a real account, write a production database,
or invoke models. Its screenshot is a coded UI preview with test status data.
It checks routing/build/readiness behaviour, not football recognition accuracy.

Useful commands from the repository root:

```bash
node frontend/scripts/audit-analysis-poll.cjs
node frontend/scripts/check-report-coverage.cjs
node frontend/scripts/check-video-frame-authority.cjs
node frontend/scripts/check-scout-tap-policy.cjs
node frontend/scripts/check-browser-cjs.cjs
```

After a frontend production build, the native browser regression needs
Playwright, Chromium, ffmpeg, and a local test video containing a frame at 25s:

```bash
SCOUT_BROWSER_EXECUTABLE=/path/to/chromium \
SCOUT_TEST_VIDEO_PATH=/path/to/local-test-video.mp4 \
node frontend/scripts/verify-analysis-wait-browser.cjs
```

## Deployment handoff

Synchronize the reviewed GitHub main commit into Emergent's deploy source.
Include `frontend/craco.config.js`, frontend source and scripts, backend source,
docs, and the CI workflow. Preserving only `frontend/src` would miss the
production bundling correction. No dependency changes are needed.

Preserve environment files, credentials, uploads, PDFs, and runtime data. Verify
the copied source against the exact commit, build the frontend, and run the
asset-manifest guard. Deployment remains an operator action. No live analysis
is started by this synchronization; the next live upload validates real worker
status updates and report delivery with the deployed code.
