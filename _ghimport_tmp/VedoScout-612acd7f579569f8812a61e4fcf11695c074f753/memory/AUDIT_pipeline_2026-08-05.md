# FASE 1 AUDIT — Tapping, Analysis Reliability & UX (Aug 5, 2026)

## 1. PLAYER SELECTION LINEAGE — VERIFIED SOLID ✅
Trace: tap (ScoutMode/MarkerStudio) → markerAnchors [{t, box, thumb}] → POST /reports/upload
(`marker_anchors` JSON, thumbs detached to `{id}-anchor-{i}-thumb.jpg`) → doc.raw_marker_anchors
→ analyze_preview_task: anchor crops (`{id}-subject.jpg`, `{id}-anchor-{i}.jpg` + wide) → R2 flush
→ build_identity_profile (GPT-vision on tap crops) → identity_profile_block injected in BOTH prompts
→ full report: track_player(file, valid_anchors, t_off) optical tracking seeded ONLY by taps
→ _ground_truth_positions_block in Gemini prompt → anchor crops attached to Gemini call
→ _apply_tracking_verification on action_timeline → _verify_enriched_frames (GPT-4o) drops wrong-player
images → identity gate retry if ≥50% hard-rejected → movement/pace math from tap-seeded track only.
NOTHING overwrites or replaces the selection. "THE TAP IS THE TRUTH" enforced everywhere.

### Minor coordinate inconsistency (MANUAL fallback mode only)
MarkerStudio.jsx handleDone (line ~1184): only anchors[0].box converted from wrapper-normalised to
video-native coords. Anchors 2..5 (manual adds + auto-suggest) stay wrapper-normalised → letterbox
offset baked in on mobile → anchor crops 2..5 slightly wrong region. ScoutMode (default path) is
correct (video-native from handleStageTap). Fix: convert all anchors in handleDone, same math as idx 0.

## 2. DUPLICATE EDITOR BUG — REPRODUCED ✅ (screenshot proof, headless webm)
Root cause: MarkerStudio.jsx lines 1011-1018 auto-open effect:
```
if (!open||!videoReady||scoutOpen) return; if (anchors.length>0) return;
setTimeout(()=>setScoutOpen(true), 250)
```
Cancelling ScoutMode (X / scout-close) sets scoutOpen=false but anchors stays [] → effect refires →
ScoutMode REOPENS 250ms later → INFINITE LOOP. User sees: X → MANUAL editor flashes beneath →
"jumps back" into ScoutMode boot ("Uploading video → Analysing footage → screenshots") which looks
like a new analysis starting. Reproduce: upload webm → open studio → wait scout-mode-overlay → click
scout-close → overlay returns within 720ms (verified twice).
Fix plan: userDismissedScout ref/state — cancel sets it, auto-open respects it; MANUAL becomes real
fallback. Also ScoutMode bootStage label "uploading" is a LIE (it's screenshot prep, video is local) →
rename. AnchorPreview → MANUAL round-trips (Replace/Second-tap) are intended but unexplained → add
context copy.

There is only ONE analysis pipeline (analyze_preview_task → generate_full_report_task). No duplicate
pipelines. generate-full endpoint has idempotency guard (status generating/awaiting_confirmation).
Editors: MarkerStudio(MANUAL) + ScoutMode overlay + AnchorPreview = 3 stacked UIs, one mounted tree.

## 3. CONSISTENCY / DETERMINISM AUDIT
Deterministic: optical tracking (NCC), movement/pace math, benchmarks rubric (in prompt), GYG gate,
teaser score (avg full scores × 10).
Non-deterministic sources (same video re-uploaded):
  a) Gemini 2.5 Pro sampling — temperature 0.2, NO seed param, no top_p/top_k pinning.
  b) GPT-4o identity verification verdicts vary run-to-run → different evidence images kept.
  c) Identity-gate corrective retry fires stochastically (≥50% frame rejects) → whole re-analysis.
  d) User taps differ per upload → different anchors → different GT block/evidence timestamps (inherent).
  e) Preview (15s clip, PREVIEW_PROMPT) vs full (whole video) can contradict each other.
Anti-hallucination: prompts are strong (EVIDENCE OR SILENCE, outcome-claim guardrails, content-type
locked vocabulary, cannot_evaluate). scrub_hedging + _validate_grow_your_game + _validate_parent_corner
post-gates exist.
Improvement options (Fase 2): temperature 0.0 (keep or lower), pass seed via extra_params (litellm
supports for Gemini), consider score-band stabilisation note in prompt; document expected variance.

## 4. STEP 3 GAPS (Fase 3 build)
No player photo field, no country field in UploadPage form. Required: photo (required), country
(required), block submit until present. Backend upload endpoint needs new Form fields + storage.

## 5. CATEGORIES (Fase 3 build)
Current video_type: highlight | match | training | drill | freestyle (5).
Target: match (30s-5min) | skills_training (15s-5min) | highlights (15s-5min).
Backend: only max duration validated (305s in analyze_preview_task); NO min duration. Add per-category
min check (fail early with refund like the 5-min cap path). Content gate stays authoritative on
detected type.

## Test assets
/tmp/audit_test_video.webm (20s VP9) — headless-safe. H.264 mp4 does NOT decode in headless Chrome
(videoReady never true → studio black screen, no user-facing error — known iter60 backlog item).

## FASE 2/3 IMPLEMENTED (same day)
1. Editor loop FIXED: scoutDismissed state in MarkerStudio (auto-open respects X). Verified in browser.
2. MANUAL anchors 2..N coordinate conversion FIXED (toVideoCoords in handleDone).
3. Guided ScoutMode UX: intro coach card (scout-intro-overlay), lock flash (scout-lock-flash),
   auto zoom-out on confirm, honest boot labels.
4. Step 3: player photo REQUIRED (upload compressed 512px OR video_crop→display crop), country
   REQUIRED (searchable combobox, /app/frontend/src/lib/countries.js). Backend 400s enforced.
5. Categories: match(30s min)/skills(15s)/highlight(15s), max 305s. Backend min-check in
   analyze_preview_task with refund. Verified: 20s match upload → failed with friendly error.
6. temperature 0.0 both Gemini call sites. seed NOT supported by proxy (UnsupportedParamsError).
7. INTELLIGENT DUAL-PASS (cross-verification):
   - VERIFICATION_PROMPT + _apply_cross_verification + _cross_verify_full_report in server.py
   - Pass 2 re-watches video, verdicts per timeline claim (identity+event), independent scores
   - Deterministic merge: drop WRONG_PLAYER/NOT_SEEN, track-window drop (8s), timestamp snap (2s),
     scores = rounded mean, scores_confidence=low if gap>=3, meta in full_report.cross_verification
   - Runs in main path AND identity-retry path. Fail-open on error.
   - UI: PremiumBuildingDashboard stage "Cross-Verifying"; PremiumReportV2 v2-cross-verified-strip
8. player_photo_url exposed in serializer+status; R2 flush handles photo (reuses display crop URL
   when photo_source=video_crop).

## Consistency measurements (same 41s video, identical 6 taps, admin uploads)
- BEFORE (temp 0.2, single pass): A vs B → technical 3 vs 8, ALL 5 scores differed,
  tier Strong_club vs Pro_academy, timeline narratives contradictory (defensive vs goal-scoring).
- Reports A=3ad7ef64… B=65d45868… kept for comparison until cleanup.
- AFTER (temp 0.0 + dual-pass): runs C=c7d76766… D=63caff03… → results pending below.
- Assets for re-runs: /app/memory/consistency_assets/ (video.mp4, marker.jpg, anchors.json, token).
- CLEANUP TODO: delete test reports A/B/C/D + MinDur(41d71f82…) via admin, remove assets dir.
