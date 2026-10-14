# Shared fresh seed qualification before contact-role review

Continuation forked from PR #29 at `575737e30a441c832774c45a463e635601cb5876`.
This change corrects the order of native evidence selection. It does not approve
the original goal or complete the five reference actions.

## Problem and resulting behavior

The original 30,915 ms verified contact has a 30,965 ms ball-after observation
with confidence 0.0389. That observation is below the unchanged 0.04 release
reacquisition floor. Contact-role review passed it directly to the selector,
received no contact-bound trajectory and retained `RECEIVE_CONTROL`.

Later strike reconstruction separately qualified a unique native 30,982 ms
measurement with confidence 0.22787 and recovered six post-contact positions.
Consequently the earlier role review could not use evidence available to the
later stage. A controlled receive followed by a real release could remain
misclassified even when the later physical separation met every existing gate.

Both producers now call `qualify_produced_contact_seed` before binding. It only
accepts an unchanged ball-after observation of a verified physical touch from
the supported producer namespaces. The native qualifier checks the contact,
original candidate, unique measured path, camera transforms, time bounds and
competitors. Explicit rejection, external required anchors and spare-ball flags
are not repaired. Original touch coordinates/confidence are preserved.

Role review records the qualification and exact binding, then runs its existing
four-measurement/three-strong-separation rule. Qualification is not release
authority. Missing bodies, retained possession, quick recontact or ambiguity
still prevent a release. Forged/stale qualification metadata is cleared during
reassessment; it is never consumed as native evidence.

## Validation

- 171 focused contact-role/seed/anchor/contact/pixel-geometry checks passed.
- 1,559 offline regressions passed, 28 SDK-dependent cases skipped, in 46.98 s.
  The regression process recorded zero SDK, network or video-decoding attempts.
- Twenty new cases cover before/after stage consistency, three canvas aspects,
  preserved weak confidence, retention of control without strong separation,
  source/camera/cut/contact/competitor rejection, missing bodies, quick recontact,
  explicit spare flags and stale/forged records.
- Original saved-evidence replay changes the contact binding from REJECTED to
  VERIFIED and supplies six measured positions at 30,982 / 31,015 / 31,032 /
  31,065 / 31,132 / 31,182 ms. A separate fresh decode verifies all eight original
  goal-region RGB hashes for the contact, weak observation and selected path.
  Saved native classifications were reused; these are not eight fresh detector
  classifications or a fresh full five-action reconstruction.
- The original role remains `RECEIVE_CONTROL`. Only four selected positions
  have the same verified actor body; it is absent at 31,132 and 31,182 ms.
  None of the available four positions meets the unchanged strong-distance gate.
  No original RELEASE or GOAL PASS is claimed. The last strict five-action
  acceptance remains 0/5.
- A bounded local jersey OCR diagnostic found no reads above confidence 85 on
  the measured crops. It was not integrated or used to hand off player identity.

No paid model calls, Emergent execution, new uploads, selection changes,
production report/database writes, merge or deployment occurred.
The compact receipt and exact offline target list are in
`docs/evidence/FIX15_CONTACT_ROLE_SEED_HANDOFF_VALIDATION.json`.

## Next physical work

Recover and independently bind the actual #15 body through its brief detector
dropouts, then reassess the literal kick/ball separation. Preserve competing
body hypotheses; an expected shirt number or an interpolated rectangle cannot
replace an observed body. In parallel with that evidence path, automatic goal
acceptance still needs same-ball recognition after occlusion and independent
goal/field geometry. The control-contact goal-review lane remains available;
this fork does not redefine control as a shot or a goal.
