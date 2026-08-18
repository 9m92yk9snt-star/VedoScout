// FIX 00B — the ONE authoritative frontend completion check for the full
// report lifecycle: generating → verifying → finalizing → ready.
// `has_full_report`/`full_report` alone MUST NOT mean finalization is done —
// the backend may still be verifying identity or persisting proof assets.
// Legacy docs that predate the lifecycle states carry no status and are
// complete by definition when the report body exists.
export function isFullReportReady(data) {
  if (!data) return false;
  const st = data.full_report_status;
  if (st === "ready") return true;
  if (st) return false; // generating | verifying | finalizing | failed | awaiting_confirmation
  return data.has_full_report === true || !!data.full_report;
}
