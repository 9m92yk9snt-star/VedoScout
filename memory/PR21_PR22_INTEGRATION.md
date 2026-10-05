# PR #21 + #22 integration (prepared for live deploy) — 2026-10-05

Repo: 9m92yk9snt-star/VedoScout. Integrated into /app (Emergent deploy source). NOT deployed, NOT pushed/merged on GitHub by agent. No analyses run.

## What was integrated
- PR #21 `fix12-live-identity-event-recovery` head `6f60e04`
- PR #22 `report-evidence-export` head `0d23f70a3de4bd3435482f53c27c32093bcc06f1`
- Base: GitHub main `f051fa11c6d73eccb0e15a643c57b6d7c5f9fccd` (currently LIVE → rollback target)
- Clean 3-way merge, NO conflicts (git auto-merged server.py + .github workflow). Repro merge SHA (scratch): a09dece.
- Synced into /app via rsync (excluded .env/.git/.emergent/node_modules/uploads/pdfs/yarn.lock/memory). requirements.txt & package.json unchanged → no dep installs.

## Export extension (added by agent on top of PR #22)
Files: backend/report_evidence_export.py, report_export_routes.py, scripts/export_report_evidence.py, tests/test_report_evidence_export.py
- build_export() gains run_records / model_call_records params; writes `analysis_runs.json`, `analysis_model_calls/index.json`, `analysis_model_calls/NNN.json` (raw model responses).
- Strictly report-scoped: records with foreign report_id are dropped + logged in missing_data.json. Redaction + size caps (MAX_MODEL_CALLS=2000) reused. Read-only; no writes; no model calls.
- Route + CLI fetch analysis_runs/analysis_model_calls by {report_id} and pass in.

## Collections schema (PR #21, analysis_jobs.py)
- analysis_runs: {run_id (unique), report_id, updated_at, outputs.<audited fix10a_/fix10b_/unified_/sequence/canonical/...>}; run manifest via analysis_jobs.manifest().
- analysis_model_calls: {call_id (unique), run_id, report_id, session_id, model="gemini-2.5-pro", status, started_at/finished_at, video_sha256, video_role, prompt_sha256, response_sha256, response_bytes, raw_response(≤8MB), raw_response_truncated, error_type}.

## Verification (all on integrated /app)
- Export tests: 30/30 PASS (incl. new cross-report isolation test `test_run_audit_collections_scoped_to_report_and_exclude_foreign`).
- PR #21 analysis regressions (fix09/fix10/fix12): 224/224 PASS (run with --asyncio-mode=auto).
- Frontend production build: SUCCESS. AdminPage "Download analysis evidence ZIP" button wired to /admin/reports/{id}/evidence-export.
- Backend boots (GET /api/ = 200). Export route returns 401 unauth (wired + admin-protected).
- deployment_agent readiness scan: PASS, no blockers.
- Production model path uses real LlmChat .with_model("gemini","gemini-2.5-pro"); no test-stubs in prod path (_stub_invalid = defensive invalid-input placeholder). No hardcoded goals/assists found.
- Full bare pytest suite: analysis+export green; ~86 failed/248 errors are pre-existing app integration tests needing live services (Stripe/subscriptions/dashboard/veo/DB) — NONE in analysis/export code.

## Rollback
GitHub main `f051fa11c6d73eccb0e15a643c57b6d7c5f9fccd` (the version live before this integration).

## NOT done (by instruction)
No deploy, no new analysis, no GitHub merge/push, no change to old report 5df7c569 (untouched). Video-analysis correctness NOT declared solved — pending user's live video test.
