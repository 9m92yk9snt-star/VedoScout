# Sequence-only production analysis

New full reports, manual retry and interrupted-run recovery use `SEQUENCE_V1`.
The old full-report tracking/discovery/reconstruction/Gemini/cross-verification
orchestrator and its corrective regeneration/identity gates have been deleted
from `server.py`, together with their private model-based evidence generation
functions and runtime imports. Environment flags cannot restore this chain.

Paid uploads prepare source media and retain original player selections, then
start Sequence directly. They no longer spend time on a separate Gemini preview,
identity-profile review, preview verification or corrective preview retry. The
metadata-only initial preview deliberately contains no player claims; the completed
Sequence report remains the source for the assessment. Free-preview entitlements
retain their separate preview product flow.

## Saved reports and failure behavior

- Completed historical reports and existing assets remain readable. This is a
  code change, with no database migration or deletion of reports/uploads/taps.
- Historical bodies with explicit incomplete states fail closed with
  `LEGACY_INCOMPLETE_REPORT_REQUIRES_NEW_SEQUENCE_ANALYSIS`; they cannot resume
  the retired models or become verified solely because a body exists. Reassess
  these through a new Sequence analysis.
- Sequence retry retains source-bound checkpoints, response receipts and safe
  failure diagnostics. Completed source work can be reused when source,
  selections and code signatures still match.
- Sequence asset repair uses the leased full-report worker and the authoritative
  finalization step. Existing URLs are kept until replacement publication succeeds.
  Historical evidence repair returns a conflict before changing saved assets.
- A normal run becomes ready only after Sequence evidence assets succeed.
  Asset/source/model failures never fall back to the retired engine.

Shared deterministic media/timebase, proof-authority and old-document rendering
helpers remain because archived reports still use their data contracts. Standalone
historical reconstruction modules and offline experiments remain as regression
fixtures/tools; the production full-report worker does not import or call their
runtimes. Experimental feint model calls are not added to live analysis.

## Waiting and recovery limits

The worker renews ownership every 45 seconds. Production admission and recovery
now consistently use a three-minute inactivity lease, rather than twenty minutes.
There is at most one automatic interrupted-owner recovery instead of two. The
per-attempt wall-clock watchdog is thirty minutes rather than two hours.
These are failure ceilings, not promised completion times. Actual elapsed time
must be measured on the next deployed run; no new model/video analysis was run
for this cleanup. Existing per-stage Sequence limits and visible live ETA remain.

## Verification

Offline tests exercise the actual server orchestration, source/selection-bound
retry, asset failures, preserved archived bodies, paid preview bypass, and leased
asset repair. Historical assertions that required the deleted orchestration have
been replaced with Sequence retirement/publication boundaries. Deterministic
geometry, scoring authority and media-time tests are retained. The Sequence CI
workflow also runs `test_sequence_only.py`.
