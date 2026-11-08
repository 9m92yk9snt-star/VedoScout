# Match Room arrow styling — 2026-11-08

The report player now renders the existing source-bound arrow with a warm gold gradient, a narrow bright core, a concave arrowhead and a bounded 1.5-screen-pixel glow. The outer source-person mask is applied after the glow, including the head. The existing maximum 10-screen-pixel head and 30% short-line cap are retained.

Only presentation changes. Video sizing remains object-fit contain; there is no crop or zoom. Positions, timing, source validation, acceptance and pending/rejected playback gates are unchanged. No reconstructed preview coordinates were copied into production data. The accepted third assist is retained; its exact pass trajectory remains unverified and its rejected production arrow remains hidden.

Validation: six existing frontend Match Room tests passed; localization/camera-space display bridge contracts passed; JSX parser and git diff whitespace checks passed. No full React build or browser visual test was performed. This change is not a live-report verification. No merge, deployment or new model call.
