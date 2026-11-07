# Football-trained detector experiment — 2026-11-07

Diagnostic only; no production changes, no LLM calls, no arrow approval.

Model: Dura-S/reco-yolo26s-football, pinned revision d20231484951d4ebf3f9f2a7437aa922a4c1b395, best.onnx. See provenance.json and result hashes. Model author describes amateur/youth football training on a specific fixed fisheye camera rig; transfer to this handheld source is unvalidated. License AGPL-3.0. Weights are not committed or integrated into production.

CPU ONNX Runtime 1.31.1, telemetry disabled before session creation, two inference threads, OpenCV 4.13.0. Local inference only. Network was used to retrieve public model weights and packages, not to upload the video.

Inputs: same hash-bound canonical video as the prior pilot. First test uses its 21 JPEG frame exports at approximately 50 ms intervals, 49.615–50.615 s. Full image is letterboxed to 1920 square with RGB conversion and 0–1 normalization; ROI (100,800)-(740,1280) is similarly letterboxed. Class 1 is ball; confidence threshold 0.10. Output includes NMS in the exported model. ROIs enlarge players/ball far beyond the full-frame scale and therefore are not a controlled accuracy benchmark.

First test: full-frame inference gives three candidates; ROI gives zero. Visual inspection confirms the visible match ball at 49.615 and 49.665 s. The 50.265 s candidate is near a blue player's boot and does not establish the match ball; reject it as pass evidence. Total run 65.23 seconds, excluding initialization, including both modes and file IO. No continuous pass track or receiver contact recovered.

Dense follow-up uses every decoded frame in 49.615–50.648 s, full-frame mode only, same 0.10 threshold. See dense_result.json. JPEG exports introduce compression; this is a transfer feasibility probe, not a lossless benchmark. run_dense.py uses the dense/ input folder generated from the canonical source; run.py uses the prior pilot nonllm_probe/ images. Both run from the parent directory of VedoScout/.

Conclusion: football-specific training recovered some visible ball positions missed by the generic model, but this model is not sufficient evidence to approve the pass arrow. Do not interpolate a verified pass from a visible point before occlusion and an unverified boot candidate. Existing accepted assist and rejected playback remain unchanged.

Primary source: https://huggingface.co/Dura-S/reco-yolo26s-football

Dense result: 63 frames, 7 candidates in 7 frames; three visually confirmed pre-pass ball detections and four unverified candidates near a blue player's foot. No other >=0.10 ball detections. Elapsed 111.87 seconds.
