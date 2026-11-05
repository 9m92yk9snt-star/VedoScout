# Nearby motion-window decode reuse

Repeated source seeks consumed20.2s of the initial duel worker's30.95s profile. A per-call reader now decodes nearby frames once in groups spanning at most1.5s, capped at96 processed frames, and independently resamples every original interval with the same sampling phase, seed-frame inclusion and source PTS. Larger/high-density windows fall back to the original reader. No model, drawing, uncertainty gate or timeout changes.

Real retained source, one CPU: observed_motion duel23.527s ->4.584s; shot3.530s ->1.430s. Complete output objects identical in both cases. Reproducible comparison helper included. 88 local tests passed; three previously blocked server-import tests excluded. New tests compare exact timestamps and arrays across actual VFR frames and exercise density fallback.

Targeted normal bounded duel worker with experimental ONNX Runtime:238.361s including refinement; source-frame playback coverage228/249 versus prior175/249. Recovery61/61. Earlier0.5s cache trial covered205/249, superseded. NOT a full-report timing or visual acceptance. Existing report shot rows were not regenerated in this duel-only playback probe: its13/19 arrow result is old report data, not a regression of the separately demonstrated19/19 shot worker.

Remaining duel gaps:10016–10233ms (14frames) and11016–11116ms (7frames). First window ends withTIME_BUDGET after80 decoded frames. Second gap lies inside completed11000–11750ms refinement; whether clipping refinement context at11000 loses necessary identity/display-bridge support requires investigation. Do not label this second gap a proven timing failure.

All249 frames are still required; no padding, invented positions or relaxed tests added. ONNX remains experimental, PR56 draft, no merge/deploy.
