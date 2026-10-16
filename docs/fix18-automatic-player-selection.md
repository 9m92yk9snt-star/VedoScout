# FIX18 — one player selection, automatic identity review

The Orman100 screenshots show an initial box editor followed by a separate
circle-based confirmation page. The backend waited up to 120 seconds for three
additional owner taps. The initial editor also required three extra checks
after its guided selections. A colour-based GrabCut suggestion appeared as the
main player preview and could show only the shirt or include grass.
The exported anchors retain masks on nine of eleven taps. The earlier native
replay bound six clear tap points and left four unresolved (one other tap was
partial). This establishes that masks were part of the real identity input;
it does not establish that they caused every unresolved point.

## Resulting flow

- One initial editor with 3–10 clear, human-confirmed moments. The first
  suggestions span the start, middle and end of the clip. Skipped or partial
  views cannot replace the three clear references.
  Their broad ordering is preserved in the uploaded anchors so the existing
  bounded identity-crop budget includes later references without extra reads.
- The main preview always shows the complete selected rectangle. Adjusting the
  box still preserves its actual displayed frame, time and selected point.
  Cutout refinement is optional and explicitly opened by the user, displayed
  beside the whole crop, and can be discarded. There is no automatic mask
  request or silently saved segmentation in the default tap flow.
- Saving returns to the upload form. Once the user starts analysis, player
  identity checks continue automatically with the original anchors. There is
  no second tap stage or later mandatory crossover confirmation page.
- Optical tracking uncertainty is retained in `identity_recovery` and
  `doubt_moments` in the report export. The worker continues to the existing
  native identity and physical evidence pipeline without waiting, extracting
  extra owner-check images, adding model calls or reseeding from guesses.
- An older worker already waiting can be resumed automatically with the
  existing skip endpoint. New runs reject late owner taps. Existing saved
  drafts containing three explicit verification anchors remain compatible;
  their flags are not inferred for new guided anchors.

## Jersey number and proof

The export contains `jersey_number: 5` while the description says number 15.
The upload form passes the number separately from anchor geometry. No tap path
was found that truncates 15 to 5; the historical origin of the wrong entry is
not established. The selected-player card now displays the entered number.
FIX16 already rejects an unambiguous number/description conflict before
charging or starting analysis. Historical reports are not silently rewritten.

Neither a user-selected rectangle nor a mask proves the identity at a later
scene, ball contact, a goal or an assist. Automatic review must retain UNKNOWN
when measured body/number/contact evidence does not support attribution. FIX17
prioritises reinspection around relevant uncertain contacts without weakening
these gates. The five reference actions are evaluation labels only.

## Validation and next video run

The regressions exercise the actual worker and compatibility endpoint with
injected tracking and database fixtures: no owner wait, no additional seeds,
unchanged UNKNOWN points, no discarded track after a diagnostic write failure,
report ownership and old-worker resumption. Editor tests cover single-flow
completion, unchanged source frames, masks only on explicit request, whole
crop previews, partial hints, tracking checks and retry-safe saving.

Deploy the combined FIX16/FIX17/FIX18 branch through the usual Emergent flow.
Run the video in ScoutMePlay with the correct number and fresh initial taps,
then export the new ZIP and PDF. Compare source versions, saved anchors,
native identities, contacts and scoring chains for each of the five reference
actions. These changes have not yet demonstrated five accepted actions on a
new production video run.
