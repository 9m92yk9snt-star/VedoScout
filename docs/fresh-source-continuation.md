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
