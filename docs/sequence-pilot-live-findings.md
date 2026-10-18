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

Native-contact run 39143372317 completed in 32.797 s (25.155 s model call).
Its actual response separates #15's cross at 56.448 s, #10's finishing contact
at 57.164 s and the goal at 57.264 s, with #13 uninvolved in the final contact.
No explicit model question remains. Independent source-image inspection agrees
with this sequence. This documents one assist, not the complete five-action goal.
The 145-image request (including 91 native source-rate crops) was 14.433 MB.

## Full-source trial of the demonstrated input approach

Reuse the source/reference-hash-matched identity-only receipt, not action answers.
Read all ten source-derived packets with GPT-6-sol, 1280 edge, high detail and 8 fps.
Preserve original in-play selection references beside canonical examples.
Respect explicit unresolved model questions even when estimated contact fields
are filled; uncertainty about the finisher also keeps a proposed assist unverified.
One targeted native-contact review can answer such a question with new evidence.
Choose only unresolved target-related releases, one review per source packet,
at most four within the same 300-second overall budget. A single shared decode
prepares all native contact crops; retain every overview source instant.
These limits constrain work, not desired event counts. No reference answers
or previously observed action results enter the full-source trial.

The source video and original taps were published as test input with the
owner's explicit permission. Credentials remain in GitHub Actions secrets.

## Resume the completed full-source trial without repeating model work

Run 39143973766 completed all ten initial GPT-6-sol requests. Preparation took
19.565 seconds and the analysis phase 149.166 seconds, but the five-action goal
was not achieved. The follow-up planner wrongly excluded uncertain contacts
labelled RUN or DUEL, and missed selected-player control before a later chance.
The planned goal review also exceeded the wire-size limit and was never sent.
These are observed failures, not evidence that a green workflow proves accuracy.

The next experiment reuses those ten exact raw initial responses, after checking
source, original taps, packet fingerprint, response hashes and model identity.
No initial or identity model call is repeated. Up to six reviews are derived
from actual unresolved observations, including selected control before a chance.
Each review reads the complete source play and replaces its coarse observation
graph; original responses remain saved. An explicit model question still prevents
the questioned action or dependent assist from being counted as documented.

Every 8-fps overview instant is retained at 768-edge JPEG quality 70. Contact
detail uses native source-rate crops at 1280 edge, JPEG quality 60, with bounds
derived from original tap geometry; cited outcome instants receive native crops
too. Source timestamps and crop hashes are recorded. This controls wire bytes
without deleting contact instants. Model quality must still be verified against
the real source. Cached-resume elapsed time is not fresh end-to-end analysis time.

Run 39145583264 completed all six native reviews in 77.947 seconds, reusing
all ten initial responses without new initial calls. All six wire payloads fit.
None of the five reference cases was verified. The saved shot was labelled
OFF_TARGET; goal outcome remained unknown; two earlier assists were lost to
an alleged opponent recovery or an obscured release; the previously documented
last assist was now an uncertain shot. Native detail alone is not a reliable fix.
Do not replace this result with the earlier isolated success or remove uncertainty
checks to improve apparent counts. At this commit 97 isolated GitHub code tests
passed; those tests do not validate model perception.

Next controlled probe uses the review with highest original-tap density, chosen
without reference event answers. Reconstruct its exact low-reasoning wire payload
and require its hash to match run 39145583264 before sending anything. Then change
only reasoning_effort from low to medium: same model, images, ordering, timestamps,
identity examples and question. One new call, 150-second overall bound, 120 seconds
per call. Compare actual observation accuracy and latency; no full-source replay.


Run 39145977560 changed only low to medium reasoning on hash-identical input.
It took 47.779 seconds including detail preparation (40.424 seconds for the call)
and still could not establish the passing and finishing contacts. Extra reasoning
alone did not recover the previously observed assist.

Next controlled call retains the exact 145 image bytes, ordering, timestamps,
references, model and low reasoning from run 39145583264. Only an additional
contact-evidence instruction changes: a short before/after bracket may express
a uniquely visible actor when the exact simultaneous foot/ball instant is absent.
It requires two cited source instants, concrete motion evidence, a unique actor
and at most one second; contact_ms stays null. Explicit unresolved questions,
ambiguous actors, spare balls and unconnected outcomes still prevent approval.
This is an experimental representation, not a waiver of physical evidence or
a production change. The previous baseline payload hash must match before the
new request is sent, and ordered image hashes must remain identical. One new
call, 150 seconds overall, 120 seconds per request. No expected answers enter it.


Contact-representation run 39147827003 took 33.776 seconds including detail
preparation; the model call took 24.052 seconds. It confidently assigned the
recipient's goal to number 15 and omitted number 10's finishing touch. The
result is an incorrect goal, not an assist recovery. A contact bracket does not
make an incorrect causal reading correct. Do not promote this experiment.
107 isolated code tests and production verification passed; perception failed.

Next focused test restores the native detail geometry/quality of the earlier
source-inspected success: union of original local boxes with one player-height
margin, JPEG quality 80. The overview stays exactly at the failed baseline's
768 edge/quality 70; original source instants, order, question, references,
model and low reasoning stay fixed. No contact-bracket instruction is added.
The old wire hash is first reproduced. This tests the combined native-detail
delivery policy, not an isolated claim about JPEG quality. Preflight retained
all 145 image appearances and fits at 10,583,205 bytes. At most one new call,
150 seconds overall and 120 seconds per call. If this does not recover the
known source-inspected contact, stop scaling this approach to the whole video.


Restored-detail run 39148103504 took 42.179 seconds including preparation
(23.044 seconds for its model call). It still described a number-15 shot into
goal and left a contact question; no assist was established. Thus neither extra
reasoning, a contact-bracket instruction nor this restored crop policy reliably
recovers the contact. Do not scale these failed still-image variants to all plays.

The next single-play input is a different temporal representation: synchronized
normal-duration overview video (8 fps) and native-pixel band video (30 fps), both
covering the same complete automatically tap-density-selected source play. Source
interval and crop derive only from the original image packet and human boxes.
Reuse only the hash-matched identity profile; no historical action reply or
reference event answer is read. Original duration is preserved; audio is removed.
The output asks for players, ball motion and last touch, retaining native-video
times as approximate raw observations rather than exact-frame proof.

Local preflight: 5 identity pictures, 2 videos covering the same 5.999-second
source interval, 8,143,046 encoded request bytes, 3.393 seconds including encoding.
The available Gemini 3.1 Pro model gets one call, at most 120 seconds and an
overall probe budget of 150 seconds. This differs from the failed whole-video
Gemini trial by supplying a short complete play and synchronized native detail;
a successful response alone would still not establish all five reference cases.


Run 39148383227 stopped during preparation because ffprobe was absent from
the GitHub runner. It made zero native-video model calls. The local test passed
with installed FFmpeg; the GitHub test exposed the missing workflow dependency.
Both model and isolated-test workflows now explicitly install FFmpeg before
any credential-bearing step. The same native-play experiment is retried once.


Run 39148519061 encoded both views and received HTTP 400 in 1.193 seconds,
without observation output. Overall probe time was 6.585 seconds. The new
30-fps request exceeds Google's documented VideoMetadata.fps maximum of 24
(https://ai.google.dev/api/generate-content#VideoMetadata). The transport now
rejects sampling above 24 locally, and native detail encoding/sampling uses 24
fps. The synchronized views, source interval, prompt, model and references
remain the same. No claim about perception exists for this rejected request.
109 isolated GitHub code tests passed at the preceding commit.


Run 39148754244 completed the 24-fps synchronized video call in 24.973 seconds;
probe time was 31.459 seconds, plus 18.945 seconds full-source preparation.
The selected play was 53.015–59.014 seconds. The returned model swapped the
selected passer with the final recipient, described an uncertain goalkeeper
interaction and returned UNKNOWN outcome. No assist was established. The raw
response and input hashes are retained in the run artifact. A green job is
execution success, not football accuracy.

Next single-call comparison keeps both encoded views, model, profile and source
interval fixed. Reference labels now include existing source timestamps and
normalized original human selection boxes/points. Local references also carry
clip-relative times so the model can ground identity in the actual play rather
than matching jersey numbers across unrelated pictures. These are original
selection metadata, not action labels or evaluation answers. Ambiguous crops
must remain uncertain. This input change still needs real model verification.


Run 39149030812 tested textual source times/normalized selection coordinates
with the same video views. Its call took 22.670 seconds; probe time was
29.045 seconds. It still swapped identity onto the final scorer and incorrectly
attributed a goal to the selected player. Textual coordinate labels did not
recover the assist. Original geometry is now also tested visually as below.

Next focused input adds the original local human marks in full-source context:
only their original boxes and positive points at the actual original tap PTS,
with source/clip times. The videos remain unannotated. No marker is propagated
to another instant, no detector identity is asserted, and no event is annotated.
This tests spatial identification information lost by crop-only references.
The original source is hash-checked and unchanged. The two added pictures were
visually inspected: both boxes enclose the trailing white number 15, separate
from white 13 and 10. Clicks are user geometry, not precise body-centre truth.
All video views, source interval, prompt and model remain as the supported-rate
run. One additional call under the same 150/120-second bounds. Offline input
fits at 8,409,638 bytes and prepares in 3.937 seconds.

Native-probe CLI now exits nonzero for a model error while preserving the
actual failure receipt; a completed GitHub job must not hide model access failure.


## Visual selection trial result, 2026-10-18

Run 39149235839 completed the model call in 14.219 seconds, with 21.688 seconds
probe execution and 19.316 seconds separately measured full-source preparation.
This reads only the 5.999-second source play, not the complete 76.76-second video.
The seven-image/two-video request was 8,481,194 bytes. The 116 isolated GitHub
code tests passed; that is not a perception acceptance result.

The raw reply labels p5 as the selected white number 15 and describes him as
a passer, while p1 is white number 10 and the final scorer. This corrects the
previous selected-player/scorer swap in the returned description. However, it
adds an intervening number-13 shot, goalkeeper save onto the post and rebound.
These claims are not supported by the source-inspected sequence and do not
establish the direct 15-to-10 assist. Do not accept this as a verified assist,
all-five success, complete-video timing, or production-ready replacement.
The exact response, source hashes, annotated selection geometry, model usage
and request hashes are retained in the run artifact:
https://github.com/9m92yk9snt-star/VedoScout/actions/runs/39149235839

The remaining defect is the physical possession/contact chain after identity
selection, not simply missing runtime dependencies or insufficient reasoning.
No further identical-input votes are justified by this result. The next useful
implementation must preserve source-grounded actor continuity and test the
alleged intervening contact with actual before/after ball motion, while keeping
uncertainty when the evidence does not resolve it. Production remains unchanged.


The proxy catalog also lists gemini/gemini-3.8-flash. A final controlled model comparison changes only the model to this available video model. The previous spatial-reference request's full wire payload hash must reproduce exactly before any paid request is sent. The new request body must be identical apart from its model field; input bytes, order, video sampling, original selection geometry, profile and prompts remain fixed. The baseline action reply is checked for integrity and never inserted into the prompt. One call, 150 seconds overall and 120 seconds per call. This tests a different model, not another vote from the failed model.
