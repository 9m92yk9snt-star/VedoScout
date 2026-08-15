import React, { useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Radar, Loader2, ChevronDown, ChevronUp } from "lucide-react";

export default function CvShadowStats() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const toggle = async () => {
    if (open) return setOpen(false);
    setOpen(true);
    if (data) return;
    try {
      setLoading(true);
      const { data: d } = await api.get("/admin/cv-shadow/summary");
      setData(d);
    } catch {
      toast.error("Could not load shadow stats");
    } finally {
      setLoading(false);
    }
  };

  const agg = data?.aggregate;
  return (
    <div className="border border-gray-border mb-4">
      <button
        onClick={toggle}
        data-testid="cv-shadow-stats-toggle"
        className="w-full flex items-center justify-between px-4 py-2.5 text-left"
      >
        <span className="flex items-center gap-2 uppercase tracking-widest text-[11px] font-bold text-ink">
          <Radar className="w-4 h-4 text-volt" /> CV Shadow — cross-report validation
        </span>
        {open ? <ChevronUp className="w-4 h-4 text-ink/50" /> : <ChevronDown className="w-4 h-4 text-ink/50" />}
      </button>
      {open && (
        <div className="px-4 pb-4" data-testid="cv-shadow-stats-panel">
          {loading ? (
            <div className="flex items-center gap-2 text-ink/60 text-sm py-3">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading…
            </div>
          ) : !agg ? (
            <p className="text-sm text-ink/60 py-2">No shadow data yet.</p>
          ) : (
            <>
              <div className="flex flex-wrap gap-4 text-xs text-ink/75 border-b border-gray-border pb-3 mb-3" data-testid="cv-shadow-agg">
                <span><b>{agg.reports}</b> reports</span>
                <span><b>{agg.checked}</b> track checks</span>
                <span>identity match <b>{agg.sim_mean ?? "—"}</b></span>
                <span className={agg.suspect_rate > 0.15 ? "text-amber-600" : ""}>suspect rate <b>{Math.round((agg.suspect_rate || 0) * 100)}%</b></span>
                <span className={agg.switch_risk_frames > 0 ? "text-red-500" : ""}>switch-risk frames <b>{agg.switch_risk_frames}</b> ({Math.round((agg.switch_rate || 0) * 100)}%)</span>
              </div>
              <div className="space-y-1 max-h-56 overflow-y-auto">
                {data.reports.map((r) => (
                  <div key={r.report_id} className="flex flex-wrap items-center gap-x-4 gap-y-0.5 text-[11px] text-ink/65" data-testid={`cv-shadow-row-${r.report_id}`}>
                    <span className="font-bold text-ink w-28 truncate">{r.player}</span>
                    <span>v{r.engine_version}</span>
                    <span>{r.checked} checks</span>
                    <span>sim {r.sim_mean ?? "—"}</span>
                    <span>suspect {r.suspect_frames} ({Math.round((r.suspect_rate || 0) * 100)}%)</span>
                    <span className={r.switch_risk_frames > 0 ? "text-red-500" : ""}>switch {r.switch_risk_frames}</span>
                    <span className={r.empty_box_frames > 2 ? "text-purple-600" : ""}>empty {r.empty_box_frames ?? "—"}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
