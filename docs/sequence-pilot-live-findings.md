# Actual model experiments: Orman400

These are standalone source-image experiments, not production report latency.
Expected reference answers are evaluated after requests, never supplied as input.
No merge or deployment is justified by the results so far.

## Follow-up source review and the remaining attempt outcome

Manual reinspection of original instants 49.131, 49.348, 49.565 and 50.198s,
alongside the earlier release images and the owner's red/black-arrow screenshot,
does not establish anatomical foot side through the occlusion. The rear white
sock is easier to distinguish than the ball-side leg; the pelvis-to-knee-to-foot
connection at release is obscured. LEFT remains the actual model claim, RIGHT
the owner's reading, and independent side verification remains false. No raw
reply or approved assist is rewritten by this review.

The next bounded probe selects the unique ACTIVE_BALL_OUTCOME_AFTER_ATTEMPT
gap from the existing native-source model observations: sequence_003,
19.266–25.631s, with continuous native detail at 23.566–25.366s. The old claimed
outcome only schedules inspection; it is not supplied to the new model. Original
identity references, full-play overview and native images go through the existing
event schema and resolver, including its existing contact-bracket support. No
expected result is prefilled. A stationary ball inside the goal and the moving
ball near the goalkeeper must be distinguished using their source motion.
The probe makes at most one GPT-6-astra medium request, with a 120-second request
limit, and retains the actual receipt separately from source preparation and
any resolved events. A completed request does not establish a saved shot.

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


Run 39149532820 stopped before any model call: COMPARISON_INPUT_NOT_IDENTICAL.
Inspection of its artifact showed that both annotated JPEGs exactly match the
baseline, while re-encoding produced different MP4 bytes (overview 3,119,886
versus 3,120,074 bytes; native detail 2,834,413 versus 2,835,083). Identical source
and encoding settings do not guarantee identical encoded files across runners.
The exact-input guard was retained. The comparison now downloads the measured
baseline's own two MP4s through the normal GitHub artifact API, copies them
without invoking the encoder, and still requires the complete old request hash
to match before changing only the model field. A regression checks byte-exact
reuse and that no encoder process runs. No failed comparison is counted as a
Gemini 3.8 perception result.


Run 39149857306 reproduced the complete baseline wire hash and changed only
the model. Gemini 3.8 Flash returned in 8.198 seconds (9.637 seconds probe time,
excluding separately measured full-source preparation). Its ending sequence is
selected white 15 playing toward goal, then white 10 tapping the moving ball in;
white 13 has no intervening action. This matches the source-inspected ending.
The native approximate release time is early, and the opening midfield possession
still needs inspection; do not claim exact contact time or all-five correctness.

Next trial reads every source-derived packet with the same model/input approach.
No reference event time, count or outcome guides the packet plan. In-play original
marks appear only where actual taps exist; packets without taps retain canonical
identity pictures and a full-frame overview, with no invented local markers.
All nine new request preflights fit the 19.5 MB cap; largest about 17.02 MB.
The demonstrated play is reused only if the newly constructed request exactly
matches its Gemini 3.8 receipt; that completed call is not repeated. The other
nine packets make new calls with two owned workers, 90 seconds per call and a
300-second combined preparation/model budget. Actual video encodes retain normal
duration. Raw native times/observations stay separate from exact-frame approval.
Elapsed time in this resumed trial must not be relabelled a fresh ten-call
production-analysis time. Production is unchanged and all five remain unproven
until the returned observations and source evidence have been examined.


All-play run 39150431172 completed all ten packet observations: nine new Gemini
3.8 calls and one exact-request cached response. Native preparation/model work
took 108.837 seconds, including 48.176 seconds of request preparation. Full-source
preparation separately took 12.129 seconds, for 120.966 seconds in this resumed
trial. No request exceeded the byte cap. This is not fresh ten-call production
latency. The raw observations match the selected goal and the last 15-to-10
finishing sequence. They still call the saved-shot reference a miss and give
number 15 the recipient's goal in the middle attack. The earlier assist includes
an explicitly unresolved defender touch/control. Other-play identity also remains
inconsistent. These results do not establish five correct actions or production
readiness. No broad replay or deployment follows from the execution success.

Next bounded review plans three source gaps from the actual native observations,
not the reference-answer file: an own attempt labelled miss with a keeper; an
explicit uncertain intervening contact in a scoring play; and an attributed own
goal without an in-play human identity example. It retains every prepared 8-fps
whole-play instant and adds 24-fps native-pixel detail around model-derived times.
The detail crop is the union of original selection vertical extents/margins across
the source, avoiding the earlier narrow band that could lose a later ball outcome.
Original visual identity marks are retained; the old model's speculative appearance
contradictions are not supplied as facts. No expected saved shot, assist, goal or
event time is provided. Responses remain raw observations for source review.

The available GPT-6-astra gets these three image requests with medium reasoning,
two workers and 120 seconds per call. The resumed native trial's 120.966 seconds
are subtracted from the same 300-second accounting bound, leaving 179.034 seconds
for source preparation and these reviews. Offline source preparation took 7.945
seconds; request sizes are 13.479, 14.665 and 12.205 MB. All fit without deleting
whole-play instants. Actual correctness and time remain to be measured.


Source-gap run 39151281244 completed all three GPT-6-astra image requests.
Preparation and calls took 124.775 seconds (source image preparation 10.844);
the separate repeated whole-source preparation took 19.279 seconds. Calls took
48.360, 46.278 and 67.319 seconds. The shot review now gives concrete active-ball
evidence for a goalkeeper parry: contact region around 24.366 seconds followed
by a slower, floating departure, descent and bounce outside the near post, with
the spare stationary. The earlier-assist review supports number 15's pass, a
glancing defensive touch without controlled possession and a distinct teammate
shot into goal; the receiving touch remains occluded. The middle-attack review
favors a separate teammate as finisher but explicitly cannot securely resolve
the hidden striking actor. Do not turn that uncertainty into an approved assist
or retain the earlier wrong own-goal attribution as confirmed.

The next review is one new Gemini 3.8 image call for that explicitly unresolved
final-touch actor. It downloads the previous checked source JPEGs and manifest;
all original overview/detail image hashes must match the earlier wire audit in
order. Canonical identity crops are recovered by exact source PTS and their
original JPEG hashes. No whole-source decode or completed model call repeats.
A pixel-only white/blue kit mask proposes a tighter cluster around the actual
model-derived contact focus. It does not label a person, ball contact or result.
The unchanged whole-play overview remains alongside the newly cropped detail.
A blank/uninformative mask falls back to the full checked source band. Every
new crop records its parent JPEG hash and original-source bounds. Geometry is
unit-tested before the credential-bearing model step.

The native/source-review work plus repeated preparation accounts for 265.020
seconds so far; this last preparation/call gets at most the remaining 34.980
seconds of the 300-second accounting bound. This remains a series with cached
work, not measured fresh production latency. Correctness is still unproven for
the hidden finishing connection. Code, source observations and explicit failed
readings stay preserved; production remains unchanged.


Cluster run 39152285766 passed cached image integrity and crop preparation, but
its final model request exceeded the remaining 34.98-second accounting bound.
It returned no observation, so the hidden finishing actor remains unresolved.

A separate one-off workflow now tests a different bounded detail input without
altering the existing refinement workflow. The only navigation is the saved,
hash-checked response's explicitly unknown finishing actor. Eight sparse local
person detections choose a common full-width viewing band, unioning every detected
person with body-height margins. They assign no player identity, contact or event.
All 46 whole-play overview instants remain, alongside every native source instant
in the unresolved interval. No previous speculative action text or expected event
answer is sent. This is a single-play delivery trial, not an isolated-model-effect
comparison or a fresh full-video latency result. It has a separate 90-second probe
bound and one request limited to 45 seconds; it must not be added to the previous
300-second run and represented as within that original budget.

Local preflight: 3.127 seconds, 8 detector forwards, 109 source contact instants,
18,074,269 request bytes, original source and original selections hash-checked.
122 isolated local tests passed before adding the two existing cluster tests.
This preparation/test success is not evidence of perception success. Actual model
response is pending. The production pipeline remains unchanged.

Run 39152527031 completed that actor-continuity call in 16.652 seconds; the
probe took 17.959 seconds including 1.191 seconds preparation. The separate
whole-source preparation took 12.409 seconds. All 109 native contact instants
and 46 overview instants were delivered in the measured 18,074,269-byte request.
The eight sparse person detections produced the same [0,751,1080,1317] source
band as local preflight. Runtime execution succeeded; perception did not.

The response labels white number 13 as selected, while assigning canonical r2
and r7 to a non-selected shooter and r6 to the claimed selected player. It omits
the selected player's passing chain and reports a different actor's goal.
This does not establish the unresolved assist or correct selected identity.
The earlier source-inspected 15-to-10 ending is retained separately; it must not
be substituted for this failed middle-attack result. Actual receipt and response
hashes are retained in docs/examples/native-actor-continuity-receipt.json and the
workflow evidence. 124 isolated local tests passed; GitHub's isolated suite also
passed. No further identical-input vote, full-source replay, merge or deployment
is justified by this result. The next useful experiment must resolve physical
identity across local play context before treating another contact verdict as
selected-player evidence. Detector-bounded native detail alone did not solve it.


Post-response identity consistency check: the actor probe now asks for separate
positive reference_ids and source evidence_frames. A free-text citation alone
cannot establish whether it means the same person or a negative comparison.
The retained 39152527031 response therefore remains UNRESOLVED under this
structural review; its original receipt and response hash are unchanged. See
native-actor-identity-review.json. No model request was repeated for this check.

The canonical event resolver also now rejects selected-player credit when
positive matches to the same selected identity profile are split between
separate physical people, including a person marked false or unknown. It does
not choose a winner or reinterpret a negative comparison as a positive match.
The actor probe records this review separately from transport COMPLETED, and
STRUCTURALLY_CONSISTENT explicitly does not mean visually verified or approve
any events. Thirteen new regression cases pass locally, including replay of
the retained failed actor response and the actual event resolver's assist path.
The source inspection still cannot uniquely establish the middle finishing
actor; all-five acceptance and fresh full-source latency remain unproven.

## Complete pass-to-finish detail experiment

The owner clarified that the intended review is the earlier play beginning near
42 seconds, with a turn, release to a teammate and an obscured finishing foot.
That clarification selects the play for diagnosis; it is not supplied as the
model's expected answer and does not make this a blind full-video recall test.

The existing sequence_006 review's native detail ended at 44.932 seconds, while
its actual returned shot bracket was 45.382–45.765. That finishing contact was
only represented in the coarser full-play overview. The new pass-finish mode
derives two detail windows from the saved, integrity-checked pass and shot source
frame IDs, padded by 250ms: 43.732–44.382 and 45.132–46.015. These are observed
contact brackets, not reference-event timestamps. It preserves the complete
38.632–47.264 source-play overview, including the original in-play selections.
No historical action wording, desired assist or reference answer is inserted.
The prompt retains uncertainty if before/after movement cannot determine a touch.

All 70 overview instants remain at 768-edge/quality 70, beside 94 original-rate
source contact instants in the shared full-width person-union band. Preparation
took 2.917 seconds with seven sparse detector forwards. The preflighted request
is 17,275,044 bytes. Missing the later finishing window now fails the coverage
check even when the passing window is complete. Four new regressions and all
141 relevant local tests pass. One Gemini 3.8 Flash call has a 45-second request
limit and a separate 90-second probe bound. This is not fresh full-video timing.
Actual response and football correctness remain pending; production is unchanged.

Run 39154736273 completed the two-contact Gemini 3.8 trial. Its call took
23.879 seconds; probe preparation/model time was 26.679 seconds, plus separately
measured whole-source preparation of 19.049 seconds. The selected identity is
structurally consistent, and the reply separates selected 15 from the finisher.
However, it credits the finishing action to blond white 12 at 45.765–45.815,
omitting the earlier dark-haired white attacker's striking movement. Source
inspection does not support accepting that finishing attribution. Structural
consistency is not visual correctness or an assist approval.

One controlled reader comparison now uses the exact same input messages/images
with GPT-6-astra at medium reasoning, the reader that previously described the
dark-haired finisher but lacked these native finishing images. The completed
Gemini request's full wire hash must reproduce before any new model call. Its
reply is integrity-checked but never supplied as instruction or evidence. Model,
reasoning effort and provider completion-budget parameter change; this does not
isolate reasoning from model choice. One new call, at most 90 seconds, with a
separate 120-second probe bound. Local preflight reproduced the full Gemini hash
b260f2edf69c5b4e2e30c52f047438dbd75169e471874d69fc120abeb5bbc0c1.
The 142 relevant local tests pass, including rejecting changed comparison input.

Run 39155042754 reproduced the full baseline hash and returned in 67.982 seconds;
the probe took 70.918 seconds plus 18.903 seconds separate source preparation.
It tracks the original r2-marked person through reception, turn and release,
describes a blue contact without established control, identifies the dark-haired
forward teammate as the finishing attacker and sees the goal. It correctly keeps
the blond player separate from that striking movement. It retains uncertainty
about a possible defensive touch at the hidden foot/ball instant. Crucially,
it assigns r2/r6 to the releasing actor and r7 to a different person; selected
identity therefore remains UNRESOLVED. This is not an accepted assist.

The next bounded comparison changes only the scope of identity reference images.
When an original human selection exists inside this source play, use that local
selection and its original full-source cyan mark as the identity anchor. Keep
all source-play frames, detailed contact instants, model, reasoning, question and
identity consistency gate unchanged. References from other plays remain in the
original data and are not declared incorrect; they are unnecessary appearance
comparisons for this local track. Missing a local selection causes explicit stop.
This is a general local-context option, not a jersey-number or event-time rule.

Before narrowing references, the prior GPT-6-astra request must reproduce hash
bc0a51feeb11e15d910cee00a696f364a69547cf49e967d9ca39ab1949bd4b95.
Then only the out-of-play r6/r7 identity picture/label pairs are omitted; the
original in-play r2 selection stays. The baseline action reply is never supplied.
Local preflight: 2.829 seconds, 17,245,280 bytes, all 70 overview and 94 native
contact instants retained. All 143 relevant tests pass. One 90-second request,
120-second probe bound; actual perception result remains pending.

Run 39155426908 reproduced the previous full GPT-6-astra request before removing
only the two out-of-play reference pairs. All source-play images/timestamps,
contact windows, prompt, model and reasoning remained unchanged. The call took
66.735 seconds; probe time was 69.455 seconds including 2.536 seconds preparation.
Separately repeated whole-source preparation took 17.499 seconds. This is one
8.6-second source play, not fresh full-video latency or a five-action PASS.

The returned original-r2 track is selected=true and uniquely identified. The
response follows reception, outward dribble, turn and release, keeps the selected
player back on the left, identifies a different dark-haired white forward as the
finishing attacker and observes the active ball continuing into goal. Blond p3
is separate; no new touch by that player is established. The identity consistency
review now passes STRUCTURALLY_CONSISTENT without changing its rejection rules.
This is an identity improvement on this local play, not independent event proof.

The source-supported finishing movement is assigned to p4 despite the obscured
foot/ball instant. A defensive touch at that shot cannot be excluded. The remaining
pass-to-finish gap is p6's attempted interception: the response cannot conclusively
distinguish a light touch from the ball passing the boot and does not establish
controlled possession. The hidden passage before p4 appears at the ball remains
explicitly uncertain. Do not manufacture a complete direct-assist approval from
that response or count the teammate's goal as the selected player's own goal.
The actual reply, source brackets, timing and comparison hashes are preserved in
docs/examples/native-pass-finish-local-receipt.json and workflow 39155426908.
143 relevant local tests and GitHub's isolated suite pass. All-five correctness,
the direct-assist connection and fresh full-video latency remain unproven.

## Continuous passage through the attempted interception

The owner explicitly requested one cropped-play experiment on the earlier assist.
The reader retains the full 38.632–47.264s source-derived play and the original
r2 in-play identity anchor. It rebuilds the exact local-anchor request from run
39155426908 and checks its complete wire hash before changing any input.

The previous 60-fps contact windows had a 44.382–45.132s gap covered only by the
8-fps overview. Add native-pixel source samples at 24fps across that gap, keeping
all 70 original overview images and all 94 previous native contact images byte
for byte. The 18 added samples make the maximum detailed-source gap 50ms. Only
the newly added JPEGs use quality 80 to fit the request cap; no existing image
or source instant is removed or recompressed. Original source timestamps remain.

The neutral prompt also requests explicit evidence for same-ball passage to the
receiver, that receiver's finishing movement, the goal, defensive contact and
intervening control/deliberate passing. It supplies no desired assist, no assertion
that a defender missed, and no expected result. The prior action reply is not sent.
This changes both delivery and the observation schema; it is not an isolated
measurement of either change alone.

An experimental link review requires all three affirmative links, distinct
selected passer/receiver-finisher identities, valid supplied source citations and
no observed intervening control. A possible unconfirmed defensive touch alone
does not veto otherwise supported links, but NOT_OBSERVED control cannot fill
a missing or uncertain same-ball/receiver/goal link. Structural and link reviews
are still model-observation checks, not independent visual proof or production
canonical events. The source review and actual response determine whether this
particular experiment is useful; no desired answer is hard-coded.

Local preflight: 3.927 seconds, 19,198,197 request bytes, all prior image hashes
retained, 18 new detail samples, JPEG quality 80 for those new samples only.
156 relevant local tests pass, including unsupported links, identity conflicts,
invented citations and observed intervening control. One GPT-6-astra medium call,
90-second request and 120-second probe bounds; the actual result follows.

Run 39161654199 completed successfully on commit 3f335cc. GPT-6-astra medium took
61.037 seconds; preparation plus the model probe took 63.362 seconds, including
2.206 seconds probe preparation. Separate whole-source preparation took 12.826
seconds. This is a measured isolated 8.632-second play, not fresh full-video
latency. The 19,198,197-byte request retained all previous image hashes and added
the 18 original-source bridge instants. The actual reply and measured result are
saved in docs/examples/native-continuous-pass-receipt.json; its unmodified response
hash is 2ba52e4798ceb6c96cc3feca0d40cca80e85b4f24d60460fa6f1b21dced9a1da.

The model now affirmatively supports all three physical links: p1's release to
p4's reception, p4's finishing movement, and the goal from that finish. It cites
the continuing ball emerging beyond the reaching defender at 44.598s and entering
the recipient's channel, rather than inferring the pass only from a lack of
defensive control. The selected r2 player is uniquely p1; p4 is a different
dark-haired white attacker, while the blond teammate remains separate. The
identity review is STRUCTURALLY_CONSISTENT. The experimental link decision is
ASSIST_SUPPORTED_BY_MODEL_OBSERVATIONS, with no missing-link reasons.

Intervening defensive control is NOT_OBSERVED. Defensive contact is UNCERTAIN:
the response does not demonstrate a touch or interruption at the reaching boot,
but cannot exclude a slight brush there or around the finishing action. Thus this
result does not establish the stronger claim that no defender touched the ball.
An unproven hypothetical brush does not veto the separately supported attacking
chain. The attacking finisher is identified; absolute last-touch ownership is
left null. This distinction is deliberate, not a removal of uncertainty.

Manual source inspection agrees with the distinct selected passer, central
finishing attacker and moving ball in goal; the bridge shows the defender reaching
and the ball continuing. It does not independently resolve every possible brush.
The experiment therefore supports this assist, but emits no production canonical
event: target_events remains empty and independent_visual_correctness_verified
remains false. No merge or deployment; the earlier #15-to-#10 ending is preserved
separately. Five-action correctness and fresh full-video latency remain unproven.

The final local suite passes 160 tests. Four additional contradiction tests require
an explicit overall GOAL outcome, so an asserted goal-link cannot override SAVED,
NO_GOAL, UNKNOWN or a missing outcome. Rechecking this saved actual reply against
that guard preserves the supported-assist result without another model call.

## Automatic approval through the existing assist resolver

The owner clarified that this play must reach the same automatic event decision
as the previously documented later assist. The continuous reader previously
stopped at a link-support label and left target_events empty. Add a typed mapping
from its observed contact_chain into sequence_pilot.resolve_response/reconcile,
the existing event path used for that later assist. The event resolver itself and
its contact/identity requirements are unchanged.

The model must explicitly identify the pass, reception and finish rows, the
teammate relationship, same active ball, continuous play, unique attacking actors
and a source-cited goal frame. The mapper checks source/request/response hashes,
recomputes identity and physical-link checks, validates chronology and intervening
actions, and preserves short contact brackets instead of inventing exact touches.
It feeds a PASS ending in TEAMMATE_GOAL and the recipient's bracketed SHOT into
the resolver. Only an eligible selected-player ASSIST with no unresolved question
or conflict receives APPROVED. Defensive-contact uncertainty remains attached.
No expected answers, player numbers, row indexes or source times choose the event.

The previous actual reply lacks the typed event mapping and remains unchanged;
it cannot be retroactively promoted by supplying missing model claims. A bounded
new GPT-6-astra medium call sees the same 184 source/reference images plus the
neutral typed-mapping instruction. No historical action reply or desired result
is provided. Local source preparation retains the prior image hashes, the 50ms
maximum detail gap and 19,199,413 request bytes. The actual approval result follows.

Run 39164556304 on commit e3509ea completed successfully, including its automatic
approval check. The actual GPT-6-astra medium reply supplies typed indexes 4/5/6
for its observed pass, reception and finish, and explicitly supports the teammate
relationship, same active ball, continuous play and unique attacking actors.
These are returned model observations, not input answers. Identity and all three
physical-link checks pass. The existing event resolver returns VISIBLE_DIRECT_ASSIST,
proof_eligible=true, and the mapper emits APPROVED with counts {"ASSIST":1}.
The selected passer is p1 with original r2; p4 is the distinct recipient/finisher,
not the foreground teammate or blond runner. No selected-player goal is credited.

The approved event 8a2678eb0a7c4143655e preserves:

| Evidence | Source interval or frame |
| --- | --- |
| Passing action | 43.948–44.132s |
| Recipient's arrival/reception | 44.598–45.332s |
| Recipient's finishing action | 45.448–45.682s |
| Moving active ball established in goal | 46.015s, supported by 45.915/46.131s |

Exact contact_ms remains null, with BRACKETED_VISUAL_SEQUENCE as its basis.
The relatively broad receiving bracket does not claim a precise first touch.
Intervening control remains NOT_OBSERVED and possible slight defensive contact
remains UNCERTAIN in the approved event. Absolute last-touch ownership stays null;
the supported attacking finisher and complete causal chain determine this assist.
The raw reply and the emitted event are retained together in
docs/examples/native-assist-approval-receipt.json. Replaying that hash-checked raw
reply reproduces exactly the saved automatic decision without a new model call.

The actual call took 68.600 seconds; probe time including preparation was 72.169
seconds, with 3.394 seconds preparation. Separate whole-source preparation took
19.288 seconds. This remains one bounded play, not measured fresh whole-video
latency or proof of all five actions. The original image hashes were retained;
the only new model instruction requests the typed event mapping.
The image hashes and byte sizes for all 184 images also match run 39161654199
exactly, checked against its actual workflow receipt; model and reasoning match.
195 relevant local tests pass, including the actual-reply replay and substantive rejection
cases. The earlier separately documented later assist is preserved. This assist
is now automatically approved in the standalone experiment's event path; applying
that implementation to the live report remains a subsequent integration step.

## Third play: continuous source detail and bracketing original identity selections

The next scoped trial addresses the earlier unresolved middle play from the
hash-checked sequence_007 reply in run 39151281244. Its 47.265–53.014s bounds
and explicitly uncertain final actor are retained as navigation, never input
answers. The source-cited selected player's first buildup bracket starts at
49.131s, so native detail extends back to 48.881s (250ms margin) and continues
through the prior 51.465s detail end. This covers reception, release and finish
without the earlier sparse interval. All 156 native-rate instants and all 46
whole-play overview instants are supplied. No event-reference file chooses them.

This play has no original in-play selection. A time-only rule chooses the nearest
original selection before and after the play, plus neighbours within 500ms of
either: r2, r9 and r8. Their original crops and full source frames with the actual
human box/positive point are identity-only. No new mark or predicted target is
fabricated in the play. The failed r2/r6/r7 model identity assignments are not
supplied as facts. Original taps and source input remain retained.

Sparse detections union all people into a common viewing band [0,753,1080,1318],
with no assigned identity/contact/outcome. Whole-frame overviews remain available
throughout the complete play. A neutral prompt requests the same source-grounded
players/contact_chain/link_assessment/event_mapping as the approved earlier play.
It also permits an explicitly supported first-time finish to use one row for
reception and shot, without inventing an extra touch or settled possession.
Identical receiving/finishing indexes require one_touch_finish=true; separate rows
must still preserve order. Existing source, identity, same-ball, opponent-control
and goal requirements remain. Both previously documented actual assist replies
are regression controls; replay verifies code behavior, not a fresh visual read.

Local preflight uses quality 85 native-pixel crops, maximum 17ms detail gap and
208 images total. One GPT-6-astra medium request gets a 90-second call bound and
120-second probe bound. Actual observations and the automatic decision follow.

Run 39168276199 completed the model call in 62.160 seconds; probe time was 66.262
seconds including 3.916 seconds preparation. Whole-source preparation separately
took 19.248 seconds. The original-r2/r9/r8 identity claims are structurally
consistent, but the model says the selected receiver also finishes, with number
7 as the initial passer and the deeper dark-haired white teammate staying behind.
It does not describe a selected-player pass to a distinct finisher. Accordingly
the assist mapper returns UNRESOLVED/PASSER_RECIPIENT_FINISHER_NOT_ESTABLISHED.
No selected-player goal is automatically substituted for this disputed play.
The actual receipt is retained in native-unanchored-play-receipt.json. Workflow
execution reached the decision check, which correctly failed assist acceptance.
The 210 isolated code tests passed, including the earlier two assist controls.

Manual inspection shows overlapping foreground/deeper white players around the
strike; the prior 39151281244 reading favored the deeper teammate but was explicitly
uncertain. Do not resolve that disagreement by silently accepting either answer.
One additional focused input uses the latest reply's source-cited finishing
bracket solely as navigation, expanded 100ms on either side. Sparse person boxes
choose the largest horizontal group, unioned with generous body-height margins;
they assign no identity, touch or outcome. In that interval only, native detail
uses a tighter source-pixel crop. All original source instants, whole-play
overviews and original identity examples remain. A neutral instruction compares
same-person continuity and a distinct teammate, without giving either old verdict.
This is a changed-view physical-separation trial, not an unchanged-input vote.

Focused run 39168769510 completed its call in 86.098 seconds. Probe time was
90.079 seconds, including 3.779 seconds preparation; repeated full-source
preparation separately took 19.204 seconds. The 17,342,144-byte request retained
208 images/source instants. Detail from 50.281–50.798s uses the native source
region [0,806,633,1177]. Preparation explicitly checks the detector's top-left
xywh convention and the head/foot extents; the focused view was inspected before
the call. No erroneous crop or hypothetical touch becomes event evidence.

The reply now keeps the lighter-haired selected player and the deeper dark-haired
white teammate explicitly separate throughout the overlap. It no longer uniquely
attributes the finishing movement to the selected player's following stride.
The responsible attacking actor remains null: either white player's contact, and
a possible defensive brush, remain unresolved around 50.381–50.681s. The moving
active ball is still followed past the goalkeeper and into goal at 51.131s.
Same-ball goal evidence is not enough to decide which attacker struck it.

The decision remains UNRESOLVED, with no target event or count. Neither a third
selected-player assist nor an extra selected-player goal is approved. The actual
focused response is retained in native-contact-separation-receipt.json; replay
reproduces its refusal without another call. Both prior approved assist receipts
continue to pass their separate structural/event regressions. Current validation
has 215 relevant local tests, including first-time finishing and preservation of
the disputed actor. This trial has narrowed the remaining failure to the selected
player's onward release and the attacking finisher, rather than goal outcome or
a demand for visible every-pixel contact. No merge/deployment follows from the
unsuccessful assist-acceptance checks. Further identical-input votes are not a
solution to the remaining physical ambiguity.

## Human navigation at 49.85s: paired body and lower-limb review

The owner supplied a new navigation hint at 49.85s and a hypothesis involving
the selected player's turn, surrounding defenders' legs and an onward release.
The new request uses only the timestamp and a neutral body-to-limb review method,
not the claimed action, kicking side, recipient or result as input facts.
This is human-guided inspection, not automatic discovery of this source interval.

Keep the preceding whole-play overview, original reference images, continuous
native detail and later contact-cluster view. Add 42 synchronized original-pixel
lower-body images from 49.500–50.200s. Person-cluster geometry chooses a body view
[82,799,856,1218] and a lower-body region [82,988,856,1218]; neither assigns an
identity or a contact. A source inspection confirms knees/socks/boots remain.
The model must trace shorts/torso through knees to socks/boots across time and
state visible-leg limitations. Counting unmatched/hidden legs alone cannot prove
a touch. Anatomical right is distinguished from screen right.

The contact_ownership_review explicitly records whether a selected-player release
is supported, contradicted or uncertain, with a positive actor, non-forced side
(LEFT/RIGHT/UNKNOWN), at least two supplied frames in the inspection window and
concrete before/after motion. It cannot replace recipient, finishing and goal
links. Missing or uncertain ownership stops approval even if other fields claim
a positive assist. A request for another side is never hard-coded as evidence.

Preflight: 250 images, quality 85, 18,490,357 request bytes and 17ms continuous
detail gap. This expanded input has one 120-second model-call bound and a
150-second total probe bound; the previous reader's bounds remain unchanged for
other modes. Actual outcome and measured timing follow.

Run 39171339112 completed in 90.791 model seconds, 94.862 probe seconds including
3.871 preparation seconds. Separate source preparation took 19.076 seconds.
It retains all previous 208 image hashes/sizes and adds only the 42 lower-body
views. The model now positively distinguishes the separate dark-haired teammate's
first-time finish at 50.365–50.665s from the selected player's following run.
Receiver/finisher and goal links are SUPPORTED. The selected release is still
UNCERTAIN: its actor remains null, with one selected-player leg visible and the
other contact foot masked. The model's explanation asks for continuously traced
hip/knee/boot ownership through the decisive overlap. No assist is emitted.
The actual reply and refusal are in native-limb-release-receipt.json.

The next focused input adds five comparison panels, each stacking four subsequent
native-pixel lower-body instants with labels outside the crop. Original pixels
are neither resized nor interpolated; source times, crop geometry and image hashes
are retained. All 250 preceding images remain. This changes simultaneous visual
comparison and the ownership instruction; it is not independent new source
evidence or an isolated comparison of either change alone.

The instruction explicitly allows positive before/after boot/sock movement,
body stance/anatomical reach and independently accounted alternative legs to
establish ownership even if a joint is briefly hidden. It does not demand a
continuously visible hip-knee-boot chain at every instant. It still prohibits
guessing an unseen contact by counting leftover legs alone. No candidate actor,
kicking side, recipient or expected result is supplied. The same positive
ownership and complete assist-link checks apply; uncertainty cannot be promoted
by this presentation. Preflight: 255 images, 19,144,787 bytes, quality 85.

Comparison run 39171853971 completed successfully, including automatic event
acceptance. The actual reply now supports selected p1's release through the cluster
at 49.715–50.081s, the same ball arriving at distinct teammate p3, p3's first-time
receiving finish at 50.331–50.648s, and the moving ball inside goal at 51.131s.
The leg review positively identifies the white sock/dark boot's forward sweep,
the selected player's other leg, the separately moving blue legs and the deeper
teammate's separate stance. Ownership is established by this before/after motion,
not simply by an unmatched leg count or uninterrupted visibility of every joint.

Identity and all three links pass. contact_ownership_review is SUPPORTED with a
positive selected release actor and source citations in the inspection interval.
The existing resolver returns APPROVED / VISIBLE_DIRECT_ASSIST and {"ASSIST":1}.
Approved event 369acbc54dce00fca4a7 preserves the 49.715–50.081s passing bracket,
the shared reception/finishing bracket [50.331,50.648]s and one_touch_finish=true.
Exact contact_ms stays null. Possible slight defensive brushes and absolute last
touch remain unresolved, with no observed intervening defensive control. The
teammate's goal is not attributed as a selected-player goal.

The model calls the releasing foot LEFT; the owner had described RIGHT. This
disagreement is explicitly retained in the receipt's review_notes and is not
silently corrected or supplied as a desired input answer. Actor/ball/recipient/
finishing ownership determines the assist; independent kicking-side verification
has not been claimed. The schema accepts LEFT, RIGHT or UNKNOWN only when the
selected release owner itself is affirmatively supported.

The actual call took 85.405 seconds; preparation plus model probe was 88.148
seconds including 2.627 seconds preparation. Separate source preparation took
12.708 seconds. The actual wire hash matches preflight, with 19,144,787 bytes.
Every one of the preceding 250 image hashes, byte sizes AND order is unchanged;
only five comparison-panel images are added. Both simultaneous comparison and
the occlusion-ownership instruction changed, so no isolated causal effect or
independent new raw-source evidence is claimed.

The complete actual reply and approved event are retained in
native-third-assist-approval-receipt.json. Replaying it reproduces the same
automatic decision, while the earlier refusals remain unchanged. 230 relevant
local tests pass, including the two prior assist controls and this third assist.
There are now three separately documented assist experiments. This successful
play used the owner's timestamp for navigation; automatic full-video discovery,
fresh whole-video latency, all-five acceptance and live integration still require
their own end-to-end verification. No merge or deployment is part of this trial.


## Saved-attempt identity disagreement: original-selection review

Actual run 39174579835 completed a GPT-6-astra request in 63.217 seconds.
The raw response describes SAVED, incoming ball at the goalkeeper glove and
changed outgoing motion, and keeps the stationary spare ball separate. It
labels the shooter unselected, citing darker hair and a beard. This is not an
approved shot for the selected player. The raw receipt is retained in
`docs/examples/native-attempt-outcome-receipt.json`.

The reused Gemini identity-only response already claims that r5 depicts a
different person with a dark beard. Original r5 is a 93x198 crop at 21.482s,
with an original point inside this play. Blur/shadow does not independently
establish facial hair. Agreement between that profile and the later request
is not independent verification of the disputed identity.

A bounded diagnostic now removes the prior inferred profile from the action
request, supplies all ten original selections (rather than canonical three plus
r5), and retains the same source overview, native outcome images, spatial
reference and event resolver. The old profile is still checksum-validated and
retained as audit, not rewritten. Original spatial selection and fresh image
comparison must resolve identity; a contradiction must remain an IDENTITY
question. The local point alone does not prove cross-play identity. This is
one fresh model call, with no desired action or outcome supplied. A new result
is required before claiming any improvement.
