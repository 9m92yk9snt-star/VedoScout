# Localized foreground difference

Comparison of all 99 emitted samples in the saved source-bound replay confirms that every sample field except confidence and foreground is identical, including measured/display ground, player width and stance bounds when present.

Only one sample's foreground differs: 9.983s in position-contour:9750:10000. Independently rasterizing and unioning the normalized person polygons at the analysis resolution (720 x 1280) gives three removed pixels and two added pixels. Coordinates are retained in the audit JSON. This quantifies the rounded polygon raster, not the raw detector masks or the browser's antialiasing.

Neither exact full-output parity nor which engine better matches the real person's boundary follows from this measurement. Keep production engine selection unchanged. Do not round away confidence differences, alter mask thresholds or relax identity/graphics gates to force parity. Future engine validation should address this measured boundary difference and full recovery/deadline behavior.

Reproduce with backend/scripts/audit_foreground_difference.py using the saved final-contours OpenCV/ONNX JSONs and the SHA-bound original video. No model rerun, paid request, sync or deployment was needed for this audit.
