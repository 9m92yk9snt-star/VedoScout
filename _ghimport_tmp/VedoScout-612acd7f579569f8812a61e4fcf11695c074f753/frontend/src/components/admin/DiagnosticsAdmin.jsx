import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, RefreshCw, Activity } from "lucide-react";
import api from "@/lib/api";

const Row = ({ k, v, warn }) => (
  <div className="flex justify-between gap-4 py-2 border-b border-gray-border/50 text-sm">
    <span className="text-ink/55 uppercase tracking-wider text-xs font-bold">{k}</span>
    <span className={`font-mono text-right ${warn ? "text-red-400 font-bold" : "text-ink"}`}>{String(v ?? "–")}</span>
  </div>
);

export default function DiagnosticsAdmin() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/admin/diagnostics");
      setData(r.data);
    } catch {
      toast.error("Failed to load diagnostics");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  if (loading && !data) return <div className="py-16 text-center"><Loader2 className="w-6 h-6 animate-spin text-volt mx-auto" /></div>;
  if (!data) return null;

  const memLimit = data.memory?.cgroup_limit || "unknown";
  const lowMem = /MB$/.test(memLimit) && parseFloat(memLimit) < 1500;

  return (
    <div data-testid="admin-diagnostics" className="space-y-8">
      <div className="flex items-center justify-between">
        <h2 className="font-barlow font-black uppercase text-2xl tracking-tight flex items-center gap-2">
          <Activity className="w-5 h-5 text-volt" /> Pod diagnostics
        </h2>
        <button data-testid="diagnostics-refresh-btn" onClick={load}
          className="flex items-center gap-2 px-4 py-2 border border-gray-border text-xs uppercase tracking-widest font-bold hover:border-volt hover:text-volt transition-colors">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        <div className="border border-gray-border p-5">
          <p className="text-xs uppercase tracking-widest font-bold text-volt mb-3">Memory</p>
          <Row k="Pod limit" v={memLimit} warn={lowMem} />
          <Row k="Pod used now" v={data.memory?.cgroup_used} />
          <Row k="Backend RSS" v={data.memory?.backend_rss_mb ? `${data.memory.backend_rss_mb} MB` : "–"} />
          {lowMem && <p className="mt-3 text-xs text-red-400 font-bold">⚠ Limit under 1.5 GB — ffmpeg transcoding of 1080p video needs ~600-800 MB combined</p>}
        </div>
        <div className="border border-gray-border p-5">
          <p className="text-xs uppercase tracking-widest font-bold text-volt mb-3">CPU & Pod</p>
          <Row k="Visible cores" v={data.pod?.cpu_count} />
          <Row k="CPU limit (cores)" v={data.pod?.cpu_limit_cores ?? "no limit / unknown"} />
          <Row k="Hostname" v={data.pod?.hostname} />
          <Row k="Process started" v={data.pod?.process_started_utc?.slice(0, 19)} />
          <Row k="ffmpeg present" v={data.ffmpeg?.exists ? "yes" : "MISSING"} warn={!data.ffmpeg?.exists} />
        </div>
        <div className="border border-gray-border p-5">
          <p className="text-xs uppercase tracking-widest font-bold text-volt mb-3">Disk</p>
          <Row k="Total" v={data.disk?.total} />
          <Row k="Used" v={`${data.disk?.used || "–"} (${data.disk?.used_pct ?? "–"}%)`} warn={(data.disk?.used_pct || 0) > 85} />
          <Row k="Free" v={data.disk?.free} />
          <Row k="Uploads dir" v={data.disk?.uploads_dir_size} />
        </div>
      </div>

      <div>
        <p className="text-xs uppercase tracking-widest font-bold text-volt mb-3">Recent pipeline runs — last stage reached</p>
        <div className="border border-gray-border divide-y divide-gray-border/50">
          {(data.recent_reports || []).map((r) => (
            <div key={r.id} data-testid={`diag-report-${r.id}`} className="p-4">
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <span className={`px-2 py-0.5 text-xs font-black uppercase ${
                  r.analysis_status === "ready" ? "bg-volt/20 text-volt" :
                  r.analysis_status === "failed" ? "bg-red-500/20 text-red-400" : "bg-ink/10 text-ink/70"}`}>
                  {r.analysis_status}
                </span>
                <span className="font-bold">{r.player_name || "—"}</span>
                <span className="text-ink/40 font-mono text-xs">{(r.created_at || "").slice(0, 19)}</span>
                <span className="ml-auto font-mono text-xs text-ink/70">
                  last stage: <b className="text-ink">{r.last_stage || "none recorded"}</b>
                </span>
              </div>
              {r.analysis_error && <p className="mt-1 text-xs text-red-400">{r.analysis_error}</p>}
              {(r.trace || []).length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {r.trace.map((t, i) => (
                    <span key={i} className="px-1.5 py-0.5 bg-ink/8 text-[10px] font-mono text-ink/70" title={t.at}>
                      {t.s} <span className="text-ink/40">{(t.at || "").slice(11, 19)}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
