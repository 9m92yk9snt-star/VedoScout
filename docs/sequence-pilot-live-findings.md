# Actual model experiments: Orman400

These are standalone source-image experiments, not production report latency.
Expected reference answers are evaluated after requests, never supplied as input.
No merge or deployment is justified by the results so far.

| Run | Preparation | Model phase | Reference matches | Quality |
| --- | --- | --- | --- | --- |
| 39138207424 | 17.809 s | 175.529 s | 0/5 | Two of three calls timed out; remaining response misattributed the goal. |
| 39139382430 | 16.540 s | 184.007 s | 2/5 | All 12 calls returned; saved shot and goal matched. All three assists missing, with additional incorrect scoring events. |
| 39140261843 | 12.051 s | 138.170 s | 1/5 | All ten initial calls returned; follow-up preflight stopped at the byte cap. Only goal matched; saved shot became a false goal. |
| 39140714682 | 16.633 s | 186.506 s | 1/5 | Shared profile correctly inferred #15, but action attribution/outcomes still failed. Five unexpected scoring events; not accepted. |

Run 2 uses source-image scene candidates, raw selection consensus, 8 fps and
low reasoning effort. The evaluator's two time matches are not independent
visual proof. Raw responses are preserved in each run's evidence artifact.
All five production code verification jobs at fc5f535 passed; code checks do
not prove football perception.

Inspection of the actual raw responses identified perceptual errors before
the resolver: sequence_007 calls a white recipient a blue opponent;
sequence_008 invents an intervening pass; followup_002 assigns the selected
identity to white #10. Sequence_006 conflates adjacent play contexts. Source
image changes are candidates, not reliable edit boundaries on the same pitch.
Removing causal checks would turn these errors into confident wrong statistics.

## Controlled resolution comparison

Next run changes only preparation's maximum image edge from 768 to 1280.
Same source checksums, ten raw references, model, 8 fps, prompt, packet plan,
two workers, reasoning effort, follow-up rules and budgets are retained.
The source stays uncropped. No action time or expected outcome determines
which images receive more pixels. Offline preparation retained all 622 sampled
instants and 704 packet appearances. All ten initial wire requests fit the
19.5 MB cap; largest is 14,917,983 bytes. This establishes deliverability,
not a prediction that the model will recover the missing assists.

The resolution comparison did not improve perception: it still confused #15,
#17 and #13, and mistook the spare-ball outcome for a goal. Keep 768 as the
baseline rather than paying for more pixels without demonstrated improvement.

## Shared identity experiment

Infer one identity profile from all ten original crops in a separate reference-only
request. No action timeline, expected number or expected events are supplied.
The model chooses up to three complementary clear reference crops and a visual
description. Reuse these throughout every play, reducing repeated identity
inference and reference images. If no coherent identity emerges, stop explicitly.
The profile is model evidence, not independent truth or an approval of actions.
All action instants, 8 fps, scene packets, model and low reasoning effort stay
at the run 2 baseline. The profile consumes the same overall 300-second budget.

Also isolate byte-cap failures to their packet: preserve its NOT_SENT receipt
and run other deliverable packets without dropping any source frames. A local
regression verifies that oversized input cannot silently produce full success.

The profile run does not demonstrate improved action correctness. The next probe
is limited to one source packet, chosen by original tap density per source second,
with identical inputs/profile compared at default versus explicit high model detail.
It does not run or evaluate all five actions. Both previous resolution runs reported
exactly 251,302 initial prompt tokens despite different JPEG bytes. This is a measured
delivery ambiguity, not proof of a specific upstream resize. The probe also requests
the normal read-only proxy model list, exporting only model IDs, with no redirect
or alternate endpoint after an error. At most three model calls and 180 seconds.

Provider documentation: https://docs.litellm.ai/docs/providers/gemini describes
image_url.detail=high mapping to Gemini media resolution; this proxy's handling
must be verified from actual responses, not assumed from that documentation.

Focused run 39141150261 completed in 45.534 s plus 15-second-scale preparation.
Both Gemini 2.5 replies used exactly 15,738 image tokens and 18,814 prompt tokens
despite explicit high detail on one request. Both still assigned the selected
player only a run and misattributed the assist. No detail improvement demonstrated.
The authenticated normal model catalog returned gemini/gemini-3.1-pro-preview.
The next paired probe uses that available model on the same tap-density-selected
packet. Its temperature is left at the provider default, as Google recommends
for Gemini 3 (https://ai.google.dev/gemini-api/docs/gemini-3).
The profile request remains Gemini 2.5 for a consistent identity-only stage.

Gemini 3.1 focused run 39141394306 completed in 37.696 s. The default-detail
response attributed an assist at 56.764 s to #15, but the high-detail response
misidentified #13 as the selected player. Both used 67,068 image tokens. This
isolated match is not reliable five-action validation.

Next: normal-duration native video, using the available Gemini 3.1 model for
both identity and action reading. A 720x1280, 8 fps H.264 copy retains the full
source timeline without held frames; audio is removed. Compare requested native
sampling at 1 versus 8 fps on the SAME encoded bytes. At most three model calls,
240 seconds including encoding, 120 seconds per action call, two workers.
Raw JSON observations are retained separately: approximate native video times
must not be relabelled as exact-frame proof or silently passed through the
still-image citation resolver. No reference event answers enter either request.

Native run 39141841836 did not reach the video requests: Gemini 3.1 returned
the reference profile inside a one-element JSON array. The profile reader now
accepts that equivalent envelope while rejecting multiple profiles or unknown
reference IDs. No video sampling or perception result exists for that failed run.

Native run 39142076608 completed: 14.062 s preparation plus 79.682 s including
encoding, identity and both action calls. The identical file yielded 20,328 video
tokens at requested 1 fps versus 162,096 at 8 fps. This supports effective sampling
control through this proxy; a silent fixed 1-fps bridge is not the remaining
explanation for this experiment. Perception still failed: 1 fps invented times
past the 76.75-second video; 8 fps returned only one action and incorrectly called
the outcome a crossbar hit. These are raw observations, not accepted events.

Next bounded comparison: one GPT-6-sol still-image request on the same automatically
selected short packet, using a shared identity-only profile. The normal authenticated
catalog lists gpt-6-sol. No duplicate default/high call and no full-video rerun yet.
Use the reasoning-model completion budget parameter and leave temperature unset.
For this different vision model, use the already preflighted 1280-pixel source
edge and explicit high detail. This is a best-input model trial, not a claim
that model and resolution effects have been isolated. Source instants remain
the same 8-fps observations; no event navigation answers enter the input.

GPT-6-sol run 39142443248 took 38.518 s plus preparation (13.575 s identity,
24.456 s action reading). It retained uncertainty about the forward white runner
and number 10's final contact, so it did not establish an assist. It did not
silently award the receiver's goal to the selected person.

Next probe resumes that actual request/profile receipt without replaying either
completed model call. Verify source/response hashes, select the same tap-dense
packet, and inspect the model's own unresolved focused action. Preserve the full
core play, add 24-fps detail around its missing contact, and restore original local
selection crops alongside canonical references. The earlier profile reduction
had discarded in-play r8/r9 identity examples. Bound context to the source packet
core to avoid unrelated adjacent plays. No reference action answers are read.
This is one new model request, not a second approval of an already proven event.

Run 39142837172 returned a selected-player assist at 56.264 s in 38.331 s
(28.504 s model call), but the raw reply explicitly asks CONTACT for its inferred
#13 finishing touch. The resolver's filled fields are not independent confirmation
of that contact; do not report this as fully verified. The next request reuses
that explicit unresolved contact as navigation, adds native source-rate crops
around it, and retains the 8-fps whole-play overview. The crop spans the full
source width; its vertical band is derived from the existing in-play human boxes,
with one player-height margin. No detector coordinates or expected event times
are used. This changes actual visible detail rather than asking for another vote
on unchanged images. Each crop retains actual source PTS, bounds and checksum.

The source video and original taps were published as test input with the
owner's explicit permission. Credentials remain in GitHub Actions secrets.
