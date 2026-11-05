# Tracking CPU investigation — 2026-11-04

Base: 46fdc01136db7237ea63b2b1060de7333e60fdee; preparation change: 131f7725ddac8b936b614eb2ecb3b70fb957cbf2.

Real retained source, bound model receipt, duel event 88aa8bbdedbec570d4de, recovery window 11750–12883 ms, affinity one CPU, OpenCV 4.13.0, one OpenCV worker. No paid calls; no 4GB cap.

cProfile: contour_segments 105.458s; 69 fresh source frames; detect_frame 99.102s; predict 98.002s; DNN forward 97.342s (92.3% of total). Seven supported intervals. This is a short-window profile, not full-report acceptance. Initial model loading is outside profile.

Alternative execution of the exact same pinned ONNX model was tested locally using ONNX Runtime CPU with one intra/inter-op thread. Nine warm samples after first sample: approximately 21.1% lower inference time. The first timing overlapped the tail of another experiment and must not be used. This microbenchmark is not evidence of full-analysis speed or accuracy.

Eight of ten frames had identical masks and integer boxes. Separate repeat confirmed a one-pixel mask difference in each of two frames, with identical boxes. No runtime change/dependency is added to production: broader sequence/graphics regression verification is still required. Winograd toggling showed no clear gain and was not adopted.

Preparation-only optimization remains in PR56. Tracking graphics gaps from the earlier full one-core trial remain unresolved. No merge or deploy.
