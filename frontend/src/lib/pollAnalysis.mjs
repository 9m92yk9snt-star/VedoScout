import { isFullReportReady } from "./reportReady.mjs";
import { isPreviewReady } from "./analysisProgress.mjs";

const terminal = (message, kind) => Object.assign(new Error(message), { analysisTerminal: true, kind });

/** One read-only polling policy for preview and full report. Injectable clock
 * and wait make long, interrupted runs testable without real model calls.
 */
export async function pollAnalysis(api, id, {
  target = "full", onStatus = () => {}, onConnectionError = () => {},
  isCancelled = () => false, now = Date.now,
  wait = ms => new Promise(resolve => setTimeout(resolve, ms)),
  noProgressMs = 20 * 60_000, maxRunMs = 2 * 60 * 60_000,
} = {}) {
  const start = now();
  let lastProgress = start, heartbeat = null;
  while (now() - start < maxRunMs && !isCancelled()) {
    try {
      const { data } = await api.get(`/reports/${id}/status`, { timeout: 15000 });
      if (isCancelled()) return null;
      onConnectionError(null);
      onStatus(data);
      if (target === "full" ? isFullReportReady(data) : isPreviewReady(data)) return data;
      if (data?.analysis_status === "failed" || data?.status === "failed" || (target === "full" && data?.full_report_status === "failed")) {
        throw terminal((target === "full" && data.full_report_error) || data.analysis_error || data.error || "Analysis was interrupted. Please try again.", "failed");
      }
      if (data?.last_progress_at && data.last_progress_at !== heartbeat) {
        heartbeat = data.last_progress_at;
        const serverTime = Date.parse(heartbeat);
        if (Number.isFinite(serverTime) && serverTime <= now() + 60_000 && now() - serverTime < noProgressMs) lastProgress = now();
      }
    } catch (error) {
      if (isCancelled()) return null;
      const status = error?.response?.status;
      if (error.analysisTerminal) throw error;
      if (status >= 400 && status < 500 && ![408, 429].includes(status)) {
        throw terminal(status === 401 ? "Please sign in again to check your analysis." : error?.response?.data?.detail || "The analysis status could not be accessed.", "access");
      }
      onConnectionError("Connection interrupted. Rechecking the status; this does not restart your analysis.");
    }
    if (now() - lastProgress >= noProgressMs) {
      throw terminal("Analysis has not reported progress for 20 minutes. Check the status again before retrying.", "stalled");
    }
    await wait(4500);
  }
  if (isCancelled()) return null;
  throw terminal("This analysis is taking longer than usual. Check the status again to continue following it.", "timeout");
}
