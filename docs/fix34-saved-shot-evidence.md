# Source-bound saved-shot sequence

A saved shot can lose its player attribution when the camera follows the ball
and local body labels change. A goalkeeper may be visible in the source video
while the native player detector supplies no body label. A stationary spare in
the net must not supply the shot's outcome.

## Changes

The existing temporal action reader observes the full play once. Its response
now includes frame-specific shooter labels and a response-local ball ID linking
four visible stages: strike, incoming ball, goalkeeper intervention and aftermath.

`saved_shot_sequence.connect` maps every cited box through that frame's existing
source ROI. It checks the source clock, chronological order, shooter/ball contact,
keeper/ball proximity, and consistent active-ball identity. A ball marked as a
stationary spare anywhere in this response cannot complete that active sequence.
A keeper absent from native detections can be located by a visible source box;
this creates no native measurement, player track or physical certificate.

An earlier dribbling touch cannot serve as the shot if another visible control
of the same ball occurs before the keeper's intervention. That contradiction
opens the existing bounded backward CONTACT search. An incomplete save chain
cannot retain a bare SAVED approval; it uses the existing missing-link feedback
budget. This adds no reader, feedback round, changed model or detector.

Per-frame shooter labels enter the existing canonical identity resolver.
Different labels are accepted as one actor only when every cited visible sample
already maps exactly to verified GLOBAL_TARGET on the actual source clock, with
no cut, fallback or competing verified target. The keeper need not be the target
and the shooter need not stay in view after his strike.

The resulting visual observations remain distinct from native physical evidence.
The shared resolver and projections publish one shot/on-target outcome only
after the original player's identity and continuous source sequence qualify.

## Existing-video evidence

The inspected export is for source SHA-256
`b9e2ba4975ed9dc2497f860a80644711bfd12a2125d9fba6390600b0409ab999`,
window `dense_e29df0078338b31c`, source interval 19.466–25.466 seconds.
These are diagnostic input identifiers, never production event rules.

The saved older model response describes SAVED but cites contact at 20.600 s.
Visual inspection of the source places the final kicking motion around
23.6–23.8 s. The older trace also has no measured player body during the keeper's
dive. Repeating its label or demanding an existing keeper ID cannot establish
a correct new source-bound event.

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
access blocked. It cannot return a fresh model success. On a runtime with the
existing production SDK and configured model key, run one fresh window read:

```bash
python scripts/review_source_window.py EXPORT VIDEO TRACE_ID OUTPUT --run-model
```

`--key-env` selects a configured environment variable; the key is never an
argument value or output. The default uses the same `EMERGENT_LLM_KEY` setting
as production. No Emergent agent, database write, payment, notification, report
mutation, merge or deployment is performed.

The fresh mode uses one existing action-reader call, applies the same source
identity handoff, and sends only that fresh observation to the canonical
resolver. It retains `fresh_observation.json`, `fresh_trace.json`, and
`review_summary.json`. A positive `qualified_saved_shot_count` must be assessed
with its contact time, ball stages, source hashes and original-player proof.
A qualified carry/run alone does not count as a verified saved shot.

## Validation and limits

Regression coverage includes local-label changes, camera-followed outcomes,
wrong players, cuts and wrong clocks, spare balls, switching/duplicate ball IDs,
unbound striker/keeper boxes, an untracked keeper, held-ball geometry, missing
source stages, later touches, conflicting goals and missing-link requests. The
production adapter/driver tests use explicit test doubles, not new perception.
Source timestamps can be shifted without changing classification logic.

The main local regression group passed 2,488 tests with one skip in 27.12 s
(the process-runner module was exercised separately). All 379 backend Python
files parse and the diff whitespace checks pass.

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
