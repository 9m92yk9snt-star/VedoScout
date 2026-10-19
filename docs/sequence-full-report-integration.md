# Sequence full report (PR #39)

All new full reports use the source-sequence path in
`generate_full_report_task`. The user authorized replacing the legacy analysis
path and merging PR #39. `FULL_REPORT_ENGINE` is obsolete: even a retained
`legacy` value cannot reactivate the old reconstruction for a new report.
No deployment is performed as part of this change. Existing report bodies and
their engine-specific asset recovery remain intact; historical reports are not
automatically reanalyzed. The existing frontend and PDF templates are retained.

## Model-call economy and offline defaults

Ordinary PR checks run offline. The source-window probe is available only by
manual workflow dispatch on the draft branch, with `run_model_probe=false` by
default. The CLI/function also defaults to preflight-only; an actual request
requires `--run-model`. Offline validation, hashes, deterministic projection,
statistics, asset encoding and error inspection do not need a model call.

A quota/rate error now stops queued requests and prevents later contact/outcome
rounds. Already-sent remote work cannot be recalled, but pending calls are marked
NOT_SENT. No automatic retry, provider change or alternate credential is used.
Tests simulate quota failure in the initial, contact and outcome rounds and
exercise the owned process scheduler without network requests.

The retained old HTTP 429 receipts contain neither an upstream error code nor
Retry-After, so their quota-versus-rate cause cannot be recovered offline. Future
402/429 errors retain only allowlisted structured categories and a bounded
numeric Retry-After value. Unknown detail stays UNSPECIFIED; raw messages,
response bodies, credentials and general headers are never persisted. This
diagnostic change does not itself send any requests or retry a failed call.

`SEQUENCE_REPORT_WRITER_MODEL` explicitly selects `gemini-2.5-pro` (default) or
`gpt-6-astra`. Actual successful section-writing tests use GPT-6 Astra with low
reasoning; source discovery uses GPT-6 Astra with medium reasoning. There is no
automatic provider/model fallback. Enabling the sequence engine alone does not
change the default writer selection.

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

A failed sequence report with no body can resume its retained complete source
phase only when video SHA, raw original-selection fingerprint and all four
source-analysis code hashes still match. Receipt hashes and event role bindings
are checked again. Legacy/partial analyses, inferred identity mode and changed
inputs/code cannot resume; altered receipts fail before another paid call.
Writer/assessment runs again with current player metadata and report schema.
`source_phase_reused` and `retained_source_analysis_seconds` distinguish this
retry's elapsed time from the original source analysis; a retry is not a fresh
end-to-end benchmark. The original source checkpoint survives another writer
failure. Original selections changing always require fresh source analysis.

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
Actual run 39189511045 completed the two-section report and assets in **192.669s
(3m12.669s)**: 179.569s writing/projection and 12.976s asset generation.
The actual server finalizer wrote READY with eight matching source frames and
eight clips, zero production notifications and no legacy reconstruction.
Source discovery was explicitly replayed, so this is not fresh end-to-end timing.
Both completed raw writer receipts are retained in
`examples/sequence-report-sections-receipts.json`.

Content review found a stale provisional Strong Club label in presentation after
the evidence authority withheld the aggregate tier. The presentation writer now
consumes the reconciled assessment; deterministic final projection also removes
current/potential level labels and recruitment dots when the tier is unavailable.
Regression tests reproduce the inconsistency using the actual raw responses.
The fresh source-to-report trial is recorded below. Distinct-match validation
remains outstanding.

## Latest cold attempt: blocked, not a completed benchmark

Run **39190024773**, commit `0dc4901342d53409300fb0aa9c5a7e283b02174e`,
started with only the original video/selections and age 11/Winger metadata.
It completed fifteen fresh source calls in **650.155s**. The first assessment
request then returned **HTTP 429** after **62.292s**. Total failed trial wall time
was **713.018s (11m53.018s)**. No report body, assets or READY were produced;
no production database, notifications or legacy reconstruction were used.
This is a failed attempt duration, not a new full-report processing benchmark.
The complete unchanged source/writer receipts and failure document are retained
in `examples/sequence-report-cold-failed.json`.

Four scoring references passed the old resolver. The fifth raw observation
explicitly identifies the selected shooter, contact interval 23666–23749ms,
keeper glove contact, changed active-ball motion and SAVED. Its separate question
asks whether the parried ball goes out of play after frame s000025516. Because
the old contract gives every OUTCOME question the same blocking scope, this
later-possession uncertainty also blocks the already described shot. This is
not a fresh model assertion that another player shot.

The question contract now preserves the exact question text and distinguishes
ACTION from explicitly structured AFTERMATH. AFTERMATH can be nonblocking only
for a shot with structurally established contact/terminal outcome, continuous
active ball and a supplied after_frame at or beyond the action end. It remains
an open question and creates no claim about the later possession. Identity,
contact and terminal-outcome questions, unknown scopes and invalid boundaries
continue to block approval. Aftermath-only gaps do not trigger more release
reviews. Tests use the actual retained response with explicit synthetic scope
metadata and counterexamples; **the original unscoped receipt is not rewritten
or retrospectively promoted**. This new contract still needs an actual fresh
model validation when normal API access is available. No additional calls
were started within that attempt after the rate-limit response. After the
user requested continuation, a separate one-call source-window validation was
prepared using the same ordinary API/model. It never repeats whole-source
discovery and stops on any further quota/rate error. Only original video and
selections, the user-located window and the new question contract are inputs;
no prior model answers or expected result is supplied.

That bounded follow-up was run **39191911227**, commit
`6e485d585d49bf0ff92bb89fcf329c8787cde46c`. Offline preflight prepared the
19,266–25,631ms source window, 135 source instants / 159 delivered images and a
7,572,361-byte request with zero model calls. The later actual request used the
same ordinary API/model and returned **HTTP 429 after 63.330s**; total probe wall
time was **79.199s**, exactly one model request. No new model observation or
approval was obtained. Its complete request/selection hashes and error receipt
are retained in `examples/sequence-question-scope-rate-limit.json`. Model calls
stop here; no repeated quota retries, alternative credentials or model fallback
are used. At that point the structured scope contract was offline-tested,
awaiting actual model validation. The probe also checkpoints raw responses before parsing so a
malformed response cannot discard paid evidence.

## Actual shot-filter validation succeeded

Following the user's explicit request to validate the filter, run **39193772410**
(commit `291c5fb1fd1f6878259612b957b8fd60e0d90e52`) made exactly **one** fresh
GPT-6 Astra request using only the original video/selections and user-located
19,266–25,631ms window. No historical answers or expected outcome were supplied.
The model call completed in **56.214s**; total preparation/probe wall time was
**80.355s**. This is single-window validation, not whole-source/report timing.

The actual returned observation identifies the selected player from r5/r6 as
the shooter, with contact bracket **23,682–23,749ms**. It identifies the nearby
white teammate as a separate person, describes the goalkeeper's glove contact
and changed active-ball motion, and returns **SAVED**. The ball bouncing outside
the post is distinguished from the stationary spare ball inside the net.

Crucially, the model itself returned the new structured question:
`scope=AFTERMATH`, `after_frame=s000025516`, asking who next collects the loose
ball after the established save. The live resolver retained this unanswered
question while returning the selected shot with `proof_eligible=true` and
`model_requested_clarification=false`. No scope metadata was added manually.

The complete raw response, payload/response hashes, delivered source frame
catalog and original-selection hashes are retained in
`examples/sequence-shot-filter-validation.json`. Offline regression now
reproduces the actual live resolved output exactly. Counterexamples changing
the question to ACTION, giving an invalid aftermath boundary, removing unique
contact support or breaking active-ball continuity still block approval.

The explicitly authorized one-run PR trigger is removed again; ordinary PR
checks and the CLI remain offline by default. No second model call, full-video
analysis, report writing, merge or deployment was performed for this validation.
The middle-assist anatomical-foot disagreement remains unresolved. A complete
fresh source-to-READY report benchmark and distinct-match testing still remain.

There is still no successful uninterrupted cold source-to-READY timing. The
successful 192.669s report-stage replay and earlier 518.498s source run cannot
be added and presented as one observed complete run. Production/long-match
rollout is not validated.
