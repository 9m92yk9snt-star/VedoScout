# Opt-in sequence full report (draft PR #39)

`FULL_REPORT_ENGINE=sequence_v1` selects the new path in
`generate_full_report_task`. The default remains `legacy`. No merge, deployment
or production switch is part of this change.

## Report contract

The new path starts from the source video and original positive user selections.
It does not call legacy tracking, the inferred identity timeline, physical match
reconstruction, whole-video rediscovery or corrective identity reconstruction.
Failure stays failed; it never falls back into those stages.

Fresh visual sequence observations, native contact/outcome reviews and hashed
model receipts supply the canonical events. An explicitly selected text-only writer uses
the existing report schema and assessment rubric. The new path uses the bounded
standard-library transport already used by the sequence experiment, rather than
the old report SDK. Neither report prose nor model-generated timeline/comments
can replace the canonical facts.

Existing deterministic statistics and claim reconciliation remain in use.
Completed requests do not prove exhaustive coverage: report totals remain
partial, with verified observed goals/assists shown by the existing frontend.
A teammate's goal is never counted as the selected passer's shot. A contact
interval stays an interval; its displayed source moment is not represented as
an exact contact. Anatomical foot side remains UNKNOWN. The prior middle-assist
LEFT/RIGHT disagreement is not resolved by this integration.

Source evidence frames require actual matching media PTS and the same video
hash/event ID. Clips show the cited action and outcome without invented player
boxes or rings. No movement map, speed measurement or tracked geometry is
inferred from sequence labels. Assets must publish before the existing finalizer
can write READY. Recovery re-renders retained proofs without new discovery.
The evidence ZIP includes sequence receipts, timing, engine and analysis source.

## Existing complete-run baseline

The user's latest uploaded evidence ZIP contains exactly the same source video
SHA256 `b9e2ba4975ed9dc2497f860a80644711bfd12a2125d9fba6390600b0409ab999`.
Its persisted start-to-ready trace is **5,094.270 seconds (84m54.270s)**:

| Stage | Seconds |
| --- | ---: |
| Tracking | 31.489 |
| Identity timeline | 105.979 |
| Unified preparation | 119.147 |
| Initial model | 121.296 |
| Physical reconstruction | 4,488.440 |
| Report synthesis | 151.216 |
| Evidence assets | 68.971 |

Physical reconstruction occupies 88.1% of the full wall time. Nested inspection
timings are not independent wall times and must not be summed into a substitute
total. The stored 157 goal-review requests are not evidence of 157 actual model
calls. The ZIP contains private account/report data and is not committed.

## Validation and limits

Retained real receipts from source run 39182857433 project to 1 observed goal,
3 observed assists and 2 shots/on-target shots. A replay through the actual
server orchestration completed eight exact source images and eight clips, with
no new model calls. This is a replay/asset test, not fresh end-to-end timing.

A separate fresh full-report run started from commit
`59b0e47257ac06d76c4493caff48a11fcd61c040` in Actions run 39186278770. It
uses an isolated report store, real models and real source encoding. Emails and
dashboard notifications are suppressed. The initial harness used a synthetic
age of 12; its age-based grades are not accepted as this player's assessment.
That run stopped after 569.373s at writer transport preflight, before a report
model request: the writer requested 180s but the transport only accepted 150s.
It never wrote READY or called legacy reconstruction. The transport now accepts
up to 210s, with the sequence reader still requesting 120s. An owned-worker test
exercises the writer's actual 180s configuration and report-object parsing
without network calls. Source receipts/canonical events now checkpoint before
writing, so a later writer failure cannot discard completed source evidence.

The harness now accepts explicit metadata (the supplied report states age 11,
position Winger). Production always forwards the stored player details.

The pilot bounds remain: source preparation has a deadline, at most twelve
initial scene packets, six follow-ups and a shared 900-second discovery budget.
Nonzero anchor offsets are rejected until separately validated. Missing original
positive selections, incomplete calls, missing/altered receipts and missing
assets prevent READY. This is not yet a validated long-match or multi-match
production rollout.

Five additional files were inspected: three older evidence ZIP videos and two
uploaded Almin test07 videos. Their byte hashes differ, but all show the same
76.8-second sequence. Eight sampled images of each uploaded video correlate
0.9968–0.9986 with the original; older ZIP versions average about 0.9981 across
39 sampled moments. These are encoding variants, not independent matches.
Generalization testing still needs distinct match footage with original player
selections and independently checked events.

## Current actual report-stage evidence

Fresh run 39187246868 completed source analysis in **518.498s (8m38.498s)**
with thirteen completed requests. All five reference scoring actions matched.
The persisted source checkpoint is `examples/sequence-report-source-checkpoint.json`.
This duration is source analysis only, not a completed full-report duration.

Report-only run 39188297174 replayed those observations and made a real Gemini
2.5 Pro writer request. It failed with HTTP 429 after 62.343s (62.829s trial
wall time). Run 39188665065 explicitly selected GPT-6 Astra, low reasoning,
and failed at the 180s wall deadline (180.211s trial wall time). Neither trial
wrote READY, generated a usable full report, or called legacy reconstruction.
Their compact failure receipts are retained next to the source checkpoint.

The writer now requests two bounded sections using the same report schema and
rubric: assessment first, then family/coaching presentation with the returned
assessment attached. Canonical facts, timeline, comments and statistics remain
application-owned. Each section requests concise text (below 6000 tokens) with
a 12288-token hard output ceiling and a 180s wall deadline. There is no automatic
model fallback or network retry. Missing section keys and a failed second
section prevent publication; both receipts remain available for diagnosis.
This change still requires a successful actual report-stage run before claiming
a complete new report or comparing full old/new report timings.
