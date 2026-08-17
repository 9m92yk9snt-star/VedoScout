# SCOUTMEPLAY — FULL END-TO-END ANALYSIS ENGINE AUDIT (June 2026)
Diagnosis only. No code changed. Evidence: source tracing + real report docs (d8c04d5d…) + preview logs.

## A — EXECUTIVE DIAGNOSIS (10 findings)
1. **No event/evidence IDs anywhere.** Events are Gemini-generated `video_comments` keyed by "MM:SS" STRINGS. Every binding (finding→evidence→frame→clip→frontend) is timestamp-string/nearest-second matching. Single biggest architecture risk.
2. **Dual timebase.** Raw upload timeline vs transcoded analysis rendition (t_off) vs constant-FPS frame math (`t = frame/fps`). Variable-frame-rate phone video can drift seconds over long videos. Partially masked by fail-safe GPT gates (wrong frames get deleted, not fixed).
3. **Identity ownership ≠ spatial geometry — correctly separated, but geometry is the weak link.** Proven case: 29.0–29.5s box a full body-height off-player while identity was intact. Tracker (NCC + color veto + honest stops) is authoritative for location; the render layer now resolves/rescues/hides — a visual mitigation of an upstream tracking weakness.
4. **score_meaning is computed at READ time**, not persisted. A cv_shadow rerun changes risky windows → the same report can show different evidence picks on different days. Consistency risk.
5. **Verification is real but distributed.** VERIFIED = (GPT frame-identity gate on raw crop) + (not inside cv_shadow risky/empty windows) + (cross-verification merge survived). No single "verified" flag object; each consumer recomputes parts of it.
6. **The full video is decoded ~5–6×** per report (transcode, tracking, cv_shadow, frame extraction, clip rendering, preview clip/poster). Main CPU cost driver.
7. **LLM call fan-out per report**: content gate 1, preview 1(+1 retry), identity profile 1, full report 1(+1 retry on poor identity stats), cross-verify 1, frame gates ~1/moment, doubt checks ≤3, clip edge checks ≤2×3 rounds/moment, agent review 1. Retries can silently double Gemini video cost.
8. **The ring guard (verify_ring_placement) is ACTIVE** — but only as a clip-window honesty gate (GPT judges ring-rendered crops at window edges; shrinks/denies clips). It does NOT feed identity/evidence/analysis. Rendering errors can therefore reduce proof coverage (fail-safe direction).
9. **Recovery machinery is good now** (preview watchdog fail+refund→requeue-once; full-report watchdog requeue; R2 tmp mirrors; heartbeats; liveness UI) — but only added recently; production before that froze forever on pod restarts.
10. **Observability gap**: `pipeline_trace` exists (capped 50) but entries don't carry the key the status endpoint reads (`pipeline_stage` is always None — display-only bug found during this audit). No end-to-end IDs → post-mortem tracing relies on timestamps + logs.

## B — REAL PRODUCTION PIPELINE (actual code path)
1. **Upload** — `UploadPage.jsx`: file pick → `startBgUpload` → `chunkedUpload` (8MB chunks, 5 retries + 3 resume passes) → `POST /api/me/chunked-upload/{init,chunk,complete}` (`chunked_upload.py`: local assembly + R2 `tmp/{name}` mirror 24h, multi-pod safe, idempotent per index) → `temp_video_token`. Files ≤12MB: single multipart POST.
2. **Report creation** — `POST /api/reports/upload` (server.py ~5290): materialize raw (token→local), save marker image, mirror raw+marker→R2 tmp, insert report `{analysis_status: analyzing, progress_step: 1}` → background `_analyze_preview_task_with_timeout` (900s cap, watchdog heartbeats).
3. **Preview pipeline** — `analyze_preview_task` (5717+), stages via `_trace`: transcode_start (analysis rendition ≤1280w veryfast crf32, `t_off`) → tap refinement → anchor crops→R2 → `build_identity_profile` (GPT, async) → preview clip → `run_content_gate` (Gemini: is this football?) → `call_gemini_with_video` preview (+`verify_preview_summary`, retry once) → poster → `analysis_status: ready`, `progress_step: 5`. Watchdog: stale heartbeat 5min → requeue once → fail+refund.
4. **Doubt gate** — low-confidence crossovers → `doubt_moments`/`doubt_status: awaiting` → user confirms taps → `_verify_doubt_taps` (GPT gate) → extra anchors.
5. **Full report** — `generate_full_report_task` (8020+, wrapped by `_full_report_with_heartbeat`): `_ensure_report_video_local` (R2 restore) → PARALLEL `_tracking_core` (`track_player`: NCC per anchor span ±4s, scene-cut stops, non-green veto 0.55, span limits) + `_audio_core` → doubt wait → `cv_shadow` bg task (admin diagnostics only, engine v6) → `compute_movement_map` → full prompt (FULL_REPORT_PROMPT + identity_profile_block + memory + ground-truth track block) → **Analysis A**: `call_gemini_with_video` → full_report JSON (scores, texts, `video_comments` "MM:SS", action_timeline, match_stats…) → **Analysis B**: `_cross_verify_full_report` (independent Gemini pass) + `_apply_cross_verification` (merge/downgrade authority) → `_persist_video_frames` (frame per moment; GPT `verify_frame_identity` on RAW crop vs anchor refs; failed → frame dropped; passed → `telestration.render_telestration` grounded ellipse; R2) → poor identity_stats → ONE full retry → `_generate_tele_clips` (per moment: `_teleclip_verified_window` — GPT `verify_ring_placement` on ring-rendered edge crops, ≤3 shrink rounds; `tele_clip.generate_tracked_clip` — ≥1.2s verified core, padded to ≥3s raw context, marker only in verified window, `tele_clip_start/end` persisted; R2) → `full_report_status: ready`.
6. **Serving** — `GET /api/reports/{id}`: `_serialize_report` whitelist, signed R2 URLs, `ensure_video_frames` (restore/backfill on read — can spawn `_persist_video_frames` task), `build_score_meaning(doc)` computed AT READ (uses `_verified_seconds`, `_risky_seconds` from cv_shadow, `_pick_evidence` hard gate: identity-verified + not risky). `GET /reports/{id}/status`: progress_step, statuses, heartbeat, doubt.
7. **Frontend** — `PrecisionScanOverlay` (+liveness), `PremiumBuildingDashboard` (+liveness), `PremiumReportV2` → `scoremeaning.jsx` SEE WHY (`sm-evidence-*`) → `playAt(ts)`: exact-string match `video_comments.timestamp === ts && tele_clip_url` → `ProofPlayerSheet` (THE MOMENT = sec − tele_clip_start; fallback full video seek sec−4).

## C — ARCHITECTURE MAP (dependencies)
taps/anchors → identity refs (GPT profile + crops) → {preview analysis, tracking, frame gates, clip edge gates}
player_track (authoritative location) → {movement map, cv_shadow, evidence frames, clips, ellipse}
full_report (Analysis A) ← cross-verify (Analysis B) → video_comments → {frames (GPT gate) → clips (GPT edge gate) → frontend proofs} and → score_meaning (read-time) → report UI
cv_shadow → {admin dialog, risky windows → score_meaning evidence picks, clip risk fades, gap-bridge aggregate rule}
watchdogs → {analysis_status, full_report_status} · R2 → all durable media · Mongo → all state

## D — DATA LINEAGE (traced on real report d8c04d5d)
Finding "Cuts inside from the right wing…" → video_comments ts "00:36" → sec 36 → frame `moment_*.jpg` (GPT identity gate PASSED) + clip 32.02–38.02 (edges GPT-verified, THE MOMENT at 36−32.02=3.98s) → track points around 36s (coverage 2.13–72.03) → identity from tap anchors (span 3.8–70.9) + GPT ref crops. Same chain verified for "00:49" (clip 47.38–53.38) and "00:57" (frame only — clip window too short → honest no-clip). **Lineage EXISTS functionally, but every link is a timestamp, not an ID.** Note: 36s is a shadow-flagged risk zone — its assets passed the GPT gates; the layered gates (not the tracker) are what carries correctness there.

## E — SINGLE SOURCES OF TRUTH
| Concept | Source | Status |
|---|---|---|
| Player identity | tap anchors + GPT ref crops (`anchors`) ; per-frame: GPT gate verdicts | OK (single) |
| Player location | `player_track.points` (raw-video normalized) | OK — but consumers re-derive smoothing separately (frames: nearest pt; clips: ±2 smooth+EMA+resolver) |
| Timestamp | float seconds (raw timeline) AND "MM:SS" strings in video_comments | **ARCHITECTURE RISK — dual representation** |
| Event | full_report.video_comments (Gemini text) | **ARCHITECTURE RISK — no IDs** |
| Verified evidence | frame gate result (frame_url/telestrated) + read-time risky windows | **RISK — distributed, partly read-time** |
| Score | full_report categories (post cross-verify) | OK |
| Report finding | full_report texts + score_meaning (READ-time) | **RISK — not persisted** |
| Video proof | video_comments.tele_clip_url + start/end | OK (since clip_start persisted) |
| Analysis status | analysis_status + full_report_status + doubt_status + progress_step | Acceptable — 3 coordinated fields, no single machine |

## F — DUPLICATE / CONFLICTING SYSTEMS
- Tracking: ONE production tracker (player_tracking.py). cv_shadow's MOT/state machine is diagnostics-only — no overwrite path. ✔
- Two smoothing/anchor derivations (static frames vs clips) now share `_draw_ring`/`_ground_anchor` — converged. ✔
- Two analysis passes (A/B) by design; merge authority = `_apply_cross_verification`. ✔
- Legacy present but inert: `_make_chip/_blend_chip` (DEAD), PLAYER TRACKED badge (REMOVED), old ring/label rendering (REMOVED).

## G — BROKEN / WEAK INTEGRATIONS (most important)
1. Timestamp-string contract frontend↔backend ("00:36" exact match; format drift → silent fallback to full video).
2. Read-time score_meaning vs persisted report (shadow rerun changes evidence picks later).
3. Constant-FPS assumption vs VFR video (frame↔second conversion everywhere: tracking, shadow, frames, clips).
4. `ensure_video_frames` on READ can spawn `_persist_video_frames` concurrently with pipeline/regenerate (duplicate work, last-writer-wins).
5. Renderer→clip-gate coupling: ellipse render errors shrink/deny clips (fail-safe but reduces product value silently).
6. Tracker geometry drift during sprints → resolver/rescue compensates; beyond ~1.9·bh the marker hides (honest, but coverage loss).

## H — RACE / ASYNC RISKS
- Watchdog double-claim: mitigated (atomic find_one_and_update). ✔
- Preview requeue vs still-alive task: 900s hard cap kills stragglers; claim refreshes heartbeat. Low risk.
- ensure_video_frames (read) vs _persist_video_frames (pipeline) vs regenerate-evidence (admin): no lock — duplicate frame/clip generation possible. MEDIUM.
- Full retry-once path re-enters _persist_video_frames — old assets overwritten mid-poll. LOW.
- Hot-reload (preview) / pod restart (prod) kills create_task children (cv_shadow bg, tele clips) — full watchdog requeues whole task, but cv_shadow bg is NOT requeued (stays absent until manual run). LOW (diagnostics only).

## I — ACCURACY RISKS (ranked)
- CRITICAL: dual timebase / VFR drift (silent, end-of-video events most exposed).
- CRITICAL: timestamp-keyed evidence binding (wrong-pairing class of bugs).
- HIGH: tracker geometry in sprints/crowds (identity kept; location off → downstream visual + coverage).
- HIGH: read-time score_meaning instability.
- MEDIUM: Gemini timestamp perception vs rendition timeline (t_off applied to track, but Gemini sees rendition — mapping correctness rests on t_off discipline).
- MEDIUM: retry-once full report can produce a different narrative than first pass (nondeterminism).
- LOW: EMA/smoothing lag at render (bounded, sprint-responsive now).

## J — PERFORMANCE BOTTLENECKS (est. impact order)
1. 5–6 full decode passes per video (transcode, tracking, shadow, frames, clips, poster).
2. Gemini video calls ×3 (+retries) — wall-clock dominates "being analysed" phase.
3. GPT vision gate fan-out (frames + clip edges ×3 rounds ×moments).
4. NCC tracking at 12.5Hz over all anchor spans (CPU-bound; slow prod pods).
5. Clip rendering (imageio/libx264 per moment) + R2 uploads.
6. Read-time score_meaning on every report GET (small but repeated).

## K — STABILITY RISKS
- Pod restart mid-pipeline: now covered (heartbeats, requeue, R2 restore). Residual: repeated OOM restarts → 2 attempts → honest fail.
- Local disk ephemerality: raw/marker mirrored (24h TTL) — **reports older than 24h cannot re-run preview from mirrors; full path uses persisted rendition (video_url_override) — OK**.
- tmp file accumulation in uploads/ (no janitor observed) — slow disk growth. LOW.
- Unbounded `pipeline_trace`? capped 50 ✔. Large report docs (full_report + shadow + trace + comments) approach big-doc territory — monitor.

## L — LEGACY CODE
| Item | Status |
|---|---|
| `_make_chip` / `_blend_chip` (tele_clip) | DEAD |
| PLAYER TRACKED badge | REMOVED |
| name/pill/pointer rendering | REMOVED |
| `verify_ring_placement` | ACTIVE (clip-window gate only) |
| cv_shadow v6 (+MOT/team/reacq) | ACTIVE, shadow/diagnostics only |
| gap bridging | ACTIVE behind aggregate rule (currently bridging 0 — conservative) |
| direct ≤12MB upload path | ACTIVE fallback |
| movement map, audio events | ACTIVE support inputs |
| old preview URL/fetch experiments (url_video_fetch) | ACTIVE for URL fetch flow |

## M — ERROR HANDLING PROBLEMS
- Numerous best-effort `except: pass` (R2 mirrors, trace, heartbeat) — intentional, low risk.
- Silent quality reducers: audio extraction failure → analysis continues without audio (warn only); identity-profile failure → prompt without profile; cross-verify failure path → ? (merge skipped → Analysis A unverified narrative could ship — verify before optimizing; flagged for Phase 1).
- Retry paths (preview retry, full retry) hide first-pass failures and double cost without surfacing to user/admin.
- Frontend: proof lookup failure is silent (falls to full video, no telemetry).

## N — TOP 20 TECHNICAL PROBLEMS (Problem · Location · Root cause · Consequence · Severity · Confidence)
1. Timestamp-string evidence binding · video_comments/scoremeaning/playAt · no IDs · wrong/missing proof pairing · CRITICAL · High
2. Dual timebase raw vs rendition vs FPS-math · tracking/frames/clips · constant-fps + t_off discipline · drift on VFR/long videos · CRITICAL · Medium
3. Read-time score_meaning · server GET · computed not persisted · unstable findings after shadow rerun · HIGH · High
4. Tracker sprint geometry · player_tracking NCC · template latch + fixed box · off-player boxes (29s case) · HIGH · High (proven)
5. Cross-verify failure path may let A ship unverified · _apply_cross_verification error branch · needs confirmation · unverified narrative · HIGH · Medium
6. ensure_video_frames read-time task spawn · server 6971 · no lock vs pipeline/regenerate · duplicate assets/races · MEDIUM · High
7. Full-report retry duplicates Gemini cost silently · 8345-8396 · identity_stats trigger · 2× cost, narrative nondeterminism · MEDIUM · High
8. VFR fps from cv2 assumed exact · everywhere frame↔sec · cv2 CAP_PROP_FPS · off-by-frames · MEDIUM · Medium
9. Ellipse gate coupling (render→clip window) · _teleclip_verified_window · design choice · silent proof-coverage loss · MEDIUM · High
10. pipeline_trace key mismatch in status (`pipeline_stage` None) · server status endpoint · wrong key read · liveness stage never shows · LOW · High
11. cv_shadow bg not requeued after pod death · full task create_task · fire-and-forget · missing diagnostics · LOW · High
12. tmp/upload dir janitorless growth · uploads/ · no cleanup loop · disk creep · LOW · Medium
13. Frontend exact-string ts match ("0:36" vs "00:36") · playAt · format coupling · silent full-video fallback · MEDIUM · High
14. 24h R2 tmp TTL vs later requeues · chunked_upload/upload · TTL choice · old reports unrecoverable at preview stage · LOW · High
15. Multiple smoothing derivations frame vs clip · telestration/server vs tele_clip · historic · same instant renders differ slightly · LOW · High
16. Big report docs (full_report+shadow+trace) · Mongo · accretion · doc-size ceiling long-term · LOW · Medium
17. GPT gate fan-out cost scaling with moments · _persist/_teleclip · per-moment calls · cost grows with content · MEDIUM · High
18. progress_step only 1..5 · preview UI · coarse · "frozen" perception (now mitigated by liveness) · LOW · High
19. No proof-play telemetry · proofplayer · none · can't detect broken proofs in prod · MEDIUM · High
20. Doubt wait blocks full pipeline up to DOUBT_WAIT_S · _run_doubt_confirmation · sync wait · slower reports when user idle · LOW · High

## O — OPTIMIZATION OPPORTUNITIES (classified — NOT implemented)
- QUICK WIN: fix pipeline_trace stage key in status; normalize ts strings one place; proof-play telemetry event; janitor for uploads/tmp.
- ACCURACY: introduce `event_id`/`evidence_id` minted when video_comments are parsed; persist score_meaning snapshot at report-ready; single timeline doc field (fps, t_off, timebase note) consumed by all converters.
- ARCHITECTURE FIX: one `resolve_time(sec↔frame)` utility; one persisted "canonical position at t" API used by frames+clips; lock ensure_video_frames vs pipeline (report-level mutex flag).
- PERFORMANCE: reuse ONE decode pass for tracking+shadow sampling; batch GPT gates (multi-image calls); cache rendition; skip poster re-extract.
- STABILITY: requeue cv_shadow bg with full task; extend raw mirror TTL or persist raw to durable key while status != ready.
- COST: gate full-report retry behind explicit flag/admin; reduce clip edge rounds from 3→2 with same trust maths.

## P — PROPOSED TARGET ARCHITECTURE (preserving working parts)
Keep: tap→identity refs, NCC tracker as location authority, A/B dual Gemini analysis with merge authority, GPT fail-safe gates, shadow diagnostics, watchdogs, R2 media, render-layer resolver.
Add (thin layers, no rewrites):
1. **Event ledger**: when Analysis A returns, mint `event_id` per video_comment; carry it through frames, clips, score_meaning, frontend (`data-event-id`). All bindings become ID joins; timestamps become display-only.
2. **Timebase contract**: one persisted `timeline` object per report `{fps_detected, vfr_suspected, t_off, duration}` + one converter module used by tracking/shadow/frames/clips.
3. **Verification record**: persist per-event `verified: {frame_gate, risk_windows, cross_check}` at pipeline time; score_meaning reads the record instead of recomputing.
4. **Position service**: single `position_at(report, t)` (smooth+resolver) used by both static frames and clips.
5. **Asset locks**: report-level `assets_lock` field around _persist/_generate/regenerate.

## Q — RECOMMENDED IMPLEMENTATION ORDER
- Phase 0 — protect: snapshot current outputs of 3 seeded reports (already have iteration tests); freeze contracts (`tele_clip_start`, statuses).
- Phase 1 — critical correctness: event_id ledger + verification record persisted (depends on nothing; unblocks all bindings). Confirm cross-verify failure branch behavior.
- Phase 2 — pipeline integration: timebase contract + converter; frontend ID-based proof lookup (falls back to ts during migration); asset locks.
- Phase 3 — performance: shared decode pass (tracking+shadow), GPT gate batching, retry gating.
- Phase 4 — stability: cv_shadow requeue, raw mirror TTL policy, tmp janitor.
- Phase 5 — cleanup: delete dead chip code, legacy flags; collapse duplicate smoothing.
- Phase 6 — observability: end-to-end IDs in logs (`report_id/event_id/asset`), fix trace stage key, proof-play telemetry, admin lineage view.
Dependencies: 1 → 2 → (3,4 parallel) → 5 → 6 (6 can start alongside 2).
