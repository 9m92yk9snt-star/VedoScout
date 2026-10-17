# Reuse the first source-video observation

The whole-video sequence reader previously returned actor/outcome labels through
the legacy identity path, while a later source-indexed motion reader could own a
complete visual chain. Consequently the same play could need another video read,
another identity bootstrap and native outcome reconstruction after the model had
already documented it.

## Final behavior

- The existing video call records the actual input video/reference hashes,
  canonical run source hash and raw response hash outside model JSON. Each action
  is bound to its response content and enclosing scene, including after bounded
  coverage retries. A model-supplied receipt or VERIFIED label is insufficient.
- The first reader compares the original selected-player references with clear
  actor evidence and follows that person through changing measurement labels.
  That comparison enters the existing canonical resolver; there is no new model,
  provider, approval stage or production module.
- The same qualified actor geometry can identify a measured dense body at an
  actual source timestamp within the existing 20 ms alignment bound. Bodies with
  different IDs are mapped through geometry once. Actual cuts, ambiguous body
  mappings, different verified targets and explicit source/user conflicts remain
  unresolved. No shirt number is required to repeat an established identity.
- A native graph frame from another source instant is supporting context, not a
  direct contradiction of current actor pixels. An ambiguous native association
  may leave the canonical actor as GLOBAL_TARGET without erasing the source
  comparison. A different selected body observed at the aligned instant remains
  a contradiction. For an assist, explicit observed teammate/same-finisher roles
  may use response-local person handles without requiring another native body
  detection. No native track ID is fabricated for those handles.
- An outcome timestamp or an outcome-evidence list is sufficient. Likewise the
  source contact can be supplied in either contact field. Normalization fills the
  equivalent representation; two different contact times remain a contradiction.
  The prompt distinguishes the final shot from buildup, follows the active ball
  through camera movement, excludes stationary spares and keeps assist roles
  separate. Instructions alone do not prove the model followed them.
- A completely reviewed, fully resolved source window replaces its extra initial
  video inspection and releases that allocation to another unresolved window.
  Empty, partial, foreign-source or overlapping unresolved observations retain
  their inspection. The native detector, thresholds, frame coverage and physical
  recall remain unchanged; new contacts can still open targeted feedback.
- Known actor/contact outcomes bypass repeated ball-path, keeper-role, goal,
  intervention, direction and ball-proof reconstruction. A teammate finish can
  also be bound to its already measured source geometry across changed IDs.
  Matching is computed once per strike. A reused outcome stores a canonical event
  reference with physical crossing NOT_ASSESSED; it does not fabricate an
  independent physical certificate. The completed play opens no further generic
  identity or forward/backward outcome search.

All changes extend existing modules. The first-call prompt/response contains a
small amount of additional evidence metadata; the savings come from replacing
later work, not from reducing source-image coverage.

## Verification and limits

Initial revision `e846c66f3ecf73443e6b2b72791a2acaebd30bf2`: **2,537 passed**
across 125 offline regression modules in 29.82 seconds, including 52 new
first-read/reuse controls. All five GitHub checks also passed for that revision.

The final source-time/role follow-up passed **216 relevant tests** in 4.09 seconds
across the first-read, canonical-resolver, temporal-video and coherent-evidence
modules. Plugin autoload and ONNX Runtime were excluded; Python socket connections
were blocked. A broader follow-up's result was blocked by automatic approval
review over a telemetry attempt and is not counted as passed. The safe focused
run completed. These overlapping test totals must not be added. All 383 backend
Python files parse and the patch passes whitespace validation. The existing
GitHub backend contract includes the new first-read tests automatically.

The new regression replies are explicitly synthetic test doubles. They exercise
first-call provenance and JSON retry wiring, native-ID changes, direct assists,
alternative timestamp fields, actual cuts, source/actor conflicts, incomplete
chains, budget reuse, dense identity handoff, changed finisher IDs, retained new
native-release searches and final reconciliation. They do not establish model
recognition accuracy.

The actual exported first model response has SHA-256
`9e7dc403ad4dbe8e11aa7c93fc3f3ebcb8e9688accab4c9a3160682eca522860`.
Its hash matches its stored audit. Normalizing those same 25 original actions
with main and this revision, without new out-of-band observation evidence,
produces identical output. Zero actions receive invented first-read provenance.
No new model call was made in that replay.

No new Gemini perception run, full end-to-end timing, production analysis,
deployment or five-action recognition pass has been performed. The earlier
detector benchmark is separate and is not a timing measurement of this change.
There is no hardcoded reference-action timestamp, count, player number or result.
This change must remain distinguishable from a documented five-action model run.
