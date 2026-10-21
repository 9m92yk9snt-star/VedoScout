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

## Actual source-sheet results

Run `39613934001`, code `fab3b182996793271b98a4a3c81f80b353502fdb`, completed
three actual `gpt-6-astra` calls. The complete source was sampled without target
times: 232, 232 and 183 frames (including boundary overlaps). Returned calls took
40.491s, 28.653s and 19.816s individually and reported 230,442 total tokens.
These are individual call durations, not end-to-end/user waiting time.

The model returned five supported movement observations:

| Source interval | Model-supported observation | Immediate outcome |
| --- | --- | --- |
| 8.750–9.750s | Shield-turn | Retains locally; later loss remains separate |
| 20.249–20.882s | Direction change | Progresses; deception/defender beaten not established |
| 28.999–29.632s | Direction change | Progresses; precise trick not established |
| 42.748–43.382s | Direction reversal | Progresses; contacting foot unresolved |
| 62.381–63.631s | Direction change and protective turn | Progresses; overlapping contacts unresolved |

The human/model-assisted source review agrees that these are visible protective
turns or changes of route. It does not upgrade them into five successful take-ons.
A potential body dip near 8.1–8.8s remains uncertain as a deceptive body feint.
Other uncertain observations were returned near 3.5–4.25s, 21.25–22.13s and
34.88–35.75s. In particular, the latter model observation suggests an interception
or loss, while the wider already-reviewed play shows a pass to white #7; that
possession interpretation is not accepted. This is one reason the raw responses
must not directly overwrite canonical events or report statistics.

`docs/examples/feint-source-sheet-receipts.json` preserves all three raw responses,
usage, source/selection hashes, source-sheet hashes, original references and cited
source frames. Exact request payloads were reconstructed from the preserved source
sheets and original prompt, and all three request and response hashes verified.
The original preflight used the default 16384 output token budget while actual
calls used 12288; both audits are retained and the preflight code is corrected.
No further model request is needed for that audit correction.

The first source-sheet run `39612874577` stopped before model access because the
main transport lacked a newer local callback argument; the experiment now uses
main's interface. No model receipts were produced by that setup failure.

**Status:** a documented positive result on this footage; generic input support
exists, but accuracy and recall on unrelated videos remain untested. No production
analysis, PDF/web content, scores, merge or deployment changed. Next evaluation
must include another selected-player video, failed moves, ordinary carries/pass
preparations and occluded duels before production integration is considered.

## Extended-context follow-up

`recheck_uncertain_feints.py` selects the four uncertain incidents from the actual
raw source-sheet responses. It verifies their source, selection and response hashes,
adds one second before and four seconds after each movement interval, and prepares
only those contexts by one forward source decode. Neither user reference times nor
canonical outcomes are inputs. Movement and possession outcome each require their
own decision and citations; a supported pass requires a separate teammate, and a
supported loss requires opponent possession rather than proximity alone.

Run `39616673706`, code `a0c02f7f171639815e1ddb5f8bb69cb07863714b`, completed
one actual `gpt-6-astra` request on 186 context source frames. Preparation took
14.927s on the runner (10.598s locally); the model call took 39.591s and reported
80,328 tokens. These numbers exclude CI installation/queueing and are not live
production analysis time.

Results:
- Near 3.5s, movement remains uncertain; subsequent opponent possession is supported.
- Near 8.1s, the body dip remains uncertain as a feint; immediate retention is
  supported. The later fall/loss is explicitly separate.
- Near 21.25s, the extra cut remains uncertain; the model supports intervening blue
  possession. Its uncertainty about a later striking contact does not supersede
  existing higher-detail saved-shot evidence.
- Near 35s, a feint is rejected and the pass to a separate white teammate is supported.
  This corrects the earlier tentative interception/loss interpretation after following
  the recipient into the subsequent carry and shot. Source review of that expanded
  sequence agrees with the pass interpretation.

No uncertain movement was promoted to a supported feint. The earlier five supported
movement observations remain a separate set; these are not successful take-on totals.
Raw response, source-frame metadata, original references, usage and duration are in
`docs/examples/feint-uncertainty-context-receipt.json`. The exact submitted request was
reconstructed from preserved source sheets and prompt; request/response hashes and
all source-JPEG hashes verified. Twenty-two offline contract/regression tests pass;
the live follow-up workflow also passed its then-current 21 tests.

Independent-video testing remains blocked by the available footage: the inspected
older uploaded Almin test07 versions show the same recording at the sampled instants.
The repository's other MP4s are a non-match clip and generated introduction cards.
These do not establish new-match generalisation. A different match video, preferably
with its existing original selections/evidence export, is required for that test.
No production reports, scores, canonical events or layout have been changed.
