/**
 * BackgroundAnalysisTracker
 *
 * A globally-mounted floating pill that lets the user "Continue in background"
 * after they've kicked off a video analysis. It survives page navigation,
 * persists across reloads (via localStorage), and polls the report status
 * every 5 s until the report is ready or fails.
 *
 * Usage:
 *   - Mounted ONCE in App.js so it's available on every route.
 *   - Activated from anywhere via:
 *         import { startBackgroundAnalysis } from "@/components/BackgroundAnalysisTracker";
 *         startBackgroundAnalysis(reportId);
 *   - When the report is ready: shows a success toast with a "View" CTA + clears itself.
 *   - When the report fails:    shows an error toast + clears itself.
 *   - User can dismiss the pill at any time (analysis still runs server-side).
 */

import { useEffect, useState, useRef, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { X, FileText, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { getAnalysisView } from "../lib/analysisProgress.mjs";

const STORAGE_KEY = "scoutmeplay.activeAnalysis";
const POLL_INTERVAL_MS = 5000;

/* ---------- Public API: start tracking from anywhere ---------- */
export function startBackgroundAnalysis(reportId, meta = {}) {
  if (!reportId) return;
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ id: reportId, startedAt: Date.now(), ...meta })
    );
    window.dispatchEvent(new Event("scoutmeplay:bg-analysis-start"));
  } catch {
    /* localStorage may be blocked; the tracker just won't activate */
  }
}

/* ---------- Component ---------- */
export default function BackgroundAnalysisTracker() {
  const navigate = useNavigate();
  const location = useLocation();
  const [active, setActive] = useState(() => readStored());
  const [status, setStatus] = useState(null);
  const [connectionError, setConnectionError] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const pollRef = useRef(null);
  const didNotifyReady = useRef(false);

  /* React to programmatic .startBackgroundAnalysis() calls */
  useEffect(() => {
    const onStart = () => {
      setActive(readStored());
      setStatus(null);
      setDismissed(false);
      didNotifyReady.current = false;
    };
    window.addEventListener("scoutmeplay:bg-analysis-start", onStart);
    return () => window.removeEventListener("scoutmeplay:bg-analysis-start", onStart);
  }, []);

  const clear = useCallback(() => {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
    setActive(null);
    setStatus(null);
    if (pollRef.current) {
      clearTimeout(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  /* Poll loop */
  useEffect(() => {
    if (!active) return undefined;
    if (location.pathname === `/report/${active.id}` || location.pathname === "/dashboard") return undefined;
    let cancelled = false;
    let finished = false;

    const poll = async () => {
      try {
        const { data } = await api.get(`/reports/${active.id}/status`, { timeout: 15000 });
        if (cancelled) return;
        setStatus(data);
        setConnectionError(false);
        const view = getAnalysisView(data);
        if (view.complete && !didNotifyReady.current) {
          finished = true;
          didNotifyReady.current = true;
          toast.success(view.target === "full" ? "Your full scout report is ready!" : "Your initial preview is ready", {
            duration: 8000,
            action: {
              label: "View",
              onClick: () => navigate(`/report/${active.id}`),
            },
          });
          clear();
        } else if (view.failed) {
          finished = true;
          toast.error(view.detail);
          clear();
        }
      } catch (err) {
        if (cancelled) return;
        // Report deleted or 4xx → stop polling
        if (err?.response?.status >= 400 && err.response.status < 500 && ![408, 429].includes(err.response.status)) {
          finished = true;
          toast.error(err.response.status === 401 ? "Sign in again to check your analysis." : "The analysis status could not be accessed.");
          clear();
        }
        setConnectionError(true);
        // 5xx / network: just keep polling on the next tick
      } finally {
        if (!cancelled && !finished) pollRef.current = setTimeout(poll, POLL_INTERVAL_MS);
      }
    };

    poll();

    return () => {
      cancelled = true;
      if (pollRef.current) {
        clearTimeout(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [active, navigate, clear, location.pathname]);

  /* Don't render while the user is on the upload page — the in-page overlay
     already shows progress there. Re-appears once they navigate away. */
  const onUploadPage = location.pathname === "/upload";

  if (!active || dismissed || onUploadPage || location.pathname === "/dashboard" || location.pathname === `/report/${active.id}` || !status || getAnalysisView(status).complete || getAnalysisView(status).failed) {
    return null;
  }

  const view = getAnalysisView(status);

  return (
    <div
      data-testid="bg-analysis-tracker"
      className="fixed z-[65] pointer-events-auto"
      style={{
        right: 12,
        bottom: "calc(env(safe-area-inset-bottom, 0px) + 84px)",
        width: "min(320px, calc(100vw - 24px))",
      }}
    >
      <div
        className="bg-deepnavy border-2 border-volt overflow-hidden"
        style={{
          boxShadow:
            "0 18px 40px -10px rgba(8,18,12,0.55), 0 0 0 4px rgba(31,79,47,0.18), 0 0 30px rgba(204,255,0,0.18)",
        }}
      >
        <div className="p-3.5 flex items-center gap-3">
          <div className="relative w-9 h-9 flex-shrink-0">
            <Loader2 className="absolute inset-0 w-9 h-9 text-volt animate-spin" strokeWidth={1.5} />
            <FileText className="absolute inset-0 m-auto w-3.5 h-3.5 text-volt" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[9px] uppercase tracking-[0.22em] font-bold text-volt mb-0.5">
              {active.playerName || "Your video"} · {view.target === "full" ? "Full analysis" : "Initial review"}
            </div>
            <div className="text-[13px] font-bold text-cream-card leading-tight">{view.title}</div>
            {connectionError && <div className="mt-1 text-[10px] text-cream-card/70">Rechecking the connection</div>}
            {status?.retry_in_progress && (
              <div
                className="mt-1 text-[10px] text-amber-300/90 leading-tight italic"
                data-testid="bg-analysis-retry-hint"
              >
                The server is repeating the review
              </div>
            )}
          </div>
          <button
            type="button"
            aria-label="Dismiss tracker"
            data-testid="bg-tracker-dismiss"
            onClick={() => setDismissed(true)}
            className="text-cream-card/60 hover:text-cream-card p-1 transition-colors flex-shrink-0"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <button
          type="button"
          data-testid="bg-tracker-goto-dashboard"
          onClick={() => navigate(`/report/${active.id}`)}
          className="w-full px-4 py-2 bg-white/5 hover:bg-volt hover:text-ink text-[10px] uppercase tracking-[0.22em] font-bold text-cream-card/85 border-t border-white/10 transition-colors"
        >
          Follow your analysis
        </button>
      </div>
    </div>
  );
}

/* ---------- Helpers ---------- */
function readStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.id) return null;
    // Long analyses can outlast 30 minutes. Read server readiness after a
    // reload instead of discarding a still-active report prematurely.
    if (Date.now() - (parsed.startedAt || 0) > 7 * 24 * 60 * 60 * 1000) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}
