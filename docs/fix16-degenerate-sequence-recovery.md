# Physical review after a one-frame scene

A hard cut can create a scene containing one sampled frame. Its measured start
and end times are equal. Previously the planner sent this zero-duration window
to the semantic model. Actions could not satisfy that window's time contract,
and the partial-result admission check rejected the whole physical analysis.
The production pipeline then used the legacy spatial ledger instead.

The planner now omits zero-duration windows and records the unreviewable scene.
Its neighbouring scenes retain their original cut boundaries. The physical
admission adapter also handles older plans containing such a window: positive
windows continue, while malformed, reversed, negative or non-finite windows
still reject the plan. No semantic observation or event proof is promoted.

The physical runtime receives the filtered scheduling plan. Omitted windows
remain visible in persistence and scoring-coverage diagnostics; completing the
remaining windows does not certify complete video coverage.

Legacy report fallback now records its provenance. Its semantic scoring scan
cannot certify complete physical evidence, and the existing report-fact
authority also reconciles its prose and skill evidence with verified events.
A model story about goals must not coexist with an empty approved timeline.

Upload preflight also detects an unambiguous disagreement between the shirt
number field and an explicit number in the player description. It returns 422
before billing, storage or background analysis. Neither declaration is silently
replaced; ages, scores and ambiguous multi-player descriptions are ignored.

## Validation

- Dedicated regressions cover one-frame scenes, preserved cuts, partial physical
  execution, coverage diagnostics, malformed plans, fallback claims and identity
  declaration validation before billing.
- Both server fallback routes are checked through their shared authority bridge,
  including real empty/invalid-ledger and valid-ledger behaviour. Reference
  diagnostics read the persisted accepted, unresolved and rejected contact groups;
  displaying a local contact does not grant player identity or scoring authority.
- A read-only replay of the failing export validates every echoed sequence ID
  against its scene/time boundaries. The 17 positive windows now enter physical
  review; the zero-duration window remains an explicit omission.
- Native preparation on the unchanged canonical video and 11 original taps
  reproduces 312 identity points, 221 production-track points and 576 scene-graph
  frames. All 17 remaining sequence IDs match the original response. Stored
  responses satisfy all 17 retained contracts and retain 32 normalised actions.
  Native preparation used local OpenCV 5.0.0, not the deployment's 4.13.0.92.
- No new model call, database write or event approval is performed by these
  offline checks. They do not establish a five-action scoring PASS.

The private export and media are not committed. To inspect another compatible
fallback export locally:

```bash
python backend/scripts/audit_sequence_admission.py \
  --evidence /path/to/private-evidence.zip \
  --output /path/to/private-admission-audit.json
```

The diagnostic infers only ID-bound window boundaries, never a historical dense
graph or identity record. Actual goal/save/assist acceptance still requires the
normal physical, player, ball, role and causal proof gates.
