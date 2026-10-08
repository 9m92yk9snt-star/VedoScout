import { isFullReportReady } from "./reportReady.mjs";

export function isPreviewReady(data) {
  if (!data) return false;
  const status = data.analysis_status ?? data.status;
  if (status && status !== "ready") return false;
  return data.preview_ready === true || !!data.preview;
}

const FULL_PHASES = {
  awaiting_confirmation: ["A quick player check", "Confirm the player in the highlighted moments so the analysis can continue."],
  verifying: ["Checking the evidence", "Checking which actions can be attributed to your player before completing the report."],
  finalizing: ["Preparing your report", "Saving the report and its video evidence. The report opens when this step is complete."],
};
const TASKS = {
  tracking_start: "Following your player through the video",
  identity_timeline_start: "Checking player identity across the video",
  identity_timeline_complete: "Preparing the action review",
  unified_preparation_start: "Preparing sequences for action review",
  unified_preparation_complete: "Preparing the action review",
  sequence_model_start: "Reviewing play and the sequence of actions",
  sequence_model_retry: "Repeating the action review",
  sequence_model_complete: "Preparing the evidence review",
  physical_reconstruction_start: "Connecting touches, passes and subsequent play",
  physical_reconstruction_complete: "Reconciling actions with the evidence",
  canonical_reconciliation: "Reconciling actions with the evidence",
  legacy_fallback: "Continuing with the alternative analysis path",
  evidence_assets_start: "Preparing video evidence for the report",
  evidence_assets_complete: "Completing the report checks",
};

/** Shared by the upload sheet, report page, dashboard and background tracker.
 * Passing time never advances a phase, changes a score, or implies readiness.
 */
export function getAnalysisView(data = {}, { phase, uploadPct, target } = {}) {
  const full = target ? target === "full" : data.analysis_target === "full" || !!(data.is_paid || data.manually_unlocked);
  const previewReady = isPreviewReady(data);
  const fullReady = isFullReportReady(data);
  const complete = full ? fullReady : previewReady;
  const st = data.full_report_status;
  const previewStatus = data.analysis_status ?? data.status;
  const step = Number(data.progress_step) || 1;
  let key, title, detail;
  if (phase === "uploading") {
    key = "uploading"; title = "Uploading your video";
    detail = "Keep this page open while your video is being sent.";
  } else if (phase === "saving") {
    key = "preparing"; title = "Saving your video";
    detail = "Your upload is being received. Analysis starts after the server has saved it.";
  } else if (complete) {
    key = full ? "ready" : "preview_ready";
    title = full ? "Your full report is ready" : "Your preview is ready";
    detail = full ? "The completed report and available video evidence are ready to open." : "This is the initial preview. The full report is a separate analysis.";
  } else if (previewStatus === "failed" || (full && st === "failed")) {
    key = "failed"; title = "Analysis was interrupted";
    detail = (full && data.full_report_error) || data.analysis_error || data.error || "Check the status or try again.";
  } else if (full && FULL_PHASES[st]) {
    key = st; [title, detail] = FULL_PHASES[st];
  } else if (full && st === "generating") {
    key = [undefined, null, "queued", "full_start"].includes(data.full_pipeline_stage) ? "queued" : "analyzing";
    title = key === "queued" ? "Waiting for analysis to start" : "Your video is being analyzed";
    detail = TASKS[data.full_pipeline_stage] || "Reviewing your player’s actions and the surrounding play.";
  } else if (previewReady && full) {
    key = "queued"; title = "Preparing the full analysis";
    detail = "The initial review is complete. Your full report is still being prepared.";
  } else if (step >= 4 && previewStatus === "analyzing") {
    key = "initial_review"; title = "Reviewing your video";
    detail = "Preparing the initial review before the full analysis.";
  } else if (step === 3 && previewStatus === "analyzing") {
    key = "checking_video"; title = "Checking your video";
    detail = "Checking the video content and preparing it for analysis.";
  } else {
    key = "preparing"; title = "Preparing your video";
    detail = "Preparing the video and the player marks you supplied.";
  }
  const duringUpload = ["uploading", "saving"].includes(phase);
  const prepared = !duringUpload && (previewReady || ["generating", ...Object.keys(FULL_PHASES), "ready"].includes(st) || (previewStatus === "analyzing" && step >= 3));
  const analyzed = full ? ["verifying", "finalizing"].includes(st) || fullReady : previewReady;
  const labels = full ? ["Video received", "Reviewing play", "Final checks"] : ["Prepare video", "Create preview"];
  const states = full
    ? [prepared ? "done" : "active", analyzed ? "done" : prepared ? "active" : "pending", fullReady ? "done" : analyzed ? "active" : "pending"]
    : [prepared ? "done" : "active", previewReady ? "done" : prepared ? "active" : "pending"];
  return {
    key, title, detail, target: full ? "full" : "preview", complete: !duringUpload && complete,
    failed: key === "failed", confirmation: key === "awaiting_confirmation",
    uploadPercent: key === "uploading" && Number.isFinite(uploadPct) ? Math.max(0, Math.min(100, uploadPct)) : null,
    task: TASKS[data.full_pipeline_stage] || null,
    steps: labels.map((label, index) => ({ label, state: states[index] })),
  };
}

export function elapsedLabel(startedAt, now = Date.now()) {
  const start = typeof startedAt === "number" ? startedAt : Date.parse(startedAt);
  if (!Number.isFinite(start) || start > now) return null;
  const seconds = Math.floor((now - start) / 1000);
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

export function activityLabel(at, now = Date.now()) {
  const time = Date.parse(at);
  if (!Number.isFinite(time) || time > now + 60_000) return "Waiting for a server update";
  const seconds = Math.max(0, Math.floor((now - time) / 1000));
  if (seconds > 120) return "No recent server update · checking again";
  return seconds < 60 ? `Server activity ${seconds}s ago` : `Server activity ${Math.floor(seconds / 60)}m ago`;
}

export function assetUrl(src, base = "") {
  if (!src) return null;
  return /^(https?:|blob:|data:)/i.test(src) ? src : `${base}${src}`;
}

/** Deadline ranges are server-calibrated; the client clock only counts down. */
export function completionLabel(data, now = Date.now()) {
  const estimate = data?.completion_estimate;
  const updated = Date.parse(estimate?.calculated_at);
  const heartbeat = Date.parse(data?.last_progress_at);
  if (Number.isFinite(heartbeat) && (heartbeat > now + 60000 || now - heartbeat > 120000)) return "Waiting for a status update";
  if (!["estimated", "overdue"].includes(estimate?.status) || !Number.isFinite(updated)
      || updated > now + 60000 || now - updated > 120000) return "Estimate not available yet";
  const latest = Date.parse(estimate.latest_at), earliest = Date.parse(estimate.earliest_at);
  if (!Number.isFinite(latest) || !Number.isFinite(earliest) || earliest > latest) return "Estimate not available yet";
  if (estimate.status === "overdue" || latest <= now) return "Taking longer than estimated";
  const low = Math.max(0, Math.ceil((earliest - now) / 60000));
  const high = Math.ceil((latest - now) / 60000);
  return low === 0 ? `Under ${high} min` : low === high ? `About ${high} min` : `About ${low}–${high} min`;
}
