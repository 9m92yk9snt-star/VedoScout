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
- Schedule goal reviews across the report, preserving verified-chain priority
  and scene diversity. Budgets and ownership/crossing/intervention gates remain
  enforced. Incremental traces are replaced by ID after final reviews; pending
  and complete versions cannot race or create duplicate manifest rows.
- Bind match claims and skill evidence to qualified canonical events. Unsupported
  scoring claims are withheld; unavailable grades and aggregates are null.
  Partial coverage remains visible and does not establish zero goals/assists.
  Parent prose, comments and frontend outlook use the same evidence authority.

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
```

The saved-observation replay increased verified dense observations from 475 to
1,496 (overlapping windows count observations, not unique video frames), and
accepted actions from six to seven. It still verified no shots, goals or assists.
The fictional scoring prose and unsupported shooting grade were withheld.
This proves specific boundary fixes, not recovery of the user's five actions.
Newly scheduled visual reviews are not executed in this offline replay, and the
original weak Step-3 detector proposals were not exported. Full recovery must be
validated against newly produced physical/model evidence before claiming success.

No production report is rewritten by this change. This is a code review branch;
deployment and a new analysis are separate operations.
