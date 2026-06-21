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

const STORAGE_KEY = "scoutmeplay.activeAnalysis";
const POLL_INTERVAL_MS = 5000;
const STAGE_LABELS = {
  1: "Receiving your video",
  2: "Checking the content",
  3: "Building your analysis",
  4: "Writing your scout report",
  5: "Finishing up",
};

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
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  /* Poll loop */
  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;

    const poll = async () => {
      try {
        const { data } = await api.get(`/reports/${active.id}/status`);
        if (cancelled) return;
        setStatus(data);
        if (data.status === "ready" && !didNotifyReady.current) {
          didNotifyReady.current = true;
          toast.success("Your scout report is ready!", {
            duration: 8000,
            action: {
              label: "View",
              onClick: () => navigate(`/report/${active.id}`),
            },
          });
          clear();
        } else if (data.status === "failed") {
          toast.error(data.error || "Analysis failed. Please try again.");
          clear();
        }
      } catch (err) {
        // Report deleted or 4xx → stop polling
        if (err?.response?.status && err.response.status >= 400 && err.response.status < 500) {
          clear();
        }
        // 5xx / network: just keep polling on the next tick
      }
    };

    poll();
    pollRef.current = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [active, navigate, clear]);

  /* Don't render while the user is on the upload page — the in-page overlay
     already shows progress there. Re-appears once they navigate away. */
  const onUploadPage = location.pathname === "/upload";

  if (!active || dismissed || onUploadPage || !status || status.status !== "analyzing") {
    return null;
  }

  const step = Math.max(1, Math.min(5, Number(status.progress_step) || 1));
  const pct = Math.round((step / 5) * 100);
  const label = STAGE_LABELS[step] || "Working…";

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
              Step {step} of 5 · Cooking
            </div>
            <div className="text-[13px] font-bold text-cream-card truncate leading-tight">{label}</div>
            <div className="mt-1.5 h-1 bg-white/15 overflow-hidden rounded-full">
              <div
                className="h-full bg-gradient-to-r from-forest via-forest-pop to-volt transition-all duration-700"
                style={{ width: `${pct}%` }}
              />
            </div>
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
          onClick={() => navigate("/dashboard")}
          className="w-full px-4 py-2 bg-white/5 hover:bg-volt hover:text-ink text-[10px] uppercase tracking-[0.22em] font-bold text-cream-card/85 border-t border-white/10 transition-colors"
        >
          Open dashboard
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
    // Self-expire after 30 min so stale entries don't haunt the user forever
    if (Date.now() - (parsed.startedAt || 0) > 30 * 60 * 1000) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}
