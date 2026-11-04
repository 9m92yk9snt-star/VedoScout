# Automatic Match Room integration — 4 November 2026

The report now receives automatic source-position measurements in its normal asset pipeline. All ten original user selections are preserved. No reviewed/manual positions are supplied to this trial. Canonical action identity, scores and source proofs remain unchanged.

## Verified result

The scoped graphics check passes on the independent Orman400 source. In the actual React Match Room player, the ellipse reappears under the same white player at **12.749–12.883s**, after the duel and fall; it does not transfer to the blue opponent. Nine decoded playback frames show that recovered ellipse. The shot card shows the observed ball direction up/right after the **30.915s** contact, visually checked at **31.115s**. Continuous playback records 13 arrow frames and eight ellipse frames for that shot card.

The complete report contains eight cards. The frontend accepts 11 measured contour segments on six cards and 24 moving-ball segments across eight cards. Coverage is short and incomplete. Two cards still have no accepted ellipse; absent evidence is not replaced by raw model coordinates. This is not a claim that every frame or every match works.

All 76 observations without confirmed visible player ground suppress the ellipse, and all 65 observations without a confirmed ball suppress the arrow. No JavaScript errors were recorded in the final playback checks.

## Execution and cost scope

- [All-eight graphics run 41771330758](https://github.com/9m92yk9snt-star/VedoScout/actions/runs/41771330758): one prior localization reused, seven missing graphics requests completed.
- [Duel recovery run 41772727152](https://github.com/9m92yk9snt-star/VedoScout/actions/runs/41772727152): seven exact receipts reused; exactly one new duel request. That request contains all ten original references plus 34 timeline frames, is 11,558,751 bytes and covers 8.750–12.883s. The 19,500,000-byte cap is unchanged.
- Final local replay uses all eight exact completed receipts with `--max-new-requests 0`. No source-analysis, report-writer or new localization calls occur in that replay.
- The retained all-ten-tap analysis contains 17 canonical events. Do not confuse it with the historical one-tap/19-event diagnostic.

The test uses the real report asset orchestration and React player in isolated storage. The authenticated upload UI has not been exercised. No production database writes, notifications, merge or deployment occurred. PR #55 remains draft.

## Changes that made this work

The position stage now runs before asset rendering, binds observations to source/frame/selection/request/response hashes and checkpoints each paid response. Original taps identify the target; model observations never become human selections.

Player contours require fresh masks on every source frame, independent endpoint observations and agreement of forward/backward association. Completed intervals are saved incrementally. Windows share no interval, and a separately observed recovery gets compute budget before earlier uninterrupted runs. Unknown identity or hidden feet remain barriers.

Duel perception can use the already encoded clip's 750ms trailing context, without extending the canonical action proof. Ball direction remains bounded by the original action proof and measured camera-compensated endpoints. Explicit-source playback rejects sparse coordinate fallbacks. Short arrows fade in within their measured interval and never persist into an unknown observation.

## Validation

All six Production verification jobs pass on code commit `2850c69f08ac62240e42b09466060be2816687f4` ([run 41773659919](https://github.com/9m92yk9snt-star/VedoScout/actions/runs/41773659919)). The paid duel run passed 173 focused backend controls; the final frontend localization suite has nine controls. Synthetic controls are separate from the real-video/browser observations above.

Machine-readable scope, intervals, counts, artifact digest and limitations are in `matchroom-all-tap-result-2026-11-04.json`. Completed model receipts and browser verification JSON are retained with the evidence bundle. Historical one-tap results remain historical; they are not the current result.
