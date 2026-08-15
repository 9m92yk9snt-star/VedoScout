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

const ShadowThumb = ({ reportId, entry, kind }) => {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let url;
    let alive = true;
    api.get(`/admin/reports/${reportId}/cv-shadow/frame/${entry.img}`, { responseType: "blob" })
      .then(({ data }) => {
        url = URL.createObjectURL(data);
        if (alive) setSrc(url);
      })
      .catch(() => {});
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [reportId, entry.img]);
  return (
    <div className="border border-gray-border bg-black/5" data-testid="cv-shadow-thumb">
      {src ? (
        <img src={src} alt={`${kind} at ${fmtT(entry.t)}`} className="w-full h-auto block" />
      ) : (
        <div className="aspect-[9/16] flex items-center justify-center">
          <Loader2 className="w-4 h-4 animate-spin text-ink/30" />
        </div>
      )}
      <div className={`px-1.5 py-1 text-[9px] font-bold uppercase tracking-wider ${kind === "SWITCH" ? "text-red-500" : "text-amber-600"}`}>
        {kind} · {fmtT(entry.t)} · {entry.sim}
      </div>
    </div>
  );
};

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
                      {pv.switch_ts.map((x) => fmtT(typeof x === "number" ? x : x.t)).join(", ")}
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
              {(() => {
                const thumbs = [
                  ...(pv?.switch_ts || []).filter((x) => x && x.img).map((x) => ({ ...x, kind: "SWITCH" })),
                  ...(pv?.suspect_ts || []).filter((x) => x && x.img).map((x) => ({ ...x, kind: "SUSPECT" })),
                ];
                if (!thumbs.length) return null;
                return (
                  <div data-testid="cv-shadow-gallery">
                    <div className="text-[10px] uppercase tracking-widest text-ink/50 font-bold mb-2">
                      Flagged moments — judge with your own eyes (yellow = production box, red = competing player)
                    </div>
                    <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                      {thumbs.map((x) => (
                        <ShadowThumb key={x.img} reportId={reportId} entry={x} kind={x.kind} />
                      ))}
                    </div>
                  </div>
                );
              })()}
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
