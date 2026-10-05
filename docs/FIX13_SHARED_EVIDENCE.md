# Shared evidence authority and live replay

The live failure crossed three boundaries: later jersey identity did not update
dense body frames or earlier sequence observations; goal clarification was spent
in window order; and prose/assessment evidence could contradict canonical events.
A model response saying “three excellent goals” survived the previous numeric
claim filter even though no goal had passed the physical proof path.

## Changes

- Share an independently verified tap/jersey identity along the same local body
  for at most 1,200 ms, with actual media timestamps and adjacent frames at most
  80 ms apart. Cuts, ambiguous associations, conflicting verified targets and
  discontinuous boxes stop propagation. Propagated frames cannot seed another
  propagation. Uncertain contacts remain uncertain.
- Reconsider existing identity-unresolved sequence actions against dense proof.
  Shots, goals and assists retain their physical outcome path. Recovered passes
  require a verified target release within 120 ms.
- Use contact-anchored ball trajectories to inspect delayed releases. Missing
  balls in portrait footage get an additional ground-band detector pass, using
  the same sports-ball class/confidence threshold. A detection is a proposal,
  never event proof.
- Add a report-wide pixel inspection stage BEFORE contact and identity proof.
  All observation labels can select an inspection, including OTHER, DUEL and
  OFF_BALL_RUN. Empty semantic windows have a physical-recall inspection path.
  Model ball boxes are search locations only: a fresh native class-32 detector
  match at the same actual decoded frame must corroborate them. Jersey crops
  must match one measured, unambiguous body and still use the independent
  number reader and existing temporal consensus. No model event/identity label
  is copied into the physical graph. Invalid/cut/fallback frames stay excluded.
- Schedule goal reviews across scenes and time within each scene. Select the
  widest available context before spending budget on overlapping ball/body
  contacts. Local track IDs are never compared across windows; distinct balls
  never share geometry. Every original contact retains its own outcome and
  attribution gates. The defaults are 16 pixel inspections (at most 12 images
  each), 16 verified-chain goal reviews and 16 uncertain-owner clarifications;
  they can be reduced through their environment settings. The old separate
  clarification limit of four could not inspect five uncertain situations.
  Budgets and ownership/crossing/intervention gates remain
  enforced. Incremental traces are replaced by ID after final reviews; pending
  and complete versions cannot race or create duplicate manifest rows.
- Give outcome vision the exact measured active-ball reference (actual frame
  time and box) belonging to the contact. Keep that reference within its existing
  image budget. A structured visual crossing must link to that ball before the
  crossing; a spare/unlinked ball cannot supply the contact's outcome. The
  existing whole-ball proof gate rechecks this link. Legacy saved evidence is
  not silently relabeled as new reference-bound proof.
- Persist inspection selection/defer reasons, actual frame times, raw pixel and
  goal-reader responses, model/input/response hashes, corroboration/binding
  rejections and review reuse. The report run manifest records the new budgets,
  and the physical summary carries both review plans into the existing export.
- Bind match claims and skill evidence to qualified canonical events. Unsupported
  scoring claims are withheld; unavailable grades and aggregates are null.
  Partial coverage remains visible and does not establish zero goals/assists.
  Parent prose, comments and frontend outlook use the same evidence authority.
- Anchor capture waits for the presented video frame and stores its media time.
  Manual verification cannot accept a tap during a pending seek; the box keeps
  the timestamp of the frame on which it was drawn. Overlapping seeks cancel
  old requests, and a timeout cannot be treated as successful frame decoding.
  This fixes a concrete race; it does not establish that the race caused any
  particular tap in the original live run.

## Verification and limits

Focused regression tests include ambiguity/cut boundaries, propagation limits,
release/scoring safety, malformed times, the live adjective-count failure,
portrait coordinate mapping, and pending-to-complete trace persistence.

The private live evidence ZIP is deliberately excluded from this repository.
Replay it without database writes or new model-service requests:

```sh
PYTHONPATH=backend python backend/scripts/replay_report_evidence.py /path/to/evidence.zip
# Optional CPU detector inference against the checksum-verified original video:
PYTHONPATH=backend python backend/scripts/replay_report_evidence.py /path/to/evidence.zip --video-detail
# Fresh supporting reviews using only the operator's existing environment key:
PYTHONPATH=backend python backend/scripts/replay_report_evidence.py /path/to/evidence.zip \
  --support-vision --output-dir /tmp/private-report-review
```

The last command uses `EMERGENT_LLM_KEY` already in the process environment.
It never needs `MONGO_URL`, never connects to Mongo and never edits the source
report. It reuses saved body observations and runs detector inference only on
bounded proposed ball regions, avoiding a full CV/tracking re-analysis. It
writes a checkpoint after each trace/review and a checksummed
`reviewed-evidence.zip`, containing physical traces, canonical output, corrected
report, source ZIP/video hashes and backend code hashes. The original ZIP is
still needed for the original video and omitted source data. Missing source
scene-graph frames prevent replay from claiming complete full-video coverage.
Model requests/errors are recorded as attempts, never as successful proofs.
The fresh model path is wired/tested with injected readers; no live model
credential is available in the local review workspace.

The saved-observation replay increased verified dense observations from 475 to
1,496 (overlapping windows count observations, not unique video frames), and
accepted actions from six to seven. It still verified no shots, goals or assists.
The fictional scoring prose and unsupported shooting grade were withheld.
This proves specific boundary fixes, not recovery of the user's five actions.
The original-video detail pass added ball proposals to 1,624 frame observations
and reduced target ball gaps from 978 to 665. Its accepted scoring counts also
remained unchanged. More detector proposals alone did not repair scoring.
Newly scheduled visual reviews are not executed in this offline replay, and the
original weak Step-3 detector proposals were not exported. Full recovery must be
validated against newly produced physical/model evidence before claiming success.

The remaining evidence breaks include a model action described as a pass where
the user identified a saved shot, a jersey-verified target contact classified as
receive/control without a verified release, an absent assist chain, and crowded
contacts with uncertain body ownership or split tracks. These must be resolved
by physical/visual evidence; lowering outcome or identity gates would hide them.

The five private live reference areas are covered by the default inspection
plan using only exported observation times and window geometry. Their expected
types/times are not embedded in production selection or model prompts:

| Human reference | Current saved-evidence break | New inspection path |
|---|---|---|
| 23.68 s, saved shot | Primary story calls it a key pass; keeper/contact/outcome proof is incomplete | Inspect the observed contact and terminal context, then retain keeper/non-crossing gates |
| 30.83 s, goal | Target contact/jersey is verified; role is receive/control and ball disappears | Native ball re-detection before role classification; independent outcome review |
| 43.19 s, assist | Target releases exist; primary story says duel/lost and the receiving/scoring chain is missing | Labels cannot close inspection; review body/ball evidence before causal registration |
| 49.44 s, assist | Physical release owner does not bind to the tapped target | Ambiguous OTHER situation gets body/crop inspection without assuming target ownership |
| 56.44 s, assist | Target contact is occluded; a different body owns the measured release and tracks split | Run/unknown-label situation is inspectable; body ambiguity and same-ball gates still apply |

Coverage by an inspection plan is not recovery of an action. None of these five
is yet proved by the saved-observation replay. Fresh model evidence and the
unchanged final proof gates must establish or reject each action explicitly.

No production report is rewritten by this change. This is a code review branch;
deployment and a new analysis are separate operations.
