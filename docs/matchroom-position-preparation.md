# Automatic Match Room graphics — verified 4 November 2026

The retained Orman400 trial passes on code `5d6e9709c9c2c8fc1a58a794368b955b375b08ac`: all ten original taps and all 17 canonical events are unchanged. The actual report contains eight clips, with 14 accepted ellipse segments and 21 moving-ball segments across all eight cards. These remain short measured intervals, not continuous tracking.

Actual React playback confirms the same white player is reacquired after the duel at 12.749–12.883s (nine decoded frames). The shot arrow points up/right after contact at30.915s, visually inspected at31.115s. All76 missing/unconfirmed player-ground observations and65 missing/unconfirmed ball observations suppress the corresponding graphics. No browser errors occurred.

[Final automatic trial](https://github.com/9m92yk9snt-star/VedoScout/actions/runs/41778466214) reused all eight exact position receipts with max-new-requests0. Source analysis and report prose were retained. No fresh paid requests, production writes or notifications occurred.207 backend controls, nine frontend controls and the real-report acceptance test pass. All six [Production verification jobs](https://github.com/9m92yk9snt-star/VedoScout/actions/runs/41778459424) pass.

Missing ellipses receive separate bounded retries after all original passes complete. Interrupted paths get the original small model first; complete small-model misses can use the pinned medium model. At most three25-second retries run. Identity, visible-foot, bidirectional and exact-source-frame gates are unchanged. Completed ball evidence is preserved. The workflow now rejects a finished report missing any card's accepted graphics, post-duel recovery, post-kick direction or uncertainty suppression.

The earlier run41777471752 completed its job but failed graphics acceptance because the duel timed out; it is superseded by the final run above.

The production frontend serializer and server thumbnail-detachment function preserve all ten original taps. This is a data-transfer check, not an authenticated upload UI test. Full authenticated upload-to-report UI remains untested. PR55 stays draft; no merge or deployment. This one-match trial does not establish accuracy on every match.

See `matchroom-all-tap-result-2026-11-04.json` for exact intervals, checks and artifact digest.
