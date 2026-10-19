# Fresh-source trial and verified continuation

Run 39179116053 completed all ten initial GPT-6-astra medium calls. Analysis
took 439.163s; fresh source processing including preparation took 455.956s,
excluding workflow setup. Each call took 61.037–91.427s. The ten-call first
stage is a measured latency bottleneck.

Before any automatic review was sent, the spatial-image helper received a
follow-up packet without core_start_ms. Its KeyError escaped the old error
handler. The finally block preserved the ten actual receipts and counts,
but status incorrectly stayed NOT_STARTED. This was a code failure after
model work. The original evaluation matched two assists and retained a false
selected-player goal in the middle-assist play. It did not pass. Raw result
and evaluation are in fresh-whole-source-first-run-result.json; all ten raw
receipts and a replay catalog are in fresh-whole-source-initial-receipts.json.

The spatial helper now receives core bounds derived from the actual follow-up
interval. Runtime KeyError/TypeError produce EXPERIMENT_STOPPED. A regression
uses real local source frames and a follow-up without core fields.

The parser now separates within-play identity context citations from actual
in-action evidence. At least one supplied frame must still support the action
inside its own bounds; contextual frames must remain in the same play. Contact,
identity and active-ball outcome requirements are unchanged. The actual initial
saved-shot answer already said selected SHOT/SAVED, but cited 22.016s for
identity before the shot's start. That one citation previously discarded the
entire supported shot. The corrected decoder records it as actor_context_frames
and retains the valid in-action evidence. It does not move the contact or invent
an observation. This also admits the analogous RECOVERY from the earlier goal
receipt as a non-scoring action, while leaving that goal unchanged. Original
raw results are not rewritten. Offline replay now matches three references;
the false middle goal remains. Replay is not another model trial.

The continuation validates source and tap hashes, packet fingerprint, response
hashes, model and every reproduced fresh request payload hash before reuse.
All ten exact payloads were reproduced locally in 2.987s with model calls
disabled. --resume-fresh-initial is distinct from arbitrary historical-result
replay. Metadata marks this as a continuation, not a new cold end-to-end test.
It sends zero repeated initial requests.

Automatic terminal-review planning now anchors an unknown shot outcome to its
observed contact rather than the final aftermath frame. Control-to-chance review
includes the recent control through the strike, capped at three seconds, because
a coarse dribble may conceal a release within it. Already supported distinct
passer/finisher assists are not redundantly reviewed. Other nonterminal questions
remain recorded without spending terminal-review calls on them. Nonlocal temporal
identity references receive a wider vertical margin, after source inspection
showed the smaller fallback clipped heads. No desired result, reference-event
timestamp or new human navigation enters the planner.

The actual new plan has three reviews. All retain their overview/native instants
and fit preflight: 14.707, 10.893 and 12.880 MB. 261 local offline tests pass,
including source-clock separation, missing-core bounds, exact-request replay
and refusal after a payload-hash change. These are code tests, not new model
approvals. The continuation has a 300s budget and at most six new calls; the
current plan has three. The prior 455.956s and continuation timing remain
separate. No merge or deployment.

## Actual continuation: four of five, not a pass

Run 39180556938 completed three new reviews (57.731, 80.639 and 91.717s),
with zero repeated initial calls. Analysis took 161.277s; continuation source
processing took 175.232s. It matched the selected goal and all three assists,
removed the erroneous middle selected-player goal, and retained no extra scoring
events or identity conflicts. The middle release bracket is 49.631–50.265s;
this broader actual bracket is not replaced with the earlier separate trial's
more precise result. The finisher is a distinct white teammate, number unreadable.
The earlier left/right-foot disagreement remains unresolved.

The saved-shot review identifies selected #15 as the shooter but says UNKNOWN
for the outcome and explicitly asks CONTACT and OUTCOME. The previous initial
SAVED answer remains in the audit; the newer uncertainty is not suppressed.
Inspection shows the goalkeeper and goal are inside the delivered local strip:
a claim that the crop removed the goalkeeper would be incorrect. However, the
native continuous detail ends at 23.966s, before the keeper encounter, followed
by sparse aftermath images. Missing temporal detail is a plausible limitation,
not a proven cause of the model's disagreement. Raw receipts, result and separate
reference evaluation are in fresh-whole-source-review-receipts.json.

A bounded second continuation verifies all ten initial and three review request
payload hashes and raw-response hashes, reproduces the exact four-of-five result,
then derives one new request from the unique explicit selected-shot OUTCOME gap.
It includes every native source instant from contact-before minus 100ms through
contact-after plus 1500ms (23.566–25.249s in this actual navigation), full-play
overviews and all original selections. The wider vertical band is computed from
the union of original selections, not the known goalkeeper location. Previous
answers, human event timestamps and evaluator cases are absent from the new
request. Offline preflight reproduces all thirteen prior payloads, gives 166
images / 17,558,067 request bytes, and sends no calls. The new run permits only
one GPT-6-astra medium request, with a 120s per-call limit. Its result replaces
the prior terminal review only in the active view; prior observations and raw
receipts remain available. This is still a continuation, not a cold end-to-end
benchmark. 261 prior checks and three new navigation/refusal tests pass.

## Outcome transport rejection and smaller evidence delivery

Run 39181338773 verified all thirteen prior requests and sent the new outcome
request. The provider returned HTTP 429 / MODEL_QUOTA_OR_RATE_LIMIT after
65.464s, with no response text. Source processing took 105.488s. The raw
transport receipt is retained in fresh-outcome-rate-limit-receipt.json. This
adds no visual conclusion; the active previous result remains four of five.
The original failed probe output omitted prior events, so its zero-match
evaluation must not be interpreted as invalidating earlier observations. The
continuation now initializes its result with the verified prior observations
before attempting transport, preserving them on failure.

The bounded retry uses the original local selection band rather than the wider
all-selection union, with the same native times, overview instants and original
identity references. Actual source inspection confirmed that both the keeper
encounter and goal are inside that local band. This reduces image area and
request size; it does not supply a desired answer or delete intervening instants.
HTTP 429 does not identify its precise cause, so this is a smaller evidence
delivery attempt, not a claim to have diagnosed or bypassed a provider limit.

The smaller preflight retains exactly the same frame IDs, native window, 103
native images including two extra cited instants, and 166 total images. The
local source band is [0,704,1080,1098]; request size is 7,861,799 bytes, 55.2%
smaller. Full-source overviews remain. Source inspection at the strike, keeper
encounter, departure and descending ball confirms the relevant motion stays
inside the local strip. This delivery, unlike the first review's early control
window, includes all native instants through the keeper encounter.

## Actual smaller continuation: all five matched

Run 39181686181 completed the one smaller GPT-6-astra medium request in
55.808s. Source processing for this continuation, including fresh preparation
and thirteen exact prior-request checks, took 96.059s. No initial or prior
review call was repeated. The actual request hash exactly matches the offline
preflight, 99495f97d9b0f90bacbbd7da4276f9609742633d4999d5ad396d9eb446db27ea.

The new answer identifies selected white #15 through r5/r6 and continuous
motion, brackets his strike at 23.682–23.749s, and returns SAVED. It separately
brackets the goalkeeper encounter at 24.349–24.382s: the incoming ball reaches
the raised glove, loses its previous forward progress and departs above/left,
then descends and bounces outside the goalmouth. It distinguishes that moving
ball from the stationary spare inside goal. There are no new model questions
or invalid rows. The existing resolver emits one proof-eligible selected
SHOT/SAVED without changing acceptance requirements.

The active combined continuation matches all five references, with no extra
scoring events or conflicts: saved shot [23.682,23.749], goal [30.882,31.015],
assist 1 [44.015,44.132], assist 2 [49.631,50.265], assist 3 [56.264,56.514]s.
These are the actual new observation brackets, not substituted earlier golden
timestamps. Raw receipt, response/request hashes, source-frame replay context,
combined result and separate evaluation are retained in
fresh-outcome-approval-receipt.json. The preceding UNKNOWN reading remains
inside previous_terminal_observations and in its original receipt bundle; the
HTTP 429 remains separately preserved.

continued_observations_pass is true; fresh_run_complete and experiment_pass
remain false because this is a verified multi-stage continuation, not a new
cold end-to-end benchmark. The fresh initial stage took 455.956s, first review
continuation 175.232s, rejected wide outcome attempt 105.488s, and successful
local outcome continuation 96.059s: 832.735s measured source processing across
the resumed stages, including repeated preparation but excluding workflow
setup and offline work between runs. That is not acceptable production latency
and is not presented as one uninterrupted execution. Live-report integration
and a fresh complete cold run remain unverified. No merge or deployment.

Validation: the standalone GitHub check passed 264 tests at the smaller-run
commit (39181686295). Two further retained-answer replay/refusal tests now
check the new actual SAVED reply and prevent approval if an explicit target
CONTACT question is introduced. All five new continuation tests pass locally;
with the 261 existing relevant tests, 266 local checks pass. An offline injected
transport error also retained all four prior approvals and the unresolved shot
without any model call. These are code validations, not extra perception calls.

## Integrated cold-run preparation

The next run starts from the exact original video and taps, loads no saved
model receipt, and makes fresh discovery requests for all ten scene packets.
The --automatic-outcomes mode requires fresh-original contact mode and rejects
resume inputs. Initial reading, native contact reviews and at most one further
outcome round share the same deadline and total follow-up cap (six). Source
preparation is subtracted from the workflow's 900s source-processing allowance;
per-call timeout stays 120s, worker count stays two, and there is no HTTP retry.
The ordinary runner's 600s cap and legacy replay planner remain unchanged.

A proposed optimization to skip every proof-eligible selected shot was rejected
by retained-source testing: it would also skip the coarse false selected GOAL
in the middle-assist play. The actor/control review is therefore retained. In
the cold mode, a review of a non-goal shot now keeps recent control, strike and
continuous aftermath together, with a 4.8s native-window cap. Direct terminal
questions with a contact bracket include 100ms before the bracket and 1500ms
after it. An explicit remaining selected-shot OUTCOME question can schedule
a bounded second-round native reading without using any reference-case answer.
Superseded observations and their unresolved questions remain in the audit; a
failed review does not remove the previous active observations.

Offline source preflight, using retained answers for navigation testing only,
produces three image requests: goal 16,102,769 bytes / 187 images, control-to-shot
14,997,290 bytes / 353 images, middle handoff 12,880,445 bytes / 180 images. The shot
window now covers 20.466–25.266s, including the goalkeeper encounter, rather
than stopping at 23.966s. All requests fit the unchanged 19.5 MB wire cap and keep
all supplied source instants. These are preflight measurements, not new model
results or an assurance that a provider will accept the requests.

272 relevant offline checks pass, including synthetic three-stage success,
second-round transport failure preserving uncertainty, a shared unchanged
deadline across rounds, the total follow-up limit, refusal of resume in cold
mode, and exact reconstruction of the previous successful outcome navigation.
The final prior resumed-branch GitHub check (39181993193) passed 266 tests.
Cold-run reference evaluation is performed only after all actual model calls.
No merge or deployment.
