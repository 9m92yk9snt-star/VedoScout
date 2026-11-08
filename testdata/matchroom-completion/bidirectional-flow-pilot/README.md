# Bidirectional optical-flow experiment — 2026-11-07

No LLM calls; no production changes; pass-arrow approval remains false.

Lossless frames decoded from the hash-bound canonical video. Seeds manually inspected: ball center at 49.665 s before occlusion; ball at 50.648 s during the finishing phase. The latter is NOT a documented receiver's first touch. The experiment cannot claim that it tracked backward from reception.

Local pyramidal Lucas–Kanade optical flow on a nine-point grid; forward/backward numerical consistency and a fixed seed-patch appearance check. Thresholds are exploratory, not calibrated identity confidence. Results are proposals, not automatic ball evidence. No interpolation across a failed step.

Forward proposals continue through 49.731 s and stop at 49.748 s (only two of nine points pass consistency). Backward proposal reaches 50.631 s and stops at 50.615 s (zero consistent points). Visual review confirms these short tracks stay on the visible ball. No joined pass trajectory is recovered; 0.900 seconds separate the surviving endpoints, including the missing pass and subsequent action. Numerical consistency must never be equated with proof of ball identity.

Reproduce from the parent of VedoScout with source_audit/video containing the canonical MP4, an existing bidirectional_probe output directory, Python, OpenCV, NumPy and Pillow. Run run.py. It records source SHA-256 and creates a review sheet; no network requests.
