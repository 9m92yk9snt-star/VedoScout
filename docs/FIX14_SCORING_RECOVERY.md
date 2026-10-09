# FIX14: scoring evidence recovery

The Orman10 export reaches `ready` without accepting the expected saved shot,
goal or three assists. This change repairs search coverage, measured crop
selection and identity wiring. It remains a draft until the five references
have complete, independent physical proof. A passing unit suite is not 5/5
video acceptance.

## Changes

- Semantic planning searches measured scene intervals even when target identity
  is unresolved. A completed response for a one-frame transition cannot hide
  the following six-second scene.
- Action inspection uses the entire bounded physical window. The old saved-shot
  search ended at 23.466 seconds; its window now spans 19.466–25.466 seconds.
  The old later-shot hint opened 49.700–52.600 seconds, excluding the earlier
  pass. Its window now spans 47.331–52.931 seconds. Times remain search hints.
- Portrait search images show the measured pitch band. A recorded native ROI
  maps displayed ball coordinates back into the exact source frame before the
  existing native class-32 corroboration. Independent number, role and goal
  readers retain their original native/full-context inputs.
- The search reader selects measured body IDs instead of guessing portrait
  body coordinates. IDs open independent number reads only. Ambiguous,
  overlapping or unmeasured bodies cannot acquire identity from an ID selection.
- Pixel-selected crops retain physical actor priority. Uninvolved backs cannot
  consume the first two temporally independent reads for an involved release
  actor. Reused and near-duplicate frames are deduplicated.
- Jersey re-identification compares canonical time bounds and measured physical
  cuts. The canonical and physical graphs number their scenes independently;
  comparing their scene labels rejected the same clip after the first cut.
  Duplicate numbers, opposing kits and conflicting target proofs still block
  the handoff. Identity is not carried across a cut.
- Dense tracking preserves both hypotheses when two previous tracks compete
  for one detected body. Greedy iteration order cannot select the target.
- Camera estimation uses bounded background images and maps verified transforms
  back to native coordinates. Person/ball detector inputs, confidence gates and
  temporal sampling are unchanged.
- Report authority also checks absence-based claims embedded in training and
  development advice. The actual exported issue, which interpreted no detected
  shots as an undeveloped attacking skill, becomes an explicit evidence-gap
  explanation. Generic exercises remain available; missing actions cannot earn
  a weak shooting grade.
- Offline replay restores only the direct user selections present in checksummed
  `anchors.json`. It does not manufacture the omitted continuous identity spine.
  Source fingerprints are captured before replay and checked again before the
  final evidence package is certified.

The existing limits remain 16 initial action reviews, four feedback reviews,
12 search images per call and 24 number reads per provider allocation. No
expected action result or target number is added to the pixel reader. Assist
acceptance still requires the target pass, same-ball receipt, teammate strike,
goal outcome and continuous causal chain.

## Validation

The local focused regression suite passes **709 tests**, including the new
FIX14 controls. The GitHub workflow runs FIX14 and the affected sequence
planning tests in the production verification job.

```bash
PYTHONPATH=backend:backend/tests python -m pytest -q --asyncio-mode=auto \
  backend/tests/test_fix09a*.py backend/tests/test_fix09b*.py \
  backend/tests/test_fix10*.py backend/tests/test_fix12*.py \
  backend/tests/test_fix13*.py backend/tests/test_fix14*.py
```

All 70 original export checksums pass. The exported 37 Python modules match
the base source at `4b89e714e365f4ecd1af7f7247cf7059959446d5`. Historical deployment
and commit identifiers were not stored; matching source bytes do not invent a
historical deployment SHA. The native detector matches the exported model
SHA-256 `013a98f3bc0264a3d793ef29ccbd178ceb0bbb86bc12ff3510273ce85b1c4526`.

The supplied video SHA-256 is
`2774978344f9c54e44f81c2328f3165d3aada4f1b95193964bb22b73a9ecf85b`.
The new default plan selects 16 reviews and defers 15, exactly as before. All
five reference intervals now have a selected full-context search window.
The saved-shot window offers 56 uniquely measured crop candidates across its
12 images; candidate availability is not a successful jersey read or identity
proof.

On 48 consecutive actual-PTS image pairs from 43.198–43.998 seconds, using
OpenCV 4.13.0.92 and two threads, camera estimation took 0.8872 seconds before
and 0.4411 seconds after. Both produced 48 verified transforms. This is a
local camera-stage measurement, not a claim that the complete 84-minute
production reconstruction is now twice as fast. A separate unchanged native
identity rebuild took 63.92 seconds for 355 sampled frames and reproduced the
saved-shot scene's `reid_failed` interval.

## Five-reference acceptance

The unchanged reference specification is
`docs/examples/five_action_reference_cases.json`. Both the saved-observation
baseline and the final patched offline replay accept **0/5**. The final replay
restores 12 direct user selections, preserves the original canonical counts and
2752 verified dense-frame observations, and removes the actual shooting-weakness
claim. Its source fingerprint stays unchanged throughout the run, all eight
review-package checksums pass, and it performs zero model requests and zero
database writes. Newly scheduled reader requests are not successful observations.

| Reference | Expected result | Remaining independent evidence |
| --- | --- | --- |
| 00:23.68 | Target shot, saved | Cross-cut target re-identification, target release, active-ball path and goalkeeper save |
| 00:30.83 | Target goal | Correct shooter identity, release and goal crossing/direction |
| 00:43.19 | Target assist | Target pass through receipt to teammate shot and goal |
| 00:49.44 | Target assist | Earlier target pass through receipt to teammate shot and goal |
| 00:56.44 | Target assist | Target pass chain, teammate identity and field-side goal direction |

The saved-shot scene contains no direct same-scene user tap. Its original
identity spine fails re-identification after the cut. The new inspection path
can collect pixels there; it cannot pretend a previous-scene tap is proof of
the later shooter. That identity gap still requires independent resolution.

Fresh supporting vision was not run locally: the process has neither the
configured model key nor the supporting SDK. The existing read-only command
can use an operator's already-configured environment without uploading a new
report or writing production data:

```bash
python backend/scripts/replay_report_evidence.py /private/original-evidence.zip \
  --cases-json docs/examples/five_action_reference_cases.json \
  --support-vision --output-dir /private/fix14-review
```

The command returns exit code 2 while any reference remains unverified. Each
accepted reference must have `causal_verified` and actor/physical proof, with
the target distinct from the teammate receiving or scoring. No labels are
injected to force 5/5. The original export, PDF, production report and video
remain unchanged; local replay performs zero database writes.
