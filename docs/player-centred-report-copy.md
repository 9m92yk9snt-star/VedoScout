# Player-centred report copy, existing Premium V2 design

Sequence reports explain the player's football: strengths shown in the video,
their place in ScoutMePlay's age-band coaching guide, and useful next practice.
The shared publication projection supplies both web and PDF with the same copy.
It reads retained observations only. No new model request, analysis or database
rewrite is needed to present an already completed Sequence report.

`player_report_copy.py` translates qualified actions into concise observations,
football value and skill-specific practice. Suggestions are future exercises,
not extra observations, measured achievements or claims about club selection.
The existing scores, positional weights, age ranges and source/identity/media
bindings remain in force. Diagnostic coverage calculations stay in the export;
they no longer occupy the primary web explanation.

- The introduction describes the player's strongest shown skills and uses
  distinct, bound moments. It can include a documented goal without inventing
  assists or saves in the message to the player.
- Existing snapshot cards can feature dribbling and ball protection as well as
  scoring. Each uses its own event/frame binding.
- Development focuses build on actual actions instead of treating the lowest
  grades as weaknesses. Each has a different exercise and a future practice goal.
- Skill explanations, strengths, video descriptions and parent copy use football
  language. Internal IDs/contact precision remain available for audit and playback
  joins, not as visible prose.
- The existing statistics card shows ball carries and recoveries in place of
  internal action-segment totals and the misleading zero from a duel-only counter.
  Carries are not labelled as successful take-ons or defenders beaten.
- Academy bands are explicitly ScoutMePlay coaching references for shown skills,
  not empirical percentiles, recruitment promises or academy selection decisions.

No CSS, className, style attribute, grid or PDF card geometry changes are included.
The report still uses the original six-page structure for the Orman600 example.
Its grade remains 7.3 and its source ledger still contains nine original segments.
Rendering that retained export is an offline presentation review, not a new model
test. The portrait is not repaired or regenerated in this change.
