# Dense pass-contact model result — 2026-11-08

The existing accepted assist was not reopened. One fresh localization-only request used 57 consecutive source frames (49.765–50.698 s), assembled into seven native-resolution foot-detail panels plus four full-frame context images. The owner's 49.865 s hint was supplied explicitly as a search hint, not as ground truth. No reconstructed arrow coordinates were supplied. The video itself was not cropped or changed.

GitHub run 42444973838, job 128621892438, input commit cb694a9f80ee456a6c9793dea0907e00f164211f. One model call completed in 16.033 seconds. The raw result is retained in result.json, with source, packet and response hashes.

Result: no visible pass-ball samples, null release contact, null reception contact, continuity_supported=false, safe_direction_anchors=false. The model reports that the hinted toe/ball area is blurred and occluded. It separates the later outgoing-shot ball from the earlier pass and supplies no fabricated location.

This is not a rejection of the accepted assist. It is also not proof that every possible source view is unusable: the dense window starts at 49.765 s and does not cover the earliest part of the previously accepted release interval. It provides no new coordinates suitable for correcting the existing reconstructed animation. The earlier pass-position request independently also had no reception anchor.

No precise moving-arrow approval, no guessed endpoint replacement, no production data changes, no merge or deploy. A repeat of the same detail packet is not justified. The current visual style remains available; exact third-assist motion remains unresolved. Do not describe the work as a corrected or verified ball trajectory.
