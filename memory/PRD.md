# PRD — Football Player Video Analysis App

## Original problem statement
React + FastAPI + MongoDB app that analyses football match footage of a tapped player and produces verified scouting reports. User taps are ground truth; FIX04 accepted geometry is the owned track; FIX02 is fail-closed (identity==CONFIRMED && event==CONFIRMED only). Authority chain: VIDEO → TAPPED PLAYER → CROSS-VERIFIED EVENT → CANONICAL ACTION+OUTCOME → STABLE EVENT_ID → DETERMINISTIC VERIFIED STATS → CLAIM RECONCILIATION → REPORT.

## Completed phases (all committed, all suites green)
- FIX00A tap authority (16), FIX00B ready contract (31), FIX01 evidence authority (29), FIX02 fail-closed (29), FIX03 video timebase (26)
- FIX04 tracking geometry + Corr 01/02 (38)
- FIX05 ground anchor/ellipse + Corr 01 (30)
- FIX06 pace/distance camera compensation + Corr 01/02 (33)
- FIX07 verified stats & claim reconciliation (V01–V50), commit d2b5d27; INTRO_CLIP_VERSION bumped 1→2
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
