# Match Room inside the live premium report

SkillMeaningCard now opens its verified evidence inside the same card on both
mobile and desktop. The existing report owns the score, reasoning and next-level
coaching. Match Room adds the original evidence video, half-speed playback and
a paused inspection at the cited moment, without a second profile or scores.

PremiumReportV2 shares one active skill selection through MatchRoomContext.
Opening other proof navigation closes this selection. The existing floating
proof viewer remains available for timeline and other legacy entry points.

The existing canUseAuthorityProof and resolveProofClip contracts remain in force.
Clip-local inspection subtracts tele_clip_start from the source timestamp. If
the clip fails, the original upload uses its original timestamp instead. Inline
video starts paused, does not loop, and pauses when replaced or closed. Demo and
locked proof behavior stays in the existing proof component.

There are no sample player values, hardcoded timestamps, invented tracking,
model calls, backend changes or PDF changes. The prototype's hand-reviewed
graphics are deliberately not applied to unrelated live uploads.

Validation: MatchRoomContext.test.jsx and publication.test.jsx cover evidence
gating, contextual navigation, one inline player, time conversion, slow motion,
and clip fallback. Run them with the project's existing craco test command.
Run npm run build before merging, then synchronize Emergent with the resulting
main commit and deploy using the existing production workflow.
