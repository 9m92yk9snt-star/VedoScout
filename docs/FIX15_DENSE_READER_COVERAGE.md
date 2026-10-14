# Complete original-image coverage for a brief ball reappearance

Sparse twelve-image review retained one frame of the documented approximately 100 ms reappearance. Independent same-ball verification needs at least three classified after images spanning at least 80 ms. Increasing recognition capability alone therefore could not recover this event reliably.

For a verified contact-bound native path followed by a complete bounded native gap scan, the provider now sends the entire already decoded gap to the existing single goal reader call. It also retains contact, seed, the last six before positions and terminal context. This plan uses actual media timestamps, source BGR hashes and original frame dimensions. It does not use screenshot circles, expected event times or predicted ball positions.

The dense cap is 64 images (FIX15_MAX_DENSE_GOAL_FRAMES); native gap sampling remains at most 56 images over at most 900 ms. The ordinary reader budget remains 12. When validated dense coverage cannot fit, source pixels are missing/changed, or the contact/scan is invalid, the provider keeps the existing sparse review path. Dense versus appearance refocusing and the selected budget are recorded in sampling_audit. Reader caching includes the dense cap.

This increases image volume for eligible occlusion reviews, from up to 12 to up to 64, while retaining one remote call. Real model latency, response completeness and cost have not been measured for this larger payload. It is not a cost-neutral claim. Existing request and worker deadlines remain and incomplete replies fail closed. Model response retention increases from 50,000 to 262,144 characters so a complete larger response is not silently truncated below its hash-bound original length.

## Validation

- 1,610 offline regressions passed; 28 SDK-dependent cases skipped. No model, network or video-decoding attempts in the regression process.
- Twenty added cases check translated media clocks, every arbitrary 100 ms gap window, unchanged source data, one cached reader call, oversized complete responses, and rejection of missing/changed images, invalid timestamp/source/dimensions, unbound contact, predicted path, duplicates, budget overflow and false event/proof authority.
- Fresh original-video decode verifies 55 full native BGR hashes and 55 original goal-region RGB hashes against archived receipts. The plan retains 62 images, including all seven actual 31,849–31,949 ms reappearance images and before positions 30,982 / 31,015 / 31,032 / 31,065 / 31,132 / 31,182 ms.
- The original scan's detector classifications are archived metadata, not fresh classifier outputs. The fresh probe validates image coverage and source identity only. No independent original image response was obtained and no fresh full five-action reconstruction ran. Original goal remains UNRESOLVED; last strict five-action acceptance remains 0/5.

Next acceptance work: independently classify the actual before/after ball and competing visible footballs on these inputs; verify native same-ball identity, independent goal/field geometry, full-ball goal-volume position and contradictions. Synthetic fixture success and screenshot testimony cannot approve the original goal.

Keep draft. No paid calls, Emergent, new uploads/taps, production count writes, merge or deployment.
