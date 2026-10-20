# Shared publication of Sequence reports

`report_publication.publish_report` is a pure, read-only projection used by the
report API, PDF builder, snapshot sharing and evidence export. It applies to
`SEQUENCE_V1`; legacy report contracts remain unchanged. It never imports the
server, invokes a model, persists report changes, or changes raw source evidence.

## Observed score

The aggregate is a **provisional assessment of observed skills in this clip**.
It is not a full-match development grade. Retained assessment grades qualify
only with a unique canonical event ID and identity-verified evidence. Unknown,
non-finite, out-of-range and unbound grades are excluded rather than scored zero.
Weak-foot grades cannot be inferred from events with unknown anatomical side.

The schema contains 25 skills. Position priorities use weight 2, other skills
weight 1, following the position emphasis in `FULL_REPORT_PROMPT`. The precise
weighting is a publication policy, not a measured talent predictor. The aggregate
is the weighted average of qualified grades, rounded once to one decimal, half up.
It requires at least four rated skills, three distinct supporting actions and two
categories. Display rated/total skills, weighted rubric coverage and evidence count.

Orman500 retained-data review: 13/25 skills, 15/30 weighted units (50%), 12
supporting actions, aggregate **7.6/10**. This is a deterministic recalculation of
existing assessments, not a new model result or independent validation of grades.

## Academy reference

Reference ranges are the existing editorial age-band rubric in
`backend/server.py:FULL_REPORT_PROMPT`, versioned here as coaching rubric 1.
Every displayed comparison exposes its age bracket, ranges and limitations.
It is not a measured population percentile or an academy-admission prediction.
Position changes weights, not range boundaries. The retained older-age ranges
overlap; publication chooses the highest lower threshold reached and discloses
all ranges. Under-11 references are withheld because this rubric defines none.

For U11-U12: Standard Club 3-5; Strong Club 5-6.5; Academy 6.5-8;
Elite Academy 8-9. A full playing-level/recruitment-ladder placement remains
withheld even when an observed aggregate can be calculated.

## Facts and evidence

- Target event IDs are authoritative. Snapshot title, summary, timestamp and
  frame derive from the same event. No nearest-frame or token-matching fallback.
- Public copy uses the profile's player name. Internal IDs and original model
  text remain in raw evidence. Contact brackets remain brackets, not invented
  exact contact instants or foot-side conclusions.
- All key scoring actions and the complete chronological event log are retained.
  PDF front pages can show a preview; the measured-height appendix includes the
  full log, skill evidence and stable links back to the authenticated report.
- Shots include goals. Key passes are explicitly defined here as teammate-shot
  passes without a goal, with assists counted separately. Observed duels are
  distinguished from wins. Action segments are not ball touches.
- Report date uses the stored completion instant in Europe/Copenhagen, never
  the reader's timezone or current date. Duration is source video duration,
  not pipeline processing time.
- Automated completion and human review delivery are separate. Existing
  48-hour product messaging replaces the conflicting five-day review copy.
- A content revision enters the PDF cache key. Expiring media URL parameters
  do not change the semantic revision. Raw stored report data is not migrated.
- Evidence ZIPs retain raw `report.json` and separately include
  `publication/current.json`, explicitly marked as code-at-export projection.
  Current projection source is included without claiming historical provenance.

## Review without model spend

```sh
python backend/scripts/review_report_publication.py \
  --evidence-dir /path/to/extracted-evidence --output /path/to/review
```

This checks stored proof-frame PTS against the exported canonical video, extracts
local review images, and renders the PDF. A review portrait is a crop from the
original marked frame, not a recovered historical portrait file. No new analysis,
model requests, merge or deployment is performed.

Tests cover projection immutability/idempotence, invalid grades, missing evidence,
unknown foot, date/age references, exact frame joins, complete logs, PDF/shared-view
parity, key-action navigation, and withholding recruitment placement. Browser
visual review of the changed web UI remains required: the cloud browser could
not connect to the local preview server in this session.
