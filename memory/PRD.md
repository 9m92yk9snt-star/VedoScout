# PRD — Football Player Video Analysis App

## Original problem statement
React + FastAPI + MongoDB app that analyses football match footage of a tapped player and produces verified scouting reports. User taps are ground truth; FIX04 accepted geometry is the owned track; FIX02 is fail-closed (identity==CONFIRMED && event==CONFIRMED only). Authority chain: VIDEO → TAPPED PLAYER → CROSS-VERIFIED EVENT → CANONICAL ACTION+OUTCOME → STABLE EVENT_ID → DETERMINISTIC VERIFIED STATS → CLAIM RECONCILIATION → REPORT.

## Completed phases (all committed, all suites green)
- FIX00A tap authority (16), FIX00B ready contract (31), FIX01 evidence authority (29), FIX02 fail-closed (29), FIX03 video timebase (26)
- FIX04 tracking geometry + Corr 01/02 (38)
- FIX05 ground anchor/ellipse + Corr 01 (30)
- FIX06 pace/distance camera compensation + Corr 01/02 (33)
- FIX07 verified stats & claim reconciliation (V01–V50), commit d2b5d27; INTRO_CLIP_VERSION bumped 1→2
- FIX07 — CORRECTION 04 (June 2026), commit 2a3f74e:
  - C20 scan coverage keys built ONLY from verified scoring rows: identity==CONFIRMED + normalize_canonical survivors (GOAL=SHOT+SCORED+visible, ASSIST=PASS/CROSS+TEAMMATE_SCORED+visible) + parseable snapped ts; WRONG_PLAYER/NOT_VISIBLE/SAVED/invisible/TEAMMATE_SHOT rows stay structurally valid but never cover a known GOAL/ASSIST
  - Tests C20–C26. FIX07 suite 87 passed; regressions FIX06 33, FIX05 30, FIX04 38, FIX03 26, FIX02 29, FIX01 29, FIX00B 31, FIX00A 16; server.py untouched
- FIX07 — CORRECTION 03 (June 2026), commit 8198acd:
  - C14 dedicated `_SCAN_RESULTS` enum (SCORED, TEAMMATE_SCORED, TEAMMATE_SHOT, SAVED, BLOCKED, OFF_TARGET, NO_GOAL, OUTCOME_NOT_VISIBLE, COMPLETED, UNKNOWN) — `_valid_scan_row` no longer accepts general RESULTS values (WON/FAILED/POSSESSION_* invalidate whole scan); general RESULTS unchanged
  - C15 full-scan consistency: every surviving cross-verified canonical GOAL/ASSIST must have an exact-time/action scan entry (same track snap, no fuzzy); omission → performed=false + incomplete_scoring_coverage=true → goals_assists unavailable, events remain; extracted shared `_snap` helper
  - Tests C14–C19 added; V45 scan fixture completed for C15. FIX07 suite 80 passed; regressions FIX06 33, FIX05 30, FIX04 38, FIX03 26, FIX02 29, FIX01 29, FIX00B 31, FIX00A 16; server.py untouched
- FIX07 — CORRECTION 02 (June 2026), commit 275dae9:
  - C07 `_valid_scan_row` schema validation: scan performed only when discovered_scoring_events is a list and EVERY row matches schema (parseable ts, identity/event/action/result enums, boolean outcome_visible, optional string note); [] is a valid completed scan; malformed scans never partially trusted
  - C08 `verified_stats.goals_assists_available`; goals/assists = None when scan not performed; match_stats omits goals/assists keys and carries `goals_assists_source` ("full_video_scoring_scan" | "unavailable"); other timeline stats remain
  - C09 verified_stat_line only exists behind a valid completed scan
  - C10 `_sentence_supported` fails closed on goal/assist claims when totals unavailable; `_canonical_line` returns neutral "Verified match involvement." (never manufactured zeros); exact verified event language remains
  - Tests: FIX07 suite 74 passed (67 + C07–C13); regressions FIX06 33, FIX05 30, FIX04 38, FIX03 26, FIX02 29, FIX01 29, FIX00B 31, FIX00A 16; server.py untouched
- FIX07 — CORRECTION 01 (June 2026), commit c563105:
  - C01 normalize_canonical: GOAL/ASSIST never manufacture missing action type (GOAL+UNKNOWN → UNCLASSIFIED)
  - C02 scoring_scan.performed only for a valid verifier list; verifier fail_closed_error → verified_stats.available=False, match_stats source=verified_events_unavailable (no authoritative zeros)
  - C03 scan promotes existing SHOT→GOAL / PASS,CROSS→ASSIST at exact snapped time/action instead of duplicating or dropping
  - C04 discoveries/promotions require same player-track support as _apply_cross_verification (≥10 pts, within 8 s, ≤2 s snap); verifier-only behavior preserved when no usable track
  - C05 claim reconciliation extended to technical/tactical/physical/mentality/parents_package
  - C06 event-bound snapshot/cinematic titles & event text obey canonical type; ASSIST goal-language requires explicit "teammate"; aggregate claims (hat-trick etc.) reconciled in event titles/descriptions
  - Tests: FIX07 suite 67 passed (47 + 20 new C-tests); regressions FIX06 33, FIX05 30, FIX04 38, FIX03 26, FIX02 29, FIX01 29, FIX00B 31, FIX00A 16

## Key files
- backend/verified_stats.py — FIX07 deterministic stats + reconciliation
- backend/server.py — verifier prompt/schema (~2860–3010), _apply_cross_verification (~8141), scan merge (~8220), pipeline hooks (~8476, ~8918)
- backend/evidence_authority.py, intro_clip.py, pdf_v2.py
- Protected: player_tracking.py, tracking_geometry.py, video_timebase.py, motion_compensation.py, speed_metrics.py, movement_metrics.py, tele_clip.py, telestration.py

## Branch note
Local fork checkout only has `main`; user-named branches (fix-07-verified-stats-claims) do not exist in this environment. Commits land on main; ChatGPT handles branch hygiene later. Do NOT create branches/PRs/merges.

## Next
- Waiting for "@GitHub tjek FIX 07" review feedback; no pending backlog items.
