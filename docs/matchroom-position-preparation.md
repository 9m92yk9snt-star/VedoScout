# Explicit position evidence — preparation only

These helpers are not connected to the production report renderer or frontend yet. They do not establish that automatic graphics work. A live report using a source-visible original tap is still being evaluated.

`match_room_position_evidence.bound_samples` checks the source, original selection digest, event, request/response receipt, supplied source-image hashes and ordered source timestamps. It retains empty uncertainty rows. Unknown selected-player identity suppresses both selected-player graphics and ball coordinates in that row. These observations never become human taps.

`match_room_position_contours` is a short-proof candidate: two independently localized source positions must each resolve to one visible person contour. Forward and backward flow must agree on every intervening source frame. Unknown observations, competing owners, missing foot contours and missing frames reject that interval. Separate accepted intervals may support reacquisition, but are never joined through missing evidence. No frontend method support or report mutation has been enabled.

Nineteen local parser, provenance and contour-control tests pass, including synthetic positive protocol cases and negative identity, source, ambiguity, missing-measurement and timing cases. They are not model accuracy or end-to-end validation.
