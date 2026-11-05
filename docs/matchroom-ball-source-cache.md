# Reuse decoded source pixels for ball foregrounds

The ball playback path decoded each source interval for camera estimation and then sought/decoded it again for foreground masks. `_read_window` now optionally supplies each exact decoded BGR frame via callback. Ball playback retains a maximum64MiB /150 frames, consumes them at their actual source timestamps, and uses the original second decode when the cache overflows. Default `_read_window` output and other callers remain unchanged. No arrow geometry, rendering, model, evidence gate or deadline is changed.

Real shot: isolated experimental ONNX Runtime builder completed all five intervals in6.222s under normal8s allowance, with complete segment data exactly equal to the prior7.870s extended-budget diagnostic. Normal owned child process: ONNX Runtime25.510s, five arrow intervals through31249ms, no ball failures; existing OpenCV31.443s, four intervals through31149ms, BUDGET. The runtime switch is still experimental and NOT added to production dependencies.

Playback-model checks against the original encoded clip source timestamps, using only this newly generated shot-worker result: 19/19 arrow visibility frames. This is a targeted worker check, not a fresh full report or visual approval. The eight-clip trial and continuous visual comparison must still be repeated; whole-duel ellipse failure remains unresolved.

43 relevant tests passed, including fresh-frame foregrounds, camera/cut/uncertainty rejection, encoded VFR timebase and cache-overflow fallback. Three server-import timebase tests excluded due missing local server dependencies, as previously documented. No merge/deploy; keep PR56 draft.
