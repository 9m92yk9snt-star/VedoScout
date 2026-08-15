import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { X, Radar, Loader2, Play } from "lucide-react";

const fmtT = (s) => {
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${String(Math.round(s - m * 60)).padStart(2, "0")}`;
};

const Stat = ({ label, value, warn }) => (
  <div className="border border-gray-border p-3 bg-surface">
    <div className="text-[10px] uppercase tracking-widest text-ink/50 font-bold">{label}</div>
    <div className={`text-lg font-bold ${warn ? "text-red-500" : "text-ink"}`}>{value ?? "—"}</div>
  </div>
);

export default function CvShadowDialog({ reportId, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const load = async (run = false) => {
    try {
      run ? setRunning(true) : setLoading(true);
      const { data: d } = await api.get(`/admin/reports/${reportId}/cv-shadow${run ? "?run=1" : ""}`, {
        timeout: run ? 300000 : 20000,
      });
      setData(d.cv_shadow);
      if (run) toast.success("Shadow analysis complete");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not load shadow diagnostics");
    } finally {
      setLoading(false);
      setRunning(false);
    }
  };
  useEffect(() => { load(); }, [reportId]); // eslint-disable-line

  const pv = data?.prod_verify;
  return (
    <div className="fixed inset-0 z-[95] bg-black/60 flex items-center justify-center p-4" data-testid="cv-shadow-dialog">
      <div className="bg-white max-w-2xl w-full max-h-[85vh] overflow-y-auto border border-gray-border">
        <div className="flex items-center justify-between p-4 border-b border-gray-border sticky top-0 bg-white">
          <div className="flex items-center gap-2">
            <Radar className="w-4 h-4 text-volt" />
            <span className="uppercase tracking-widest text-xs font-bold text-ink">CV Shadow Diagnostics</span>
            <span className="text-[10px] text-ink/45">observe-only · never affects reports</span>
          </div>
          <button onClick={onClose} data-testid="cv-shadow-close" className="p-2 text-ink/60 hover:text-ink">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-4 space-y-4">
          {loading ? (
            <div className="flex items-center gap-2 text-ink/60 text-sm p-6 justify-center">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading…
            </div>
          ) : !data || data.status !== "ok" ? (
            <div className="space-y-3">
              <p className="text-sm text-ink/65" data-testid="cv-shadow-empty">
                {data?.status ? `No usable shadow data (${data.reason || data.status}).` : "No shadow analysis stored for this report yet."}
              </p>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2" data-testid="cv-shadow-stats">
                <Stat label="Track checks" value={pv?.checked} />
                <Stat label="Identity match (mean)" value={pv?.sim_mean} />
                <Stat label="Suspect frames" value={`${pv?.suspect_frames ?? 0} (${Math.round((pv?.suspect_rate || 0) * 100)}%)`} warn={(pv?.suspect_rate || 0) > 0.2} />
                <Stat label="Switch-risk frames" value={pv?.switch_risk_frames} warn={(pv?.switch_risk_frames || 0) > 0} />
                <Stat label="Crowded frames" value={pv?.crowded_frames} />
                <Stat label="Tap self-verify" value={data.tap_self_verify} />
              </div>
              {(pv?.suspect_ts?.length > 0 || pv?.switch_ts?.length > 0) && (
                <div className="border border-gray-border p-3 space-y-2" data-testid="cv-shadow-moments">
                  {pv.switch_ts?.length > 0 && (
                    <div className="text-xs text-ink/70">
                      <span className="font-bold text-red-500 uppercase tracking-widest text-[10px]">Switch risk at:</span>{" "}
                      {pv.switch_ts.map((t) => fmtT(t)).join(", ")}
                    </div>
                  )}
                  {pv.suspect_ts?.length > 0 && (
                    <div className="text-xs text-ink/70">
                      <span className="font-bold text-amber-600 uppercase tracking-widest text-[10px]">Low identity match at:</span>{" "}
                      {pv.suspect_ts.map((x) => `${fmtT(x.t)} (${x.sim})`).join(", ")}
                    </div>
                  )}
                </div>
              )}
              <div className="text-[11px] text-ink/50 leading-relaxed">
                Taps: {data.taps?.length} · outliers {data.tap_outliers} · verified coverage {Math.round((data.verified_coverage || 0) * 100)}% ·
                crossovers {data.crossover_samples} · engine v{data.engine_version} · {data.compute_s}s
              </div>
              {data.scene && (
                <div className="text-[11px] text-ink/50 leading-relaxed border-t border-gray-border pt-2" data-testid="cv-shadow-scene">
                  Scene: detector {data.scene.detector ? "on" : "off"} · {data.scene.avg_persons} persons/frame ·
                  MOT tracks {data.scene.mot_tracks_created} · crossover events {data.scene.mot_crossover_events} ·
                  team {data.scene.team_ready ? `${data.scene.team_counts?.target_team}/${data.scene.team_counts?.opponent}/${data.scene.team_counts?.other} (own/opp/other)` : "not ready"} ·
                  negatives {data.scene.det_negatives}
                </div>
              )}
            </>
          )}
          <button
            onClick={() => load(true)}
            disabled={running}
            data-testid="cv-shadow-run-btn"
            className="w-full py-2.5 uppercase tracking-widest text-[11px] font-bold border border-volt text-volt hover:bg-volt hover:text-white transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            {running ? "Running (30–60s)…" : "Run shadow analysis now"}
          </button>
        </div>
      </div>
    </div>
  );
}
