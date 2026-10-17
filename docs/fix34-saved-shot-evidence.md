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

The resulting visual observations remain distinct from native physical evidence.
The shared resolver and projections publish one shot/on-target outcome only
after the original player's identity and continuous source sequence qualify.

## Existing-video evidence

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

## Validation and limits

Regression coverage now explicitly admits source-video identity across local
labels with one selected-reference comparison, optional save detail boxes,
untracked keepers, held balls without another keeper box, either outcome-index
format, partial-clip observations and wider source-sampling intervals. Different
selected bodies, wrong source clocks/hashes, known spares, different active
balls, contradictory controls and actual cuts remain separate controls. The
production adapter/driver tests use explicit test doubles, not new perception.
Source timestamps can be shifted without changing classification logic.

The focused identity/video/save group passed 193 tests after the simplification.
This deliberately gives source-video observations more authority instead of
recertifying them through native geometry. Unchanged perception accuracy or
full-report latency cannot be claimed without a fresh real model run.

After the simplification, 122 backend regression files passed 2,415 cases with
one skip in 30.90 s (the process-runner module is checked separately in CI).
All 379 backend Python files parse and diff whitespace checks pass. The focused
193-case group overlaps this sweep; the counts must not be added together.
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
