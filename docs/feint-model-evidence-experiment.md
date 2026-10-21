# Feint evidence experiment

This is an isolated experiment, not a production feature. It neither updates existing
reports nor changes SEQUENCE_V1, scores, PDF layouts or deployment.

`backend/scripts/probe_feint_evidence.py` accepts a video and original selections.
It supplies no expected incident times, counts, successful results or historical
report. A native-video discovery request is followed by one separate model review
of timestamped source images for at most six discovered candidates. Additional
candidates remain explicitly unreviewed. Empty discovery is valid.

Each observation separates identity, before/movement/after evidence, opponent
response and immediate outcome. Types include body feint, direction change,
stop-start, step-over and shield-turn, plus other/unknown. A retained ball is not
necessarily an opponent beaten; a later goal does not validate a prior feint.
Specific tricks, foot side, scanning and personality must not be inferred from
hidden contacts. Source-frame citations, ordering, candidate ownership and
vocabulary are checked. These checks do not independently prove football accuracy.

The experiment retains source/selection/image/payload/response SHA256 values,
provider/model version, raw responses, usage and request durations. Receipts are
written before parsing. At most two model requests; no automatic retry. A failed
or incomplete response cannot become a completed result.

## Current fixture

The workflow reuses the already committed Orman400 video encoding and its original
selections, SHA256 `b9e2ba4975ed9dc2497f860a80644711bfd12a2125d9fba6390600b0409ab999`.
This is **not** the Orman500 export file, whose SHA256 is
`6e7439d5d657a601f8195e4555cec9970e7d901b3a7a2605cdea2b49d536b3a4`.
Local visual/time comparisons at ten instants (0, 3.86, 8, 20.45, 35.25, 44, 50,
56.45, 63.12 and 71 seconds) show corresponding footage with matching dimensions;
mean absolute decoded-pixel differences range 1.04–3.47/255. This is a correspondence
check, not a claim of identical files or exhaustive pixel equality. The run receipt
must identify the actual repository encoding. The comparison times are not model input.

## Validation needed before production

Evaluate returned claims against original video, including ordinary carries,
passing preparations, failed moves, teammate actions and occlusions. Test unrelated
videos without supplied target moments; this one fixture cannot establish recall,
precision or generalisation. Native-video discovery timestamps remain approximate.
Only independently reviewed observations should later be projected through one
shared publication representation into online report and PDF. No report wording
is generated or published by this probe.

## Run

```
python backend/scripts/probe_feint_evidence.py --video VIDEO --anchors ANCHORS --output NEW_DIR
```

This performs offline preparation only. Add `--run-model` with the existing
`EMERGENT_LLM_KEY` environment variable to send requests. Never pass credentials
in arguments or persist them in artifacts.

The GitHub experiment triggers only when its same-repository draft PR opens, on
`experiment/feint-model-evidence`, first attempt only. Existing historical experiment
gates are unchanged. The uploaded artifact contains the actual receipts and source
images for review and expires after 14 days.

## Actual native-video trial

Run `39611370114` at code commit `aa370f1161fd204f892ef00a06ab8b867f4c7809`
completed both real calls. Gemini discovery took 47.579s (334,452 tokens reported);
Astra source-frame review took 26.835s (119,187 tokens). These are model-call times,
not end-to-end processing or user waiting time. One shield-turn was supported near
9s; five other candidates were rejected as feints in the supplied review frames.
The discovery missed important relevant intervals and described several unrelated
shots/passes and unsupported outcomes. **This native discovery is not suitable for
production feint evidence.** Raw receipts and source metadata are retained in
`docs/examples/feint-native-experiment-receipts.json`. The initial CI setup failure
occurred before any model request; a missing dotenv test dependency was corrected.

## Source-sheet alternative

`backend/scripts/probe_feint_frames.py` is a separate, generic whole-source trial.
It covers the complete input at 8 source frames/s, in fixed 27s chunks with 2s
boundary overlap. Exact frame IDs and source timestamps are printed on every tile;
original source selections provide identity only. No earlier model candidate,
expected event time or historical report is read. At most three Astra image calls
are made for an input up to 80s. Each returned claim must cite actual before,
movement, after and identity frames and original reference IDs. Overlap observations
are explicitly not deduplicated and cannot be used as unique dribble counts.
This remains an experiment; unrelated-video generalisation is unverified.
