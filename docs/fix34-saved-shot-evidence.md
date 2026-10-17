# Source-bound saved-shot sequence

A saved shot can lose its player attribution when the camera follows the ball
and local body labels change. A goalkeeper may be visible in the source video
while the native player detector supplies no body label. A stationary spare in
the net must not supply the shot's outcome.

## Changes

The existing temporal action reader observes the full play once. Frame-specific
shooter labels follow the observed person when native track IDs change. A direct
high-confidence comparison with the original selected-player reference is an
identity anchor; the video path no longer demands two comparisons separated by
150 ms under every ID, a fixed feature count, isolated native torso crops, or a
second continuous native identity proof. Coarse unknown/team labels do not veto
this direct reference observation. Static image-only reads retain their existing
multi-frame rules.

`saved_shot_sequence.connect` retains a source-video SAVED observation without
demanding four extra ball boxes, native keeper identification, prescribed
ball-to-body pixel distances, or a separate held-ball keeper box. Detail boxes
are optional audit data and map through the actual source ROI when available.
Explicit stage observations of the same active ball, keeper intervention and
aftermath can also resolve UNKNOWN without four independent ball detections.
A known stationary spare or a different observed ball/actor remains a
contradiction. No native measurement or physical certificate is fabricated.

An earlier dribbling touch cannot serve as the shot if another visible control
of the same ball occurs before the keeper's intervention. That contradiction
opens the existing bounded backward CONTACT search. An observed outcome need
not be rediscovered because an optional detail form is absent. This adds no
reader, feedback round, changed model or detector.

Per-frame shooter labels enter the existing canonical identity resolver.
One directly identified sample can anchor the same person followed by the video
reader across the action's other labels. Those labels do not each require a new
GLOBAL_TARGET proof. Explicit evidence that a cited actor is a different selected
body, actual cuts, source mismatches and fallback source times remain unresolved.
The keeper need not be the target and the shooter need not stay in view after
his strike.

Outcome indices are alternatives: either `outcome_idx` or a source-indexed
`outcome_evidence_indices` list suffices. The duplicate field is not required.
A missing whole-clip completion flag no longer discards an observed action; it
only prevents that read from suppressing other coverage work. An arbitrary
250 ms source-sampling gap alone no longer rejects video continuity.
The prompt requests only useful frame observation rows, rather than mandatory
empty rows for every supplied source frame. Source image coverage is unchanged.
The production reader treats optional pixel/crop rows separately: omitted rows,
duplicate rows or malformed jersey fields do not discard valid video actions.
Native pixel proposals still use their own parser; explicit spare/ball conflicts
remain visible to the video adapter even if an auxiliary pixel field is invalid.

The resulting visual observations remain distinct from native physical evidence.
The shared resolver and projections publish one shot/on-target outcome only
after the original player's identity and continuous source sequence qualify.

## Audit of repeated approvals across actions

The complete observation-to-report path was reviewed, including assists and
ordinary involvements. The changes use existing modules and the existing video
read; they add no model pass or runtime approval module.

| Repeated decision | Previous effect | Current behavior |
| --- | --- | --- |
| Assist team and possession | An observed continuous pass/receive/finish still needed two native kit samples and native ball possession at both ends. | The source-bound video observes the transfer and teammate roles once. Missing detections or contradictory coarse kit labels do not veto that observation. |
| Receiver/finisher track stitching | A changed native label required verified native touches within 150 ms and another physical same-person proof. | The video follows the receiver through the finish. Explicit evidence of a different finisher, opponent or target receiving/finishing remains a role contradiction. |
| Overlap merge | A stronger event could contribute its label while losing its video provenance and causal chain, triggering physical approval again. | Keep the complete stronger observation and merge supporting source IDs/evidence. A later goal view can extend a completed pass to an assist. |
| Physical reconciliation | A physical boolean could discard a fresh video observation; a later proposal could overwrite a resolved video outcome. | Retain the qualified video result. Keep secondary physical corroboration/disagreement in the audit, without attaching a contradictory physical certificate. A nearby separate release does not relabel a receive or dribble. |
| Report timestamp binding | A save/goal after the player's action ended could fall outside the report's action-only matching interval. | Bind the report to the already verified causal outcome as well as the player's action. Preserve causal verification through timeline/stat projections. |

An actually contradictory pair of complete source-video outcomes remains visible
as `CONFLICTING_VIDEO_OUTCOMES`, including within one trace; deduplication cannot
silently choose the first or revive it from an overlapping trace. UNKNOWN is
missing knowledge, not contrary evidence. COMPLETED, TEAMMATE_SHOT and
TEAMMATE_GOAL are compatible stages of the same observed pass.

This policy intentionally gives the complete source-video interpretation priority
over the independent native reconstruction. It is not proof of unchanged model
accuracy or improved full-report latency.

The immutable real-response audit is
[`observation-approval-audit.json`](observation-approval-audit.json). It checks the
stored response hash and maps every one of its 25 action claims to its recorded
canonical decision: seven accepted, 18 unresolved, all 18 with
`INSUFFICIENT_PHYSICAL_IDENTITY_EVIDENCE`. All 25 raw claims said target VERIFIED;
that assertion was not the missing selected-reference pixel comparison. The old
export contains no source-indexed temporal action inspections. This is a record
of the actual older model run, not a fabricated new acceptance result.

The raw run includes SHOT/SAVED and a completed pass around the first reference
assist, but does not contain three complete direct-assist chains. Removing later
vetoes cannot repair those original role/chain omissions. The audit retains
every recorded decision instead of relabelling all 25 claims as approved.

## Existing-video evidence

### Expensive-work audit and removals

[`analysis-work-audit.json`](analysis-work-audit.json) records the original
provider diagnostic totals, source-trace hashes, a fresh native profile and a
paired comparison on original video frames. The historical provider rows total
2,343.276 s (39.05 minutes), but include cache reuse and unavailable results;
382 rows are not 382 paid model calls. Physical reconciliation proposed zero
new scoring events and recovered one other action through identity feedback.
The number reader produced seven VERIFIED consensus statuses and role readers
produced two VERIFIED goalkeeper statuses. These are recorded model outputs,
not independent proof that every classification was correct. One failed run
does not show that an entire detector or reader has never worked.

Removed or bypassed work:

- Delete the standalone playable-field-side decoder/model reader and its worker
  registration. The goal-scene reader already observes goal geometry and field
  side together. Custom readers retain their literal orientation evidence; a
  missing orientation stays missing rather than opening a second model call.
  This path was already bypassed by valid combined production responses, so its
  deletion is not credited with saving the historical 39 minutes.
- Merge identical jersey/role crop requests within a pending batch. Previously
  the cache was only filled after the batch returned, allowing the same source
  instant/body crop under different local labels to open duplicate model calls.
  Preserve each recipient/request ID and actual timestamp. Copies of one frame
  remain one independent observation. Cache keys include source path and exact
  body coordinates rather than rounded coordinates.
- Reuse current-run physical results when feedback adds no physical input and
  requests no new jersey crop. The source hash, measured frames, shared jersey
  reference and explicit role evidence must be unchanged. Keep the fresh video
  response for the common resolver. New native pixels, identity information,
  jersey crops or changed shared evidence still re-enter the physical path;
  exported replays without the current run's work record still reconstruct.
- Remove person-box/kit-colour postprocessing from the native ground-band pass:
  its caller only consumes ball candidates. Keep the entire detector forward,
  ball thresholds, full-scene person pass and all original source views.

The fresh local profile decoded/refined all 361 frames of the six-second saved
shot window with four OpenCV threads. It took 67.202 s, with 672 detector forwards
accounting for 54.044 s. This is a native-stage profile, not model recognition or
full-analysis latency. That detector work produces source proposals and cannot
be deleted merely because later canonical scoring was unresolved.

On 13 uniformly selected frames from the same source window, the old and revised
native functions returned exactly identical person, ball and support proposals.
Discarded kit computations fell from 24 to 13; the final paired local times were
2.063 s and 1.957 s. Native person-refinement crops retain their person outputs;
only the ball-only ground-band pass drops them. This small sample does not
establish a full-analysis speedup.

The 30–60 minute chat estimate was not derived from a calibrated measurement
and is withdrawn as a reliable runtime prediction. None of these measurements
establishes a five-action model PASS or a complete-video speedup.

The inspected export is for source SHA-256
`b9e2ba4975ed9dc2497f860a80644711bfd12a2125d9fba6390600b0409ab999`,
window `dense_e29df0078338b31c`, source interval 19.466–25.466 seconds.
These are diagnostic input identifiers, never production event rules.

The saved older model response describes SAVED but cites contact at 20.600 s.
Visual inspection places the final kicking motion around 23.6–23.8 s; buildup
belongs to the same play. This timing mismatch is not itself the resolver's
rejection reason. Replaying the unchanged, checksummed real response returns
SHOT/SAVED from causal resolution and INSUFFICIENT_PHYSICAL_IDENTITY_EVIDENCE
from actor resolution. The trace stores zero selected-reference comparisons.
Removing a duplicate proof demand cannot create a missing comparison in an old
response. No replayed observation is relabelled as a new model result.

The new input-only review successfully reconstructed:

- 81 source-indexed frames across the full existing window;
- a full-scene overview in all 81 frames, body detail in 62;
- actual source timestamps throughout, maximum source gap 133 ms;
- the original selected-player source crops, without new taps;
- zero new model calls.

Preparation took 8.692 s in this environment. This measures input preparation
only, not model inference, full analysis latency, or automatic recognition.

## Focused verification without another upload

From `backend`, use an extracted evidence directory and its matching local video:

```bash
python scripts/review_source_window.py EXPORT VIDEO TRACE_ID OUTPUT
```

The default builds the source input and original tap references with network
access blocked. It cannot return a fresh model success. With `GEMINI_API_KEY`
configured in the runtime, run one fresh window read directly against Gemini:

```bash
python scripts/review_source_window.py EXPORT VIDEO TRACE_ID OUTPUT --run-model
```

The default transport is `gemini-rest`: the existing video transport posts the
same model (`gemini-2.5-pro`), clip, prompt and selected-player references to
Google's native `generateContent` endpoint. It attaches `videoMetadata.fps` to
the video part, requests JSON, records model version/response ID/token usage,
and rejects incomplete, blocked or failed responses. It uses standard-library
HTTP, without Emergent, LiteLLM, uploads or retries. Inline requests above
20 MB stop before network access. A response does not certify which frames
the provider internally inspected; the audit keeps that distinction.

`--transport sdk` retains the existing production transport and defaults to
`EMERGENT_LLM_KEY`. `--key-env` selects a configured variable name; the key is
never an argument value or output. Production transport defaults are unchanged.
There is no database write, payment, notification, report mutation, merge or
deployment in either focused mode.

The fresh mode uses one existing action-reader call, applies the same source
identity handoff, and sends only that fresh observation to the canonical
resolver. It retains `fresh_observation.json`, `fresh_trace.json`, and
`review_summary.json`. A positive `qualified_saved_shot_count` must be assessed
with its contact time, ball stages, source hashes and original-player proof.
A qualified carry/run alone does not count as a verified saved shot.

Native request format and sampling follow the official
[GenerateContent / Part reference](https://ai.google.dev/api/generate-content)
and [video-understanding documentation](https://ai.google.dev/gemini-api/docs/video-understanding).

## Active pipeline and recorded cost

FIX numbers describe the project's history, not 36 sequential runtime stages.
The current `generate_full_report_task` calls these paths:

| Phase | Active path | Work and evidence responsibility |
|---|---|---|
| Player selection/tracking | `player_tracking` | Source taps and measured player path; audio runs alongside it. |
| Identity preparation | `player_identity_timeline`, `unified_analysis_engine.prepare_analysis` | Reconcile selected-player identity and build the native scene graph/sequence plan. These include additional video work. |
| Broad temporal read | `call_gemini_with_video` | Find actions across the video; one bounded retry can request incomplete windows. |
| Detailed reconstruction | `physical_match_reconstruction` | Dense tracking, source-window action read, ball/contact work, identity handoff, jersey/role/goal work and bounded feedback. Dense tracking currently precedes the action read. |
| Shared resolution | Canonical resolver and FIX10B reconciliation | Bind actor/contact/outcome, merge observations, and project report facts. |
| Report writing | `call_gemini_with_facts` | Write from the resolved observations without another video discovery pass. |

FIX08 remains a fallback if the unified route cannot run. It is not a second
full route always run after the unified analysis. Selection UI, training/test
files, exports and historical FIX documentation are not separate live readers.

The existing exported run records **4,138.355 s** for physical reconstruction
(68.97 minutes). These figures are from the old export, not a new PR-head run:

| Provider diagnostic rows | Rows | Recorded elapsed seconds |
|---|---:|---:|
| Action pixel inspection | 24 | 465.304 |
| Jersey inspection | 23 | 260.426 |
| Intervention role | 23 | 237.804 |
| Goal geometry | 312 | 1,379.742 |
| Total recorded provider time | 382 | 2,343.276 |
| Physical time not assigned to these rows | — | 1,795.079 |

These are diagnostic rows, **not counts of paid model calls**. In particular,
258 goal rows have elapsed time rounded to zero, consistent with cache/reuse
paths. The export does not assign the remaining 29.92 minutes precisely enough
to claim that any particular module consumed it.

The 15 stored windows contain 6,165 decoded-frame rows but 4,551 unique source
timestamps, 192 physical strike/control-release candidates and 34 inspection
records including feedback. Overlap is real, but this is not a claim that the
current branch still repeats all of that work: prior shared-window, pixel,
detector and resolved-outcome reuse already change its scheduling.

The saved-shot window specifically contains 361 frames, all with unresolved
GLOBAL_TARGET, and 19 physical strike candidates, none bound to GLOBAL_TARGET.
The old semantic SHOT at 20.600 s precedes the visually observed final kicking
motion. The missing correct actor/contact and the keeper detection gap are
perception/binding failures. Deleting approval checks cannot supply those pixels
or turn an earlier dribble into the final shot.

The focused driver avoids a fresh full-report rebuild: it reads the original
six-second source interval once using the existing measured context and taps,
then sends the fresh response through the same identity and event resolver.
One source-bound temporal response should carry the player, final strike,
active ball, keeper and aftermath together. A failed response must identify the
missing link before further fallback work is justified. Changing the full
pipeline to run this way before dense detection still requires real perception
validation; no end-to-end performance or quality claim follows from this audit.

## Shared detector work and the two-pass design

The production path does not run two independent whole-video reports
in parallel. At `1bd23012`, `generate_full_report_task` ran optical tracking
and audio extraction in parallel. The follow-up removes the unused audio
extraction: tracking precedes the identity/scene preparation and whole-video
sequence read. Report prose consumes canonical facts. The
legacy full-video writer and `_cross_verify_full_report` remain a fallback
when the unified path cannot run. Removing that fallback verifier alone would
not accelerate successful unified analyses.

The source-indexed motion reader has a different job: inspecting the player,
contact, active ball and outcome in a bounded original-source sequence.
Existing motion reconciliation already skips contact-bound native paths,
interventions and goal reviews for an outcome resolved from that source clip.
Unresolved contacts can still receive a goal review; missing observations are
not treated as resolved merely to save work. No second outcome approval was
added by this change.

Native identity, scene, dense and ROI readers did repeat the same network
inference for identical pixels. They now use one preprocessing/head reader in
`cv_detect`, with a report-local cache. Its key binds the model SHA, network
type, input size, candidate thresholds and exact image shape/dtype/pixels.
It retains exact coordinates, winning class/confidence and class-32 scores,
including support candidates whose winning class is different. It changes no
precision, confidence/NMS threshold, source sample or crop coverage.

The readers retain their separate NMS, kit measurements, tracking, player
binding, ball association and event decisions. Returned arrays are isolated
from caller mutations. Identical concurrent requests share one forward;
failed/unknown-model requests cannot populate the cache. LRU storage is bounded
to 64 MiB of array payload and 8,192 entries per report. Context restoration
runs on success, early return and cancellation. `unified_detector_cache`
records actual hits, forwards and payload use without becoming a proof gate.
Ball-only review ROIs also stop computing discarded person/kit output.

A fresh, offline native comparison used all 361 actual-PTS source frames from
the existing six-second diagnostic window. The measured pattern exercised
31 identity-reader inputs, 46 scene-reader inputs, all 361 dense inputs and
13 sparse native revisits. The baseline loaded the three reader functions
from the preceding published head `f534902c` (tree `b3d5db38`):

| Native reader pattern | Before | Shared inference |
| --- | ---: | ---: |
| Network forwards | 773 | 672 |
| Elapsed seconds | 44.496892 | 40.919901 |
| Source/reader input frames | 361 / 451 | 361 / 451 |
| Cached payload bytes | 0 | 1,382,624 |

All returned person/ball/support proposals were exactly identical (canonical
JSON SHA-256 `bac481b478abe231715c888ca4876419734b5cadebbe2620d0944b470d273d54`).
This pair saved 101 forwards (13.07%) and 8.04% elapsed time in that reader
pattern. It is not the historical LLM call schedule, full tracking or complete
physical reconstruction. Decode/model loading were outside the timed reader
loops. One pair does not calibrate a full-report speed prediction or prove
ground-truth detection accuracy. Zero LLM calls and network connections ran.
The reproducible driver is `backend/scripts/benchmark_shared_detector.py`;
checksums, per-stage counts and receipts are in `docs/analysis-work-audit.json`.

A separate 13-frame experiment compared 8/4/2/1 CPU threads twice. Eight
threads were fastest here; all proposal outputs matched. No production thread
cap or ONNX-runtime change was introduced based on an assumed benefit.

## Music, observation certainty and one connected action

The legacy audio helper computes volume/RMS peaks, not music, speech, football
contact or goal recognition. On the original 76.76-second source it returned
ten `loud_event` rows in 0.403 s. These are unclassified volume observations,
not proof of any reference action. This small local time cannot explain the
69-minute reconstruction or two-hour timeout, and the old full-report branch
ran alongside tracking. No full-report wall-time gain is inferred from removing
it. The measurement is recorded in `docs/analysis-work-audit.json`.

The preview and full report no longer extract those peaks. Legacy API arrays
remain empty, and corrective recovery does not reload old peaks. Both precision
prompt builders ignore their compatibility `audio_events` argument, so saved
music peaks cannot re-enter a prompt through an older caller. The unused volume
diagnostic remains available as a legacy helper with an explicit non-evidence
description. The unified sequence reader already did not consume the extracted
peak list; this removes wasted work there and misleading cues in preview and
legacy/corrective prompt paths.

The previous voice rules instructed the model to confirm events with loud
peaks, question goals with no nearby peak, ignore every other player, and never
express uncertainty. The text scrubber then changed phrases such as `might
have` to `did`. That could manufacture certainty without adding any observation;
it is not established as the cause of the old saved-shot identity failure.

The rules now ask for direct statements of clearly seen actions, preserve the
unknown part of an action, and follow the selected player/contact/active ball
through the goalkeeper or receiver and aftermath. Observing a teammate or
keeper is necessary context, not a reason to transfer their actions to the
target. A stationary spare remains a separate ball. The legacy scrubber entry
point now returns the model's wording/data unchanged; regex rewriting and
recursive traversal have been removed.

The existing SDK and direct-REST video requests share one explicit visual
observation policy. No extra model request, model change, decoding pass or
source/frame sampling change is introduced. Source/reference bytes and their
hashes are retained. The audit records the policy and actual system-instruction
hash; that is evidence of the sent instruction, not a receipt proving model
compliance. Original uploads can still contain a soundtrack. No music
classifier or repeated audio/video transcoding was added.

Existing motion reconciliation skips the physical path, keeper-role and goal
review work that would re-establish an already resolved source-clip outcome.
It can still investigate an unresolved contact. This is the useful role for
the AI: one connected source observation, reuse of its documented result, and
bounded follow-up for the actual missing evidence, without a second assistant
model routinely repeating the full video.

## Validation and limits

After the visual/audio policy change, 2,485 tests passed with one skip across
125 offline backend files in 28.56 s (the prior sweep plus the new policy
regressions and `test_precision_engine.py`). A focused reader/precision group
also passed 174 tests, overlapping this sweep. Original source hashes, one
request per invocation, sent policy and preserved uncertainty are code-tested
with explicit transport doubles, not fresh LLM perception. The old
`test_iter18_multianchor.py` integration module requires `/app/frontend/.env`
and was not runnable here; no live service was substituted for it.

The final shared-detector code passed 2,468 tests with one skip across 123
offline backend files in 25.92 s; all Python socket connections were blocked.
The new regressions cover reader threshold independence, class-32 support,
pixel/model/config changes, caller mutations, failures, bounded storage,
concurrent reuse, separate reports and task-context restoration. These are
code fixtures. The native video measurement above is separate from them and
does not automatically recognise or approve the real saved shot with an LLM.

The final code after removing redundant work passed 2,456 tests with one skip
across the same 122 offline backend files in 27.41 s. Another focused selection
passed 12 process-wiring/reuse checks, overlapping this sweep. The separate full
process-hygiene module remains a GitHub CI check. Retiring its field-side cases
and registry entry does not change deadlines, isolation, cancellation or cleanup
for the remaining seven registered readers.

After the broader action audit, the reviewed final code passed 2,447 tests with
one skip across the same 122 backend files in 26.15 s. All Python socket
connections were explicitly blocked for this run. An earlier unrestricted
invocation was stopped by automatic approval review over an outbound fetch;
the offline run completed without needing that fetch. The separate process
runner module remains covered by GitHub CI rather than counted as locally green.
The new regressions exercise complete production projections, native detection
gaps, kit disagreement, receiver label changes, full-proof overlap merges,
compatible pass outcomes, physical disagreements, source-role contradictions,
idempotence and late report timestamps. They are code fixtures, not new model
inference of the reference video.

Regression coverage now explicitly admits source-video identity across local
labels with one selected-reference comparison, optional save detail boxes,
untracked keepers, held balls without another keeper box, either outcome-index
format, partial-clip observations and wider source-sampling intervals. Different
selected bodies, wrong source clocks/hashes, known spares, different active
balls, contradictory controls and actual cuts remain separate controls. The
production adapter/driver tests use explicit test doubles, not new perception.
Source timestamps can be shifted without changing classification logic.

The earlier focused identity/video/save group passed 198 tests after the saved-shot simplification.
This deliberately gives source-video observations more authority instead of
recertifying them through native geometry. Unchanged perception accuracy or
full-report latency cannot be claimed without a fresh real model run.

Before the broader action audit, 122 backend regression files passed 2,420 cases with
one skip in 28.99 s (the process-runner module is checked separately in CI).
All 379 backend Python files parse and diff whitespace checks pass. The focused
198-case group overlaps this sweep; the counts must not be added together.
Direct-transport controls include source-byte/reference preservation, actual
video-part sampling, no SDK dependency, HTTP failure, timeout, blocked output
and token truncation. HTTP/reader replies in those controls are explicit test
doubles. This is code validation, not new model perception.

The actual source-input preparation was repeated: the same 81-frame source
input and original reference hashes were reconstructed in 9.335 s, with zero
new model calls. The attempted `--run-model` invocation stopped before network
or output creation with `GEMINI_API_KEY is not configured`. No fresh response
exists, so the real saved shot remains unapproved here. The old model's SAVED
label is not reused as acceptance evidence.

The real source-input preparation succeeded. A fresh production-model response
for this shot is still unavailable because no live model key is configured in
this workspace. Automatic recognition of this real shot and full-report latency
remain unverified. No five-action success is claimed.

Some local process-hygiene teardown checks fail in `test_fix14_support_vision_runner.py`.
They also fail when run from the unmodified PR #36 commit `573fa934` in this
workspace (37 assertions passed, 18 SDK-dependent skips, 4 teardown errors).
The saved-shot change does not alter that runner or weaken its tests. The main
regressions and the process module are reported separately, and GitHub CI must
be checked on the final PR head.
