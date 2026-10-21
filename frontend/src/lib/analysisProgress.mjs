import { isFullReportReady } from "./reportReady.mjs";

export function isPreviewReady(data) {
  if (!data) return false;
  const status = data.analysis_status ?? data.status;
  if (status && status !== "ready") return false;
  return data.preview_ready === true || !!data.preview;
}

const FULL_PHASES = {
  awaiting_confirmation: ["Checking player identity", "Continuing automatically with your saved player marks. No extra taps are needed."],
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
  report_synthesis_start: "Writing your player assessment from the reviewed evidence",
  report_synthesis_complete: "Completing the player assessment",
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
    const livePhase = data.sequence_progress?.phase;
    if (livePhase === "writer") {
      key = "writing"; title = "Writing your player report"; detail = "Turning the reviewed actions into your player assessment and training advice.";
    } else if (livePhase === "preparation") {
      key = "analyzing"; title = "Preparing the action review"; detail = "Preparing your video and saved player marks for the review.";
    } else if (livePhase === "source") {
      key = "analyzing";
    }
  } else if (previewReady && full) {
    key = "queued"; title = "Preparing the full analysis";
    detail = "Your video is ready. Your full report is being prepared.";
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
  const analyzed = full ? ["verifying", "finalizing"].includes(st) || data.sequence_progress?.phase === "writer" || fullReady : previewReady;
  const labels = full ? ["Video received", "Reviewing play", "Final checks"] : ["Prepare video", "Create preview"];
  const states = full
    ? [prepared ? "done" : "active", analyzed ? "done" : prepared ? "active" : "pending", fullReady ? "done" : analyzed ? "active" : "pending"]
    : [prepared ? "done" : "active", previewReady ? "done" : prepared ? "active" : "pending"];
  return {
    key, title, detail, target: full ? "full" : "preview", complete: !duringUpload && complete,
    failed: key === "failed", confirmation: false,
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

/** A provisional window uses the retained 77s run until live server timing arrives. */
export function completionEstimate(data = {}, now = Date.now()) {
  const saved = data.completion_estimate;
  if (["estimated", "overdue"].includes(saved?.status) && Number.isFinite(Date.parse(saved.earliest_at))
      && Number.isFinite(Date.parse(saved.latest_at)) && Date.parse(saved.earliest_at) <= Date.parse(saved.latest_at)) return saved;
  const full = data.analysis_target !== "preview" && (data.analysis_target === "full" || data.is_paid || data.manually_unlocked || data.full_report_status);
  const duration = Number(data.video_duration_sec);
  const scale = Number.isFinite(duration) && duration > 0 ? Math.max(.5, Math.min(4, duration / 77)) : 1;
  const anchorValue = data.full_report_started_at || data.analysis_started_at || data.created_at;
  const anchor = typeof anchorValue === "number" ? anchorValue : Date.parse(anchorValue);
  const start = Number.isFinite(anchor) && anchor <= now ? anchor : now;
  const seconds = data.full_report_status ? 605 * scale + 178 + 39 * scale : 187 * scale + (full ? 605 * scale + 178 + 39 * scale : 0);
  return { status: "estimated", provisional: true, basis: "starting_workload", calculated_at: new Date(now).toISOString(),
    earliest_at: new Date(start + seconds * .75 * 1000).toISOString(), latest_at: new Date(start + seconds * 1.45 * 1000).toISOString() };
}

export function completionLabel(data, now = Date.now()) {
  const estimate = completionEstimate(data, now);
  const latest = Date.parse(estimate.latest_at), earliest = Date.parse(estimate.earliest_at);
  if (estimate.status === "overdue" || latest <= now) return "Longer than expected · updating";
  const low = Math.max(0, Math.ceil((earliest - now) / 60000));
  const high = Math.ceil((latest - now) / 60000);
  const label = low === 0 ? `Under ${high} min` : low === high ? `About ${high} min` : `About ${low}–${high} min`;
  const updated = Date.parse(estimate.calculated_at), heartbeat = Date.parse(data?.last_progress_at);
  const stale = (Number.isFinite(updated) && now - updated > 120000) || (Number.isFinite(heartbeat) && now - heartbeat > 120000);
  return stale ? `Last estimate: ${label}` : label;
}

export function completionClock(data, now = Date.now()) {
  const estimate = completionEstimate(data, now);
  if (Date.parse(estimate.latest_at) <= now) return "Review is still running";
  const format = value => new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${estimate.basis === "starting_workload" ? "Starting estimate" : "Expected finish"} ${format(estimate.earliest_at)}–${format(estimate.latest_at)}`;
}
