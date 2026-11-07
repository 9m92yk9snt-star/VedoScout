# Non-LLM supporting ball detection pilot — 2026-11-07

Diagnostic experiment only. Assist acceptance is unchanged. Pass-arrow playback remains rejected; this experiment does not approve it. No LLM calls.

21 sampled source frames, 49.615–50.648 seconds, every third decoded frame. Source and model SHA-256 values are recorded in result.json. Existing generic COCO YOLOv8n executed with OpenCV DNN, two CPU threads. Ball class must win class argmax and score >= 0.25; NMS threshold 0.45.

| Method | Candidates | Frames with candidates | Inference seconds |
|---|---:|---:|---:|
| Full frame | 0 | 0 | 2.683 |
| Fixed ROI | 1 | 1 | 2.629 |
| Six overlapping tiles | 1 | 1 | 15.350 |
| Bright round contours | 73 | 20 | 0.026 |

Counts are proposals, not verified ball detections. Visual review shows the tiled proposal at the right edge of the crop, away from the visibly located match ball. Bright contours also select clothing and background. No continuous ball track was recovered.

Limitations: custom SAHI-style slicing, not the SAHI package; no football-specific fine-tuning; no TrackNet model tested; classical branch tests color/shape only, not motion or Kalman filtering. ROI and tile union differ in area. This is an exploratory comparison, not an accuracy benchmark. Timing excludes decoding and model initialization. Sampling can miss brief contacts.

Recommended next experiment: football-specific detector with selective tiling, camera-compensated temporal association, and person occlusion masks. Separate OBSERVED, PREDICTED and OCCLUDED states. Kalman predictions guide search but cannot independently verify contact, receiver identity or arrow endpoints. TrackNet requires football-domain validation, especially its inferred/filled positions. Test against manually reviewed visible ball positions, including hard negatives such as boots, socks and reserve balls; then verify actual overlay playback behind legs and at the receiving player.

Primary references:
- https://github.com/obss/sahi — slicing for small-object detection.
- https://arxiv.org/abs/1907.03698 — TrackNet temporal heatmaps.
- https://github.com/qaz812345/TrackNetV3 — released badminton shuttlecock model and inpainting.
- https://docs.opencv.org/4.x/dd/d6a/classcv_1_1KalmanFilter.html — prediction versus measurement correction.

Reproduction: run run_probe.py from a parent directory containing VedoScout/, source_audit/video/ with the hash-matching canonical MP4, and an existing nonllm_probe/ output directory. Requires OpenCV 4.13.0, numpy and the repository's existing backend/models/yolov8n.onnx. No model download or external inference is performed by the script.
