import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Clapperboard, Download, ExternalLink, Loader2, ShieldCheck } from "lucide-react";
import api from "@/lib/api";

export default function FeaturedClipsAdmin() {
  const [clips, setClips] = useState(null);
  const [downloading, setDownloading] = useState(null);

  useEffect(() => {
    api.get("/admin/featured-clips")
      .then(({ data }) => setClips(data.clips || []))
      .catch(() => setClips([]));
  }, []);

  const downloadClip = async (c) => {
    setDownloading(c.report_id);
    try {
      const res = await api.get(`/reports/${c.report_id}/intro-clip.mp4`, { responseType: "blob", timeout: 120000 });
      const url = URL.createObjectURL(new Blob([res.data], { type: "video/mp4" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `ScoutMePlay_${(c.player_name || "player").replace(/[^A-Za-z0-9]+/g, "_")}_Intro.mp4`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Intro clip downloaded — ready to post!");
    } catch (err) {
      toast.error(err?.response?.status === 400
        ? "Full report not generated yet — clip needs a premium report."
        : "Could not generate the clip. Try again.");
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div data-testid="featured-clips-admin" className="mb-10 border border-gray-border bg-surface">
      <div className="px-6 py-5 border-b border-gray-border">
        <div className="flex items-center gap-2">
          <Clapperboard className="w-5 h-5 text-volt" />
          <h3 className="font-barlow font-black uppercase tracking-tight text-xl text-ink">Featured clips — social consent</h3>
        </div>
        <p className="mt-1.5 text-sm text-ink/60 flex items-center gap-1.5">
          <ShieldCheck className="w-4 h-4 text-forest shrink-0" />
          Only players with ACTIVE consent (ticked at upload + account toggle on) appear here. Never post clips from anywhere else.
        </p>
      </div>

      {clips === null ? (
        <div className="py-10 text-center"><Loader2 className="w-5 h-5 animate-spin text-volt mx-auto" /></div>
      ) : clips.length === 0 ? (
        <p className="px-6 py-8 text-sm text-ink/50" data-testid="featured-clips-empty">
          No consented clips yet. When users tick "feature my intro clip" at upload, they show up here.
        </p>
      ) : (
        <div className="divide-y divide-gray-border">
          {clips.map((c) => (
            <div key={c.report_id} data-testid={`featured-clip-row-${c.report_id}`} className="px-6 py-4 flex flex-wrap items-center gap-3">
              <div className="flex-1 min-w-[180px]">
                <div className="font-bold text-ink text-sm">{c.player_name || "Unknown player"}{c.age ? ` · ${c.age} yrs` : ""}</div>
                <div className="text-[11.5px] text-ink/50">{c.user_email} · consented {c.granted_at ? new Date(c.granted_at).toLocaleDateString("en-GB") : "—"}</div>
              </div>
              <span className={`text-[10px] uppercase tracking-[0.12em] font-black px-2.5 py-1 ${c.full_report_ready ? "bg-forest/10 text-forest" : "bg-amber-100 text-amber-800"}`}>
                {c.full_report_ready ? "Clip ready" : "Preview only"}
              </span>
              <button
                type="button"
                onClick={() => downloadClip(c)}
                disabled={!c.full_report_ready || downloading === c.report_id}
                data-testid={`featured-clip-download-${c.report_id}`}
                title={c.full_report_ready ? "Download the shareable intro clip (MP4)" : "Needs a full premium report first"}
                className="inline-flex items-center gap-1.5 bg-forest hover:bg-forest-pop text-white text-[11px] font-black uppercase tracking-widest px-3.5 py-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {downloading === c.report_id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                Intro clip
              </button>
              <a
                href={`/report/${c.report_id}`}
                target="_blank"
                rel="noreferrer"
                data-testid={`featured-clip-open-${c.report_id}`}
                className="inline-flex items-center gap-1.5 border border-ink/20 hover:border-forest text-ink/70 hover:text-forest text-[11px] font-black uppercase tracking-widest px-3.5 py-2 transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" /> Report
              </a>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
