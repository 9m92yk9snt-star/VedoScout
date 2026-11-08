# Full-frame arrow precision check

Verdict: NOT VERIFIED AS PRECISE BALL MOVEMENT. This concerns the latest illustrative full-frame video, not the accepted assist.

All 27 rendered source-frame coordinate pairs were independently recomputed from the original video and retained camera-motion algorithm: maximum numerical difference 0 pixels. This tests reproducibility of the same interpolation, not agreement with an independently measured ball track.

The illustration draws from 49.881 to 50.315 seconds. Its assumed arrival is 50.381 seconds: the last drawn position reaches 87.2093% of the constructed path, 66 ms before that assumed arrival. The early stop was intentionally introduced to avoid the accepted finish interval; it cannot simultaneously be described as a verified arrival animation. Do not extend it without contact evidence.

The rounded tip center is removed by the final occlusion mask in 25/27 source frames, including 23/27 inside retained person masks. Two additional centers are removed by the preview's color exclusions. This explains why a visible shaft does not guarantee a readable moving tip. Do not remove player masks to make an unsupported trajectory visible. Counts concern the center, not the entire head.

The retained position-model response has nine observations during the display interval, all without a ball coordinate. It supplies no measured release or reception interval. Human source inspection covered 16 contextual frames from 49.831 through 50.598 seconds, including the user-indicated starting frame; partial visibility does not establish all intervening ball centers. No pixel-accuracy score against the real ball can be calculated honestly.

The full output decoded to 263 frames at 1080×1920; no video crop or zoom. This is the existing half-speed export. No new model call, semantic approval change, production-playback approval change, merge or deployment.

Reproduce with `python testdata/matchroom-completion/reconstructed-pass-preview/verify_full_frame_precision.py --workspace <workspace>` using the retained workspace layout: VedoScout/, source_audit/video/, arrow_effects_full/{render.json,MatchRoom_pil_effekter_hele_billedet.mp4}, and arrow_precision_audit/ for output.

Next change must separate a reconstructed direction illustration from a measured moving ball tip. A verified moving tip requires independent visible ball/contact anchors and explicitly unresolved gaps; the present straight, constant-progress interpolation cannot certify those gaps.
