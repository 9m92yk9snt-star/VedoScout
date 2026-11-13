# Original-tap detection feasibility

Offline evaluation of all 10 original taps using the existing YOLO model through OpenCV DNN and the experimental 0.1 person-proposal threshold. Frames retain original dimensions and actual media timestamps. No LLM requests were made.

Eight taps have exactly one detection containing the tap point. At 3.07 seconds three detections contain the point; at 70.61 seconds none contains it. A missing box at the point does not establish that the player is invisible. Do not silently substitute the nearest detected person.

The measured loop took 11.1287 seconds with process affinity restricted to one CPU core on the evaluation host. This excludes model initialization and initial source hashing, and is not a production-server benchmark. See all-tap-detection.json for boxes, confidence scores, frame hashes, model hash and per-tap timings.

This evaluates seed candidates only, not ByteTrack continuity or identity accuracy. Eight unique candidates do not imply 80% LLM savings. Production analysis and LLM routing remain unchanged.

Next validation: test temporal continuity around unique seeds and resolve ambiguous/missing seeds from nearby observed frames without accepting track ID continuity as identity proof. Compare against the same source and original taps before enabling any LLM suppression.
